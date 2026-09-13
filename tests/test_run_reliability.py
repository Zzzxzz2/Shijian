"""Failure injection and immutable history checks against the real DB layer."""
import asyncio
import json
import pytest
from sqlalchemy import select
from database import async_session
from models import TestCase, TestRun, TestRunCases, TestResult
from services import executor
from services.run_history import capture_snapshot, read_snapshot

pytestmark = pytest.mark.asyncio


async def make_run(db, project, timeout=300):
    cases = [TestCase(project_id=project.id, name=name, test_type="api", content={"url":"/original", "headers":{"Authorization":"private-test-token"}, "assertions":[{"type":"status_code", "expected":200}]}) for name in ("first-original", "second-original")]
    db.add_all(cases)
    await db.flush()
    run = TestRun(project_id=project.id, status="queued", timeout_seconds=timeout)
    db.add(run)
    await db.flush()
    for case in cases:
        db.add(TestRunCases(run_id=run.id, case_id=case.id))
    await capture_snapshot(db, run)
    await db.commit()
    return run, cases


async def test_snapshot_survives_edit_delete_and_redacts(async_client, auth_headers, test_project, db_session, monkeypatch):
    run, cases = await make_run(db_session, test_project)
    assert "private-test-token" not in run.snapshot_encrypted
    original_url = test_project.url
    cases[0].name = "edited-name"
    cases[0].content = {"url":"/edited"}
    test_project.url = "http://changed.invalid"
    await db_session.commit()
    seen = []
    async def execute(case, url, *args, **kwargs):
        seen.append((case.name, case.content['url'], url))
        return {"status":"pass", "detail":{"response_body":{"access_token":"response-secret"}}, "duration_ms":1}
    monkeypatch.setattr(executor, "execute_test_case", execute)
    await executor.execute_run(run.id)
    assert seen == [("first-original", "/original", original_url), ("second-original", "/original", original_url)]
    await db_session.delete(cases[0])
    await db_session.commit()
    response = await async_client.get(f"/api/runs/{run.id}", headers=auth_headers)
    data = response.json()
    assert data['cases'][0]['name'] == 'first-original'
    assert data['snapshot']['origin'] == 'created'
    assert 'private-test-token' not in response.text
    assert data['snapshot']['cases'][0]['content']['headers']['Authorization'] == '[REDACTED]'
    report = await async_client.get(f"/api/projects/{test_project.id}/runs/{run.id}/report", headers=auth_headers)
    assert 'first-original' in report.text and 'edited-name' not in report.text
    assert 'private-test-token' not in report.text and 'response-secret' not in report.text
    result = await async_client.get(f"/api/runs/{run.id}/results", headers=auth_headers)
    assert 'response-secret' not in result.text


@pytest.mark.parametrize('action', ['cancelled', 'timeout'])
async def test_partial_results_survive_stop(action, async_client, auth_headers, test_project, db_session, monkeypatch):
    run, cases = await make_run(db_session, test_project, timeout=1 if action == 'timeout' else 300)
    started = asyncio.Event()
    async def execute(case, *args, **kwargs):
        if case.id == cases[1].id:
            started.set()
            await asyncio.sleep(60)
        return {"status":"pass", "detail":{}, "duration_ms":1}
    monkeypatch.setattr(executor, 'execute_test_case', execute)
    worker = asyncio.create_task(executor.execute_run(run.id))
    await asyncio.wait_for(started.wait(), 5)
    async with async_session() as observer:
        rows = list((await observer.execute(select(TestResult).where(TestResult.run_id == run.id))).scalars())
        assert len(rows) == 1  # Durable before the entire run completes.
    if action == 'cancelled':
        url = f'/api/projects/{test_project.id}/runs/{run.id}/cancel'
        assert (await async_client.post(url)).status_code == 401
        assert (await async_client.post(url, headers=auth_headers)).json()['status'] == 'cancelled'
        assert (await async_client.post(url, headers=auth_headers)).json()['status'] == 'cancelled'
    await asyncio.wait_for(worker, 5)
    await executor.finish_run(run.id, 'failed', 'late worker')
    await db_session.refresh(run)
    assert run.status == action
    assert run.result == 'error' and run.termination_reason
    assert json.loads(run.summary) == {'total':2, 'pass':1, 'fail':0, 'error':0, 'skipped':1}


async def test_restart_recovery_does_not_replay(test_project, db_session, monkeypatch):
    run, cases = await make_run(db_session, test_project)
    run.status = 'running'
    db_session.add(TestResult(run_id=run.id, case_id=cases[0].id, status='pass', detail={}))
    await db_session.commit()
    async def forbidden(*args, **kwargs):
        pytest.fail('Recovery must not issue requests')
    monkeypatch.setattr(executor, 'execute_test_case', forbidden)
    await executor.recover_interrupted_runs()
    await executor.execute_run(run.id)
    await db_session.refresh(run)
    assert run.status == 'interrupted'
    assert json.loads(run.summary)['skipped'] == 1
    assert await executor.recover_interrupted_runs() == 0


async def test_cancel_pending_and_timeout_validation(async_client, auth_headers, test_project, db_session, monkeypatch):
    run, cases = await make_run(db_session, test_project)
    run.status = 'pending'
    await db_session.commit()
    root = f'/api/projects/{test_project.id}/runs'
    assert (await async_client.delete(f'{root}/{run.id}', headers=auth_headers)).status_code == 409
    for seconds in (0,3601):
        assert (await async_client.post(root, headers=auth_headers, json={'case_ids':[cases[0].id],'timeout_seconds':seconds})).status_code == 422
    assert (await async_client.post(f'/api/projects/999999/runs/{run.id}/cancel', headers=auth_headers)).status_code == 404
    await async_client.post(f'{root}/{run.id}/cancel', headers=auth_headers)
    await executor.execute_run(run.id)
    await db_session.refresh(run)
    assert run.status == 'cancelled' and json.loads(run.summary)['skipped'] == 2


async def test_creation_routes_capture_snapshot(async_client, auth_headers, test_project, db_session, monkeypatch):
    from routers import test_runs, suites, schedules
    def discard(coro, **kwargs):
        coro.close()
    for module in (test_runs, suites, schedules):
        monkeypatch.setattr(module, 'create_task', discard)
    case = TestCase(project_id=test_project.id, name='frozen', test_type='api', content={}, tags=['reliability'])
    db_session.add(case)
    await db_session.commit()
    root = f'/api/projects/{test_project.id}'
    manual = await async_client.post(root+'/runs', headers=auth_headers, json={'case_ids':[case.id]})
    tagged = await async_client.post(root+'/runs/by-tag', headers=auth_headers, json={'tag':'reliability'})
    suite = await async_client.post(root+'/suites', headers=auth_headers, json={'name':'reliable', 'case_ids':[case.id]})
    assert suite.status_code == 201, suite.text
    suite_run = await async_client.post(root+f"/suites/{suite.json()['id']}/run", headers=auth_headers)
    schedule = await async_client.post(root+'/schedules', headers=auth_headers, json={'case_ids':[case.id], 'cron_expr':'0 0 * * *', 'enabled':False})
    assert schedule.status_code == 201, schedule.text
    scheduled = await async_client.post(root+f"/schedules/{schedule.json()['id']}/trigger", headers=auth_headers)
    for response in (manual, tagged, suite_run, scheduled):
        assert response.status_code in (200,201), response.text
        rid = response.json().get('id') or response.json()['run_id']
        stored = await db_session.get(TestRun, rid)
        assert read_snapshot(stored)['cases'][0]['name'] == 'frozen'
