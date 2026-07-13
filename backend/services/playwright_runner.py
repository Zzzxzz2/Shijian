"""
Playwright Runner - Subprocess script for UI test execution.

Receives step JSON via stdin, executes via Playwright, returns result JSON via stdout.
Usage: echo '{"steps": [...], "screenshots_dir": "...", "run_id": 1, "case_id": 1}' | python playwright_runner.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4


async def run_steps(steps: list, screenshots_dir: str, run_id: int, case_id: int,
                    auth_headers: dict | None = None) -> dict:
    """Execute UI steps using Playwright."""
    from playwright.async_api import async_playwright

    results = []
    current_url = ""
    screenshot_paths = []

    # ── Trace setup: uuid prevents overwrite when case.id == 0 ──────
    case_key = str(case_id) if case_id > 0 else uuid4().hex
    trace_dir = os.path.join(screenshots_dir, str(run_id), case_key)
    trace_path = os.path.join(trace_dir, "trace.zip")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        if auth_headers:
            await context.set_extra_http_headers(auth_headers)

        # ── Start trace recording (screenshots + DOM snapshots) ────
        await context.tracing.start(screenshots=True, snapshots=True)
        page = await context.new_page()

        try:
            for idx, step in enumerate(steps):
                action = step.get("action", "")
                target = step.get("target", "")
                value = step.get("value", "")
                screenshot_flag = step.get("screenshot", False)
                full_page = step.get("full_page", False)
                wait_after = step.get("wait_after", 0.5)

                step_result = {
                    "action": action,
                    "target": target,
                    "value": value,
                    "status": "pass",
                    "duration_ms": 0,
                    "screenshot": "",
                }
                step_start = time.monotonic()

                try:
                    if action == "navigate":
                        url = step.get("url") or value or target
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        current_url = page.url
                        await asyncio.sleep(wait_after)

                    elif action == "click":
                        if target.startswith("//") or target.startswith("("):
                            await page.locator(f"xpath={target}").click(timeout=10000)
                        elif target.startswith("#") or target.startswith(".") or "[" in target:
                            await page.locator(target).click(timeout=10000)
                        else:
                            await page.get_by_text(target, exact=False).first.click(timeout=10000)
                        await asyncio.sleep(wait_after)

                    elif action == "type":
                        if target:
                            if target.startswith("//") or target.startswith("("):
                                await page.locator(f"xpath={target}").fill(value, timeout=10000)
                            elif target.startswith("#") or target.startswith(".") or "[" in target:
                                await page.locator(target).fill(value, timeout=10000)
                            else:
                                await page.get_by_text(target, exact=False).first.fill(value, timeout=10000)
                        else:
                            await page.keyboard.type(value)
                        await asyncio.sleep(wait_after)

                    elif action == "keypress":
                        await page.keyboard.press(value)
                        await asyncio.sleep(wait_after)

                    elif action == "scroll":
                        direction = value or "down"
                        delta = 300 if direction == "down" else -300 if direction == "up" else 0
                        if direction in ("left", "right"):
                            delta_x = 300 if direction == "right" else -300
                            await page.mouse.wheel(delta_x, 0)
                        else:
                            await page.mouse.wheel(0, delta)
                        await asyncio.sleep(wait_after)

                    elif action == "screenshot":
                        pass  # Handled below

                    elif action == "wait":
                        await asyncio.sleep(float(value) if value else wait_after)

                    else:
                        step_result["status"] = "error"
                        step_result["error"] = f"Unknown action: {action}"

                except Exception as e:
                    step_result["status"] = "error"
                    step_result["error"] = str(e)

                # Take screenshot if requested
                if (screenshot_flag or action == "screenshot") and step_result["status"] != "error":
                    try:
                        dir_path = os.path.join(screenshots_dir, str(run_id), case_key)
                        os.makedirs(dir_path, exist_ok=True)
                        file_path = os.path.join(dir_path, f"{idx}.png")
                        await page.screenshot(path=file_path, full_page=full_page)
                        step_result["screenshot"] = os.path.basename(file_path)
                        screenshot_paths.append(os.path.basename(file_path))
                    except Exception as e:
                        step_result["screenshot_error"] = str(e)

                step_result["duration_ms"] = round((time.monotonic() - step_start) * 1000, 2)
                current_url = page.url
                results.append(step_result)

                if step_result["status"] == "error":
                    break

        finally:
            # ── Save trace (non-fatal — errors must not block result) ──
            try:
                os.makedirs(trace_dir, exist_ok=True)
                await context.tracing.stop(path=trace_path)
            except Exception:
                pass

            # Collect page text content for assertion checking
            page_text = ""
            try:
                page_text = await page.inner_text("body") if page else ""
            except Exception:
                pass

            await context.close()
            await browser.close()

    # Null path means trace was skipped entirely (never started)
    trace_available = os.path.exists(trace_path)

    return {
        "steps": results,
        "current_url": current_url,
        "screenshots": screenshot_paths,
        "page_text": page_text,
        "trace_url": f"{run_id}/{case_key}/trace.zip" if trace_available else "",
        "case_key": case_key,
    }


async def main():
    """Read steps from first CLI arg (base64 JSON), execute, write results to stdout."""
    if len(sys.argv) > 1:
        import base64
        raw_input = base64.b64decode(sys.argv[1]).decode()
    else:
        raw_input = sys.stdin.read()

    input_data = json.loads(raw_input)

    steps = input_data.get("steps", [])
    screenshots_dir = input_data.get("screenshots_dir", "screenshots")
    run_id = input_data.get("run_id", 0)
    case_id = input_data.get("case_id", 0)
    auth_headers = input_data.get("auth_headers")

    result = await run_steps(steps, screenshots_dir, run_id, case_id, auth_headers=auth_headers)
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
