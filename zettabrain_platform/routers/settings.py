from __future__ import annotations

import json
import logging
import shutil
import urllib.error
import urllib.request
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from sqlmodel import SQLModel, select

from ..config import CHROMA_DIR
from ..deps import AdminUser, SessionDep
from ..models import SystemConfig, Team

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin-settings"])

DEFAULTS: Dict[str, str] = {
    # Ollama settings
    "ollama_host":          "http://localhost:11434",
    "llm_model":            "llama3.1:8b",
    "embed_model":          "nomic-embed-text",

    # Provider selection
    "llm_provider":         "ollama",  # ollama | openai | claude | groq | together | cerebras | openrouter | fireworks
    "embed_provider":       "ollama",  # ollama | openai

    # OpenAI settings
    "openai_api_key":       "",
    "openai_llm_model":     "gpt-4o",
    "openai_embed_model":   "text-embedding-3-small",

    # Claude/Anthropic settings
    "anthropic_api_key":    "",
    "claude_llm_model":     "claude-sonnet-4-6",  # Claude 4.6 Sonnet (latest)

    # Cloud provider API keys
    "groq_api_key":         "",
    "together_api_key":     "",
    "cerebras_api_key":     "",
    "openrouter_api_key":   "",
    "fireworks_api_key":    "",

    # Cloud provider model selections
    "groq_llm_model":       "llama-3.1-8b-instant",
    "together_llm_model":   "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "cerebras_llm_model":   "llama3.1-8b",
    "openrouter_llm_model": "meta-llama/llama-3.1-8b-instruct:free",
    "fireworks_llm_model":  "accounts/fireworks/models/llama-v3p1-8b-instruct",

    # Skills/Generation LLM (separate from chat — defaults to global LLM if empty)
    "skills_llm_provider":  "",  # empty = use global llm_provider
    "skills_llm_model":     "",  # empty = use global resolved model
    "skills_llm_api_key":   "",  # empty = use the key for the chosen provider

    # LDAP settings
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
    "openrouter_api_key", "fireworks_api_key", "skills_llm_api_key",
}
# ldap_group_base was the old generic field; ldap_require_group is the AD replacement.
# Accept both on write so old saved values aren't silently dropped.


def _get_all_settings(session: Any) -> Dict[str, str]:
    rows = session.exec(select(SystemConfig)).all()
    db_map = {r.key: r.value for r in rows}
    merged: Dict[str, str] = {}
    for k, default_v in DEFAULTS.items():
        merged[k] = db_map.get(k, default_v)
    return merged


def get_setting(session: Any, key: str) -> str:
    row = session.get(SystemConfig, key)
    if row is not None:
        return row.value
    return DEFAULTS.get(key, "")


@router.get("/settings")
def read_settings(_: AdminUser, session: SessionDep) -> Dict[str, str]:
    settings = _get_all_settings(session)
    # Mask sensitive values
    for k in SENSITIVE:
        if settings.get(k):
            settings[k] = "********"
    return settings


@router.put("/settings")
def update_settings(
    body: Dict[str, str],
    _: AdminUser,
    session: SessionDep,
) -> Dict[str, str]:
    for key, value in body.items():
        if key not in DEFAULTS:
            continue
        # Don't overwrite password if masked placeholder sent back
        if key in SENSITIVE and value == "********":
            continue
        row = session.get(SystemConfig, key)
        if row is None:
            row = SystemConfig(key=key, value=value)
        else:
            row.value = value
        session.add(row)
    session.commit()
    result = _get_all_settings(session)
    for k in SENSITIVE:
        if result.get(k):
            result[k] = "********"
    return result


