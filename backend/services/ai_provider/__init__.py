"""AI Provider package — multi-vendor LLM support with failover chain.

Usage::

    from services.ai_provider import get_provider

    provider = get_provider(project, api_keys)
    result = provider.generate_plan("用户登录", context="...")
"""

import logging
from typing import Any

from models import ApiKey, Project
from services.crypto import decrypt

from .base import BaseAIProvider, GeneratePlanResult, TokenUsage
from .claude import ClaudeProvider
from .failover import FailoverProvider
from .gemini import GeminiProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

# Provider-name → (class, default_model, default_base_url)
_PROVIDER_REGISTRY: dict[str, tuple[type[BaseAIProvider], str, str]] = {
    "deepseek": (OpenAICompatibleProvider, "deepseek-chat", "https://api.deepseek.com/v1"),
    "openai":   (OpenAICompatibleProvider, "gpt-4o",          "https://api.openai.com/v1"),
    "claude":   (ClaudeProvider,           "claude-sonnet-4-20250514", "https://api.anthropic.com/v1"),
    "gemini":   (GeminiProvider,           "gemini-2.5-pro",  "https://generativelanguage.googleapis.com/v1beta/openai/"),
    "ollama":   (OllamaProvider,           "llama3",          "http://localhost:11434/v1"),
}


def get_provider(
    project: Project | None = None,
    api_keys: list[ApiKey] | None = None,
) -> BaseAIProvider:
    """Build a provider (or failover chain) for *project*.

    Resolution order:

    1. Read ``project.ai_config`` to determine mode + failover chain.
    2. Look up decrypted API keys for each provider in the chain.
    3. Return a ``FailoverProvider`` wrapping the resolved providers.
    4. If no keys are found at all → return ``MockProvider()``.

    When *project* is ``None`` (backward-compat call path) a
    ``MockProvider`` is returned.
    """
    if project is None:
        return MockProvider()

    ai_config: dict[str, Any] = project.ai_config or {}
    mode: str = ai_config.get("provider", "auto")
    api_keys = api_keys or []

    if mode == "failover":
        chain: list[str] = ai_config.get("failover_chain", ["deepseek"])
    else:
        chain = [mode] if mode != "auto" else ["deepseek"]

    providers = _resolve_chain(chain, api_keys)
    if not providers:
        logger.warning("No valid API keys for any provider in chain %s — using Mock", chain)
        return MockProvider()

    if len(providers) == 1:
        return providers[0]

    return FailoverProvider(providers)


def _resolve_chain(
    chain: list[str],
    api_keys: list[ApiKey],
) -> list[BaseAIProvider]:
    """Walk *chain* and instantiate providers for which a key exists."""
    key_index = _build_key_index(api_keys)
    providers: list[BaseAIProvider] = []

    for name in chain:
        name = name.lower().strip()
        entry = _PROVIDER_REGISTRY.get(name)
        if entry is None:
            logger.warning("Unknown provider '%s', skipping", name)
            continue

        klass, default_model, default_base = entry
        key_info = key_index.get(name)

        if key_info is None and name != "ollama":
            logger.debug("No API key for provider '%s', skipping chain entry", name)
            continue

        # Ollama needs no real key; for other providers the key is required
        api_key = key_info["api_key"] if key_info else ""
        base_url = key_info["base_url"] if key_info and key_info["base_url"] else default_base
        model = key_info["model"] if key_info and key_info["model"] else default_model

        try:
            provider = klass(api_key=api_key, base_url=base_url, model=model)
            providers.append(provider)
        except Exception:
            logger.exception("Failed to instantiate provider '%s', skipping", name)

    return providers


def _build_key_index(api_keys: list[ApiKey]) -> dict[str, dict[str, str]]:
    """Build ``{provider_name: {api_key, base_url, model}}`` from a list of ApiKey rows."""
    idx: dict[str, dict[str, str]] = {}
    for k in api_keys:
        name = (k.provider or "deepseek").lower().strip()
        try:
            decrypted = decrypt(k.api_key_encrypted)
        except Exception:
            logger.exception("Failed to decrypt API key for %s", name)
            continue
        idx[name] = {
            "api_key": decrypted,
            "base_url": k.base_url or "",
            "model": k.model or "",
        }
    return idx


# ── Re-export everything for convenience ──────────────────────────────────

__all__ = [
    "BaseAIProvider",
    "ClaudeProvider",
    "FailoverProvider",
    "GeminiProvider",
    "GeneratePlanResult",
    "MockProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "TokenUsage",
    "get_provider",
]
