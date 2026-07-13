"""OllamaProvider — local Ollama via OpenAI-compatible endpoint.

Defaults to ``llama3`` at ``http://localhost:11434/v1``.
"""

from .openai_compat import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama model via OpenAI-compatible API endpoint."""

    def __init__(
        self,
        api_key: str = "ollama",  # Ollama does not require a real key
        model: str = "llama3",
        base_url: str = "",
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url or "http://localhost:11434/v1",
            model=model,
        )
