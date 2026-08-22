"""Conversational AI endpoint — RAG-powered Q&A against team documents."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..deps import CurrentUser, SessionDep
from ..models import AuditLog, ChatRequest, ChatResponse, SystemRole, Team, TeamMember
from ..provenance import sign_bundle
from ..retrieval.rag import query_team

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

    from ..llm.model_resolver import resolve_team_models
    config = resolve_team_models(session, team.id)

    try:
        result = query_team(
            team_slug=team.slug,
            question=body.question,
            llm_provider=config["llm_provider"],
            embed_provider=config["embed_provider"],
            llm_model=config["llm_model"],
            embed_model=config["embed_model"],
            ollama_host=config["ollama_host"],
            openai_key=config["openai_key"],
            anthropic_key=config["anthropic_key"],
        )
    except Exception as e:
        error_msg = str(e)
        if "dimension" in error_msg.lower() and "expecting" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail="Vector dimension mismatch — clear vector store and re-ingest.",
            )
        raise HTTPException(status_code=400, detail=f"Query failed: {error_msg[:200]}")

    llm_provider = config["llm_provider"]
    llm_model = config["llm_model"]
    embed_provider = config["embed_provider"]
    embed_model = config["embed_model"]
    model_str = f"{llm_provider}:{llm_model}+{embed_provider}:{embed_model}"

    query_hash   = result.get("query_hash") or ""
    chunk_hashes = result.get("chunk_hashes") or []
    answer_hash  = result.get("answer_hash") or ""

    prov_sig = sign_bundle(
        query_hash=query_hash,
        chunk_hashes=chunk_hashes,
        answer_hash=answer_hash,
        team_id=body.team_id,
        model=model_str,
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
