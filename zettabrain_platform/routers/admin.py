from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from ..auth import hash_password
from ..database import get_session
from ..deps import AdminUser, SessionDep
from ..models import (
    AuditLog,
    ModelRequest,
    ModelRequestRead,
    ModelRequestReject,
    ModelRequestStatus,
    SystemRole,
    Team,
    TeamMember,
    TeamModelConfig,
    User,
    UserCreate,
    UserRead,
)
from ..provenance import get_public_key_hex, verify_bundle
from ..license import parse_license_key, LicenseState

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserRead])
def list_users(_: AdminUser, session: SessionDep):
    return session.exec(select(User)).all()


@router.post("/users", response_model=UserRead)
def create_user(body: UserCreate, _: AdminUser, session: SessionDep):
    from .. import state
    username = body.username.strip()
    email    = body.email.strip()
    password = body.password

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status_code=409, detail="Email already in use")

    max_users = state.license_info.get("max_users")
    if max_users is not None:
        current_count = session.exec(select(func.count(User.id))).one()
        if current_count >= max_users:
            raise HTTPException(
                status_code=403,
                detail=f"User seat limit reached ({max_users}). Upgrade your license to add more users.",
            )

    user = User(
        username  = username,
        email     = email,
        hashed_pw = hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, current_user: AdminUser, session: SessionDep):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.system_role == SystemRole.admin:
        admin_count = session.exec(
            select(func.count(User.id)).where(User.system_role == SystemRole.admin)
        ).one()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin account")

    for m in session.exec(select(TeamMember).where(TeamMember.user_id == user_id)).all():
        session.delete(m)

    session.delete(user)
    session.commit()


@router.patch("/users/{user_id}/role", response_model=UserRead)
def set_user_role(user_id: int, role: SystemRole, _: AdminUser, session: SessionDep):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.system_role = role
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.patch("/users/{user_id}/active", response_model=UserRead)
def set_user_active(user_id: int, active: bool, _: AdminUser, session: SessionDep):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = active
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.get("/audit")
def get_audit_log(
    _: AdminUser,
    session: SessionDep,
    limit:   int                = 1000,
    team_id: Optional[int]      = None,
    user_id: Optional[int]      = None,
    since:   Optional[datetime] = None,
    until:   Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    # Build name lookup maps (small tables — fine to load in full)
    user_map = {u.id: u.username for u in session.exec(select(User)).all()}
    team_map = {t.id: t.name     for t in session.exec(select(Team)).all()}

    q = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if team_id is not None:
        q = q.where(AuditLog.team_id == team_id)
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)
    if since is not None:
        q = q.where(AuditLog.timestamp >= since)
    if until is not None:
        q = q.where(AuditLog.timestamp <= until)

    logs = session.exec(q).all()
    return [
        {
            "id":               log.id,
            "timestamp":        log.timestamp.isoformat(),
            "action":           log.action,
            "user_id":          log.user_id,
            "username":         user_map.get(log.user_id, f"#{log.user_id}") if log.user_id else None,
            "team_id":          log.team_id,
            "team_name":        team_map.get(log.team_id, f"#{log.team_id}") if log.team_id else None,
            "query":            log.query,
            "response_preview": log.response_preview,
            "confidence":       log.confidence,
            "duration_ms":      log.duration_ms,
            "chunks_used":      log.chunks_used,
            "model":            log.model,
            "query_hash":       log.query_hash,
            "answer_hash":      log.answer_hash,
            "provenance_sig":   log.provenance_sig,
        }
        for log in logs
    ]


@router.get("/keys/public")
def get_server_public_key(_: AdminUser):
    """Return the server's Ed25519 public key for out-of-band verification."""
    return {"public_key_hex": get_public_key_hex(), "algorithm": "Ed25519"}