@router.get("/health")
def health_check(_: AdminUser, session: SessionDep) -> Dict[str, Any]:
    ollama_host = get_setting(session, "ollama_host")
    llm_model   = get_setting(session, "llm_model")
    embed_model = get_setting(session, "embed_model")

    # Ollama health
    ollama_ok     = False
    models_list: List[str] = []
    try:
        req = urllib.request.Request(
            f"{ollama_host}/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            ollama_ok   = True
            models_list = [m.get("name", "") for m in data.get("models", [])]
    except (urllib.error.URLError, Exception):
        pass

    # OpenAI health check
    openai_ok = False
    openai_models: List[str] = []
    openai_key = get_setting(session, "openai_api_key")
    if openai_key:
        try:
            from openai import OpenAI

            # Debug: log key format (first chars only for security)
            key_prefix = openai_key[:10] if len(openai_key) >= 10 else openai_key[:5]
            logger.info(f"OpenAI health check - key format: {key_prefix}... (length: {len(openai_key)})")

            client = OpenAI(api_key=openai_key.strip())  # Strip whitespace
            models_response = client.models.list()
            openai_ok = True
            # Get first 10 models, sorted by ID
            all_models = sorted([m.id for m in models_response.data])
            openai_models = all_models[:10]
            logger.info(f"OpenAI health check - API call successful, {len(all_models)} models found")
        except Exception as e:
            logger.warning(f"OpenAI health check - API call failed: {type(e).__name__}: {str(e)[:100]}")
            pass

    # Claude health check
    claude_ok = False
    anthropic_key = get_setting(session, "anthropic_api_key")
    if anthropic_key:
        try:
            from anthropic import Anthropic

            # Debug: log key format (first chars only for security)
            key_prefix = anthropic_key[:15] if len(anthropic_key) >= 15 else anthropic_key[:7]
            logger.info(f"Claude health check - key format: {key_prefix}... (length: {len(anthropic_key)})")

            client = Anthropic(api_key=anthropic_key.strip())  # Strip whitespace
            # Test with a minimal API call to verify the key works
            # Using count_tokens which is a cheap operation
            try:
                client.messages.count_tokens(
                    model="claude-sonnet-4-6",  # Claude 4.6 Sonnet (current latest)
                    messages=[{"role": "user", "content": "test"}]
                )
                claude_ok = True
                logger.info("Claude health check - API call successful")
            except Exception as e:
                logger.warning(f"Claude health check - API call failed: {type(e).__name__}: {str(e)[:100]}")
                # If count_tokens fails, fall back to format validation
                claude_ok = bool(anthropic_key and len(anthropic_key) > 20 and anthropic_key.startswith("sk-ant-"))
        except Exception as e:
            logger.error(f"Claude health check - initialization failed: {type(e).__name__}: {str(e)[:100]}")
            pass

    # Disk usage
    disk_path = "/opt/zettabrain-platform"
    try:
        usage     = shutil.disk_usage(disk_path)
        disk_used = usage.used
        disk_total = usage.total
    except OSError:
        disk_used  = 0
        disk_total = 0

    # Per-team vector doc counts (enumerate all collections for multi-embed)
    teams = session.exec(select(Team)).all()
    team_vector_stats: List[Dict[str, Any]] = []
    for team in teams:
        team_chroma = CHROMA_DIR / team.slug
        total_count = 0
        collections_info: List[Dict[str, Any]] = []
        if team_chroma.exists():
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(team_chroma))
                for col in client.list_collections():
                    c = col.count()
                    collections_info.append({"name": col.name, "count": c})
                    total_count += c
            except Exception:
                pass
        team_vector_stats.append({
            "team_id":     team.id,
            "team_name":   team.name,
            "team_slug":   team.slug,
            "docs_folder": team.docs_folder,
            "vector_docs": total_count,
            "collections": collections_info,
            "multi_embed_enabled": team.multi_embed_enabled,
        })

    return {
        "ollama": {
            "ok":         ollama_ok,
            "host":       ollama_host,
            "llm_model":  llm_model,
            "embed_model": embed_model,
            "models":     models_list,
        },
        "openai": {
            "ok":     openai_ok,
            "models": openai_models,
        },
        "claude": {
            "ok": claude_ok,
        },
        "disk": {
            "used_bytes":  disk_used,
            "total_bytes": disk_total,
            "used_gb":     round(disk_used  / (1024 ** 3), 2),
            "total_gb":    round(disk_total / (1024 ** 3), 2),
        },
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
        status = data.get("status", "done")
        return {"status": status, "model": model}
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

    # Clear hash cache and BM25 index so re-ingesting the same folder works fully
    for fname in ("ingested_files.json", "bm25_index.pkl"):
        stale = team_chroma / fname
        if stale.exists():
            stale.unlink()
