"""
app/agents/tasks.py
────────────────────
Celery task definitions — every automated action the platform can take.
Tasks are designed to be:
  - Idempotent (safe to retry)
  - Small and single-purpose
  - Fully logged via AgentTask records
  - Recoverable (exponential backoff on failure)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from celery import Celery
from celery.utils.log import get_task_logger

from app.core.config import settings

logger = get_task_logger(__name__)

# ── Celery App ───────────────────────────────────────────────────────────────

celery_app = Celery(
    "career_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Retry behavior
    task_acks_late=True,            # Ack only after task completes (safe retries)
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    # Rate limiting (be gentle with external services)
    task_annotations={
        "app.agents.tasks.scrape_linkedin_task": {"rate_limit": "10/m"},
        "app.agents.tasks.scrape_indeed_task": {"rate_limit": "20/m"},
        "app.agents.tasks.auto_apply_task": {"rate_limit": "5/m"},
    },
    # Result expiry (keep for 24 hours)
    result_expires=86400,
    # Routing — separate queues for different task types
    task_routes={
        "app.agents.tasks.scrape_*": {"queue": "scraping"},
        "app.agents.tasks.auto_apply_task": {"queue": "automation"},
        "app.agents.tasks.analyze_*": {"queue": "ai"},
        "app.agents.tasks.generate_*": {"queue": "ai"},
        "app.agents.tasks.send_*": {"queue": "notifications"},
    },
    # Periodic schedule
    beat_schedule={
        "main-agent-cycle": {
            "task": "app.agents.tasks.run_main_agent_cycle",
            "schedule": settings.SCRAPE_INTERVAL_HOURS * 3600,  # Every 6 hours
        },
        "follow-up-check": {
            "task": "app.agents.tasks.check_follow_ups",
            "schedule": 3600,  # Every hour
        },
        "market-snapshot": {
            "task": "app.agents.tasks.take_market_snapshot",
            "schedule": 86400,  # Daily
        },
        "resume-performance-update": {
            "task": "app.agents.tasks.update_resume_performance",
            "schedule": 3600 * 6,  # Every 6 hours
        },
    },
)


# ── Helper: run async code in sync Celery task ───────────────────────────────

def run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def with_task_log(task_type: str):
    """
    Decorator that wraps a Celery task with AgentTask logging.
    Automatically creates AgentTask record, updates status, logs errors.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from app.core.database import get_db_context
            from app.models.interview import AgentTask, AgentTaskStatus

            async def _run():
                async with get_db_context() as db:
                    # Create task record
                    task_record = AgentTask(
                        task_type=task_type,
                        status=AgentTaskStatus.RUNNING,
                        started_at=datetime.now(timezone.utc),
                        payload={"args": list(args), "kwargs": kwargs},
                        triggered_by="scheduler",
                    )
                    db.add(task_record)
                    await db.commit()
                    task_id = task_record.id

                try:
                    result = fn(*args, **kwargs)
                    async with get_db_context() as db:
                        from sqlalchemy import select
                        rec = (await db.execute(
                            select(AgentTask).where(AgentTask.id == task_id)
                        )).scalar_one()
                        rec.status = AgentTaskStatus.SUCCESS
                        rec.result = result if isinstance(result, dict) else {"output": str(result)}
                        rec.completed_at = datetime.now(timezone.utc)
                        if rec.started_at:
                            rec.duration_ms = int(
                                (rec.completed_at - rec.started_at).total_seconds() * 1000
                            )
                        await db.commit()
                    return result
                except Exception as e:
                    async with get_db_context() as db:
                        from sqlalchemy import select
                        rec = (await db.execute(
                            select(AgentTask).where(AgentTask.id == task_id)
                        )).scalar_one()
                        rec.status = AgentTaskStatus.FAILED
                        rec.error = str(e)
                        rec.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                    raise

            return run_async(_run())
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATION TASK
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.run_main_agent_cycle", max_retries=1)
def run_main_agent_cycle(self):
    """
    Master task — runs every 6 hours.
    Orchestrates the full pipeline:
    scrape → analyze → generate → apply → notify
    """
    logger.info("Starting main agent cycle")
    try:
        # Step 1: Scrape all platforms in parallel
        scrape_group = celery_app.group(
            scrape_linkedin_task.s(),
            scrape_indeed_task.s(),
            scrape_internshala_task.s(),
            scrape_wellfound_task.s(),
        )

        # Step 2: After scraping, analyze new jobs
        analysis_chain = scrape_group | analyze_new_jobs_batch_task.s()

        # Step 3: After analysis, generate materials and queue applications
        full_chain = (
            analysis_chain
            | generate_materials_for_top_jobs_task.s()
            | queue_auto_applications_task.s()
            | take_market_snapshot.s()
            | send_daily_digest_task.s()
        )

        full_chain.delay()
        logger.info("Main agent cycle tasks dispatched")
        return {"status": "dispatched"}
    except Exception as exc:
        logger.error(f"Main cycle failed: {exc}")
        self.retry(exc=exc, countdown=300)  # Retry after 5 min


