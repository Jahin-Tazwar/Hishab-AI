"""
HishabAI Backend — Supabase Client Factory

Single access pattern: supabase-py.
- get_supabase_admin(): service-role client (bypasses RLS) — backend-only.
- get_supabase_user(token): user-scoped client (RLS-enforced via the user's JWT).
"""

from supabase import Client as SupabaseClient
from supabase import create_client

from app.config import settings

_admin_client: SupabaseClient | None = None


def get_supabase_admin() -> SupabaseClient:
    """
    Returns a Supabase client using the service-role key.
    BYPASSES RLS — use only in backend code that has independently validated tenant scope.
    Never expose the service-role key to the frontend.
    """
    global _admin_client
    if _admin_client is None:
        _admin_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _admin_client


def get_supabase_user(access_token: str) -> SupabaseClient:
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
