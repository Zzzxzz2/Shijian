"""TestRun CRUD + results."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import db_retry, get_db
from models import Project, TestCase, TestResult, TestRun, TestRunCases, User
from routers.deps import require_project_access
from schemas import (
    RunByTag,
    TestCaseResponse,
    TestResultResponse,
    TestRunCreate,
    TestRunDetailResponse,
    TestRunResponse,
)
from services.executor import execute_run
from services.report_service import generate_run_report
from services.task_manager import create_task

router = APIRouter(prefix="/api/projects/{pid}/runs", tags=["test-runs"])


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_run(
    pid: int,
    data: TestRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    if not data.case_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one case_id is required",
        )

    # Verify all case_ids belong to the project
    result = await db.execute(
        select(TestCase).where(
            TestCase.project_id == pid, TestCase.id.in_(data.case_ids)
        )
    )
    existing = {c.id for c in result.scalars().all()}
    missing = set(data.case_ids) - existing
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cases not found: {missing}",
        )

    run = TestRun(project_id=pid, status="queued")
    db.add(run)
    await db.flush()  # get run.id

    for cid in data.case_ids:
        db.add(TestRunCases(run_id=run.id, case_id=cid))

    await db.commit()
    await db.refresh(run)

    # Start execution as background task
    create_task(execute_run(run.id), task_id=f"run-{run.id}")

    return TestRunResponse.model_validate(run)


@router.get("")
async def list_runs(
    pid: int,
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return {"items": [], "total": 0}
    await require_project_access(pid, current_user, db, "viewer")

    base = select(TestRun).where(TestRun.project_id == pid)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = (
        (await db.execute(base.order_by(TestRun.created_at.desc()).offset(offset).limit(limit)))
        .scalars()
        .all()
    )

    return {
        "items": [TestRunResponse.model_validate(r).model_dump() for r in rows],
        "total": total,
    }


@router.get("/{run_id}")
async def get_run(
    pid: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await require_project_access(pid, current_user, db, "viewer")

    run = await db.get(TestRun, run_id)
    if not run or run.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    resp = TestRunDetailResponse.model_validate(run)

    # Fetch associated test cases
    link_rows = (
        await db.execute(
            select(TestCase)
            .join(TestRunCases, TestRunCases.case_id == TestCase.id)
            .where(TestRunCases.run_id == run_id)
        )
    ).scalars().all()

    resp.cases = [TestCaseResponse.model_validate(c).model_dump() for c in link_rows]
    return resp


@router.get("/{run_id}/results")
async def get_run_results(
    pid: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return []
    await require_project_access(pid, current_user, db, "viewer")

    run = await db.get(TestRun, run_id)
    if not run or run.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    # 当前 run 的结果
    rows = (
        (await db.execute(
            select(TestResult).where(TestResult.run_id == run_id)
            .order_by(TestResult.id)
        ))
        .scalars()
        .all()
    )

    # 找前一个 completed run（同项目、早于当前 run）
    prev_run = (
        (
            await db.execute(
                select(TestRun)
                .where(
                    TestRun.project_id == pid,
                    TestRun.status == "done",
                    TestRun.id < run_id,
                )
                .order_by(TestRun.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    # 构建 prev_status 映射
    prev_map: dict[int, str] = {}
    if prev_run:
        prev_results = (
            (await db.execute(
                select(TestResult).where(TestResult.run_id == prev_run.id)
            ))
            .scalars()
            .all()
        )
        prev_map = {r.case_id: r.status for r in prev_results}

    # 获取 case name 映射
    case_ids = {r.case_id for r in rows}
    name_map: dict[int, str] = {}
    if case_ids:
        case_rows = (
            (await db.execute(
                select(TestCase.id, TestCase.name).where(TestCase.id.in_(case_ids))
            ))
            .mappings()
            .all()
        )
        name_map = {r["id"]: r["name"] for r in case_rows}

    # 组装
    results = []
    for r in rows:
        prev = prev_map.get(r.case_id)
        if prev is None:
            change = "new"
        elif prev == r.status:
            change = "unchanged"
        elif prev == "pass" and r.status == "fail":
            change = "regression"
        elif prev == "fail" and r.status == "pass":
            change = "fixed"
        else:
            change = "changed"

        results.append(
            TestResultResponse(
                id=r.id,
                run_id=r.run_id,
                case_id=r.case_id,
                name=name_map.get(r.case_id, ""),
                status=r.status,
                detail=r.detail,
                duration_ms=r.duration_ms,
                failure_category=(r.detail or {}).get("failure_category", ""),
                prev_status=prev,
                change=change,
            )
        )

    return [r.model_dump() for r in results]


@router.get("/{run_id}/report")
async def get_run_report(
    pid: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        raise HTTPException(status_code=404, detail="Run not found")
    await require_project_access(pid, current_user, db, "viewer")

    run = await db.get(TestRun, run_id)
    if not run or run.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    html = await generate_run_report(run_id)
    return HTMLResponse(content=html, status_code=200)


@router.post("/by-tag", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_run_by_tag(
    pid: int,
    data: RunByTag,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    tag = data.tag
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tag is required",
        )

    base = select(TestCase).where(TestCase.project_id == pid)
    base = base.where(cast(TestCase.tags, String).contains(f'"{tag}"'))
    cases = (await db.execute(base)).scalars().all()

    if not cases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No cases found with tag '{tag}'",
        )

    run = TestRun(project_id=pid, status="queued")
    db.add(run)
    await db.flush()

    for c in cases:
        db.add(TestRunCases(run_id=run.id, case_id=c.id))

    await db.commit()
    await db.refresh(run)

    create_task(execute_run(run.id), task_id=f"run-{run.id}")
    return TestRunResponse.model_validate(run)


# ── Standalone run lookup (no project_id needed) ────────────────────────
run_lookup_router = APIRouter(prefix="/api/runs", tags=["test-runs"])


@run_lookup_router.get("/{run_id}")
async def get_run_standalone(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Get run detail without needing the project_id."""
    if current_user is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    # Verify the user owns the project this run belongs to
    project = await db.get(Project, run.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    resp = TestRunDetailResponse.model_validate(run)

    # Fetch associated test cases
    link_rows = (
        await db.execute(
            select(TestCase)
            .join(TestRunCases, TestRunCases.case_id == TestCase.id)
            .where(TestRunCases.run_id == run_id)
        )
    ).scalars().all()

    resp.cases = [TestCaseResponse.model_validate(c).model_dump() for c in link_rows]
    return resp


@run_lookup_router.get("/{run_id}/results")
async def get_run_results_standalone(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Get run results without needing the project_id."""
    if current_user is None:
        return []
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    project = await db.get(Project, run.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    rows = (
        (await db.execute(
            select(TestResult).where(TestResult.run_id == run_id)
            .order_by(TestResult.id)
        ))
        .scalars()
        .all()
    )

    return [
        TestResultResponse(
            id=r.id,
            run_id=r.run_id,
            case_id=r.case_id,
            status=r.status,
            detail=r.detail,
            duration_ms=r.duration_ms,
            failure_category=(r.detail or {}).get("failure_category", ""),
        ).model_dump()
        for r in rows
    ]


@run_lookup_router.get("/{run_id}/diff")
async def get_run_diff(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Compare current run with previous run on the same project."""
    if current_user is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    project = await db.get(Project, run.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    prev_run = (
        (await db.execute(
            select(TestRun)
            .where(
                TestRun.project_id == run.project_id,
                TestRun.status == "done",
                TestRun.id < run_id,
            )
            .order_by(TestRun.id.desc())
            .limit(1)
        ))
        .scalars()
        .first()
    )

    current_results = (
        (await db.execute(select(TestResult).where(TestResult.run_id == run_id)))
        .scalars()
        .all()
    )

    prev_results_map: dict[int, str] = {}
    if prev_run:
        prev_rows = (
            (await db.execute(select(TestResult).where(TestResult.run_id == prev_run.id)))
            .scalars()
            .all()
        )
        for r in prev_rows:
            prev_results_map[r.case_id] = r.status

    diff = []
    new_failures = 0
    new_passes = 0
    unchanged = 0

    for r in current_results:
        case = await db.get(TestCase, r.case_id)
        case_name = case.name if case else f"Case #{r.case_id}"
        prev_status = prev_results_map.get(r.case_id)

        if prev_status is None:
            status_str = "new_case"
        elif r.status == "fail" and prev_status == "pass":
            status_str = "new_failure"
            new_failures += 1
        elif r.status == "pass" and prev_status == "fail":
            status_str = "new_pass"
            new_passes += 1
        else:
            status_str = "unchanged"
            unchanged += 1

        diff.append({
            "case_id": r.case_id,
            "case_name": case_name,
            "current": r.status,
            "previous": prev_status,
            "status": status_str,
        })

    return {
        "current_run": {"id": run.id, "status": run.status, "result": run.result},
        "previous_run": {"id": prev_run.id, "status": prev_run.status, "result": prev_run.result} if prev_run else None,
        "diff": diff,
        "summary": {"new_failures": new_failures, "new_passes": new_passes, "unchanged": unchanged},
}


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_run(
    pid: int,
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")
    run = await db.get(TestRun, run_id)
    if not run or run.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    await db.delete(run)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
