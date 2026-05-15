"""End-to-end API tests using FastAPI TestClient.

Gated on the same env-var pack as persistence tests because endpoints
require a real DB and storage. Stubs LLM via set_llm_adapter.
"""
from __future__ import annotations

import io
import os
from datetime import date
from uuid import UUID

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="API tests require a live Supabase",
)


def _canonical_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    ws.append(["INV-API", "111222333", "Test Supplier",
               "2026-05-10", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


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


def test_create_job_accepts_canonical_xlsx(client, auth_headers, tenant_id, client_id):
    files = [
        ("files", ("register.xlsx", _canonical_xlsx(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
    ]
    data = {
        "client_id": str(client_id),
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "kind": "purchase_register",
    }
    res = client.post("/api/v1/ingestion/jobs", data=data, files=files,
                      headers=auth_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert "job_id" in body
    assert len(body["files"]) == 1
    assert body["files"][0]["accepted"] is True


def test_create_job_rejects_unsupported_mime(client, auth_headers, client_id):
    files = [("files", ("malware.zip", b"PK\x03\x04...", "application/zip"))]
    data = {
        "client_id": str(client_id),
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "kind": "purchase_register",
    }
    res = client.post("/api/v1/ingestion/jobs", data=data, files=files,
                      headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["files"][0]["accepted"] is False
    assert "unsupported" in body["files"][0]["rejection_reason"].lower()
