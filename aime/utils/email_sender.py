"""SMTP email sender — used for daily cultivation reports."""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from aime.config import settings

logger = logging.getLogger("aime.email")


def _send_sync(to: str, subject: str, html: str, plain: str) -> bool:
    """Synchronous SMTP send. Called from a thread executor."""
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP 未配置，跳过邮件发送。")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        if settings.smtp_use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, context=ctx, timeout=30
            ) as server:
                server.login(settings.smtp_user, settings.smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=30
            ) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(settings.smtp_user, settings.smtp_pass)
                server.send_message(msg)
        logger.info(f"邮件已发送 → {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败 → {to}: {e}")
        return False


async def send_email(to: str, subject: str, html: str, plain: str = "") -> bool:
    """Async wrapper — runs SMTP in a thread to avoid blocking the event loop."""
    if not plain:
        # Strip basic HTML tags as plain-text fallback
        import re
        plain = re.sub(r"<[^>]+>", "", html).strip()

    return await asyncio.to_thread(_send_sync, to, subject, html, plain)
