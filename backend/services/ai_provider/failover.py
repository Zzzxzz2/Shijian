"""FailoverProvider — tries providers in priority order, falls back to Mock.

Timeout uses ``asyncio.wait_for`` + ``asyncio.to_thread`` so the event
loop truly cancels waiting after the deadline (unlike
``concurrent.futures.Future.result(timeout=…)`` which is defeated by
``ThreadPoolExecutor.__exit__`` calling ``shutdown(wait=True)``).
"""

import asyncio
import logging

from .base import BaseAIProvider, GeneratePlanResult
from .mock import MockProvider

logger = logging.getLogger(__name__)

# Each provider call times out after this many seconds
_PROVIDER_TIMEOUT: int = 30


class FailoverProvider(BaseAIProvider):
    """Tries a chain of providers in priority order.

    ``generate_plan`` is **async** — it offloads each sync provider call
    to a thread via ``asyncio.to_thread`` and enforces a per-provider
    timeout with ``asyncio.wait_for``.

    On failure (exception, timeout, empty result) the next provider in
    the chain is tried.  If **all** providers fail the result comes from
    ``MockProvider`` with a ``failover_trace`` describing each failure.
    """

    def __init__(self, providers: list[BaseAIProvider]) -> None:
        self.providers = providers

    async def generate_plan(self, requirement: str, context: str = "") -> GeneratePlanResult:  # type: ignore[override]
        """Async override — runs each provider in a thread with a real timeout."""
        errors: list[str] = []

        for provider in self.providers:
            name = type(provider).__name__
            provider_task = asyncio.create_task(
                asyncio.to_thread(provider.generate_plan, requirement, context)
            )
            try:
                result: GeneratePlanResult = await asyncio.wait_for(
                    provider_task,
                    timeout=_PROVIDER_TIMEOUT,
                )
                if result is not None and result.cases:
                    logger.info("Failover: %s succeeded (%d cases)", name, len(result.cases))
                    return result
                msg = f"{name}: returned {len(result.cases) if result else 0} cases (empty)"
                errors.append(msg)
                logger.warning("Failover: %s", msg)
            except asyncio.TimeoutError:
                # ``to_thread`` cannot stop work already running in its worker,
                # but cancelling and awaiting its asyncio wrapper releases the
                # task immediately instead of retaining cancelled wrappers under
                # sustained timeouts.
                provider_task.cancel()
                try:
                    await provider_task
                except asyncio.CancelledError:
                    pass
                msg = f"{name}: timeout after {_PROVIDER_TIMEOUT}s"
                errors.append(msg)
                logger.warning("Failover: %s, trying next", msg)
            except Exception as e:
                msg = f"{name}: {e}"
                errors.append(msg)
                logger.warning("Failover: %s, trying next", msg)

        # All providers failed → Mock fallback with trace
        logger.error("All providers failed: %s", "; ".join(errors))
        mock_result = MockProvider().generate_plan(requirement, context)
        mock_result.failover_trace = errors
        return mock_result
