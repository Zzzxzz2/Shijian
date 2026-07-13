"""WebSocket endpoint for real-time test execution push."""

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from config import JWT_ALGORITHM, JWT_SECRET
from database import async_session
from models import TestRun
from services.task_manager import get_task as _get_task

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection pool: run_id → set of WebSocket connections
_connections: dict[int, set[WebSocket]] = {}


async def connect(run_id: int, ws: WebSocket):
    await ws.accept()
    if run_id not in _connections:
        _connections[run_id] = set()
    _connections[run_id].add(ws)


async def disconnect(run_id: int, ws: WebSocket):
    if run_id in _connections:
        _connections[run_id].discard(ws)
        if not _connections[run_id]:
            del _connections[run_id]


async def broadcast(run_id: int, message: dict):
    """Broadcast a message to all clients watching a run. Safe to call even with no connections."""
    for ws in list(_connections.get(run_id, set())):
        try:
            await ws.send_json(message)
        except Exception:
            _connections.get(run_id, set()).discard(ws)


@router.websocket("/ws/runs/{run_id}")
async def websocket_run(websocket: WebSocket, run_id: int):
    # Check if run exists
    async with async_session() as db:
        run = await db.get(TestRun, run_id)
        if not run:
            await websocket.accept()
            await websocket.send_json({"type": "error", "data": {"message": "Run not found"}})
            await websocket.close()
            return

        # If run already done, send final status and close
        if run.status in ("done", "failed"):
            await websocket.accept()
            await websocket.send_json({
                "type": "run_done",
                "data": {"status": run.status, "result": run.result},
            })
            await websocket.close()
            return

    # Accept connection and add to pool
    await connect(run_id, websocket)

    try:
        # Keep connection alive, listen for client messages (not used but required)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await disconnect(run_id, websocket)


# ══════════════════════════════════════════════════════════════════════════
#  Quick-test WebSocket — independent connection pool (keyed by str task_id)
# ══════════════════════════════════════════════════════════════════════════

_qt_connections: dict[str, set[WebSocket]] = {}
_qt_events: dict[str, list[dict]] = {}
_qt_locks: dict[str, asyncio.Lock] = {}
_QT_EVENT_HISTORY_LIMIT = 1000


def _qt_lock(task_id: str) -> asyncio.Lock:
    """Return the per-task lock protecting subscription and event replay."""
    if task_id not in _qt_locks:
        _qt_locks[task_id] = asyncio.Lock()
    return _qt_locks[task_id]


async def qt_connect(task_id: str, ws: WebSocket):
    """Accept a quick-test WS connection, then replay events it arrived after."""
    await ws.accept()
    async with _qt_lock(task_id):
        if task_id not in _qt_connections:
            _qt_connections[task_id] = set()
        _qt_connections[task_id].add(ws)
        for event in _qt_events.get(task_id, []):
            try:
                await ws.send_json(event)
            except Exception:
                _qt_connections[task_id].discard(ws)
                break


async def qt_disconnect(task_id: str, ws: WebSocket):
    """Remove *ws* from the quick-test connection pool; clean up empty sets."""
    if task_id in _qt_connections:
        _qt_connections[task_id].discard(ws)
        if not _qt_connections[task_id]:
            del _qt_connections[task_id]


async def qt_broadcast(task_id: str, message: dict):
    """Persist then push *message* so a just-connected client cannot miss it."""
    async with _qt_lock(task_id):
        history = _qt_events.setdefault(task_id, [])
        history.append(message)
        if len(history) > _QT_EVENT_HISTORY_LIMIT:
            del history[:-_QT_EVENT_HISTORY_LIMIT]
        for ws in list(_qt_connections.get(task_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                _qt_connections.get(task_id, set()).discard(ws)


@router.websocket("/ws/quick-test/{task_id}")
async def websocket_quick_test(
    websocket: WebSocket,
    task_id: str,
    token: str = Query(...),
):
    """Quick-test streaming endpoint — the client connects and receives the live flow.

    The caller **must** pass a valid JWT ``token`` as a query parameter.
    The endpoint validates the token and checks that *task_id* exists
    before accepting the connection.
    """
    # ── Auth: validate JWT token from query string ────────────────────
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            await websocket.close(code=4001, reason="Invalid token")
            return
        # Parse user_id (we don't need it here, just verifying the token is valid)
        _ = int(user_id_str)
    except (JWTError, ValueError, TypeError) as exc:
        logger.warning("WS quick-test rejected with invalid token: %s", exc)
        await websocket.close(code=4001, reason="Invalid token")
        return

    # ── Task existence check ──────────────────────────────────────────
    task = _get_task(task_id)
    if task is None:
        logger.warning("WS quick-test rejected: task %s not found", task_id)
        await websocket.close(code=4001, reason="Task not found")
        return

    await qt_connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await qt_disconnect(task_id, websocket)