# ═══════════════════════════════════════════════════════════════════════════
#  SCRAPING TASKS  (Module 1)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.scrape_linkedin_task", max_retries=3)
def scrape_linkedin_task(self, **kwargs):
    """Scrape LinkedIn for jobs matching user preferences."""
    try:
        from app.agents.scrapers.linkedin import LinkedInScraper
        results = run_async(LinkedInScraper().run())
        logger.info(f"LinkedIn scrape: {results['jobs_found']} jobs found")
        return results
    except Exception as exc:
        logger.error(f"LinkedIn scrape failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, name="app.agents.tasks.scrape_indeed_task", max_retries=3)
def scrape_indeed_task(self, **kwargs):
    """Scrape Indeed."""
    try:
        from app.agents.scrapers.indeed import IndeedScraper
        results = run_async(IndeedScraper().run())
        logger.info(f"Indeed scrape: {results['jobs_found']} jobs found")
        return results
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, name="app.agents.tasks.scrape_internshala_task", max_retries=3)
def scrape_internshala_task(self, **kwargs):
    """Scrape Internshala."""
    try:
        from app.agents.scrapers.internshala import IntershalaScraper
        results = run_async(IntershalaScraper().run())
        logger.info(f"Internshala scrape: {results['jobs_found']} jobs found")
        return results
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, name="app.agents.tasks.scrape_wellfound_task", max_retries=3)
def scrape_wellfound_task(self, **kwargs):
    """Scrape Wellfound (AngelList)."""
    try:
        from app.agents.scrapers.wellfound import WellfoundScraper
        results = run_async(WellfoundScraper().run())
        return results
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


# ═══════════════════════════════════════════════════════════════════════════
#  ANALYSIS TASKS  (Module 2)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.analyze_job_task", max_retries=2)
def analyze_job_task(self, job_id: str):
    """Run AI analysis on a single job."""
    try:
        from app.services.job_analyzer import JobAnalyzerService
        result = run_async(JobAnalyzerService().analyze(job_id))
        logger.info(f"Job {job_id} analyzed: match_score={result.get('match_score')}")
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="app.agents.tasks.analyze_new_jobs_batch_task")
def analyze_new_jobs_batch_task(self, scrape_results=None):
    """
    Batch analyze all NEW jobs after a scrape cycle.
    Uses cheap model for initial filter, heavy model for top candidates.
    """
    try:
        from app.services.job_analyzer import JobAnalyzerService
        result = run_async(JobAnalyzerService().analyze_new_batch())
        logger.info(f"Batch analysis complete: {result['analyzed']} jobs processed")
        return result
    except Exception as exc:
        logger.error(f"Batch analysis failed: {exc}")
        return {"analyzed": 0, "error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════
#  RESUME & COVER LETTER TASKS  (Modules 3, 4)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.generate_resume_task", max_retries=2)
def generate_resume_task(self, user_id: str, job_id: str, base_resume_id: Optional[str] = None):
    """Generate a tailored resume for a specific job."""
    try:
        from app.services.resume_service import ResumeService
        result = run_async(ResumeService().generate_tailored(user_id, job_id, base_resume_id))
        logger.info(f"Resume generated for job {job_id}: resume_id={result.get('resume_id')}")
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="app.agents.tasks.generate_cover_letter_task", max_retries=2)
def generate_cover_letter_task(self, user_id: str, job_id: str, tone: str = "professional"):
    """Generate a cover letter for a specific job."""
    try:
        from app.services.cover_letter_service import CoverLetterService
        result = run_async(CoverLetterService().generate(user_id, job_id, tone))
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.agents.tasks.generate_materials_for_top_jobs_task")
def generate_materials_for_top_jobs_task(analysis_results=None):
    """
    After batch analysis, generate resume + cover letter for
    all jobs above the apply threshold.
    """
    try:
        from app.services.resume_service import ResumeService
        result = run_async(ResumeService().generate_for_top_jobs())
        return result
    except Exception as exc:
        logger.error(f"Material generation failed: {exc}")
        return {"generated": 0}


