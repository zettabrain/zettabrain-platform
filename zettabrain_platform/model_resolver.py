"""Model resolution with three-tier fallback: team -> system config -> defaults."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from sqlmodel import Session

from .models import Team
from .routers.settings import get_setting


DEFAULTS = {
    "llm_provider": os.getenv("ZBP_LLM_PROVIDER", "ollama"),
    "llm_model": os.getenv("ZBP_LLM_MODEL", "qwen2.5:14b"),
    "embed_provider": os.getenv("ZBP_EMBED_PROVIDER", "ollama"),
    "embed_model": os.getenv("ZBP_EMBED_MODEL", "nomic-embed-text"),
    "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
}

CLOUD_PROVIDERS = ("groq", "together", "cerebras", "openrouter", "fireworks")


def resolve_team_models(session: Session, team_id: int) -> Dict[str, str | None]:
    """
    Resolve model configuration for a team with three-tier fallback.

    Returns a dictionary with all model configuration needed for RAG:
    {
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "embed_provider": "ollama",
        "embed_model": "nomic-embed-text",
        "ollama_host": "http://localhost:11434",
        "openai_key": "sk-...",
        "anthropic_key": "sk-ant-...",
    }

    Fallback hierarchy:
    1. Team.{field} (if not NULL)
    2. SystemConfig.{field} (via get_setting)
    3. Hard-coded DEFAULTS

    Args:
        session: Database session
        team_id: Team ID to resolve models for

    Returns:
        Dictionary with resolved model configuration
    """
    # Fetch the team
    team = session.get(Team, team_id)
    if not team:
        # If team doesn't exist, return system defaults
        return _resolve_system_defaults(session)

    # Resolve LLM provider and model
    llm_provider = (
        team.llm_provider
        or get_setting(session, "llm_provider")
        or DEFAULTS["llm_provider"]
    )

    # Resolve LLM model based on provider
    if team.llm_model:
        llm_model = team.llm_model
    elif llm_provider == "openai":
        llm_model = get_setting(session, "openai_llm_model") or "gpt-4o"
    elif llm_provider == "claude":
        llm_model = get_setting(session, "claude_llm_model") or "claude-sonnet-4.5"
    else:  # ollama
        llm_model = get_setting(session, "llm_model") or DEFAULTS["llm_model"]

    # Resolve embedding provider and model
    embed_provider = (
        team.embed_provider
        or get_setting(session, "embed_provider")
        or DEFAULTS["embed_provider"]
    )

    # Resolve embedding model based on provider
    if team.embed_model:
        embed_model = team.embed_model
    elif embed_provider == "openai":
        embed_model = get_setting(session, "openai_embed_model") or "text-embedding-3-small"
    else:  # ollama
        embed_model = get_setting(session, "embed_model") or DEFAULTS["embed_model"]

    ollama_host = get_setting(session, "ollama_host") or DEFAULTS["ollama_host"]
    openai_key = get_setting(session, "openai_api_key") or None
    anthropic_key = get_setting(session, "anthropic_api_key") or None

    cloud_api_key = None
    if llm_provider in CLOUD_PROVIDERS:
        cloud_api_key = (
            get_setting(session, f"{llm_provider}_api_key")
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


def _resolve_system_defaults(session: Session) -> Dict[str, str | None]:
    """
    Resolve system-level defaults (no team-specific config).

    Used as fallback when team doesn't exist or for system-wide queries.
    """
    llm_provider = get_setting(session, "llm_provider") or DEFAULTS["llm_provider"]

    if llm_provider == "openai":
        llm_model = get_setting(session, "openai_llm_model") or "gpt-4o"
    elif llm_provider == "claude":
        llm_model = get_setting(session, "claude_llm_model") or "claude-sonnet-4.5"
    else:  # ollama
        llm_model = get_setting(session, "llm_model") or DEFAULTS["llm_model"]

    embed_provider = get_setting(session, "embed_provider") or DEFAULTS["embed_provider"]

    if embed_provider == "openai":
        embed_model = get_setting(session, "openai_embed_model") or "text-embedding-3-small"
    else:  # ollama
        embed_model = get_setting(session, "embed_model") or DEFAULTS["embed_model"]

    ollama_host = get_setting(session, "ollama_host") or DEFAULTS["ollama_host"]
    openai_key = get_setting(session, "openai_api_key") or None
    anthropic_key = get_setting(session, "anthropic_api_key") or None

    cloud_api_key = None
    if llm_provider in CLOUD_PROVIDERS:
        cloud_api_key = (
            get_setting(session, f"{llm_provider}_api_key")
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
