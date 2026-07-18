"""Regression checks for security boundaries fixed during portfolio hardening."""

import pytest

from models import ProjectMembers, TestCase, TestRun
from services.http_security import redact_headers


@pytest.mark.asyncio
async def test_old_token_rejected_after_force_logout(
    async_client, db_session, test_user, user_token
):
    test_user.token_version = 1
    await db_session.commit()

    response = await async_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_viewer_cannot_read_project_credentials(
    async_client, db_session, test_project, test_user2, auth2_headers
):
    test_project.auth_config = {"enabled": True, "token_value": "secret-token"}
    db_session.add(
        ProjectMembers(
            project_id=test_project.id, user_id=test_user2.id, role="viewer"
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/projects/{test_project.id}", headers=auth2_headers
    )
    assert response.status_code == 200
    assert response.json()["auth_config"] == {}


@pytest.mark.asyncio
async def test_suite_and_schedule_reject_cross_project_cases(
    async_client, db_session, test_project, test_project2, auth_headers
):
    foreign_case = TestCase(
        project_id=test_project2.id,
        name="foreign",
        test_type="api",
        content={"method": "GET", "url": "/"},
    )
    db_session.add(foreign_case)
    await db_session.commit()
    await db_session.refresh(foreign_case)

    suite = await async_client.post(
        f"/api/projects/{test_project.id}/suites",
        headers=auth_headers,
        json={"name": "invalid", "case_ids": [foreign_case.id]},
    )
    schedule = await async_client.post(
        f"/api/projects/{test_project.id}/schedules",
        headers=auth_headers,
        json={"cron_expr": "0 6 * * *", "case_ids": [foreign_case.id]},
    )
    assert suite.status_code == 400
    assert schedule.status_code == 400


@pytest.mark.asyncio
async def test_standalone_report_lookup_allows_project_viewer(
    async_client, db_session, test_project, test_user2, auth2_headers
):
    db_session.add(
        ProjectMembers(
            project_id=test_project.id, user_id=test_user2.id, role="viewer"
        )
    )
    run = TestRun(project_id=test_project.id, status="done", result="pass")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)

    response = await async_client.get(f"/api/runs/{run.id}", headers=auth2_headers)
    assert response.status_code == 200


def test_sensitive_headers_are_redacted():
    assert redact_headers(
        {"Authorization": "Bearer secret", "Cookie": "sid=secret", "Accept": "json"}
    ) == {
        "Authorization": "[REDACTED]",
        "Cookie": "[REDACTED]",
        "Accept": "json",
    }
