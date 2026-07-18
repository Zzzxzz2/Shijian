"""Public analytics router: page view tracking (no auth required)."""

import os
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import aiosmtplib
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import JWT_ALGORITHM, JWT_SECRET
from database import db_retry, get_db
from models import PageView
from schemas import AnalyticsSummary, PageViewEnter, PageViewOut, PageViewUpdate

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_last_email_sent: dict[str, datetime] = {}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def _resolve_user(request: Request) -> int | None:
    """Try to resolve user_id from the auth cookie or Authorization header."""
    session = request.cookies.get("analytics_session")
    if session:
        try:
            payload = jwt.decode(session, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            uid_str = payload.get("sub")
            if uid_str:
                return int(uid_str)
        except (JWTError, ValueError, TypeError):
            pass

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if not payload.get("guest"):
                uid_str = payload.get("sub")
                if uid_str:
                    return int(uid_str)
        except (JWTError, ValueError, TypeError):
            pass
    return None


def _check_session(request: Request):
    cookie = request.cookies.get("analytics_session")
    if not cookie:
        raise HTTPException(status_code=401)
    try:
        p = jwt.decode(cookie, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if p.get("purpose") != "analytics_session":
            raise ValueError
    except Exception:
        raise HTTPException(status_code=401)


# ══════════════════════════════════════════════════════════════════════════
#  POST /enter — page entry (public)
# ══════════════════════════════════════════════════════════════════════════


@router.post("/enter", status_code=status.HTTP_201_CREATED)
@db_retry()
async def page_enter(data: PageViewEnter, request: Request, db: AsyncSession = Depends(get_db)):
    pid = data.session_id or ""
    if not pid:
        pid = _get_client_ip(request)

    view = PageView(
        path=data.path,
        referrer=data.referrer,
        ip_address=_get_client_ip(request),
        user_agent=data.user_agent[:500] if data.user_agent else "",
        session_id=pid,
        user_id=_resolve_user(request),
    )
    db.add(view)
    await db.commit()
    await db.refresh(view)
    return {"view_id": view.id}


# ══════════════════════════════════════════════════════════════════════════
#  PUT /leave — page leave (update duration + left_at)
# ══════════════════════════════════════════════════════════════════════════


@router.put("/leave/{view_id}")
@db_retry()
async def page_leave(view_id: int, data: PageViewUpdate, db: AsyncSession = Depends(get_db)):
    view = await db.get(PageView, view_id)
    if not view:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="View not found")
    view.duration_ms = data.duration_ms
    view.left_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
#  GET /summary — aggregated stats (session-protected)
# ══════════════════════════════════════════════════════════════════════════


@router.get("/summary")
async def analytics_summary(request: Request, db: AsyncSession = Depends(get_db)):
    _check_session(request)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total = (await db.execute(select(func.count()).select_from(PageView))).scalar() or 0

    ip_rows = await db.execute(select(PageView.ip_address).distinct())
    unique_ips = len([r for r in ip_rows.scalars().all() if r])

    today_count = (
        await db.execute(
            select(func.count()).where(PageView.entered_at >= today_start)
        )
    ).scalar() or 0

    top_rows = await db.execute(
        select(PageView.path, func.count().label("cnt"))
        .group_by(PageView.path)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_pages = [{"path": r[0], "count": r[1]} for r in top_rows.fetchall()]

    recent_rows = await db.execute(
        select(PageView).order_by(PageView.entered_at.desc()).limit(50)
    )
    recent = [PageViewOut.model_validate(r) for r in recent_rows.scalars().all()]

    daily_counts: list[int] = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        cnt = (
            await db.execute(
                select(func.count()).where(
                    PageView.entered_at >= day_start,
                    PageView.entered_at < day_end,
                )
            )
        ).scalar() or 0
        daily_counts.append(cnt)

    return AnalyticsSummary(
        total_views=total,
        unique_visitors=unique_ips,
        top_pages=top_pages,
        recent_views=recent,
        views_today=today_count,
        views_7d=daily_counts,
    )


# ══════════════════════════════════════════════════════════════════════════
#  POST /send-link — send verification email (rate-limited: 5 min)
# ══════════════════════════════════════════════════════════════════════════


@router.post("/send-link")
async def send_verify_link(request: Request):
    target = os.getenv("QQ_ALERT_EMAIL", "")
    if not target:
        raise HTTPException(status_code=500, detail="通知邮箱未配置")

    now = datetime.now(timezone.utc)

    # Rate limit: max 1 per 5 minutes per target
    if target in _last_email_sent and now - _last_email_sent[target] < timedelta(minutes=5):
        return JSONResponse(status_code=429, content={"detail": "请稍后再试"})

    # Record attempt time so rate limit applies even if SMTP fails
    _last_email_sent[target] = now

    token = jwt.encode(
        {"sub": target, "purpose": "analytics_verify",
         "exp": now + timedelta(minutes=10)},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )

    base_url = os.getenv("BASE_URL", "http://localhost:8002")
    verify_url = f"{base_url}/api/analytics/verify?token={token}"

    body = f"有人请求查看试剑 V3 浏览统计。\n\n如本人操作，点击：\n{verify_url}\n\n（10 分钟有效）\n非本人请忽略。"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "试剑 V3 — 浏览统计验证"
    msg["From"] = os.getenv("QQ_SMTP_USER", "")
    msg["To"] = target

    try:
        await aiosmtplib.send(
            msg,
            hostname=os.getenv("QQ_SMTP_HOST", "smtp.qq.com"),
            port=int(os.getenv("QQ_SMTP_PORT", "587")),
            username=os.getenv("QQ_SMTP_USER", ""),
            password=os.getenv("QQ_SMTP_AUTH_CODE", ""),
            start_tls=True,
        )
        _last_email_sent[target] = now
        return {"ok": True, "message": "验证邮件已发送"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"邮件发送失败: {e}")


@router.get("/verify")
async def verify_analytics(token: str = Query(...)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("purpose") != "analytics_verify":
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="无效或已过期的链接")

    session_token = jwt.encode(
        {"sub": "analytics_viewer", "purpose": "analytics_session",
         "exp": datetime.now(timezone.utc) + timedelta(hours=24)},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )
    resp = RedirectResponse(url="/app.html#/analytics", status_code=302)
    resp.set_cookie("analytics_session", session_token, httponly=True, max_age=86400, samesite="lax")
    return resp


# ── 统计查询（需 analytics_session cookie）───────────────────────────


@router.get("/stats")
async def get_stats(request: Request, db: AsyncSession = Depends(get_db)):
    _check_session(request)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_pv = (await db.execute(select(func.count()).select_from(PageView))).scalar() or 0
    total_uv = (await db.execute(
        select(func.count(func.distinct(PageView.session_id))).select_from(PageView)
    )).scalar() or 0
    total_ips = (await db.execute(
        select(func.count(func.distinct(PageView.ip_address))).select_from(PageView)
    )).scalar() or 0
    today_pv = (await db.execute(
        select(func.count()).select_from(PageView).where(PageView.entered_at >= today)
    )).scalar() or 0
    today_uv = (await db.execute(
        select(func.count(func.distinct(PageView.session_id))).select_from(PageView)
        .where(PageView.entered_at >= today)
    )).scalar() or 0
    avg_dur = (await db.execute(
        select(func.avg(PageView.duration_ms)).select_from(PageView)
        .where(PageView.duration_ms.isnot(None))
    )).scalar() or 0

    paths = (await db.execute(
        select(PageView.path, func.count()).select_from(PageView)
        .group_by(PageView.path).order_by(func.count().desc()).limit(10)
    )).all()

    hours = (await db.execute(
        select(func.extract("hour", PageView.entered_at).label("h"), func.count())
        .select_from(PageView).where(PageView.entered_at >= today)
        .group_by("h").order_by("h")
    )).all()

    return {
        "total_pv": total_pv, "total_uv": total_uv, "total_ips": total_ips,
        "today_pv": today_pv, "today_uv": today_uv,
        "avg_duration_ms": round(avg_dur, 1),
        "top_paths": [{"path": r[0], "count": r[1]} for r in paths],
        "hourly_today": [{"hour": int(r[0]), "count": r[1]} for r in hours],
    }


@router.get("/raw")
async def get_raw(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    _check_session(request)
    offset = (page - 1) * limit
    total = (await db.execute(select(func.count()).select_from(PageView))).scalar() or 0
    rows = (await db.execute(
        select(PageView).order_by(PageView.entered_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return {
        "items": [{
            "id": r.id, "path": r.path, "ip": r.ip_address,
            "session_id": r.session_id,
            "enter_time": r.entered_at.isoformat() if r.entered_at else None,
            "leave_time": r.left_at.isoformat() if r.left_at else None,
            "duration_ms": r.duration_ms,
        } for r in rows],
        "total": total, "page": page,
    }
