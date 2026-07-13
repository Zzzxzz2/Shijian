"""Contract 测试：响应 Schema 校验 — 19 个场景覆盖（验剑策略）。

策略文件：``.omo/tests/test-plan-contract-testing.md``
覆盖维度：
  正常路径  4 个（CONT-001 ~ CONT-004）
  边界值   8 个（CONT-101 ~ CONT-108）
  异常场景  4 个（CONT-201 ~ CONT-204）
  集成场景  3 个（CONT-301 ~ CONT-303）

核心函数：``services.executor._check_assertion``
- schema_match 使用 ``jsonschema.validate(instance=body, schema=target)``
- 匹配时 actual=True，不匹配时 actual=e.message，异常时 error 字段
- 比较规则：operator="eq" + expected=true → str(actual) == str(expected)
"""

import pytest
from services.executor import _check_assertion


def _sch(target: dict, expected: bool = True) -> dict:
    """Build a ``schema_match`` assertion dict."""
    return {"type": "schema_match", "target": target, "operator": "eq", "expected": expected}


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """CONT-001 ~ CONT-004：正常路径 4 个场景。"""

    def test_cont_001_basic_schema_match(self):
        """CONT-001：body 符合简单 schema → passed。"""
        result = _check_assertion(
            _sch({"type": "object", "properties": {"id": {"type": "integer"}}}),
            body={"id": 1},
        )
        assert result["passed"] is True
        assert result["actual"] is True
        assert result["error"] is None

    def test_cont_002_complex_nested_schema(self):
        """CONT-002：复杂嵌套 schema 匹配。"""
        target = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
        }
        result = _check_assertion(_sch(target), body={"user": {"name": "alice"}})
        assert result["passed"] is True
        assert result["actual"] is True

    def test_cont_003_required_fields(self):
        """CONT-003：schema 含 required 字段且 body 满足。"""
        target = {
            "type": "object",
            "required": ["id", "name"],
            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        }
        result = _check_assertion(_sch(target), body={"id": 1, "name": "test"})
        assert result["passed"] is True

    def test_cont_004_array_schema(self):
        """CONT-004：数组类型 schema 匹配。"""
        target = {"type": "array", "items": {"type": "integer"}}
        result = _check_assertion(_sch(target), body=[1, 2, 3])
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """CONT-101 ~ CONT-108：边界值 8 个场景。"""

    def test_cont_101_missing_required_field(self):
        """CONT-101：缺少 required 字段 → passed=false, actual 含错误。"""
        target = {
            "type": "object",
            "required": ["id", "name"],
            "properties": {"id": {"type": "integer"}},
        }
        result = _check_assertion(_sch(target), body={"id": 1})
        assert result["passed"] is False
        # actual 应为 ValidationError 消息，包含 required 提示
        assert isinstance(result["actual"], str)
        assert "name" in result["actual"].lower() or "required" in result["actual"].lower()

    def test_cont_102_field_type_mismatch(self):
        """CONT-102：字段类型不匹配 → passed=false。"""
        target = {"type": "object", "properties": {"id": {"type": "integer"}}}
        result = _check_assertion(_sch(target), body={"id": "abc"})
        assert result["passed"] is False
        assert isinstance(result["actual"], str)
        assert "integer" in result["actual"].lower() or "type" in result["actual"].lower()

    def test_cont_103_empty_body_with_required(self):
        """CONT-103：空 body {} 匹配含 required 的 schema → passed=false。"""
        target = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        result = _check_assertion(_sch(target), body={})
        assert result["passed"] is False

    def test_cont_104_body_is_null(self):
        """CONT-104：body 为 null → passed=false。"""
        target = {"type": "object"}
        result = _check_assertion(_sch(target), body=None)
        assert result["passed"] is False
        # jsonschema: None is not of type 'object'
        assert isinstance(result["actual"], str)

    def test_cont_105_body_is_empty_string(self):
        """CONT-105：body 为空字符串（尽管非标准 JSON）→ passed=false。

        body 传入空字符串时，实际已被 json.loads 转换为 str 类型，
        不是 object → schema_match 不通过。
        """
        target = {"type": "object"}
        result = _check_assertion(_sch(target), body="")
        assert result["passed"] is False

    def test_cont_106_empty_schema(self):
        """CONT-106：空 schema {} → 任意 body 通过。"""
        result = _check_assertion(_sch({}), body={"any": "data"})
        assert result["passed"] is True

    def test_cont_107_extra_fields_allowed_default(self):
        """CONT-107：body 含额外字段（additionalProperties 默认 true）→ passed。"""
        target = {"type": "object", "properties": {"id": {"type": "integer"}}}
        result = _check_assertion(_sch(target), body={"id": 1, "extra": "field"})
        assert result["passed"] is True

    def test_cont_108_extra_fields_disallowed(self):
        """CONT-108：body 含额外字段且 additionalProperties=false → passed=false。"""
        target = {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "additionalProperties": False,
        }
        result = _check_assertion(_sch(target), body={"id": 1, "extra": "field"})
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """CONT-201 ~ CONT-204：异常场景 4 个。"""

    def test_cont_201_invalid_schema(self):
        """CONT-201：无效 schema 定义（不存在的类型）→ error 非空。"""
        target = {"type": "nonexistent_type"}
        result = _check_assertion(_sch(target), body={})
        # jsonschema 对未知 type 会抛出 SchemaError 或 ValidationError
        assert result["passed"] is False
        # actual 含错误消息（异常被外层 except 捕获设到 error 或 actual）
        # 注意：jsonschema.validate 对无效 type 直接抛 SchemaError，
        # 被内层 except Exception 捕捉 → error 字段非空
        assert result["error"] is not None or isinstance(result["actual"], str)

    def test_cont_202_target_none_or_non_dict(self):
        """CONT-202：target 为 None 或非 dict → error 非空。"""
        for bad_target in (None, "string"):
            result = _check_assertion(
                {"type": "schema_match", "target": bad_target, "operator": "eq", "expected": True},
                body={},
            )
            assert result["passed"] is False
            # jsonschema.validate 校验 target 非 dict 会抛 SchemaError
            assert result["error"] is not None or isinstance(result["actual"], str)

    def test_cont_203_body_non_json_type(self):
        """CONT-203：body 为非 dict/non-JSON 类型（如 int）→ passed=false，不抛异常。"""
        target = {"type": "object"}
        # jsonschema.validate 对 body=42 抛出 ValidationError
        result = _check_assertion(_sch(target), body=42)
        assert result["passed"] is False
        assert result["error"] is None  # 不应有未捕获异常
        assert isinstance(result["actual"], str)  # 应为 ValidationError 消息

    def test_cont_204_string_schema_number_body(self):
        """CONT-204：schema 为 string 类型，body 为 number → passed=false。"""
        target = {"type": "string"}
        result = _check_assertion(_sch(target), body=42)
        assert result["passed"] is False
        assert isinstance(result["actual"], str)


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 集成场景（executor 完整断言管道）
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """CONT-301 ~ CONT-303：集成场景 3 个。"""

    def test_cont_301_api_case_with_schema_match(self):
        """CONT-301：API 用例含 schema_match 断言 → 结果中包含 assertion 结果。

        模拟 executor 管道：status_code 检查 + schema_match 断言。
        body 符合 schema → schema_match passed。
        """
        body = {"id": 1, "name": "alice"}

        # status_code 断言
        r1 = _check_assertion(
            {"type": "status_code", "target": "", "operator": "eq", "expected": 200},
            status_code=200,
        )
        assert r1["passed"] is True

        # schema_match 断言
        r2 = _check_assertion(
            _sch({"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}}),
            body=body,
        )
        assert r2["passed"] is True
        assert r2["actual"] is True

    def test_cont_302_mixed_assertions(self):
        """CONT-302：多条断言混合（status_code + json_path + schema_match）。

        各断言独立判断，互不影响，全部通过。
        """
        body = {"id": 1, "name": "test", "tags": ["a", "b"]}
        status_code = 200

        # 1. status_code
        r1 = _check_assertion(
            {"type": "status_code", "target": "", "operator": "eq", "expected": 200},
            status_code=status_code,
        )
        assert r1["passed"] is True

        # 2. json_path: $.id == 1
        r2 = _check_assertion(
            {"type": "json_path", "target": "$.id", "operator": "eq", "expected": 1},
            body=body,
        )
        assert r2["passed"] is True

        # 3. schema_match: body 为 object 且含 id/text
        r3 = _check_assertion(
            _sch({
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            }),
            body=body,
        )
        assert r3["passed"] is True
        assert r3["actual"] is True

    def test_cont_303_schema_match_fails_others_pass(self):
        """CONT-303：schema_match 断言失败不影响其他断言。

        schema_match 失败但 status_code + json_path 仍通过。
        """
        body = {"id": "abc", "name": "test"}  # id 应为 integer 而非 string

        # status_code — 正常
        r1 = _check_assertion(
            {"type": "status_code", "target": "", "operator": "eq", "expected": 200},
            status_code=200,
        )
        assert r1["passed"] is True

        # json_path — 取值正常
        r2 = _check_assertion(
            {"type": "json_path", "target": "$.name", "operator": "eq", "expected": "test"},
            body=body,
        )
        assert r2["passed"] is True

        # schema_match — 类型不匹配，失败
        r3 = _check_assertion(
            _sch({
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            }),
            body=body,
        )
        assert r3["passed"] is False
        assert isinstance(r3["actual"], str)

        # 验证其他断言未被污染
        r1b = _check_assertion(
            {"type": "status_code", "target": "", "operator": "eq", "expected": 200},
            status_code=200,
        )
        assert r1b["passed"] is True
