"""
app/agents/apply_bot.py
────────────────────────
Module 5: Auto Apply Bot
Uses Playwright to automatically fill and submit job applications.
Handles: Workday, Greenhouse, Lever, LinkedIn Easy Apply, and generic forms.
Pauses and notifies user on CAPTCHA detection.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db_context
from app.models.application import Application, ApplicationEvent, ApplicationStatus
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import UserProfile

logger = structlog.get_logger()


class ApplyBot:
    """
    Playwright-based job application bot.
    Detects which ATS system the job uses and applies the right strategy.
    """

    ATS_HANDLERS = {
        "workday": "myworkdayjobs.com",
        "greenhouse": "greenhouse.io",
        "lever": "lever.co",
        "linkedin": "linkedin.com/jobs",
        "internshala": "internshala.com",
        "indeed": "indeed.com",
    }

    async def apply(self, application_id: str) -> dict:
        """Main entry point — apply to a single job application."""
        async with get_db_context() as db:
            # Load application
            app = (await db.execute(
                select(Application).where(Application.id == application_id)
            )).scalar_one_or_none()
            if not app:
                raise ValueError(f"Application {application_id} not found")

            job = (await db.execute(
                select(Job).where(Job.id == app.job_id)
            )).scalar_one_or_none()

            profile = (await db.execute(
                select(UserProfile)
            )).scalar_one_or_none()

            resume = None
            if app.resume_id:
                resume = (await db.execute(
                    select(Resume).where(Resume.id == app.resume_id)
                )).scalar_one_or_none()

            # Update status to applying
            app.status = ApplicationStatus.APPLYING
            db.add(ApplicationEvent(
                application_id=app.id,
                event_type="bot_started",
                from_status=ApplicationStatus.QUEUED,
                to_status=ApplicationStatus.APPLYING,
                triggered_by="agent",
            ))
            await db.commit()

        # Run the bot
        result = await self._run_playwright(app, job, profile, resume)

        # Update final status
        async with get_db_context() as db:
            app_record = (await db.execute(
                select(Application).where(Application.id == application_id)
            )).scalar_one()

            if result["success"]:
                app_record.status = ApplicationStatus.APPLIED
                app_record.applied_at = datetime.now(timezone.utc)
                db.add(ApplicationEvent(
                    application_id=application_id,
                    event_type="application_submitted",
                    from_status=ApplicationStatus.APPLYING,
                    to_status=ApplicationStatus.APPLIED,
                    triggered_by="agent",
                    details=result,
                ))
                logger.info("Application submitted", app_id=application_id, job=job.title if job else "?")

                # Update resume usage stats
                if app_record.resume_id:
                    resume_record = (await db.execute(
                        select(Resume).where(Resume.id == app_record.resume_id)
                    )).scalar_one_or_none()
                    if resume_record:
                        resume_record.times_used += 1

                # Send success notification
                from app.services.job_analyzer import NotificationService
                await NotificationService().notify(
                    title=f"✅ Applied — {job.company_name if job else 'Company'}",
                    body=f"Successfully applied to {job.title if job else 'role'} at {job.company_name if job else 'company'}.",
                    event_type="application_submitted",
                )

            elif result.get("captcha"):
                app_record.status = ApplicationStatus.QUEUED  # Reset to retry manually
                app_record.bot_error = "CAPTCHA detected — manual intervention required"
                db.add(ApplicationEvent(
                    application_id=application_id,
                    event_type="captcha_detected",
                    triggered_by="agent",
                    details=result,
                ))
                # Notify user to solve CAPTCHA
                from app.services.job_analyzer import NotificationService
                await NotificationService().notify(
                    title=f"⚠️ CAPTCHA Required — {job.company_name if job else 'Company'}",
                    body=f"The application bot hit a CAPTCHA on {job.company_name if job else 'company'}. Please apply manually.\n\n{job.source_url if job else ''}",
                    event_type="captcha_detected",
                )
            else:
                app_record.status = ApplicationStatus.FAILED
                app_record.bot_error = result.get("error", "Unknown error")
                app_record.retry_count += 1
                db.add(ApplicationEvent(
                    application_id=application_id,
                    event_type="bot_failed",
                    from_status=ApplicationStatus.APPLYING,
                    to_status=ApplicationStatus.FAILED,
                    triggered_by="agent",
                    details={"error": result.get("error")},
                ))

            await db.commit()

        return result

    async def _run_playwright(
        self,
        app: Application,
        job: Optional[Job],
        profile: Optional[UserProfile],
        resume: Optional[Resume],
    ) -> dict:
        """Launch Playwright browser and execute the application."""
        if not job:
            return {"success": False, "error": "Job not found"}

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                    ]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
                    viewport={"width": 1280, "height": 720},
                )
                page = await context.new_page()

                try:
                    # Detect ATS type
                    ats = self._detect_ats(job.source_url)
                    logger.info("Detected ATS", ats=ats, url=job.source_url)

                    # Dispatch to appropriate handler
                    if ats == "linkedin":
                        result = await self._apply_linkedin(page, job, profile, resume)
                    elif ats == "greenhouse":
                        result = await self._apply_greenhouse(page, job, profile, resume)
                    elif ats == "lever":
                        result = await self._apply_lever(page, job, profile, resume)
                    elif ats == "workday":
                        result = await self._apply_workday(page, job, profile, resume)
                    else:
                        result = await self._apply_generic(page, job, profile, resume)

                    return result

                except Exception as e:
                    error_str = str(e)
                    is_captcha = any(w in error_str.lower() for w in ["captcha", "recaptcha", "verify you are human"])
                    return {
                        "success": False,
                        "captcha": is_captcha,
                        "error": error_str,
                    }
                finally:
                    await browser.close()

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return {"success": False, "error": "Playwright not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _detect_ats(self, url: str) -> str:
        """Detect which ATS the job URL belongs to."""
        url_lower = url.lower()
        for ats, domain in self.ATS_HANDLERS.items():
            if domain in url_lower:
                return ats
        return "generic"

    async def _apply_linkedin(self, page, job, profile, resume) -> dict:
        """Handle LinkedIn Easy Apply."""
        await page.goto(job.source_url, wait_until="networkidle")
        await asyncio.sleep(2)

        # Check for Easy Apply button
        easy_apply_btn = await page.query_selector("button[aria-label*='Easy Apply']")
        if not easy_apply_btn:
            return {"success": False, "error": "No Easy Apply button found — requires manual application"}

        await easy_apply_btn.click()
        await asyncio.sleep(1)

        # Fill multi-step form
        max_steps = 10
        for step in range(max_steps):
            await self._fill_linkedin_step(page, profile)
            await asyncio.sleep(1)

            # Check for submit button
            submit_btn = await page.query_selector("button[aria-label='Submit application']")
            if submit_btn:
                await submit_btn.click()
                await asyncio.sleep(2)
                return {"success": True, "ats": "linkedin", "steps": step + 1}

            # Next button
            next_btn = (
                await page.query_selector("button[aria-label='Continue to next step']") or
                await page.query_selector("button[aria-label='Review your application']")
            )
            if next_btn:
                await next_btn.click()
                await asyncio.sleep(1)
            else:
                break

        return {"success": False, "error": "Could not complete LinkedIn Easy Apply form"}

    async def _fill_linkedin_step(self, page, profile):
        """Fill visible form fields in current LinkedIn step."""
        if not profile:
            return

        # Phone number
        phone_field = await page.query_selector("input[id*='phone']")
        if phone_field:
            val = await phone_field.input_value()
            if not val and profile.phone:
                await phone_field.fill(profile.phone)

        # Common text fields
        field_mappings = {
            "input[id*='city']": profile.location or "",
            "input[id*='location']": profile.location or "",
        }
        for selector, value in field_mappings.items():
            if value:
                field = await page.query_selector(selector)
                if field:
                    existing = await field.input_value()
                    if not existing:
                        await field.fill(value)

        # Yes/No radio buttons — default to "Yes" for standard questions
        yes_radios = await page.query_selector_all("input[type='radio'][value='Yes']")
        for radio in yes_radios:
            if not await radio.is_checked():
                await radio.check()

    async def _apply_greenhouse(self, page, job, profile, resume) -> dict:
        """Handle Greenhouse ATS applications."""
        await page.goto(job.source_url, wait_until="networkidle")
        await asyncio.sleep(2)

        if not profile:
            return {"success": False, "error": "No profile configured"}

        # Fill basic fields
        await self._fill_field(page, "input#first_name", profile.user_id.split()[0] if profile.user_id else "")
        await self._fill_field(page, "input#last_name", profile.user_id.split()[-1] if profile.user_id else "")
        await self._fill_field(page, "input#email", settings.USER_EMAIL)
        await self._fill_field(page, "input#phone", profile.phone or "")

        # Upload resume
        if resume and resume.file_path:
            resume_full_path = settings.storage_path / resume.file_path
            if resume_full_path.exists():
                resume_input = await page.query_selector("input[type='file']")
                if resume_input:
                    await resume_input.set_input_files(str(resume_full_path))
                    await asyncio.sleep(2)

        # Submit
        submit_btn = await page.query_selector("input[type='submit'], button[type='submit']")
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(3)
            return {"success": True, "ats": "greenhouse"}

        return {"success": False, "error": "Could not find submit button"}

    async def _apply_lever(self, page, job, profile, resume) -> dict:
        """Handle Lever ATS applications."""
        await page.goto(job.source_url, wait_until="networkidle")
        await asyncio.sleep(2)

        if not profile:
            return {"success": False, "error": "No profile configured"}

        await self._fill_field(page, "input[name='name']", settings.USER_NAME)
        await self._fill_field(page, "input[name='email']", settings.USER_EMAIL)
        await self._fill_field(page, "input[name='phone']", profile.phone or "")

        # Resume upload
        if resume and resume.file_path:
            resume_full_path = settings.storage_path / resume.file_path
            if resume_full_path.exists():
                file_input = await page.query_selector("input[type='file']")
                if file_input:
                    await file_input.set_input_files(str(resume_full_path))
                    await asyncio.sleep(2)

        submit_btn = await page.query_selector("button[type='submit'], input[type='submit']")
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(3)
            return {"success": True, "ats": "lever"}

        return {"success": False, "error": "Submit button not found"}

    async def _apply_workday(self, page, job, profile, resume) -> dict:
        """Handle Workday ATS — most complex, requires login."""
        # Workday requires account creation — flag for manual
        return {
            "success": False,
            "error": "Workday requires account creation. Please apply manually.",
            "url": job.source_url,
        }

    async def _apply_generic(self, page, job, profile, resume) -> dict:
        """Generic form filler for unknown ATS systems."""
        await page.goto(job.source_url, wait_until="networkidle")
        await asyncio.sleep(2)

        if not profile:
            return {"success": False, "error": "No profile configured"}

        # Try common field patterns
        field_patterns = [
            ("input[name*='name'], input[placeholder*='name' i]", settings.USER_NAME),
            ("input[name*='email'], input[type='email']", settings.USER_EMAIL),
            ("input[name*='phone'], input[type='tel']", profile.phone or ""),
        ]

        for selector, value in field_patterns:
            if value:
                try:
                    field = await page.query_selector(selector)
                    if field:
                        await field.fill(value)
                except Exception:
                    pass

        # Look for submit
        submit_btn = await page.query_selector(
            "button[type='submit'], input[type='submit'], button:has-text('Apply'), button:has-text('Submit')"
        )
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(3)
            return {"success": True, "ats": "generic"}

        return {"success": False, "error": "No submit button found on generic form"}

    async def _fill_field(self, page, selector: str, value: str) -> None:
        """Safely fill a form field if it exists and is empty."""
        if not value:
            return
        try:
            field = await page.query_selector(selector)
            if field:
                existing = await field.input_value()
                if not existing:
                    await field.fill(value)
        except Exception:
            pass
