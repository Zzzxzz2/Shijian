"""GeminiProvider — Google Gemini via OpenAI-compatible endpoint.

Defaults to ``gemini-2.5-pro`` at
``https://generativelanguage.googleapis.com/v1beta/openai/``.
"""

from .openai_compat import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    """Gemini model via OpenAI-compatible API endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-pro",
        base_url: str = "",
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta/openai/",
            model=model,
        )
