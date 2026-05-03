"""Tests for request_id middleware and updated /ready endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def test_response_has_request_id_header(client: TestClient) -> None:
    """Every response should carry an X-Request-ID header."""
    response = client.get("/health")
    assert "x-request-id" in {k.lower() for k in response.headers.keys()}
    request_id = response.headers["x-request-id"]
    assert len(request_id) > 0


def test_request_id_is_unique_per_request(client: TestClient) -> None:
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_ready_uses_async_supabase_call(client: TestClient) -> None:
    """
    /ready must wrap its sync supabase call in asyncio.to_thread.
    Same regression as get_current_tenant_id.
    """
    mock_supabase = MagicMock()
    mock_supabase.table().select().limit().execute.return_value = MagicMock(data=[])

    with patch("app.main.get_supabase_admin", return_value=mock_supabase), \
         patch("app.main.asyncio.to_thread", new=AsyncMock(return_value=MagicMock(data=[]))) as to_thread:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert to_thread.called, "Expected asyncio.to_thread to wrap the sync supabase call"
