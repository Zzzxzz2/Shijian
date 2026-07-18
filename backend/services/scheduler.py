"""APScheduler 调度服务 — AsyncIOScheduler + persistent SQLAlchemy job store。"""

import logging
from datetime import datetime, timezone

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _jobstore_url(engine_url: str) -> str:
    """Convert the application's async SQLAlchemy URL for APScheduler's sync store."""
    return engine_url.replace("sqlite+aiosqlite", "sqlite", 1).replace(
        "postgresql+asyncpg", "postgresql", 1
    )


async def init_scheduler(engine_url: str) -> None:
    """启动调度器 + 注册 jobstore + 恢复已有定时任务。"""
    scheduler.add_jobstore(SQLAlchemyJobStore(url=_jobstore_url(engine_url)), "default")
    scheduler.start()
    await _restore_schedules()
    logger.info("APScheduler started (SQLAlchemyJobStore)")


async def shutdown_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("APScheduler shut down")


def add_job(schedule_id: int, cron_expr: str) -> None:
    """注册一个 APScheduler job。"""
    scheduler.add_job(
        _execute_schedule,
        trigger=CronTrigger.from_crontab(cron_expr),
        args=[schedule_id],
        id=f"schedule_{schedule_id}",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=None,
    )


def remove_job(schedule_id: int) -> None:
    """删除一个 APScheduler job（不存在时静默忽略）。"""
    try:
        scheduler.remove_job(f"schedule_{schedule_id}")
    except Exception:
        pass


async def _restore_schedules() -> None:
    """启动时把所有 enabled 的 Schedule 注册进 APScheduler。"""
    from database import async_session
    from models import Schedule

    async with async_session() as db:
        rows = (
            (await db.execute(select(Schedule).where(Schedule.enabled == True)))
            .scalars()
            .all()
        )
        for s in rows:
            add_job(s.id, s.cron_expr)
            logger.info("Restored schedule %d: %s", s.id, s.cron_expr)


async def _execute_schedule(schedule_id: int) -> None:
    """APScheduler 触发的定时执行入口。"""
    from database import async_session
    from models import Schedule, TestRun, TestRunCases, TestSuiteCases
    from services.executor import execute_run
    from services.task_manager import create_task

    async with async_session() as db:
        schedule = await db.get(Schedule, schedule_id)
        if not schedule or not schedule.enabled:
            return

        # 按 suite_id 或 case_ids 获取用例
        if schedule.suite_id:
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
            logger.warning("Schedule %d: no cases to run", schedule_id)
            return

        # 创建 TestRun + spawn execute_run
        run = TestRun(project_id=schedule.project_id, status="pending", source="scheduled")
        db.add(run)
        await db.flush()
        for cid in case_rows:
            db.add(TestRunCases(run_id=run.id, case_id=cid))
        await db.commit()

        now = datetime.now(timezone.utc)
        schedule.last_run_at = now
        schedule.next_run_at = CronTrigger.from_crontab(
            schedule.cron_expr, timezone=timezone.utc
        ).get_next_fire_time(now, now)
        await db.commit()

        # ── 执行 run（同步等待完成）────────────────────────────────────
        logger.info("Schedule %d: executing run %d (%d cases)", schedule_id, run.id, len(case_rows))
        try:
            await execute_run(run.id)
        except Exception:
            logger.exception("Schedule %d execute_run failed", schedule_id)

        # ── 执行完后发送 webhook 通知 ──────────────────────────────────
        try:
            from services.notifier import send_notification
            async with async_session() as ndb:
                s = await ndb.get(Schedule, schedule_id)
                r = await ndb.get(TestRun, run.id)
                if s and r:
                    await send_notification(s, r)
        except Exception:
            logger.exception("Schedule %d notification failed", schedule_id)
