"""
app/api/routes/jobs.py
───────────────────────
Job discovery, filtering, and analysis endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy import func, select, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.core.database import get_db
from app.api.routes.auth import get_current_user
from app.models.user import User
from app.models.job import Job, JobAnalysis, JobStatus
from app.schemas import JobOut, JobCreate, JobFilter, PaginatedResponse, MessageResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=PaginatedResponse)
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    work_mode: Optional[str] = Query(default=None),
    min_match_score: Optional[float] = Query(default=None, ge=0, le=100),
    keyword: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    sort_by: str = Query(default="match_score"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all jobs with filtering, sorting, and pagination.
    Joins with JobAnalysis to include match scores.
    """
    query = (
        select(Job)
        .outerjoin(JobAnalysis, Job.id == JobAnalysis.job_id)
        .options(selectinload(Job.analysis))
        .where(Job.is_active == True)
    )

    if source:
        query = query.where(Job.source == source)
    if job_type:
        query = query.where(Job.job_type == job_type)
    if work_mode:
        query = query.where(Job.work_mode == work_mode)
    if min_match_score is not None:
        query = query.where(JobAnalysis.match_score >= min_match_score)
    if keyword:
        query = query.where(
            or_(
                Job.title.ilike(f"%{keyword}%"),
                Job.company_name.ilike(f"%{keyword}%"),
                Job.description_clean.ilike(f"%{keyword}%"),
            )
        )
    if status:
        query = query.where(Job.status == status)

    # Sorting
    sort_col_map = {
        "match_score": JobAnalysis.match_score,
        "priority_score": JobAnalysis.priority_score,
        "posted_at": Job.posted_at,
        "created_at": Job.created_at,
    }
    sort_col = sort_col_map.get(sort_by, JobAnalysis.match_score)
    query = query.order_by(desc(sort_col).nulls_last())

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),  # Ceiling division
        items=[JobOut.model_validate(j) for j in jobs],
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Job).options(selectinload(Job.analysis)).where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("", response_model=JobOut, status_code=201)
async def create_job_manual(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add a job (user found it themselves)."""
    from datetime import datetime, timezone
    job = Job(
        source="manual",
        source_job_id=f"manual_{datetime.now(timezone.utc).timestamp()}",
        source_url=payload.source_url,
        title=payload.title,
        company_name=payload.company_name,
        description_raw=payload.description_raw,
        description_clean=payload.description_raw,
        location=payload.location,
        job_type=payload.job_type,
        work_mode=payload.work_mode,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        scraped_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Queue analysis in background
    background_tasks.add_task(_trigger_job_analysis, job.id)
    return job


@router.post("/{job_id}/analyze", response_model=MessageResponse)
async def trigger_analysis(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger AI analysis for a job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")
    background_tasks.add_task(_trigger_job_analysis, job_id)
    return MessageResponse(message=f"Analysis queued for job {job_id}")


@router.post("/{job_id}/skip", response_model=MessageResponse)
async def skip_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a job as skipped so it won't be auto-applied."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = JobStatus.SKIPPED
    await db.commit()
    return MessageResponse(message="Job marked as skipped")


async def _trigger_job_analysis(job_id: str):
    """Background task wrapper — dispatches to Celery."""
    try:
        from app.agents.tasks import analyze_job_task
        analyze_job_task.delay(job_id)
    except Exception as e:
        import structlog
        log = structlog.get_logger()
        log.error("Failed to queue job analysis", job_id=job_id, error=str(e))
