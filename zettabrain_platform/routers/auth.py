from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select

from ..auth import create_access_token, hash_password, verify_password
from ..deps import CurrentUser, SessionDep
from ..models import ChangePasswordRequest, SystemRole, Token, User, UserCreate, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token", response_model=Token)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_pw):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token({"sub": str(user.id), "role": user.system_role.value})
    return Token(
        access_token=token,
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser):
    return current_user


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    session: SessionDep,
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    current_user.hashed_pw = hash_password(body.new_password)
    current_user.must_change_password = False
    session.add(current_user)
    session.commit()
    return {"status": "ok"}


@router.post("/register", response_model=UserRead)
def register(body: UserCreate, session: SessionDep):
    existing = session.exec(
        select(User).where((User.username == body.username) | (User.email == body.email))
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already taken")

    user = User(
        username=body.username,
        email=body.email,
        hashed_pw=hash_password(body.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
