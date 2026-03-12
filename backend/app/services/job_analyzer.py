"""
app/services/job_analyzer.py
─────────────────────────────
Module 2: Job Description Analyzer
Uses GPT-4o-mini for batch filtering, GPT-4o for deep analysis of top candidates.
Produces structured JobAnalysis records with match scores, skill gaps, ATS keywords.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db_context
from app.models.job import Job, JobAnalysis, JobStatus
from app.models.user import User, UserSkill, UserProfile

logger = structlog.get_logger()
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


ANALYSIS_SYSTEM_PROMPT = """
You are an expert technical recruiter and career analyst.
Analyze the provided job description and return ONLY a valid JSON object.
Do not include any text outside the JSON.

The JSON must have exactly these fields:
{
  "required_skills": ["skill1", "skill2"],
  "preferred_skills": ["skill3"],
  "tech_stack": ["Python", "PyTorch"],
  "ats_keywords": ["keyword1", "keyword2"],
  "min_years_experience": 0,
  "max_years_experience": null,
  "education_requirement": "bachelor|master|phd|none",
  "key_responsibilities": ["responsibility1"],
  "role_category": "computer_vision|nlp|mlops|data_science|software_engineering|other",
  "seniority_detected": "entry|mid|senior|lead",
  "is_internship": true,
  "estimated_salary_min": null,
  "estimated_salary_max": null,
  "job_difficulty": "easy|medium|hard",
  "ai_summary": "2-sentence summary of the role",
  "ai_recommendation": null
}
"""

MATCH_SCORING_PROMPT = """
You are a career matching expert. Given a user's profile and a job analysis,
compute a match score and provide a recommendation.

