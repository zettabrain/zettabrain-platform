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


def get_chat_llm(
    provider: str,
    model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> BaseLLM:
    """Create a LangChain LLM for chat/RAG (cached)."""
    if provider == "ollama":
        cache_key = (provider, model, ollama_host)
    elif provider == "openai":
        cache_key = (provider, model, openai_key[:8] if openai_key else None)
    elif provider == "claude":
        cache_key = (provider, model, anthropic_key[:8] if anthropic_key else None)
    else:
        raise ValueError(f"Unsupported chat LLM provider: {provider}")

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if provider == "ollama":
        if not ollama_host:
            raise ValueError("ollama_host is required for Ollama provider")
        from langchain_ollama import OllamaLLM
        llm = OllamaLLM(model=model, base_url=ollama_host, temperature=0.0, num_predict=1024)

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
    **kwargs,
) -> LLMProvider:
    """Create a direct LLM provider for document generation (streaming support)."""
    provider_name = provider_name or os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider_name == "ollama":
        from .providers.ollama import OllamaProvider
        return OllamaProvider(**kwargs)

    elif provider_name == "groq":
        from .providers.groq_provider import GroqProvider
        if "model" not in kwargs:
            groq_model = os.getenv("GROQ_MODEL")
            if groq_model:
                kwargs["model"] = groq_model
        return GroqProvider(**kwargs)

    elif provider_name in ("claude", "anthropic"):
        try:
            from .providers.claude_provider import ClaudeProvider
            return ClaudeProvider(**kwargs)
        except ImportError:
            raise ValueError("Claude provider requires anthropic package: pip install anthropic")

    elif provider_name == "openai":
        try:
            from .providers.openai_provider import OpenAIProvider
            return OpenAIProvider(**kwargs)
        except ImportError:
            raise ValueError("OpenAI provider requires openai package: pip install openai")

    else:
        raise ValueError(
            f"Unknown generation provider: {provider_name}. "
            f"Supported: ollama, groq, claude, openai"
        )
