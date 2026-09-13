"""Immutable run inputs; encrypted at rest, redacted when presented."""
import json
from datetime import datetime, timezone
from sqlalchemy import select
from models import Project, TestCase, TestRunCases
from schemas import TestCaseResponse
from services.crypto import encrypt, decrypt
from services.http_security import redact_data


async def capture_snapshot(db, run, origin="created"):
    if run.snapshot_encrypted:
        return read_snapshot(run)
    await db.flush()
    ids = list((await db.execute(select(TestRunCases.case_id).where(TestRunCases.run_id == run.id).order_by(TestRunCases.id))).scalars())
    cases = {c.id: c for c in (await db.execute(select(TestCase).where(TestCase.id.in_(ids), TestCase.project_id == run.project_id))).scalars()}
    if not ids or any(cid not in cases for cid in ids):
        raise ValueError("执行用例已删除或不属于该项目")
    project = await db.get(Project, run.project_id)
    snapshot = {"version": 1, "origin": origin, "captured_at": datetime.now(timezone.utc).isoformat(),
                "project": {"id": project.id, "name": project.name, "url": project.url, "auth_config": project.auth_config or {}},
                "cases": [TestCaseResponse.model_validate(cases[cid]).model_dump(mode="json") for cid in dict.fromkeys(ids)]}
    run.snapshot_encrypted = encrypt(json.dumps(snapshot, ensure_ascii=False))
    return snapshot


def read_snapshot(run):
    return json.loads(decrypt(run.snapshot_encrypted)) if run.snapshot_encrypted else None


def public_snapshot(run):
    snapshot = read_snapshot(run)
    return redact_data(snapshot) if snapshot else None
