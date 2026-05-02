"""
HishabAI Backend — Application Settings

All configuration via environment variables.
Uses Supabase for auth, database, and storage.
Uses Vertex AI (Gemini 2.5 Flash) for LLM.
"""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Supabase ──────────────────────────────────────────────────────────
    SUPABASE_URL: str = "https://qlrqbqisavkfxywkiuca.supabase.co"
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # Server-side only, never expose
    SUPABASE_JWT_SECRET: str = ""  # For JWT validation

    # Direct DB connection (for SQLAlchemy complex queries)
    DATABASE_URL: str = ""  # postgresql+asyncpg://...@db.qlrqbqisavkfxywkiuca.supabase.co:5432/postgres

    # ── Redis (for Celery task queue) ─────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Vertex AI (Gemini) ────────────────────────────────────────────────
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "asia-southeast1"  # Closest to Bangladesh
    VERTEX_AI_MODEL: str = "gemini-2.5-flash"

    # ── Email ─────────────────────────────────────────────────────────────
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "noreply@hishabai.com"

    # ── App ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 20
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"

    # ── Feature Flags ─────────────────────────────────────────────────────
    FEATURE_MIS_REPORTS: bool = True

    # ── Rate Limits (per tenant per hour) ─────────────────────────────────
    RATE_LIMIT_DOCUMENT_UPLOAD: int = 50
    RATE_LIMIT_AI_DRAFT: int = 20
    RATE_LIMIT_RECONCILIATION: int = 10
    RATE_LIMIT_API_GLOBAL: int = 500

    # ── Supabase Storage ──────────────────────────────────────────────────
    STORAGE_BUCKET: str = "documents"

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
