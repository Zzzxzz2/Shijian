"""Recording middleware: intercept httpx request/response pairs and batch-write to DB.

High-frequency protection:
  - In-memory batch buffer (asyncio.Lock protected)
  - Auto-flush every BATCH_INTERVAL seconds or when buffer reaches BATCH_SIZE
  - Manual flush via flush() for graceful shutdown
"""

import asyncio
import base64
import logging
from typing import Any

from database import db_retry, async_session
from models import MockRecord
from services.http_security import redact_headers

logger = logging.getLogger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────
BATCH_SIZE: int = 100       # flush when buffer reaches this count
BATCH_INTERVAL: float = 5.0  # flush at most this many seconds apart

# ── Global registry for graceful shutdown ────────────────
_active_recorders: list["Recorder"] = []


async def shutdown_all() -> None:
    """Shut down all active recorders. Called from main.py lifespan shutdown."""
    for r in list(_active_recorders):
        await r.shutdown()
    _active_recorders.clear()
    logger.info("All mock recorders shut down")


class Recorder:
    """Intercepts outgoing HTTP requests and their responses, persists them.

    Usage::

        recorder = Recorder()
        await recorder.start()          # launches background flush loop
        await recorder.record(...)      # called by the intercepting middleware
        await recorder.shutdown()       # flush + cancel background loop
    """

    def __init__(self) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    # ── Public API ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch the periodic flush loop. Idempotent — safe to call multiple times."""
        if self._running:
            logger.debug("Recorder already running, skipping start()")
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        _active_recorders.append(self)
        logger.info("Mock recorder started (batch_size=%d, interval=%.1fs)", BATCH_SIZE, BATCH_INTERVAL)

    async def shutdown(self) -> None:
        """Flush remaining buffer and stop the background flush loop."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush()
        if self in _active_recorders:
            _active_recorders.remove(self)
        logger.info("Mock recorder shut down")

    async def record(
        self,
        project_id: int,
        method: str,
        path: str,
        query_string: str,
        request_headers: dict[str, str],
        request_body: bytes | str | None,
        response_status: int,
        response_headers: dict[str, str],
        response_body: bytes | str | None,
    ) -> None:
        """Buffer a single request/response pair for later persistence."""
        body_bytes, body_type = _encode_body(request_body)
        resp_bytes, resp_body_type = _encode_body(response_body)

        record = {
            "project_id": project_id,
            "method": method.upper(),
            "path": path,
            "query_string": query_string,
            "request_headers": redact_headers(request_headers),
            "request_body": body_bytes,
            "body_type": body_type,
            "response_status": response_status,
            "response_headers": redact_headers(response_headers),
            "response_body": resp_bytes,
            "response_body_type": resp_body_type,
            "content_type": response_headers.get("content-type", ""),
            "source": "auto",
        }

        async with self._lock:
            self._buffer.append(record)

        if len(self._buffer) >= BATCH_SIZE:
            await self.flush()

    async def flush(self) -> None:
        """Write buffered records to DB under a single db_retry."""
        async with self._lock:
            batch = list(self._buffer)
            self._buffer.clear()

        if not batch:
            return

        try:
            await self._flush_batch(batch)
            logger.info("Flushed %d mock record(s)", len(batch))
        except Exception:
            logger.exception("Failed to flush mock records (lost %d records)", len(batch))

    # ── Background flush ─────────────────────────────────────────────────

    async def _periodic_flush(self) -> None:
        while self._running:
            await asyncio.sleep(BATCH_INTERVAL)
            if self._buffer:
                await self.flush()

    # ── DB persistence ───────────────────────────────────────────────────

    @staticmethod
    @db_retry()
    async def _flush_batch(batch: list[dict[str, Any]]) -> None:
        """INSERT many records in one transaction."""
        async with async_session() as session:
            session.add_all(MockRecord(**item) for item in batch)
            await session.commit()


def _encode_body(body: bytes | str | None) -> tuple[str, str]:
    """Encode body for storage: text → text, binary → base64, None → ''."""
    if body is None or body == b"" or body == "":
        return "", "text"
    if isinstance(body, str):
        return body, "text"
    # bytes
    try:
        decoded = body.decode("utf-8")
        return decoded, "text"
    except UnicodeDecodeError:
        return base64.b64encode(body).decode("ascii"), "binary"
