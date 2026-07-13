"""BaseAIProvider ABC + data classes.

Extracted from V2 ``services/ai_provider.py`` — unchanged signatures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class GeneratePlanResult:
    cases: list[dict]
    token_usage: TokenUsage
    failover_trace: list[str] | None = None  # populated by FailoverProvider


class BaseAIProvider(ABC):
    @abstractmethod
    def generate_plan(self, requirement: str, context: str = "") -> GeneratePlanResult:
        pass
