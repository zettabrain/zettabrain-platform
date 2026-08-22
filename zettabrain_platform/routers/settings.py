"""Admin settings router — system configuration management."""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel, select

from ..config import CHROMA_DIR
from ..deps import AdminUser, SessionDep
from ..models import SystemConfig, Team
from ..security.encryption import decrypt_value, encrypt_value

router = APIRouter(prefix="/api/admin", tags=["admin-settings"])

DEFAULTS: Dict[str, str] = {
    "ollama_host":          "http://localhost:11434",
    "llm_model":            "llama-3.1-8b-instant",
    "embed_model":          "nomic-embed-text",
    "llm_provider":         "groq",
    "embed_provider":       "ollama",
    "openai_api_key":       "",
    "openai_llm_model":     "gpt-4o",
    "openai_embed_model":   "text-embedding-3-small",
    "anthropic_api_key":    "",
    "claude_llm_model":     "claude-sonnet-4-6",
    # Cloud LLM providers (all OpenAI-compatible — free tiers available)
    "groq_api_key":         "",
    "groq_model":           "llama-3.1-8b-instant",
    "together_api_key":     "",
    "together_model":       "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "cerebras_api_key":     "",
    "cerebras_model":       "llama3.1-8b",
    "openrouter_api_key":   "",
    "openrouter_model":     "meta-llama/llama-3.1-8b-instruct:free",
    "fireworks_api_key":    "",
    "fireworks_model":      "accounts/fireworks/models/llama-v3p1-8b-instruct",
    "generation_provider":  "groq",
    "generation_model":     "llama-3.1-8b-instant",
    "ldap_enabled":         "false",
    "ldap_url":             "",
    "ldap_bind_dn":         "",
    "ldap_bind_password":   "",
    "ldap_user_base":       "",
    "ldap_user_filter":     "(&(objectClass=user)(sAMAccountName={username}))",
    "ldap_require_group":   "",
    "ldap_username_attr":   "sAMAccountName",
    "ldap_email_attr":      "mail",
}

SENSITIVE = {
    "ldap_bind_password", "openai_api_key", "anthropic_api_key",
    "groq_api_key", "together_api_key", "cerebras_api_key",
    "openrouter_api_key", "fireworks_api_key",
}


def get_setting(session: Any, key: str) -> str:
    row = session.get(SystemConfig, key)
    if row is not None:
        if key in SENSITIVE:
            return decrypt_value(row.value)
        return row.value
    return DEFAULTS.get(key, "")


@router.get("/settings")
def read_settings(_: AdminUser, session: SessionDep) -> Dict[str, str]:
    rows = session.exec(select(SystemConfig)).all()
    db_map = {r.key: r.value for r in rows}
    merged: Dict[str, str] = {}
    for k, default_v in DEFAULTS.items():
        merged[k] = db_map.get(k, default_v)
    for k in SENSITIVE:
        if merged.get(k):
            merged[k] = "********"
    return merged


@router.put("/settings")
def update_settings(body: Dict[str, str], _: AdminUser, session: SessionDep) -> Dict[str, str]:
    for key, value in body.items():
        if key not in DEFAULTS:
            continue
        if key in SENSITIVE and value == "********":
            continue
        store_value = encrypt_value(value) if key in SENSITIVE and value else value
        row = session.get(SystemConfig, key)
        if row is None:
            row = SystemConfig(key=key, value=store_value)
        else:
            row.value = store_value
        session.add(row)
    session.commit()
    return read_settings(_, session)


@router.get("/health")
def health_check(_: AdminUser, session: SessionDep) -> Dict[str, Any]:
    ollama_host = get_setting(session, "ollama_host")

    ollama_ok = False
    models_list: List[str] = []
    try:
        req = urllib.request.Request(
            f"{ollama_host}/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            ollama_ok = True
            models_list = [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass

    openai_ok = False
    openai_key = get_setting(session, "openai_api_key")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key.strip())
            client.models.list()
            openai_ok = True
        except Exception:
            pass

    claude_ok = False
    anthropic_key = get_setting(session, "anthropic_api_key")
    if anthropic_key:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=anthropic_key.strip())
            client.messages.count_tokens(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "test"}]
            )
            claude_ok = True
        except Exception:
            claude_ok = bool(anthropic_key and len(anthropic_key) > 20 and anthropic_key.startswith("sk-ant-"))

    teams = session.exec(select(Team)).all()
    team_vector_stats: List[Dict[str, Any]] = []
    for team in teams:
        team_chroma = CHROMA_DIR / team.slug
        count = 0
        if team_chroma.exists():
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(team_chroma))
                col = client.get_or_create_collection("zettabrain_docs")
                count = col.count()
            except Exception:
                pass
        team_vector_stats.append({
            "team_id": team.id,
            "team_name": team.name,
            "team_slug": team.slug,
            "vector_docs": count,
        })

    cloud_providers_status: Dict[str, Any] = {}
    for cp in ("groq", "together", "cerebras", "openrouter", "fireworks"):
        cp_key = get_setting(session, f"{cp}_api_key")
        cp_ok = False
        if cp_key:
            try:
                from ..llm.providers.openai_compatible import OpenAICompatibleProvider
                provider = OpenAICompatibleProvider(provider_name=cp, api_key=cp_key)
                cp_ok = provider.check_health()
            except Exception:
                pass
        cloud_providers_status[cp] = {"ok": cp_ok, "key_set": bool(cp_key)}

    return {
        "ollama": {"ok": ollama_ok, "host": ollama_host, "models": models_list},
        "openai": {"ok": openai_ok},
        "claude": {"ok": claude_ok},
        "cloud_providers": cloud_providers_status,
        "teams": team_vector_stats,
    }


class PullModelRequest(SQLModel):
    model: str


@router.post("/pull-model")
def pull_model(body: PullModelRequest, _: AdminUser, session: SessionDep) -> Dict[str, str]:
    model = body.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    ollama_host = get_setting(session, "ollama_host")
    host = ollama_host or "http://localhost:11434"

    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(
                f"{host}/api/pull",
                data=json.dumps({"name": model, "stream": False}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=300,
        )
        data = json.loads(resp.read().decode())
        return {"status": data.get("status", "done"), "model": model}
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/vectorstore/{team_id}", status_code=204)
def clear_team_vectorstore(team_id: int, _: AdminUser, session: SessionDep) -> None:
    team = session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team_chroma = CHROMA_DIR / team.slug
    if not team_chroma.exists():
        return

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(team_chroma))
        try:
            client.delete_collection("zettabrain_docs")
        except Exception:
            pass
        client.get_or_create_collection("zettabrain_docs")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear vector store: {exc}")

    for fname in ("ingested_files.json", "bm25_index.pkl"):
        stale = team_chroma / fname
        if stale.exists():
            stale.unlink()
