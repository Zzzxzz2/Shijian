"""E2E 流程 1：注册 → 登录 → 创建项目 → 创建 API 用例 → 执行 → 查看结果。

覆盖 E2E-001 ~ E2E-007：
  - 注册新用户 (via session_user fixture)
  - 登录并跳转项目列表
  - 创建项目
  - 进入项目详情
  - 创建 API 测试用例
  - 查看执行结果

NOTE: All tests share ONE session-scoped user to avoid the backend's strict
registration rate limiter (global 3/day, per-IP 2/day, 10-min cooldown).
"""

import uuid

import pytest
from conftest import login_and_get_token, create_project, register_user, BASE_URL

pytestmark = [pytest.mark.e2e, pytest.mark.requires_backend]


def _wait_for_projects_page(page, timeout=15000):
    """Wait until the SPA navigates to the projects page.

    Uses DOM-element wait (reliable for SPA hash routing) instead of
    wait_for_url (which can miss hash-change 'navigation' events).
    """
    page.wait_for_selector("#new-project-btn", timeout=timeout)


def _login_ui(page, base_url, user):
    """Fill login form and submit — used by all tests that need UI auth."""
    page.goto(f"{base_url}/app.html#/login")
    page.wait_for_selector("#login-form", timeout=10000)
    page.locator("#login-username").fill(user["username"])
    page.locator("#login-password").fill(user["password"])
    page.locator("#login-btn").click()
    page.wait_for_load_state("networkidle")


class TestFlow1RegisterLogin:
    """登录流程（login.html 同一页面切换 tab）。"""

    def _switch_to_login(self, page):
        """切换到登录表单。"""
        page.locator("#goto-login").click()
        page.wait_for_selector("#login-form:not(.hidden)", timeout=5000)

    def test_e2e_001_register_page_loads(self, page, base_url):
        """E2E-001: 登录/注册页面正常渲染。"""
        page.goto(f"{base_url}/app.html#/login")

        # 等待页面通过 fetch 加载完毕后再验证 DOM
        page.wait_for_selector("#login-form", timeout=10000)
        page.wait_for_load_state("networkidle")

        # 登录表单可见
        assert page.locator("#login-username").is_visible()
        assert page.locator("#login-password").is_visible()
        assert page.locator("#login-btn").is_visible()

        # 切换到注册表单验证
        page.locator("#goto-register").click()
        page.wait_for_selector("#register-form:not(.hidden)", timeout=5000)
        assert page.locator("#reg-username").is_visible()
        assert page.locator("#reg-password").is_visible()
        assert page.locator("#reg-confirm").is_visible()
        assert page.locator("#register-btn").is_visible()

    def test_e2e_002_login(self, page, base_url, test_user):
        """E2E-002: 通过 UI 登录已有用户，跳转项目列表。

        NOTE: Registration is rate-limited, so we test the LOGIN flow
        with the pre-registered session user.
        """
        _login_ui(page, base_url, test_user)

        # 等待项目页加载
        _wait_for_projects_page(page)

        # 验证项目页内容
        assert page.locator("#new-project-btn").is_visible()


