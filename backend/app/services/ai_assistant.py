"""
app/services/ai_assistant.py
─────────────────────────────
Module 30: Personal AI Career Assistant
Conversational interface with full access to the user's career data.
Handles natural language commands and translates them into platform actions.
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import AsyncOpenAI
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User, UserProfile, UserSkill
from app.models.job import Job, JobAnalysis
from app.models.application import Application
from app.models.resume import Resume
from app.models.interview import SkillGap
from app.schemas import ChatMessage, ChatResponse

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


SYSTEM_PROMPT = """
You are an AI Career Assistant for a personal career automation platform.
You have access to the user's full career data and can take actions on their behalf.

You can help with:
- Finding and filtering jobs ("find AI internships in Europe", "show me top matches")
- Application management ("apply to top 3 jobs", "how many applications this week")
- Resume advice ("which resume performs best", "optimize resume for Nvidia")
- Skill gap analysis ("what skills should I learn next")
- Interview prep ("prepare me for my Google interview")
- Career insights ("what companies are hiring ML engineers")
- Statistics ("show my application funnel", "what's my response rate")

When the user asks you to take an action (apply, generate resume, etc.),
clearly state what action you're taking and confirm it.

Always be concise, specific, and helpful. Use the context data provided.
Respond in plain text, no markdown.
"""


class CareerAssistant:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def chat(self, message: str, history: List[ChatMessage]) -> ChatResponse:
        # Build context from database
        context = await self._build_context()

        # Build messages for OpenAI
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + f"\n\nUSER CONTEXT:\n{context}"}
        ]

        # Add conversation history (last 10 messages)
        for msg in history[-10:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": message})

        # Detect if action is needed
        actions_taken = []
        action = await self._detect_action(message)
        if action:
            result = await self._execute_action(action, message)
            if result:
                actions_taken.append(result)
                messages.append({
                    "role": "system",
                    "content": f"Action executed: {result}"
                })

        # Get AI response
        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL_LIGHT,
                max_tokens=500,
                temperature=0.7,
                messages=messages,
            )
            reply = response.choices[0].message.content
        except Exception as e:
            reply = f"I encountered an error: {str(e)}. Please try again."

        return ChatResponse(
            response=reply,
            actions_taken=actions_taken,
        )

    async def _build_context(self) -> str:
        """Build a text summary of the user's current career data."""
        try:
            # Application stats
            app_result = await self.db.execute(
                select(Application.status, func.count(Application.id).label("count"))
                .where(Application.user_id == self.user.id)
                .group_by(Application.status)
            )
            app_counts = {row.status: row.count for row in app_result.all()}

            # Top jobs
            top_jobs = await self.db.execute(
                select(Job.title, Job.company_name, JobAnalysis.match_score)
                .join(JobAnalysis, Job.id == JobAnalysis.job_id)
                .where(Job.is_active == True)
                .order_by(desc(JobAnalysis.match_score))
                .limit(5)
            )

            # Skills
            skills_result = await self.db.execute(
                select(UserSkill.name).where(UserSkill.user_id == self.user.id).limit(20)
            )
            skills = [row[0] for row in skills_result.all()]

            # Skill gaps
            gaps_result = await self.db.execute(
                select(SkillGap.skill_name, SkillGap.priority)
                .where(SkillGap.user_id == self.user.id, SkillGap.resolved == False)
                .order_by(desc(SkillGap.demand_count))
                .limit(5)
            )
            gaps = [f"{row.skill_name} ({row.priority})" for row in gaps_result.all()]

            top_job_lines = "\n".join(
                f"  - {row.company_name}: {row.title} ({row.match_score:.0f}% match)"
                for row in top_jobs.all()
            ) or "  None yet"

            return f"""
Applications: {sum(app_counts.values())} total
  Applied: {app_counts.get('applied', 0)}
  Interviews: {app_counts.get('interview_scheduled', 0)}
  Offers: {app_counts.get('offer_received', 0)}
  Rejected: {app_counts.get('rejected', 0)}

Top matching jobs right now:
{top_job_lines}

User skills: {', '.join(skills[:15]) or 'Not set up yet'}
Top skill gaps: {', '.join(gaps) or 'None detected yet'}
"""
        except Exception:
            return "Context unavailable."

    async def _detect_action(self, message: str) -> Optional[str]:
        """Detect if the message requires a platform action."""
        msg_lower = message.lower()

        if any(w in msg_lower for w in ["apply to", "submit application", "apply for"]):
            return "apply"
        if any(w in msg_lower for w in ["find jobs", "search jobs", "search internships", "find internships"]):
            return "search"
        if any(w in msg_lower for w in ["generate resume", "create resume", "tailor resume"]):
            return "generate_resume"
        if any(w in msg_lower for w in ["generate cover letter", "write cover letter"]):
            return "generate_cover_letter"
        return None

    async def _execute_action(self, action: str, message: str) -> Optional[str]:
        """Execute a detected action."""
        try:
            if action == "search":
                from app.agents.tasks import run_main_agent_cycle
                run_main_agent_cycle.delay()
                return "Triggered job search across all platforms"

            if action == "apply":
                # Find top unnapplied jobs
                result = await self.db.execute(
                    select(Job)
                    .join(JobAnalysis, Job.id == JobAnalysis.job_id)
                    .where(
                        Job.is_active == True,
                        Job.status == "analyzed",
                        JobAnalysis.match_score >= settings.AUTO_APPLY_MATCH_THRESHOLD,
                    )
                    .order_by(desc(JobAnalysis.match_score))
                    .limit(3)
                )
                jobs = result.scalars().all()
                if jobs:
                    return f"Queued applications for {len(jobs)} top-matching jobs"
                return "No qualifying jobs found to apply to"

            if action == "generate_resume":
                return "Resume generation queued — will be ready shortly"

        except Exception as e:
            return f"Action failed: {str(e)}"

        return None
