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
    logger.info(f"Starting {settings.APP_NAME}", env=settings.APP_ENV)

    if not await check_db_connection():
        logger.error("Database connection failed — check DATABASE_URL in .env")
        raise RuntimeError("Database unavailable")
    logger.info("Database connected")

    if settings.APP_ENV == "development":
        await init_db()
        logger.info("Database tables initialized")

    _ = settings.resumes_path
    _ = settings.cover_letters_path
    _ = settings.recordings_path
    logger.info("Storage directories ready")

    yield

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

    # ── CORS ──────────────────────────────────────────────────
    # FIX: allow_credentials=True is incompatible with allow_origins=["*"].
    # Browsers reject that combination per the CORS spec.
    # Use explicit origins in production; keep wildcard only for local dev
    # where credentials are not needed.
    allowed_origins = (
        ["*"] if settings.APP_ENV == "development"
        else [o.strip() for o in settings.SECRET_KEY.split(",") if o.strip().startswith("http")]
        # Replace the above with a real ALLOWED_ORIGINS setting in production.
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=settings.APP_ENV != "development",  # False when wildcard
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "error": str(exc) if settings.DEBUG else "",
            },
        )

    # ── Routers ───────────────────────────────────────────────
    from app.api.routes.auth import router as auth_router
    from app.api.routes.jobs import router as jobs_router
    from app.api.routes.profile import router as profile_router
    from app.api.routes.security import router as security_router
    from app.api.routes.onboarding import router as onboarding_router
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
    app.include_router(onboarding_router, prefix=API_PREFIX)
    app.include_router(jobs_router, prefix=API_PREFIX)
    app.include_router(profile_router, prefix=API_PREFIX)
    app.include_router(security_router, prefix=API_PREFIX)
    app.include_router(applications_router, prefix=API_PREFIX)
    app.include_router(resumes_router, prefix=API_PREFIX)
    app.include_router(cover_letters_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(analytics_router, prefix=API_PREFIX)
    app.include_router(chat_router, prefix=API_PREFIX)

    # ── Health check ──────────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health():
        db_ok = await check_db_connection()
        return {
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "disconnected",
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
        }

    # ── Dashboard ─────────────────────────────────────────────
    @app.get("/dashboard", tags=["System"])
    async def dashboard():
        dashboard_path = Path(__file__).parent.parent / "dashboard.html"
        if not dashboard_path.exists():
            return JSONResponse(
                status_code=404,
                content={"detail": "dashboard.html not found."},
            )
        return FileResponse(str(dashboard_path), media_type="text/html")

    @app.get("/", tags=["System"])
    async def root():
        return {
            "app": settings.APP_NAME,
            "dashboard": "/dashboard",
            "onboarding": "/onboarding",
            "docs": "/api/docs",
            "health": "/health",
        }

    @app.get("/onboarding", tags=["System"])
    async def onboarding_page():
        onboarding_path = Path(__file__).parent.parent / "frontend" / "onboarding.html"
        if not onboarding_path.exists():
            return JSONResponse(
                status_code=404,
                content={"detail": "onboarding.html not found."},
            )
        return FileResponse(str(onboarding_path), media_type="text/html")

    return app


app = create_app()