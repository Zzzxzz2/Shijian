"""个人用户中心：查看/修改资料、修改密码、通知配置。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, hash_password, verify_password
from database import db_retry, get_db
from models import User
from schemas import (
    NotificationConfigUpdate,
    PasswordUpdate,
    ProfileUpdate,
    UserProfileResponse,
)

router = APIRouter(prefix="/api/user", tags=["user"])


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.put("/profile", response_model=UserProfileResponse)
@db_retry()
async def update_profile(
    data: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    from sqlalchemy import select

    existing = await db.execute(
        select(User).where(User.username == data.username, User.id != current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    current_user.username = data.username
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/password")
@db_retry()
async def update_password(
    data: PasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="旧密码不正确",
        )
    current_user.password_hash = hash_password(data.new_password)
    current_user.token_version = (current_user.token_version or 0) + 1
    await db.commit()
    return {"ok": True}


@router.put("/notifications", response_model=UserProfileResponse)
@db_retry()
async def update_notifications(
    data: NotificationConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    current_config = dict(current_user.notification_config or {})
    current_config[data.type] = data.webhook_url
    current_user.notification_config = current_config
    await db.commit()
    await db.refresh(current_user)
    return current_user
