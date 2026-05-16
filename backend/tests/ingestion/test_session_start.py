"""API tests for POST /api/v1/ingestion/sessions/start."""
from __future__ import annotations

import os
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Session-start tests require live Supabase",
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


def test_fresh_both_returns_pr_job_id(client, auth_headers, client_id):
    res = client.post(
        "/api/v1/ingestion/sessions/start",
        json={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pr_job_id"] is not None
    assert body["sf_job_id"] is None
    assert body["reconciliation_id"] is None


def test_reuse_doc_id_validates_kind(client, auth_headers, client_id):
    res = client.post(
        "/api/v1/ingestion/sessions/start",
        json={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "reuse_pr_doc_id": str(_uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INGESTION_BAD_REUSE"


def test_period_end_before_start_rejected(client, auth_headers, client_id):
    res = client.post(
        "/api/v1/ingestion/sessions/start",
        json={
            "client_id": str(client_id),
            "period_start": "2026-05-31",
            "period_end": "2026-05-01",
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
