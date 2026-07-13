"""Mock replay engine: match incoming request → return recorded response."""

import logging
from typing import Any
from urllib.parse import quote

import httpx

from database import async_session
from models import MockConfig, MockRecord

from .matcher import find_best_match

logger = logging.getLogger(__name__)


async def find_records(
    project_id: int,
    method: str,
    path: str,
    *,
    only_enabled: bool = True,
) -> list[MockRecord]:
    """Query matching MockRecord rows from DB (layer-0 pre-filter)."""
    from sqlalchemy import select  # noqa: PLC0415  – keep local to avoid top-level import churn

    async with async_session() as session:
        base = (
            select(MockRecord)
            .where(MockRecord.project_id == project_id)
            .where(MockRecord.method == method.upper())
            .where(MockRecord.path == path)
        )
        if only_enabled:
            base = base.where(MockRecord.enabled == True)  # noqa: E712

        result = await session.execute(base)
        rows = list(result.scalars().all())
        # Detach from session so we can use them outside
        for r in rows:
            session.expunge(r)
        return rows


async def replay(
    project_id: int,
    request: httpx.Request,
    *,
    only_enabled: bool = True,
    check_config: bool = False,
) -> httpx.Response | None:
    """Match *request* against stored records and return a recorded response.

    Returns ``None`` when no matching record is found (caller should treat as 404).

    Parameters
    ----------
    check_config:
        When ``True``, also check the project-level MockConfig.  If the engine
        is disabled (``enabled=False``) the call returns ``None`` immediately.
        Callers that sit behind a middleware (e.g. ``MockEngine.replay()``)
        should pass ``True``; unit tests that call ``replay_raw`` directly
        should keep the default ``False``.
    """
    if check_config and not await _is_engine_enabled(project_id):
        logger.debug("Mock engine disabled for project %d, skipping replay", project_id)
        return None

    method = request.method.upper()
    path = str(request.url.path)
    query_string = str(request.url.query.decode("utf-8") if request.url.query else "")
    request_headers = dict(request.headers)
    request_body = _read_body(request)

    records = await find_records(project_id, method, path, only_enabled=only_enabled)
    if not records:
        logger.debug("No mock records for %s %s", method, path)
        return None

    match = find_best_match(records, method, path, query_string, request_headers, request_body)
    if match is None:
        logger.debug("No matching mock record for %s %s (body/query/CT mismatch)", method, path)
        return None

    # Increment hit count
    await _increment_hit_count(match.id)

    # Build response
    content_bytes = _decode_body(match.response_body, match.response_body_type)
    return httpx.Response(
        status_code=match.response_status,
        headers=dict(match.response_headers or {}),
        content=content_bytes,
    )


async def replay_raw(
    project_id: int,
    method: str,
    path: str,
    query_string: str = "",
    request_headers: dict[str, str] | None = None,
    request_body: str = "",
    *,
    only_enabled: bool = True,
    check_config: bool = False,
) -> httpx.Response | None:
    """Synchronous-style replay for internal use when no httpx.Request is at hand."""
    # Build a minimal httpx.Request to reuse the core logic
    qs_bytes = _encode_query(query_string)
    url = httpx.URL(path=path, query=qs_bytes)
    req = httpx.Request(method=method, url=url, headers=request_headers or {}, content=request_body)
    return await replay(project_id, req, only_enabled=only_enabled, check_config=check_config)


async def _increment_hit_count(record_id: int) -> None:
    """Atomically increment hit_count."""
    from sqlalchemy import update  # noqa: PLC0415

    async with async_session() as session:
        stmt = (
            update(MockRecord)
            .where(MockRecord.id == record_id)
            .values(hit_count=MockRecord.hit_count + 1)
        )
        await session.execute(stmt)
        await session.commit()


def _read_body(request: httpx.Request) -> str:
    """Read request body as a string."""
    try:
        content = request.content
        if not content:
            return ""
        return content.decode("utf-8")
    except Exception:
        return ""


def _decode_body(body: str | None, body_type: str | None) -> bytes:
    """Decode stored body back to bytes for the httpx.Response."""
    if not body:
        return b""
    if (body_type or "text").lower() == "binary":
        import base64  # noqa: PLC0415
        try:
            return base64.b64decode(body)
        except Exception:
            logger.warning("Failed to decode base64 body, returning raw bytes")
            return body.encode("utf-8")
    return body.encode("utf-8")


# ── Internal helpers ─────────────────────────────────────────────────────────


def _encode_query(query_string: str) -> bytes:
    """Encode query string to ASCII-suitable bytes for ``httpx.URL``.

    URLs should be ASCII-only per HTTP spec; any non-ASCII chars are
    percent-encoded so ``httpx.URL(…, query=…)`` doesn't raise.
    """
    if not query_string:
        return b""
    try:
        return query_string.encode("ascii")
    except UnicodeEncodeError:
        # URL-encode non-ASCII characters, preserving common query delimiters.
        return quote(query_string, safe="=&?/%+").encode("ascii")


async def _is_engine_enabled(project_id: int) -> bool:
    """Check whether the project's MockConfig has ``enabled=True``.

    Returns ``True`` when no config row exists (conservative: allow replay).
    """
    from sqlalchemy import select  # noqa: PLC0415

    async with async_session() as session:
        result = await session.execute(
            select(MockConfig.enabled).where(MockConfig.project_id == project_id)
        )
        enabled = result.scalar_one_or_none()
        # No config row → assume enabled (allow through); otherwise respect the flag.
        return enabled if enabled is not None else True
