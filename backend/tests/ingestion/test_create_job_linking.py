"""Validation tests for the new linked_pr_job_id + reuse_*_doc_id fields.

Live-DB tests gated by INGESTION_TEST_SUPABASE_URL / INGESTION_TEST_USER_JWT
(same as test_api.py).
"""
from __future__ import annotations

import io
import os
import uuid as _uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Linking tests require live Supabase",
)


def _canonical_pr() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    ws.append(["INV-LNK", "111222333", "Lnk Supplier",
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


def _create_pr_job(client, auth_headers, client_id) -> str:
    files = [("files", ("pr.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "purchase_register",
        },
        files=files, headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["job_id"]


def test_linked_pr_job_id_must_point_to_a_purchase_register_job(
    client, auth_headers, client_id,
):
    # Create an SF job first, then try to link a NEW SF job to it (wrong kind).
    files = [("files", ("sf.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
        },
        files=files, headers=auth_headers,
    )
    bogus_sf_id = res.json()["job_id"]

    files2 = [("files", ("sf2.xlsx", _canonical_pr(),
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res2 = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "linked_pr_job_id": bogus_sf_id,
        },
        files=files2, headers=auth_headers,
    )
    assert res2.status_code == 422
    body = res2.json()
    assert body["detail"]["code"] == "INGESTION_BAD_LINKAGE"


def test_linked_pr_job_id_rejected_on_pr_kind(
    client, auth_headers, client_id,
):
    pr_id = _create_pr_job(client, auth_headers, client_id)
    files = [("files", ("pr2.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "purchase_register",
            "linked_pr_job_id": pr_id,
        },
        files=files, headers=auth_headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INGESTION_BAD_LINKAGE"


def test_linked_pr_job_id_rejected_when_already_linked(
    client, auth_headers, client_id,
):
    pr_id = _create_pr_job(client, auth_headers, client_id)
    files = [("files", ("sf.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    ok = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "linked_pr_job_id": pr_id,
        },
        files=files, headers=auth_headers,
    )
    assert ok.status_code == 201, ok.text

    files2 = [("files", ("sf2.xlsx", _canonical_pr(),
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    dup = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "linked_pr_job_id": pr_id,
        },
        files=files2, headers=auth_headers,
    )
    assert dup.status_code == 422
    assert dup.json()["detail"]["code"] == "INGESTION_DUPLICATE_LINKAGE"


def test_reuse_doc_id_unknown_doc_rejected(
    client, auth_headers, client_id,
):
    fake_doc = str(_uuid.uuid4())
    files = [("files", ("sf.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "reuse_pr_doc_id": fake_doc,
        },
        files=files, headers=auth_headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INGESTION_BAD_REUSE"
