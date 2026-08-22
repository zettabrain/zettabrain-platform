from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR   = Path(os.environ.get("ZBP_BASE_DIR", "/opt/zettabrain-platform"))
DATA_DIR   = BASE_DIR / "data"
CHROMA_DIR = BASE_DIR / "chromadb"
SKILLS_DIR = BASE_DIR / "skills"
CERTS_DIR  = BASE_DIR / "certs"
ENV_FILE   = BASE_DIR / "platform.env"

DATABASE_URL = f"sqlite:///{DATA_DIR / 'platform.db'}"

PORT        = int(os.environ.get("ZBP_PORT", "7860"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL   = os.environ.get("ZETTABRAIN_LLM_MODEL", "llama3.1:8b")
EMBED_MODEL = os.environ.get("ZETTABRAIN_EMBED_MODEL", "nomic-embed-text")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ZBP_TOKEN_EXPIRE", "480"))

_TLS_CERT = CERTS_DIR / "server.crt"
_TLS_KEY  = CERTS_DIR / "server.key"
TLS_ENABLED = _TLS_CERT.exists() and _TLS_KEY.exists()
TLS_CERT    = str(_TLS_CERT) if TLS_ENABLED else None
TLS_KEY     = str(_TLS_KEY)  if TLS_ENABLED else None


def _load_env_file() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _ensure_jwt_secret() -> str:
    cfg = _load_env_file()
    if "ZBP_JWT_SECRET" in cfg:
        return cfg["ZBP_JWT_SECRET"]
    secret = secrets.token_hex(32)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ENV_FILE, "a") as f:
        f.write(f'\nZBP_JWT_SECRET="{secret}"\n')
    return secret


JWT_SECRET    = os.environ.get("ZBP_JWT_SECRET") or _ensure_jwt_secret()
JWT_ALGORITHM = "HS256"


def team_chroma_path(team_slug: str) -> str:
    return str(CHROMA_DIR / team_slug)
