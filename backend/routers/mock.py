"""Mock management API — CRUD, enable/disable, config."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import MockConfig, MockRecord, TestCase, User
from routers.deps import require_project_access
from schemas import (
    MockConfigResponse,
    MockConfigUpdate,
    MockConvertRequest,
    MockConvertResponse,
    MockPaginatedResponse,
    MockRecordResponse,
    MockRecordUpdate,
    MockToggleResponse,
)


_SENSITIVE_HEADERS = {"host", "cookie", "set-cookie", "authorization", "x-api-key", "x-forwarded-for", "content-length"}
from services.mock.engine import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{pid}/mocks", tags=["mock"])


# ══════════════════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════════════════


async def _get_record(record_id: int, pid: int, db: AsyncSession) -> MockRecord:
    """Fetch a single record owned by the given project, or raise 404."""
    record = await db.get(MockRecord, record_id)
    if record is None or record.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mock record not found",
        )
    return record


# ══════════════════════════════════════════════════════════════════════════
#  Mock Config
# ══════════════════════════════════════════════════════════════════════════


@router.get("/config")
async def get_mock_config(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockConfigResponse:
    """Get the project-level mock configuration."""
    await require_project_access(pid, current_user, db, "viewer")

    result = await db.execute(
        select(MockConfig).where(MockConfig.project_id == pid)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = MockConfig(project_id=pid)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return MockConfigResponse.model_validate(config)


@router.patch("/config")
async def update_mock_config(
    pid: int,
    data: MockConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockConfigResponse:
    """Update the project-level mock configuration."""
    await require_project_access(pid, current_user, db, "editor")

    result = await db.execute(
        select(MockConfig).where(MockConfig.project_id == pid)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = MockConfig(project_id=pid)
        db.add(config)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    await db.commit()
    await db.refresh(config)
    return MockConfigResponse.model_validate(config)


# ══════════════════════════════════════════════════════════════════════════
#  Mock Record CRUD
# ══════════════════════════════════════════════════════════════════════════


@router.get("")
async def list_mocks(
    pid: int,
    method: str = Query("", description="Filter by HTTP method"),
    path: str = Query("", description="Filter by path (partial match)"),
    enabled: bool | None = Query(None, description="Filter by enabled state"),
    source: str = Query("", description="Filter by source (auto/manual/import)"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockPaginatedResponse:
    """List mock records for a project, with optional filters."""
    await require_project_access(pid, current_user, db, "viewer")
    engine = registry.get(pid)
    if engine:
        await engine.flush_recordings()

    base = select(MockRecord).where(MockRecord.project_id == pid)

    if method:
        base = base.where(MockRecord.method == method.upper())
    if path:
        base = base.where(MockRecord.path.contains(path))
    if enabled is not None:
        base = base.where(MockRecord.enabled == enabled)
    if source:
        base = base.where(MockRecord.source == source)

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            base.order_by(MockRecord.recorded_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return MockPaginatedResponse(
        items=[MockRecordResponse.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/{record_id}")
async def get_mock(
    pid: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockRecordResponse:
    """Get a single mock record with full details."""
    await require_project_access(pid, current_user, db, "viewer")
    record = await _get_record(record_id, pid, db)
    return MockRecordResponse.model_validate(record)


@router.patch("/{record_id}")
@db_retry()
async def update_mock(
    pid: int,
    record_id: int,
    data: MockRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockRecordResponse:
    """Edit a mock record. Automatically sets source='manual'."""
    await require_project_access(pid, current_user, db, "editor")
    record = await _get_record(record_id, pid, db)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)
    record.source = "manual"

    await db.commit()
    await db.refresh(record)
    return MockRecordResponse.model_validate(record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_mock(
    pid: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a mock record."""
    await require_project_access(pid, current_user, db, "editor")
    record = await _get_record(record_id, pid, db)

    await db.delete(record)
    await db.commit()


@router.post("/{record_id}/toggle")
@db_retry()
async def toggle_mock(
    pid: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MockToggleResponse:
    """Flip the enabled flag on a mock record."""
    await require_project_access(pid, current_user, db, "editor")
    record = await _get_record(record_id, pid, db)

    record.enabled = not record.enabled
    await db.commit()
    return MockToggleResponse(enabled=record.enabled)


# ══════════════════════════════════════════════════════════════════════════
#  Recording lifecycle (via engine)
# ══════════════════════════════════════════════════════════════════════════


@router.post("/start-recording")
async def start_recording(
    pid: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Enable record mode for this project.

    Uses ``registry.get_or_create`` so subsequent calls (including
    ``stop-recording``) share the **same** MockEngine instance.
    """
    await require_project_access(pid, current_user, db, "editor")
    engine = registry.get_or_create(pid)
    await engine.start_recording()
    return {"status": "recording"}


@router.post("/stop-recording")
async def stop_recording(
    pid: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Disable record mode and flush pending records."""
    await require_project_access(pid, current_user, db, "editor")
    engine = registry.get_or_create(pid)
    await engine.stop_recording()
    return {"status": "stopped"}


# ══════════════════════════════════════════════════════════════════════════
#  Convert recordings → TestCases
# ══════════════════════════════════════════════════════════════════════════


@router.post("/convert", status_code=status.HTTP_201_CREATED)
@db_retry()
async def convert_recordings(
    pid: int,
    data: MockConvertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Convert selected MockRecords into TestCases.

    Each MockRecord becomes one TestCase (test_type="api", source="recorded")
    with a single status_code assertion matching the recorded response.
    Sensitive headers (host, cookie, authorization, etc.) are stripped.
    """
    await require_project_access(pid, current_user, db, "editor")

    result = MockConvertResponse()

    for mid in data.mock_ids:
        record = await db.get(MockRecord, mid)
        if not record or record.project_id != pid:
            # 单条缺失跳过，不阻塞其余
            continue

        # 构建 URL（path + query_string）
        url = record.path
        if record.query_string:
            url = f"{record.path}?{record.query_string}"

        # 过滤敏感头
        safe_headers = {
            k: v
            for k, v in (record.request_headers or {}).items()
            if k.lower() not in _SENSITIVE_HEADERS
        }

        # 构建 body
        raw_body = record.request_body or ""
        body: Any = raw_body
        if record.body_type == "json" and raw_body:
            try:
                import json
                body = json.loads(raw_body)
            except (json.JSONDecodeError, TypeError):
                body = raw_body

        # 构建断言
        assertions = [
            {
                "type": "status_code",
                "target": "status_code",
                "operator": "eq",
                "expected": record.response_status,
            },
        ]

        content = {
            "method": record.method.upper(),
            "url": url,
            "headers": safe_headers,
            "body": body,
            "assertions": assertions,
        }

        case = TestCase(
            project_id=pid,
            name=f"{record.method} {record.path} — 录制",
            test_type="api",
            source="recorded",
            content=content,
            tags=["recorded"],
        )
        db.add(case)
        await db.flush()

        result.imported += 1
        result.cases.append({
            "id": case.id,
            "name": case.name,
        })

    await db.commit()
    return result
