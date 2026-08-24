"""Unified LLM factory — LangChain instances for chat, direct providers for generation."""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLLM

from .base import LLMProvider

# ──────────────────────────────────────────────────────────────────────────────
# LangChain-based factory (for RAG chat — handles response parsing, chains)
# ──────────────────────────────────────────────────────────────────────────────

_llm_cache: Dict[Tuple, BaseLLM] = {}
_embed_cache: Dict[Tuple, Embeddings] = {}


CLOUD_PROVIDERS = {
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
}


def get_chat_llm(
    provider: str,
    model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    cloud_api_key: Optional[str] = None,
) -> BaseLLM:
    """Create a LangChain LLM for chat/RAG (cached).

    Supports: ollama, openai, claude, groq, together, cerebras, openrouter, fireworks.
    """
    if provider == "ollama":
        cache_key = (provider, model, ollama_host)
    elif provider == "openai":
        cache_key = (provider, model, openai_key[:8] if openai_key else None)
    elif provider == "claude":
        cache_key = (provider, model, anthropic_key[:8] if anthropic_key else None)
    elif provider in CLOUD_PROVIDERS:
        cache_key = (provider, model, cloud_api_key[:8] if cloud_api_key else None)
    else:
        raise ValueError(f"Unsupported chat LLM provider: {provider}")

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if provider == "ollama":
        if not ollama_host:
            raise ValueError("ollama_host is required for Ollama provider")
        from langchain_ollama import OllamaLLM
        llm = OllamaLLM(model=model, base_url=ollama_host, temperature=0.0, num_predict=1024)

    elif provider in CLOUD_PROVIDERS:
        if not cloud_api_key:
            env_var = f"{provider.upper()}_API_KEY"
            cloud_api_key = os.getenv(env_var) or os.getenv("ZBP_LLM_API_KEY")
        if not cloud_api_key:
            raise ValueError(f"API key required for {provider}. Set {provider.upper()}_API_KEY.")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            api_key=cloud_api_key,
            base_url=CLOUD_PROVIDERS[provider],
            temperature=0.0,
            max_tokens=1024,
        )

    elif provider == "openai":
        if not openai_key:
            raise ValueError("openai_api_key is required for OpenAI provider")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=model, api_key=openai_key, temperature=0.0, max_tokens=1024)

    elif provider == "claude":
        if not anthropic_key:
            raise ValueError("anthropic_api_key is required for Claude provider")
        from langchain_anthropic import ChatAnthropic
        kwargs = {"model": model, "api_key": anthropic_key, "max_tokens": 1024}
        if model.startswith("claude-opus-4-") or model.startswith("claude-sonnet-4-") or model.startswith("claude-haiku-4-"):
            parts = model.split("-")
            if len(parts) >= 4:
                try:
                    minor_version = int(parts[3])
                    if minor_version < 7:
                        kwargs["temperature"] = 0.0
                except (ValueError, IndexError):
                    pass
        else:
            kwargs["temperature"] = 0.0
        llm = ChatAnthropic(**kwargs)

    _llm_cache[cache_key] = llm
    return llm


def get_embeddings(
    provider: str,
    model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
) -> Embeddings:
    """Create a LangChain embeddings instance (cached)."""
    if provider == "ollama":
        cache_key = (provider, model, ollama_host)
    elif provider == "openai":
        cache_key = (provider, model, openai_key[:8] if openai_key else None)
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")

    if cache_key in _embed_cache:
        return _embed_cache[cache_key]

    if provider == "ollama":
        if not ollama_host:
            raise ValueError("ollama_host is required for Ollama embeddings")
        from langchain_ollama import OllamaEmbeddings
        embeddings = OllamaEmbeddings(model=model, base_url=ollama_host)
    elif provider == "openai":
        if not openai_key:
            raise ValueError("openai_api_key is required for OpenAI embeddings")
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(model=model, api_key=openai_key)

    _embed_cache[cache_key] = embeddings
    return embeddings


# ──────────────────────────────────────────────────────────────────────────────
# Direct provider factory (for generation — streaming-capable, more providers)
# ──────────────────────────────────────────────────────────────────────────────

def create_generation_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> LLMProvider:
    """Create a direct LLM provider for document generation (streaming support).

    Supported providers:
      - ollama: Local models (requires Ollama running)
      - groq, together, cerebras, openrouter, fireworks: Free cloud APIs (OpenAI-compatible)
      - openai: OpenAI API (paid)
      - claude/anthropic: Anthropic API (paid)

    When called from the generate router, provider_name/model/api_key come from
    the system config (skills LLM settings or global LLM settings).
    """
    provider_name = provider_name or os.getenv("ZBP_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "groq")).lower()

    if provider_name == "ollama":
        from .providers.ollama import OllamaProvider
        ollama_kwargs = {}
        if base_url:
            ollama_kwargs["base_url"] = base_url
        if model:
            ollama_kwargs["model"] = model
        ollama_kwargs.update(kwargs)
        return OllamaProvider(**ollama_kwargs)

    elif provider_name in ("groq", "together", "cerebras", "openrouter", "fireworks", "openai"):
        from .providers.openai_compatible import OpenAICompatibleProvider
        oai_kwargs = {"provider_name": provider_name}
        if api_key:
            oai_kwargs["api_key"] = api_key
        if model:
            oai_kwargs["model"] = model
        if base_url:
            oai_kwargs["base_url"] = base_url
        oai_kwargs.update(kwargs)
        return OpenAICompatibleProvider(**oai_kwargs)

    elif provider_name in ("claude", "anthropic"):
        try:
            from .providers.claude_provider import ClaudeProvider
            claude_kwargs = {}
            if api_key:
                claude_kwargs["api_key"] = api_key
            if model:
                claude_kwargs["model"] = model
            claude_kwargs.update(kwargs)
            return ClaudeProvider(**claude_kwargs)
        except ImportError:
            raise ValueError("Claude provider requires anthropic package: pip install anthropic")

    else:
        raise ValueError(
            f"Unknown generation provider: {provider_name}. "
            f"Supported: ollama, groq, together, cerebras, openrouter, fireworks, openai, claude"
        )
