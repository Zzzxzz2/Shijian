"""通知服务 — 定时执行完后发送企业微信 / 飞书 Webhook。"""

import logging

import httpx

logger = logging.getLogger(__name__)


async def send_notification(schedule, run) -> None:
    """根据 schedule 关联项目的 ``notification_config`` 发送通知。

    Args:
        schedule: Schedule ORM 对象（需要 ``.name`` / ``.project_id``）。
        run:      TestRun  ORM 对象（需要 ``.result`` / ``.summary``）。
    """
    from database import async_session
    from models import Project

    async with async_session() as db:
        project = await db.get(Project, schedule.project_id)
        if not project:
            return
        config = project.notification_config or {}

    notify_type = config.get("type")
    webhook_url = config.get("webhook_url", "")

    if not notify_type or not webhook_url:
        return

    passed = 0
    failed = 0
    if run.summary:
        try:
            import json
            summary = json.loads(run.summary) if isinstance(run.summary, str) else run.summary
            passed = summary.get("pass", 0) or summary.get("passed", 0)
            failed = summary.get("fail", 0) + summary.get("error", 0)
        except (json.JSONDecodeError, TypeError):
            pass

    text = (
        f"试剑 — 定时执行完成\n"
        f"任务：定时调度 #{schedule.id}\n"
        f"结果：{run.result or 'unknown'}\n"
        f"通过：{passed}\n"
        f"失败：{failed}"
    )

    if notify_type == "feishu":
        await _send_feishu(webhook_url, text)
    elif notify_type == "wechat":
        await _send_wechat(webhook_url, text)
    else:
        logger.warning("Unknown notification type: %s", notify_type)


async def _send_feishu(webhook_url: str, text: str) -> None:
    """飞书机器人 — msg_type=text。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                webhook_url,
                json={"msg_type": "text", "content": {"text": text}},
            )
            logger.info("Feishu notify status=%s body=%s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("Feishu webhook call failed")


async def _send_wechat(webhook_url: str, text: str) -> None:
    """企业微信机器人 — msgtype=text。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                webhook_url,
                json={"msgtype": "text", "text": {"content": text}},
            )
            logger.info("WeChat notify status=%s body=%s", resp.status_code, resp.text[:200])
    except Exception:
        logger.exception("WeChat webhook call failed")
