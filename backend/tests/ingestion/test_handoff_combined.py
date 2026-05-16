"""End-to-end handoff tests for the combined-doc path matrix.

Live-DB; seeds two confirmed jobs (PR + SF linked), finalizes the SF, and
asserts both jobs end at status=completed with the same reconciliation_id.
"""
from __future__ import annotations

import io
import os

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Handoff tests require live Supabase",
)


def _canonical_pr() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    ws.append(["INV-HC", "111222333", "HC Supplier",
               "2026-05-10", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _canonical_sf() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Invoice Date",
               "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN"])
    ws.append(["INV-HC", "2026-05-10", 1000, 150, "999000111"])
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


def _confirm_all_rows(client, auth_headers, job_id: str) -> None:
    res = client.get(
        f"/api/v1/ingestion/jobs/{job_id}/rows",
        params={"filter": "all"}, headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    row_ids = [r["id"] for r in res.json()["rows"]]
    if not row_ids:
        return
    bulk = client.post(
        f"/api/v1/ingestion/jobs/{job_id}/rows/bulk-confirm",
        json={"row_ids": row_ids}, headers=auth_headers,
    )
    assert bulk.status_code == 200, bulk.text


def _wait_extracted(client, auth_headers, job_id: str, timeout_s: int = 30) -> None:
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = client.get(f"/api/v1/ingestion/jobs/{job_id}", headers=auth_headers)
        if res.json()["job"]["status"] == "ready_for_review":
            return
        time.sleep(0.5)
    pytest.fail(f"Job {job_id} did not reach ready_for_review in {timeout_s}s")


def test_combined_finalize_completes_both_jobs(client, auth_headers, client_id):
    files_pr = [("files", ("pr.xlsx", _canonical_pr(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    pr_res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-06-01", "period_end": "2026-06-30",
            "kind": "purchase_register",
        },
        files=files_pr, headers=auth_headers,
    )
    assert pr_res.status_code == 201, pr_res.text
    pr_job_id = pr_res.json()["job_id"]
    _wait_extracted(client, auth_headers, pr_job_id)
    _confirm_all_rows(client, auth_headers, pr_job_id)

    files_sf = [("files", ("sf.xlsx", _canonical_sf(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    sf_res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-06-01", "period_end": "2026-06-30",
            "kind": "supplier_export",
            "linked_pr_job_id": pr_job_id,
        },
        files=files_sf, headers=auth_headers,
    )
    assert sf_res.status_code == 201, sf_res.text
    sf_job_id = sf_res.json()["job_id"]
    _wait_extracted(client, auth_headers, sf_job_id)
    _confirm_all_rows(client, auth_headers, sf_job_id)

    fin = client.post(
        f"/api/v1/ingestion/jobs/{sf_job_id}/finalize",
        headers=auth_headers,
    )
    assert fin.status_code == 200, fin.text
    recon_id = fin.json()["reconciliation_id"]

    pr_after = client.get(
        f"/api/v1/ingestion/jobs/{pr_job_id}", headers=auth_headers,
    ).json()["job"]
    sf_after = client.get(
        f"/api/v1/ingestion/jobs/{sf_job_id}", headers=auth_headers,
    ).json()["job"]
    assert pr_after["status"] == "completed"
    assert sf_after["status"] == "completed"
    assert pr_after["reconciliation_id"] == recon_id
    assert sf_after["reconciliation_id"] == recon_id
    assert pr_after["linked_sf_job_id"] == sf_job_id
