"""Test executor: dispatches to type-specific handlers (API/UI/Perf)."""

import json
import os
import re
import time
import asyncio
import base64
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import Project, TestCase, TestResult, TestRun, TestRunCases
from routers.ws import broadcast
from services.auth_helper import _get_auth_token
from services.http_security import redact_headers
from services.mock.engine import registry
from services.ui_executor import execute_ui_case
from services.perf_executor import execute_perf_case


SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")


async def _commit_with_retry(db: AsyncSession, max_retries: int = 3) -> None:
    """Commit executor state with bounded retry for SQLite writer contention."""
    for attempt in range(max_retries):
        try:
            await db.commit()
            return
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.1 * (2 ** attempt))

# ── Failure classification constants ───────────────────────────────────────

FAILURE_CATEGORIES = {
    "assertion_failed":  "断言失败",
    "timeout":           "超时",
    "connection_error":  "连接错误",
    "unexpected_status": "状态码不符",
    "execution_error":   "配置错误",
    "internal_error":    "系统内部错误",
}

_REMEDIATION_HINTS: dict[str, str] = {
    "timeout": (
        "目标服务响应超时，请检查：1) 服务是否运行 2) 超时配置是否够用"
    ),
    "connection_error": (
        "无法连接到目标服务，请检查：1) URL 是否正确 2) 网络是否可达 3) SSL 证书是否有效"
    ),
    "execution_error": (
        "检查用例 content 字段是否完整（method/url/headers/body）"
    ),
    "internal_error": (
        "系统内部错误，请查看日志"
    ),
    "unexpected_status": (
        "检查请求参数是否正确，或确认目标服务状态"
    ),
    "assertion_failed": (
        "检查预期值与实际值的差异，确认被测接口返回值是否正确"
    ),
}


def _resolve_url(url: str, project_url: str) -> str:
    """Replace {{base_url}} with project.url and resolve relative paths."""
    if "{{base_url}}" in url:
        url = url.replace("{{base_url}}", (project_url or "").rstrip("/"))
    if not url.startswith("http"):
        base = (project_url or "").rstrip("/")
        if not base:
            base = "http://localhost:8002"
        url = base + (url if url.startswith("/") else "/" + url)
    return url


def _normalize_json_path(target: str) -> str:
    """Convert '$[0].id' or '$.data.items[0].name' to '0.id' or 'data.items.0.name'."""
    target = target.strip()
    if target.startswith("$"):
        target = target[1:]
        target = target.lstrip(".")
    target = re.sub(r"\[(\d+)\]", r".\1", target)
    return target


