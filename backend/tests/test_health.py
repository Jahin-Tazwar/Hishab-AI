"""Smoke tests for /health and /ready endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import __version__
from app.main import app


def test_health_returns_200_with_version() -> None:
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["service"] == "hishabai-api"
    assert body["version"] == __version__


def test_ready_returns_200_when_supabase_reachable() -> None:
    """When the Supabase ping succeeds, /ready returns 200 with version."""
    fake_supabase = MagicMock()
    fake_supabase.table.return_value.select.return_value.limit.return_value.execute.return_value = (
        MagicMock(data=[])
    )

    with patch("app.main.get_supabase_admin", return_value=fake_supabase):
        client = TestClient(app)
        res = client.get("/ready")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"
        assert body["version"] == __version__


def test_ready_returns_503_when_supabase_unreachable() -> None:
    """When the Supabase ping raises, /ready returns 503."""
    fake_supabase = MagicMock()
    fake_supabase.table.side_effect = RuntimeError("connection refused")

    with patch("app.main.get_supabase_admin", return_value=fake_supabase):
        client = TestClient(app)
        res = client.get("/ready")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "not_ready"
