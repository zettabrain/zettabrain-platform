from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import SQLModel, select

from ..deps import SessionDep, get_team_membership
from ..models import AuditLog, Team, TeamMember, TeamRole
from ..rag import ingest_team_docs
from ..routers.settings import get_setting

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


class IngestRequest(SQLModel):
    folder: Optional[str] = None


def _can_ingest(membership: TeamMember) -> bool:
    return membership.team_role in (TeamRole.manager,)


@router.post("/{team_id}")
def trigger_ingest(
    team_id: int,
    body: IngestRequest,
    membership: Annotated[TeamMember, Depends(get_team_membership)],
    session: SessionDep,
):
    if not _can_ingest(membership):
        raise HTTPException(status_code=403, detail="Manager role required to ingest")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    folder = body.folder if body.folder else team.docs_folder
    if not folder:
        raise HTTPException(
            status_code=400,
            detail="No docs folder specified. Set docs_folder on the team or pass folder in request body.",
        )

    from pathlib import Path
    if not Path(folder).exists():
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")

    # Resolve team-level model configuration (with fallback to system defaults)
    from ..model_resolver import resolve_team_models
    config = resolve_team_models(session, team.id)

    try:
        result = ingest_team_docs(
            team_slug=team.slug,
            folder=folder,
            embed_provider=config["embed_provider"],
            embed_model=config["embed_model"],
            ollama_host=config["ollama_host"],
            openai_key=config["openai_key"],
            multi_embed_enabled=team.multi_embed_enabled,
        )
        output = (
            f"Ingested {result['files_ingested']} file(s), "
            f"skipped {result['files_skipped']} unchanged. "
            f"Total chunks in store: {result['total_chunks']}."
        )
        if result["errors"]:
            output += f" Errors: {'; '.join(result['errors'][:3])}"
        success = True
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
        # Handle dimension mismatch errors (embedding provider changed)
        elif "dimension" in str(e).lower() and "expecting" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    "❌ Vector dimension mismatch - The embedding provider was changed. "
                    "Clear Vector Store first, then try ingesting again. "
                    "Different embedding providers use different vector dimensions (Ollama: 768, OpenAI small: 1536, OpenAI large: 3072)."
                )
            )
        else:
            # Re-raise with 400 so UI can display the message
            raise HTTPException(status_code=400, detail=f"❌ Ingest failed: {str(e)[:200]}")

    log = AuditLog(
        user_id          = membership.user_id,
        team_id          = team_id,
        action           = "ingest",
        query            = folder,
        response_preview = output[:200],
    )
    session.add(log)
    session.commit()

    if not success:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {output}")

    return {"status": "ok", "output": output, "details": result}
