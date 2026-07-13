"""MockEngine — top-level orchestrator that ties recording, matching, and replay together.

Typical lifecycle::

    engine = MockEngine()
    await engine.initialize()       # create project-level config if missing
    await engine.start_recording()  # enable record mode + start background flush
    # ... intercept requests via engine.record_request() ...
    await engine.stop()             # stop recording, flush buffer
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from database import async_session, db_retry
from models import MockConfig, MockRecord

from .recorder import Recorder

logger = logging.getLogger(__name__)


# ── MockEngineRegistry ──────────────────────────────────────────────────────


class MockEngineRegistry:
    """Singleton cache of MockEngine instances keyed by project_id.

    Ensures `start-recording` and `stop-recording` talk to the **same**
    engine instance so background tasks are not leaked.
    """

    def __init__(self) -> None:
        self._engines: dict[int, MockEngine] = {}

    def get_or_create(self, project_id: int) -> MockEngine:
        """Return existing engine for *project_id*, or create and cache one."""
        if project_id not in self._engines:
            self._engines[project_id] = MockEngine(project_id)
        return self._engines[project_id]

    def get(self, project_id: int) -> MockEngine | None:
        """Return cached engine, or None if not yet created."""
        return self._engines.get(project_id)

    async def remove(self, project_id: int) -> None:
        """Shut down and remove engine for *project_id*."""
        engine = self._engines.pop(project_id, None)
        if engine is not None:
            await engine.shutdown()

    async def shutdown_all(self) -> None:
        """Shut down all cached engines. Called from ``main.py`` lifespan."""
        for engine in list(self._engines.values()):
            await engine.shutdown()
        self._engines.clear()
        logger.info("All MockEngines shut down")


# Module-level singleton — importers share the same registry.
registry: MockEngineRegistry = MockEngineRegistry()


# ── MockEngine ──────────────────────────────────────────────────────────────


class MockEngine:
    """Manages recording and replay for a given project.

    Thread-safe (asyncio): uses the Recorder's internal lock for buffer writes.
    """

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        self._recorder = Recorder()

        # ── In-memory config cache (refresh on first access) ──
        self._config: MockConfig | None = None
        self._loaded = False

    # ── Initialization ──────────────────────────────────────────────────

    async def initialize(self) -> MockConfig:
        """Ensure a MockConfig row exists for this project (create if missing).

        Returns the existing or freshly created config.
        """
        config = await self._load_config()
        if config is None:
            config = await self._create_config()
        self._config = config
        self._loaded = True
        return config

    async def _load_config(self) -> MockConfig | None:
        async with async_session() as session:
            result = await session.execute(
                select(MockConfig).where(MockConfig.project_id == self.project_id)
            )
            return result.scalar_one_or_none()

    @db_retry()
    async def _create_config(self) -> MockConfig:
        async with async_session() as session:
            config = MockConfig(project_id=self.project_id)
            session.add(config)
            await session.commit()
            await session.refresh(config)
            return config

    # ── Config accessors ───────────────────────────────────────────────

    async def get_config(self) -> MockConfig | None:
        """Return the cached config (refresh from DB if stale)."""
        if not self._loaded:
            await self.initialize()
        return self._config

    async def refresh_config(self) -> MockConfig:
        """Force-reload config from DB."""
        config = await self._load_config()
        if config is None:
            config = await self._create_config()
        self._config = config
        self._loaded = True
        return config

    @db_retry()
    async def update_config(self, **kwargs: Any) -> MockConfig:
        """Update config fields and persist."""
        async with async_session() as session:
            config = await session.get(MockConfig, self._config.id) if self._config else (
                await session.execute(
                    select(MockConfig).where(MockConfig.project_id == self.project_id)
                )
            ).scalar_one_or_none()
            if config is None:
                config = MockConfig(project_id=self.project_id)
                session.add(config)
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            await session.commit()
            await session.refresh(config)
            self._config = config
            self._loaded = True
            return config

    # ── Recording ──────────────────────────────────────────────────────

    async def start_recording(self) -> None:
        """Enable record mode and start the background flush loop."""
        await self.update_config(enabled=True, mode="record")
        await self._recorder.start()
        logger.info("Mock recording started for project %d", self.project_id)

    async def stop_recording(self) -> None:
        """Disable recording and flush pending records."""
        await self.update_config(enabled=False)
        await self._recorder.shutdown()
        logger.info("Mock recording stopped for project %d", self.project_id)

    async def record_request(
        self,
        method: str,
        path: str,
        query_string: str,
        request_headers: dict[str, str],
        request_body: bytes | str | None,
        response_status: int,
        response_headers: dict[str, str],
        response_body: bytes | str | None,
    ) -> None:
        """Record a single request/response pair (thread-safe, buffered)."""
        await self._recorder.record(
            project_id=self.project_id,
            method=method,
            path=path,
            query_string=query_string,
            request_headers=request_headers,
            request_body=request_body,
            response_status=response_status,
            response_headers=response_headers,
            response_body=response_body,
        )

    async def flush_recordings(self) -> None:
        """Persist buffered records before a management read."""
        await self._recorder.flush()

    # ── Replay ─────────────────────────────────────────────────────────

    async def replay(self, request: Any) -> Any:
        """Match *request* and return a recorded response (or None).

        *request* can be an ``httpx.Request`` or any object with
        ``.method``, ``.url.path``, ``.url.query``, ``.headers``, ``.content``.

        Respects the project-level ``MockConfig.enabled`` flag: when the
        engine is disabled, replay always returns ``None`` (the middleware
        should let the request fall through to the real API).
        """
        # Late import to avoid circular dependencies at module level
        from .replayer import replay  # noqa: PLC0415
        return await replay(self.project_id, request, check_config=True)

    # ── Management helpers ─────────────────────────────────────────────

    @db_retry()
    async def toggle_mock(self, record_id: int) -> bool:
        """Flip the enabled flag on a MockRecord. Returns the new state."""
        async with async_session() as session:
            record = await session.get(MockRecord, record_id)
            if record is None or record.project_id != self.project_id:
                return False
            record.enabled = not record.enabled
            await session.commit()
            return record.enabled

    @db_retry()
    async def update_mock(self, record_id: int, **fields: Any) -> MockRecord | None:
        """Update fields of a MockRecord. Updates ``source='manual'`` on edit."""
        async with async_session() as session:
            record = await session.get(MockRecord, record_id)
            if record is None or record.project_id != self.project_id:
                return None
            for key, value in fields.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            record.source = "manual"
            await session.commit()
            await session.refresh(record)
            return record

    # ── Shutdown ───────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Flush buffer and clean up. Called from ``registry.shutdown_all()``."""
        await self._recorder.shutdown()
        logger.info("MockEngine shut down for project %d", self.project_id)
