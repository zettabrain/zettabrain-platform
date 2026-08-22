"""Model request workflow — managers request, admins approve."""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..deps import CurrentUser, SessionDep, get_team_membership
from ..models import (
    ModelRequest,
    ModelRequestCreate,
    ModelRequestRead,
    ModelRequestStatus,
    Team,
    TeamMember,
    TeamModelConfigRead,
    TeamRole,
    User,
)
from ..routers.settings import get_setting

router = APIRouter(prefix="/api/teams", tags=["model-requests"])


def _validate_model_config(
    llm_provider: str | None,
    llm_model: str | None,
    embed_provider: str | None,
    embed_model: str | None,
) -> None:
    has_llm = llm_provider is not None or llm_model is not None
    has_embed = embed_provider is not None or embed_model is not None

    if not has_llm and not has_embed:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one model configuration (LLM or embedding)"
        )

    if has_llm:
        if llm_provider and not llm_model:
            raise HTTPException(status_code=400, detail="llm_model is required when llm_provider is set")
        if llm_model and not llm_provider:
            raise HTTPException(status_code=400, detail="llm_provider is required when llm_model is set")

    if has_embed:
        if embed_provider and not embed_model:
            raise HTTPException(status_code=400, detail="embed_model is required when embed_provider is set")
        if embed_model and not embed_provider:
            raise HTTPException(status_code=400, detail="embed_provider is required when embed_model is set")


def _validate_provider_credentials(session: Any, llm_provider: str | None, embed_provider: str | None) -> None:
    if llm_provider == "openai" or embed_provider == "openai":
        openai_key = get_setting(session, "openai_api_key")
        if not openai_key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key not configured. Ask admin to configure it in system settings."
            )

    if llm_provider == "claude":
        anthropic_key = get_setting(session, "anthropic_api_key")
        if not anthropic_key:
            raise HTTPException(
                status_code=400,
                detail="Anthropic API key not configured. Ask admin to configure it in system settings."
            )


def _build_model_request_read(
    req: ModelRequest,
    team: Team,
    requester: User,
    reviewer: User | None = None,
) -> ModelRequestRead:
    return ModelRequestRead(
        id=req.id,
        team_id=req.team_id,
        team_name=team.name,
        requester_id=req.requester_id,
        requester_username=requester.username,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
        embed_provider=req.embed_provider,
        embed_model=req.embed_model,
        justification=req.justification,
        status=req.status,
        reviewed_by=req.reviewed_by,
        reviewer_username=reviewer.username if reviewer else None,
        reviewed_at=req.reviewed_at,
        rejection_reason=req.rejection_reason,
        created_at=req.created_at,
    )


@router.post("/{team_id}/model-requests", response_model=ModelRequestRead)
def create_model_request(
    team_id: int,
    body: ModelRequestCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> ModelRequestRead:
    membership = get_team_membership(team_id, current_user, session)
    if membership.team_role != TeamRole.manager:
        raise HTTPException(status_code=403, detail="Team manager role required")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    _validate_model_config(body.llm_provider, body.llm_model, body.embed_provider, body.embed_model)
    _validate_provider_credentials(session, body.llm_provider, body.embed_provider)

    existing = session.exec(
        select(ModelRequest)
        .where(ModelRequest.team_id == team_id)
        .where(ModelRequest.status == ModelRequestStatus.pending)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Team already has a pending model request. Wait for admin review."
        )

    request = ModelRequest(
        team_id=team_id,
        requester_id=current_user.id,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        embed_provider=body.embed_provider,
        embed_model=body.embed_model,
        justification=body.justification,
        status=ModelRequestStatus.pending,
    )
    session.add(request)
    session.commit()
    session.refresh(request)

    try:
        from .notifications import notify_new_request
        notify_new_request(request, session)
    except Exception:
        pass

    return _build_model_request_read(request, team, current_user)


@router.get("/{team_id}/model-requests", response_model=List[ModelRequestRead])
def list_team_model_requests(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> List[ModelRequestRead]:
    membership = get_team_membership(team_id, current_user, session)
    if membership.team_role != TeamRole.manager:
        raise HTTPException(status_code=403, detail="Team manager role required")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    requests = session.exec(
        select(ModelRequest)
        .where(ModelRequest.team_id == team_id)
        .order_by(ModelRequest.created_at.desc())
    ).all()

    result = []
    for req in requests:
        requester = session.get(User, req.requester_id)
        reviewer = session.get(User, req.reviewed_by) if req.reviewed_by else None
        if requester:
            result.append(_build_model_request_read(req, team, requester, reviewer))
    return result


@router.get("/{team_id}/models", response_model=TeamModelConfigRead)
def get_team_models(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> TeamModelConfigRead:
    get_team_membership(team_id, current_user, session)

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    llm_provider = team.llm_provider or get_setting(session, "llm_provider")
    llm_model = team.llm_model or get_setting(session, "llm_model")
    embed_provider = team.embed_provider or get_setting(session, "embed_provider")
    embed_model = team.embed_model or get_setting(session, "embed_model")

    return TeamModelConfigRead(
        team_id=team.id,
        team_name=team.name,
        llm_provider=llm_provider,
        llm_model=llm_model,
        embed_provider=embed_provider,
        embed_model=embed_model,
        llm_from_team=team.llm_provider is not None,
        embed_from_team=team.embed_provider is not None,
    )


@router.post("/{team_id}/model-requests/{request_id}/apply")
def apply_approved_model_config(
    team_id: int,
    request_id: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    membership = get_team_membership(team_id, current_user, session)
    if membership.team_role != TeamRole.manager:
        raise HTTPException(status_code=403, detail="Team manager role required")

    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    request = session.get(ModelRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Model request not found")
    if request.team_id != team_id:
        raise HTTPException(status_code=403, detail="Request does not belong to this team")
    if request.status != ModelRequestStatus.approved:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot apply {request.status} request. Only approved requests can be applied."
        )

    embed_changing = False
    if request.embed_provider and request.embed_model:
        embed_changing = (
            team.embed_provider != request.embed_provider
            or team.embed_model != request.embed_model
        )

    if request.llm_provider and request.llm_model:
        team.llm_provider = request.llm_provider
        team.llm_model = request.llm_model

    if request.embed_provider and request.embed_model:
        team.embed_provider = request.embed_provider
        team.embed_model = request.embed_model

    session.add(team)
    session.commit()

    if embed_changing:
        try:
            from ..config import CHROMA_DIR
            team_chroma = CHROMA_DIR / team.slug
            if team_chroma.exists():
                import chromadb
                client = chromadb.PersistentClient(path=str(team_chroma))
                try:
                    client.delete_collection("zettabrain_docs")
                except Exception:
                    pass
                client.get_or_create_collection("zettabrain_docs")
                for fname in ("ingested_files.json", "bm25_index.pkl"):
                    stale = team_chroma / fname
                    if stale.exists():
                        stale.unlink()
        except Exception:
            import logging
            logging.error(f"Failed to auto-clear vector store for team {team.id}")

    return {
        "success": True,
        "message": "Model configuration applied successfully",
        "embed_changed": embed_changing,
        "llm_provider": team.llm_provider,
        "llm_model": team.llm_model,
        "embed_provider": team.embed_provider,
        "embed_model": team.embed_model,
    }
