"""Backward-compatible re-export from the ``services/ai_provider/`` package.

All V2 code that imports from ``services.ai_provider`` continues to work
unchanged.  New code should import from ``services.ai_provider`` directly
(the package) — this file will be removed in a future cleanup.
"""

# ruff: noqa: F401 — intentional re-export for backward compat

from services.ai_provider.base import BaseAIProvider, GeneratePlanResult, TokenUsage
from services.ai_provider.claude import ClaudeProvider
from services.ai_provider.failover import FailoverProvider
from services.ai_provider.gemini import GeminiProvider
from services.ai_provider.mock import MockProvider
from services.ai_provider.ollama import OllamaProvider
from services.ai_provider.openai_compat import OpenAICompatibleProvider
from services.ai_provider import get_provider

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
