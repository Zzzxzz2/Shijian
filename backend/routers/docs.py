"""Document upload / list / delete."""

import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import Document, User
from routers.deps import require_project_access
from schemas import DocumentResponse
from services.doc_parser import extract_text

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

router = APIRouter(prefix="/api/projects/{pid}/docs", tags=["documents"])


@router.post("", status_code=status.HTTP_201_CREATED)
@db_retry()
async def upload_document(
    pid: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    # Determine doc_type from extension
    ext = os.path.splitext(file.filename or "unknown")[1].lower()
    doc_type = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "doc",
        ".md": "md",
        ".txt": "txt",
    }.get(ext, "other")

    # Save to disk
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = f"{pid}_{len(os.listdir(UPLOAD_DIR))}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        project_id=pid,
        filename=file.filename or safe_name,
        doc_type=doc_type,
        file_path=file_path,
    )

    # Synchronous text extraction (P3 requirement)
    content_text = extract_text(file_path, doc_type)
    doc.content_text = content_text

    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)


@router.get("")
async def list_documents(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "viewer")

    rows = (
        (await db.execute(
            select(Document).where(Document.project_id == pid)
            .order_by(Document.created_at.desc())
        ))
        .scalars()
        .all()
    )
    return [DocumentResponse.model_validate(r).model_dump() for r in rows]


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_retry()
async def delete_document(
    pid: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_project_access(pid, current_user, db, "editor")

    doc = await db.get(Document, doc_id)
    if not doc or doc.project_id != pid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    # Remove file from disk
    try:
        if os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass

    await db.delete(doc)
    await db.commit()
    return None
