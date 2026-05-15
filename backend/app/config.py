"""
HishabAI Backend — Application Settings

All configuration via environment variables.
Uses Supabase for auth, database, and storage.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Supabase ──────────────────────────────────────────────────────────
    SUPABASE_URL: str = "https://qlrqbqisavkfxywkiuca.supabase.co"
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # Server-side only, never expose
    SUPABASE_JWT_SECRET: str = ""        # For JWT validation

    # ── App ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 20
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    FRONTEND_ORIGIN: str = ""

    # ── Supabase Storage ──────────────────────────────────────────────────
    STORAGE_BUCKET: str = "documents"

    # ── Ingestion (Phase F) ───────────────────────────────────────────────
    # Tolerate the optional ingestion env vars so they can live in the same
    # .env without raising "extra_forbidden". The ingestion module reads
    # these directly via os.environ; we don't need to surface them here.
    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
