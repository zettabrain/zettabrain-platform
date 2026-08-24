from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..deps import CurrentUser, SessionDep
from ..models import AuditLog, ChatHistory, ChatRequest, ChatResponse, SystemRole, Team, TeamMember
from ..provenance import sign_bundle
from ..rag import query_team
from ..routers.settings import get_setting

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    current_user: CurrentUser,
    session: SessionDep,
):
    membership = session.exec(
        select(TeamMember).where(
            TeamMember.user_id == current_user.id,
            TeamMember.team_id == body.team_id,
        )
    ).first()
    team = session.get(Team, body.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.system_role != SystemRole.admin and not membership:
        raise HTTPException(status_code=403, detail="Not a team member")

    # Resolve team-level model configuration (with fallback to system defaults)
    from ..model_resolver import resolve_team_models
    config = resolve_team_models(session, team.id)

    # Extract variables for later use
    llm_provider = config["llm_provider"]
    llm_model = config["llm_model"]
    embed_provider = config["embed_provider"]
    embed_model = config["embed_model"]

    try:
        result = query_team(
            team_slug=team.slug,
            question=body.question,
            llm_provider=llm_provider,
            embed_provider=embed_provider,
            llm_model=llm_model,
            embed_model=embed_model,
            ollama_host=config["ollama_host"],
            openai_key=config["openai_key"],
            anthropic_key=config["anthropic_key"],
            cloud_api_key=config.get("cloud_api_key"),
            multi_embed_enabled=team.multi_embed_enabled,
        )
    except Exception as e:
        # Handle Ollama-specific errors
        error_str = str(e)
        if "not found, try pulling it" in error_str or ("404" in error_str and "ollama" in error_str.lower()):
            raise HTTPException(
                status_code=400,
                detail="❌ Model not found — the configured Ollama model has not been pulled. Ask your admin to pull it via System Config."
            )
        elif "does not support" in error_str.lower() and "embedding" in error_str.lower():
            raise HTTPException(
                status_code=400,
                detail="❌ This model does not support embeddings. Please choose a model designed for embeddings (e.g. nomic-embed-text)."
            )
        # Handle OpenAI API errors with user-friendly messages
        elif "openai" in str(type(e).__module__):
            error_msg = str(e)
            if "429" in error_msg or "insufficient_quota" in error_msg:
                raise HTTPException(
                    status_code=400,
                    detail="❌ OpenAI quota exceeded - Your OpenAI account has insufficient credits. Please add credits at: https://platform.openai.com/settings/organization/billing/overview"
                )
            elif "401" in error_msg or "Incorrect API key" in error_msg or "invalid_api_key" in error_msg:
                raise HTTPException(
                    status_code=400,
                    detail="❌ OpenAI API key invalid - Please check your API key in System Config. Get your key at: https://platform.openai.com/api-keys"
                )
            elif "rate_limit" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="⚠️ OpenAI rate limit exceeded - Please wait a moment and try again."
                )
            else:
                raise HTTPException(status_code=400, detail=f"❌ OpenAI API error: {error_msg[:200]}")

        # Handle Anthropic/Claude API errors with user-friendly messages
        elif "anthropic" in str(type(e).__module__):
            error_msg = str(e)
            if "401" in error_msg or "invalid x-api-key" in error_msg.lower() or "authentication" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="❌ Claude API key invalid - Please check your API key in System Config. Get your key at: https://console.anthropic.com/settings/keys"
                )
            elif "429" in error_msg or "rate_limit" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="⚠️ Claude rate limit exceeded - Please wait a moment and try again."
                )
            elif "insufficient_quota" in error_msg or "quota" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="❌ Claude quota exceeded - Your Anthropic account has insufficient credits. Please check your billing at: https://console.anthropic.com/settings/billing"
                )
            elif "400" in error_msg and "temperature" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="⚠️ Claude model configuration error - Temperature parameter issue. Please contact support."
                )
            else:
                raise HTTPException(status_code=400, detail=f"❌ Claude API error: {error_msg[:200]}")

        # Handle dimension mismatch errors (embedding provider changed)
        elif "dimension" in str(e).lower() and "expecting" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    "❌ Vector dimension mismatch - The embedding provider was changed but documents were not re-ingested. "
                    "Go to Admin → Teams & Storage, then: 1) Clear Vector Store, 2) Ingest Docs. "
                    "Different embedding providers use different vector dimensions (Ollama: 768, OpenAI small: 1536, OpenAI large: 3072)."
                )
            )

        # Re-raise other errors as 400 (client can see the message)
        else:
            raise HTTPException(status_code=400, detail=f"❌ Query failed: {str(e)[:200]}")

    model_str    = f"{llm_provider}:{llm_model}+{embed_provider}:{embed_model}"
    query_hash   = result.get("query_hash") or ""
    chunk_hashes = result.get("chunk_hashes") or []
    answer_hash  = result.get("answer_hash") or ""

    prov_sig = sign_bundle(
        query_hash   = query_hash,
        chunk_hashes = chunk_hashes,
        answer_hash  = answer_hash,
        team_id      = body.team_id,
        model        = model_str,
    )

    log = AuditLog(
        user_id          = current_user.id,
        team_id          = body.team_id,
        action           = "chat",
        query            = body.question,
        response_preview = result["answer"][:200],
        chunks_used      = result["chunks"],
        model            = model_str,
        confidence       = result["confidence"],
        duration_ms      = result["duration_ms"],
        query_hash       = query_hash or None,
        chunk_hashes     = json.dumps(chunk_hashes) if chunk_hashes else None,
        answer_hash      = answer_hash or None,
        provenance_sig   = prov_sig or None,
    )
    session.add(log)

    chat_record = ChatHistory(
        user_id=current_user.id,
        team_id=body.team_id,
        question=body.question,
        answer=result["answer"],
        confidence=result["confidence"],
        chunks_used=result["chunks"],
        sources=json.dumps(result["sources"]) if result.get("sources") else None,
        duration_ms=result["duration_ms"],
    )
    session.add(chat_record)
    session.commit()

    answer = result["answer"]
    if result.get("below_threshold"):
        answer = (
            f"{answer}\n\n"
            "_Note: confidence is low — the answer may not be fully grounded in your documents._"
        )

    return ChatResponse(
        answer      = answer,
        confidence  = result["confidence"],
        chunks      = result["chunks"],
        duration_ms = result["duration_ms"],
        sources     = result["sources"],
    )


