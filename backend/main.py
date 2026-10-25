"""
OmniSight — FastAPI Application Entry Point
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Main application module that bootstraps the FastAPI server with:
- CORS middleware for frontend communication
- Health check endpoint
- API route registration
- Startup/shutdown lifecycle events
- Structured logging
"""

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router as api_router
from backend.core.config import get_settings
from backend.core.logging import setup_logging
from backend.db.database import init_db
from backend.db.database import engine
import backend.models.models  # Import to register models with SQLAlchemy Base
from sqlalchemy import text

# Load settings & configure logging
settings = get_settings()
setup_logging(level=settings.log_level)
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Create necessary directories
os.makedirs("output", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup initialization and graceful shutdown.
    """
    logger.info("🚀 Starting OmniSight v%s", settings.app_version)
    logger.info("📡 Staging URL: %s", settings.staging_url)
    logger.info("🤖 Gemini configured: %s", settings.is_gemini_configured)
    logger.info("🐙 GitHub configured: %s", settings.is_github_configured)
    logger.info("🗄️  Database: %s", settings.database_url)

    # Initialize database tables
    await init_db()

    # Clean up any orphaned scans from previous server restarts
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE scan_runs SET status = 'failed' WHERE UPPER(status) IN ('RUNNING', 'PENDING')")
            )
        logger.info("🧹 Cleaned up orphaned scan runs on startup")
    except Exception as e:
        logger.warning("Could not clean up orphaned scan runs: %s", e)
    
    yield

    logger.info("👋 Shutting down OmniSight...")


app = FastAPI(
    title="OmniSight API",
    description=(
        "Multimodal UI Self-Healing & RPA Agent — "
        "Automatically detects UI bugs using Vision-Language Models "
        "and generates fix PRs via GitHub."
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
)


# No-cache static files handler to prevent browser caching of live demo assets
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Any):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


# Static files for screenshots and mock app
app.mount("/static", StaticFiles(directory="output"), name="static")
app.mount("/mock-app", NoCacheStaticFiles(directory="mock-app"), name="mock-app")

# Register API routes
app.include_router(api_router)

from backend.api.webhook import router as webhook_router
app.include_router(webhook_router, prefix="/api/v1")

from backend.api.design_routes import design_router
app.include_router(design_router)


@app.get(
    "/health",
    tags=["system"],
    summary="Health check",
    response_description="Service health status",
)
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint.
    Returns the current service status, version, and uptime info.
    Includes a real database connectivity check.
    """
    db_status = "disconnected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "gemini": "configured" if settings.is_gemini_configured else "missing_key",
            "github": "configured" if settings.is_github_configured else "missing_key",
            "database": db_status,
        },
    }


@app.get("/", tags=["system"], include_in_schema=False)
async def root() -> dict[str, str]:
    """Redirect root to API documentation."""
    return {
        "message": f"Welcome to {settings.app_name} API v{settings.app_version}",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level=settings.log_level.lower(),
    )
