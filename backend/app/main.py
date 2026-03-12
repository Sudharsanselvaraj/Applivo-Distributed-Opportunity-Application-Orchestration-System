"""
app/main.py
────────────
FastAPI application factory.
Registers all routers, middleware, startup/shutdown events.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import settings
from app.core.database import check_db_connection, close_db, init_db

logger = structlog.get_logger()


# ── Lifespan (startup + shutdown) ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    # ── STARTUP ──────────────────────────────
    logger.info(f"Starting {settings.APP_NAME}", env=settings.APP_ENV)

    # Check database
    if not await check_db_connection():
        logger.error("Database connection failed — check DATABASE_URL in .env")
        raise RuntimeError("Database unavailable")
    logger.info("Database connected")

    # Create tables in development
    if settings.APP_ENV == "development":
        await init_db()
        logger.info("Database tables initialized")

    # Ensure storage directories exist
    _ = settings.resumes_path
    _ = settings.cover_letters_path
    _ = settings.recordings_path
    logger.info("Storage directories ready")

    yield

    # ── SHUTDOWN ─────────────────────────────
    await close_db()
    logger.info("Database connections closed")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Personal AI Career Automation Platform API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler ──────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error", "error": str(exc) if settings.DEBUG else ""},
        )

    # ── Routers ───────────────────────────────
    from app.api.routes.auth import router as auth_router
    from app.api.routes.jobs import router as jobs_router
    from app.api.routes.routes import (
        applications_router,
        resumes_router,
        cover_letters_router,
        agent_router,
        analytics_router,
        chat_router,
    )

    API_PREFIX = "/api"
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(jobs_router, prefix=API_PREFIX)
    app.include_router(applications_router, prefix=API_PREFIX)
    app.include_router(resumes_router, prefix=API_PREFIX)
    app.include_router(cover_letters_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(analytics_router, prefix=API_PREFIX)
    app.include_router(chat_router, prefix=API_PREFIX)

    # ── Health check ──────────────────────────
    @app.get("/health", tags=["System"])
    async def health():
        db_ok = await check_db_connection()
        return {
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "disconnected",
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
        }

    # ── Dashboard ─────────────────────────────
    @app.get("/dashboard", tags=["System"])
    async def dashboard():
        """Serve the CareerOS frontend dashboard."""
        dashboard_path = Path(__file__).parent.parent / "dashboard.html"
        if not dashboard_path.exists():
            return JSONResponse(
                status_code=404,
                content={"detail": "dashboard.html not found. Place it in the backend/ folder."}
            )
        return FileResponse(str(dashboard_path), media_type="text/html")

    @app.get("/", tags=["System"])
    async def root():
        return {
            "app": settings.APP_NAME,
            "dashboard": "/dashboard",
            "docs": "/api/docs",
            "health": "/health",
        }

    return app


app = create_app()