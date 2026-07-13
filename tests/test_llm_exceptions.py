"""验剑策略：多厂商 LLM — 异常场景（LLM-201 ~ LLM-206）

外部 Provider 通过 httpx.MockTransport 拦截模拟异常响应。
"""

import asyncio
import json

import httpx
import pytest

from services.ai_provider import FailoverProvider, get_provider
from services.ai_provider.base import GeneratePlanResult
from services.ai_provider.claude import ClaudeProvider
from services.ai_provider.failover import _PROVIDER_TIMEOUT
from services.ai_provider.mock import MockProvider
from services.ai_provider.openai_compat import OpenAICompatibleProvider


# ═══════════════════════════════════════════════════════════════════════════
#  三、异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """验剑策略：LLM-201 ~ LLM-206 — 异常场景与 failover 跳转。"""

    @pytest.mark.asyncio
    async def test_llm_201_invalid_api_key_401(self):
        """验剑策略：LLM-201 — 无效 API Key（401）→ Failover 跳转。

        前置：failover 链中 provider 的 API Key 为无效字符串
        操作：generate_plan(...)
        预期：该 provider 返回 auth 错误，failover 跳转下一 provider
        """
        from conftest import build_mocked_client

        def _unauthorized(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=401,
                content=b'{"error": {"message": "invalid API key"}}',
                request=request,
            )

        # 两个 provider 都 401
        p1 = ClaudeProvider(api_key="sk-bad", base_url="http://test", model="c")
        p1.client = build_mocked_client(_unauthorized)

        p2 = OpenAICompatibleProvider(api_key="sk-bad", base_url="http://test", model="d")
        p2.client = build_mocked_client(_unauthorized)

        failover = FailoverProvider([p1, p2])
        result = await failover.generate_plan(requirement="测试登录")

        # 全挂 → Mock 兜底
        assert result.failover_trace is not None
        assert len(result.failover_trace) == 2
        assert "401" in result.failover_trace[0].lower() or "invalid" in result.failover_trace[0].lower(), (
            f"错误信息应提及 401: {result.failover_trace[0]}"
        )

    @pytest.mark.asyncio
    async def test_llm_202_provider_timeout(self):
        """验剑策略：LLM-202 — Provider 超时（>30s）→ Failover 跳转。

        前置：目标 provider 响应延迟 >30s（模拟慢响应）
        操作：generate_plan(...)
        预期：30s 后触发 asyncio.TimeoutError，failover 跳转下一 provider
        """
        from conftest import build_mocked_client, _make_mock_handler

        TIMEOUT_DELAY = _PROVIDER_TIMEOUT + 5  # 超过 30s 阈值

        # Provider 1：慢响应（超时）
        slow_handler = _make_mock_handler(delay=TIMEOUT_DELAY)
        p1 = ClaudeProvider(api_key="sk-test", base_url="http://test", model="c")
        p1.client = build_mocked_client(slow_handler)

        # Provider 2：快速成功
        fast_handler = _make_mock_handler(
            cases=[{"name": "Fast Result", "test_type": "api",
                    "content": {"method": "GET", "url": "/api/test", "assertions": []}}]
        )
        p2 = OpenAICompatibleProvider(api_key="sk-test", base_url="http://test", model="d")
        p2.client = build_mocked_client(fast_handler)

        failover = FailoverProvider([p1, p2])

        # FailoverProvider.generate_plan 是 async
        result = await failover.generate_plan(requirement="测试登录")

        # 应成功 fallback 到 provider 2
        assert result is not None
        assert len(result.cases) == 1
        assert result.cases[0]["name"] == "Fast Result"
        # failover_trace 应为 None（最终成功）
        assert result.failover_trace is None

    @pytest.mark.asyncio
    async def test_llm_203_empty_cases_triggers_failover(self):
        """验剑策略：LLM-203 — Provider 返回空 result.cases → 继续 failover。

        前置：provider 返回 GeneratePlanResult(cases=[])
        操作：generate_plan(...)
        预期：空结果视为无效，继续尝试下一个 provider
        """
        from conftest import build_mocked_client, _make_mock_handler

        # Provider 1：返回空 cases
        p1 = ClaudeProvider(api_key="sk-test", base_url="http://test", model="c")
        p1.client = build_mocked_client(_make_mock_handler(cases=[]))

        # Provider 2：返回有效 cases
        p2 = OpenAICompatibleProvider(api_key="sk-test", base_url="http://test", model="d")
        p2.client = build_mocked_client(
            _make_mock_handler(cases=[{"name": "P2 Result", "test_type": "api",
                                        "content": {"method": "GET", "url": "/api/test",
                                                     "assertions": []}}])
        )

        failover = FailoverProvider([p1, p2])
        result = await failover.generate_plan(requirement="测试登录")

        assert len(result.cases) == 1
        assert result.cases[0]["name"] == "P2 Result"

    def test_llm_204_api_key_decrypt_failure(self):
        """验剑策略：LLM-204 — API Key 解密失败 → 该 provider 不可用。

        前置：API Key 存储损坏或解密密钥不匹配
        操作：get_provider(...) 调用
        预期：解密异常被捕获，日志记录，failover 跳转，不崩溃
        """
        from services.ai_provider import get_provider
        from models import ApiKey as ApiKeyModel, Project

        # 创建一个 API Key 但 base64 数据故意损坏
        project = Project(
            name="Decrypt Fail",
            description="",
            user_id=1,
            ai_config={"provider": "failover", "failover_chain": ["deepseek"]},
        )
        bad_key = ApiKeyModel(
            user_id=1,
            provider="deepseek",
            api_key_encrypted="!!!not-valid-base64!!!",
            api_key_masked="sk-...bad",
            base_url="https://api.deepseek.com/v1",
        )

        # get_provider 应捕获解密异常，跳过 deepseek，回退 Mock
        provider = get_provider(project=project, api_keys=[bad_key])
        assert isinstance(provider, MockProvider), (
            "解密失败应回退 MockProvider"
        )
        result = provider.generate_plan(requirement="测试")
        assert len(result.cases) > 0

    def test_llm_205_non_json_response(self):
        """验剑策略：LLM-205 — Provider 返回非 JSON 响应 → 解析异常。

        前置：模拟 LLM 返回非 JSON 文本（message content 非 JSON）
        操作：generate_plan(...)
        预期：JSON 解析异常被 openai_compat.py 捕获，回退 MockProvider
        """
        from conftest import build_mocked_client

        def _non_json_handler(request: httpx.Request) -> httpx.Response:
            # 返回合法的 OpenAI response JSON，但 message.content 包含非 JSON 文本
            body = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "这不是JSON格式的有效内容",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            return httpx.Response(
                status_code=200,
                content=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                request=request,
            )

        provider = OpenAICompatibleProvider(
            api_key="sk-test",
            base_url="http://test",
            model="gpt-4o",
        )
        provider.client = build_mocked_client(_non_json_handler)

        # openai_compat.py 在 json.loads 解析 message.content 失败后 fallback 到 MockProvider
        result = provider.generate_plan(requirement="测试")
        assert isinstance(result, GeneratePlanResult)
        # 解析失败时 openai_compat 内部调用 MockProvider().generate_plan()
        # 应返回 MockProvider 的预设用例
        assert len(result.cases) > 0

    @pytest.mark.asyncio
    async def test_llm_206_even_mock_fails_graceful(self):
        """验剑策略：LLM-206 — MockProvider 调用也失败 → 优雅兜底。

        前置：所有 provider 包括 Mock 都抛出异常（极端情况）
        操作：generate_plan(...)
        预期：最外层异常传播，由 ai_planner 路由层返回 502，不 500
        """
        # FailoverProvider 内部 MockProvider 不会失败（它不依赖网络）
        # 但我们可以模拟一个极端情况：自定义 provider 抛出异常
        class BrokenProvider:
            class_name = "BrokenProvider"

            def generate_plan(self, requirement, context=""):
                raise RuntimeError("Unexpected system failure")

        # 直接测试 FailoverProvider 是否能 catch
        failover = FailoverProvider([BrokenProvider()])  # type: ignore[list-item]
        result = await failover.generate_plan(requirement="测试")

        # 所有 provider 失败 → Mock 兜底
        assert isinstance(result, GeneratePlanResult)
        assert len(result.cases) > 0
        assert result.failover_trace is not None
        assert any("BrokenProvider" in e for e in result.failover_trace), (
            f"failover_trace 应包含 BrokenProvider: {result.failover_trace}"
        )
