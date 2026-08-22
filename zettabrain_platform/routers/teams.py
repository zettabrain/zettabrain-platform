from __future__ import annotations

import re
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..deps import AdminUser, CurrentUser, SessionDep, get_team_membership
from ..models import (
    Team, TeamCreate, TeamMember, TeamMemberRead, TeamRead, TeamRole, TeamUpdate, User,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "team"


@router.get("/", response_model=List[TeamRead])
def list_teams(current_user: CurrentUser, session: SessionDep):
    if current_user.system_role.value == "admin":
        return session.exec(select(Team)).all()
    team_ids = [m.team_id for m in current_user.memberships]
    if not team_ids:
        return []
    return session.exec(select(Team).where(Team.id.in_(team_ids))).all()


@router.post("/", response_model=TeamRead)
def create_team(body: TeamCreate, _: AdminUser, session: SessionDep):
    slug = _slugify(body.name)
    if session.exec(select(Team).where(Team.slug == slug)).first():
        raise HTTPException(status_code=409, detail="Team slug already exists")
    team = Team(name=body.name, slug=slug, description=body.description, docs_folder=body.docs_folder)
    session.add(team)
    session.commit()
    session.refresh(team)
    return team


@router.get("/{team_id}", response_model=TeamRead)
def get_team(
    team_id: int,
    membership: Annotated[TeamMember, Depends(get_team_membership)],
    session: SessionDep,
):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.put("/{team_id}", response_model=TeamRead)
def update_team(team_id: int, body: TeamUpdate, _: AdminUser, session: SessionDep):
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    if body.name is not None:
        team.name = body.name
    if body.description is not None:
        team.description = body.description
    if body.docs_folder is not None:
        team.docs_folder = body.docs_folder
    session.add(team)
    session.commit()
    session.refresh(team)
    return team


@router.get("/{team_id}/members", response_model=List[TeamMemberRead])
def list_members(
    team_id: int,
    membership: Annotated[TeamMember, Depends(get_team_membership)],
    session: SessionDep,
):
    members = session.exec(select(TeamMember).where(TeamMember.team_id == team_id)).all()
    result = []
    for m in members:
        user = session.get(User, m.user_id)
        if user:
            result.append(TeamMemberRead(
                user_id=user.id,
                username=user.username,
                email=user.email,
                team_role=m.team_role,
                joined_at=m.joined_at,
            ))
    return result


@router.post("/{team_id}/members")
def add_member(team_id: int, username: str, role: str = "member", _: AdminUser = None, session: SessionDep = None):
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = session.exec(
        select(TeamMember).where(TeamMember.user_id == user.id, TeamMember.team_id == team_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already a member")
    member = TeamMember(user_id=user.id, team_id=team_id, team_role=TeamRole(role))
    session.add(member)
    session.commit()
    return {"status": "ok", "user_id": user.id, "team_id": team_id}
