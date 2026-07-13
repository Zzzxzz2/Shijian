"""Project member management — CRUD for ProjectMembers (owner only)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import ProjectMembers, User
from schemas import ProjectMemberCreate, ProjectMemberResponse, ProjectMemberUpdate
from routers.deps import require_project_access

router = APIRouter(prefix="/api/projects/{pid}/members", tags=["members"])


async def _get_member(pid: int, uid: int, db: AsyncSession) -> ProjectMembers:
    """Fetch a single project member or raise 404."""
    member = (
        await db.execute(
            select(ProjectMembers).where(
                ProjectMembers.project_id == pid,
                ProjectMembers.user_id == uid,
            )
        )
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )
    return member


@router.get("")
async def list_members(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all members of a project (viewer+ can see)."""
    await require_project_access(pid, current_user, db, "viewer")

    rows = (
        await db.execute(
            select(ProjectMembers).where(ProjectMembers.project_id == pid)
            .order_by(ProjectMembers.created_at)
        )
    ).scalars().all()

    result = []
    for m in rows:
        from models import User as UserModel  # noqa: PLC0415
        user = await db.get(UserModel, m.user_id)
        result.append(ProjectMemberResponse(
            id=m.id,
            project_id=m.project_id,
            user_id=m.user_id,
            role=m.role,
            username=user.username if user else "unknown",
            created_at=m.created_at,
        ))
    return result


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def add_member(
    pid: int,
    data: ProjectMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a member (owner only)."""
    await require_project_access(pid, current_user, db, "owner")

    # Verify target user exists
    from models import User as UserModel  # noqa: PLC0415
    target = await db.get(UserModel, data.user_id)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目标用户不存在",
        )

    # Check not already a member
    existing = (
        await db.execute(
            select(ProjectMembers).where(
                ProjectMembers.project_id == pid,
                ProjectMembers.user_id == data.user_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该用户已是项目成员",
        )

    member = ProjectMembers(
        project_id=pid,
        user_id=data.user_id,
        role=data.role or "viewer",
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        username=target.username,
        created_at=member.created_at,
    )


@router.patch("/{uid}")
@db_retry()
async def update_member_role(
    pid: int,
    uid: int,
    data: ProjectMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change a member's role (owner only). Cannot change the last owner."""
    await require_project_access(pid, current_user, db, "owner")

    member = await _get_member(pid, uid, db)

    # Protect last owner
    if member.role == "owner" and data.role != "owner":
        owner_count = (
            await db.execute(
                select(func.count()).where(
                    ProjectMembers.project_id == pid,
                    ProjectMembers.role == "owner",
                )
            )
        ).scalar() or 0
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="项目至少需要一名 owner",
            )

    member.role = data.role
    await db.commit()
    await db.refresh(member)

    from models import User as UserModel  # noqa: PLC0415
    user = await db.get(UserModel, member.user_id)

    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        username=user.username if user else "unknown",
        created_at=member.created_at,
    )


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def remove_member(
    pid: int,
    uid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member (owner only). Cannot remove self."""
    await require_project_access(pid, current_user, db, "owner")

    if uid == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除自己",
        )

    member = await _get_member(pid, uid, db)

    # Protect last owner
    if member.role == "owner":
        owner_count = (
            await db.execute(
                select(func.count()).where(
                    ProjectMembers.project_id == pid,
                    ProjectMembers.role == "owner",
                )
            )
        ).scalar() or 0
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="项目至少需要一名 owner",
            )

    await db.delete(member)
    await db.commit()
    return None