@router.get("/audit/{log_id}/verify")
def verify_audit_log(log_id: int, _: AdminUser, session: SessionDep):
    """Verify the cryptographic provenance signature on an audit log entry."""
    log = session.get(AuditLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    if not log.provenance_sig:
        return {
            "verified":       False,
            "log_id":         log_id,
            "reason":         "No provenance signature stored for this entry",
            "query_hash":     None,
            "answer_hash":    None,
            "chunk_hashes":   [],
            "signature_hex":  None,
            "public_key_hex": get_public_key_hex(),
            "canonical_payload": None,
        }

    chunk_hashes = json.loads(log.chunk_hashes or "[]")
    ok = verify_bundle(
        query_hash    = log.query_hash or "",
        chunk_hashes  = chunk_hashes,
        answer_hash   = log.answer_hash or "",
        team_id       = log.team_id,
        model         = log.model or "",
        signature_hex = log.provenance_sig,
    )

    canonical_obj = {
        "answer_hash":  log.answer_hash or "",
        "chunk_hashes": sorted(chunk_hashes),
        "model":        log.model or "",
        "query_hash":   log.query_hash or "",
        "team_id":      log.team_id,
    }

    return {
        "verified":          ok,
        "log_id":            log_id,
        "reason":            "Signature valid — answer bundle is tamper-evident" if ok
                             else "Signature mismatch — bundle may have been altered",
        "query_hash":        log.query_hash,
        "answer_hash":       log.answer_hash,
        "chunk_hashes":      chunk_hashes,
        "signature_hex":     log.provenance_sig,
        "public_key_hex":    get_public_key_hex(),
        "model":             log.model,
        "team_id":           log.team_id,
        "timestamp":         log.timestamp.isoformat(),
        "query_preview":     log.query,
        "canonical_payload": json.dumps(canonical_obj, sort_keys=True, separators=(",", ":")),
    }


@router.get("/stats")
def get_stats(_: AdminUser, session: SessionDep):
    from .. import state
    total_users  = session.exec(select(func.count(User.id))).one()
    total_teams  = session.exec(select(func.count(Team.id))).one()
    total_chats  = session.exec(
        select(func.count(AuditLog.id)).where(AuditLog.action == "chat")
    ).one()
    avg_conf = session.exec(
        select(func.avg(AuditLog.confidence)).where(AuditLog.action == "chat")
    ).one()
    return {
        "users":            total_users,
        "teams":            total_teams,
        "total_queries":    total_chats,
        "avg_confidence":   round(avg_conf or 0.0, 3),
        "license_state":    state.license_info.get("state"),
        "licensed":         state.license_info.get("licensed", False),
        "plan":             state.license_info.get("plan", "trial"),
        "days_left":        state.license_info.get("days_left"),
        "expires_at":       state.license_info.get("expires_at"),
        "max_users":        state.license_info.get("max_users"),
        "max_teams":        state.license_info.get("max_teams"),
        "customer":         state.license_info.get("customer"),
    }


@router.get("/license")
def get_license(_: AdminUser):
    from .. import state
    return state.license_info


@router.post("/license")
def upload_license(body: dict, _: AdminUser, session: SessionDep):
    from .. import state
    key_str = (body.get("key") or "").strip()
    if not key_str:
        raise HTTPException(status_code=400, detail="License key is required")

    payload = parse_license_key(key_str)
    if payload is None:
        raise HTTPException(status_code=422, detail="Invalid or tampered license key")

    from ..models import SystemConfig
    row = session.get(SystemConfig, "license_key")
    if row:
        row.value = key_str
        session.add(row)
    else:
        session.add(SystemConfig(key="license_key", value=key_str))
    session.commit()

    from ..config import DATA_DIR
    from ..license import check_startup
    state.license_info = check_startup(DATA_DIR, session)
    return state.license_info


# -------------------------------------------------------
# Model Delegation - Admin Endpoints
# -------------------------------------------------------

def _build_model_request_read(
    req: ModelRequest,
    session: SessionDep,
) -> ModelRequestRead:
    """Build a ModelRequestRead response with joined data."""
    team = session.get(Team, req.team_id)
    requester = session.get(User, req.requester_id)

    if not team or not requester:
        raise HTTPException(status_code=404, detail="Related team or user not found")

    # Fetch reviewer username if request was reviewed
    reviewer_username = None
    if req.reviewed_by:
        reviewer = session.get(User, req.reviewed_by)
        if reviewer:
            reviewer_username = reviewer.username

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
        reviewer_username=reviewer_username,
        reviewed_at=req.reviewed_at,
        rejection_reason=req.rejection_reason,
        created_at=req.created_at,
    )


@router.get("/model-requests", response_model=List[ModelRequestRead])
def list_model_requests(
    _: AdminUser,
    session: SessionDep,
    status: Optional[ModelRequestStatus] = None,
) -> List[ModelRequestRead]:
    """
    List all model requests, optionally filtered by status.

    Query params:
    - status: Filter by status (pending/approved/rejected). Defaults to all.

    Requires: Admin role
    """
    query = select(ModelRequest).order_by(ModelRequest.created_at.desc())

    if status is not None:
        query = query.where(ModelRequest.status == status)

    requests = session.exec(query).all()

    return [_build_model_request_read(req, session) for req in requests]


