"""ZettaBrain Teams — offline license verification (Ed25519)."""
from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Master public key — ZettaBrain retains the private key.
# Changing this constant would require a new package release.
_MASTER_PUBLIC_KEY_HEX = "45262b428e2a23a7fe5b13cc999e0c731f6482557038147283665af02f71457a"

TRIAL_DAYS   = 90
GRACE_DAYS   = 14   # warn-only window after license expiry before blocking


class LicenseState(str, Enum):
    trial_active    = "trial_active"
    trial_expiring  = "trial_expiring"   # ≤ 14 days left in trial
    trial_expired   = "trial_expired"
    licensed        = "licensed"
    license_expiring = "license_expiring"  # ≤ 30 days to license expiry
    license_grace   = "license_grace"     # expired but within 14-day grace
    license_expired = "license_expired"   # hard block


def _verify_signature(payload: dict, sig_hex: str) -> bool:
    try:
        pub_bytes = bytes.fromhex(_MASTER_PUBLIC_KEY_HEX)
        pub_key: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(pub_bytes)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        pub_key.verify(bytes.fromhex(sig_hex), canonical)
        return True
    except (InvalidSignature, ValueError):
        return False


def parse_license_key(key_str: str) -> Optional[dict]:
    """Decode and verify a base64 license string. Returns payload or None."""
    try:
        raw = base64.b64decode(key_str.strip().encode())
        doc = json.loads(raw)
        payload = doc["payload"]
        sig     = doc["sig"]
        if not _verify_signature(payload, sig):
            return None
        return payload
    except Exception:
        return None


def load_license(data_dir: Path, session=None) -> Optional[dict]:
    """Try loading a valid license from file then DB. Returns verified payload or None."""
    # 1. License file on disk (scp / manual install)
    lic_file = data_dir / "license.lic"
    if lic_file.exists():
        payload = parse_license_key(lic_file.read_text().strip())
        if payload:
            return payload

    # 2. License key stored in SystemConfig via admin UI
    if session is not None:
        try:
            from sqlmodel import select
            from .models import SystemConfig
            row = session.get(SystemConfig, "license_key")
            if row and row.value:
                payload = parse_license_key(row.value)
                if payload:
                    return payload
        except Exception:
            pass

    return None


def _trial_days_left(session) -> int:
    """Return days remaining in trial (can be negative if expired)."""
    from datetime import timedelta
    from sqlmodel import Session
    from .models import SystemConfig
    from .database import engine

    with Session(engine) as s:
        cfg = s.get(SystemConfig, "trial_start")
        if cfg is None:
            now_iso = datetime.now(timezone.utc).isoformat()
            s.add(SystemConfig(key="trial_start", value=now_iso))
            s.commit()
            return TRIAL_DAYS
        ts = datetime.fromisoformat(cfg.value)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - ts).days
        return TRIAL_DAYS - elapsed


def check_startup(data_dir: Path, session=None) -> dict:
    """
    Evaluate license/trial state at server startup.
    Exits the process if access must be blocked.
    Returns a license_info dict used by the rest of the app.
    """
    from datetime import timedelta

    lic = load_license(data_dir, session)

    # ── LICENSED PATH ────────────────────────────────────────────────
    if lic is not None:
        expires_str = lic.get("expires_at")  # None = perpetual
        if expires_str:
            expires_dt = datetime.fromisoformat(expires_str).replace(tzinfo=timezone.utc)
            now        = datetime.now(timezone.utc)
            days_left  = (expires_dt - now).days

            if days_left < -GRACE_DAYS:
                _print_license_expired(lic, abs(days_left) - GRACE_DAYS)
                sys.exit(1)

            state = (
                LicenseState.license_grace    if days_left < 0
                else LicenseState.license_expiring if days_left <= 30
                else LicenseState.licensed
            )
        else:
            days_left = None
            state     = LicenseState.licensed

        info = {
            "state":      state,
            "licensed":   True,
            "customer":   lic.get("customer", ""),
            "email":      lic.get("email", ""),
            "license_id": lic.get("license_id", ""),
            "plan":       lic.get("plan", ""),
            "issued_at":  lic.get("issued_at", ""),
            "expires_at": expires_str,
            "days_left":  days_left,
            "max_users":  lic.get("max_users"),
            "max_teams":  lic.get("max_teams"),
            "features":   lic.get("features", []),
        }
        _print_license_status(info)
        return info

    # ── TRIAL PATH ───────────────────────────────────────────────────
    days_left = _trial_days_left(session)

    if days_left <= 0:
        border = "=" * 64
        print(f"\n{border}")
        print("  ZettaBrain Teams — Trial Expired")
        print(f"  Your {TRIAL_DAYS}-day trial ended {abs(days_left)} day(s) ago.")
        print("  Email sales@zettabrain.io to purchase a license.")
        print(f"{border}\n")
        sys.exit(1)

    from datetime import timedelta
    from .database import engine
    from sqlmodel import Session
    from .models import SystemConfig

    with Session(engine) as s:
        cfg = s.get(SystemConfig, "trial_start")
        ts  = datetime.fromisoformat(cfg.value) if cfg else datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        expires_at = (ts + timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d")

    state = LicenseState.trial_expiring if days_left <= 14 else LicenseState.trial_active

    info = {
        "state":      state,
        "licensed":   False,
        "customer":   None,
        "email":      None,
        "license_id": None,
        "plan":       "trial",
        "issued_at":  None,
        "expires_at": expires_at,
        "days_left":  days_left,
        "max_users":  None,
        "max_teams":  None,
        "features":   [],
    }
    _print_license_status(info)
    return info


def _print_license_status(info: dict) -> None:
    state = info["state"]
    if state == LicenseState.licensed:
        exp = f"expires {info['expires_at']}" if info["expires_at"] else "perpetual"
        print(f"  License: {info['plan'].upper()} — {info['customer']} ({exp})")
    elif state == LicenseState.license_expiring:
        print(f"  ⚠  License expiring in {info['days_left']} day(s) — contact sales@zettabrain.io")
    elif state == LicenseState.license_grace:
        print(f"  🚨 License expired (grace period). Contact sales@zettabrain.io immediately.")
    elif state == LicenseState.trial_active:
        print(f"  Trial: {info['days_left']} of {TRIAL_DAYS} days remaining (expires {info['expires_at']})")
    elif state == LicenseState.trial_expiring:
        print(f"  ⚠  Trial expires in {info['days_left']} day(s) ({info['expires_at']}) — contact sales@zettabrain.io")


def _print_license_expired(lic: dict, days_over: int) -> None:
    border = "=" * 64
    print(f"\n{border}")
    print("  ZettaBrain Teams — License Expired")
    print(f"  Customer  : {lic.get('customer', '')}")
    print(f"  Expired   : {lic.get('expires_at', '')} ({days_over} day(s) past grace period)")
    print("  Renew at  : sales@zettabrain.io")
    print(f"{border}\n")
