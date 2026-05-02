"""
HishabAI Backend — FastAPI Application Factory

Main entry point. Registers routers, middleware, exception handlers, and health checks.
"""

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.exceptions import HishabError

logger = structlog.get_logger()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="HishabAI API",
        description="Automated CA workflow platform for Bangladesh",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://localhost:3000",   # Alt dev port
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ────────────────────────────────────────────────

    @app.exception_handler(HishabError)
    async def hishab_error_handler(request: Request, exc: HishabError) -> JSONResponse:
        """Convert HishabError exceptions to standard API error responses."""
        logger.warning(
            "api_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all: log full traceback internally, return safe message to client."""
        logger.exception(
            "unhandled_error",
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                    "details": {},
                },
            },
        )

    # ── Health Checks ─────────────────────────────────────────────────────

    @app.get("/health", tags=["system"])
    async def health_check():
        """Basic health check — returns 200 if the server is running."""
        return {"status": "healthy", "service": "hishabai-api"}

    @app.get("/ready", tags=["system"])
    async def readiness_check():
        """Readiness check — verifies database connectivity."""
        from app.database import get_supabase_admin
        try:
            supabase = get_supabase_admin()
            # Simple query to verify DB is reachable
            supabase.table("tenants").select("id").limit(1).execute()
            return {"status": "ready", "database": "connected"}
        except Exception as e:
            logger.error("readiness_check_failed", error=str(e))
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": "disconnected"},
            )

    # ── Register Routers ──────────────────────────────────────────────────
    # These will be added as we build each module:
    # from app.tenants.router import router as tenants_router
    # from app.clients.router import router as clients_router
    # from app.documents.router import router as documents_router
    # from app.reconciliation.router import router as reconciliation_router
    # from app.notices.router import router as notices_router
    # from app.calendar.router import router as calendar_router
    # from app.reports.router import router as reports_router

    # app.include_router(tenants_router, prefix="/api/v1/tenant", tags=["tenant"])
    # app.include_router(clients_router, prefix="/api/v1/clients", tags=["clients"])
    # ...

    return app


app = create_app()
