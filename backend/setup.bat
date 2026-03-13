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

REM Check .env exists
if not exist .env (
    echo [ERROR] .env file not found!
    echo Copy .env.example to .env and fill in your values first.
    pause
    exit /b 1
)

echo [1/5] Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your internet connection.
    pause
    exit /b 1
)
echo.

echo [2/5] Installing Playwright browser (Chromium)...
python -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Playwright browser install failed.
    echo Try manually: python -m playwright install chromium
    pause
    exit /b 1
)
echo Chromium installed.
echo.

echo [3/5] Creating storage directories...
mkdir storage 2>nul
mkdir storage\resumes 2>nul
mkdir storage\cover_letters 2>nul
mkdir storage\recordings 2>nul
echo Storage directories ready.
echo.

echo [4/5] Running database migrations...
alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Migration failed. Check DATABASE_URL in .env
    echo Make sure PostgreSQL is running and the database exists:
    echo   psql -U postgres -c "CREATE DATABASE career_platform;"
    pause
    exit /b 1
)
echo Migrations complete.
echo.

echo [5/5] Setup complete!
echo.
echo Next steps:
echo   1. Run: start_platform.bat
echo   2. Open: http://localhost:8000/api/docs
echo   3. Register: POST /api/auth/register
echo   4. Set up profile: PATCH /api/profile  (skills, desired roles, etc.)
echo.
pause