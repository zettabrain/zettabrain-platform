from __future__ import annotations

import os
import ssl
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel, select

from ..auth import hash_password
from ..deps import AdminUser, SessionDep
from ..models import SystemRole, User, UserRead

router = APIRouter(prefix="/api/admin/ldap", tags=["ldap"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _esc(value: str) -> str:
    return (
        value
        .replace("\\", "\\5c").replace("*",  "\\2a")
        .replace("(",  "\\28").replace(")",  "\\29")
        .replace("\0", "\\00")
    )


def _str(entry, attr: str) -> str:
    try:
        val = str(entry[attr])
        return "" if val in ("None", "[]", "") else val
    except Exception:
        return ""


def _ldap_conn(ldap_url: str, bind_dn: str, bind_pw: str):
    from ldap3 import ALL, Connection, Server, Tls
    use_ssl    = ldap_url.lower().startswith("ldaps://")
    tls_config = Tls(validate=ssl.CERT_NONE) if use_ssl else None
    server     = Server(ldap_url, get_info=ALL, use_ssl=use_ssl, tls=tls_config, connect_timeout=5)
    return Connection(server, user=bind_dn, password=bind_pw, auto_bind=True, read_only=True)


def _saved_settings(session) -> Dict[str, str]:
    from .settings import get_setting
    return {
        "ldap_url":       get_setting(session, "ldap_url"),
        "bind_dn":        get_setting(session, "ldap_bind_dn"),
        "bind_pw":        get_setting(session, "ldap_bind_password"),
        "user_base":      get_setting(session, "ldap_user_base"),
        "user_filter":    get_setting(session, "ldap_user_filter")  or "(&(objectClass=person)(sAMAccountName={username}))",
        "username_attr":  get_setting(session, "ldap_username_attr") or "sAMAccountName",
        "email_attr":     get_setting(session, "ldap_email_attr")    or "mail",
        "require_group":  get_setting(session, "ldap_require_group"),
    }


def _derive_base_dns(user_base: str) -> List[str]:
    """
    Given whatever the admin typed as User Search Base DN, derive a list of
    alternative base DNs to probe if the original returns nothing.

    Handles the common mistakes:
      "acme.com"          → DC=acme,DC=com
      "CN=Users,DC=..."   → already specific, also try DC=... root
      "OU=Staff,DC=..."   → also try DC=... root
    """
    candidates = []
    b = user_base.strip()

    # If it looks like a plain domain (acme.com / corp.acme.com), convert it
    if "." in b and "=" not in b:
        dc_parts = ",".join(f"DC={p}" for p in b.split("."))
        candidates.append(dc_parts)
        candidates.append(f"CN=Users,{dc_parts}")
        return candidates

    # Already in DN notation — derive the root DC= part and CN=Users sub-path
    parts = [p.strip() for p in b.split(",")]
    dc_parts = [p for p in parts if p.upper().startswith("DC=")]
    if dc_parts:
        root_dc = ",".join(dc_parts)
        cn_users = f"CN=Users,{root_dc}"
        if b != root_dc:
            candidates.append(root_dc)
        if b != cn_users:
            candidates.append(cn_users)

    return candidates


# ── test endpoint (uses form values, not saved settings) ─────────────────────

# AD-specific fallback filters tried in order when the configured filter finds nothing.
# Ordered from most-specific (correct AD filter) to broadest (any LDAP entry).
_AD_FALLBACK_FILTERS = [
    ("(&(objectClass=user)(sAMAccountName=*))",          "AD user accounts (objectClass=user)"),
    ("(&(objectCategory=person)(objectClass=user))",     "AD users (objectCategory=person + objectClass=user)"),
    ("(&(objectClass=user)(!(objectClass=computer)))",   "AD users excluding computers"),
    ("(sAMAccountName=*)",                               "any object with a sAMAccountName"),
    ("(objectClass=person)",                             "objectClass=person (abstract)"),
    ("(objectClass=*)",                                  "any LDAP entry at this base DN"),
]


class LdapTestRequest(SQLModel):
    ldap_url:       str
    bind_dn:        str = ""
    bind_password:  str = ""
    user_base:      str
    user_filter:    str = "(&(objectClass=user)(sAMAccountName={username}))"
    username_attr:  str = "sAMAccountName"
    email_attr:     str = "mail"
    require_group:  str = ""


@router.post("/test")
def test_ldap(body: LdapTestRequest, _: AdminUser, session: SessionDep) -> Dict[str, Any]:
    """
    Test AD/LDAP connectivity using the form values (before saving).
    If the configured filter returns no users, automatically tries a series of
    fallback filters to identify what is wrong and suggest a fix.
    """
    if not body.ldap_url or not body.user_base:
        raise HTTPException(status_code=400, detail="LDAP URL and User Search Base DN are required")

    try:
        import ldap3  # noqa: F401
    except ImportError:
        raise HTTPException(status_code=500, detail="ldap3 package not installed — reinstall zettabrain-platform")

    # If the UI sent back the masked placeholder, use the saved password instead
    bind_pw = body.bind_password
    if bind_pw == "********":
        from .settings import get_setting
        bind_pw = get_setting(session, "ldap_bind_password")

    # Stage 1: connect + service-account bind
    try:
        conn = _ldap_conn(body.ldap_url, body.bind_dn, bind_pw)
    except Exception as exc:
        return {"ok": False, "stage": "bind",
                "message": f"Service account bind failed: {exc}",
                "user_count": 0, "sample_users": [], "diagnostics": []}

    # Stage 2: search with the configured filter (wildcard)
    wildcard_filter = body.user_filter.replace("{username}", "*")
    try:
        conn.search(
            search_base   = body.user_base,
            search_filter = wildcard_filter,
            attributes    = [body.username_attr, body.email_attr, "displayName"],
            size_limit    = 5,
        )
        entries = list(conn.entries)
    except Exception as exc:
        conn.unbind()
        return {"ok": False, "stage": "search",
                "message": f"User search failed with filter '{wildcard_filter}': {exc}",
                "user_count": 0, "sample_users": [], "diagnostics": []}

    # Stage 3: if nothing found, try fallback filters AND fallback base DNs
    diagnostics: List[Dict[str, Any]] = []
    working_filter: str = ""
    working_base: str = ""

    if not entries:
        # Build a list of base DNs to probe in addition to the one the user gave.
        # This catches the common mistake of entering "acme.com" instead of
        # "DC=acme,DC=com", or only specifying an OU when users are in CN=Users.
        alt_bases = _derive_base_dns(body.user_base)

        for base_dn in [body.user_base] + alt_bases:
            if working_filter:
                break
            for fallback, label in _AD_FALLBACK_FILTERS:
                if base_dn == body.user_base and fallback == wildcard_filter:
                    continue   # already tried this exact combination
                try:
                    conn.search(
                        search_base   = base_dn,
                        search_filter = fallback,
                        attributes    = [body.username_attr, body.email_attr, "displayName"],
                        size_limit    = 3,
                    )
                    found = len(conn.entries)
                    diag_label = label if base_dn == body.user_base else f"{label}  [base: {base_dn}]"
                    diagnostics.append({"filter": fallback, "label": diag_label,
                                        "base_dn": base_dn, "found": found})
                    if found and not working_filter:
                        entries       = list(conn.entries)
                        working_filter = fallback
                        working_base   = base_dn
                except Exception as exc:
                    diagnostics.append({"filter": fallback, "label": label,
                                        "base_dn": base_dn, "found": 0, "error": str(exc)})

    conn.unbind()

    # Build sample user list
    sample = []
    for e in entries:
        uname = _str(e, body.username_attr)
        if not uname:
            continue
        sample.append({
            "username":     uname,
            "email":        _str(e, body.email_attr) or _str(e, "mail"),
            "display_name": _str(e, "displayName") or uname,
        })

    if working_filter:
        base_note = f"  Also update the User Search Base DN to: {working_base}" if working_base != body.user_base else ""
        msg = (
            f"Bound successfully. Your configured filter returned no results, but this combination works — "
            f"click 'Apply' to update the form:{base_note}"
        )
        ok = False
    elif entries:
        msg = f"Connected successfully. Found {len(entries)}+ user(s) — sample shown below."
        ok = True
    else:
        msg = (
            "Bound successfully, but no entries were found anywhere. "
            "Check that the User Search Base DN is the root of your domain, "
            "e.g. DC=acme,DC=com (not acme.com, not OU=...). "
            "For acme.com with users in the default Users container use: "
            "Base DN = DC=acme,DC=com, Filter = (&(objectClass=user)(sAMAccountName={username}))"
        )
        ok = False

    return {
        "ok":             ok,
        "stage":          "success" if ok else "search",
        "message":        msg,
        "user_count":     len(entries),
        "sample_users":   sample,
        "working_filter": working_filter,
        "working_base":   working_base,
        "diagnostics":    diagnostics,
    }


# ── user search (uses saved settings) ────────────────────────────────────────

@router.get("/search")
def search_ad_users(q: str, _: AdminUser, session: SessionDep) -> List[Dict[str, Any]]:
    """Search Active Directory for users whose username or display name matches q."""
    cfg = _saved_settings(session)
    if not cfg["ldap_url"] or not cfg["user_base"] or not q.strip():
        return []

    try:
        import ldap3  # noqa: F401
    except ImportError:
        raise HTTPException(status_code=500, detail="ldap3 not installed")

    try:
        conn = _ldap_conn(cfg["ldap_url"], cfg["bind_dn"], cfg["bind_pw"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AD bind failed: {exc}")

    q_esc   = _esc(q.strip())
    ua      = cfg["username_attr"]
    ea      = cfg["email_attr"]
    # search sAMAccountName *or* displayName containing the query
    search_filter = f"(&(objectClass=person)(|({ua}=*{q_esc}*)(displayName=*{q_esc}*)))"

    try:
        conn.search(
            search_base   = cfg["user_base"],
            search_filter = search_filter,
            attributes    = [ua, ea, "displayName", "mail"],
            size_limit    = 25,
        )
        entries = list(conn.entries)
    except Exception as exc:
        conn.unbind()
        raise HTTPException(status_code=500, detail=f"AD search failed: {exc}")

    conn.unbind()

    existing = {u.username for u in session.exec(select(User)).all()}

    results = []
    for e in entries:
        uname = _str(e, ua)
        if not uname:
            continue
        email = _str(e, ea) or _str(e, "mail")
        results.append({
            "username":      uname,
            "email":         email,
            "display_name":  _str(e, "displayName") or uname,
            "exists_locally": uname in existing,
        })
    return results


# ── import (provision) an AD user locally ────────────────────────────────────

class LdapImportRequest(SQLModel):
    username: str


@router.post("/import", response_model=UserRead)
def import_ad_user(body: LdapImportRequest, _: AdminUser, session: SessionDep) -> User:
    """
    Find a user in AD by username and create a local account for them.
    Safe to call if the user already exists — returns the existing record.
    """
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    # Return existing user immediately
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing:
        return existing

    cfg = _saved_settings(session)
    if not cfg["ldap_url"] or not cfg["user_base"]:
        raise HTTPException(status_code=400, detail="LDAP is not configured")

    try:
        import ldap3  # noqa: F401
    except ImportError:
        raise HTTPException(status_code=500, detail="ldap3 not installed")

    try:
        conn = _ldap_conn(cfg["ldap_url"], cfg["bind_dn"], cfg["bind_pw"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AD bind failed: {exc}")

    search_filter = cfg["user_filter"].replace("{username}", _esc(username))
    conn.search(
        search_base   = cfg["user_base"],
        search_filter = search_filter,
        attributes    = [cfg["username_attr"], cfg["email_attr"], "displayName", "mail"],
    )

    if not conn.entries:
        conn.unbind()
        raise HTTPException(status_code=404, detail=f"User '{username}' not found in Active Directory")

    entry = conn.entries[0]
    email = _str(entry, cfg["email_attr"]) or _str(entry, "mail")
    conn.unbind()

    new_user = User(
        username             = username,
        email                = email if ("@" in email) else f"{username}@ldap.local",
        hashed_pw            = hash_password(os.urandom(32).hex()),
        system_role          = SystemRole.user,
        is_active            = True,
        must_change_password = False,
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    return new_user
