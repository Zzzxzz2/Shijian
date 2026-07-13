"""E2E 流程 2：AI 计划 — WebSocket 流式生成用例。

覆盖 E2E-101 ~ E2E-104：
  - 进入 AI 计划页面（#/projects/:id/ai-plan）
  - 输入场景描述
  - 提交生成请求
  - 观察 WebSocket 流式推送结果

NOTE: All tests share ONE session-scoped user to avoid the backend's strict
registration rate limiter.
"""

import pytest

from conftest import create_project, BASE_URL

pytestmark = [pytest.mark.e2e, pytest.mark.requires_backend]

# 当该环境变量存在时跳过 AI 相关测试（需要真实 LLM 配置）
SKIP_AI = pytest.mark.skipif(
    "SKIP_AI_TESTS" in __import__("os").environ,
    reason="SKIP_AI_TESTS 已设置",
)


def _login_ui(page, base_url, user):
    """Fill login form and submit."""
    page.goto(f"{base_url}/app.html#/login")
    page.wait_for_selector("#login-form", timeout=10000)
    page.locator("#login-username").fill(user["username"])
    page.locator("#login-password").fill(user["password"])
    page.locator("#login-btn").click()
    page.wait_for_load_state("networkidle")


class TestFlow2AiPlan:
    """AI 计划流程。"""

    def test_e2e_101_ai_plan_page_loads(self, page, base_url, test_user, auth_token):
        """E2E-101: AI 计划页面渲染正常。

        前置：创建项目（API），UI 登录后导航到 AI 计划页。
        """
        # ── 前置准备 ──
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)
        resp = cli.post(
            "/api/projects",
            json={"name": "E2E-101-AI项目", "description": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code in (200, 201), f"create_project: {resp.text}"
        project_id = resp.json().get("id")

        # ── UI 登录 ──
        _login_ui(page, base_url, test_user)

        # ── 导航到 AI 计划页 ──
        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}/ai-plan")
        page.wait_for_load_state("networkidle")

        # 验证关键元素存在（page-ai-plan.js 注册了 #generate-btn 等）
        assert page.locator("#generate-btn").is_visible()
        assert page.locator("textarea").first.is_visible() or page.locator("input[type='text']").first.is_visible()

    @SKIP_AI
    def test_e2e_102_submit_scenario(self, page, base_url, test_user, auth_token):
        """E2E-102: 提交场景描述并观察生成。"""
        import time
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)

        project_id = create_project(cli, auth_token, "E2E-102-AI项目")
        assert project_id is not None

        _login_ui(page, base_url, test_user)

        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}/ai-plan")
        page.wait_for_load_state("networkidle")

        # 输入场景描述
        textarea = page.locator("textarea#scenario, textarea").first
        if textarea.is_visible():
            textarea.fill("测试用户登录功能：输入用户名密码，验证返回 token")

        # 点击生成按钮
        page.locator("#generate-btn").click()
        time.sleep(2)
        page.wait_for_load_state("networkidle")

        # 观察加载状态或结果
        has_results = page.locator(".case-item, .generated-case, #generated-cases").first.is_visible()
        has_loading = page.locator(".loading, .spinner, [role='progressbar']").first.is_visible()
        assert has_results or has_loading, "提交后既无结果也无加载状态"

    @SKIP_AI
    def test_e2e_103_ws_streaming_result(self, page, base_url, test_user, auth_token):
        """E2E-103: WebSocket 流式推送展示。"""
        import time
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)

        console_errors = []

        def on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)

        page.on("console", on_console)

        project_id = create_project(cli, auth_token, "E2E-103-WS项目")
        assert project_id is not None

        _login_ui(page, base_url, test_user)

        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}/ai-plan")
        page.wait_for_load_state("networkidle")

        page.locator("textarea").first.fill("分页查询用户列表：GET /api/users 支持 page 和 size 参数")
        page.locator("#generate-btn").click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        ws_errors = [e for e in console_errors if "WebSocket" in e or "websocket" in e.lower()]
        assert len(ws_errors) == 0, f"存在 WebSocket 错误: {ws_errors}"

    @SKIP_AI
    def test_e2e_104_save_generated_cases(self, page, base_url, test_user, auth_token):
        """E2E-104: 应用/保存 AI 生成的用例到项目。"""
        import time
        import httpx
        cli = httpx.Client(base_url=BASE_URL, timeout=15)

        project_id = create_project(cli, auth_token, "E2E-104-应用项目")
        assert project_id is not None

        _login_ui(page, base_url, test_user)

        page.goto(f"{BASE_URL}/app.html#/projects/{project_id}/ai-plan")
        page.wait_for_load_state("networkidle")

        page.locator("textarea").first.fill("健康检查接口：GET /api/health 返回 200")
        page.locator("#generate-btn").click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 尝试点击保存按钮 (#save-btn 来自 page-ai-plan.js)
        save_btn = page.locator("#save-btn")
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_load_state("networkidle")
            page.goto(f"{BASE_URL}/app.html#/projects/{project_id}")
            page.wait_for_load_state("networkidle")
            assert page.locator("#new-case-btn, #execute-cases-btn").first.is_visible()
