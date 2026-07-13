"""Token usage statistics API."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import get_db
from models import Project, TokenUsageLog, User

router = APIRouter(prefix="/api/token-stats", tags=["token-stats"])


@router.get("")
async def get_token_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Return token usage statistics aggregated by date, provider, and project."""
    if current_user is None:
        return {"total_tokens": 0, "total_input": 0, "total_output": 0, "by_date": [], "by_provider": [], "by_project": []}
    base = select(TokenUsageLog).where(TokenUsageLog.user_id == current_user.id)

    # Totals
    total_q = select(
        func.coalesce(func.sum(TokenUsageLog.input_tokens), 0),
        func.coalesce(func.sum(TokenUsageLog.output_tokens), 0),
    ).where(TokenUsageLog.user_id == current_user.id)
    row = (await db.execute(total_q)).one()
    total_input = row[0]
    total_output = row[1]

    # By date
    by_date_q = (
        select(
            func.date(TokenUsageLog.created_at).label("date"),
            func.sum(TokenUsageLog.input_tokens).label("input_tokens"),
            func.sum(TokenUsageLog.output_tokens).label("output_tokens"),
        )
        .where(TokenUsageLog.user_id == current_user.id)
        .group_by(func.date(TokenUsageLog.created_at))
        .order_by(func.date(TokenUsageLog.created_at))
    )
    by_date = [
        {
            "date": str(r.date),
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
        }
        for r in (await db.execute(by_date_q)).all()
    ]

    # By provider
    by_provider_q = (
        select(
            TokenUsageLog.provider,
            func.sum(TokenUsageLog.input_tokens).label("input_tokens"),
            func.sum(TokenUsageLog.output_tokens).label("output_tokens"),
        )
        .where(TokenUsageLog.user_id == current_user.id)
        .group_by(TokenUsageLog.provider)
    )
    by_provider = [
        {
            "provider": r.provider,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
        }
        for r in (await db.execute(by_provider_q)).all()
    ]

    # By project
    by_project_q = (
        select(
            TokenUsageLog.project_id,
            Project.name.label("project_name"),
            func.sum(TokenUsageLog.input_tokens).label("input_tokens"),
            func.sum(TokenUsageLog.output_tokens).label("output_tokens"),
        )
        .join(Project, Project.id == TokenUsageLog.project_id, isouter=True)
        .where(TokenUsageLog.user_id == current_user.id)
        .group_by(TokenUsageLog.project_id, Project.name)
    )
    by_project = [
        {
            "project_id": r.project_id,
            "project_name": r.project_name or f"Project #{r.project_id}",
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
        }
        for r in (await db.execute(by_project_q)).all()
    ]

    return {
        "total_tokens": total_input + total_output,
        "total_input": total_input,
        "total_output": total_output,
        "by_date": by_date,
        "by_provider": by_provider,
        "by_project": by_project,
    }
