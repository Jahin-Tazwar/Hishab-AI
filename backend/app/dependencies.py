"""
HishabAI Backend — FastAPI Dependencies

Shared dependencies for auth, tenant resolution, and database access.
Auth is validated against Supabase JWT.

Supabase issues two flavours of JWT depending on project age:

  * ES256 (asymmetric, modern projects since 2024) — verified against the
    project's public key fetched from /auth/v1/.well-known/jwks.json.
    PyJWKClient caches keys with automatic rotation.
  * HS256 (legacy projects, also used by our test suite) — verified
    against the shared SUPABASE_JWT_SECRET.

We dispatch on the `alg` claim in the JWT header so both kinds work.

IMPORTANT: supabase-py is sync. Every supabase client call inside an async
function MUST be wrapped in asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings
from app.database import get_supabase_admin


# JWKS client for ES256 verification — lazy-built so config edits at test
# time still take effect, and so we don't hit the network at import.
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        # PyJWKClient caches keys in memory; on a `kid` miss it auto-refetches.
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_client


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": message},
    )


async def get_current_user(
    authorization: str = Header(..., description="Bearer <supabase_jwt>"),
) -> dict[str, Any]:
    """Validates the Supabase JWT from the Authorization header. Returns decoded payload."""
    if not authorization.startswith("Bearer "):
        raise _unauthorized("Missing Bearer token")

    token = authorization.removeprefix("Bearer ").strip()

    # Inspect the header to decide which signing scheme to use. This is
    # safe pre-verification — we're only reading the `alg` field; we still
    # cryptographically verify below.
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"Invalid token: {exc}")

    alg = header.get("alg")

    try:
        if alg == "ES256":
            # Modern Supabase projects sign with the project's private key;
            # we verify with the public key from JWKS.
            jwks = _get_jwks_client()
            signing_key = await asyncio.to_thread(
                jwks.get_signing_key_from_jwt, token
            )
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
            )
        elif alg == "HS256":
            # Legacy / test path.
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            raise _unauthorized(f"Unsupported JWT alg: {alg}")
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"Invalid token: {exc}")

    return payload


async def get_current_user_id(
    user: dict[str, Any] = Depends(get_current_user),
) -> UUID:
    """Extracts the user UUID from the validated Supabase JWT."""
    return UUID(user["sub"])


async def get_current_tenant_id(
    user_id: UUID = Depends(get_current_user_id),
) -> UUID:
    """
    Looks up the tenant_id for the authenticated user from user_profiles.
    Raises 403 if user has no tenant association.

    The supabase-py call is sync, so we wrap it in asyncio.to_thread.
    """
    supabase = get_supabase_admin()

    def _query() -> Any:
        return (
            supabase.table("user_profiles")
            .select("tenant_id")
            .eq("id", str(user_id))
            .single()
            .execute()
        )

    result = await asyncio.to_thread(_query)

    if not result.data or not result.data.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_NOT_FOUND",
                "message": "User is not associated with any firm. Complete onboarding first.",
            },
        )

    return UUID(result.data["tenant_id"])


def require_role(*allowed_roles: str):
    """Dependency factory: restricts endpoint to specific user roles."""

    async def _check_role(
        user_id: UUID = Depends(get_current_user_id),
    ) -> str:
        supabase = get_supabase_admin()

        def _query() -> Any:
            return (
                supabase.table("user_profiles")
                .select("role")
                .eq("id", str(user_id))
                .single()
                .execute()
            )

        result = await asyncio.to_thread(_query)

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "User profile not found"},
            )

        role = result.data["role"]
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": (
                        f"Role '{role}' does not have access. "
                        f"Required: {', '.join(allowed_roles)}"
                    ),
                },
            )
        return role

    return _check_role


async def set_request_user(user_id: UUID) -> None:
    """
    Sets the request.jwt.claim.sub Postgres setting via the set_request_user RPC.

    Backend MUST call this before any service-role write so the audit trigger
    captures the correct user_id. Effective only within the same transaction —
    keep the subsequent write in the same supabase-py client session.

    See migrations/0006_set_request_user.sql.
    """
    supabase = get_supabase_admin()

    def _call() -> None:
        supabase.rpc("set_request_user", {"p_user_id": str(user_id)}).execute()

    await asyncio.to_thread(_call)
