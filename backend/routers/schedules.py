"""定时执行 CRUD + 手动触发。由 services/scheduler.py (APScheduler) 驱动。"""

import logging

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import Schedule, TestRun, TestRunCases, User
from routers.deps import require_project_access
from schemas import ScheduleCreate, ScheduleResponse, ScheduleUpdate
from services.executor import execute_run
from services.scheduler import add_job, remove_job
from services.task_manager import create_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{pid}/schedules", tags=["schedules"])


# ── List ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_schedules(
    pid: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_project_access(pid, user, db, "viewer")
    rows = (
        (await db.execute(
            select(Schedule).where(Schedule.project_id == pid).order_by(Schedule.id)
        ))
        .scalars()
        .all()
    )
    return [ScheduleResponse.model_validate(r).model_dump() for r in rows]


# ── Create ────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_schedule(
    pid: int,
    data: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_project_access(pid, user, db, "editor")

    # 校验 cron 表达式
    try:
        CronTrigger.from_crontab(data.cron_expr)
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cron expression",
        )

    schedule = Schedule(
        project_id=pid,
        suite_id=data.suite_id,
        case_ids=data.case_ids or [],
        cron_expr=data.cron_expr,
        enabled=data.enabled,
    )
    db.add(schedule)
    await db.flush()
    # APScheduler writes via a second SQLite connection, so release our lock first.
    await db.commit()

    if schedule.enabled:
        add_job(schedule.id, schedule.cron_expr)

    await db.refresh(schedule)
    return ScheduleResponse.model_validate(schedule)


# ── Update ────────────────────────────────────────────────────────────────


@router.put("/{sid}")
@db_retry()
async def update_schedule(
    pid: int,
    sid: int,
    data: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_project_access(pid, user, db, "editor")

    schedule = await db.get(Schedule, sid)
    if not schedule or schedule.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found"
        )

    if data.suite_id is not None:
        schedule.suite_id = data.suite_id
    if data.case_ids is not None:
        schedule.case_ids = data.case_ids
    if data.cron_expr is not None:
        schedule.cron_expr = data.cron_expr
    if data.enabled is not None:
        schedule.enabled = data.enabled

    # APScheduler writes via a second SQLite connection, so release our lock first.
    await db.commit()

    # 同步 APScheduler job
    remove_job(sid)
    if schedule.enabled:
        add_job(sid, schedule.cron_expr)

    await db.refresh(schedule)
    return ScheduleResponse.model_validate(schedule)


# ── Delete ────────────────────────────────────────────────────────────────


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_schedule(
    pid: int,
    sid: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_project_access(pid, user, db, "editor")

    schedule = await db.get(Schedule, sid)
    if not schedule or schedule.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found"
        )

    remove_job(sid)
    await db.delete(schedule)
    await db.commit()
    return None


# ── Manual trigger ────────────────────────────────────────────────────────


@router.post("/{sid}/trigger")
@db_retry()
async def trigger_schedule(
    pid: int,
    sid: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await require_project_access(pid, user, db, "editor")

    schedule = await db.get(Schedule, sid)
    if not schedule or schedule.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found"
        )

    # 按 suite_id 或 case_ids 取用例
    if schedule.suite_id:
        from models import TestSuiteCases

        case_rows = (
            (
                await db.execute(
                    select(TestSuiteCases.case_id)
                    .where(TestSuiteCases.suite_id == schedule.suite_id)
                )
            )
            .scalars()
            .all()
        )
    else:
        case_rows = schedule.case_ids or []

    if not case_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No cases to run",
        )

    run = TestRun(project_id=pid, status="pending", source="scheduled")
    db.add(run)
    await db.flush()
    for cid in case_rows:
        db.add(TestRunCases(run_id=run.id, case_id=cid))
    await db.commit()

    create_task(execute_run(run.id), task_id=f"run-{run.id}")
    return {"run_id": run.id}
