"""OpenAICompatibleProvider — works with any OpenAI-compatible API.

DeepSeek, OpenAI, GLM, Qwen, Gemini (OpenAI compat endpoint), etc.
"""

import json
import logging
import re

from openai import OpenAI

from .base import BaseAIProvider, GeneratePlanResult, TokenUsage
from .mock import MockProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseAIProvider):
    """Generic OpenAI-compatible provider.

    Works with any API that exposes ``/v1/chat/completions``.
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate_plan(self, requirement: str, context: str = "") -> GeneratePlanResult:
        system_prompt = (
            "你是一个测试用例生成专家。根据用户描述的需求，生成结构化的测试用例列表。\n\n"
            "返回格式：严格返回 JSON 对象，格式为 {\"cases\": [...]}，不要包含 markdown 代码块标记。\n"
            "每个用例格式：\n"
            '{"name":"用例名称","test_type":"api|ui|perf","content":{...}}\n\n'
            "content 字段结构：\n"
            "- API 类型：method, url, headers, body, assertions\n"
            "- UI 类型：url, steps, selectors, assertions\n"
            "- Perf 类型：url, method, concurrency, duration, ramp_up\n\n"
             "assertions 每项格式：\n"
             '{"type":"status_code|json_path|header|body_contains","target":"字段路径","operator":"eq|ne|gt|lt|contains|regex","expected":值}\n'
             "json_path 的 target 支持 `$[0].id`、`$.data.items[0].name` 和 `data.items.0.name` 三种风格。\n\n"
            "规则：\n"
            "1. 根据需求生成合理的测试场景，覆盖正常和异常情况\n"
            "2. 每个用例内容必须完整可用\n"
            "3. 对于需要认证的接口，不要手动写 Authorization 头，系统会自动注入。\n"
             "4. 如果某个用例不需要认证（如登录接口本身、公开接口），可在用例中设置 skip_auth=true。默认为 false。\n"
             "5. 只返回 JSON 对象，不要解释\n"
        )

        user_msg = f"需求：{requirement}"
        if context:
            user_msg += f"\n\n参考文档：\n{context}"

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            raw = resp.choices[0].message.content or "{}"
            # Strip markdown code fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")]
            raw = raw.strip()

            # Log raw response for debugging
            logger.info("AI raw response (first 500 chars): %s", raw[:500])

            # Smart extraction: find first [ or { to last ] or }
            match = re.search(r'[\[{].*[\]}]', raw, re.DOTALL)
            if match:
                raw = match.group()

            # Parse JSON with fallback to mock
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.error("JSON parse failed: %s, raw: %s", e, raw[:500])
                return MockProvider().generate_plan(requirement, context)

            # Handle both array and object format
            if isinstance(parsed, list):
                cases = parsed
            elif isinstance(parsed, dict) and "cases" in parsed:
                cases = parsed["cases"]
            else:
                cases = []

            usage = TokenUsage(
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            )
            return GeneratePlanResult(cases=cases, token_usage=usage)

        except Exception as e:
            logger.error("OpenAI-compatible API call failed: %s", e)
            raise
