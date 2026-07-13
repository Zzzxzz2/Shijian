"""Security — attack vector generator.

POST /api/projects/{pid}/security/generate
  Accepts a base_url and optional category filter.
  Returns list of security test stubs with injected payloads.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import User
from routers.deps import require_project_access
from schemas import SchemaEndpointStub
from services.security_vectors import SECURITY_VECTORS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{pid}/security", tags=["security"])


class SecurityGenerateRequest(BaseModel):
    """Security test generation request."""

    base_url: str = ""
    categories: list[str] | None = None  # None → all categories


@router.post("/generate")
@db_retry()
async def generate_security_tests(
    pid: int,
    data: SecurityGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate security test stubs for a target base_url.

    Picks from ``SECURITY_VECTORS`` (optionally filtered by ``categories``)
    and returns one stub per (category × payload × method) combination
    for a handful of common HTTP methods.
    """
    await require_project_access(pid, current_user, db, "editor")

    categories = {k: v for k, v in SECURITY_VECTORS.items()
                  if data.categories is None or k in data.categories}
    if not categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未找到匹配的安全向量类别。可用: {list(SECURITY_VECTORS)}",
        )

    # Make sure base_url doesn't end with slash
    base_url = data.base_url.rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"  # fallback

    stubs: list[SchemaEndpointStub] = []
    _methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

    for cat_name, cat in categories.items():
        targets = cat.get("target", [])
        type_hint = cat.get("type_hint")
        payloads = cat["payloads"]

        for payload in payloads:
            # Pick a method that matches the injection target
            if "body" in targets:
                method = "POST"
            elif "header" in targets:
                method = "GET"
            else:
                method = "GET"

            content: dict[str, Any] = {
                "method": method,
                "url": base_url,
                "headers": {},
                "body": None,
                "assertions": [
                    {"type": "status_code", "target": "status_code", "operator": "ne", "expected": 500},
                ],
            }

            # Inject payload
            if isinstance(payload, dict) and "header" in targets:
                content["headers"].update(payload)
            elif isinstance(payload, dict):
                content["body"] = payload
            elif isinstance(payload, str):
                if "body" in targets:
                    content["body"] = payload
                else:
                    sep = "&" if "?" in base_url else "?"
                    content["url"] = f"{base_url}{sep}q={payload}"

            stub_name = f"[security] {cat_name} — {str(payload)[:50]}"
            stubs.append(SchemaEndpointStub(
                name=stub_name,
                test_type="api",
                source="security",
                content=content,
                coverage_key="",
            ))

    return {
        "total": len(stubs),
        "categories": list(categories),
        "stubs": stubs,
    }
