"""Quick Test — natural language instant execution.

POST /api/quick-test  →  returns task_id + ws_url  →  background execution
streams results via WebSocket /ws/quick-test/{task_id}.
"""

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import async_session, db_retry, get_db
from models import ApiKey, Document, Project, TestCase, User
from routers.deps import require_project_access
from schemas import QuickTestRequest, QuickTestResponse
from services.ai_provider import get_provider
from services.auth_helper import _get_auth_token
from services.executor import execute_test_case
from services.task_manager import create_task as _spawn_task

from .ws import qt_broadcast

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quick-test"])

# Maximum wall-clock duration for a single quick-test run (seconds)
_MAX_DURATION: int = 600


# ── Normalisation ──────────────────────────────────────────────────────────


def _normalize_case(case: dict) -> dict:
    """Fill default fields so the executor never hits KeyError.

    Handles both the top-level fields and the nested ``content`` map
    consumed by ``execute_api_case``.
    """
    case.setdefault("test_type", "api")
    case.setdefault("name", "未命名用例")

    content: dict[str, Any] = case.get("content", {})
    content.setdefault("method", "GET")
    content.setdefault("url", "")
    content.setdefault("headers", {})
    content.setdefault("body", None)
    content.setdefault("assertions", [])
    case["content"] = content
    return case


# ── Background execution ───────────────────────────────────────────────────


async def _run_quick_test(
    task_id: str,
    prompt: str,
    project_id: int,
    doc_ids: list[int],
    user_id: int,
) -> dict:
    """Background coroutine — the core of the quick-test flow.

    Everything runs in a single ``asyncio.create_task`` so the POST
    handler returns immediately.  WebSocket pushes use the isolated
    ``_qt_connections`` pool in ``ws.py``.
    """
    task_start = time.monotonic()
    passed = 0
    failed = 0

    # ── Helper: push & check timeout ──────────────────────────────────
    async def _push(msg: dict) -> bool:
        """Broadcast *msg*; return ``True`` if still within deadline."""
        await qt_broadcast(task_id, msg)
        return time.monotonic() - task_start < _MAX_DURATION

    # ── Helper: push error + done and signal abort ────────────────────
    async def _abort(reason: str) -> dict:
        await _push({"type": "error", "data": reason})
        await _push({
            "type": "done",
            "data": {"passed": passed, "failed": failed, "total": passed + failed},
        })
        return {"passed": passed, "failed": failed, "total": passed + failed, "error": reason}

    # ── 0. Status: analysing ──────────────────────────────────────────
    if not await _push({"type": "status", "data": "正在分析需求..."}):
        return await _abort("任务超时")

    # ── 1. Resolve context + API keys ─────────────────────────────────
    async with async_session() as db:
        project = await db.get(Project, project_id)

        if not project:
            return await _abort("项目不存在")

        # Build context from referenced documents
        context = ""
        if doc_ids:
            rows = (
                (await db.execute(
                    select(Document).where(
                        Document.project_id == project_id,
                        Document.id.in_(doc_ids),
                    )
                ))
                .scalars()
                .all()
            )
            context = "\n\n".join(
                (d.content_text or "")[:3000] for d in rows if d.content_text
            )

        # Gather API keys for the user
        key_rows = (
            (await db.execute(
                select(ApiKey).where(ApiKey.user_id == user_id)
            ))
            .scalars()
            .all()
        )

    # ── 2. Generate test cases via AI ─────────────────────────────────
    provider = get_provider(project=project, api_keys=list(key_rows))

    auth_headers = None
    try:
        token = await _get_auth_token(project.auth_config or {}, project.url or "")
        if token:
            auth = project.auth_config or {}
            auth_headers = {
                auth.get("header_name", "Authorization"): auth.get(
                    "header_format", "Bearer {token}"
                ).format(token=token)
            }
    except Exception:
        logger.warning("Quick-test project authentication failed", exc_info=True)

    try:
        result_or_coro = provider.generate_plan(requirement=prompt, context=context)
        plan = await result_or_coro if asyncio.iscoroutine(result_or_coro) else result_or_coro
    except Exception as exc:
        logger.exception("Quick-test AI generation failed")
        return await _abort(f"AI 生成失败：{exc}")

    cases = plan.cases
    failover_trace = plan.failover_trace
    total = len(cases)

    if total == 0:
        return await _abort("AI 未生成任何用例")

    if not await _push({"type": "status", "data": f"生成了 {total} 条用例"}):
        return await _abort("任务超时")

    # ── 3. Execute each case ──────────────────────────────────────────
    for i, raw_case in enumerate(cases):
        # Check timeout before each case
        if time.monotonic() - task_start >= _MAX_DURATION:
            return await _abort("任务超时")

        case = _normalize_case(raw_case)
        temp_case = TestCase(
            id=0,
            project_id=project_id,
            name=case["name"],
            test_type=case.get("test_type", "api"),
            content=case.get("content", {}),
        )
        project_url = project.url or ""

        await _push({
            "type": "case_start",
            "data": {
                "name": case["name"],
                "index": i,
                "total": total,
                "test_type": case["test_type"],
            },
        })

        try:
            result = await execute_test_case(
                temp_case,
                project_url,
                run_id=0,
                auth_headers=auth_headers,
                project_id=project_id,
            )
        except Exception as exc:
            logger.exception("Quick-test case #%d failed", i)
            result = {
                "case_id": 0,
                "status": "error",
                "detail": {"error": str(exc)},
                "duration_ms": 0,
                "error": str(exc),
            }

        if result["status"] == "pass":
            passed += 1
        else:
            failed += 1

        await _push({
            "type": "case_done",
            "data": {
                "index": i,
                "name": case["name"],
                "status": result["status"],
                "duration_ms": result.get("duration_ms", 0),
                "detail": result.get("detail", {}),
            },
        })

    # ── 4. Final summary ──────────────────────────────────────────────
    done_data: dict[str, Any] = {
        "passed": passed,
        "failed": failed,
        "total": total,
    }
    if failover_trace:
        done_data["failover_trace"] = failover_trace

    await _push({"type": "done", "data": done_data})
    logger.info("Quick-test %s done: %d passed / %d failed / %d total", task_id, passed, failed, total)
    return done_data


# ── REST endpoint ──────────────────────────────────────────────────────────


@router.post("/api/quick-test")
@db_retry()
async def create_quick_test(
    data: QuickTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a quick-test prompt and get a WebSocket URL for live results.

    The request returns immediately — execution runs in the background
    and pushes results to ``/ws/quick-test/{task_id}``.
    """
    # Authorisation: the requesting user must own the target project
    await require_project_access(data.project_id, current_user, db, "editor")

    task_id = f"qt_{uuid.uuid4().hex[:8]}"
    ws_url = f"/ws/quick-test/{task_id}"

    _spawn_task(
        _run_quick_test(task_id, data.prompt, data.project_id, data.context_doc_ids, current_user.id),
        task_id=task_id,
        owner_id=current_user.id,
    )

    return QuickTestResponse(task_id=task_id, ws_url=ws_url)
