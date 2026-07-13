"""TestCase CRUD + batch operations."""

import json

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, get_optional_user
from database import db_retry, get_db
from models import Project, TestCase, User
from routers.deps import require_project_access
from schemas import (
    ImportRequest,
    ImportResponse,
    ImportResult,
    PaginatedResponse,
    TestCaseBatchCreate,
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)


VALID_TEST_TYPES = ("api", "ui", "perf", "schema")

router = APIRouter(prefix="/api/projects/{pid}/cases", tags=["test-cases"])


@router.get("")
async def list_cases(
    pid: int,
    test_type: str = "",
    tag: str = "",
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return {"items": [], "total": 0}
    await require_project_access(pid, current_user, db, "viewer")

    base = select(TestCase).where(TestCase.project_id == pid)
    if test_type:
        base = base.where(TestCase.test_type == test_type)
    if tag:
        base = base.where(TestCase.tags.cast(String).contains(tag))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    rows = (
        (await db.execute(base.order_by(TestCase.created_at.desc()).offset(offset).limit(limit)))
        .scalars()
        .all()
    )

    return {
        "items": [TestCaseResponse.model_validate(r).model_dump() for r in rows],
        "total": total,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_case(
    pid: int,
    data: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    if not data.name or not data.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name is required",
        )

    case = TestCase(
        project_id=pid,
        name=data.name,
        test_type=data.test_type,
        source=data.source,
        content=data.content,
        tags=data.tags,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return TestCaseResponse.model_validate(case)


@router.post("/batch", status_code=status.HTTP_201_CREATED)
@db_retry()
async def create_cases_batch(
    pid: int,
    data: TestCaseBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    models = [
        TestCase(
            project_id=pid,
            name=c.name,
            test_type=c.test_type,
            source=c.source,
            content=c.content,
            tags=c.tags,
        )
        for c in data.cases
    ]
    db.add_all(models)
    await db.commit()
    for m in models:
        await db.refresh(m)

    return {
        "items": [TestCaseResponse.model_validate(m).model_dump() for m in models],
        "total": len(models),
        "imported": len(models),
    }


@router.delete("/batch", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_cases_batch(
    pid: int,
    ids: list[int] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    result = await db.execute(
        select(TestCase).where(
            TestCase.project_id == pid, TestCase.id.in_(ids)
        )
    )
    cases = result.scalars().all()
    for c in cases:
        await db.delete(c)
    await db.commit()
    return None


@router.patch("/{case_id}")
@db_retry()
async def update_case(
    pid: int,
    case_id: int,
    data: TestCaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    case = await db.get(TestCase, case_id)
    if not case or case.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )

    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name cannot be empty",
            )
        case.name = data.name
    if data.test_type is not None:
        case.test_type = data.test_type
    if data.content is not None:
        case.content = data.content
    if data.tags is not None:
        case.tags = data.tags

    await db.commit()
    await db.refresh(case)
    return TestCaseResponse.model_validate(case)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_case(
    pid: int,
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    case = await db.get(TestCase, case_id)
    if not case or case.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )

    await db.delete(case)
    await db.commit()
    return None


# ── Import / Export ──────────────────────────────────────────────────────


@router.get("/export")
async def export_cases(
    pid: int,
    format: str = "json",
    test_type: str = "",
    tag: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return Response(content="{}", media_type="application/json")
    await require_project_access(pid, current_user, db, "viewer")

    # 获取项目名
    project = await db.get(Project, pid)
    project_name = project.name if project else f"project_{pid}"

    base = select(TestCase).where(TestCase.project_id == pid)
    if test_type:
        base = base.where(TestCase.test_type == test_type)
    if tag:
        base = base.where(TestCase.tags.cast(String).contains(tag))

    rows = (
        (await db.execute(base.order_by(TestCase.id)))
        .scalars()
        .all()
    )

    from datetime import datetime, timezone

    data = {
        "project": project_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "cases": [
            {
                "name": c.name,
                "test_type": c.test_type,
                "source": c.source,
                "content": c.content,
                "skip_auth": c.skip_auth,
                "tags": c.tags or [],
            }
            for c in rows
        ],
    }

    return Response(
        content=json.dumps(data, ensure_ascii=False, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="project_{pid}_cases.json"',
        },
    )


@router.post("/import", status_code=status.HTTP_201_CREATED)
@db_retry()
async def import_cases(
    pid: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    # 解析上传 JSON 文件
    raw = await file.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON file",
        )

    items = payload.get("cases", [])
    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='JSON must contain a "cases" array',
        )

    # 逐条验证 + 导入
    result = ImportResult()
    for idx, item in enumerate(items):
        name = item.get("name", "")
        test_type = str(item.get("test_type", "")).lower()

        # 验证
        error = None
        if not name or not name.strip():
            error = "name 为空"
        elif test_type not in VALID_TEST_TYPES:
            error = f"test_type 无效，允许: {', '.join(VALID_TEST_TYPES)}"
        elif "content" not in item:
            error = "缺少 content 字段"

        if error:
            result.failed += 1
            result.errors.append({"index": idx, "name": name, "error": error})
            continue

        # 入库
        try:
            case = TestCase(
                project_id=pid,
                name=name.strip(),
                test_type=test_type,
                source=item.get("source", "manual"),
                content=item["content"],
                skip_auth=item.get("skip_auth", False),
                tags=item.get("tags", []),
            )
            db.add(case)
            result.imported += 1
        except Exception as exc:
            result.failed += 1
            result.errors.append({"index": idx, "name": name, "error": str(exc)})

    await db.commit()
    return result


# ── Tags ─────────────────────────────────────────────────────────────────


@router.get("/tags")
async def list_tags(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    if current_user is None:
        return {"tags": []}
    await require_project_access(pid, current_user, db, "viewer")

    rows = (
        (await db.execute(
            select(TestCase.tags).where(TestCase.project_id == pid)
        ))
        .scalars()
        .all()
    )

    all_tags: set[str] = set()
    for tag_list in rows:
        if isinstance(tag_list, list):
            all_tags.update(tag_list)
        elif isinstance(tag_list, str) and tag_list:
            all_tags.add(tag_list)

    return {"tags": sorted(all_tags)}