@router.post("/model-requests/{request_id}/approve", response_model=ModelRequestRead)
def approve_model_request(
    request_id: int,
    current_user: AdminUser,
    session: SessionDep,
) -> ModelRequestRead:
    """
    Approve a model request and apply the configuration to the team.

    Requires: Admin role
    """
    request = session.get(ModelRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Model request not found")

    if request.status != ModelRequestStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve request with status: {request.status}"
        )

    # Apply the requested configuration to the team
    team = session.get(Team, request.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Detect if embedding provider/model is changing
    embed_changed = False
    if request.embed_provider and request.embed_model:
        old_provider = team.embed_provider
        old_model = team.embed_model
        new_provider = request.embed_provider
        new_model = request.embed_model

        # Check if either provider or model changed
        embed_changed = (old_provider != new_provider) or (old_model != new_model)

    # Update team model configuration
    if request.llm_provider and request.llm_model:
        team.llm_provider = request.llm_provider
        team.llm_model = request.llm_model

    if request.embed_provider and request.embed_model:
        team.embed_provider = request.embed_provider
        team.embed_model = request.embed_model

    # Mark request as approved
    request.status = ModelRequestStatus.approved
    request.reviewed_by = current_user.id
    request.reviewed_at = datetime.utcnow()

    session.add(team)
    session.add(request)
    session.commit()
    session.refresh(request)

    # Send real-time notification to requester
    try:
        from .notifications import notify_request_reviewed
        notify_request_reviewed(request, session)
    except Exception:
        pass  # Don't fail approval if notification fails

    # CRITICAL: Clear vector store if embedding model changed
    # Different embedding models use incompatible vector dimensions
    # (e.g., Ollama=768d, OpenAI-small=1536d, OpenAI-large=3072d)
    if embed_changed:
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

                # Clear hash cache and BM25 index
                for fname in ("ingested_files.json", "bm25_index.pkl"):
                    stale = team_chroma / fname
                    if stale.exists():
                        stale.unlink()
        except Exception as e:
            # Log error but don't fail the approval
            # Team can manually clear and re-ingest
            import logging
            logging.error(f"Failed to auto-clear vector store for team {team.id}: {e}")

    return _build_model_request_read(request, session)


@router.post("/model-requests/{request_id}/reject", response_model=ModelRequestRead)
def reject_model_request(
    request_id: int,
    body: ModelRequestReject,
    current_user: AdminUser,
    session: SessionDep,
) -> ModelRequestRead:
    """
    Reject a model request with a reason.

    Requires: Admin role
    """
    request = session.get(ModelRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Model request not found")

    if request.status != ModelRequestStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject request with status: {request.status}"
        )

    # Mark request as rejected
    request.status = ModelRequestStatus.rejected
    request.reviewed_by = current_user.id
    request.reviewed_at = datetime.utcnow()
    request.rejection_reason = body.reason

    session.add(request)
    session.commit()
    session.refresh(request)

    # Send real-time notification to requester
    try:
        from .notifications import notify_request_reviewed
        notify_request_reviewed(request, session)
    except Exception:
        pass  # Don't fail rejection if notification fails

    return _build_model_request_read(request, session)


@router.patch("/teams/{team_id}/models", status_code=200)
def assign_team_models(
    team_id: int,
    body: TeamModelConfig,
    _: AdminUser,
    session: SessionDep,
) -> Dict[str, str]:
    """
    Directly assign model configuration to a team (bypass request workflow).

    Allows partial updates:
    - Provide only llm_provider + llm_model to update LLM only
    - Provide only embed_provider + embed_model to update embedding only
    - Provide both to update everything

    Requires: Admin role
    """
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Validate that at least one configuration is provided
    has_llm = body.llm_provider is not None or body.llm_model is not None
    has_embed = body.embed_provider is not None or body.embed_model is not None

    if not has_llm and not has_embed:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one model configuration (LLM or embedding)"
        )

    # Validate LLM configuration if provided
    if has_llm:
        if body.llm_provider and not body.llm_model:
            raise HTTPException(
                status_code=400,
                detail="llm_model is required when llm_provider is set"
            )
        if body.llm_model and not body.llm_provider:
            raise HTTPException(
                status_code=400,
                detail="llm_provider is required when llm_model is set"
            )
        if body.llm_provider not in ("ollama", "openai", "claude"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid llm_provider: {body.llm_provider}. Must be ollama, openai, or claude"
            )
        team.llm_provider = body.llm_provider
        team.llm_model = body.llm_model

    # Validate embedding configuration if provided
    if has_embed:
        if body.embed_provider and not body.embed_model:
            raise HTTPException(
                status_code=400,
                detail="embed_model is required when embed_provider is set"
            )
        if body.embed_model and not body.embed_provider:
            raise HTTPException(
                status_code=400,
                detail="embed_provider is required when embed_model is set"
            )
        if body.embed_provider not in ("ollama", "openai"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid embed_provider: {body.embed_provider}. Must be ollama or openai"
            )
        team.embed_provider = body.embed_provider
        team.embed_model = body.embed_model

    session.add(team)
    session.commit()

    return {
        "message": f"Model configuration updated for team '{team.name}'",
        "team_id": str(team_id),
        "llm_provider": team.llm_provider or "system default",
        "llm_model": team.llm_model or "system default",
        "embed_provider": team.embed_provider or "system default",
        "embed_model": team.embed_model or "system default",
    }


@router.delete("/teams/{team_id}/models", status_code=200)
def clear_team_models(
    team_id: int,
    _: AdminUser,
    session: SessionDep,
) -> Dict[str, str]:
    """
    Clear team-specific model configuration (revert to system defaults).

    Requires: Admin role
    """
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Clear all team-level model configuration
    team.llm_provider = None
    team.llm_model = None
    team.embed_provider = None
    team.embed_model = None

    session.add(team)
    session.commit()

    return {
        "message": f"Team '{team.name}' model configuration cleared. Now using system defaults.",
        "team_id": str(team_id),
    }
