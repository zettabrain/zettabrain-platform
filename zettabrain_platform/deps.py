from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from .auth import decode_token
from .database import get_session
from .models import SystemRole, Team, TeamMember, TeamRole, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
) -> User:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = session.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or unknown user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    if current_user.system_role != SystemRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


def get_team_membership(
    team_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> TeamMember:
    if current_user.system_role == SystemRole.admin:
        team = session.get(Team, team_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        return TeamMember(user_id=current_user.id, team_id=team_id, team_role=TeamRole.manager)

    membership = session.exec(
        select(TeamMember).where(
            TeamMember.user_id == current_user.id,
            TeamMember.team_id == team_id,
        )
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a team member")
    return membership


def require_team_manager(
    membership: Annotated[TeamMember, Depends(get_team_membership)],
) -> TeamMember:
    if membership.team_role not in (TeamRole.manager,):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Team manager only")
    return membership
