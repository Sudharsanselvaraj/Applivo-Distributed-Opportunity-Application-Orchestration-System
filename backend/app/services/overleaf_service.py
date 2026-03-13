"""
app/services/overleaf_service.py
────────────────────────────────
Module: Overleaf/LaTeX Resume Generator
Generates professional LaTeX resumes that can be copied to Overleaf.
"""

from __future__ import annotations

import structlog
from openai import AsyncOpenAI
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db_context
from app.models.user import User, UserProfile, UserSkill
from app.models.resume import Resume

logger = structlog.get_logger()

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)


class OverleafService:
    """Generate LaTeX resumes for Overleaf."""

    async def generate_latex_resume(self, user_id: str) -> dict:
        """Generate a complete LaTeX resume from user profile data."""
        async with get_db_context() as db:
            # Load user and profile
            user = (await db.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if not user:
                return {"error": "No user found."}

            profile = (await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )).scalar_one_or_none()

            if not profile:
                return {"error": "No profile found. Please set up your profile first."}

            # Load skills
            skills = (await db.execute(
                select(UserSkill).where(UserSkill.user_id == user_id)
            )).scalars().all()

            # Get experience and projects from profile JSON fields
            experiences = profile.work_experience or []
            projects = profile.projects or []

            # Build context for AI
            context = self._build_profile_context(user, profile, skills, experiences, projects)

            # Generate LaTeX using AI
            latex = await self._generate_latex_with_ai(context)

            return {
                "latex": latex,
                "filename": f"{user.full_name.replace(' ', '_')}_resume.tex" if user.full_name else "resume.tex",
                "preview_url": "https://www.overleaf.com/docs?type=project"
            }

    def _build_profile_context(self, user, profile, skills, experiences, projects) -> str:
        """Build a text context from profile data."""
        skills_list = ", ".join([s.name for s in skills]) if skills else "Not specified"
        
        exp_list = []
        for exp in experiences:
            title = exp.get('title', 'Position')
            company = exp.get('company', 'Company')
            start = exp.get('start', 'Date')
            end = exp.get('end', 'Present')
            bullets = exp.get('bullets', [])
            
            exp_list.append(f"- {title} at {company}: {start} to {end}")
            if bullets:
                for bullet in bullets:
                    exp_list.append(f"  • {bullet}")
        exp_text = "\n".join(exp_list) if exp_list else "No experience listed"

        proj_list = []
        for proj in projects:
            name = proj.get('name', 'Project')
            desc = proj.get('description', '')
            tech = proj.get('tech_stack', [])
            
            proj_list.append(f"- {name}: {desc}")
            if tech:
                proj_list.append(f"  Tech: {', '.join(tech)}")
        proj_text = "\n".join(proj_list) if proj_list else "No projects listed"

        return f"""
Profile: {user.full_name or 'N/A'}
Email: {user.email if hasattr(user, 'email') else 'N/A'}
Phone: {profile.phone or 'N/A'}
Location: {profile.location or 'N/A'}
LinkedIn: {profile.linkedin_url or 'N/A'}
GitHub: {profile.github_url or 'N/A'}

Skills: {skills_list}

Experience:
{exp_text}

Projects:
{proj_text}

Education:
{', '.join([e.get('degree', '') + ' ' + e.get('field', '') for e in (profile.education or [])]) or 'Not specified'}
"""

    async def _generate_latex_with_ai(self, context: str) -> str:
        """Generate professional LaTeX resume using AI."""
        prompt = f"""Generate a professional LaTeX resume using the moderncv package.
The resume should be clean, ATS-friendly, and follow best practices.

IMPORTANT: Use the moderncv package with casual or classic style.
Include proper sections: contact info, summary, experience, education, skills, projects.

User Profile Data:
{context}

Return ONLY the LaTeX code (no explanations). Use this template structure:

\\documentclass[11pt,a4paper,sans]{{moderncv}}
\\moderncvstyle{{casual}}
\\moderncvcolor{{blue}}

\\name{{FirstName}}{{LastName}}
\\phone{{Phone Number}}
\\email{{Email}}
\\homepage{{Website}}
\\social[linkedin]{{LinkedIn}}
\\social[github]{{GitHub}}

\\begin{{document}}
\\makecvtitle

\\section{{Summary}}
\\cvitem{{}}{{Your professional summary here}}

\\section{{Experience}}
\\cvitem{{Title}}{{Company}}\\hspace{{\\fill}}\\emph{{Date}}
\\cvitem{{}}{{Description}}

\\section{{Education}}
\\cvitem{{Degree}}{{University}}\\hspace{{\\fill}}\\emph{{Date}}

\\section{{Skills}}
\\cvitem{{}}{{Skill1, Skill2, Skill3}}

\\section{{Projects}}
\\cvitem{{Project Name}}{{Description}}

\\end{{document}}

Now generate the actual LaTeX code with the user's real data filled in:"""

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL_LIGHT,
                max_tokens=2000,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LaTeX generation failed: {e}")
            return f"% Error generating LaTeX: {str(e)}"

    async def analyze_all_resumes(self, user_id: str) -> dict:
        """Analyze all resumes in the user's profile."""
        async with get_db_context() as db:
            # Load all resumes
            resumes = (await db.execute(
                select(Resume).where(Resume.user_id == user_id)
            )).scalars().all()

            if not resumes:
                return {"error": "No resumes found. Please upload a resume first."}

            # Load user profile for context
            profile = (await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )).scalar_one_or_none()

            skills = (await db.execute(
                select(UserSkill).where(UserSkill.user_id == user_id)
            )).scalars().all()

            analysis_results = []

            for resume in resumes:
                # Analyze each resume
                analysis = await self._analyze_resume(resume, profile, skills)
                analysis_results.append({
                    "resume_id": resume.id,
                    "filename": resume.filename,
                    "analysis": analysis
                })

            return {
                "total_resumes": len(resumes),
                "resumes": analysis_results,
                "recommendations": self._generate_recommendations(analysis_results)
            }

    async def _analyze_resume(self, resume: Resume, profile, skills) -> dict:
        """Analyze a single resume."""
        # This is a simplified analysis
        # In production, you'd use AI to parse and analyze the PDF content
        
        analysis = {
            "filename": resume.filename,
            "created_at": resume.created_at.isoformat() if resume.created_at else "Unknown",
            "last_used": resume.times_used if hasattr(resume, 'times_used') else 0,
            "issues": [],
            "suggestions": []
        }

        # Check basic info
        if not resume.filename:
            analysis["issues"].append("Missing filename")

        # Generate suggestions based on profile
        if profile:
            if not profile.full_name:
                analysis["suggestions"].append("Add your full name to the resume")
            if not profile.email:
                analysis["suggestions"].append("Add your email address")
            if not profile.phone:
                analysis["suggestions"].append("Add your phone number")

        # Check skills coverage
        if skills:
            skill_names = [s.name for s in skills]
            if len(skill_names) < 5:
                analysis["suggestions"].append("Add more skills to your profile for better resume matching")

        return analysis

    def _generate_recommendations(self, analysis_results: list) -> dict:
        """Generate overall recommendations."""
        if not analysis_results:
            return {"message": "No resumes to analyze"}

        # Find best resume
        best_resume = max(analysis_results, key=lambda x: len(x["analysis"].get("suggestions", [])) == 0)

        return {
            "best_resume": best_resume["filename"],
            "message": f"'{best_resume['filename']}' appears to be your most complete resume.",
            "action": "Use this resume for job applications or generate a tailored version"
        }
