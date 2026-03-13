"""
app/services/application_service.py
──────────────────────────────────────
Handles batch application queuing logic.
Respects daily limits, approval settings, and match thresholds.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select, func, desc
from datetime import datetime, timezone, date

from app.core.config import settings
from app.core.database import get_db_context
from app.models.job import Job, JobAnalysis, JobStatus
from app.models.application import Application, ApplicationStatus, ApplicationMethod
from app.models.user import User, UserProfile
from app.models.resume import Resume, ResumeType

logger = structlog.get_logger()


class ApplicationService:

    async def queue_batch_applications(self) -> dict:
        """
        Find all high-match analyzed jobs that haven't been applied to,
        and queue them for auto-apply respecting daily limits.
        """
        async with get_db_context() as db:
            # Get user
            user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if not user:
                return {"queued": 0, "reason": "No user found"}

            profile = (await db.execute(
                select(UserProfile).where(UserProfile.user_id == user.id)
            )).scalar_one_or_none()

            # Check if auto-apply is enabled - either via profile or global config
            is_auto_apply_enabled = (
                (profile and profile.auto_apply_enabled) or settings.AUTO_APPLY_ENABLED
            )
            if not is_auto_apply_enabled:
                return {"queued": 0, "reason": "Auto-apply disabled"}

            # Check daily limit
            today = datetime.now(timezone.utc).date()
            apps_today = (await db.execute(
                select(func.count(Application.id))
                .where(
                    Application.user_id == user.id,
                    func.date(Application.created_at) == today,
                )
            )).scalar() or 0

            # Use profile settings with global settings as fallback
            daily_limit = (
                profile.auto_apply_daily_limit 
                if profile and profile.auto_apply_daily_limit 
                else settings.AUTO_APPLY_DAILY_LIMIT
            )
            remaining = daily_limit - apps_today
            if remaining <= 0:
                return {"queued": 0, "reason": f"Daily limit of {daily_limit} reached"}

            # Find already-applied job IDs to exclude
            applied_job_ids = (await db.execute(
                select(Application.job_id).where(Application.user_id == user.id)
            )).scalars().all()

            # Use profile settings with global settings as fallback
            threshold = (
                profile.auto_apply_threshold 
                if profile and profile.auto_apply_threshold 
                else settings.AUTO_APPLY_MATCH_THRESHOLD
            )

            # Find top qualifying jobs
            result = await db.execute(
                select(Job)
                .join(JobAnalysis, Job.id == JobAnalysis.job_id)
                .where(
                    Job.is_active == True,
                    Job.status == JobStatus.ANALYZED,
                    JobAnalysis.match_score >= threshold,
                    ~Job.id.in_(applied_job_ids),
                )
                .order_by(desc(JobAnalysis.priority_score))
                .limit(remaining)
            )
            jobs = result.scalars().all()

            queued = 0
            for job in jobs:
                try:
                    # Find best resume for this job
                    resume = await self._find_best_resume(db, user.id, job)

                    status = (
                        ApplicationStatus.PENDING_APPROVAL
                        if profile.require_apply_approval
                        else ApplicationStatus.QUEUED
                    )

                    # Get match score
                    analysis = (await db.execute(
                        select(JobAnalysis).where(JobAnalysis.job_id == job.id)
                    )).scalar_one_or_none()

                    app = Application(
                        user_id=user.id,
                        job_id=job.id,
                        resume_id=resume.id if resume else None,
                        method=ApplicationMethod.AUTO_BOT,
                        status=status,
                        job_title_snapshot=job.title,
                        company_snapshot=job.company_name,
                        match_score_at_apply=analysis.match_score if analysis else None,
                    )
                    db.add(app)
                    queued += 1

                    # If not requiring approval, trigger immediately
                    if not profile.require_apply_approval:
                        await db.flush()
                        from app.agents.tasks import auto_apply_task
                        auto_apply_task.delay(app.id)

                except Exception as e:
                    logger.error("Failed to queue application", job_id=job.id, error=str(e))

            await db.commit()

            # Send notification about queued applications
            if queued > 0:
                from app.services.job_analyzer import NotificationService
                await NotificationService().notify(
                    title=f"📝 {queued} Applications Queued",
                    body=f"{queued} jobs matched your criteria and are {'waiting for approval' if profile.require_apply_approval else 'being applied to automatically'}.",
                    event_type="applications_queued",
                    data={"count": queued},
                    telegram_markup={
                        "inline_keyboard": [[
                            {"text": "✅ Approve All", "callback_data": "approve_all"},
                            {"text": "👀 Review", "callback_data": "review_applications"},
                        ]]
                    } if profile.require_apply_approval else None,
                )

            return {"queued": queued, "daily_remaining": remaining - queued}

    async def _find_best_resume(self, db, user_id: str, job: Job) -> Resume | None:
        """Find the most appropriate resume for a job."""
        # First try: tailored resume for this exact job
        tailored = (await db.execute(
            select(Resume).where(
                Resume.user_id == user_id,
                Resume.target_job_id == job.id,
                Resume.is_active == True,
            )
        )).scalar_one_or_none()
        if tailored:
            return tailored

        # Second try: role-variant resume matching job category
        analysis = (await db.execute(
            select(JobAnalysis).where(JobAnalysis.job_id == job.id)
        )).scalar_one_or_none()

        if analysis and analysis.role_category:
            variant = (await db.execute(
                select(Resume).where(
                    Resume.user_id == user_id,
                    Resume.resume_type == ResumeType.ROLE_VARIANT,
                    Resume.role_category == analysis.role_category,
                    Resume.is_active == True,
                )
            )).scalar_one_or_none()
            if variant:
                return variant

        # Fallback: default base resume
        return (await db.execute(
            select(Resume).where(
                Resume.user_id == user_id,
                Resume.is_default == True,
                Resume.is_active == True,
            )
        )).scalar_one_or_none()
