"""测试集管理：CRUD + 一键执行。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import Project, TestCase, TestRun, TestRunCases, TestSuite, TestSuiteCases, User
from routers.deps import require_project_access
from schemas import SuiteCreate, SuiteDetail, SuiteItem, SuiteRunResponse, SuiteUpdate
from services.executor import execute_run
from services.task_manager import create_task

router = APIRouter(prefix="/api/projects/{pid}/suites", tags=["suites"])


# ── List ──────────────────────────────────────────────────────────────────


@router.get("")
async def list_suites(
    pid: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(pid, user, db, "viewer")

    rows = (
        (
            await db.execute(
                select(
                    TestSuite.id,
                    TestSuite.name,
                    TestSuite.description,
                    TestSuite.created_at,
                    func.count(TestSuiteCases.id).label("case_count"),
                )
                .outerjoin(TestSuiteCases, TestSuiteCases.suite_id == TestSuite.id)
                .where(TestSuite.project_id == pid)
                .group_by(TestSuite.id, TestSuite.name, TestSuite.description, TestSuite.created_at)
                .order_by(TestSuite.created_at.desc())
            )
        )
        .mappings()
        .all()
    )

    return [SuiteItem(**r) for r in rows]


# ── Create ────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_suite(
    pid: int,
    data: SuiteCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(pid, user, db, "editor")

    suite = TestSuite(project_id=pid, name=data.name, description=data.description)
    db.add(suite)
    await db.flush()

    for idx, cid in enumerate(data.case_ids or []):
        db.add(TestSuiteCases(suite_id=suite.id, case_id=cid, sort_order=idx))

    await db.commit()
    await db.refresh(suite)

    return SuiteItem(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        case_count=len(data.case_ids or []),
        created_at=suite.created_at,
    )


# ── Detail ────────────────────────────────────────────────────────────────


@router.get("/{sid}")
async def get_suite(
    pid: int,
    sid: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(pid, user, db, "viewer")

    suite = await db.get(TestSuite, sid)
    if not suite or suite.project_id != pid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    case_rows = (
        (
            await db.execute(
                select(
                    TestSuiteCases.case_id,
                    TestCase.name,
                )
                .join(TestCase, TestCase.id == TestSuiteCases.case_id)
                .where(TestSuiteCases.suite_id == sid)
                .order_by(TestSuiteCases.sort_order)
            )
        )
        .mappings()
        .all()
    )

    from schemas import SuiteCaseBrief

    cases = [SuiteCaseBrief(id=r["case_id"], name=r["name"]) for r in case_rows]

    return SuiteDetail(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        cases=cases,
        created_at=suite.created_at,
    )


# ── Update ────────────────────────────────────────────────────────────────


@router.put("/{sid}")
@db_retry()
async def update_suite(
    pid: int,
    sid: int,
    data: SuiteUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(pid, user, db, "editor")

    suite = await db.get(TestSuite, sid)
    if not suite or suite.project_id != pid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    if data.name is not None:
        suite.name = data.name
    if data.description is not None:
        suite.description = data.description

    if data.case_ids is not None:
        # 全量替换
        await db.execute(
            TestSuiteCases.__table__.delete().where(TestSuiteCases.suite_id == sid)
        )
        for idx, cid in enumerate(data.case_ids):
            db.add(TestSuiteCases(suite_id=sid, case_id=cid, sort_order=idx))

    await db.commit()
    await db.refresh(suite)

    return SuiteItem(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        case_count=len(data.case_ids or []),
        created_at=suite.created_at,
    )


# ── Delete ────────────────────────────────────────────────────────────────


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_suite(
    pid: int,
    sid: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(pid, user, db, "editor")

    suite = await db.get(TestSuite, sid)
    if not suite or suite.project_id != pid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    await db.execute(TestSuiteCases.__table__.delete().where(TestSuiteCases.suite_id == sid))
    await db.delete(suite)
    await db.commit()
    return None


# ── One-click run ─────────────────────────────────────────────────────────


@router.post("/{sid}/run")
@db_retry()
async def run_suite(
    pid: int,
    sid: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_access(pid, user, db, "editor")

    suite = await db.get(TestSuite, sid)
    if not suite or suite.project_id != pid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suite not found")

    # 按 sort_order 拿用例 ID
    case_ids = (
        (
            await db.execute(
                select(TestSuiteCases.case_id)
                .where(TestSuiteCases.suite_id == sid)
                .order_by(TestSuiteCases.sort_order)
            )
        )
        .scalars()
        .all()
    )

    if not case_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suite is empty")

    # 创建 TestRun
    run = TestRun(project_id=pid, status="pending", source="suite")
    db.add(run)
    await db.flush()  # 先 flush 拿到 run.id

    for cid in case_ids:
        db.add(TestRunCases(run_id=run.id, case_id=cid))

    # ⚠️ 顺序：必须先 commit，再 spawn
    # execute_run 在新 Session 中查询 run/test_run_cases，
    # 不 commit 的话那侧读不到数据
    await db.commit()
    create_task(execute_run(run.id), task_id=f"run-{run.id}")

    return SuiteRunResponse(run_id=run.id)
