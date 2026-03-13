# Security & User Onboarding Plan

## Overview
AI Career Platform - Comprehensive security and onboarding implementation.

---

## 1. Authentication Strategy

### User Sign-up/Login
- **Password Storage**: bcrypt hashing via Passlib
- **Session Management**: JWT tokens with 24-hour expiry
- **API Endpoints**:
  - `POST /api/v1/auth/register` - User registration
  - `POST /api/v1/auth/login` - User login
  - `POST /api/v1/auth/logout` - User logout
  - `GET /api/v1/auth/me` - Get current user

### Implementation Files
- [`backend/app/api/routes/auth.py`](backend/app/api/routes/auth.py) - Authentication routes
- [`backend/app/models/user.py`](backend/app/models/user.py) - User model with password hashing

---

## 2. Environment/Config Management

### Configuration
- Environment variables stored in `.env` file
- Secrets management via environment variables
- Default values provided in [`backend/app/core/config.py`](backend/app/core/config.py)

### Key Settings
```python
DATABASE_URL=postgresql://...
SECRET_KEY=your-secret-key
OPENAI_API_KEY=sk-...
ENCRYPTION_KEY=32-byte-key-for-aes-256
```

---

## 3. External Service Credentials

### Credentials Vault
- Encrypted storage using AES-256-GCM
- User-provided API keys (LinkedIn, Indeed, etc.)
- API Routes:
  - `POST /api/v1/credentials` - Store credential
  - `GET /api/v1/credentials` - List credentials (masked)
  - `DELETE /api/v1/credentials/{id}` - Revoke credential

### Implementation Files
- [`backend/app/models/credentials.py`](backend/app/models/credentials.py) - Credential vault model
- [`backend/app/utils/encryption.py`](backend/app/utils/encryption.py) - Encryption utilities

---

## 4. Personal Data Management

### Data Model
- **User**: Core authentication entity
- **UserProfile**: Career preferences, contact info, experience
- **UserSkill**: Individual skills with proficiency
- **Resume**: Uploaded resumes
- **Education/Work Experience**: Stored in JSON fields

### Privacy Controls
- Encryption at rest for sensitive data
- User consent tracking via [`backend/app/models/consent.py`](backend/app/models/consent.py)
- GDPR-compliant data export/deletion

---

## 5. Compliance & Security

### Security Features
- **Data Minimization**: Only collect necessary data
- **Access Controls**: Role-based permissions
- **Audit Logging**: All data access logged
- **User Consent**: Explicit opt-in for data sharing

### Implementation Files
- [`backend/app/models/audit_log.py`](backend/app/models/audit_log.py) - Audit trail
- [`backend/app/utils/audit.py`](backend/app/utils/audit.py) - Audit decorators

---

## 6. User Onboarding Flow

### Step-by-Step Onboarding
The platform implements a comprehensive 8-step onboarding process:

| Step | Endpoint | Data Collected |
|------|----------|----------------|
| 1 | `POST /api/v1/onboarding/basic-info` | Name, summary, career goals |
| 2 | `POST /api/v1/onboarding/contact-info` | Phone, location, LinkedIn, GitHub |
| 3 | `POST /api/v1/onboarding/education` | Degree, institution, year, GPA |
| 4 | `POST /api/v1/onboarding/work-experience` | Job title, company, dates, bullets |
| 5 | `POST /api/v1/onboarding/skills` | Skills with proficiency levels |
| 6 | `POST /api/v1/onboarding/resume` | Primary resume selection |
| 7 | `POST /api/v1/onboarding/job-preferences` | Desired roles, locations, salary |
| 8 | `POST /api/v1/onboarding/platform-setup` | Auto-apply, notifications |

### Onboarding Status
- `GET /api/v1/onboarding/status` - Get current progress
- Returns: completed steps, current step, progress percentage

### Implementation Files
- [`backend/app/services/onboarding_service.py`](backend/app/services/onboarding_service.py) - Onboarding logic
- [`backend/app/api/routes/onboarding.py`](backend/app/api/routes/onboarding.py) - Onboarding API routes

---

## 7. AI-Powered Job Application

### Screening Question Answering
The AI assistant can answer job application screening questions based on user profile:

- **Service**: [`backend/app/services/screening_question_service.py`](backend/app/services/screening_question_service.py)
- **Features**:
  - Generates personalized answers based on user profile
  - Handles various question types (experience, authorization, salary, etc.)
  - Provides confidence scores for answers
  - Batch question answering

### API Endpoints
- `POST /api/v1/applications/answer-question` - Answer a single question
- `POST /api/v1/applications/prepare-answers` - Prepare answers for a job

---

## 8. Job Update Monitoring

### Monitor Service
Tracks application status and notifies users of updates:

- **Check Applications**: `GET /api/v1/applications/updates`
- **Recent Updates**: `GET /api/v1/applications/recent-updates?days=7`
- **New Matches**: `GET /api/v1/applications/new-matches`

### Status Tracking
- Applied → Viewed → Shortlisted → Interview → Offer/Rejected
- Automatic notifications for status changes

---

## 9. Technical Stack

### Backend
- **Framework**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT + bcrypt
- **Encryption**: cryptography (AES-256-GCM)
- **AI**: OpenAI/Groq API

### Frontend
- HTML/JavaScript dashboard
- RESTful API consumption
- Real-time notifications

### Deployment
- Python uvicorn server
- Celery for background tasks
- Playwright for browser automation

---

## 10. Phased Implementation

### MVP Phase
- [x] User registration/login
- [x] Basic profile storage
- [x] Resume upload
- [x] Job search and save

### Phase 1
- [x] Credentials vault with encryption
- [x] Comprehensive onboarding flow
- [x] AI screening question answering

### Phase 2
- [x] Audit logging
- [x] Consent management
- [x] Job update monitoring

### Phase 3 (Future)
- [ ] Multi-user support
- [ ] Advanced analytics
- [ ] Team collaboration

---

## API Reference Summary

### Authentication
```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

### Onboarding
```
GET  /api/v1/onboarding/status
POST /api/v1/onboarding/basic-info
POST /api/v1/onboarding/contact-info
POST /api/v1/onboarding/education
POST /api/v1/onboarding/work-experience
POST /api/v1/onboarding/skills
POST /api/v1/onboarding/resume
POST /api/v1/onboarding/job-preferences
POST /api/v1/onboarding/platform-setup
POST /api/v1/onboarding/complete
POST /api/v1/onboarding/complete-profile  # Bulk update
```

### Applications
```
GET  /api/v1/applications
POST /api/v1/applications
GET  /api/v1/applications/{id}
GET  /api/v1/applications/updates
GET  /api/v1/applications/recent-updates
GET  /api/v1/applications/new-matches
```

### Security
```
POST /api/v1/credentials
GET  /api/v1/credentials
DELETE /api/v1/credentials/{id}
POST /api/v1/consents
GET  /api/v1/consents
DELETE /api/v1/users/me  # GDPR deletion
```
