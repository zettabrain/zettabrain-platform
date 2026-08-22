"""Model resolution with three-tier fallback: team → system config → defaults."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from sqlmodel import Session

from ..models import Team

DEFAULTS = {
    "llm_provider": os.getenv("ZBP_LLM_PROVIDER", "groq"),
    "llm_model": os.getenv("ZBP_LLM_MODEL", "llama-3.1-8b-instant"),
    "embed_provider": os.getenv("ZBP_EMBED_PROVIDER", "ollama"),
    "embed_model": os.getenv("ZBP_EMBED_MODEL", "nomic-embed-text"),
    "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
}


SENSITIVE_KEYS = {
    "openai_api_key", "anthropic_api_key", "groq_api_key",
    "together_api_key", "cerebras_api_key", "openrouter_api_key", "fireworks_api_key",
}


def _get_setting(session, key: str) -> str:
    from ..models import SystemConfig
    row = session.get(SystemConfig, key)
    if row is not None:
        if key in SENSITIVE_KEYS:
            from ..security.encryption import decrypt_value
            return decrypt_value(row.value)
        return row.value
    return ""


def resolve_team_models(session, team_id: int) -> Dict[str, str | None]:
    """Resolve model configuration for a team with three-tier fallback."""
    team = session.get(Team, team_id)
    if not team:
        return _resolve_system_defaults(session)

    llm_provider = (
        team.llm_provider
        or _get_setting(session, "llm_provider")
        or DEFAULTS["llm_provider"]
    )

    if team.llm_model:
        llm_model = team.llm_model
    elif llm_provider == "openai":
        llm_model = _get_setting(session, "openai_llm_model") or "gpt-4o"
    elif llm_provider == "claude":
        llm_model = _get_setting(session, "claude_llm_model") or "claude-sonnet-4.5"
    else:
        llm_model = _get_setting(session, "llm_model") or DEFAULTS["llm_model"]

    embed_provider = (
        team.embed_provider
        or _get_setting(session, "embed_provider")
        or DEFAULTS["embed_provider"]
    )

    if team.embed_model:
        embed_model = team.embed_model
    elif embed_provider == "openai":
        embed_model = _get_setting(session, "openai_embed_model") or "text-embedding-3-small"
    else:
        embed_model = _get_setting(session, "embed_model") or DEFAULTS["embed_model"]

    ollama_host = _get_setting(session, "ollama_host") or DEFAULTS["ollama_host"]
    openai_key = _get_setting(session, "openai_api_key") or None
    anthropic_key = _get_setting(session, "anthropic_api_key") or None

    cloud_providers = ("groq", "together", "cerebras", "openrouter", "fireworks")
    cloud_api_key = None
    if llm_provider in cloud_providers:
        cloud_api_key = (
            _get_setting(session, f"{llm_provider}_api_key")
            or os.getenv(f"{llm_provider.upper()}_API_KEY")
            or os.getenv("ZBP_LLM_API_KEY")
            or None
        )

    return {
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "embed_provider": embed_provider,
        "embed_model": embed_model,
        "ollama_host": ollama_host,
        "openai_key": openai_key,
        "anthropic_key": anthropic_key,
        "cloud_api_key": cloud_api_key,
    }


def _resolve_system_defaults(session) -> Dict[str, str | None]:
    llm_provider = _get_setting(session, "llm_provider") or DEFAULTS["llm_provider"]

    if llm_provider == "openai":
        llm_model = _get_setting(session, "openai_llm_model") or "gpt-4o"
    elif llm_provider == "claude":
        llm_model = _get_setting(session, "claude_llm_model") or "claude-sonnet-4.5"
    else:
        llm_model = _get_setting(session, "llm_model") or DEFAULTS["llm_model"]

    embed_provider = _get_setting(session, "embed_provider") or DEFAULTS["embed_provider"]

    if embed_provider == "openai":
        embed_model = _get_setting(session, "openai_embed_model") or "text-embedding-3-small"
    else:
        embed_model = _get_setting(session, "embed_model") or DEFAULTS["embed_model"]

    ollama_host = _get_setting(session, "ollama_host") or DEFAULTS["ollama_host"]
    openai_key = _get_setting(session, "openai_api_key") or None
    anthropic_key = _get_setting(session, "anthropic_api_key") or None

    cloud_providers = ("groq", "together", "cerebras", "openrouter", "fireworks")
    cloud_api_key = None
    if llm_provider in cloud_providers:
        cloud_api_key = (
            _get_setting(session, f"{llm_provider}_api_key")
            or os.getenv(f"{llm_provider.upper()}_API_KEY")
            or os.getenv("ZBP_LLM_API_KEY")
            or None
        )

    return {
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "embed_provider": embed_provider,
        "embed_model": embed_model,
        "ollama_host": ollama_host,
        "openai_key": openai_key,
        "anthropic_key": anthropic_key,
        "cloud_api_key": cloud_api_key,
    }
