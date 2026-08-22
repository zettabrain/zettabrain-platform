"""Fernet encryption for secrets at rest (API keys stored in SystemConfig)."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet

from ..config import DATA_DIR

_KEY_FILE = DATA_DIR / "encryption.key"
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.environ.get("ZBP_ENCRYPTION_KEY")
    if not key:
        if _KEY_FILE.exists():
            key = _KEY_FILE.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _KEY_FILE.write_text(key)
            _KEY_FILE.chmod(0o600)

    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext prefixed with 'enc:'."""
    if not plaintext or plaintext.startswith("enc:"):
        return plaintext
    token = _get_fernet().encrypt(plaintext.encode())
    return f"enc:{token.decode()}"


def decrypt_value(stored: str) -> str:
    """Decrypt a value. If not encrypted (no 'enc:' prefix), returns as-is."""
    if not stored or not stored.startswith("enc:"):
        return stored
    token = stored[4:]
    return _get_fernet().decrypt(token.encode()).decode()
