"""Admin-only endpoints: system stats, user management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import ApiKey, Document, Project, ProjectMembers, TestCase, TestRun, TokenUsageLog, User
from auth import hash_password
from schemas import (
    AdminProjectItem,
    AdminProjectListResponse,
    AdminResetPassword,
    AdminStats,
    AdminSystemStats,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserRoleUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


@router.get("/stats")
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    async def _count(model) -> int:
        return (await db.execute(select(func.count()).select_from(model))).scalar() or 0

    return AdminStats(
        users=await _count(User),
        projects=await _count(Project),
        test_cases=await _count(TestCase),
        test_runs=await _count(TestRun),
        api_keys=await _count(ApiKey),
        documents=await _count(Document),
    )


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    rows = (
        (await db.execute(select(User).order_by(User.created_at.desc())))
        .scalars()
        .all()
    )
    return [AdminUserResponse.model_validate(r).model_dump() for r in rows]


@router.put("/users/{user_id}/role")
@db_retry()
async def update_user_role(
    user_id: int,
    data: AdminUserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    if data.role not in ("admin", "user"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Role must be "admin" or "user"',
        )

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.role = data.role
    await db.commit()
    await db.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.post("/users", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_user(
    data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """Admin creates a user (bypasses register rate limits)."""
    result = await db.execute(
        select(User).where(User.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        email=data.email,
        verified=True,  # admin-created users are pre-verified
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    # Clean up related records before deleting user
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(TokenUsageLog).where(TokenUsageLog.user_id == user_id))
    await db.execute(sa_delete(ApiKey).where(ApiKey.user_id == user_id))
    # Reassign projects to admin
    from sqlalchemy import update as sa_update
    await db.execute(sa_update(Project).where(Project.user_id == user_id).values(user_id=admin.id))
    await db.delete(user)
    await db.commit()
    return None


@router.put("/users/{user_id}/reset-password")
@db_retry()
async def reset_password(
    user_id: int,
    data: AdminResetPassword,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    user.password_hash = hash_password(data.new_password)
    await db.commit()
    await db.refresh(user)
    return AdminUserResponse.model_validate(user)


# ── p2b: system-stats ─────────────────────────────────────────────────────


@router.get("/system-stats")
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    from datetime import datetime, timezone

    async def _count(model) -> int:
        return (await db.execute(select(func.count()).select_from(model))).scalar() or 0

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_exec = (
        await db.execute(
            select(func.count()).select_from(TestRun).where(TestRun.created_at >= today_start)
        )
    ).scalar() or 0

    return AdminSystemStats(
        users=await _count(User),
        projects=await _count(Project),
        test_cases=await _count(TestCase),
        test_runs=await _count(TestRun),
        today_executions=today_exec,
    )


# ── p2b: projects list ────────────────────────────────────────────────────


@router.get("/projects")
async def admin_list_projects(
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    total = (await db.execute(select(func.count()).select_from(Project))).scalar() or 0

    rows = (
        (
            await db.execute(
                select(
                    Project.id,
                    Project.name,
                    Project.user_id,
                    User.username.label("creator_name"),
                    func.count(ProjectMembers.id).label("member_count"),
                )
                .outerjoin(ProjectMembers, ProjectMembers.project_id == Project.id)
                .join(User, User.id == Project.user_id)
                .group_by(Project.id, Project.name, Project.user_id, User.username)
                .order_by(Project.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .mappings()
        .all()
    )

    items = [AdminProjectItem(**r) for r in rows]
    return AdminProjectListResponse(items=items, total=total)


# ── p2b: force logout ─────────────────────────────────────────────────────


@router.post("/users/{user_id}/logout")
@db_retry()
async def admin_force_logout(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    user.token_version = (user.token_version if user.token_version is not None else 0) + 1
    await db.commit()
    return {"ok": True}