class TestFlow1Project:
    """项目创建 + 用例管理。"""

    def test_e2e_003_create_project(self, page, base_url, test_user, auth_token):
        """E2E-003: 创建项目（UI 完整流程）。"""
        _login_ui(page, base_url, test_user)

        # 点"新建项目"按钮
        page.locator("#new-project-btn").wait_for(timeout=8000)
        page.locator("#new-project-btn").click()

        # 等待 modal
        page.wait_for_selector("#new-project-modal:not(.hidden)", timeout=5000)

        project_name = f"E2E项目-{uuid.uuid4().hex[:8]}"
        page.locator("#np-name").fill(project_name)
        page.locator("#np-desc").fill("由 E2E 测试自动创建")
        page.locator("#np-confirm").click()

        # 等待项目列表刷新显示新项目
        page.get_by_text(project_name).first.wait_for(state="visible", timeout=10000)

    def test_e2e_004_create_api_case(self, page, base_url, test_user, auth_token):
        """E2E-004: 创建 API 测试用例（通过用例弹窗 #case-modal）。"""
        # Setup: create project via API
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)
        resp = cli.post(
            "/api/projects",
            json={"name": f"E2E-004-{test_user['username'][:8]}", "description": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code in (200, 201), f"create_project: {resp.text}"
        project_id = resp.json().get("id")

        # UI login → navigate to project detail
        _login_ui(page, base_url, test_user)
        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}")
        page.wait_for_load_state("networkidle")

        page.locator("#new-case-btn").wait_for(timeout=8000)
        page.locator("#new-case-btn").click()
        page.wait_for_selector("#case-modal:not(.hidden)", timeout=5000)

        # 填写弹窗中的用例名称
        page.locator("#cm-name").fill("测试登录接口")

        # 确认
        page.locator("#cm-confirm").click()
        page.wait_for_load_state("networkidle")

        # 验证用例在列表中
        assert page.locator("#case-list").is_visible()
        assert page.locator("text=测试登录接口").first.is_visible()


class TestFlow1Execute:
    """用例执行 + 结果查看。"""

    def test_e2e_005_execute_case(self, page, base_url, test_user, auth_token):
        """E2E-005: 从项目页选中并执行 API 用例。"""
        import httpx
        api = httpx.Client(base_url=BASE_URL, timeout=15)
        project = api.post(
            "/api/projects",
            json={"name": "E2E-005-exec", "url": BASE_URL},
            headers={"Authorization": f"Bearer {auth_token}"},
        ).json()
        case = api.post(
            f"/api/projects/{project['id']}/cases",
            json={
                "name": "E2E-005 健康检查",
                "test_type": "api",
                "content": {
                    "method": "GET",
                    "url": "/api/health",
                    "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
                },
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert case.status_code == 201, case.text

        _login_ui(page, base_url, test_user)
        page.goto(f"{BASE_URL}/app.html#/projects/{project['id']}")
        page.locator(".case-select").first.wait_for(state="visible", timeout=10000)
        page.locator(".case-select").first.check()
        page.locator("#execute-cases-btn").click()
        page.wait_for_url("**#/runs/*", timeout=15000)
        page.locator("#case-results").wait_for(state="visible", timeout=10000)

    def test_e2e_006_view_run_result(self, page, base_url, test_user, auth_token):
        """E2E-006: 查看执行结果页。"""
        import httpx
        api = httpx.Client(base_url=BASE_URL, timeout=15)

        # Setup via API
        resp = api.post(
            "/api/projects",
            json={"name": "E2E-006-proj", "description": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code in (200, 201), f"create_project: {resp.text}"
        project_id = resp.json().get("id")

        case_resp = api.post(
            f"/api/projects/{project_id}/cases",
            json={
                "name": "GET 健康检查",
                "test_type": "api",
                "content": {
                    "method": "GET",
                    "url": "/api/health",
                    "headers": {},
                    "body": None,
                    "assertions": [{"type": "status_code", "expected": 200}],
                },
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert case_resp.status_code in (200, 201), f"创建用例失败: {case_resp.text}"
        case_id = case_resp.json().get("id")

        run_resp = api.post(
            f"/api/projects/{project_id}/runs",
            json={"case_ids": [case_id]},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert run_resp.status_code in (200, 201), f"创建运行失败: {run_resp.text}"
        run_id = run_resp.json().get("id")

        # UI 登录 → 查看运行详情
        _login_ui(page, base_url, test_user)
        page.goto(f"{BASE_URL}/app.html#/runs/{run_id}")
        page.wait_for_load_state("networkidle")

        # 验证页面渲染
        assert page.locator("#case-results").is_visible() or page.locator("#report-btn").is_visible()

    def test_e2e_007_full_flow(self, page, base_url, test_user, screenshots_dir):
        """E2E-007: 完整端到端流程（UI only）。"""
        # UI 登录
        _login_ui(page, base_url, test_user)
        _wait_for_projects_page(page)

        # 创建项目
        page.locator("#new-project-btn").wait_for(timeout=8000)
        page.locator("#new-project-btn").click()
        page.wait_for_selector("#new-project-modal:not(.hidden)", timeout=5000)

        project_name = f"完整流程-{uuid.uuid4().hex[:8]}"
        page.locator("#np-name").fill(project_name)
        page.locator("#np-desc").fill("端到端自动测试")
        page.locator("#np-confirm").click()
        page.wait_for_load_state("networkidle")

        page.screenshot(path=str(screenshots_dir / "e2e-007-full-flow.png"))

        # 验证项目在列表中
        assert page.locator(f"text={project_name}").first.is_visible()
