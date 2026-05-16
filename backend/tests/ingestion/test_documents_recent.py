"""API test for GET /api/v1/ingestion/documents/recent."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Recent-docs test requires live Supabase",
)


@pytest.fixture
def client():
    set_llm_adapter(StubLLMAdapter())
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = os.environ.get("INGESTION_TEST_USER_JWT")
    if not token:
        pytest.skip("INGESTION_TEST_USER_JWT required")
    return {"Authorization": f"Bearer {token}"}


def test_recent_docs_endpoint_returns_pr_and_sf_keys(
    client, auth_headers, client_id,
):
    res = client.get(
        "/api/v1/ingestion/documents/recent",
        params={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert "pr" in body
    assert "sf" in body


def test_recent_docs_rejects_missing_client_id(client, auth_headers):
    res = client.get(
        "/api/v1/ingestion/documents/recent",
        params={"period_start": "2026-05-01", "period_end": "2026-05-31"},
        headers=auth_headers,
    )
    assert res.status_code == 422
