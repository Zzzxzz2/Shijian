"""Email sending utility via QQ SMTP (aiosmtplib)."""

import logging
import os
from email.message import EmailMessage

import aiosmtplib

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587

_alert_email: str | None = None
_auth_code: str | None = None


def _load_config():
    global _alert_email, _auth_code
    if _alert_email is not None:
        return
    _alert_email = os.getenv("QQ_ALERT_EMAIL", "")
    _auth_code = os.getenv("QQ_SMTP_AUTH_CODE", "")
    if not _alert_email or not _auth_code:
        logger.warning("QQ_ALERT_EMAIL or QQ_SMTP_AUTH_CODE not set — emails disabled")


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via QQ SMTP. Returns True on success."""
    _load_config()
    if not _alert_email or not _auth_code:
        logger.error("Email not sent: QQ mail not configured")
        return False

    msg = EmailMessage()
    msg["From"] = _alert_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    msg.set_type("text/plain")

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=_alert_email,
            password=_auth_code,
            start_tls=True,
        )
        logger.info("Email sent to %s", to)
        return True
    except Exception as exc:
        logger.exception("Failed to send email to %s: %s", to, exc)
        return False


async def send_verify_email(to: str, username: str, verify_url: str) -> bool:
    """Send an email verification link."""
    subject = "试剑 V2 — 邮箱验证"
    body = f"""您好 {username}，

感谢您注册试剑 V2。

请点击以下链接验证您的邮箱（链接 24 小时内有效）：

{verify_url}

如果您没有注册此账号，请忽略本邮件。
"""
    return await send_email(to, subject, body)
