"""
app/schemas/__init__.py + all schemas in one file (split into files in production)
────────────────────────────────────────────────────────────────────────────────
Pydantic v2 schemas for every API endpoint.
Naming convention:
  <Model>Base    — shared fields
  <Model>Create  — request body for POST
  <Model>Update  — request body for PATCH (all optional)
  <Model>Out     — response schema (safe, no secrets)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


# ═══════════════════════════════════════════════════════════════════════════
#  SHARED / PAGINATION
# ═══════════════════════════════════════════════════════════════════════════

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: List[Any]


class MessageResponse(BaseModel):
    message: str
    success: bool = True


# ═══════════════════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    user_id: str
    email: str


# ═══════════════════════════════════════════════════════════════════════════
#  USER
# ═══════════════════════════════════════════════════════════════════════════

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=255)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserSkillCreate(BaseModel):
    name: str = Field(max_length=100)
    category: Optional[str] = None
    proficiency: Optional[Literal["beginner", "intermediate", "advanced", "expert"]] = None
    years_experience: Optional[float] = Field(default=None, ge=0, le=50)
    is_primary: bool = False


class UserSkillOut(UserSkillCreate):
    id: str
    user_id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class EducationItem(BaseModel):
    degree: str
    field: str
    institution: str
    year: int
    gpa: Optional[float] = None


class WorkExperienceItem(BaseModel):
    title: str
    company: str
    start: str  # "YYYY-MM"
    end: Optional[str] = None  # None = current
    location: Optional[str] = None
    bullets: List[str] = []


class ProjectItem(BaseModel):
    name: str
    description: str
    tech_stack: List[str] = []
    github: Optional[str] = None
    demo: Optional[str] = None
    highlights: List[str] = []


class UserProfileUpdate(BaseModel):
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    experience_level: Optional[Literal["entry", "mid", "senior"]] = None
    desired_roles: Optional[List[str]] = None
    desired_locations: Optional[List[str]] = None
    open_to_remote: Optional[bool] = None
    open_to_hybrid: Optional[bool] = None
    min_salary: Optional[int] = None
    preferred_company_size: Optional[List[str]] = None
    preferred_industries: Optional[List[str]] = None
    avoid_companies: Optional[List[str]] = None
    professional_summary: Optional[str] = None
    career_goals: Optional[str] = None
    education: Optional[List[EducationItem]] = None
    work_experience: Optional[List[WorkExperienceItem]] = None
    projects: Optional[List[ProjectItem]] = None
    certifications: Optional[List[dict]] = None
    auto_apply_enabled: Optional[bool] = None
    auto_apply_threshold: Optional[int] = Field(default=None, ge=0, le=100)
    auto_apply_daily_limit: Optional[int] = Field(default=None, ge=1, le=50)
    require_apply_approval: Optional[bool] = None
    notify_new_jobs: Optional[bool] = None
    notify_applications: Optional[bool] = None
    notify_interviews: Optional[bool] = None
    notify_via_telegram: Optional[bool] = None
    notify_via_email: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    notification_email: Optional[EmailStr] = None


class UserProfileOut(UserProfileUpdate):
    id: str
    user_id: str
    updated_at: datetime
    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════
#  JOBS
# ═══════════════════════════════════════════════════════════════════════════

class JobFilter(BaseModel):
    source: Optional[str] = None
    job_type: Optional[str] = None
    work_mode: Optional[str] = None
    experience_level: Optional[str] = None
    location: Optional[str] = None
    min_match_score: Optional[float] = Field(default=None, ge=0, le=100)
    company: Optional[str] = None
    keyword: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = True
    posted_after: Optional[datetime] = None
    sort_by: Literal["match_score", "posted_at", "priority_score", "created_at"] = "match_score"
    sort_order: Literal["asc", "desc"] = "desc"


class JobAnalysisOut(BaseModel):
    id: str
    job_id: str
    required_skills: List[str]
    preferred_skills: List[str]
    tech_stack: List[str]
    ats_keywords: List[str]
    min_years_experience: Optional[float]
    max_years_experience: Optional[float]
    education_requirement: Optional[str]
    key_responsibilities: List[str]
    role_category: Optional[str]
    match_score: Optional[float]
    skill_match_score: Optional[float]
    semantic_similarity_score: Optional[float]
    matching_skills: List[str]
    missing_skills: List[str]
    skill_gap_count: int
    estimated_applicants: Optional[int]
    competition_level: Optional[str]
    interview_probability: Optional[float]
    job_difficulty: Optional[str]
    priority_score: Optional[float]
    ai_summary: Optional[str]
    ai_recommendation: Optional[str]
    model_used: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    source: str
    source_url: str
    title: str
    company_name: str
    company_logo_url: Optional[str]
    description_clean: Optional[str]
    location: Optional[str]
    country: Optional[str]
    work_mode: str
    job_type: str
    experience_level: str
    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: Optional[str]
    posted_at: Optional[datetime]
    status: str
    is_active: bool
    applicant_count: Optional[int]
    easy_apply: bool
    scraped_at: datetime
    analysis: Optional[JobAnalysisOut]
    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    """For manual job entry."""
    title: str
    company_name: str
    source_url: str
    description_raw: str
    location: Optional[str] = None
    job_type: str = "full_time"
    work_mode: str = "unknown"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════
#  RESUME
# ═══════════════════════════════════════════════════════════════════════════

class ResumeCreate(BaseModel):
    name: str = Field(max_length=255)
    resume_type: Literal["base", "tailored", "role_variant"] = "base"
    role_category: Optional[str] = None
    content_json: Optional[dict] = None


class ResumeGenerateRequest(BaseModel):
    job_id: str
    tone: Literal["professional", "technical", "concise"] = "professional"
    base_resume_id: Optional[str] = None
    # If None, use the default base resume


class ResumeOut(BaseModel):
    id: str
    user_id: str
    name: str
    version: int
    resume_type: str
    role_category: Optional[str]
    file_path: Optional[str]
    ats_score: Optional[float]
    times_used: int
    response_count: int
    response_rate: Optional[float]
    is_active: bool
    is_default: bool
    keywords_injected: List[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════
#  COVER LETTER
# ═══════════════════════════════════════════════════════════════════════════

class CoverLetterGenerateRequest(BaseModel):
    job_id: str
    tone: Literal["professional", "technical", "enthusiastic", "concise"] = "professional"
    additional_context: Optional[str] = None
    # Extra instructions for the AI


class CoverLetterOut(BaseModel):
    id: str
    job_id: Optional[str]
    content: str
    tone: str
    target_company: Optional[str]
    target_role: Optional[str]
    highlighted_skills: List[str]
    word_count: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════
#  APPLICATIONS
# ═══════════════════════════════════════════════════════════════════════════

class ApplicationCreate(BaseModel):
    job_id: str
    resume_id: Optional[str] = None
    cover_letter_id: Optional[str] = None
    method: Literal["auto_bot", "easy_apply", "manual", "email"] = "auto_bot"
    notes: Optional[str] = None


class ApplicationStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    interview_date: Optional[datetime] = None
    offer_salary: Optional[int] = None


class ApplicationOut(BaseModel):
    id: str
    user_id: str
    job_id: str
    resume_id: Optional[str]
    cover_letter_id: Optional[str]
    status: str
    method: str
    applied_at: Optional[datetime]
    match_score_at_apply: Optional[float]
    job_title_snapshot: Optional[str]
    company_snapshot: Optional[str]
    recruiter_name: Optional[str]
    recruiter_email: Optional[str]
    follow_up_status: str
    follow_up_date: Optional[datetime]
    interview_date: Optional[datetime]
    interview_type: Optional[str]
    offer_salary: Optional[int]
    notes: Optional[str]
    is_starred: bool
    retry_count: int
    created_at: datetime
    job: Optional[JobOut] = None
    model_config = {"from_attributes": True}


class ApplicationStats(BaseModel):
    total_sent: int
    pending_approval: int
    applied: int
    viewed: int
    shortlisted: int
    interviews: int
    offers: int
    rejected: int
    response_rate: float  # (viewed + shortlisted + interviews + offers) / applied
    interview_rate: float
    offer_rate: float


# ═══════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════

class NotificationOut(BaseModel):
    id: str
    channel: str
    status: str
    title: str
    body: str
    event_type: Optional[str]
    sent_at: Optional[datetime]
    read_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════
#  AGENT
# ═══════════════════════════════════════════════════════════════════════════

class AgentTaskOut(BaseModel):
    id: str
    task_type: str
    status: str
    celery_task_id: Optional[str]
    payload: Optional[dict]
    result: Optional[dict]
    error: Optional[str]
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    retry_count: int
    triggered_by: str
    created_at: datetime
    model_config = {"from_attributes": True}


class AgentStatusResponse(BaseModel):
    is_running: bool
    current_task: Optional[str]
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    tasks_today: int
    tasks_succeeded: int
    tasks_failed: int
    jobs_found_today: int
    applications_today: int


class ManualAgentRunRequest(BaseModel):
    task_type: str
    payload: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════════
#  SKILL GAP & MARKET
# ═══════════════════════════════════════════════════════════════════════════

class SkillGapOut(BaseModel):
    id: str
    skill_name: str
    category: Optional[str]
    demand_count: int
    demand_percentage: Optional[float]
    priority: str
    user_has_skill: bool
    learning_plan_generated: bool
    resolved: bool
    model_config = {"from_attributes": True}


class MarketInsightResponse(BaseModel):
    snapshot_date: datetime
    total_jobs_analyzed: int
    top_skills: List[dict]
    top_companies_hiring: List[dict]
    emerging_roles: List[str]
    salary_data: Optional[dict]
    by_work_mode: Optional[dict]


# ═══════════════════════════════════════════════════════════════════════════
#  INTERVIEWS
# ═══════════════════════════════════════════════════════════════════════════

class InterviewOut(BaseModel):
    id: str
    application_id: str
    interview_type: str
    scheduled_at: Optional[datetime]
    duration_minutes: Optional[int]
    platform: Optional[str]
    meeting_link: Optional[str]
    technical_questions: List[dict]
    behavioral_questions: List[dict]
    study_topics: List[str]
    company_report: Optional[dict]
    completed_at: Optional[datetime]
    outcome: Optional[str]
    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════════════
#  CHAT / AI ASSISTANT
# ═══════════════════════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str
    actions_taken: List[str] = []
    # e.g. ["Searched 8 jobs", "Queued 3 applications"]
    data: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════════
#  DASHBOARD / ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════

class DashboardStats(BaseModel):
    # Applications
    applications: ApplicationStats
    # Jobs
    total_jobs_in_db: int
    new_jobs_today: int
    top_match_score: Optional[float]
    # Agent
    agent: AgentStatusResponse
    # Recent activity
    recent_applications: List[ApplicationOut]
    top_jobs: List[JobOut]
