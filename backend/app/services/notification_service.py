"""
app/services/notification_service.py
──────────────────────────────────────
Module 8: Notification System
Sends notifications via Telegram Bot and Email (SMTP).
Every notification is logged in the Notification table for audit/history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib
import structlog
from sqlalchemy import select, func

from app.core.config import settings
from app.core.database import get_db_context
from app.models.interview import Notification, NotificationStatus

logger = structlog.get_logger()


class NotificationService:
    """
    Central notification dispatcher.
    Supports Telegram Bot and Email channels.
    Automatically reads user preferences before sending.
    """

    async def notify(
        self,
        title: str,
        body: str,
        event_type: str,
        data: Optional[dict] = None,
        telegram_markup: Optional[dict] = None,
    ) -> None:
        """
        Create and dispatch notifications to all enabled channels.
        Reads user notification preferences from UserProfile.
        """
        async with get_db_context() as db:
            from app.models.user import UserProfile
            result = await db.execute(select(UserProfile).limit(1))
            profile = result.scalar_one_or_none()

            if not profile:
                logger.warning("No user profile found — skipping notification")
                return

            user_id = profile.user_id

            # Use profile settings with global settings as fallback for notifications
            notify_telegram = (
                (profile.notify_via_telegram if profile else False) or bool(settings.TELEGRAM_BOT_TOKEN)
            )
            notify_email = (
                (profile.notify_via_email if profile else False) or bool(settings.SMTP_USERNAME)
            )

            if notify_telegram and settings.TELEGRAM_BOT_TOKEN:
                tg_notif = Notification(
                    user_id=user_id,
                    channel="telegram",
                    title=title,
                    body=body,
                    event_type=event_type,
                    data=data,
                    telegram_reply_markup=telegram_markup,
                )
                db.add(tg_notif)
                await db.flush()
                await self._send_telegram(tg_notif, db)

            if notify_email and settings.SMTP_USERNAME:
                to_email = profile.notification_email or settings.SMTP_USERNAME
                email_notif = Notification(
                    user_id=user_id,
                    channel="email",
                    title=title,
                    body=body,
                    event_type=event_type,
                    data=data,
                )
                db.add(email_notif)
                await db.flush()
                await self._send_email(email_notif, to_email, db)

            await db.commit()

    # ── Telegram ─────────────────────────────────────────────────────────────

    async def send_telegram(self, notification_id: str) -> dict:
        """Send a specific notification by ID via Telegram. Used by Celery tasks."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            notif = result.scalar_one_or_none()
            if not notif:
                return {"error": "Notification not found"}
            result = await self._send_telegram(notif, db)
            await db.commit()
            return result

    async def _send_telegram(self, notif: Notification, db) -> dict:
        """Internal Telegram send."""
        try:
            import httpx

            text = f"*{notif.title}*\n\n{notif.body}"
            payload: dict = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            }
            if notif.telegram_reply_markup:
                payload["reply_markup"] = notif.telegram_reply_markup

            async with httpx.AsyncClient(timeout=15) as http:
                response = await http.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json=payload,
                )
                data = response.json()

            if data.get("ok"):
                notif.status = NotificationStatus.SENT
                notif.sent_at = datetime.now(timezone.utc)
                notif.telegram_message_id = str(data["result"]["message_id"])
                logger.info("Telegram notification sent", title=notif.title)
                return {"sent": True}
            else:
                notif.status = NotificationStatus.FAILED
                notif.error_message = str(data)
                logger.error("Telegram send failed", error=data)
                return {"error": str(data)}

        except Exception as e:
            notif.status = NotificationStatus.FAILED
            notif.error_message = str(e)
            logger.error("Telegram exception", error=str(e))
            return {"error": str(e)}

    # ── Email ─────────────────────────────────────────────────────────────────

    async def send_email(self, notification_id: str) -> dict:
        """Send a specific notification by ID via Email. Used by Celery tasks."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            notif = result.scalar_one_or_none()
            if not notif:
                return {"error": "Notification not found"}
            from app.models.user import UserProfile
            profile = (await db.execute(select(UserProfile).limit(1))).scalar_one_or_none()
            to_email = profile.notification_email or settings.SMTP_USERNAME if profile else settings.SMTP_USERNAME
            result = await self._send_email(notif, to_email, db)
            await db.commit()
            return result

    async def _send_email(self, notif: Notification, to_email: str, db) -> dict:
        """Internal email send."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = notif.title
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = to_email

            # Plain text
            msg.attach(MIMEText(notif.body, "plain"))

            # HTML version
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; background: #f9f9f9;">
              <div style="background: white; padding: 24px; border-radius: 8px; border-left: 4px solid #00d4ff;">
                <h2 style="color: #1a1a2e; margin-top: 0;">{notif.title}</h2>
                <div style="color: #444; white-space: pre-line; line-height: 1.6;">{notif.body}</div>
              </div>
              <p style="color: #aaa; font-size: 11px; text-align: center; margin-top: 16px;">
                AI Career Platform &middot; Automated notification
              </p>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME,
                password=settings.SMTP_PASSWORD,
                start_tls=True,
                timeout=30,
            )

            notif.status = NotificationStatus.SENT
            notif.sent_at = datetime.now(timezone.utc)
            logger.info("Email notification sent", title=notif.title, to=to_email)
            return {"sent": True}

        except Exception as e:
            notif.status = NotificationStatus.FAILED
            notif.error_message = str(e)
            logger.error("Email send failed", error=str(e))
            return {"error": str(e)}

    # ── Digest ────────────────────────────────────────────────────────────────

    async def send_daily_digest(self) -> dict:
        """
        Send daily summary: jobs found, applications sent, status changes.
        Called by Celery beat daily.
        """
        from app.models.job import Job, JobAnalysis
        from app.models.application import Application

        async with get_db_context() as db:
            today = datetime.now(timezone.utc).date()

            jobs_today = (await db.execute(
                select(func.count(Job.id)).where(
                    func.date(Job.scraped_at) == today
                )
            )).scalar() or 0

            apps_today = (await db.execute(
                select(func.count(Application.id)).where(
                    func.date(Application.applied_at) == today
                )
            )).scalar() or 0

            top_jobs = (await db.execute(
                select(Job.title, Job.company_name, JobAnalysis.match_score)
                .join(JobAnalysis, Job.id == JobAnalysis.job_id)
                .where(func.date(Job.scraped_at) == today)
                .order_by(JobAnalysis.match_score.desc())
                .limit(5)
            )).all()

        if not jobs_today and not apps_today:
            logger.info("No activity today — skipping digest")
            return {"sent": False, "reason": "No activity"}

        job_lines = "\n".join(
            f"• {j.company_name} — {j.title} ({j.match_score:.0f}% match)"
            for j in top_jobs
        ) or "No new jobs today."

        body = (
            f"📊 *Daily Career Summary*\n\n"
            f"🔍 Jobs Found Today: {jobs_today}\n"
            f"📝 Applications Sent: {apps_today}\n\n"
            f"🏆 Top Matches:\n{job_lines}"
        )

        await self.notify(
            title="Daily Career Update",
            body=body,
            event_type="daily_digest",
            data={"jobs_today": jobs_today, "apps_today": apps_today},
        )
        return {"sent": True, "jobs_today": jobs_today, "apps_today": apps_today}
