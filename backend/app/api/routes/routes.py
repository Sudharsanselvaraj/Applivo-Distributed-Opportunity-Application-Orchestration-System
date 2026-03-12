"""
app/api/routes/applications.py  — Application tracking
app/api/routes/resumes.py       — Resume version control
app/api/routes/agent.py         — Agent control panel
app/api/routes/analytics.py     — Dashboard stats
app/api/routes/chat.py          — AI assistant
"""

# ═══════════════════════════════════════════════════════════════════════════
#  applications.py
# ═══════════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, timezone

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.models.application import Application, ApplicationEvent, ApplicationStatus
from app.models.job import Job
from app.schemas import (
    ApplicationCreate, ApplicationOut, ApplicationStatusUpdate,
    ApplicationStats, MessageResponse, PaginatedResponse
)

applications_router = APIRouter(prefix="/applications", tags=["Applications"])


@applications_router.get("", response_model=PaginatedResponse)
async def list_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    is_starred: Optional[bool] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Application)
        .options(selectinload(Application.job).selectinload(Job.analysis))
        .where(Application.user_id == current_user.id)
        .order_by(desc(Application.created_at))
    )
    if status:
        query = query.where(Application.status == status)
    if is_starred is not None:
        query = query.where(Application.is_starred == is_starred)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    apps = result.scalars().all()

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        pages=-(-total // page_size),
        items=[ApplicationOut.model_validate(a) for a in apps],
    )


