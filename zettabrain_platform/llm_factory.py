from __future__ import annotations

from typing import Dict, Optional, Tuple

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLLM


# Instance caches keyed by (provider, model, credential) tuples
_llm_cache: Dict[Tuple, BaseLLM] = {}
_embed_cache: Dict[Tuple, Embeddings] = {}


CLOUD_PROVIDERS = {
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
}


class LLMProvider:
    """Supported LLM provider identifiers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    CLAUDE = "claude"


class EmbeddingProvider:
    """Supported embedding provider identifiers."""
    OLLAMA = "ollama"
    OPENAI = "openai"


def get_llm(
    provider: str,
    model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    cloud_api_key: Optional[str] = None,
) -> BaseLLM:
    """
    Create an LLM instance based on the provider (cached per configuration).

    Args:
        provider: One of 'ollama', 'openai', 'claude'
        model: Model identifier (provider-specific)
        ollama_host: Ollama server URL (required for Ollama)
        openai_key: OpenAI API key (required for OpenAI)
        anthropic_key: Anthropic API key (required for Claude)

    Returns:
        BaseLLM: Initialized language model instance (cached)

    Raises:
        ValueError: If provider is unsupported or required credentials missing
    """
    # Create cache key based on provider and credentials
    if provider == LLMProvider.OLLAMA:
        cache_key = (provider, model, ollama_host)
    elif provider == LLMProvider.OPENAI:
        cache_key = (provider, model, openai_key[:8] if openai_key else None)
    elif provider == LLMProvider.CLAUDE:
        cache_key = (provider, model, anthropic_key[:8] if anthropic_key else None)
    elif provider in CLOUD_PROVIDERS:
        cache_key = (provider, model, cloud_api_key[:8] if cloud_api_key else None)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    # Return cached instance if available
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    # Create new instance
    if provider == LLMProvider.OLLAMA:
        if not ollama_host:
            raise ValueError("ollama_host is required for Ollama provider")
        from langchain_ollama import OllamaLLM
        llm = OllamaLLM(
            model=model,
            base_url=ollama_host,
            temperature=0.0,
            num_predict=1024,
        )

    elif provider in CLOUD_PROVIDERS:
        import os as _os
        key = cloud_api_key or _os.getenv(f"{provider.upper()}_API_KEY") or _os.getenv("ZBP_LLM_API_KEY")
        if not key:
            raise ValueError(f"API key required for {provider}. Set {provider.upper()}_API_KEY.")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            api_key=key,
            base_url=CLOUD_PROVIDERS[provider],
            temperature=0.0,
            max_tokens=1024,
        )

    elif provider == LLMProvider.OPENAI:
        if not openai_key:
            raise ValueError("openai_api_key is required for OpenAI provider")
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            api_key=openai_key,
            temperature=0.0,
            max_tokens=1024,
        )

    elif provider == LLMProvider.CLAUDE:
        if not anthropic_key:
            raise ValueError("anthropic_api_key is required for Claude provider")
        from langchain_anthropic import ChatAnthropic

        # Claude 4.7+ deprecated temperature parameter
        # Keep temperature for Claude 4.5, 4.6 and all 3.x models
        # Only exclude temperature for Claude 4.7+
        kwargs = {
            "model": model,
            "api_key": anthropic_key,
            "max_tokens": 1024,
        }

        # Parse version from model name to determine temperature support
        if model.startswith("claude-opus-4-") or model.startswith("claude-sonnet-4-") or model.startswith("claude-haiku-4-"):
            # Extract minor version (e.g., "claude-opus-4-8" -> 8)
            parts = model.split("-")
            if len(parts) >= 4:
                try:
                    minor_version = int(parts[3])
                    # Only add temperature for versions < 7 (4.5, 4.6)
                    if minor_version < 7:
                        kwargs["temperature"] = 0.0
                except (ValueError, IndexError):
                    # If we can't parse version, skip temperature (safer for newer models)
                    pass
        else:
            # Claude 3.x models and other formats - always include temperature
            kwargs["temperature"] = 0.0

        llm = ChatAnthropic(**kwargs)

    # Cache and return
    _llm_cache[cache_key] = llm
    return llm


def get_embeddings(
    provider: str,
    model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
) -> Embeddings:
    """
    Create an embeddings instance based on the provider (cached per configuration).

    Args:
        provider: One of 'ollama', 'openai'
        model: Model identifier (provider-specific)
        ollama_host: Ollama server URL (required for Ollama)
        openai_key: OpenAI API key (required for OpenAI)

    Returns:
        Embeddings: Initialized embeddings instance (cached)

    Raises:
        ValueError: If provider is unsupported or required credentials missing
    """
    # Create cache key based on provider and credentials
    if provider == EmbeddingProvider.OLLAMA:
        cache_key = (provider, model, ollama_host)
    elif provider == EmbeddingProvider.OPENAI:
        # Use first 8 chars of key for cache
        cache_key = (provider, model, openai_key[:8] if openai_key else None)
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")

    # Return cached instance if available
    if cache_key in _embed_cache:
        return _embed_cache[cache_key]

    # Create new instance
    if provider == EmbeddingProvider.OLLAMA:
        if not ollama_host:
            raise ValueError("ollama_host is required for Ollama embeddings")
        from langchain_ollama import OllamaEmbeddings
        embeddings = OllamaEmbeddings(model=model, base_url=ollama_host)

    elif provider == EmbeddingProvider.OPENAI:
        if not openai_key:
            raise ValueError("openai_api_key is required for OpenAI embeddings")
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(model=model, api_key=openai_key)

    # Cache and return
    _embed_cache[cache_key] = embeddings
    return embeddings


def get_llm_and_embeddings(
    llm_provider: str,
    embed_provider: str,
    llm_model: str,
    embed_model: str,
    ollama_host: Optional[str] = None,
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
) -> Tuple[BaseLLM, Embeddings]:
    """
    Convenience function to create both LLM and embeddings in one call.

    Args:
        llm_provider: LLM provider identifier
        embed_provider: Embedding provider identifier
        llm_model: LLM model name
        embed_model: Embedding model name
        ollama_host: Ollama server URL
        openai_key: OpenAI API key
        anthropic_key: Anthropic API key

    Returns:
        Tuple[BaseLLM, Embeddings]: Initialized LLM and embeddings instances
    """
    llm = get_llm(
        provider=llm_provider,
        model=llm_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
        anthropic_key=anthropic_key,
    )

    embeddings = get_embeddings(
        provider=embed_provider,
        model=embed_model,
        ollama_host=ollama_host,
        openai_key=openai_key,
    )

    return llm, embeddings
