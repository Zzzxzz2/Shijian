"""UI Test Executor - Executes UI test cases using Playwright subprocess."""

import asyncio
import base64
import json
import os
import sys
import time
from typing import Any

from models import TestCase

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")
RUNNER_SCRIPT = os.path.join(os.path.dirname(__file__), "playwright_runner.py")


def _check_assertion(assertion: dict, current_url: str = "", elements: list = None) -> dict:
    """Check a single assertion rule for UI tests. Returns {passed, rule, actual, error}."""
    elements = elements or []
    a_type = assertion.get("type", "")
    target = assertion.get("target", "")
    operator = assertion.get("operator", "eq")
    expected = assertion.get("expected")

    actual = None
    error = None
    passed = False

    try:
        if a_type == "element_exists":
            actual = any(target.lower() in str(el).lower() for el in elements)
            expected = True
            operator = "eq"
        elif a_type == "text_contains":
            all_text = " ".join(str(el) for el in elements)
            actual = all_text
        elif a_type == "url_contains":
            actual = current_url
        else:
            error = f"Unknown UI assertion type: {a_type}"
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
        else:
            error = f"Unknown operator: {operator}"
            passed = False

    except Exception as e:
        error = str(e)
        passed = False

    return {"passed": passed, "rule": assertion, "actual": actual, "error": error}


async def execute_ui_case(case: TestCase, project_url: str, run_id: int = 0,
                          auth_headers: dict | None = None) -> dict:
    """Execute a UI test case via Playwright subprocess.

    ``auth_headers`` are injected from the project's auth config
    and forwarded to the Playwright runner as extra HTTP headers.
    """
    content = case.content or {}
    steps = content.get("steps", [])
    assertions = content.get("assertions", [])

    detail = {
        "steps": [],
        "assertions": [],
        "screenshots": [],
    }

    error_msg = None
    current_url = ""
    start = time.monotonic()

    # Prepare input for playwright_runner
    runner_input = {
        "steps": steps,
        "screenshots_dir": SCREENSHOT_DIR,
        "run_id": run_id,
        "case_id": case.id,
    }
    if auth_headers:
        runner_input["auth_headers"] = auth_headers

    try:
        # Encode input as base64 CLI arg to avoid Windows stdin pipe issues
        encoded_input = base64.b64encode(json.dumps(runner_input).encode()).decode()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, RUNNER_SCRIPT, encoded_input,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=120,  # 2 minute timeout for UI tests
        )

        if proc.returncode != 0:
            error_msg = f"Playwright runner failed: {stderr.decode()[:500]}"
            detail["error"] = error_msg
        else:
            raw_stdout = stdout.decode()
            if not raw_stdout.strip():
                err_text = stderr.decode()[:500]
                error_msg = f"Playwright runner returned empty output. stderr: {err_text}"
                detail["error"] = error_msg
            else:
                try:
                    result = json.loads(raw_stdout)
                except json.JSONDecodeError as e:
                    error_msg = f"Playwright runner invalid JSON: {e}. Raw: {raw_stdout[:300]}"
                    detail["error"] = error_msg
                else:
                    detail["steps"] = result.get("steps", [])
                    detail["screenshots"] = result.get("screenshots", [])
                    detail["trace_url"] = result.get("trace_url", "")
                    if detail["screenshots"]:
                        detail["screenshot_url"] = (
                            f"/api/screenshots/{run_id}/{result['case_key']}/{detail['screenshots'][0]}"
                        )
                    current_url = result.get("current_url", "")
                    page_text = result.get("page_text", "")

                    # Check if any step failed
                    for step in detail["steps"]:
                        if step.get("status") == "error":
                            error_msg = step.get("error", "Step failed")
                            break

    except asyncio.TimeoutError:
        error_msg = "UI test execution timed out (120s)"
        detail["error"] = error_msg
    except Exception as e:
        error_msg = str(e)
        detail["error"] = error_msg

    duration_ms = (time.monotonic() - start) * 1000

    # Check assertions
    page_elements = [page_text] if page_text else []
    for assertion in assertions:
        result = _check_assertion(assertion, current_url=current_url, elements=page_elements)
        detail["assertions"].append(result)

    if error_msg:
        case_status = "error"
    elif detail["assertions"] and not all(a["passed"] for a in detail["assertions"]):
        case_status = "fail"
    else:
        case_status = "pass"

    return {
        "case_id": case.id,
        "status": case_status,
        "detail": detail,
        "duration_ms": round(duration_ms, 2),
        "error": error_msg,
    }
