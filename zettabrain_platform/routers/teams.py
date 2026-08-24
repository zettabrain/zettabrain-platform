from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select

from ..deps import AdminUser, CurrentUser, SessionDep, get_team_membership
from ..models import (
    AuditLog,
    ModelRequest,
    SystemRole,
    Team,
    TeamCreate,
    TeamMember,
    TeamMemberRead,
    TeamRead,
    TeamRole,
    TeamUpdate,
    User,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@router.get("/", response_model=list[TeamRead])
def list_teams(current_user: CurrentUser, session: SessionDep):
    if current_user.system_role == "admin":
        return session.exec(select(Team)).all()
    memberships = session.exec(
        select(TeamMember).where(TeamMember.user_id == current_user.id)
    ).all()
    team_ids = [m.team_id for m in memberships]
    if not team_ids:
        return []
    return session.exec(select(Team).where(Team.id.in_(team_ids))).all()


@router.post("/", response_model=TeamRead)
def create_team(body: TeamCreate, _: AdminUser, session: SessionDep):
    from .. import state
    slug = _slugify(body.name)
    if session.exec(select(Team).where(Team.slug == slug)).first():
        raise HTTPException(status_code=409, detail="Team slug already exists")

    max_teams = state.license_info.get("max_teams")
    if max_teams is not None:
        current_count = session.exec(select(func.count(Team.id))).one()
        if current_count >= max_teams:
            raise HTTPException(
                status_code=403,
                detail=f"Team limit reached ({max_teams}). Upgrade your license to create more teams.",
            )

    team = Team(
        name=body.name,
        slug=slug,
        description=body.description,
        docs_folder=body.docs_folder,
    )
    session.add(team)
    session.commit()
    session.refresh(team)
    return team


@router.patch("/{team_id}", response_model=TeamRead)
def update_team(
    team_id: int,
    body: TeamUpdate,
    current_user: CurrentUser,
    session: SessionDep,
):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Admins can update any team; managers can update their own
    if current_user.system_role != SystemRole.admin:
        membership = session.exec(
            select(TeamMember).where(
                TeamMember.user_id == current_user.id,
                TeamMember.team_id == team_id,
            )
        ).first()
        if not membership or membership.team_role not in (TeamRole.manager,):
            raise HTTPException(
                status_code=403,
                detail="Admin or team manager role required",
            )

    if body.name is not None:
        new_slug = _slugify(body.name)
        existing = session.exec(select(Team).where(Team.slug == new_slug)).first()
        if existing and existing.id != team_id:
            raise HTTPException(status_code=409, detail="Team slug already exists")
        team.name = body.name
        team.slug = new_slug
    if body.description is not None:
        team.description = body.description
    if body.docs_folder is not None:
        team.docs_folder = body.docs_folder

    session.add(team)
    session.commit()
    session.refresh(team)
    return team


@router.get("/{team_id}/members", response_model=list[TeamMemberRead])
def list_members(
    team_id: int,
    _: Annotated[TeamMember, Depends(get_team_membership)],
    session: SessionDep,
):
    rows = session.exec(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
    ).all()
    return [
        TeamMemberRead(
            user_id   = m.user_id,
            username  = u.username,
            email     = u.email,
            team_role = m.team_role,
            joined_at = m.joined_at,
        )
        for m, u in rows
    ]


@router.post("/{team_id}/members/{user_id}", response_model=TeamMemberRead)
def add_member(
    team_id: int,
    user_id: int,
    _: AdminUser,
    session: SessionDep,
    role: TeamRole = TeamRole.member,
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = session.exec(
        select(TeamMember).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id == team_id,
        )
    ).first()
    if existing:
        existing.team_role = role
        session.add(existing)
        session.commit()
        session.refresh(existing)
        m = existing
    else:
        m = TeamMember(user_id=user_id, team_id=team_id, team_role=role)
        session.add(m)
        session.commit()
        session.refresh(m)
    return TeamMemberRead(
        user_id=m.user_id, username=user.username, email=user.email,
        team_role=m.team_role, joined_at=m.joined_at,
    )


@router.delete("/{team_id}", status_code=204)
def delete_team(team_id: int, _: AdminUser, session: SessionDep):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Cascade: remove memberships
    members = session.exec(select(TeamMember).where(TeamMember.team_id == team_id)).all()
    for m in members:
        session.delete(m)

    # Cascade: remove model requests
    requests = session.exec(select(ModelRequest).where(ModelRequest.team_id == team_id)).all()
    for r in requests:
        session.delete(r)

    # Cascade: null out audit log foreign keys (preserve logs)
    logs = session.exec(select(AuditLog).where(AuditLog.team_id == team_id)).all()
    for log in logs:
        log.team_id = None
        session.add(log)

    # Cascade: remove chromadb data
    try:
        from ..config import CHROMA_DIR
        import shutil
        team_chroma = CHROMA_DIR / team.slug
        if team_chroma.exists():
            shutil.rmtree(team_chroma)
    except Exception:
        pass

    session.delete(team)
    session.commit()


@router.delete("/{team_id}/members/{user_id}", status_code=204)
def remove_member(
    team_id: int,
    user_id: int,
    _: AdminUser,
    session: SessionDep,
):
    m = session.exec(
        select(TeamMember).where(
            TeamMember.user_id == user_id,
            TeamMember.team_id == team_id,
        )
    ).first()
    if m:
        session.delete(m)
        session.commit()


@router.get("/{team_id}/stats")
def get_team_stats(
    team_id: int,
    membership: Annotated[TeamMember, Depends(get_team_membership)],
    session: SessionDep,
):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    vector_docs = 0
    collections_info = []
    try:
        from ..config import CHROMA_DIR
        import chromadb
        team_chroma = CHROMA_DIR / team.slug
        if team_chroma.exists():
            client = chromadb.PersistentClient(path=str(team_chroma))
            for col in client.list_collections():
                count = col.count()
                collections_info.append({"name": col.name, "count": count})
                vector_docs += count
    except Exception:
        pass

    return {
        "team_id": team.id,
        "team_name": team.name,
        "vector_docs": vector_docs,
        "collections": collections_info,
        "docs_folder": team.docs_folder,
    }


@router.patch("/{team_id}/multi-embed-permission")
def set_multi_embed_permission(
    team_id: int,
    _: AdminUser,
    session: SessionDep,
    allowed: bool = True,
):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.multi_embed_allowed = allowed
    if not allowed:
        team.multi_embed_enabled = False
    session.add(team)
    session.commit()
    session.refresh(team)
    return {"multi_embed_allowed": team.multi_embed_allowed, "multi_embed_enabled": team.multi_embed_enabled}


@router.patch("/{team_id}/multi-embed-settings")
def toggle_multi_embed(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    enabled: bool = True,
):
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
        if not membership or membership.team_role != TeamRole.manager:
            raise HTTPException(status_code=403, detail="Manager role required")

    if not team.multi_embed_allowed:
        raise HTTPException(
            status_code=403,
            detail="Multi-embedding not allowed for this team. Ask an admin to enable it.",
        )

    team.multi_embed_enabled = enabled
    session.add(team)
    session.commit()
    session.refresh(team)
    return {"multi_embed_enabled": team.multi_embed_enabled}


@router.delete("/{team_id}/collections/{collection_name}", status_code=204)
def delete_collection(
    team_id: int,
    collection_name: str,
    current_user: CurrentUser,
    session: SessionDep,
):
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
        if not membership or membership.team_role != TeamRole.manager:
            raise HTTPException(status_code=403, detail="Manager role required")

    from ..config import CHROMA_DIR
    import chromadb
    team_chroma = CHROMA_DIR / team.slug
    if not team_chroma.exists():
        raise HTTPException(status_code=404, detail="No vector store for this team")

    client = chromadb.PersistentClient(path=str(team_chroma))
    try:
        client.delete_collection(collection_name)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found")

    # Clean up associated BM25 index and hash cache
    for suffix in (f"_bm25_{collection_name}.pkl", f"_hashes_{collection_name}.json"):
        stale = team_chroma / suffix
        if stale.exists():
            stale.unlink()
