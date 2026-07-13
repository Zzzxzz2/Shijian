"""Shared dependency: project-level access control based on role hierarchy.

Usage (pure function call, not FastAPI Depends):

    await require_project_access(pid, user, db, "editor")

Exceptions:
- admin role → always pass (no membership check)
- missing project → 404
- not a member → 403
- role too low → 403
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Project, ProjectMembers, User
from schemas import ROLE_HIERARCHY


async def require_project_access(
    project_id: int,
    user: User,
    db: AsyncSession,
    required_role: str = "viewer",
) -> Project:
    """Raise if ``user`` has insufficient access to ``project_id``. Returns the ``Project``."""

    # 1. Project existence (404 for non-existent projects, info hiding)
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # 2. Admin bypass
    if user.role == "admin":
        return project

    # 3. Membership check
    result = await db.execute(
        select(ProjectMembers).where(
            ProjectMembers.project_id == project_id,
            ProjectMembers.user_id == user.id,
        )
    )
    member = result.scalars().first()

    # 4. Legacy fallback: project owner still has full access even if no ProjectMembers row
    if not member:
        if project.user_id == user.id:
            return project
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="你不是该项目的成员",
        )

    # 5. Role-level check
    if ROLE_HIERARCHY.get(member.role, -1) < ROLE_HIERARCHY.get(required_role, 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )

    return project
