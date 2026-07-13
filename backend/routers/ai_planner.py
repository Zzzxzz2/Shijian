"""AI Planner: generate test cases from requirement text + optional reference documents."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import ApiKey, Document, Project, TokenUsageLog, User
from routers.deps import require_project_access
from schemas import AIPlanRequest, AIPlanResponse, TokenUsageResponse
from services.ai_provider import get_provider

router = APIRouter(prefix="/api/projects/{pid}", tags=["ai-planner"])


@router.post("/ai-plan")
@db_retry()
async def generate_ai_plan(
    pid: int,
    data: AIPlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await require_project_access(pid, current_user, db, "editor")

    # Gather context from referenced documents
    context = ""
    if data.doc_ids:
        rows = (
            (await db.execute(
                select(Document).where(
                    Document.project_id == pid,
                    Document.id.in_(data.doc_ids),
                )
            ))
            .scalars()
            .all()
        )
        context = "\n\n".join(
            (d.content_text or "")[:3000] for d in rows if d.content_text
        )

    # Gather all API keys for this user
    key_rows = (
        (await db.execute(
            select(ApiKey).where(ApiKey.user_id == current_user.id)
        ))
        .scalars()
        .all()
    )

    # Build provider from project config + available keys
    provider = get_provider(project=project, api_keys=list(key_rows))

    try:
        result_or_coro = provider.generate_plan(requirement=data.requirement, context=context)
        # FailoverProvider's generate_plan is async; all others are sync
        result = await result_or_coro if asyncio.iscoroutine(result_or_coro) else result_or_coro
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI 生成失败：{e}",
        )

    # Derive model name for token logging (best effort)
    model_name = "mock"
    if hasattr(provider, "model") and provider.model:  # type: ignore[union-attr]
        model_name = provider.model  # type: ignore[union-attr]

    # Log token usage
    log = TokenUsageLog(
        user_id=current_user.id,
        project_id=pid,
        provider=type(provider).__name__,
        model=model_name,
        source="ai_plan",
        input_tokens=result.token_usage.input_tokens,
        output_tokens=result.token_usage.output_tokens,
    )
    db.add(log)
    await db.commit()

    return {
        "cases": result.cases,
        "token_usage": {
            "input_tokens": result.token_usage.input_tokens,
            "output_tokens": result.token_usage.output_tokens,
        },
        "failover_trace": result.failover_trace,
    }
