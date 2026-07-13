"""ClaudeProvider — Anthropic Claude via OpenAI-compatible endpoint.

Defaults to ``claude-sonnet-4-20250514`` at ``https://api.anthropic.com/v1``.
JSON mode may not be supported on the OpenAI-compatible endpoint — if so,
the prompt already instructs JSON output explicitly.
"""

from .openai_compat import OpenAICompatibleProvider


class ClaudeProvider(OpenAICompatibleProvider):
    """Claude model via OpenAI-compatible API endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "",
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com/v1",
            model=model,
        )
