from __future__ import annotations

import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from ..auth import create_access_token, hash_password, verify_password
from ..deps import CurrentUser, SessionDep
from ..models import ChangePasswordRequest, SystemRole, Token, User, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Active Directory / LDAP authentication ───────────────────────────────────

def _escape_ldap(value: str) -> str:
    """Escape special characters in an LDAP filter value (RFC 4515)."""
    return (
        value
        .replace("\\", "\\5c")
        .replace("*",  "\\2a")
        .replace("(",  "\\28")
        .replace(")",  "\\29")
        .replace("\0", "\\00")
    )


def _ldap_authenticate(session: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate against Active Directory via LDAP.
    Returns a (possibly auto-provisioned) User on success, None on any failure.

    Flow:
      1. Bind to AD with service account to search for the user by sAMAccountName.
      2. Optionally verify the user is a member of a required group.
      3. Re-bind using the found user DN + supplied password to verify credentials.
      4. Auto-provision a local User row on first successful login.
    """
    from .settings import get_setting

    if get_setting(session, "ldap_enabled") != "true":
        return None

    ldap_url      = get_setting(session, "ldap_url")
    bind_dn       = get_setting(session, "ldap_bind_dn")
    bind_pw       = get_setting(session, "ldap_bind_password")
    user_base     = get_setting(session, "ldap_user_base")
    user_filter   = get_setting(session, "ldap_user_filter") or "(&(objectClass=person)(sAMAccountName={username}))"
    username_attr = get_setting(session, "ldap_username_attr") or "sAMAccountName"
    email_attr    = get_setting(session, "ldap_email_attr") or "mail"
    require_group = get_setting(session, "ldap_require_group")

    if not ldap_url or not user_base:
        return None

    try:
        import ssl
        from ldap3 import ALL, Connection, Server, Tls

        use_ssl    = ldap_url.lower().startswith("ldaps://")
        tls_config = Tls(validate=ssl.CERT_NONE) if use_ssl else None
        server     = Server(ldap_url, get_info=ALL, use_ssl=use_ssl, tls=tls_config, connect_timeout=5)

        # Step 1: service-account bind to search the directory
        svc_conn = Connection(server, user=bind_dn, password=bind_pw, auto_bind=True, read_only=True)

        search_filter = user_filter.replace("{username}", _escape_ldap(username))
        svc_conn.search(
            search_base   = user_base,
            search_filter = search_filter,
            attributes    = [username_attr, email_attr, "distinguishedName", "memberOf", "mail"],
        )

        if not svc_conn.entries:
            svc_conn.unbind()
            return None

        entry    = svc_conn.entries[0]
        user_dn  = entry.entry_dn

        # Step 2: optional group membership check
        if require_group:
            try:
                member_of = [str(g) for g in entry.memberOf]
            except Exception:
                member_of = []
            if not any(require_group.lower() in g.lower() for g in member_of):
                svc_conn.unbind()
                return None

        # Grab email from the directory entry
        user_email = ""
        for attr in (email_attr, "mail"):
            try:
                val = str(entry[attr])
                if val and "@" in val:
                    user_email = val
                    break
            except Exception:
                pass

        svc_conn.unbind()

        # Step 3: verify the user's own password by binding as them
        user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        user_conn.unbind()

        # Step 4: auto-provision in local DB
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            return existing if existing.is_active else None

        new_user = User(
            username             = username,
            email                = user_email or f"{username}@ldap.local",
            hashed_pw            = hash_password(os.urandom(32).hex()),
            system_role          = SystemRole.user,
            is_active            = True,
            must_change_password = False,
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return new_user

    except Exception:
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/token", response_model=Token)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    # Try local auth first (covers admin even when LDAP is enabled)
    user = session.exec(select(User).where(User.username == form.username)).first()
    if user and verify_password(form.password, user.hashed_pw):
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    else:
        # Fall back to LDAP / Active Directory
        user = _ldap_authenticate(session, form.username, form.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
            )

    token = create_access_token({"sub": str(user.id), "role": user.system_role})
    return Token(
        access_token         = token,
        must_change_password = user.must_change_password,
    )


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser):
    return current_user


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    session: SessionDep,
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_pw            = hash_password(body.new_password)
    user.must_change_password = False
    session.add(user)
    session.commit()