@router.get("/history/{team_id}")
def list_chat_history(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    limit: int = 50,
):
    """List chat history for a team (current user's messages)."""
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.system_role != SystemRole.admin:
        membership = session.exec(
            select(TeamMember).where(
                TeamMember.user_id == current_user.id,
                TeamMember.team_id == team_id,
            )
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Not a team member")

    rows = session.exec(
        select(ChatHistory)
        .where(ChatHistory.team_id == team_id, ChatHistory.user_id == current_user.id)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    ).all()

    return [
        {
            "id": r.id,
            "question": r.question,
            "answer": r.answer[:300],
            "confidence": r.confidence,
            "chunks_used": r.chunks_used,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/history/{team_id}/{history_id}")
def get_chat_detail(
    team_id: int,
    history_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    """Get full details of a chat history record."""
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.system_role != SystemRole.admin:
        membership = session.exec(
            select(TeamMember).where(
                TeamMember.user_id == current_user.id,
                TeamMember.team_id == team_id,
            )
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Not a team member")

    record = session.get(ChatHistory, history_id)
    if not record or record.team_id != team_id:
        raise HTTPException(status_code=404, detail="Record not found")

    return {
        "id": record.id,
        "question": record.question,
        "answer": record.answer,
        "confidence": record.confidence,
        "chunks_used": record.chunks_used,
        "sources": json.loads(record.sources) if record.sources else [],
        "duration_ms": record.duration_ms,
        "created_at": record.created_at.isoformat(),
    }
