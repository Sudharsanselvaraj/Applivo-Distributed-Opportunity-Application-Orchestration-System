<div align="center">
### Distributed Autonomous Opportunity Intelligence and Strategic Application Orchestration System

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7+-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)](https://openai.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

A personal AI career automation platform that autonomously discovers opportunities, generates tailored application materials, submits applications, and orchestrates the full job search lifecycle through a distributed background agent system.

[Overview](#overview) · [Architecture](#architecture) · [Modules](#core-modules) · [Quick Start](#quick-start) · [Configuration](#configuration) · [API Reference](#api-reference) · [Roadmap](#roadmap)

</div>

---

## Overview

D.A.O.I.S.A.O.S is a **distributed, AI-powered career automation platform** built for single-user personal deployment. It operates as a background system — continuously scraping job boards, scoring opportunities against your profile using LLM analysis, generating ATS-optimised application materials, submitting applications via browser automation, and delivering notifications across multiple channels.

The platform is structured around a clear separation of concerns: a FastAPI backend exposes all functionality as a REST API, a Celery worker cluster handles all asynchronous and scheduled automation, and a ChromaDB vector store maintains semantic memory of your career profile, past applications, and recruiter interactions.

**Core automation loop (runs every 6 hours):**

```
Job Discovery  -->  AI Analysis & Scoring  -->  Resume Tailoring  -->  Auto Apply  -->  Track & Follow-up  -->  Notify
```

---

## Architecture

```
+-----------------------------------------------------------------+
|                  FRONTEND  (Next.js + TailwindCSS)              |
|   Dashboard  |  Job Feed  |  Resume Manager  |  Chat  |  Analytics  |
+------------------------------+----------------------------------+
                               | REST  (JSON / JWT)
+------------------------------v----------------------------------+
|                      FASTAPI APPLICATION                        |
|  /auth  /jobs  /applications  /resumes  /agent  /analytics  /chat  |
+-------+--------------------------------------+-----------------+
        | SQLAlchemy async                     | Celery task dispatch
+-------v--------+  +------------+  +---------v---------------------+
|  PostgreSQL 15 |  |  ChromaDB  |  |        CELERY WORKERS          |
|  (primary      |  |  (vector   |  |   queue: scraping              |
|   datastore)   |  |   memory)  |  |   queue: ai                    |
+----------------+  +------------+  |   queue: automation            |
                                     |   queue: notifications         |
                    +------------+  +--------------------------------+
                    |   Redis 7  |<-- Celery Broker + Result Backend
                    +------------+
                                     +--------------------------------+
                                     |         AI SERVICES            |
                                     |  GPT-4o      (analysis, gen)   |
                                     |  GPT-4o-mini (scoring, chat)   |
                                     |  text-embedding-3-small        |
                                     |  Whisper     (interview audio) |
                                     +--------------------------------+
                                     +--------------------------------+
                                     |    NOTIFICATION CHANNELS       |
                                     |  Telegram Bot                  |
                                     |  SMTP Email (Gmail / custom)   |
                                     +--------------------------------+
```

---

## Core Modules

| # | Module | Source File | Description |
|---|--------|-------------|-------------|
| 1 | Job Discovery | `agents/scrapers/` | Multi-platform scrapers: LinkedIn, Indeed, Internshala, Wellfound |
| 2 | Job Analyzer | `services/job_analyzer.py` | LLM-powered JD parsing, skill extraction, ATS keyword detection, match scoring |
| 3 | Resume Engine | `services/resume_service.py` | ATS-optimised resume generation, version control, performance tracking |
| 4 | Cover Letter Generator | `services/cover_letter_service.py` | Per-job cover letter tailored to company, role, and tone |
| 5 | Auto Apply Bot | `agents/apply_bot.py` | Playwright browser automation: Workday, Greenhouse, Lever, LinkedIn Easy Apply, Indeed |
| 6 | Application Tracker | `models/application.py` | Full lifecycle status tracking with event log per application |
| 7 | Follow-up Automation | `services/follow_up_service.py` | Scheduled recruiter follow-ups, interview confirmations, thank-you emails |
| 8 | Notification Service | `services/notification_service.py` | Telegram bot and SMTP email dispatch |
| 9 | AI Chat Assistant | `services/ai_assistant.py` | Conversational interface for issuing natural language commands |
| 10 | Market Intelligence | `services/market_service.py` | Job market trend analysis, skill demand aggregation, salary data |
| 11 | Interview Engine | `services/interview_service.py` | Interview prep generation, mock interviewer, Whisper-based recording analysis |
| 12 | Background Agent | `agents/tasks.py` | Celery task definitions, beat schedule, queue routing, retry policies |

---

## Quick Start

### Prerequisites

| Dependency | Minimum Version | Notes |
|---|---|---|
| Python | 3.11 | |
| PostgreSQL | 15 | Primary datastore |
| Redis | 7 | Celery broker and result backend |
| Node.js | 18 | Next.js frontend |
| Playwright | 1.44 | Chromium browser automation |

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
# Edit .env with your values — refer to the Configuration section below
```

### 4. Database Initialisation

```bash
psql -U postgres -c "CREATE DATABASE career_platform;"
cd career_platform
alembic upgrade head
```

### 5. Starting Services

**Windows:**
```bat
start_platform.bat
```

**Linux / macOS — run each in a separate terminal:**
```bash
# FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Celery worker (all queues)
celery -A app.agents.tasks.celery_app worker --loglevel=info \
  -Q scraping,ai,automation,notifications

# Celery Beat scheduler
celery -A app.agents.tasks.celery_app beat --loglevel=info

# Flower monitoring UI (optional)
celery -A app.agents.tasks.celery_app flower --port=5555
```

### 6. Service Endpoints

| Service | URL |
|---|---|
| API — Swagger UI | http://localhost:8000/api/docs |
| API — ReDoc | http://localhost:8000/api/redoc |
| Health Check | http://localhost:8000/health |
| Celery Flower | http://localhost:5555 |

---

## Configuration

All configuration is managed via `career_platform/.env`. Copy from `.env.example` and populate each section.

### Application

```env
APP_NAME="AI Career Platform"
APP_ENV=development              # development | staging | production
DEBUG=true
SECRET_KEY=your-secret-key-minimum-32-characters
```

### Database and Queue

```env
DATABASE_URL=postgresql+asyncpg://career_user:career_pass@localhost:5432/career_platform
DATABASE_URL_SYNC=postgresql://career_user:career_pass@localhost:5432/career_platform
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### AI Layer (Required)

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL_HEAVY=gpt-4o          # Deep analysis, resume generation, cover letters
OPENAI_MODEL_LIGHT=gpt-4o-mini     # Batch scoring, filtering, chat responses
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=0.3
```

### Vector Database

```env
CHROMA_HOST=localhost
CHROMA_PORT=8001
CHROMA_COLLECTION_USER_PROFILE=user_profile
CHROMA_COLLECTION_JOBS=jobs
CHROMA_COLLECTION_RESUMES=resumes
```

### Notifications

```env
# Telegram — create a bot via @BotFather, retrieve chat ID via @userinfobot
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-personal-chat-id

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-gmail-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME="AI Career Agent"
```

### User Profile

The profile section drives job match scoring and platform-wide filtering logic.

```env
USER_NAME="Your Name"
USER_EMAIL=your-email@gmail.com
USER_PHONE=+91-XXXXXXXXXX
USER_LOCATION="Chennai, India"
USER_DESIRED_ROLES=["Computer Vision Engineer","ML Engineer","AI Research Intern"]
USER_DESIRED_LOCATIONS=["Remote","Bangalore","Europe","USA"]
USER_EXPERIENCE_LEVEL=entry        # entry | mid | senior
USER_OPEN_TO_REMOTE=true
USER_MIN_SALARY=0                  # 0 = no minimum
```

### Job Scraping

```env
SCRAPE_INTERVAL_HOURS=6
MAX_JOBS_PER_CYCLE=200
SCRAPE_DELAY_MIN_SECONDS=2.0       # Polite delay between requests
SCRAPE_DELAY_MAX_SECONDS=6.0

LINKEDIN_EMAIL=your-linkedin@email.com
LINKEDIN_PASSWORD=your-linkedin-password
```

### Auto-Apply

Auto-apply is **disabled by default**. Enable only after verifying match thresholds and approval settings.

```env
AUTO_APPLY_ENABLED=false
AUTO_APPLY_MATCH_THRESHOLD=75      # Minimum AI match score to trigger application
AUTO_APPLY_DAILY_LIMIT=10          # Hard cap on applications per day
AUTO_APPLY_REQUIRE_APPROVAL=true   # Send Telegram alert and await explicit approval
```

### Authentication

```env
JWT_SECRET_KEY=your-jwt-secret-minimum-32-characters
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

---

## API Reference

Full interactive documentation is available at `/api/docs` (Swagger) and `/api/redoc` (ReDoc) when the server is running.

| Router | Prefix | Responsibility |
|---|---|---|
| Auth | `/api/auth` | Registration, login, JWT token issuance and refresh |
| Jobs | `/api/jobs` | Job feed, search, filtering, per-job AI analysis |
| Applications | `/api/applications` | Create, update, and query application records |
| Resumes | `/api/resumes` | Upload, version, generate, and compare resume variants |
| Cover Letters | `/api/cover-letters` | Generate and manage cover letter versions |
| Agent | `/api/agent` | Manually trigger automation tasks |
| Analytics | `/api/analytics` | Dashboard metrics, market intelligence reports |
| Chat | `/api/chat` | Natural language commands to the AI assistant |

**Example — trigger a manual job search cycle:**

```bash
curl -X POST http://localhost:8000/api/agent/run \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"task": "scrape_jobs", "params": {"platforms": ["linkedin", "indeed"]}}'
```

**Example — conversational AI assistant:**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "Find AI internships in Europe and apply to the top 3 matches"}'
```

---

## Automation Schedule

All scheduled tasks run via Celery Beat. The schedule is defined in `agents/tasks.py`.

| Task | Interval | Description |
|---|---|---|
| `run_main_agent_cycle` | Every 6 hours | Full pipeline: scrape → analyse → generate → apply → notify |
| `check_follow_ups` | Every 1 hour | Dispatch follow-up emails and recruiter reminders |
| `take_market_snapshot` | Daily | Capture job market trends, top skills, salary data |
| `update_resume_performance` | Every 6 hours | Recalculate response rates per resume version |

### Queue Architecture

Tasks are routed to purpose-specific queues to allow independent scaling:

```
scraping        -->  LinkedIn, Indeed, Internshala, Wellfound scrapers
ai              -->  Job analysis, resume generation, cover letters, scoring
automation      -->  Auto apply bot  (rate-limited: 5 tasks/min)
notifications   -->  Telegram and email dispatch
```

Task retry policy: maximum 3 retries with exponential backoff, `task_acks_late=true` for safe crash recovery.

---

## Project Structure

```
career_platform/
├── app/
│   ├── agents/
│   │   ├── apply_bot.py              # Playwright auto-apply bot
│   │   ├── tasks.py                  # Celery task definitions and beat schedule
│   │   └── scrapers/
│   │       ├── base.py               # Abstract scraper base class
│   │       ├── linkedin.py
│   │       ├── indeed.py
│   │       ├── internshala.py
│   │       └── wellfound.py
│   ├── api/
│   │   └── routes/
│   │       ├── auth.py               # JWT auth endpoints
│   │       ├── jobs.py               # Job feed endpoints
│   │       └── routes.py             # Applications, resumes, agent, analytics, chat
│   ├── core/
│   │   ├── config.py                 # Pydantic Settings (reads .env)
│   │   └── database.py               # SQLAlchemy async engine and session factory
│   ├── models/
│   │   ├── application.py            # Application and ApplicationEvent ORM models
│   │   ├── interview.py              # Interview prep and simulation models
│   │   ├── job.py                    # Job and JobAnalysis ORM models
│   │   ├── resume.py                 # Resume version ORM models
│   │   └── user.py                   # User, UserProfile, UserSkill ORM models
│   ├── services/
│   │   ├── ai_assistant.py           # Conversational assistant
│   │   ├── application_service.py
│   │   ├── cover_letter_service.py
│   │   ├── follow_up_service.py
│   │   ├── interview_service.py
│   │   ├── job_analyzer.py           # GPT-4o JD analysis and match scoring
│   │   ├── market_service.py         # Job market intelligence
│   │   ├── notification_service.py   # Telegram + SMTP
│   │   └── resume_service.py         # ATS resume generation and versioning
│   ├── schemas/
│   │   └── __init__.py               # Pydantic request / response schemas
│   ├── utils/
│   │   └── helpers.py
│   └── main.py                       # FastAPI application factory
├── alembic/                           # Database migration scripts
├── tests/
├── .env.example
├── requirements.txt
├── setup.bat
└── start_platform.bat
```

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Web Framework | FastAPI, Uvicorn | 0.111.0, 0.30.1 |
| Database | PostgreSQL, SQLAlchemy (async), Alembic | 15+, 2.0.30, 1.13.1 |
| Task Queue | Celery, Redis, APScheduler, Flower | 5.4.0, 5.0.4, 3.10.4, 2.0.1 |
| AI / LLM | OpenAI GPT-4o, GPT-4o-mini, Whisper | openai 1.30.1 |
| LLM Orchestration | LangChain, LangChain-OpenAI | 0.2.1, 0.1.7 |
| Vector Store | ChromaDB | 0.5.0 |
| Browser Automation | Playwright | 1.44.0 |
| HTTP / Scraping | httpx, aiohttp, BeautifulSoup4, lxml | 0.27.0, 3.9.5, 4.12.3, 5.2.2 |
| Notifications | python-telegram-bot, aiosmtplib, Jinja2 | 21.2, 3.0.1, 3.1.4 |
| Authentication | python-jose, passlib, bcrypt | 3.3.0, 1.7.4, 4.1.3 |
| PDF Generation | WeasyPrint, ReportLab | 62.1, 4.2.0 |
| File Storage | Local filesystem / AWS S3 (boto3) | 1.34.113 |
| Logging | structlog | 24.1.0 |
| Resilience | tenacity | 8.3.0 |
| Settings | pydantic-settings | 2.3.0 |
| Frontend | Next.js, TailwindCSS | 18+, 3+ |

---

## Security

- All API endpoints require a JWT Bearer token. Register via `POST /api/auth/register`, then authenticate via `POST /api/auth/login` to obtain a token.
- `SECRET_KEY` and `JWT_SECRET_KEY` must be replaced with cryptographically random strings of at least 32 characters before any deployment.
- Platform credentials (LinkedIn, Gmail) are stored exclusively in the local `.env` file. This file must never be committed to version control.
- `AUTO_APPLY_ENABLED` defaults to `false`. When enabled, `AUTO_APPLY_REQUIRE_APPROVAL=true` sends a Telegram notification and awaits explicit confirmation before any application is submitted, providing a mandatory human-in-the-loop gate.
- Scraper rate limiting is enforced at the Celery task level (configurable per-platform) to reduce detection and ban risk on external platforms.

---

## Roadmap

- [ ] Next.js frontend dashboard (Job Feed, Resume Manager, Analytics, Chat)
- [ ] Glassdoor scraper integration
- [ ] LangChain RAG memory layer for full career knowledge base
- [ ] WhatsApp notification channel
- [ ] Skill gap analyser with auto-generated weekly learning roadmap
- [ ] GitHub profile and LinkedIn automated optimiser
- [ ] Networking assistant — hiring manager identification and outreach generation
- [ ] Docker Compose full-stack deployment configuration
- [ ] Application success probability predictor
- [ ] Offer comparison and decision engine

---

## Contributing

Please open an issue before submitting a pull request to allow discussion of the proposed change.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit: `git commit -m "feat: description of change"`
4. Push: `git push origin feature/your-feature-name`
5. Open a Pull Request against `main`

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

<div align="center">
Built by <a href="https://github.com/Sudharsanselvaraj">Sudharsan Selvaraj</a>
</div>
