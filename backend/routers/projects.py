from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import db_retry, get_db
from models import Project, ProjectMembers, TestCase, TestRun, User
from routers.deps import require_project_access
from schemas import (
    AuthConfig,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectStats,
    ProjectUpdate,
)
from services.auth_helper import _get_auth_token

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects(
    search: str = "",
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List projects accessible by the current user (owned or member) with optional search + pagination.

    Admin users see all projects (bypass membership check).
    """
    # Admin bypass: see all projects
    if current_user.role == "admin":
        base = select(Project)
    else:
        # Owned projects + projects where user is a member
        member_subq = select(ProjectMembers.project_id).where(ProjectMembers.user_id == current_user.id)
        base = select(Project).where(
            or_(Project.user_id == current_user.id, Project.id.in_(member_subq))
        )

    if search:
        base = base.where(Project.name.ilike(f"%{search}%"))

    # Total count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated rows
    rows_q = (
        base.order_by(Project.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(rows_q)).scalars().all()

    return {
        "items": [
            ProjectResponse.model_validate(r).model_dump() for r in rows
        ],
        "total": total,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        name=data.name,
        description=data.description or "",
        url=data.url or "",
        auth_config=data.auth_config or {},
        user_id=current_user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Auto-add creator as owner member
    db.add(ProjectMembers(project_id=project.id, user_id=current_user.id, role="owner"))
    await db.commit()

    return ProjectResponse.model_validate(project)


@router.get("/{id}")
async def get_project(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project = await require_project_access(id, current_user, db, "viewer")

    resp = ProjectDetailResponse.model_validate(project)
    case_cnt = (
        await db.execute(
            select(func.count()).where(TestCase.project_id == id)
        )
    ).scalar() or 0
    run_cnt = (
        await db.execute(
            select(func.count()).where(TestRun.project_id == id)
        )
    ).scalar() or 0
    resp.stats = {"test_cases": case_cnt, "test_runs": run_cnt}
    return resp


@router.put("/{id}")
@db_retry()
async def update_project(
    id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await require_project_access(id, current_user, db, "editor")

    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    if data.url is not None:
        project.url = data.url
    if data.auth_config is not None:
        project.auth_config = data.auth_config

    await db.commit()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_project(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await require_project_access(id, current_user, db, "owner")

    await db.delete(project)
    await db.commit()
    return None


@router.get("/{id}/stats")
async def get_project_stats(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return ProjectStats()
    project = await require_project_access(id, current_user, db, "viewer")

    case_cnt = (
        await db.execute(
            select(func.count()).where(TestCase.project_id == id)
        )
    ).scalar() or 0
    run_cnt = (
        await db.execute(
            select(func.count()).where(TestRun.project_id == id)
        )
    ).scalar() or 0
    return ProjectStats(test_cases=case_cnt, test_runs=run_cnt)


@router.get("/{id}/coverage")
async def get_project_coverage(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the coverage dashboard contract for schema-generated cases."""
    await require_project_access(id, current_user, db, "viewer")
    cases = (await db.execute(select(TestCase).where(TestCase.project_id == id))).scalars().all()
    endpoints = []
    type_counts: dict[str, int] = {}
    for case in cases:
        type_counts[case.test_type] = type_counts.get(case.test_type, 0) + 1
        key = (case.content or {}).get("coverage_key", "")
        if key:
            endpoints.append({"key": key, "covered": True, "name": case.name})
    covered = sum(1 for endpoint in endpoints if endpoint["covered"])
    return {
        "mode": "schema" if endpoints else "simple",
        "endpoints": endpoints,
        "endpoints_total": len(endpoints),
        "endpoints_covered": covered,
        "endpoints_uncovered": len(endpoints) - covered,
        "tests_by_type": type_counts,
    }


@router.post("/{id}/test-auth")
async def test_project_auth(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: AuthConfig | None = None,
):
    """Test whether the project's auth config can obtain a token.

    If a request body is provided, it overrides the stored auth_config for testing.
    """
    project = await require_project_access(id, current_user, db, "viewer")

    # Use body override if provided, otherwise fall back to stored config
    if body is not None:
        auth_config = body.model_dump()
    else:
        auth_config = project.auth_config or {}

    token = await _get_auth_token(auth_config, project.url or "")
    if token:
        return {
            "success": True,
            "token_preview": token[:20] + "...",
            "message": "认证成功",
        }
    else:
        return {
            "success": False,
            "message": "认证失败：无法获取 token，请检查配置",
        }
