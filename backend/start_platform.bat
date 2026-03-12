@echo off
REM ═══════════════════════════════════════════════════════════
REM  AI Career Platform — Windows Startup Script
REM  Run this from inside your backend\ folder
REM  Usage: start_platform.bat
REM ═══════════════════════════════════════════════════════════

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║    AI Career Platform - Starting Up      ║
echo  ╚══════════════════════════════════════════╝
echo.

REM Activate virtual environment
call venv\Scripts\activate

REM Check if .env exists
if not exist .env (
    echo [ERROR] .env file not found!
    echo Please copy .env.example to .env and fill in your values.
    pause
    exit /b 1
)

echo [1/4] Starting FastAPI server...
start "Career API" cmd /k "venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"

timeout /t 3 /nobreak > nul

echo [2/4] Starting Celery AI Worker...
start "Celery AI" cmd /k "venv\Scripts\activate && celery -A app.agents.tasks.celery_app worker --loglevel=info --pool=solo -Q ai,default -n worker_ai@%%h"

timeout /t 2 /nobreak > nul

echo [3/4] Starting Celery Scraping Worker...
start "Celery Scraping" cmd /k "venv\Scripts\activate && celery -A app.agents.tasks.celery_app worker --loglevel=info --pool=solo -Q scraping,automation,notifications -n worker_scraping@%%h"

timeout /t 2 /nobreak > nul

echo [4/4] Starting Celery Beat Scheduler...
start "Celery Beat" cmd /k "venv\Scripts\activate && celery -A app.agents.tasks.celery_app beat --loglevel=info"

echo.
echo  ✅ All services started!
echo.
echo  API Docs:    http://localhost:8000/api/docs
echo  Health:      http://localhost:8000/health
echo.
echo  Close the terminal windows to stop each service.
pause