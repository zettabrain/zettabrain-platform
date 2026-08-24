"""Ed25519 signing for ZettaBrain Verified Answer Provenance."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

_private_key: Optional[Ed25519PrivateKey] = None
_public_key_hex: str = ""


def init_signing_key(data_dir: Path) -> str:
    """Generate or load the server Ed25519 signing key. Returns public key hex."""
    global _private_key, _public_key_hex
    key_path = data_dir / "server_signing.key"
    if key_path.exists():
        pem = key_path.read_bytes()
        _private_key = load_pem_private_key(pem, password=None)  # type: ignore[assignment]
    else:
        _private_key = Ed25519PrivateKey.generate()
        pem = _private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        data_dir.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(pem)
        key_path.chmod(0o600)
    raw_pub = _private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    _public_key_hex = raw_pub.hex()
    return _public_key_hex


def get_public_key_hex() -> str:
    return _public_key_hex


def sign_bundle(query_hash: str, chunk_hashes: list, answer_hash: str,
                team_id: Optional[int], model: str) -> str:
    """Return Ed25519 hex signature over the canonical provenance payload."""
    if _private_key is None:
        return ""
    payload = _canonical_payload(query_hash, chunk_hashes, answer_hash, team_id, model)
    sig = _private_key.sign(payload)
    return sig.hex()


def verify_bundle(query_hash: str, chunk_hashes: list, answer_hash: str,
                  team_id: Optional[int], model: str, signature_hex: str) -> bool:
    """Return True if signature verifies over the same canonical payload."""
    if not _public_key_hex or not signature_hex:
        return False
    try:
        raw_pub = bytes.fromhex(_public_key_hex)
        pub_key: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(raw_pub)
        payload = _canonical_payload(query_hash, chunk_hashes, answer_hash, team_id, model)
        pub_key.verify(bytes.fromhex(signature_hex), payload)
        return True
    except (InvalidSignature, ValueError):
        return False


def _canonical_payload(query_hash: str, chunk_hashes: list, answer_hash: str,
                       team_id: Optional[int], model: str) -> bytes:
    obj = {
        "answer_hash":  answer_hash,
        "chunk_hashes": sorted(chunk_hashes),
        "model":        model,
        "query_hash":   query_hash,
        "team_id":      team_id,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
