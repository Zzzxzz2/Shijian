"""Regression checks for project accuracy and the failure/retry loop."""
import pytest
from sqlalchemy import select
from models import TestCase, TestResult, TestRun, TestRunCases

pytestmark = pytest.mark.asyncio

async def test_project_counts_and_pagination(async_client, auth_headers, test_project, db_session):
    case = TestCase(project_id=test_project.id, name="Count", test_type="api", content={})
    db_session.add(case)
    await db_session.commit()
    response = await async_client.get("/api/projects", headers=auth_headers)
    item = next(x for x in response.json()["items"] if x["id"] == test_project.id)
    assert item["case_count"] == 1
    assert item["latest_run"] is None
    assert (await async_client.get("/api/projects?limit=-1", headers=auth_headers)).status_code == 422

async def test_error_regression_and_retry(async_client, auth_headers, test_project, db_session, monkeypatch):
    import routers.test_runs as routes
    def close_task(coro, **kwargs):
        coro.close()
    monkeypatch.setattr(routes, "create_task", close_task)
    case = TestCase(project_id=test_project.id, name="Retry", test_type="api", content={})
    db_session.add(case)
    await db_session.flush()
    for state in ("pass", "error"):
        run = TestRun(project_id=test_project.id, status="done", result=state)
        db_session.add(run)
        await db_session.flush()
        db_session.add(TestResult(run_id=run.id, case_id=case.id, status=state, detail={}))
    await db_session.commit()
    diff = (await async_client.get(f"/api/runs/{run.id}/diff", headers=auth_headers)).json()
    assert diff["summary"]["new_failures"] == 1
    url = f"/api/projects/{test_project.id}/runs"
    response = await async_client.post(f"{url}/{run.id}/retry-failed", headers=auth_headers)
    assert response.status_code == 201, response.text
    rid = response.json()["id"]
    ids = list((await db_session.execute(select(TestRunCases.case_id).where(TestRunCases.run_id == rid))).scalars())
    assert ids == [case.id]
    assert (await async_client.delete(f"{url}/{rid}", headers=auth_headers)).status_code == 409
    assert (await async_client.post(f"{url}/{run.id}/retry-failed")).status_code == 401
    response = await async_client.post(url, json={"case_ids": [case.id, case.id]}, headers=auth_headers)
    assert response.status_code == 201
    ids = list((await db_session.execute(select(TestRunCases.case_id).where(TestRunCases.run_id == response.json()["id"]))).scalars())
    assert ids == [case.id]

async def test_verification_token_is_not_login(async_client, test_user):
    from auth import create_access_token
    token = create_access_token({"sub": str(test_user.id), "purpose": "verify"})
    response = await async_client.get("/api/auth/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401

async def test_schema_counts_unique_endpoints(async_client, auth_headers, test_project):
    import json
    spec = {"openapi": "3.0.0", "info": {"title": "Check", "version": "1"}, "paths": {"/items": {"get": {"parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}], "responses": {"200": {"description": "OK"}}}}}}
    response = await async_client.post(f"/api/projects/{test_project.id}/schema/parse", headers=auth_headers, json={"spec": json.dumps(spec), "mode": "all"})
    assert response.status_code == 200, response.text
    summary = response.json()["coverage_summary"]
    assert summary == {"total": 1, "covered": 1, "uncovered": 0}

async def test_workflow_relative_url_and_failure_evidence(monkeypatch):
    import httpx
    from services.executor import _execute_workflow
    seen = []
    async def send(method, url, headers, body, project_id):
        seen.append(url)
        return httpx.Response(403, json={"detail": "Forbidden"})
    monkeypatch.setattr("services.executor._send_api_request", send)
    result = await _execute_workflow([{"name": "permission", "method": "DELETE", "url": "/items/1", "assertions": [{"type": "status_code", "expected": 204}]}], "http://localhost:8013")
    step = result["detail"]["steps"][0]
    assert seen == ["http://localhost:8013/items/1"]
    assert result["status"] == "fail"
    assert step["detail"]["status_code"] == 403
    assert step["assertions"][0]["actual"] == 403
    assert result["duration_ms"] == step["duration_ms"]

async def test_case_type_and_exact_tag_filters(async_client, auth_headers, test_project, db_session):
    db_session.add_all([TestCase(project_id=test_project.id, name="one", test_type="api", content={}, tags=["smoke"]), TestCase(project_id=test_project.id, name="two", test_type="API", content={}, tags=["smoke-extra"])])
    await db_session.commit()
    response = await async_client.get(f"/api/projects/{test_project.id}/cases?test_type=API&tag=smoke", headers=auth_headers)
    assert [x["name"] for x in response.json()["items"]] == ["one"]
    db_session.add(TestCase(project_id=test_project.id, name="literal", test_type="api", content={}, tags=["sm_ke"]))
    await db_session.commit()
    response = await async_client.get(f"/api/projects/{test_project.id}/cases?tag=sm_ke", headers=auth_headers)
    assert [x["name"] for x in response.json()["items"]] == ["literal"]

async def test_coverage_uses_catalog_and_survives_case_deletion(async_client, auth_headers, test_project, db_session):
    from sqlalchemy import delete
    test_project.schema_endpoints = [{"method": "GET", "path": "/one"}, {"method": "GET", "path": "/two"}]
    db_session.add_all([TestCase(project_id=test_project.id, name="one", test_type="api", content={"coverage_key": "GET /one"}), TestCase(project_id=test_project.id, name="one boundary", test_type="api", content={"coverage_key": "GET /one"})])
    await db_session.commit()
    url = f"/api/projects/{test_project.id}/coverage"
    data = (await async_client.get(url, headers=auth_headers)).json()
    assert (data["endpoints_total"], data["endpoints_covered"], data["endpoints_uncovered"]) == (2, 1, 1)
    await db_session.execute(delete(TestCase).where(TestCase.project_id == test_project.id))
    await db_session.commit()
    data = (await async_client.get(url, headers=auth_headers)).json()
    assert data["endpoints_uncovered"] == 2

async def test_negative_schema_respects_documented_status():
    from routers.schema_driver import _generate_assertions
    assert _generate_assertions("get", {"responses": {"401": {"description": "Unauthorized"}}})[0]["expected"] == 401
    assert _generate_assertions("get", {"responses": {"200": {}, "401": {}}})[0]["expected"] == 200

async def test_analytics_beacon_post(async_client):
    entry = await async_client.post('/api/analytics/enter', json={'path':'/review','session_id':'review-test'})
    assert entry.status_code == 201
    response = await async_client.post(f"/api/analytics/leave/{entry.json()['view_id']}", json={'duration_ms':1234})
    assert response.status_code == 200
    assert response.json()['ok'] is True
