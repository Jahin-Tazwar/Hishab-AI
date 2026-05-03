"""Tests for FastAPI auth/tenant dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.dependencies import (
    get_current_tenant_id,
    get_current_user,
    get_current_user_id,
)


def _make_jwt(sub: str) -> str:
    return jwt.encode(
        {"sub": sub, "aud": "authenticated", "exp": 9999999999},
        settings.SUPABASE_JWT_SECRET or "test-secret",
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "test-secret")


@pytest.mark.asyncio
async def test_get_current_user_decodes_valid_jwt() -> None:
    user_id = str(uuid4())
    token = _make_jwt(user_id)
    payload = await get_current_user(authorization=f"Bearer {token}")
    assert payload["sub"] == user_id


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_bearer() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization="not-a-bearer")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_returns_uuid() -> None:
    payload = {"sub": str(uuid4())}
    user_uuid = await get_current_user_id(user=payload)
    assert isinstance(user_uuid, UUID)


@pytest.mark.asyncio
async def test_get_current_tenant_id_does_not_block_event_loop() -> None:
    """
    Regression test: get_current_tenant_id calls the sync supabase-py client.
    It MUST wrap that call in asyncio.to_thread (or similar) to avoid blocking.
    We assert this by mocking asyncio.to_thread and verifying it gets invoked.
    """
    user_id = uuid4()
    tenant_id = uuid4()

    # Mock supabase chain: .table().select().eq().single().execute()
    mock_result = MagicMock()
    mock_result.data = {"tenant_id": str(tenant_id)}
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().single().execute.return_value = mock_result

    with patch("app.dependencies.get_supabase_admin", return_value=mock_supabase), \
         patch("app.dependencies.asyncio.to_thread", new=AsyncMock(return_value=mock_result)) as to_thread:
        result = await get_current_tenant_id(user_id=user_id)
        assert result == tenant_id
        assert to_thread.called, "Expected asyncio.to_thread to wrap the sync supabase call"
