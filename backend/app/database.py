"""
HishabAI Backend — Database & Supabase Client Factory

Two access patterns:
1. supabase-py client — for auth validation, storage operations, simple CRUD
2. SQLAlchemy async — for complex business logic (reconciliation, aggregations)

Both connect to the same Supabase PostgreSQL instance.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from supabase import create_client, Client as SupabaseClient

from app.config import settings

# ── Supabase Client (admin/service-role) ──────────────────────────────────

_supabase_admin: SupabaseClient | None = None


def get_supabase_admin() -> SupabaseClient:
    """
    Returns a Supabase client using the service_role key.
    This bypasses RLS — use ONLY in backend server-side code.
    Never expose the service_role key to the frontend.
    """
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_admin


def get_supabase_client_for_user(access_token: str) -> SupabaseClient:
    """
    Returns a Supabase client authenticated as a specific user.
    RLS policies will be enforced based on the user's JWT.
    """
    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )
    client.auth.set_session(access_token, "")
    return client


# ── SQLAlchemy Async Engine (for complex queries) ─────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.ENVIRONMENT == "development"),
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
) if settings.DATABASE_URL else None

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
) if engine else None


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models (used for complex query mapping)."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: provides an async SQLAlchemy session.
    Used for complex queries (reconciliation, aggregations, joins).
    For simple CRUD, prefer the Supabase client.
    """
    if async_session_factory is None:
        raise RuntimeError(
            "DATABASE_URL not configured. Set it in .env for direct DB access."
        )
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
