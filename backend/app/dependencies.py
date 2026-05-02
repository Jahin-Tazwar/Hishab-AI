"""
HishabAI Backend — FastAPI Dependencies

Shared dependencies for auth, tenant resolution, and database access.
Auth is validated against Supabase JWT.
"""

from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings
from app.database import get_supabase_admin


async def get_current_user(
    authorization: str = Header(..., description="Bearer <supabase_jwt>"),
) -> dict[str, Any]:
    """
    Validates the Supabase JWT from the Authorization header.
    Returns the decoded payload with user ID and metadata.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing Bearer token"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Token expired"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": f"Invalid token: {e}"},
        )

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
    """
    supabase = get_supabase_admin()
    result = (
        supabase.table("user_profiles")
        .select("tenant_id")
        .eq("id", str(user_id))
        .single()
        .execute()
    )

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
    """
    Dependency factory: restricts endpoint to specific user roles.
    Usage: Depends(require_role("firm_admin", "senior_ca"))
    """

    async def _check_role(
        user_id: UUID = Depends(get_current_user_id),
    ) -> str:
        supabase = get_supabase_admin()
        result = (
            supabase.table("user_profiles")
            .select("role")
            .eq("id", str(user_id))
            .single()
            .execute()
        )

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
                    "message": f"Role '{role}' does not have access. Required: {', '.join(allowed_roles)}",
                },
            )
        return role

    return _check_role
