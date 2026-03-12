@echo off
REM ═══════════════════════════════════════════════════════════
REM  AI Career Platform — First Time Setup Script
REM  Run ONCE after placing all files in backend\ folder
REM  Usage: setup.bat
REM ═══════════════════════════════════════════════════════════

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   AI Career Platform - First Time Setup  ║
echo  ╚══════════════════════════════════════════╝
echo.

REM Activate virtual environment
call venv\Scripts\activate
if errorlevel 1 (
    echo [ERROR] Virtual environment not found.
    echo Please run: python -m venv venv
    pause
    exit /b 1
)

echo [1/4] Installing Python packages...
pip install fastapi uvicorn[standard] sqlalchemy asyncpg alembic psycopg2-binary pydantic pydantic-settings python-dotenv celery redis openai tiktoken python-multipart aiofiles httpx passlib python-jose bcrypt APScheduler beautifulsoup4 lxml aiosmtplib jinja2 structlog tenacity aiohttp fake-useragent python-telegram-bot
echo.

echo [2/4] Creating storage directories...
mkdir storage 2>nul
mkdir storage\resumes 2>nul
mkdir storage\cover_letters 2>nul
mkdir storage\recordings 2>nul
echo Storage directories created.
echo.

echo [3/4] Running database migrations...
alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Migration failed. Check your DATABASE_URL in .env
    echo Make sure PostgreSQL is running and career_platform database exists.
    pause
    exit /b 1
)
echo Migrations complete.
echo.

echo [4/4] Setup complete!
echo.
echo Next steps:
echo   1. Run: start_platform.bat
echo   2. Open: http://localhost:8000/api/docs
echo   3. Register your account at POST /api/auth/register
echo.
pause