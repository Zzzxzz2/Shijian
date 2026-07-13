"""Screenshot file serving for UI test results."""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/screenshots", tags=["screenshots"])

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")


@router.get("/{run_id}/{case_key}/{filename}")
async def get_screenshot(run_id: int, case_key: str, filename: str):
    """Serve a screenshot or trace file for a specific test step.

    ``case_key`` is the case id (int, backward-compatible) or a uuid
    hex string for temporary cases where ``case.id == 0``.
    """
    file_path = os.path.join(SCREENSHOT_DIR, str(run_id), case_key, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "application/zip" if filename.endswith(".zip") else "image/png"
    return FileResponse(file_path, media_type=media_type)
