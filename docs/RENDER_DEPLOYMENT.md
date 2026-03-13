# Deploying to Render - Database Setup Guide

## Database Options on Render

Render offers two main database options:

### 1. Managed PostgreSQL (Recommended)

**Steps:**
1. Create a new PostgreSQL service on Render
2. Get the connection string from Render dashboard
3. Set as environment variable in your web service

**Pros:**
- Fully managed, auto-scaling
- Automated backups
- Easy setup

**Cons:**
- Paid ($7/month for starter plan)

---

## Environment Variables Needed

Create these in Render dashboard:

```env
# Database - Get from Render PostgreSQL dashboard
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Security - Generate a strong random key
SECRET_KEY=your-random-secret-key-min-32-chars

# Encryption - Generate a 32-byte key (base64 encoded)
ENCRYPTION_KEY=your-32-byte-base64-encryption-key

# OpenAI API Key
OPENAI_API_KEY=sk-...

# Optional: Telegram Bot
TELEGRAM_BOT_TOKEN=...

# Optional: Email (SMTP)
SMTP_USERNAME=...
SMTP_PASSWORD=...
```

---

## How to Generate Keys

### SECRET_KEY (Django/FastAPI secret)
```bash
# Run this in terminal
python -c "import secrets; print(secrets.token_hex(32))"
```

### ENCRYPTION_KEY (For AES-256 encryption)
```bash
# Run this in terminal  
python -c "import base64; import secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

---

## Deploy Steps

### 1. Push Code to GitHub
```bash
git add .
git commit -m "Ready for production"
git push origin main
```

### 2. Create Render Web Service
1. Go to https://dashboard.render.com
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3.11

### 3. Add Environment Variables
In Render dashboard → Your Web Service → Environment:
- Add all environment variables from above
- DATABASE_URL will come from your PostgreSQL

### 4. Create PostgreSQL Database
1. In Render dashboard → "New" → "PostgreSQL"
2. Configure: name, region (same as web service)
3. Once created, copy "Internal Database URL"
4. Add as DATABASE_URL in your web service env vars

### 5. Run Migrations
Add a **Post-Deploy Command** in Render:
```bash
alembic upgrade head
```

Or SSH into the service and run:
```bash
python -c "import asyncio; from app.core.database import init_db; asyncio.run(init_db())"
```

---

## File Storage (Resumes)

For storing uploaded resumes on Render, you have options:

### Option A: Render Disk (Ephemeral - not recommended)
- Files deleted on deploy/restart
- Not suitable for production

### Option B: AWS S3 (Recommended)
```python
# In config.py, add:
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET_NAME=careeros-resumes
S3_RESUME_PATH=https://careeros-resumes.s3.amazonaws.com/
```

### Option C: Cloudinary
```python
# For smaller files
CLOUDINARY_URL=...
```

---

## Production Checklist

- [ ] PostgreSQL database created
- [ ] DATABASE_URL set
- [ ] SECRET_KEY generated and set
- [ ] ENCRYPTION_KEY generated and set
- [ ] OPENAI_API_KEY set
- [ ] ALLOWED_HOSTS updated (for production)
- [ ] Debug set to False in production
- [ ] Alembic migrations run

---

## Troubleshooting

### "Database connection failed"
- Check DATABASE_URL is correct
- Ensure PostgreSQL is in same region as web service
- Wait 2-3 minutes for PostgreSQL to initialize

### "Permission denied" on migrations
- Add to your alembic/env.py:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Static files not loading
- In production, serve static files via CDN or Nginx
- Or add: `app.mount("/static", StaticFiles(directory="static"), tags=["Static"])`