@applications_router.get("/stats", response_model=ApplicationStats)
async def get_application_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard statistics for the application funnel."""
    result = await db.execute(
        select(Application.status, func.count(Application.id).label("count"))
        .where(Application.user_id == current_user.id)
        .group_by(Application.status)
    )
    counts = {row.status: row.count for row in result.all()}

    applied = counts.get(ApplicationStatus.APPLIED, 0)
    viewed = counts.get(ApplicationStatus.VIEWED, 0)
    shortlisted = counts.get(ApplicationStatus.SHORTLISTED, 0)
    interviews = counts.get(ApplicationStatus.INTERVIEW_SCHEDULED, 0) + \
                 counts.get(ApplicationStatus.INTERVIEW_COMPLETED, 0)
    offers = counts.get(ApplicationStatus.OFFER_RECEIVED, 0) + \
             counts.get(ApplicationStatus.OFFER_ACCEPTED, 0)
    rejected = counts.get(ApplicationStatus.REJECTED, 0)

    total_sent = applied + viewed + shortlisted + interviews + offers + rejected
    positive = viewed + shortlisted + interviews + offers

    return ApplicationStats(
        total_sent=total_sent,
        pending_approval=counts.get(ApplicationStatus.PENDING_APPROVAL, 0),
        applied=applied,
        viewed=viewed,
        shortlisted=shortlisted,
        interviews=interviews,
        offers=offers,
        rejected=rejected,
        response_rate=round(positive / applied * 100, 1) if applied > 0 else 0.0,
        interview_rate=round(interviews / applied * 100, 1) if applied > 0 else 0.0,
        offer_rate=round(offers / applied * 100, 1) if applied > 0 else 0.0,
    )


@applications_router.get("/{app_id}", response_model=ApplicationOut)
async def get_application(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.job).selectinload(Job.analysis))
        .where(Application.id == app_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@applications_router.post("", response_model=ApplicationOut, status_code=201)
async def create_application(
    payload: ApplicationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a new application (manual or bot-assisted)."""
    # Verify job exists
    job_result = await db.execute(select(Job).where(Job.id == payload.job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    app = Application(
        user_id=current_user.id,
        job_id=payload.job_id,
        resume_id=payload.resume_id,
        cover_letter_id=payload.cover_letter_id,
        method=payload.method,
        notes=payload.notes,
        job_title_snapshot=job.title,
        company_snapshot=job.company_name,
        status=ApplicationStatus.PENDING_APPROVAL if
            payload.method == "auto_bot" else ApplicationStatus.APPLIED,
    )
    db.add(app)
    await db.flush()

    # Log creation event
    event = ApplicationEvent(
        application_id=app.id,
        event_type="application_created",
        to_status=app.status,
        triggered_by="user",
        details={"method": payload.method},
    )
    db.add(event)
    await db.commit()
    await db.refresh(app)

    # Trigger auto-apply bot if approved
    if payload.method == "auto_bot" and not current_user.profile.require_apply_approval:
        background_tasks.add_task(_trigger_auto_apply, app.id)

    return app


@applications_router.patch("/{app_id}/status", response_model=ApplicationOut)
async def update_application_status(
    app_id: str,
    payload: ApplicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Application).where(Application.id == app_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    old_status = app.status
    app.status = payload.status
    if payload.notes:
        app.notes = payload.notes
    if payload.recruiter_name:
        app.recruiter_name = payload.recruiter_name
    if payload.recruiter_email:
        app.recruiter_email = payload.recruiter_email
    if payload.interview_date:
        app.interview_date = payload.interview_date
    if payload.offer_salary:
        app.offer_salary = payload.offer_salary

    # Auto-set timestamps
    now = datetime.now(timezone.utc)
    status_timestamps = {
        "applied": "applied_at",
        "viewed": "viewed_at",
        "shortlisted": "shortlisted_at",
        "interview_scheduled": "interview_scheduled_at",
        "rejected": "rejected_at",
    }
    if payload.status in status_timestamps:
        setattr(app, status_timestamps[payload.status], now)

    # Log event
    event = ApplicationEvent(
        application_id=app.id,
        event_type="status_changed",
        from_status=old_status,
        to_status=payload.status,
        triggered_by="user",
    )
    db.add(event)
    await db.commit()
    await db.refresh(app)
    return app


@applications_router.post("/{app_id}/approve", response_model=MessageResponse)
async def approve_application(
    app_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a pending application — triggers the auto-apply bot."""
    result = await db.execute(
        select(Application).where(Application.id == app_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status != ApplicationStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail=f"Application is not pending approval (current: {app.status})")

    app.status = ApplicationStatus.QUEUED
    db.add(ApplicationEvent(
        application_id=app.id,
        event_type="status_changed",
        from_status=ApplicationStatus.PENDING_APPROVAL,
        to_status=ApplicationStatus.QUEUED,
        triggered_by="user",
        details={"action": "approved"},
    ))
    await db.commit()
    background_tasks.add_task(_trigger_auto_apply, app.id)
    return MessageResponse(message="Application approved and queued for bot")


@applications_router.patch("/{app_id}/star", response_model=ApplicationOut)
async def toggle_star(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Application).where(Application.id == app_id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.is_starred = not app.is_starred
    await db.commit()
    await db.refresh(app)
    return app


async def _trigger_auto_apply(application_id: str):
    try:
        from app.agents.tasks import auto_apply_task
        auto_apply_task.delay(application_id)
    except Exception as e:
        import structlog
        structlog.get_logger().error("Failed to queue auto-apply", app_id=application_id, error=str(e))


# ═══════════════════════════════════════════════════════════════════════════
#  resumes.py
# ═══════════════════════════════════════════════════════════════════════════

resumes_router = APIRouter(prefix="/resumes", tags=["Resumes"])

from app.models.resume import Resume, CoverLetter
from app.schemas import ResumeOut, CoverLetterOut, ResumeGenerateRequest, CoverLetterGenerateRequest
import aiofiles
from fastapi import UploadFile, File
from pathlib import Path


@resumes_router.get("", response_model=List[ResumeOut])
async def list_resumes(
    is_active: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == current_user.id, Resume.is_active == is_active)
        .order_by(desc(Resume.created_at))
    )
    return result.scalars().all()


@resumes_router.post("/upload", response_model=ResumeOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    name: str = Query(...),
    resume_type: str = Query(default="base"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a PDF resume file."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    from app.core.config import settings
    import uuid
    file_name = f"{uuid.uuid4()}.pdf"
    file_path = settings.resumes_path / file_name

    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    resume = Resume(
        user_id=current_user.id,
        name=name,
        resume_type=resume_type,
        file_path=str(file_path.relative_to(settings.storage_path)),
        file_size_bytes=len(content),
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return resume


@resumes_router.post("/generate", response_model=ResumeOut, status_code=201)
async def generate_tailored_resume(
    payload: ResumeGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI-generate a tailored resume for a specific job."""
    background_tasks.add_task(_trigger_resume_generation, current_user.id, payload.job_id, payload.base_resume_id)
    return MessageResponse(message="Resume generation queued")


@resumes_router.patch("/{resume_id}/set-default", response_model=ResumeOut)
async def set_default_resume(
    resume_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Unset all defaults first
    result = await db.execute(select(Resume).where(Resume.user_id == current_user.id, Resume.is_default == True))
    for r in result.scalars().all():
        r.is_default = False

    result = await db.execute(select(Resume).where(Resume.id == resume_id, Resume.user_id == current_user.id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    resume.is_default = True
    await db.commit()
    await db.refresh(resume)
    return resume


async def _trigger_resume_generation(user_id: str, job_id: str, base_resume_id: Optional[str]):
    try:
        from app.agents.tasks import generate_resume_task
        generate_resume_task.delay(user_id, job_id, base_resume_id)
    except Exception as e:
        import structlog
        structlog.get_logger().error("Failed to queue resume gen", error=str(e))


# ── Cover Letters ────────────────────────────────────────────────────────────

cover_letters_router = APIRouter(prefix="/cover-letters", tags=["Cover Letters"])


@cover_letters_router.post("/generate", response_model=CoverLetterOut, status_code=201)
async def generate_cover_letter(
    payload: CoverLetterGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    background_tasks.add_task(_trigger_cover_letter_gen, current_user.id, payload.job_id, payload.tone)
    return MessageResponse(message="Cover letter generation queued")


@cover_letters_router.get("", response_model=List[CoverLetterOut])
async def list_cover_letters(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CoverLetter)
        .where(CoverLetter.user_id == current_user.id)
        .order_by(desc(CoverLetter.created_at))
    )
    return result.scalars().all()


async def _trigger_cover_letter_gen(user_id: str, job_id: str, tone: str):
    try:
        from app.agents.tasks import generate_cover_letter_task
        generate_cover_letter_task.delay(user_id, job_id, tone)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  agent.py — Agent control panel
# ═══════════════════════════════════════════════════════════════════════════

agent_router = APIRouter(prefix="/agent", tags=["Agent"])

from app.models.interview import AgentTask, AgentTaskStatus
from app.schemas import AgentTaskOut, AgentStatusResponse, ManualAgentRunRequest


@agent_router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current background agent status."""
    from datetime import date
    today = datetime.now(timezone.utc).date()

    result = await db.execute(
        select(AgentTask)
        .where(func.date(AgentTask.created_at) == today)
        .order_by(desc(AgentTask.created_at))
    )
    tasks_today = result.scalars().all()

    running = [t for t in tasks_today if t.status == AgentTaskStatus.RUNNING]
    succeeded = [t for t in tasks_today if t.status == AgentTaskStatus.SUCCESS]
    failed = [t for t in tasks_today if t.status == AgentTaskStatus.FAILED]

    # Jobs found today
    from app.models.job import Job
    from sqlalchemy import cast, Date
    jobs_today = (await db.execute(
        select(func.count(Job.id)).where(func.date(Job.scraped_at) == today)
    )).scalar()

    # Applications today
    apps_today = (await db.execute(
        select(func.count(Application.id))
        .where(
            Application.user_id == current_user.id,
            func.date(Application.applied_at) == today,
        )
    )).scalar()

    last_task = tasks_today[0] if tasks_today else None

    return AgentStatusResponse(
        is_running=len(running) > 0,
        current_task=running[0].task_type if running else None,
        last_run_at=last_task.created_at if last_task else None,
        next_run_at=None,  # Populated by scheduler
        tasks_today=len(tasks_today),
        tasks_succeeded=len(succeeded),
        tasks_failed=len(failed),
        jobs_found_today=jobs_today or 0,
        applications_today=apps_today or 0,
    )


@agent_router.get("/tasks", response_model=List[AgentTaskOut])
async def list_agent_tasks(
    limit: int = Query(default=50, le=200),
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(AgentTask).order_by(desc(AgentTask.created_at)).limit(limit)
    if status:
        query = query.where(AgentTask.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@agent_router.post("/run", response_model=MessageResponse)
async def trigger_agent_manually(
    payload: ManualAgentRunRequest,
    current_user: User = Depends(get_current_user),
):
    """Manually trigger an agent task (e.g. run scraper now)."""
    try:
        from app.agents.tasks import TASK_REGISTRY
        task_fn = TASK_REGISTRY.get(payload.task_type)
        if not task_fn:
            raise HTTPException(status_code=400, detail=f"Unknown task type: {payload.task_type}")
        task_fn.delay(**(payload.payload or {}))
        return MessageResponse(message=f"Task '{payload.task_type}' triggered")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.post("/pause", response_model=MessageResponse)
async def pause_agent(current_user: User = Depends(get_current_user)):
    """Pause background automation."""
    # In production: update Redis key that worker checks
    return MessageResponse(message="Agent paused")


@agent_router.post("/resume", response_model=MessageResponse)
async def resume_agent(current_user: User = Depends(get_current_user)):
    """Resume background automation."""
    return MessageResponse(message="Agent resumed")


# ═══════════════════════════════════════════════════════════════════════════
#  chat.py — AI Career Assistant
# ═══════════════════════════════════════════════════════════════════════════

chat_router = APIRouter(prefix="/chat", tags=["AI Assistant"])

from app.schemas import ChatRequest, ChatResponse


@chat_router.post("", response_model=ChatResponse)
async def chat_with_assistant(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Conversational AI assistant with access to the user's career data.
    Handles natural language commands like:
    - "Find AI internships in Europe"
    - "Apply to the top 3 jobs"
    - "What skills should I learn next?"
    - "How many applications did I send this week?"
    """
    from app.services.ai_assistant import CareerAssistant
    assistant = CareerAssistant(db=db, user=current_user)
    response = await assistant.chat(
        message=payload.message,
        history=payload.conversation_history,
    )
    return response


# ═══════════════════════════════════════════════════════════════════════════
#  analytics.py
# ═══════════════════════════════════════════════════════════════════════════

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])

from app.schemas import DashboardStats, MarketInsightResponse
from app.models.interview import MarketSnapshot, SkillGap
from app.schemas import SkillGapOut


@analytics_router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full dashboard data in a single API call."""
    from app.schemas import ApplicationStats

    # Application stats
    app_result = await db.execute(
        select(Application.status, func.count(Application.id).label("count"))
        .where(Application.user_id == current_user.id)
        .group_by(Application.status)
    )
    counts = {row.status: row.count for row in app_result.all()}
    applied = counts.get("applied", 0)
    interviews = counts.get("interview_scheduled", 0) + counts.get("interview_completed", 0)
    offers = counts.get("offer_received", 0) + counts.get("offer_accepted", 0)
    total_positive = counts.get("viewed", 0) + counts.get("shortlisted", 0) + interviews + offers

    app_stats = ApplicationStats(
        total_sent=sum(counts.values()),
        pending_approval=counts.get("pending_approval", 0),
        applied=applied,
        viewed=counts.get("viewed", 0),
        shortlisted=counts.get("shortlisted", 0),
        interviews=interviews,
        offers=offers,
        rejected=counts.get("rejected", 0),
        response_rate=round(total_positive / applied * 100, 1) if applied else 0.0,
        interview_rate=round(interviews / applied * 100, 1) if applied else 0.0,
        offer_rate=round(offers / applied * 100, 1) if applied else 0.0,
    )

    # Job stats
    today = datetime.now(timezone.utc).date()
    total_jobs = (await db.execute(select(func.count(Job.id)))).scalar()
    jobs_today = (await db.execute(
        select(func.count(Job.id)).where(func.date(Job.scraped_at) == today)
    )).scalar()
    top_score = (await db.execute(select(func.max(JobAnalysis.match_score)))).scalar()

    # Top jobs
    top_jobs_result = await db.execute(
        select(Job).options(selectinload(Job.analysis))
        .outerjoin(JobAnalysis)
        .where(Job.is_active == True, JobAnalysis.match_score.isnot(None))
        .order_by(desc(JobAnalysis.match_score))
        .limit(5)
    )

    # Recent applications
    recent_apps_result = await db.execute(
        select(Application)
        .options(selectinload(Application.job).selectinload(Job.analysis))
        .where(Application.user_id == current_user.id)
        .order_by(desc(Application.created_at))
        .limit(5)
    )

    # Agent status (reuse)
    agent_status_result = await get_agent_status(db=db, current_user=current_user)

    return DashboardStats(
        applications=app_stats,
        total_jobs_in_db=total_jobs or 0,
        new_jobs_today=jobs_today or 0,
        top_match_score=top_score,
        agent=agent_status_result,
        recent_applications=[ApplicationOut.model_validate(a) for a in recent_apps_result.scalars().all()],
        top_jobs=[JobOut.model_validate(j) for j in top_jobs_result.scalars().all()],
    )


@analytics_router.get("/skill-gaps", response_model=List[SkillGapOut])
async def get_skill_gaps(
    resolved: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SkillGap)
        .where(SkillGap.user_id == current_user.id, SkillGap.resolved == resolved)
        .order_by(desc(SkillGap.demand_count))
    )
    return result.scalars().all()


@analytics_router.get("/market", response_model=MarketInsightResponse)
async def get_market_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Latest job market intelligence snapshot."""
    result = await db.execute(
        select(MarketSnapshot).order_by(desc(MarketSnapshot.snapshot_date)).limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No market data available yet. Run the agent first.")
    return MarketInsightResponse(
        snapshot_date=snapshot.snapshot_date,
        total_jobs_analyzed=snapshot.total_jobs_analyzed,
        top_skills=snapshot.top_skills,
        top_companies_hiring=snapshot.top_companies_hiring,
        emerging_roles=snapshot.emerging_roles,
        salary_data=snapshot.salary_data,
        by_work_mode=snapshot.by_work_mode,
    )


@analytics_router.get("/resume-performance")
async def get_resume_performance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Which resume versions are getting the most responses."""
    from app.models.resume import Resume
    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == current_user.id, Resume.times_used > 0)
        .order_by(desc(Resume.response_rate))
    )
    resumes = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "version": r.version,
            "times_used": r.times_used,
            "response_count": r.response_count,
            "response_rate": r.response_rate,
            "ats_score": r.ats_score,
        }
        for r in resumes
    ]
