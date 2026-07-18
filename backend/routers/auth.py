from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_access_token,
    create_guest_token,
    get_current_user,
    hash_password,
    verify_password,
)
from database import db_retry, get_db
from mail import send_verify_email
from models import User
from schemas import (
    ChangePassword,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── In-memory register rate limit store ───────────────────────────────────
_reg_global: list[datetime] = []  # all register timestamps (global daily)
_reg_ip: dict[str, list[datetime]] = defaultdict(list)  # per-IP timestamps
_reg_cooldown: dict[str, datetime] = {}  # per-IP last register (10-min cooldown)

# Rate-limit email resends
_last_send: dict[str, datetime] = {}


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting common reverse-proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def _clean_old(entries: list[datetime], cutoff: datetime) -> list[datetime]:
    """Remove entries older than *cutoff*."""
    return [e for e in entries if e > cutoff]


# ══════════════════════════════════════════════════════════════════════════
#  Register (rate-limited)
# ══════════════════════════════════════════════════════════════════════════


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
@db_retry()
async def register(data: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    client_ip = _get_client_ip(request)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ten_min_ago = now - timedelta(minutes=10)

    # ── Rate limits ───────────────────────────────────────────────────────
    # 1) Global daily max 3
    _reg_global[:] = _clean_old(_reg_global, today_start)
    if len(_reg_global) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="今日注册名额已满",
        )

    # 2) Per-IP daily max 2
    ip_entries = _reg_ip[client_ip]
    ip_entries[:] = _clean_old(ip_entries, today_start)
    if len(ip_entries) >= 2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="今日注册次数已达上限",
        )

    # 3) Per-IP 10-min cooldown (max 1 per 10 min)
    last = _reg_cooldown.get(client_ip)
    if last and last > ten_min_ago:
        remaining_sec = int((last - ten_min_ago).total_seconds())
        remaining_min = remaining_sec // 60 + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"注册太频繁，请 {remaining_min} 分钟后再试",
        )

    # ── Check duplicate ───────────────────────────────────────────────────
    result = await db.execute(
        select(User).where(User.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    # ── Create user ───────────────────────────────────────────────────────
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role="admin" if user_count == 0 else "user",
        email=data.email,
        verified=False,
        ip_address=client_ip,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # ── Update rate-limit state ───────────────────────────────────────────
    _reg_global.append(now)
    ip_entries.append(now)
    _reg_cooldown[client_ip] = now

    # ── Send verification email (if email provided) ──────────────────────
    if data.email:
        verify_token = create_access_token({"sub": str(user.id), "email": data.email, "purpose": "verify"})
        verify_url = f"{str(request.base_url).rstrip('/')}/app.html#/verify?token={verify_token}"
        await send_verify_email(data.email, data.username, verify_url)

    token = create_access_token({"sub": str(user.id)}, user=user)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


# ══════════════════════════════════════════════════════════════════════════
#  Login
# ══════════════════════════════════════════════════════════════════════════


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.username == data.username)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token({"sub": str(user.id)}, user=user)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


# ══════════════════════════════════════════════════════════════════════════
#  Guest token
# ══════════════════════════════════════════════════════════════════════════


@router.post("/guest-token", response_model=TokenResponse)
async def guest_token():
    token = create_guest_token()
    now = datetime.now(timezone.utc)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(id=0, username="访客", role="guest", created_at=now),
    )


# ══════════════════════════════════════════════════════════════════════════
#  Get current user
# ══════════════════════════════════════════════════════════════════════════


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


# ══════════════════════════════════════════════════════════════════════════
#  Change password
# ══════════════════════════════════════════════════════════════════════════


@router.put("/change-password")
@db_retry()
async def change_password(
    data: ChangePassword,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )
    if len(data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters",
        )
    current_user.password_hash = hash_password(data.new_password)
    current_user.token_version = (current_user.token_version or 0) + 1
    await db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
#  Email verification
# ══════════════════════════════════════════════════════════════════════════


class VerifyBody(BaseModel):
    token: str


class SendVerifyBody(BaseModel):
    email: str = ""


@router.post("/verify-email")
@db_retry()
async def verify_email(data: VerifyBody, db: AsyncSession = Depends(get_db)):
    """Verify a user's email using the token from the verification link."""
    try:
        payload = jwt.decode(data.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "verify":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token purpose",
            )
        user_id_str: str = payload.get("sub", "")
        user_id = int(user_id_str)
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if user.verified:
        return {"ok": True, "message": "邮箱已验证"}
    user.verified = True
    await db.commit()
    return {"ok": True, "message": "邮箱验证成功"}


@router.post("/send-verify")
@db_retry()
async def send_verify(
    data: SendVerifyBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-send verification email."""
    email = data.email or current_user.email
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address to send to",
        )

    # Rate-limit resends: 1 per 60 seconds
    now = datetime.now(timezone.utc)
    last = _last_send.get(current_user.username)
    if last and (now - last).total_seconds() < 60:
        remaining = 60 - int((now - last).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"发送太频繁，请 {remaining} 秒后再试",
        )

    verify_token = create_access_token({"sub": str(current_user.id), "email": email, "purpose": "verify"})
    verify_url = f"{str(request.base_url).rstrip('/')}/app.html#/verify?token={verify_token}"
    ok = await send_verify_email(email, current_user.username, verify_url)
    if ok:
        _last_send[current_user.username] = now
        return {"ok": True, "message": "验证邮件已发送"}
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="邮件发送失败，请检查邮箱配置",
    )
