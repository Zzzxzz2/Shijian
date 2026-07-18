"""E2E 流程 3：上传文档 → Schema 解析 OpenAPI → 生成用例骨架。

覆盖 E2E-201 ~ E2E-203：
  - 上传 OpenAPI 规范文档
  - 验证解析成功
  - 验证基于 schema 生成的用例骨架

NOTE: All tests share ONE session-scoped user to avoid the backend's strict
registration rate limiter.
"""

import json
import tempfile
from pathlib import Path

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.e2e, pytest.mark.requires_backend]

MINIMAL_OPENAPI_JSON = {
    "openapi": "3.0.0",
    "info": {"title": "E2E Test API", "version": "1.0.0"},
    "paths": {
        "/api/users": {
            "get": {
                "summary": "List users",
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "summary": "Create user",
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/api/users/{id}": {
            "get": {
                "summary": "Get user by ID",
                "parameters": [{"name": "id", "in": "path", "required": True}],
                "responses": {"200": {"description": "OK"}},
            },
            "delete": {
                "summary": "Delete user",
                "parameters": [{"name": "id", "in": "path", "required": True}],
                "responses": {"204": {"description": "No Content"}},
            },
        },
        "/api/health": {
            "get": {
                "summary": "Health check",
                "responses": {"200": {"description": "OK"}},
            }
        },
    },
}


@pytest.fixture
def openapi_spec_file() -> Path:
    """Create a temporary OpenAPI JSON specification file."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(MINIMAL_OPENAPI_JSON, tmp, ensure_ascii=False, indent=2)
    tmp.close()
    yield Path(tmp.name)
    # Teardown
    Path(tmp.name).unlink(missing_ok=True)


def _login_ui(page, base_url, user):
    """Fill login form and submit."""
    page.goto(f"{base_url}/app.html#/login")
    page.wait_for_selector("#login-form", timeout=10000)
    page.locator("#login-username").fill(user["username"])
    page.locator("#login-password").fill(user["password"])
    page.locator("#login-btn").click()
    page.wait_for_load_state("networkidle")


class TestFlow3DocUpload:
    """文档上传 + OpenAPI schema 解析流程。"""

    def test_e2e_201_upload_page_loads(self, page, base_url, test_user, auth_token):
        """E2E-201: 上传文档页面正常渲染。

        NOTE: `#upload-doc-btn` opens the OS file dialog (not a DOM element),
        so we just verify the button exists in the docs tab.
        """
        # ── 前置：创建项目 ──
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)
        resp = cli.post(
            "/api/projects",
            json={"name": "E2E-201-Upload项目", "description": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code in (200, 201), f"create_project: {resp.text}"
        project_id = resp.json().get("id")

        # ── 登录 ──
        _login_ui(page, base_url, test_user)

        # ── 进入项目 → 切换到文档 tab ──
        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}")
        page.wait_for_load_state("networkidle")

        # 切换到文档 tab（data-tab="docs"）
        docs_tab = page.locator("button.tab-btn[data-tab='docs']")
        docs_tab.wait_for(state="visible", timeout=10000)
        docs_tab.click()

        # 验证文档 tab 正常渲染 + 上传按钮可见
        page.locator("#upload-doc-btn").wait_for(state="visible", timeout=10000)
        assert page.locator("#upload-doc-btn").is_visible(), "上传按钮不可见"
        assert page.locator("#doc-list").is_visible()

    def test_e2e_202_upload_openapi_json(self, page, base_url, test_user, auth_token, openapi_spec_file):
        """E2E-202: 上传 OpenAPI JSON 文件并验证解析。"""
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)

        # ── 前置：创建项目 ──
        resp = cli.post(
            "/api/projects",
            json={"name": "E2E-202-Schema项目", "description": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code in (200, 201), f"create_project: {resp.text}"
        project_id = resp.json().get("id")

        _login_ui(page, base_url, test_user)

        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}")
        page.wait_for_load_state("networkidle")

        # ── 通过正式 multipart 文档端点上传 ──
        with open(openapi_spec_file, "rb") as spec:
            upload_resp = cli.post(
                f"/api/projects/{project_id}/docs",
                files={"file": ("openapi.json", spec, "application/json")},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        assert upload_resp.status_code == 201, upload_resp.text

        # ── UI 验证 ──
        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}")
        page.wait_for_load_state("networkidle")

        docs_tab = page.locator("button.tab-btn[data-tab='docs']")
        docs_tab.wait_for(state="visible", timeout=10000)
        docs_tab.click()
        page.get_by_text("openapi.json").wait_for(state="visible", timeout=10000)

    def test_e2e_203_case_skeleton_from_schema(self, page, base_url, test_user, auth_token, openapi_spec_file):
        """E2E-203: 基于 Schema 生成用例骨架。"""
        import time
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)

        resp = cli.post(
            "/api/projects",
            json={"name": "E2E-203-Skeleton项目", "description": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code in (200, 201), f"create_project: {resp.text}"
        project_id = resp.json().get("id")

        _login_ui(page, base_url, test_user)

        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}")
        page.wait_for_load_state("networkidle")

        gen_resp = cli.post(
            f"/api/projects/{project_id}/schema/parse",
            json={"spec": json.dumps(MINIMAL_OPENAPI_JSON), "mode": "coverage"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert gen_resp.status_code == 200, gen_resp.text
        generated = gen_resp.json()
        assert len(generated["stubs"]) == 5
        assert generated["coverage_summary"]["total"] == 5
