"""
HishabAI Backend — FastAPI Application Factory

Main entry point. Registers routers, middleware, exception handlers, and health checks.
"""

import asyncio
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.exceptions import HishabError
from app.database import get_supabase_admin

logger = structlog.get_logger()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to every request and response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        # Bind to structlog context so all logs in this request carry the id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="HishabAI API",
        description="Automated CA workflow platform for Bangladesh",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    )

    # ── Middleware (registered in reverse order of execution) ─────────────
    app.add_middleware(RequestIdMiddleware)

    # Build allow-origins from a static dev list plus an optional production
    # origin set via FRONTEND_ORIGIN. Setting FRONTEND_ORIGIN on Render after
    # the first frontend deploy avoids a code change.
    import os
    cors_origins = [
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # Alt dev port
    ]
    prod_origin = os.environ.get("FRONTEND_ORIGIN", "").strip()
    if prod_origin:
        cors_origins.append(prod_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ────────────────────────────────────────────────

    @app.exception_handler(HishabError)
    async def hishab_error_handler(request: Request, exc: HishabError) -> JSONResponse:
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
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
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
        from app import __version__
        return {"status": "healthy", "service": "hishabai-api", "version": __version__}

    @app.get("/ready", tags=["system"])
    async def readiness_check():
        """Readiness check — verifies database connectivity (async-safe)."""
        try:
            supabase = get_supabase_admin()
            # Wrap sync supabase call in to_thread to avoid blocking the event loop
            await asyncio.to_thread(
                lambda: supabase.table("tenants").select("id").limit(1).execute()
            )
            from app import __version__
            return {"status": "ready", "database": "connected", "version": __version__}
        except Exception as exc:
            logger.error("readiness_check_failed", error=str(exc))
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": "disconnected"},
            )

    # ── Routers ───────────────────────────────────────────────────────────
    from app.reconciliation.router import router as reconciliation_router
    app.include_router(reconciliation_router)

    return app


app = create_app()


if __name__ == "__main__":
    # Allow `python -m app.main` from the `backend/` directory.
    # For day-to-day dev prefer: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
    # Note: `python app/main.py` will NOT work — Python can't resolve the `app.*` package
    # imports when main.py is run as a top-level script. Always run from `backend/` as a module.
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
    )
