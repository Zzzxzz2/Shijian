"""Lightweight async task manager using ``asyncio.create_task``.

Keeps task state in an in-memory dict.  Designed for background execution
where persistence is not required (development / MVP).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any

_tasks: dict[str, dict[str, Any]] = {}
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))
_run_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


async def _run(task_id: str, coro) -> dict[str, Any]:
    async with _run_semaphore:
        _tasks[task_id]["status"] = "running"
        try:
            result = await coro
            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["result"] = result
        except asyncio.CancelledError:
            _tasks[task_id]["status"] = "cancelled"
            _tasks[task_id]["error"] = "Task was cancelled"
        except Exception as exc:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(exc)
    return _tasks[task_id]


def create_task(coro, task_id: str | None = None, **metadata: Any) -> str:
    """Schedule *coro* and return a unique task id for status polling."""
    tid = task_id or str(uuid.uuid4())
    _tasks[tid] = {
        "task_id": tid,
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }
    asyncio.create_task(_run(tid, coro))
    return tid


def get_task(task_id: str) -> dict[str, Any] | None:
    """Return task state dict, or ``None`` if the id is unknown."""
    return _tasks.get(task_id)