Return ONLY valid JSON:
{
  "match_score": 75.0,
  "skill_match_score": 80.0,
  "experience_match_score": 70.0,
  "matching_skills": ["Python", "PyTorch"],
  "missing_skills": ["Docker", "AWS"],
  "skill_gap_count": 2,
  "competition_level": "medium",
  "interview_probability": 0.35,
  "priority_score": 65.0,
  "ai_recommendation": "Strong match — your PyTorch and OpenCV experience directly aligns. Missing: Docker, AWS (learnable). Apply immediately."
}
"""


class JobAnalyzerService:
    """
    AI-powered job description analysis service.
    Two-tier analysis:
      Tier 1 (gpt-4o-mini): Fast batch analysis of all new jobs
      Tier 2 (gpt-4o): Deep analysis + match scoring for top candidates
    """

    async def analyze(self, job_id: str) -> dict:
        """Analyze a single job (full pipeline)."""
        async with get_db_context() as db:
            # Load job
            result = await db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if not job:
                raise ValueError(f"Job {job_id} not found")

            # Load user profile
            user_result = await db.execute(select(UserProfile))
            profile = user_result.scalar_one_or_none()
            skills_result = await db.execute(select(UserSkill))
            skills = skills_result.scalars().all()

            # Run analysis
            analysis_data = await self._analyze_description(job)
            match_data = await self._compute_match(analysis_data, profile, skills)

            # Save or update
            existing = (await db.execute(
                select(JobAnalysis).where(JobAnalysis.job_id == job_id)
            )).scalar_one_or_none()

            combined = {**analysis_data, **match_data}

            if existing:
                for key, value in combined.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                analysis = JobAnalysis(job_id=job_id, **{
                    k: v for k, v in combined.items() if hasattr(JobAnalysis, k)
                })
                db.add(analysis)

            # Update job status
            job.status = JobStatus.ANALYZED
            await db.commit()

            return {"job_id": job_id, "match_score": match_data.get("match_score")}

    async def analyze_new_batch(self) -> dict:
        """Analyze all NEW jobs using tiered approach."""
        async with get_db_context() as db:
            result = await db.execute(
                select(Job).where(Job.status == JobStatus.NEW).limit(100)
            )
            new_jobs = result.scalars().all()

        analyzed = 0
        for job in new_jobs:
            try:
                await self.analyze(job.id)
                analyzed += 1
            except Exception as e:
                logger.error("Job analysis failed", job_id=job.id, error=str(e))

        return {"analyzed": analyzed, "total_new": len(new_jobs)}

    async def _analyze_description(self, job: Job) -> dict:
        """Tier 1: Extract structured data from job description."""
        description = job.description_clean or job.description_raw or ""
        if not description:
            return self._empty_analysis()

        start = time.time()
        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL_LIGHT,  # gpt-4o-mini for speed/cost
                max_tokens=1000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Job Title: {job.title}\nCompany: {job.company_name}\n\nDescription:\n{description[:8000]}"},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content)
            data["model_used"] = settings.OPENAI_MODEL_LIGHT
            data["tokens_used"] = response.usage.total_tokens
            data["processing_time_ms"] = int((time.time() - start) * 1000)
            return data
        except Exception as e:
            logger.error("LLM analysis failed", error=str(e))
            return self._empty_analysis()

    async def _compute_match(self, analysis: dict, profile: Optional[UserProfile], skills: list) -> dict:
        """Tier 2: Score the match against user profile."""
        if not profile:
            return {"match_score": 0.0, "matching_skills": [], "missing_skills": [], "skill_gap_count": 0}

        user_skills = {s.name.lower() for s in skills}
        required = [s.lower() for s in analysis.get("required_skills", [])]
        preferred = [s.lower() for s in analysis.get("preferred_skills", [])]

        matching = [s for s in required + preferred if s in user_skills]
        missing = [s for s in required if s not in user_skills]

        skill_match = (len(matching) / max(len(required), 1)) * 100 if required else 50.0

        # Use GPT for nuanced scoring when skill match is above threshold
        if skill_match > 30:
            try:
                profile_summary = self._build_profile_summary(profile, skills)
                response = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL_LIGHT,
                    max_tokens=500,
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": MATCH_SCORING_PROMPT},
                        {"role": "user", "content": f"USER PROFILE:\n{profile_summary}\n\nJOB ANALYSIS:\n{json.dumps(analysis, indent=2)[:3000]}"},
                    ],
                    response_format={"type": "json_object"},
                )
                match_data = json.loads(response.choices[0].message.content)
                match_data["matching_skills"] = matching
                match_data["missing_skills"] = missing
                match_data["skill_gap_count"] = len(missing)
                return match_data
            except Exception as e:
                logger.error("Match scoring LLM failed", error=str(e))

        # Fallback: simple rule-based scoring
        return {
            "match_score": round(skill_match, 1),
            "skill_match_score": round(skill_match, 1),
            "experience_match_score": 50.0,
            "matching_skills": matching,
            "missing_skills": missing,
            "skill_gap_count": len(missing),
            "competition_level": "medium",
            "interview_probability": skill_match / 200,
            "priority_score": skill_match * 0.6,
            "ai_recommendation": f"Skill match: {skill_match:.0f}%. Missing: {', '.join(missing[:3])}.",
        }

    def _build_profile_summary(self, profile: UserProfile, skills: list) -> str:
        skill_names = ", ".join(s.name for s in skills[:30])
        roles = ", ".join(profile.desired_roles[:5]) if profile.desired_roles else "ML/AI roles"
        return (
            f"Experience Level: {profile.experience_level}\n"
            f"Target Roles: {roles}\n"
            f"Skills: {skill_names}\n"
            f"Summary: {profile.professional_summary or 'AI/ML student'}"
        )

    def _empty_analysis(self) -> dict:
        return {
            "required_skills": [], "preferred_skills": [], "tech_stack": [],
            "ats_keywords": [], "key_responsibilities": [], "role_category": "other",
            "seniority_detected": "unknown", "is_internship": False,
            "job_difficulty": "medium", "ai_summary": "", "model_used": None,
            "tokens_used": 0, "processing_time_ms": 0,
        }


# ── Re-export NotificationService for backwards compatibility ────────────────
# The real implementation is in app/services/notification_service.py
from app.services.notification_service import NotificationService  # noqa: F401



# Suppress the unused legacy code below — replaced by notification_service.py
if False:
    class _NotificationServiceLegacy:
    """
    Handles sending notifications via Telegram and Email.
    Every notification is logged in the Notification table.
    """

    async def notify(
        self,
        title: str,
        body: str,
        event_type: str,
        data: Optional[dict] = None,
        telegram_markup: Optional[dict] = None,
    ) -> None:
        """Create and dispatch notifications to all enabled channels."""
        async with get_db_context() as db:
            # Load user preferences
            result = await db.execute(select(UserProfile))
            profile = result.scalar_one_or_none()
            if not profile:
                return

            from app.models.user import UserProfile as UP
            if profile.notify_via_telegram:
                tg_notif = Notification(
                    user_id=profile.user_id,
                    channel="telegram",
                    title=title,
                    body=body,
                    event_type=event_type,
                    data=data,
                    telegram_reply_markup=telegram_markup,
                )
                db.add(tg_notif)
                await db.flush()
                await self.send_telegram(tg_notif.id, db=db)

            if profile.notify_via_email:
                email_notif = Notification(
                    user_id=profile.user_id,
                    channel="email",
                    title=title,
                    body=body,
                    event_type=event_type,
                    data=data,
                )
                db.add(email_notif)
                await db.flush()
                await self.send_email(email_notif.id, db=db)

            await db.commit()

    async def send_telegram(self, notification_id: str, db=None) -> dict:
        """Send a Telegram message via Bot API."""
        ctx = db if db else get_db_context()

        async def _send(session):
            result = await session.execute(select(Notification).where(Notification.id == notification_id))
            notif = result.scalar_one_or_none()
            if not notif:
                return {"error": "Notification not found"}

            try:
                import httpx
                payload = {
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": f"*{notif.title}*\n\n{notif.body}",
                    "parse_mode": "Markdown",
                }
                if notif.telegram_reply_markup:
                    payload["reply_markup"] = notif.telegram_reply_markup

                async with httpx.AsyncClient() as http:
                    response = await http.post(
                        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                        json=payload,
                        timeout=10,
                    )
                    response_data = response.json()

                if response_data.get("ok"):
                    notif.status = NotificationStatus.SENT
                    notif.sent_at = datetime.now(timezone.utc)
                    notif.telegram_message_id = str(response_data["result"]["message_id"])
                else:
                    notif.status = NotificationStatus.FAILED
                    notif.error_message = str(response_data)

                await session.commit()
                return {"sent": True}
            except Exception as e:
                notif.status = NotificationStatus.FAILED
                notif.error_message = str(e)
                await session.commit()
                return {"error": str(e)}

        if db:
            return await _send(db)
        else:
            async with get_db_context() as session:
                return await _send(session)

    async def send_email(self, notification_id: str, db=None) -> dict:
        """Send an email notification."""
        async def _send(session):
            result = await session.execute(select(Notification).where(Notification.id == notification_id))
            notif = result.scalar_one_or_none()
            if not notif:
                return {"error": "Notification not found"}

            # Load user email
            profile_result = await session.execute(select(UserProfile))
            profile = profile_result.scalar_one_or_none()
            to_email = profile.notification_email or settings.SMTP_USERNAME if profile else settings.SMTP_USERNAME

            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = notif.title
                msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
                msg["To"] = to_email

                html_body = f"""
                <html><body style="font-family: Arial; max-width: 600px; margin: auto; padding: 20px;">
                <h2 style="color: #00d4ff;">{notif.title}</h2>
                <div style="white-space: pre-line; color: #333;">{notif.body}</div>
                <hr style="margin-top: 30px; border-color: #eee;">
                <p style="color: #999; font-size: 12px;">AI Career Platform | Automated notification</p>
                </body></html>
                """
                msg.attach(MIMEText(notif.body, "plain"))
                msg.attach(MIMEText(html_body, "html"))

                await aiosmtplib.send(
                    msg,
                    hostname=settings.SMTP_HOST,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USERNAME,
                    password=settings.SMTP_PASSWORD,
                    start_tls=True,
                )
                notif.status = NotificationStatus.SENT
                notif.sent_at = datetime.now(timezone.utc)
                await session.commit()
                return {"sent": True}
            except Exception as e:
                notif.status = NotificationStatus.FAILED
                notif.error_message = str(e)
                await session.commit()
                return {"error": str(e)}

        if db:
            return await _send(db)
        else:
            async with get_db_context() as session:
                return await _send(session)

    async def send_daily_digest(self) -> dict:
        """Send daily summary of agent activity."""
        from sqlalchemy import func
        async with get_db_context() as db:
            today = datetime.now(timezone.utc).date()

            jobs_today = (await db.execute(
                select(func.count(Job.id)).where(func.date(Job.scraped_at) == today)
            )).scalar() or 0

            apps_today = (await db.execute(
                select(func.count(Application.id)).where(func.date(Application.applied_at) == today)
            )).scalar() or 0

            top_jobs = (await db.execute(
                select(Job.title, Job.company_name, JobAnalysis.match_score)
                .join(JobAnalysis, Job.id == JobAnalysis.job_id)
                .where(func.date(Job.scraped_at) == today)
                .order_by(JobAnalysis.match_score.desc())
                .limit(5)
            )).all()

        job_lines = "\n".join(
            f"• {j.company_name} — {j.title} ({j.match_score:.0f}% match)"
            for j in top_jobs
        ) or "No jobs found today."

        body = (
            f"📊 Daily Summary\n\n"
            f"🔍 Jobs Found: {jobs_today}\n"
            f"📝 Applications Sent: {apps_today}\n\n"
            f"🏆 Top Matches:\n{job_lines}"
        )

        await self.notify(
            title="Daily Career Update",
            body=body,
            event_type="daily_digest",
        )
        return {"sent": True}


from app.models.user import UserProfile
from app.models.job import Job
from app.models.application import Application
