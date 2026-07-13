"""验剑策略：多厂商 LLM — 权限/认证（LLM-301 ~ LLM-303）

通过 FastAPI 测试客户端验证路由层的认证和授权逻辑。
外部 Provider 通过 httpx.MockTransport 拦截。
"""

import json

import httpx
import pytest

from services.ai_provider.base import GeneratePlanResult, TokenUsage
from services.crypto import encrypt as _encrypt


# ═══════════════════════════════════════════════════════════════════════════
#  四、权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """验剑策略：LLM-301 ~ LLM-303 — 认证与授权。"""

    @pytest.mark.asyncio
    async def test_llm_301_no_token_returns_401(self, async_client: httpx.AsyncClient):
        """验剑策略：LLM-301 — 未认证用户访问 AI 生成接口 → 401。

        前置：无 JWT
        操作：调用 POST /api/projects/{pid}/ai-plan
        预期：返回 401
        """
        resp = await async_client.post(
            "/api/projects/1/ai-plan",
            json={"requirement": "测试登录功能"},
        )
        assert resp.status_code == 401, (
            f"未认证应返回 401，实际 {resp.status_code}: {resp.text[:200]}"
        )

    @pytest.mark.asyncio
    async def test_llm_302_non_member_returns_403(
        self,
        async_client: httpx.AsyncClient,
        test_project,
        auth2_headers: dict[str, str],
    ):
        """验剑策略：LLM-302 — 非项目成员调用 AI 生成 → 403。

        使用 require_project_access 判断，非项目成员返回 403。
        """
        # test_project 属于 test_user（user1）
        # auth2_headers 是 test_user2 的 token
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/ai-plan",
            json={"requirement": "测试登录功能"},
            headers=auth2_headers,
        )
        # V2 实现：非 Owner 访问项目返回 403
        assert resp.status_code == 403, (
            f"非 Owner 应返回 403，实际 {resp.status_code}: {resp.text[:200]}"
        )

    @pytest.mark.asyncio
    async def test_llm_303_no_key_for_provider(
        self,
        async_client: httpx.AsyncClient,
        db_session,
        test_user,
        test_project,
        auth_headers: dict[str, str],
    ):
        """验剑策略：LLM-303 — 项目 API Key 中无对应 provider 的 Key → 不可用/Mock 兜底。

        前置：项目无任何 API Key，配置 failover_chain=["claude"]
        操作：POST /api/projects/{pid}/ai-plan
        预期：get_provider 因无 Key 回退 MockProvider，返回 Mock 用例
        """
        # test_project 默认 ai_config={}，会走 "auto" → deepseek
        # 但 test_project 也没有 API Key（未创建）
        # 所以应回退 MockProvider

        resp = await async_client.post(
            f"/api/projects/{test_project.id}/ai-plan",
            json={"requirement": "测试登录功能"},
            headers=auth_headers,
        )

        # 应成功（MockProvider 兜底）
        assert resp.status_code == 200, (
            f"无 Key 时应返回 200（Mock 兜底），实际 {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "cases" in data, f"响应应包含 cases: {data}"
        assert len(data["cases"]) > 0, "Mock 兜底应返回预设用例"
        # 验证是 MockProvider 的典型用例
        case_names = [c["name"] for c in data["cases"]]
        assert "正常登录" in case_names, (
            f"MockProvider 预设用例应包含'正常登录': {case_names}"
        )
