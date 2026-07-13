"""Report generation service: produces HTML test run reports."""

import json
from datetime import datetime, timezone

from sqlalchemy import select

from database import async_session
from models import TestCase, TestResult, TestRun, TestRunCases


def _escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


async def generate_run_report(run_id: int) -> str:
    """Generate a self-contained HTML report for a given TestRun.

    Returns the full HTML string (with inline CSS) ready to render or download.
    """
    async with async_session() as db:
        run = await db.get(TestRun, run_id)
        if not run:
            return "<html><body><h1>Run not found</h1></body></html>"

        # Fetch results
        rows = (
            (await db.execute(
                select(TestResult).where(TestResult.run_id == run_id)
                .order_by(TestResult.id)
            ))
            .scalars()
            .all()
        )

        # Fetch cases
        cases = {}
        link_rows = (
            (await db.execute(
                select(TestCase)
                .join(TestRunCases, TestRunCases.case_id == TestCase.id)
                .where(TestRunCases.run_id == run_id)
            ))
            .scalars()
            .all()
        )
        for c in link_rows:
            cases[c.id] = c

        # Parse summary
        try:
            summary = json.loads(run.summary or "{}")
        except Exception:
            summary = {}

        total = summary.get("total", len(rows))
        passed = summary.get("pass", 0)
        failed = summary.get("fail", 0)
        errors = summary.get("error", 0)

        started = run.started_at or datetime.now(timezone.utc)
        finished = run.finished_at or datetime.now(timezone.utc)
        duration_s = (finished - started).total_seconds() if run.started_at and run.finished_at else 0

    # ── Build HTML ──────────────────────────────────────────────────────
    result_rows = ""
    for r in rows:
        case = cases.get(r.case_id)
        case_name = _escape(case.name) if case else f"Case #{r.case_id}"
        status_label = r.status
        status_color = {
            "pass": "#16a34a",
            "fail": "#dc2626",
            "error": "#ca8a04",
        }.get(r.status, "#6b7280")

        detail = r.detail or {}
        assertions_html = ""
        for a in detail.get("assertions", []):
            rule = a.get("rule", {})
            passed_icon = "✓" if a.get("passed") else "✗"
            passed_color = "#16a34a" if a.get("passed") else "#dc2626"
            assertions_html += (
                f'<tr><td style="color:{passed_color};font-weight:bold;padding:2px 8px">{passed_icon}</td>'
                f'<td style="padding:2px 8px">{_escape(rule.get("type",""))}</td>'
                f'<td style="padding:2px 8px">{_escape(rule.get("target",""))}</td>'
                f'<td style="padding:2px 8px">{_escape(rule.get("operator",""))}</td>'
                f'<td style="padding:2px 8px">{_escape(str(rule.get("expected","")))}</td>'
                f"</tr>"
            )

        error_html = ""
        if detail.get("error"):
            error_html = f'<p style="color:#dc2626;margin:4px 0">Error: {_escape(detail["error"])}</p>'

        response_info = ""
        if detail.get("request_url"):
            response_info = (
                f'<p style="margin:4px 0;color:#374151">{_escape(detail.get("method",""))} '
                f'{_escape(detail["request_url"])}</p>'
                f'<p style="margin:4px 0;color:#374151">Status: {detail.get("status_code","-")}</p>'
            )

        duration_str = f"{r.duration_ms:.0f}ms" if r.duration_ms else "-"

        result_rows += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;margin-bottom:12px;overflow:hidden">
            <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#f9fafb">
                <div style="display:flex;align-items:center;gap:8px">
                    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{status_color}"></span>
                    <span style="font-weight:600;color:#111827">{case_name}</span>
                </div>
                <span style="color:#6b7280;font-size:0.85em">{duration_str}</span>
            </div>
            <div style="padding:12px 16px;font-size:0.9em">
                {error_html}
                {response_info}
                <table style="width:100%;border-collapse:collapse;margin-top:8px">
                    <thead><tr style="background:#f3f4f6">
                        <th style="padding:4px 8px;text-align:left">结果</th>
                        <th style="padding:4px 8px;text-align:left">类型</th>
                        <th style="padding:4px 8px;text-align:left">目标</th>
                        <th style="padding:4px 8px;text-align:left">操作符</th>
                        <th style="padding:4px 8px;text-align:left">期望值</th>
                    </tr></thead>
                    <tbody>{assertions_html}</tbody>
                </table>
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Test Run Report #{run_id}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; background: #f3f4f6; color: #111827; }}
  .container {{ max-width: 800px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  .meta {{ color: #6b7280; font-size: 0.9em; margin-bottom: 20px; }}
  .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
  .summary-card {{ background: white; border-radius: 8px; padding: 16px; border: 1px solid #e5e7eb; text-align: center; }}
  .summary-card .num {{ font-size: 1.8rem; font-weight: 700; }}
  .summary-card .label {{ font-size: 0.8em; color: #6b7280; margin-top: 4px; }}
  .pass {{ color: #16a34a; }} .fail {{ color: #dc2626; }} .error {{ color: #ca8a04; }} .total {{ color: #111827; }}
  .result-box {{ border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }}
  .result-header {{ display: flex; justify-content: space-between; padding: 12px 16px; background: #f9fafb; }}
</style>
</head>
<body>
<div class="container">
    <h1>Test Run Report #{run_id}</h1>
    <p class="meta">
        开始: {_escape(started.strftime("%Y-%m-%d %H:%M:%S"))} &nbsp;|&nbsp;
        结束: {_escape(finished.strftime("%Y-%m-%d %H:%M:%S"))} &nbsp;|&nbsp;
        耗时: {duration_s:.1f}s &nbsp;|&nbsp;
        结果: {"通过" if run.result == "pass" else "失败"}
    </p>

    <div class="summary">
        <div class="summary-card"><div class="num total">{total}</div><div class="label">总数</div></div>
        <div class="summary-card"><div class="num pass">{passed}</div><div class="label">通过</div></div>
        <div class="summary-card"><div class="num fail">{failed}</div><div class="label">失败</div></div>
        <div class="summary-card"><div class="num error">{errors}</div><div class="label">错误</div></div>
    </div>

    <h2 style="font-size:1.1rem;margin-bottom:12px">详细结果</h2>
    {result_rows}
</div>
</body>
</html>"""

    return html
