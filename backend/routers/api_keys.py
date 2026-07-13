"""ApiKey management: create (encrypt), list (masked), delete, test."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import db_retry, get_db
from models import ApiKey, User
from schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate
from services.crypto import encrypt

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


def _mask(key: str) -> str:
    """Show first 4 + last 4 chars, mask middle."""
    if len(key) <= 8:
        return key[:4] + "****"
    return key[:4] + "****" + key[-4:]


@router.get("")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return []
    rows = (
        (await db.execute(
            select(ApiKey).where(ApiKey.user_id == current_user.id)
            .order_by(ApiKey.provider)
        ))
        .scalars()
        .all()
    )
    return [ApiKeyResponse.model_validate(r).model_dump() for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    encrypted = encrypt(data.api_key)
    api_key = ApiKey(
        user_id=current_user.id,
        name=data.name,
        provider=data.provider,
        api_key_encrypted=encrypted,
        api_key_masked=_mask(data.api_key),
        base_url=data.base_url,
        model=data.model,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyResponse.model_validate(api_key)


@router.patch("/{key_id}")
@db_retry()
async def update_api_key(
    key_id: int,
    data: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    api_key = await db.get(ApiKey, key_id)
    if not api_key or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        )

    if data.name is not None:
        api_key.name = data.name
    if data.provider is not None:
        api_key.provider = data.provider
    if data.base_url is not None:
        api_key.base_url = data.base_url
    if data.model is not None:
        api_key.model = data.model

    await db.commit()
    await db.refresh(api_key)
    return ApiKeyResponse.model_validate(api_key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    api_key = await db.get(ApiKey, key_id)
    if not api_key or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        )

    await db.delete(api_key)
    await db.commit()
    return None


@router.post("/{key_id}/test")
@db_retry()
async def test_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    api_key = await db.get(ApiKey, key_id)
    if not api_key or api_key.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        )

    from datetime import datetime, timezone
    from services.crypto import decrypt
    from openai import OpenAI

    decrypted_key = decrypt(api_key.api_key_encrypted)
    base_url = api_key.base_url or "https://token-plan-cn.xiaomimimo.com/v1"

    try:
        client = OpenAI(api_key=decrypted_key, base_url=base_url)
        client.models.list()
        api_key.is_valid = True
        api_key.last_tested_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "key_id": key_id,
            "provider": api_key.provider,
            "is_valid": True,
            "message": "连通性测试通过",
        }
    except Exception as e:
        api_key.is_valid = False
        api_key.last_tested_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "key_id": key_id,
            "provider": api_key.provider,
            "is_valid": False,
            "message": f"连通性测试失败：{e}",
        }