def _check_assertion(assertion: dict, status_code: int = 0, headers: dict = None, body: Any = None,
                     current_url: str = "", elements: list = None) -> dict:
    """Check a single assertion rule. Returns {passed, rule, actual, error}."""
    headers = headers or {}
    elements = elements or []
    a_type = assertion.get("type", "")
    target = assertion.get("target", "")
    operator = assertion.get("operator", "eq")
    expected = assertion.get("expected")

    actual = None
    error = None
    passed = False

    try:
        if a_type == "status_code":
            actual = status_code
        elif a_type == "json_path":
            parts = _normalize_json_path(target).split(".")
            obj = body
            for p in parts:
                if isinstance(obj, dict) and p in obj:
                    obj = obj[p]
                elif isinstance(obj, list) and p.isdigit():
                    obj = obj[int(p)]
                else:
                    obj = None
                    break
            actual = obj
        elif a_type == "header":
            actual = headers.get(target.lower(), headers.get(target))
        elif a_type == "body_contains":
            actual = str(body) if body else ""
        elif a_type == "regex":
            actual = str(body) if body else ""
        elif a_type == "element_exists":
            actual = any(target.lower() in str(el).lower() for el in elements)
            expected = True
            operator = "eq"
        elif a_type == "text_contains":
            all_text = " ".join(str(el) for el in elements)
            actual = all_text
        elif a_type == "url_contains":
            actual = current_url
        elif a_type == "schema_match":
            import jsonschema
            try:
                jsonschema.validate(instance=body, schema=target)
                actual = True
            except jsonschema.ValidationError as e:
                actual = e.message
            except Exception as e:
                error = f"Schema validation error: {e}"
        else:
            error = f"Unknown assertion type: {a_type}"
            return {"passed": False, "rule": assertion, "actual": None, "error": error}

        if operator in ("eq", "ne", "gt", "lt"):
            try:
                actual_num = float(actual) if actual is not None else None
                expected_num = float(expected)
                if operator == "eq":
                    passed = actual_num == expected_num
                elif operator == "ne":
                    passed = actual_num != expected_num
                elif operator == "gt":
                    passed = actual_num > expected_num
                elif operator == "lt":
                    passed = actual_num < expected_num
            except (TypeError, ValueError):
                if operator == "eq":
                    passed = str(actual) == str(expected)
                elif operator == "ne":
                    passed = str(actual) != str(expected)
                else:
                    passed = False
        elif operator == "contains":
            passed = str(expected) in str(actual)
        elif operator == "regex":
            passed = bool(re.search(str(expected), str(actual)))
        else:
            error = f"Unknown operator: {operator}"
            passed = False

    except Exception as e:
        error = str(e)
        passed = False

    return {"passed": passed, "rule": assertion, "actual": actual, "error": error}


# ══════════════════════════════════════════════════════════════════════════
#  Workflow helpers — template render + capture
# ══════════════════════════════════════════════════════════════════════════


