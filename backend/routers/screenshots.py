"""Screenshot file serving for UI test results."""

import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth import authenticate_token, security_optional
from database import get_db
from models import TestRun
from routers.deps import require_project_access

router = APIRouter(prefix="/api/screenshots", tags=["screenshots"])

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")


@router.get("/{run_id}/{case_key}/{filename}")
async def get_screenshot(
    run_id: int,
    case_key: str,
    filename: str,
    token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_optional),
    db: AsyncSession = Depends(get_db),
):
    """Serve a screenshot or trace file for a specific test step.

    ``case_key`` is the case id (int, backward-compatible) or a uuid
    hex string for temporary cases where ``case.id == 0``.
    """
    raw_token = token or (credentials.credentials if credentials else "")
    user = await authenticate_token(raw_token, db) if raw_token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    run = await db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        await require_project_access(run.project_id, user, db, "viewer")
    except HTTPException:
        raise HTTPException(status_code=404, detail="File not found")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_key) or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", filename
    ) or filename in {".", ".."}:
        raise HTTPException(status_code=404, detail="File not found")

    run_dir = (Path(SCREENSHOT_DIR) / str(run_id)).resolve()
    file_path = (run_dir / case_key / filename).resolve()
    if run_dir not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "application/zip" if filename.endswith(".zip") else "image/png"
    return FileResponse(file_path, media_type=media_type)