# ═══════════════════════════════════════════════════════════════════════════
#  AUTO APPLY TASK  (Module 5)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.auto_apply_task", max_retries=2)
def auto_apply_task(self, application_id: str):
    """
    Run Playwright bot to submit a job application.
    Handles: form filling, resume upload, cover letter attach, submit.
    Pauses and notifies on CAPTCHA detection.
    """
    try:
        from app.agents.apply_bot import ApplyBot
        result = run_async(ApplyBot().apply(application_id))
        logger.info(f"Auto-apply {application_id}: {result['status']}")
        return result
    except Exception as exc:
        logger.error(f"Auto-apply failed for {application_id}: {exc}")
        raise self.retry(exc=exc, countdown=60 * 2)


@celery_app.task(name="app.agents.tasks.queue_auto_applications_task")
def queue_auto_applications_task(material_results=None):
    """
    Queue applications for all jobs that have materials generated
    and haven't been applied to yet.
    Respects daily limit and approval settings.
    """
    try:
        from app.services.application_service import ApplicationService
        result = run_async(ApplicationService().queue_batch_applications())
        logger.info(f"Queued {result.get('queued', 0)} applications")
        return result
    except Exception as exc:
        logger.error(f"Batch queue failed: {exc}")
        return {"queued": 0}


# ═══════════════════════════════════════════════════════════════════════════
#  FOLLOW-UP TASK  (Module 7)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(name="app.agents.tasks.check_follow_ups")
def check_follow_ups():
    """
    Runs hourly. Sends follow-up emails to recruiters when:
    - Application is 7 days old with no response
    - Interview thank-you email is due
    """
    try:
        from app.services.follow_up_service import FollowUpService
        result = run_async(FollowUpService().process_due_follow_ups())
        logger.info(f"Follow-ups processed: {result}")
        return result
    except Exception as exc:
        logger.error(f"Follow-up check failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
#  NOTIFICATION TASKS  (Module 8)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.send_telegram_notification", max_retries=3)
def send_telegram_notification(self, notification_id: str):
    """Send a notification via Telegram."""
    try:
        from app.services.notification_service import NotificationService
        result = run_async(NotificationService().send_telegram(notification_id))
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, name="app.agents.tasks.send_email_notification", max_retries=3)
def send_email_notification(self, notification_id: str):
    """Send a notification via Email."""
    try:
        from app.services.notification_service import NotificationService
        result = run_async(NotificationService().send_email(notification_id))
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(name="app.agents.tasks.send_daily_digest_task")
def send_daily_digest_task(queue_results=None):
    """
    Send daily digest notification with:
    - Jobs found today
    - Applications submitted
    - Status changes
    """
    try:
        from app.services.notification_service import NotificationService
        result = run_async(NotificationService().send_daily_digest())
        return result
    except Exception as exc:
        logger.error(f"Daily digest failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
#  MARKET & ANALYTICS TASKS  (Module 22)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(name="app.agents.tasks.take_market_snapshot")
def take_market_snapshot(prev_results=None):
    """Aggregate job data into a market intelligence snapshot."""
    try:
        from app.services.market_service import MarketIntelligenceService
        result = run_async(MarketIntelligenceService().take_snapshot())
        logger.info(f"Market snapshot taken: {result}")
        return result
    except Exception as exc:
        logger.error(f"Market snapshot failed: {exc}")


@celery_app.task(name="app.agents.tasks.update_resume_performance")
def update_resume_performance():
    """Recalculate response rates for all resume versions."""
    try:
        from app.services.resume_service import ResumeService
        run_async(ResumeService().update_performance_metrics())
    except Exception as exc:
        logger.error(f"Resume perf update failed: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
#  INTERVIEW PREP TASK  (Module 18)
# ═══════════════════════════════════════════════════════════════════════════

@celery_app.task(bind=True, name="app.agents.tasks.prepare_interview_task", max_retries=2)
def prepare_interview_task(self, interview_id: str):
    """Auto-generate interview prep material when interview is scheduled."""
    try:
        from app.services.interview_service import InterviewPrepService
        result = run_async(InterviewPrepService().prepare(interview_id))
        logger.info(f"Interview prep complete for {interview_id}")
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


# ── Task Registry (for manual triggering via API) ────────────────────────────

TASK_REGISTRY = {
    "scrape_jobs": run_main_agent_cycle,
    "scrape_linkedin": scrape_linkedin_task,
    "scrape_indeed": scrape_indeed_task,
    "scrape_internshala": scrape_internshala_task,
    "scrape_wellfound": scrape_wellfound_task,
    "analyze_new_jobs": analyze_new_jobs_batch_task,
    "check_follow_ups": check_follow_ups,
    "market_snapshot": take_market_snapshot,
    "daily_digest": send_daily_digest_task,
}