def _render(template: str, context: dict) -> str:
    """替换 {{variable}} 为 context 中的值。未知变量保持原样。"""
    def replacer(m):
        var = m.group(1)
        return str(context.get(var, m.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def _render_value(val, context):
    """递归替换 dict/list/str 中的模板变量。"""
    if isinstance(val, str):
        return _render(val, context)
    elif isinstance(val, dict):
        return {k: _render_value(v, context) for k, v in val.items()}
    elif isinstance(val, list):
        return [_render_value(v, context) for v in val]
    return val


def _extract_json_path(obj, target: str):
    """从 JSON 对象中按点分路径提取值。复用 _normalize_json_path 逻辑。"""
    target = _normalize_json_path(target)
    parts = target.split(".")
    for p in parts:
        if isinstance(obj, dict) and p in obj:
            obj = obj[p]
        elif isinstance(obj, list) and p.isdigit():
            obj = obj[int(p)]
        else:
            return None
    return obj


async def _send_api_request(
    method: str,
    url: str,
    headers: dict[str, str] | None,
    body: Any,
    project_id: int = 0,
) -> httpx.Response:
    """Send one API request, optionally passing through the project's mock engine."""
    request = httpx.Request(
        method,
        url,
        headers=headers or None,
        json=body if body is not None else None,
    )
    engine = registry.get(project_id) if project_id else None
    config = await engine.refresh_config() if engine else None

    if config and config.enabled and config.mode == "replay":
        replayed = await engine.replay(request)
        if replayed is not None:
            return replayed

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.send(request)

    if config and config.enabled and config.mode == "record":
        await engine.record_request(
            method=request.method,
            path=request.url.path,
            query_string=request.url.query.decode("utf-8"),
            request_headers=dict(request.headers),
            request_body=request.content,
            response_status=response.status_code,
            response_headers=dict(response.headers),
            response_body=response.content,
        )
    return response


async def _execute_workflow(steps: list[dict], project_url: str, project_id: int = 0) -> dict:
    """执行多步骤 workflow。失败统一 break。"""
    context: dict[str, Any] = {}
    results: list[dict] = []
    overall_status = "pass"
    total_ms = 0.0

    for step in steps:
        step_start = time.monotonic()

        # 1. 替换模板变量
        url = _render(step["url"], context)
        headers = {k: _render(v, context) for k, v in step.get("headers", {}).items()}
        body = _render_value(step.get("body"), context)

        # 2. 执行步骤（30s 超时）
        try:
            resp = await _send_api_request(
                step["method"], url, headers, body, project_id
            )
            # resp.json() 安全包装
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = resp.text

            detail = {
                "status_code": resp.status_code,
                "response_headers": redact_headers(resp.headers),
                "response_body": resp_body,
            }
        except Exception as e:
            results.append({
                "name": step.get("name", ""),
                "status": "error",
                "error": str(e),
                "assertions": [],
                "duration_ms": round((time.monotonic() - step_start) * 1000, 2),
            })
            overall_status = "error"
            break  # 异常 → 跳过后续

        # 3. 检查断言
        step_result: dict[str, Any] = {
            "name": step.get("name", ""),
            "status": "pass",
            "assertions": [],
            "duration_ms": round((time.monotonic() - step_start) * 1000, 2),
        }
        for a in step.get("assertions", []):
            r = _check_assertion(a, resp.status_code, detail.get("response_headers", {}), resp_body)
            step_result["assertions"].append(r)
            if not r["passed"]:
                step_result["status"] = "fail"

        results.append(step_result)

        # 4. Capture 变量
        for cap in step.get("capture", []):
            val = _extract_json_path(resp_body, cap["json_path"])
            if val is not None:
                context[cap["variable"]] = val

        if step_result["status"] == "fail":
            overall_status = "fail"
            break  # 断言失败 → 跳过后续

        total_ms += step_result["duration_ms"]

    return {
        "status": overall_status,
        "detail": {"steps": results},
        "duration_ms": round(total_ms, 2),
    }


async def execute_api_case(
    case: TestCase,
    project_url: str,
    auth_headers: dict | None = None,
    project_id: int = 0,
) -> dict:
    """Execute an API test case via httpx.

    ``auth_headers`` are injected from the project's auth config.
    Case-level headers take priority over auth_headers.
    """
    content = case.content or {}

    # Workflow 模式
    if "workflow" in content:
        return await _execute_workflow(content["workflow"], project_url, project_id)

    method = content.get("method", "GET").upper()
    url = _resolve_url(content.get("url", ""), project_url)
    # Auth- injected headers first, then case headers override
    merged_headers = {**(auth_headers or {}), **(content.get("headers", {}))}
    headers = merged_headers
    body = content.get("body")
    assertions = content.get("assertions", [])

    detail = {
        "request_url": url,
        "method": method,
        "request_headers": redact_headers(headers),
        "request_body": body,
        "status_code": None,
        "response_headers": {},
        "response_body": None,
        "assertions": [],
    }

    status_code = 0
    error_msg = None
    start = time.monotonic()

    # Retrying mutating methods can duplicate side effects.
    MAX_RETRIES = 2 if method in {"GET", "HEAD", "OPTIONS"} else 1
    for attempt in range(MAX_RETRIES):
        try:
            resp = await _send_api_request(method, url, headers, body, project_id)
            status_code = resp.status_code
            detail["status_code"] = status_code
            detail["response_headers"] = redact_headers(resp.headers)
            try:
                detail["response_body"] = resp.json()
            except Exception:
                detail["response_body"] = resp.text
            break  # success — exit retry loop
        except httpx.TimeoutException as e:
            if attempt == MAX_RETRIES - 1:
                error_msg = str(e)
                detail["error"] = error_msg
                detail["failure_category"] = "timeout"
                detail["failure_message"] = str(e)
                detail["remediation_hint"] = _REMEDIATION_HINTS["timeout"]
            else:
                await asyncio.sleep(1 * (2 ** attempt))
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            if attempt == MAX_RETRIES - 1:
                error_msg = str(e)
                detail["error"] = error_msg
                detail["failure_category"] = "connection_error"
                detail["failure_message"] = str(e)
                detail["remediation_hint"] = _REMEDIATION_HINTS["connection_error"]
            else:
                await asyncio.sleep(1 * (2 ** attempt))
        except (KeyError, TypeError, ValueError) as e:
            error_msg = str(e)
            detail["error"] = error_msg
            detail["failure_category"] = "execution_error"
            detail["failure_message"] = f"测试配置错误：{e}"
            detail["remediation_hint"] = _REMEDIATION_HINTS["execution_error"]
            break
        except Exception as e:
            error_msg = str(e)
            detail["error"] = error_msg
            detail["failure_category"] = "internal_error"
            detail["failure_message"] = str(e)
            detail["remediation_hint"] = _REMEDIATION_HINTS["internal_error"]
            break

    duration_ms = (time.monotonic() - start) * 1000

    for assertion in assertions:
        result = _check_assertion(assertion, status_code, detail["response_headers"], detail["response_body"])
        detail["assertions"].append(result)

    if error_msg:
        case_status = "error"
    elif all(a["passed"] for a in detail["assertions"]):
        case_status = "pass"
    else:
        case_status = "fail"

    # ── Assertion-failed classification (no transport error already set) ──
    if case_status == "fail" and not detail.get("failure_category"):
        failed_status = any(
            not a["passed"] and a.get("rule", {}).get("type") == "status_code"
            for a in detail["assertions"]
        )
        detail["failure_category"] = "unexpected_status" if failed_status else "assertion_failed"
        first_fail = next((a for a in detail["assertions"] if not a["passed"]), None)
        if first_fail:
            rule = first_fail.get("rule", {})
            detail["failure_message"] = (
                f"断言失败：{rule.get('type', '?')} "
                f"{rule.get('operator', '?')} "
                f"{rule.get('expected', '?')}"
                f" ≠ {first_fail.get('actual', '?')}"
            )
        else:
            detail["failure_message"] = "断言失败"
        detail["remediation_hint"] = _REMEDIATION_HINTS[detail["failure_category"]]

    # ── Ensure default empty fields for backwards compat ──────────────
    detail.setdefault("failure_category", "")
    detail.setdefault("failure_message", "")
    detail.setdefault("remediation_hint", "")
    detail["duration_ms"] = round(duration_ms, 2)

    return {
        "case_id": case.id,
        "status": case_status,
        "detail": detail,
        "duration_ms": round(duration_ms, 2),
        "error": error_msg,
    }


async def execute_test_case(case: TestCase, project_url: str, run_id: int = 0,
                            auth_headers: dict | None = None, project_id: int = 0) -> dict:
    """Dispatcher: route to type-specific executor."""
    test_type = (case.test_type or "api").lower()
    if test_type == "api":
        return await execute_api_case(
            case, project_url, auth_headers=auth_headers, project_id=project_id
        )
    elif test_type == "ui":
        return await execute_ui_case(case, project_url, run_id, auth_headers=auth_headers)
    elif test_type == "perf":
        return await execute_perf_case(case, project_url)
    else:
        return {
            "case_id": case.id,
            "status": "error",
            "detail": {"error": f"Unknown test_type: {test_type}"},
            "duration_ms": 0,
            "error": f"Unknown test_type: {test_type}",
        }


async def _execute_run(run_id: int) -> dict:
    """Execute all cases in a TestRun. Updates DB with results."""
    async with async_session() as db:
        # Load run + project
        run = await db.get(TestRun, run_id)
        if not run:
            return {"error": "Run not found"}

        project = await db.get(Project, run.project_id)
        project_url = project.url if project else ""

        # Clean up old screenshots (>7 days)
        await cleanup_old_screenshots(db)

        # Update status to running
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await _commit_with_retry(db)

        # Load associated cases
        case_ids = (
            (await db.execute(
                select(TestRunCases.case_id).where(TestRunCases.run_id == run_id)
            ))
            .scalars()
            .all()
        )

        cases = (
            (await db.execute(
                select(TestCase).where(TestCase.id.in_(case_ids))
            ))
            .scalars()
            .all()
        )

        # ── Auth token injection ──────────────────────────────────────
        auth_headers = None
        try:
            token = await _get_auth_token(project.auth_config or {}, project.url or "")
            if token:
                auth = project.auth_config or {}
                header_name = auth.get("header_name", "Authorization")
                header_value = auth.get("header_format", "Bearer {token}").format(token=token)
                auth_headers = {header_name: header_value}
        except Exception:
            pass  # Auth failure shouldn't block the entire run

        results_summary = {"total": len(cases), "pass": 0, "fail": 0, "error": 0}

        # Execute each case
        for idx, case in enumerate(cases):
            # Check if run was cancelled mid-execution
            current_run = await db.get(TestRun, run_id)
            if current_run and current_run.status == "cancelled":
                break

            headers_for_case = auth_headers if not getattr(case, 'skip_auth', False) else None
            try:
                result = await execute_test_case(
                    case,
                    project_url,
                    run_id,
                    auth_headers=headers_for_case,
                    project_id=run.project_id,
                )
            except Exception as exc:
                result = {
                    "status": "error",
                    "detail": {"error": str(exc), "failure_category": "internal_error"},
                    "duration_ms": 0,
                    "error": str(exc),
                }

            # Save TestResult
            test_result = TestResult(
                run_id=run_id,
                case_id=case.id,
                status=result["status"],
                detail=result["detail"],
                duration_ms=result["duration_ms"],
            )
            db.add(test_result)

            results_summary[result["status"]] = results_summary.get(result["status"], 0) + 1

            # Broadcast case_done
            try:
                await broadcast(run_id, {
                    "type": "case_done",
                    "data": {
                        "case_id": case.id,
                        "case_name": case.name,
                        "status": result["status"],
                        "duration_ms": result["duration_ms"],
                        "detail": result["detail"],
                    },
                })
            except Exception:
                pass

            # Broadcast progress
            try:
                await broadcast(run_id, {
                    "type": "progress",
                    "data": {
                        "total": len(cases),
                        "done": idx + 1,
                        "passed": results_summary.get("pass", 0),
                        "failed": results_summary.get("fail", 0) + results_summary.get("error", 0),
                    },
                })
            except Exception:
                pass

        # Update run status
        run.finished_at = datetime.now(timezone.utc)
        run.status = "done"
        run.result = "pass" if results_summary.get("fail", 0) == 0 and results_summary.get("error", 0) == 0 else "fail"
        run.summary = json.dumps(results_summary)
        await _commit_with_retry(db)

        # Broadcast run_done
        try:
            await broadcast(run_id, {
                "type": "run_done",
                "data": {"status": run.status, "result": run.result},
            })
        except Exception:
            pass

        return results_summary


async def execute_run(run_id: int) -> dict:
    """Execute a run and guarantee that an unexpected run-level failure is finalized."""
    try:
        return await _execute_run(run_id)
    except Exception as exc:
        async with async_session() as db:
            run = await db.get(TestRun, run_id)
            if run is not None:
                run.status = "failed"
                run.result = "error"
                run.finished_at = datetime.now(timezone.utc)
                run.summary = json.dumps({"total": 0, "pass": 0, "fail": 0, "error": 1})
                await _commit_with_retry(db)
        return {"error": str(exc)}


async def cleanup_old_screenshots(db: AsyncSession) -> None:
    """Delete screenshot directories for runs finished more than 7 days ago."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        old_runs = (
            (await db.execute(
                select(TestRun.id).where(
                    TestRun.finished_at.isnot(None),
                    TestRun.finished_at < cutoff,
                )
            ))
            .scalars()
            .all()
        )

        for run_id in old_runs:
            run_dir = os.path.join(SCREENSHOT_DIR, str(run_id))
            if os.path.exists(run_dir):
                import shutil
                shutil.rmtree(run_dir, ignore_errors=True)
    except Exception:
        pass  # Cleanup failures shouldn't block execution
