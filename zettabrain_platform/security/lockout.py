"""Account lockout after repeated failed login attempts (SOC2 CC6.1)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Tuple

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

_attempts: Dict[str, Tuple[int, datetime]] = {}


def check_lockout(username: str) -> Tuple[bool, int]:
    """Check if account is locked. Returns (is_locked, seconds_remaining)."""
    if username not in _attempts:
        return False, 0

    count, last_attempt = _attempts[username]
    if count < MAX_FAILED_ATTEMPTS:
        return False, 0

    lockout_until = last_attempt + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
    now = datetime.utcnow()
    if now >= lockout_until:
        del _attempts[username]
        return False, 0

    remaining = int((lockout_until - now).total_seconds())
    return True, remaining


def record_failed_login(username: str) -> int:
    """Record a failed attempt. Returns current count."""
    now = datetime.utcnow()
    if username in _attempts:
        count, last = _attempts[username]
        if now - last > timedelta(minutes=LOCKOUT_DURATION_MINUTES):
            _attempts[username] = (1, now)
            return 1
        _attempts[username] = (count + 1, now)
        return count + 1
    _attempts[username] = (1, now)
    return 1


def reset_failed_logins(username: str) -> None:
    """Reset failed login counter on successful login."""
    _attempts.pop(username, None)
