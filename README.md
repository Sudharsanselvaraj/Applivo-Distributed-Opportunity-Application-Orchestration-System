<div align="center">

# D.A.O.I.S.A.O.S

### Distributed Autonomous Opportunity Intelligence  
### and Strategic Application Orchestration System

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Playwright](https://img.shields.io/badge/Playwright-1.44-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5-FF6F00?style=for-the-badge)](https://trychroma.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

A personal AI career automation platform that autonomously discovers job opportunities, generates tailored application materials, submits applications through browser automation, tracks the full application lifecycle, and orchestrates interview preparation — all through a distributed background agent system.

[Overview](#overview) · [System Architecture](#system-architecture) · [Agent Pipeline](#agent-pipeline) · [Core Modules](#core-modules) · [Data Models](#data-models) · [Quick Start](#quick-start) · [Configuration](#configuration) · [API Reference](#api-reference) · [Automation Schedule](#automation-schedule) · [Project Structure](#project-structure) · [Tech Stack](#tech-stack) · [Security](#security) · [Roadmap](#roadmap)

</div>

---

## Overview

D.A.O.I.S.A.O.S is a **distributed, AI-powered career automation platform** built for single-user personal deployment. It operates entirely in the background — continuously scraping job boards across multiple platforms, scoring each opportunity against your career profile using a dual-model LLM pipeline, generating ATS-optimised resumes and cover letters, submitting applications through a Playwright browser agent, and delivering real-time notifications via Telegram and email.

The system is designed around three core principles:

**Autonomy** — The platform runs on a self-scheduling Celery Beat loop. Once configured, it discovers, analyses, generates, and applies without manual intervention. Every decision point (scrape, score, generate, submit) is logged as an auditable `AgentTask` record.

**Intelligence** — Two OpenAI models operate in tandem. `GPT-4o-mini` handles high-volume, low-cost operations: batch job filtering, match scoring, and chat responses. `GPT-4o` is reserved for deep, high-value work: full job description analysis, resume tailoring, cover letter generation, and interview preparation. A ChromaDB vector store holds semantic embeddings of your profile, past applications, and recruiter interactions, enabling RAG-based personalisation across all AI calls.

**Safety** — Auto-apply is disabled by default. When enabled, every application first passes through a configurable human-in-the-loop gate: a Telegram notification is sent to the user, and the bot waits for explicit approval before submitting. A daily application limit and minimum match-score threshold provide additional safeguards.

---

## System Architecture

```
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║                         PRESENTATION LAYER                              ║
  ║                                                                          ║
  ║   ┌─────────────────────────────────────────────────────────────────┐   ║
  ║   │               Next.js Frontend (TailwindCSS)                    │   ║
  ║   │                                                                  │   ║
  ║   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐  │   ║
  ║   │  │ Job Feed │ │ Resumes  │ │  Tracker │ │Interview │ │ Chat │  │   ║
  ║   │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────┘  │   ║
  ║   └─────────────────────────┬───────────────────────────────────────┘   ║
  ║                             │  HTTPS / JWT Bearer                        ║
  ╚═════════════════════════════╪════════════════════════════════════════════╝
                                │
  ╔═════════════════════════════╪════════════════════════════════════════════╗
  ║                      APPLICATION LAYER                                   ║
  ║                             │                                            ║
  ║   ┌─────────────────────────▼───────────────────────────────────────┐   ║
  ║   │                    FastAPI  (Uvicorn)                            │   ║
  ║   │                                                                  │   ║
  ║   │  /auth    /jobs    /applications    /resumes    /cover-letters   │   ║
  ║   │  /agent   /analytics               /chat                        │   ║
  ║   └──────┬──────────────────────────────────────┬───────────────────┘   ║
  ║          │ SQLAlchemy (asyncpg)                  │ Celery .delay()        ║
  ╚══════════╪══════════════════════════════════════╪════════════════════════╝
             │                                      │
  ╔══════════╪══════════════╗    ╔══════════════════╪════════════════════════╗
  ║   DATA LAYER            ║    ║          WORKER LAYER                     ║
  ║          │              ║    ║                  │                         ║
  ║   ┌──────▼──────┐       ║    ║   ┌──────────────▼──────────────────┐    ║
  ║   │ PostgreSQL  │       ║    ║   │        Celery Workers            │    ║
  ║   │             │       ║    ║   │                                  │    ║
  ║   │  users      │       ║    ║   │  queue: scraping                 │    ║
  ║   │  jobs       │       ║    ║   │    LinkedIn · Indeed             │    ║
  ║   │  job_       │       ║    ║   │    Internshala · Wellfound       │    ║
  ║   │  analyses   │       ║    ║   │                                  │    ║
  ║   │  resumes    │       ║    ║   │  queue: ai                       │    ║
  ║   │  cover_     │       ║    ║   │    Job analysis · Scoring        │    ║
  ║   │  letters    │       ║    ║   │    Resume gen · Cover letters    │    ║
  ║   │  applications│      ║    ║   │                                  │    ║
  ║   │  interviews │       ║    ║   │  queue: automation               │    ║
  ║   │  agent_     │       ║    ║   │    Playwright apply bot          │    ║
  ║   │  tasks      │       ║    ║   │    Form fill · Submit            │    ║
  ║   └─────────────┘       ║    ║   │                                  │    ║
  ║                         ║    ║   │  queue: notifications            │    ║
  ║   ┌─────────────┐       ║    ║   │    Telegram · SMTP email         │    ║
  ║   │  ChromaDB   │       ║    ║   └────────────────┬─────────────────┘   ║
  ║   │             │       ║    ║                    │                      ║
  ║   │  user_      │       ║    ║   ┌────────────────▼─────────────────┐   ║
  ║   │  profile    │       ║    ║   │           Redis 7                │   ║
  ║   │  jobs       │       ║    ║   │   Broker (db 0) · Backend (db 1) │   ║
  ║   │  resumes    │       ║    ║   └──────────────────────────────────┘   ║
  ║   └─────────────┘       ║    ╚════════════════════════════════════════════╝
  ╚═════════════════════════╝
                                   ╔════════════════════════════════════════╗
                                   ║          EXTERNAL SERVICES             ║
                                   ║                                        ║
                                   ║  ┌──────────────────────────────────┐  ║
                                   ║  │          OpenAI API              │  ║
                                   ║  │  GPT-4o        → deep analysis   │  ║
                                   ║  │  GPT-4o-mini   → batch scoring   │  ║
                                   ║  │  text-embed-3s → embeddings      │  ║
                                   ║  │  Whisper       → audio analysis  │  ║
                                   ║  └──────────────────────────────────┘  ║
                                   ║  ┌──────────────────────────────────┐  ║
                                   ║  │       Notification Channels      │  ║
                                   ║  │  Telegram Bot API                │  ║
                                   ║  │  SMTP (Gmail / custom)           │  ║
                                   ║  └──────────────────────────────────┘  ║
                                   ║  ┌──────────────────────────────────┐  ║
                                   ║  │         Job Platforms            │  ║
                                   ║  │  LinkedIn · Indeed · Internshala │  ║
                                   ║  │  Wellfound · Glassdoor           │  ║
                                   ║  └──────────────────────────────────┘  ║
                                   ╚════════════════════════════════════════╝
```

---

## Agent Pipeline

The central automation cycle executes every 6 hours via `run_main_agent_cycle`. Each stage is a discrete Celery task, routed to a purpose-specific queue, with full `AgentTask` audit logging and exponential-backoff retry on failure.

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    MAIN AGENT CYCLE  (every 6 hours)                    │
  └─────────────────────────────────────────────────────────────────────────┘

  STAGE 1: JOB DISCOVERY                          queue: scraping
  ┌──────────────────────────────────────────────────────────────────────┐
  │                                                                      │
  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐ │
  │  │   LinkedIn   │  │    Indeed    │  │  Internshala │  │Wellfound│ │
  │  │   Scraper    │  │   Scraper    │  │   Scraper    │  │ Scraper │ │
  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬────┘ │
  │         │                 │                  │               │      │
  │         └─────────────────┴──────────────────┴───────────────┘      │
  │                                     │                                │
  │                            ScrapedJob objects                        │
  │                    (deduplication by source_job_id)                  │
  │                                     │                                │
  │                             Save NEW jobs to DB                      │
  │                        (status = NEW, raw HTML stored)               │
  └─────────────────────────────────────┬────────────────────────────────┘
                                        │
  STAGE 2: AI ANALYSIS & SCORING                  queue: ai
  ┌─────────────────────────────────────▼────────────────────────────────┐
  │                                                                      │
  │   PASS 1 — Batch filter with GPT-4o-mini  (cheap, fast)              │
  │   ┌────────────────────────────────────────────────────────────┐     │
  │   │  For every NEW job:                                        │     │
  │   │  Score against USER_DESIRED_ROLES, USER_EXPERIENCE_LEVEL  │     │
  │   │  Jobs below threshold  → status = SKIPPED                 │     │
  │   │  Jobs above threshold  → advance to Pass 2                │     │
  │   └────────────────────────────────────────────────────────────┘     │
  │                                                                      │
  │   PASS 2 — Deep analysis with GPT-4o  (high-value candidates only)   │
  │   ┌────────────────────────────────────────────────────────────┐     │
  │   │  Extract:  required_skills, preferred_skills, tech_stack   │     │
  │   │            ats_keywords, min_years_experience              │     │
  │   │            role_category, seniority_detected               │     │
  │   │            estimated_salary_min/max, job_difficulty        │     │
  │   │                                                            │     │
  │   │  Compute:  match_score (0-100) vs user profile             │     │
  │   │            priority_score (match + recency + competition)  │     │
  │   │            skill_gaps (required skills user lacks)         │     │
  │   │            ai_recommendation (apply / skip / consider)     │     │
  │   │                                                            │     │
  │   │  Persist:  JobAnalysis record  (status = ANALYZED)         │     │
  │   └────────────────────────────────────────────────────────────┘     │
  └─────────────────────────────────────┬────────────────────────────────┘
                                        │
                                        │  Jobs with match_score >= AUTO_APPLY_MATCH_THRESHOLD
                                        │
  STAGE 3: MATERIAL GENERATION                    queue: ai
  ┌─────────────────────────────────────▼────────────────────────────────┐
  │                                                                      │
  │   For each qualifying job, in parallel:                              │
  │                                                                      │
  │   ┌──────────────────────────┐   ┌──────────────────────────────┐   │
  │   │    Resume Generation     │   │   Cover Letter Generation    │   │
  │   │                          │   │                              │   │
  │   │  Load base resume        │   │  Load company context        │   │
  │   │  Load JobAnalysis        │   │  Load JobAnalysis            │   │
  │   │  GPT-4o rewrites:        │   │  GPT-4o generates:           │   │
  │   │  - Professional summary  │   │  - Opening paragraph         │   │
  │   │  - Experience bullets    │   │  - Skills alignment          │   │
  │   │  - Project bullets       │   │  - Company-specific closing  │   │
  │   │  - Skills to highlight   │   │                              │   │
  │   │  - Inject ATS keywords   │   │  Tone: professional / tech   │   │
  │   │  - Estimate ATS score    │   │  Stored as versioned record  │   │
  │   │  Render to PDF           │   │  Attached to Application     │   │
  │   │  Stored in /storage/     │   │                              │   │
  │   └──────────────────────────┘   └──────────────────────────────┘   │
  │                                                                      │
  └─────────────────────────────────────┬────────────────────────────────┘
                                        │
  STAGE 4: AUTO-APPLY                             queue: automation
  ┌─────────────────────────────────────▼────────────────────────────────┐
  │                                                                      │
  │   Respects: AUTO_APPLY_DAILY_LIMIT · AUTO_APPLY_MATCH_THRESHOLD      │
  │                                                                      │
  │   ┌─────────────────────────────────────────────────────────────┐   │
  │   │  IF AUTO_APPLY_REQUIRE_APPROVAL = true                      │   │
  │   │                                                             │   │
  │   │  Send Telegram notification with job details + match score  │   │
  │   │  Application status = PENDING_APPROVAL                      │   │
  │   │  Wait for user reply: Approve / Skip                        │   │
  │   │  On approval → status = QUEUED → Playwright bot runs        │   │
  │   └─────────────────────────────────────────────────────────────┘   │
  │                                                                      │
  │   Playwright Apply Bot:                                              │
  │                                                                      │
  │   Detect ATS platform:                                               │
  │   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
  │   │  Workday   │ │ Greenhouse │ │   Lever    │ │  LinkedIn  │      │
  │   │myworkday.. │ │greenhouse. │ │  lever.co  │ │ Easy Apply │      │
  │   └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
  │   ┌────────────┐ ┌────────────┐                                     │
  │   │ Internshala│ │   Indeed   │                                     │
  │   └────────────┘ └────────────┘                                     │
  │                                                                      │
  │   Fill form → Upload resume PDF → Attach cover letter               │
  │   → Answer standard questions → Submit                              │
  │   → On CAPTCHA: pause, notify user via Telegram, await resolution   │
  │                                                                      │
  └─────────────────────────────────────┬────────────────────────────────┘
                                        │
  STAGE 5: TRACKING & NOTIFICATIONS              queue: notifications
  ┌─────────────────────────────────────▼────────────────────────────────┐
  │                                                                      │
  │  Update application status in DB                                     │
  │  Log ApplicationEvent (every state transition is audited)            │
  │  Send Telegram + Email digest of cycle results                       │
  │                                                                      │
  └──────────────────────────────────────────────────────────────────────┘
```

---

## Application Lifecycle State Machine

Every application passes through a well-defined state machine. Every transition is recorded as an `ApplicationEvent` with a timestamp, trigger source (`agent` or `user`), and optional notes — providing a full audit trail.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │              APPLICATION STATUS STATE MACHINE                        │
  └──────────────────────────────────────────────────────────────────────┘

                           Job matched by AI
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │    PENDING_APPROVAL     │  ◄── requires_approval = true
                     │  Awaiting Telegram      │
                     │  user confirmation      │
                     └───────────┬────────────┘
                User approves    │    User skips
                    ┌────────────┘                └──────► SKIPPED
                    ▼
            ┌───────────────┐
            │    QUEUED     │  ◄── Added to Celery automation queue
            └───────┬───────┘
                    │  Bot picks up task
                    ▼
            ┌───────────────┐
            │   APPLYING    │  ◄── Playwright is filling the form
            └───────┬───────┘
         Success    │    Bot error / CAPTCHA
         ┌──────────┘         └──────────────────► FAILED (retry up to 3x)
         ▼
  ┌─────────────┐
  │   APPLIED   │  ◄── Application submitted successfully
  └──────┬──────┘
         │
         │  Recruiter opens application
         ▼
  ┌─────────────┐
  │   VIEWED    │
  └──────┬──────┘
         │                          │
         │  Shortlisted             │  Not progressed
         ▼                          ▼
  ┌──────────────┐          ┌──────────────┐
  │ SHORTLISTED  │          │   REJECTED   │
  └──────┬───────┘          └──────────────┘
         │
         │  Interview scheduled
         ▼
  ┌──────────────────────┐
  │  INTERVIEW_SCHEDULED │
  └──────────┬───────────┘
             │  Interview held
             ▼
  ┌──────────────────────┐
  │  INTERVIEW_COMPLETED │
  └──────────┬───────────┘
             │                       │
             │  Offer extended        │  Rejected post-interview
             ▼                       ▼
  ┌──────────────────────┐   ┌──────────────┐
  │    OFFER_RECEIVED    │   │   REJECTED   │
  └──────────┬───────────┘   └──────────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
  ┌───────────────┐  ┌───────────────┐
  │ OFFER_ACCEPTED│  │ OFFER_DECLINED│
  └───────────────┘  └───────────────┘

  User can trigger WITHDRAWN from any state.
  ApplicationMethod: AUTO_BOT | EASY_APPLY | MANUAL | EMAIL
```

---

## Job Analysis Pipeline

Each job description passes through a two-stage LLM pipeline. The dual-model design balances cost against depth: cheap models filter aggressively, expensive models analyse deeply only when it matters.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                    JOB ANALYSIS PIPELINE                             │
  └──────────────────────────────────────────────────────────────────────┘

  Raw Job (status = NEW)
         │
         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  STAGE 1: Quick Filter  (GPT-4o-mini, low cost)                      │
  │                                                                      │
  │  Input:   job.title + job.description_clean                          │
  │           user.USER_DESIRED_ROLES + user.USER_EXPERIENCE_LEVEL       │
  │                                                                      │
  │  Output:  preliminary_score (0-100)                                  │
  │           is_relevant  (bool)                                        │
  │           quick_reason (1 sentence)                                  │
  │                                                                      │
  │  if preliminary_score < threshold:                                   │
  │       status = SKIPPED  →  pipeline exits                           │
  └──────────────────────────────────┬───────────────────────────────────┘
                                     │ score >= threshold
                                     ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  STAGE 2: Deep Analysis  (GPT-4o, structured JSON output)            │
  │                                                                      │
  │  Input:   full job description + user profile (RAG-enhanced)         │
  │                                                                      │
  │  Extracts:                                                           │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  required_skills      []   preferred_skills      []         │    │
  │  │  tech_stack           []   ats_keywords           []        │    │
  │  │  min_years_experience  0   max_years_experience  null       │    │
  │  │  education_requirement     role_category                    │    │
  │  │  seniority_detected        is_internship          bool      │    │
  │  │  estimated_salary_min      estimated_salary_max             │    │
  │  │  job_difficulty            key_responsibilities  []         │    │
  │  │  ai_summary (2 sentences)  ai_recommendation                │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  Computes:                                                           │
  │  ┌─────────────────────────────────────────────────────────────┐    │
  │  │  match_score     = skills overlap + experience fit           │    │
  │  │                  + role category alignment (0-100)           │    │
  │  │  priority_score  = match_score + recency bonus               │    │
  │  │                  + company prestige - estimated_competition  │    │
  │  │  skill_gaps      = required_skills - user.skills             │    │
  │  └─────────────────────────────────────────────────────────────┘    │
  │                                                                      │
  │  Persists:  JobAnalysis record  ·  status = ANALYZED                │
  └──────────────────────────────────────────────────────────────────────┘

  role_category:  computer_vision | nlp | mlops | data_science |
                  software_engineering | other
  seniority:      entry | mid | senior | lead
  difficulty:     easy | medium | hard
```

---

## Core Modules

| # | Module | Source File | Description |
|---|--------|-------------|-------------|
| 1 | Job Discovery | `agents/scrapers/` | Multi-platform scrapers with rate limiting and deduplication |
| 2 | Job Analyzer | `services/job_analyzer.py` | Dual-model LLM pipeline: batch filter (GPT-4o-mini) + deep analysis (GPT-4o) |
| 3 | Resume Engine | `services/resume_service.py` | ATS-optimised resume generation, keyword injection, PDF rendering, version tracking |
| 4 | Cover Letter Generator | `services/cover_letter_service.py` | Per-job cover letter with company context, role alignment, configurable tone |
| 5 | Auto Apply Bot | `agents/apply_bot.py` | Playwright browser automation: Workday, Greenhouse, Lever, LinkedIn Easy Apply, Indeed, Internshala |
| 6 | Application Tracker | `models/application.py` | 14-state lifecycle state machine with full `ApplicationEvent` audit log |
| 7 | Follow-up Automation | `services/follow_up_service.py` | 7-day follow-up emails, interview confirmations, post-interview thank-you dispatch |
| 8 | Notification Service | `services/notification_service.py` | Telegram bot (inline keyboards) and Jinja2-templated SMTP email |
| 9 | AI Chat Assistant | `services/ai_assistant.py` | Conversational interface: natural language commands mapped to agent actions |
| 10 | Market Intelligence | `services/market_service.py` | Trend snapshots: top skills, emerging roles, salary bands, hiring velocity |
| 11 | Interview Engine | `services/interview_service.py` | Company report generation, technical/behavioural Q&A, mock sessions, Whisper recording analysis |
| 12 | Background Agent | `agents/tasks.py` | Celery task definitions, beat schedule, 4-queue routing, retry policies, `AgentTask` logging |

---

## Data Models

### Entity Relationship Overview

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                     DATABASE SCHEMA  (key tables)                    │
  └──────────────────────────────────────────────────────────────────────┘

  ┌───────────────┐          ┌───────────────────┐
  │     users     │──────────│   user_profiles   │  1:1
  │               │          │                   │
  │  id (uuid)    │          │  desired_roles[]  │
  │  email        │          │  desired_locs[]   │
  │  hashed_pass  │          │  experience_level │
  │  is_active    │          │  open_to_remote   │
  └───────┬───────┘          │  min_salary       │
          │                  └───────────────────┘
          │ 1:N
          ├──────────────────────────────────────────────────────────┐
          │                                                          │
  ┌───────▼───────┐     ┌───────────────┐     ┌───────────────────┐ │
  │   user_skills │     │     jobs      │     │    resumes        │ │
  │               │     │               │     │                   │ │
  │  skill_name   │     │  source       │     │  resume_type      │ │
  │  proficiency  │     │  source_url   │     │  target_role      │ │
  │  is_verified  │     │  title        │     │  ats_score        │ │
  └───────────────┘     │  company_name │     │  pdf_path         │ │
                        │  description  │     │  is_base          │ │
                        │  job_type     │     │  performance_data │ │
                        │  work_mode    │     └───────────────────┘ │
                        │  salary_min   │                            │
                        │  salary_max   │  1:1                       │
                        │  status       │◄─────────────────────┐    │
                        └───────┬───────┘                      │    │
                                │ 1:1                          │    │
                        ┌───────▼───────────┐                  │    │
                        │   job_analyses    │         ┌────────▼────▼───┐
                        │                   │         │  applications   │
                        │  required_skills[]│         │                 │
                        │  preferred_skills │         │  status (FSM)   │
                        │  tech_stack[]     │         │  method         │
                        │  ats_keywords[]   │         │  resume_id      │
                        │  match_score      │         │  cover_letter_id│
                        │  priority_score   │         │  applied_at     │
                        │  skill_gaps[]     │         │  follow_up_*    │
                        │  job_difficulty   │         │  is_starred     │
                        │  ai_summary       │         └────────┬────────┘
                        └───────────────────┘                  │ 1:N
                                                       ┌────────▼────────┐
                                                       │application_events│
                                                       │                 │
                                                       │  from_status    │
                                                       │  to_status      │
                                                       │  triggered_by   │
                                                       │  event_type     │
                                                       │  timestamp      │
                                                       └────────┬────────┘
                                                                │
                                                       ┌────────▼────────┐
                                                       │   interviews    │
                                                       │                 │
                                                       │  interview_type │
                                                       │  scheduled_at   │
                                                       │  company_report │
                                                       │  tech_questions │
                                                       │  behav_questions│
                                                       │  study_topics   │
                                                       │  outcome        │
                                                       └────────┬────────┘
                                                                │ 1:N
                                                       ┌────────▼────────┐
                                                       │mock_interview_  │
                                                       │   sessions      │
                                                       │                 │
                                                       │  transcript[]   │
                                                       │  overall_score  │
                                                       │  tech_depth     │
                                                       │  comm_score     │
                                                       │  confidence     │
                                                       │  improvements[] │
                                                       └─────────────────┘
```

### Job Taxonomy

```
  JobSource:   linkedin | indeed | internshala | wellfound | glassdoor |
               company_site | manual

  JobType:     full_time | part_time | internship | contract | freelance

  WorkMode:    remote | onsite | hybrid | unknown

  JobStatus:   new → analyzed → queued → applied → skipped | expired

  Seniority:   entry | mid | senior | lead | unknown

  RoleCategory: computer_vision | nlp | mlops | data_science |
                software_engineering | other
```

---

## Quick Start

### Prerequisites

| Dependency | Minimum Version | Purpose |
|---|---|---|
| Python | 3.11 | Runtime |
| PostgreSQL | 15 | Primary datastore |
| Redis | 7 | Celery broker and result backend |
| Node.js | 18 | Next.js frontend |
| Playwright / Chromium | 1.44 | Browser automation |

### 1. Clone the Repository

```bash
git clone https://github.com/Sudharsanselvaraj/Distributed-Autonomous-Opportunity-Intelligence-and-Strategic-Application-Orchestration-System.git
cd Distributed-Autonomous-Opportunity-Intelligence-and-Strategic-Application-Orchestration-System
```

### 2. Python Environment

```bash
python -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

pip install -r requirements.txt
playwright install chromium
```

### 3. Environment Configuration

```bash
cp career_platform/.env.example career_platform/.env
# Edit .env — refer to the Configuration section for all variables
```

### 4. Database Initialisation

```bash
psql -U postgres -c "CREATE DATABASE career_platform;"
cd career_platform
alembic upgrade head
```

### 5. Starting Services

**Windows (automated):**
```bat
setup.bat          # First time: install deps, create dirs, run migrations
start_platform.bat # Start all services
```

**Linux / macOS — four separate terminals:**

```bash
# Terminal 1 — FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# Terminal 2 — Celery workers (all four queues)
celery -A app.agents.tasks.celery_app worker --loglevel=info \
  -Q scraping,ai,automation,notifications --concurrency=4
```

```bash
# Terminal 3 — Celery Beat scheduler (periodic tasks)
celery -A app.agents.tasks.celery_app beat --loglevel=info
```

```bash
# Terminal 4 — Flower monitoring dashboard (optional)
celery -A app.agents.tasks.celery_app flower --port=5555
```

### 6. Register and Authenticate

```bash
# Create your account
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword", "full_name": "Your Name"}'

# Obtain a JWT token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

### 7. Service Endpoints

| Service | URL | Notes |
|---|---|---|
| API — Swagger UI | http://localhost:8000/api/docs | Full interactive docs |
| API — ReDoc | http://localhost:8000/api/redoc | Clean reference layout |
| Health Check | http://localhost:8000/health | DB connectivity status |
| Celery Flower | http://localhost:5555 | Task monitoring dashboard |

---

## Configuration

All configuration is managed via `career_platform/.env`. The full template is in `.env.example`. Below is a structured reference for every setting group.

### Application

```env
APP_NAME="AI Career Platform"
APP_ENV=development              # development | staging | production
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
SECRET_KEY=your-secret-key-minimum-32-characters
```

### Database

```env
DATABASE_URL=postgresql+asyncpg://career_user:career_pass@localhost:5432/career_platform
DATABASE_URL_SYNC=postgresql://career_user:career_pass@localhost:5432/career_platform
```

### Task Queue

```env
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### AI Layer

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL_HEAVY=gpt-4o          # Deep analysis, resume gen, cover letters, interview prep
OPENAI_MODEL_LIGHT=gpt-4o-mini     # Batch scoring, quick filtering, chat responses
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=0.3
```

### Vector Database (ChromaDB)

```env
CHROMA_HOST=localhost
CHROMA_PORT=8001
CHROMA_COLLECTION_USER_PROFILE=user_profile
CHROMA_COLLECTION_JOBS=jobs
CHROMA_COLLECTION_RESUMES=resumes
```

### Notifications

```env
# Telegram — create bot via @BotFather, get chat ID via @userinfobot
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-personal-chat-id

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password      # Gmail App Password, not account password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME="AI Career Agent"
```

### User Profile

The profile is fed into every AI prompt. Accuracy here directly determines match quality.

```env
USER_NAME="Your Name"
USER_EMAIL=your-email@gmail.com
USER_PHONE=+91-XXXXXXXXXX
USER_LOCATION="Chennai, India"
USER_DESIRED_ROLES=["Computer Vision Engineer","ML Engineer","AI Research Intern","Data Scientist"]
USER_DESIRED_LOCATIONS=["Remote","Bangalore","Hyderabad","Chennai","Europe","USA"]
USER_EXPERIENCE_LEVEL=entry        # entry | mid | senior
USER_OPEN_TO_REMOTE=true
USER_MIN_SALARY=0                  # 0 = no minimum constraint
```

### Job Scraping

```env
SCRAPE_INTERVAL_HOURS=6            # Master cycle interval
MAX_JOBS_PER_CYCLE=200             # Cap on new jobs stored per cycle
SCRAPE_DELAY_MIN_SECONDS=2.0       # Random polite delay between HTTP requests
SCRAPE_DELAY_MAX_SECONDS=6.0

# Platform credentials (for authenticated scraping)
LINKEDIN_EMAIL=your-linkedin@email.com
LINKEDIN_PASSWORD=your-linkedin-password
```

### Auto-Apply

Auto-apply is **disabled by default**. Review each setting carefully before enabling.

```env
AUTO_APPLY_ENABLED=false
AUTO_APPLY_MATCH_THRESHOLD=75      # Only queue applications with match_score >= this value
AUTO_APPLY_DAILY_LIMIT=10          # Hard ceiling on applications submitted per calendar day
AUTO_APPLY_REQUIRE_APPROVAL=true   # Human-in-the-loop: send Telegram alert, wait for user confirmation
```

### File Storage

```env
STORAGE_BACKEND=local              # local | s3
LOCAL_STORAGE_PATH=./storage       # Resumes, cover letters, interview recordings stored here

# Optional S3 configuration
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_BUCKET_NAME=career-platform-files
AWS_REGION=us-east-1
```

### Authentication

```env
JWT_SECRET_KEY=your-jwt-secret-minimum-32-characters
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440   # 24 hours
```

---

## API Reference

Full interactive documentation is available at `/api/docs` (Swagger UI) and `/api/redoc` (ReDoc) when the server is running. All endpoints require JWT Bearer authentication.

### Router Overview

| Router | Prefix | Tag | Key Endpoints |
|---|---|---|---|
| Auth | `/api/auth` | Authentication | `POST /register`, `POST /login`, `GET /me` |
| Jobs | `/api/jobs` | Jobs | `GET /` (paginated, filterable), `GET /{id}`, `POST /` (manual add), `POST /{id}/analyze`, `POST /{id}/skip` |
| Applications | `/api/applications` | Applications | `GET /` (paginated), `GET /{id}`, `POST /`, `PATCH /{id}/status`, `GET /stats` |
| Resumes | `/api/resumes` | Resumes | `GET /`, `POST /upload`, `POST /generate`, `GET /{id}/download`, `DELETE /{id}` |
| Cover Letters | `/api/cover-letters` | Cover Letters | `GET /`, `POST /generate`, `GET /{id}`, `DELETE /{id}` |
| Agent | `/api/agent` | Agent Control | `POST /run`, `GET /tasks`, `GET /tasks/{id}`, `POST /cycle/trigger` |
| Analytics | `/api/analytics` | Analytics | `GET /dashboard`, `GET /market`, `GET /resume-performance`, `GET /skill-gaps` |
| Chat | `/api/chat` | Chat | `POST /message`, `GET /history`, `DELETE /history` |

### Job Filtering Parameters

The `GET /api/jobs` endpoint supports rich query parameters:

```
source          linkedin | indeed | internshala | wellfound | manual
job_type        full_time | internship | contract | part_time
work_mode       remote | onsite | hybrid
min_match_score float (0-100)
keyword         searches title, company, and description
status          new | analyzed | queued | applied | skipped
sort_by         match_score | priority_score | posted_at | created_at
page            default 1
page_size       default 20, max 100
```

### Usage Examples

**Trigger a manual scrape cycle:**
```bash
curl -X POST http://localhost:8000/api/agent/run \
  -H "Authorization: Bearer " \
  -H "Content-Type: application/json" \
  -d '{"task": "scrape_jobs", "params": {"platforms": ["linkedin", "indeed"]}}'
```

**List top-matched jobs (score >= 80, remote only):**
```bash
curl "http://localhost:8000/api/jobs?min_match_score=80&work_mode=remote&sort_by=match_score" \
  -H "Authorization: Bearer "
```

**Generate a tailored resume for a specific job:**
```bash
curl -X POST http://localhost:8000/api/resumes/generate \
  -H "Authorization: Bearer " \
  -H "Content-Type: application/json" \
  -d '{"job_id": "uuid-of-job", "base_resume_id": "uuid-of-base-resume"}'
```

**Query the AI assistant:**
```bash
curl -X POST http://localhost:8000/api/chat/message \
  -H "Authorization: Bearer " \
  -H "Content-Type: application/json" \
  -d '{"message": "Find AI internships in Europe and apply to the top 3 matches"}'
```

**Get dashboard analytics:**
```bash
curl http://localhost:8000/api/analytics/dashboard \
  -H "Authorization: Bearer "
```

---

## Automation Schedule

All periodic tasks are registered in Celery Beat via the `beat_schedule` dictionary in `agents/tasks.py`. No cron configuration is required outside the application.

| Task Name | Celery Beat Interval | Queue | Description |
|---|---|---|---|
| `run_main_agent_cycle` | Every 6 hours (`SCRAPE_INTERVAL_HOURS`) | scraping / ai / automation | Full pipeline: discover → analyse → generate → apply → notify |
| `check_follow_ups` | Every 1 hour | notifications | Dispatch follow-up emails; 7-day automatic recruiter follow-up |
| `take_market_snapshot` | Daily (86400s) | ai | Aggregate skill demand, salary trends, hiring velocity from current job data |
| `update_resume_performance` | Every 6 hours | ai | Recalculate response rates per resume version based on application outcomes |

### Celery Queue Architecture

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                        QUEUE ROUTING                                 │
  └──────────────────────────────────────────────────────────────────────┘

  Task pattern                          Queue          Rate limit
  ─────────────────────────────────     ──────────     ──────────
  scrape_linkedin_task                  scraping       10 / min
  scrape_indeed_task                    scraping       20 / min
  scrape_internshala_task               scraping       (default)
  scrape_wellfound_task                 scraping       (default)

  analyze_job_task                      ai             (default)
  analyze_new_jobs_batch_task           ai             (default)
  generate_resume_task                  ai             (default)
  generate_cover_letter_task            ai             (default)
  generate_materials_for_top_jobs_task  ai             (default)

  auto_apply_task                       automation      5 / min
  queue_auto_applications_task          automation     (default)

  send_telegram_notification            notifications  (default)
  send_email_notification               notifications  (default)
  check_follow_ups                      notifications  (default)

  Retry policy (all tasks):
    max_retries = 3
    retry backoff = exponential
    task_acks_late = true       (re-queued if worker crashes mid-task)
    task_reject_on_worker_lost = true
    result_expires = 86400      (24 hours)
```

---

## Interview Preparation Engine

When an application advances to `INTERVIEW_SCHEDULED`, the system automatically generates a full preparation package.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                  INTERVIEW PREPARATION PIPELINE                      │
  └──────────────────────────────────────────────────────────────────────┘

  Trigger: Application status → INTERVIEW_SCHEDULED
                │
                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Company Intelligence Report  (GPT-4o + web search)             │
  │                                                                  │
  │  products_and_services     recent_news                          │
  │  tech_stack                company_culture                      │
  │  salary_data               glassdoor_rating                     │
  │  interview_difficulty      known_interview_format               │
  └─────────────────────────────────────────────────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Question Bank Generation  (GPT-4o, based on role + JD)          │
  │                                                                  │
  │  Technical Questions:                                            │
  │  { question, expected_answer, difficulty, topic }               │
  │  e.g. "Explain the ResNet skip connection and its purpose"      │
  │                                                                  │
  │  Behavioural Questions:                                          │
  │  { question, star_framework_hint }                               │
  │  e.g. "Describe a time you debugged a production ML model"      │
  │                                                                  │
  │  Study Topics:  ranked list of concepts to review               │
  └─────────────────────────────────────────────────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Mock Interview Sessions  (AI Interviewer — GPT-4o)              │
  │                                                                  │
  │  Full transcript  [{role, content, timestamp}]                   │
  │  Scoring:                                                        │
  │    overall_score         (0-100)                                 │
  │    technical_depth_score                                         │
  │    communication_score                                           │
  │    confidence_score                                              │
  │    improvement_suggestions []                                    │
  └─────────────────────────────────────────────────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Interview Recording Analysis  (Whisper + GPT-4o)                │
  │                                                                  │
  │  Transcription via OpenAI Whisper                               │
  │  Analysis:  filler_word_count, speech_clarity, confidence_level │
  │             technical_depth, pacing, improvement_notes          │
  └─────────────────────────────────────────────────────────────────┘

  InterviewType: phone_screen | technical | behavioral |
                 system_design | hr | final | take_home
```

---

## Project Structure

```
career_platform/
├── app/
│   ├── agents/
│   │   ├── apply_bot.py              # Playwright auto-apply bot
│   │   │                             # ATS detection: Workday, Greenhouse, Lever,
│   │   │                             # LinkedIn Easy Apply, Indeed, Internshala
│   │   ├── tasks.py                  # Celery task definitions, beat schedule,
│   │   │                             # queue routing, AgentTask audit logging
│   │   └── scrapers/
│   │       ├── base.py               # Abstract base: rate limiting, dedup,
│   │       │                         # DB persistence, ScrapedJob dataclass
│   │       ├── linkedin.py           # LinkedIn scraper (authenticated)
│   │       ├── indeed.py             # Indeed scraper
│   │       ├── internshala.py        # Internshala scraper
│   │       └── wellfound.py          # Wellfound (AngelList) scraper
│   │
│   ├── api/
│   │   └── routes/
│   │       ├── auth.py               # JWT registration, login, /me endpoint
│   │       ├── jobs.py               # Job feed: list, filter, get, manual add,
│   │       │                         # trigger analysis, skip
│   │       └── routes.py             # Applications, resumes, cover letters,
│   │                                 # agent control, analytics, chat
│   │
│   ├── core/
│   │   ├── config.py                 # Pydantic Settings — reads .env,
│   │   │                             # storage path properties, JSON list parsing
│   │   └── database.py               # SQLAlchemy async engine, session factory,
│   │                                 # get_db dependency, get_db_context
│   │
│   ├── models/
│   │   ├── application.py            # Application (14-state FSM),
│   │   │                             # ApplicationEvent audit log,
│   │   │                             # ApplicationMethod, FollowUpStatus
│   │   ├── interview.py              # Interview, MockInterviewSession,
│   │   │                             # RecruiterContact, Notification,
│   │   │                             # AgentTask, SkillGap, MarketSnapshot
│   │   ├── job.py                    # Job (raw), JobAnalysis (enriched),
│   │   │                             # JobSource, JobType, WorkMode, JobStatus
│   │   ├── resume.py                 # Resume versions, ResumeType
│   │   └── user.py                   # User, UserProfile, UserSkill,
│   │                                 # ExperienceLevel, SoftDeleteMixin
│   │
│   ├── services/
│   │   ├── ai_assistant.py           # Chat service: intent detection,
│   │   │                             # agent action dispatch, response generation
│   │   ├── application_service.py    # Application CRUD, status transitions
│   │   ├── cover_letter_service.py   # GPT-4o cover letter generation
│   │   ├── follow_up_service.py      # Follow-up scheduling and email dispatch
│   │   ├── interview_service.py      # Interview prep, mock sessions,
│   │   │                             # Whisper recording analysis
│   │   ├── job_analyzer.py           # Two-pass LLM analysis pipeline,
│   │   │                             # match scoring, skill gap extraction
│   │   ├── market_service.py         # Market snapshots, skill demand,
│   │   │                             # salary trend aggregation
│   │   ├── notification_service.py   # Telegram bot + SMTP email dispatch,
│   │   │                             # Jinja2 HTML templates
│   │   └── resume_service.py         # GPT-4o resume tailoring, ATS keyword
│   │                                 # injection, PDF rendering, version control
│   │
│   ├── schemas/
│   │   └── __init__.py               # All Pydantic v2 request/response schemas
│   │
│   ├── utils/
│   │   └── helpers.py                # Shared utility functions
│   │
│   └── main.py                       # FastAPI app factory, router registration,
│                                     # CORS config, global exception handler,
│                                     # lifespan (DB init + shutdown)
│
├── alembic/                           # Database migration scripts (Alembic)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── tests/
├── .env.example                       # Full configuration template
├── alembic.ini
├── requirements.txt                   # 40+ pinned dependencies
├── setup.bat                          # Windows first-time setup (4-step)
└── start_platform.bat                 # Windows service launcher
```

---

## Tech Stack

| Layer | Technology | Version | Role |
|---|---|---|---|
| Web Framework | FastAPI | 0.111.0 | REST API, dependency injection, async request handling |
| ASGI Server | Uvicorn | 0.30.1 | High-performance async server |
| Database ORM | SQLAlchemy (async) | 2.0.30 | Async database access, relationship loading |
| Database | PostgreSQL | 15+ | Primary relational datastore |
| Migrations | Alembic | 1.13.1 | Schema version control |
| Task Queue | Celery | 5.4.0 | Distributed task execution |
| Message Broker | Redis | 5.0.4 (py) | Celery broker + result backend |
| Scheduler | APScheduler | 3.10.4 | In-process scheduling fallback |
| Queue Monitor | Flower | 2.0.1 | Celery task monitoring dashboard |
| LLM (heavy) | OpenAI GPT-4o | openai 1.30.1 | Deep analysis, resume/cover letter generation |
| LLM (light) | OpenAI GPT-4o-mini | openai 1.30.1 | Batch scoring, filtering, chat |
| Embeddings | text-embedding-3-small | openai 1.30.1 | Semantic profile and job vectorisation |
| Audio | OpenAI Whisper | openai-whisper 20231117 | Interview recording transcription |
| LLM Orchestration | LangChain / LangChain-OpenAI | 0.2.1 / 0.1.7 | Prompt chaining, RAG retrieval |
| Vector Store | ChromaDB | 0.5.0 | Semantic memory: profile, jobs, resumes |
| Browser Automation | Playwright | 1.44.0 | Chromium-based auto-apply bot |
| HTTP Client | httpx | 0.27.0 | Async HTTP requests |
| HTTP Client | aiohttp | 3.9.5 | Concurrent async scraping |
| HTML Parsing | BeautifulSoup4 + lxml | 4.12.3 / 5.2.2 | Job description extraction |
| Telegram | python-telegram-bot | 21.2 | Bot API, inline keyboards |
| Email | aiosmtplib | 3.0.1 | Async SMTP dispatch |
| Email Templates | Jinja2 | 3.1.4 | HTML email rendering |
| PDF Generation | WeasyPrint | 62.1 | CSS-to-PDF resume rendering |
| PDF Generation | ReportLab | 4.2.0 | Programmatic PDF construction |
| Auth (JWT) | python-jose | 3.3.0 | JWT signing and verification |
| Auth (passwords) | passlib + bcrypt | 1.7.4 / 4.1.3 | Password hashing |
| Schemas | Pydantic v2 | 2.7.1 | Request/response validation |
| Settings | pydantic-settings | 2.3.0 | .env loading with type coercion |
| File Storage | boto3 (S3) | 1.34.113 | Optional cloud file storage |
| Async Files | aiofiles | 23.2.1 | Non-blocking file I/O |
| Logging | structlog | 24.1.0 | Structured JSON logging |
| Retry Logic | tenacity | 8.3.0 | Exponential backoff on failures |
| User Agent | fake-useragent | 1.5.1 | Scraper detection avoidance |
| Frontend | Next.js | 18+ | Dashboard UI |
| Styling | TailwindCSS | 3+ | Utility-first styling |

---

## Security

**Authentication.** All API endpoints require a JWT Bearer token. Register via `POST /api/auth/register`, authenticate via `POST /api/auth/login`. Tokens expire after 24 hours (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440`). Passwords are hashed with bcrypt.

**Secrets.** `SECRET_KEY` and `JWT_SECRET_KEY` must be replaced with cryptographically random strings of at least 32 characters before any non-local deployment. Use `openssl rand -hex 32` to generate them.

**Credentials file.** Platform
