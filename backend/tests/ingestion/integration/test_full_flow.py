"""Full happy-path integration test.

Requires: INGESTION_TEST_SUPABASE_URL, INGESTION_TEST_TENANT_ID,
INGESTION_TEST_CLIENT_ID, INGESTION_TEST_USER_ID, INGESTION_TEST_USER_JWT
to be set against a working dev Supabase project + an existing demo client
with both prior PR + SF documents available (per the seed_demo.py output).
"""
from __future__ import annotations

import asyncio
import io
import os
from datetime import date

import openpyxl
import pytest

from app.ingestion import persistence as p
from app.ingestion import service as svc
from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.ingestion.schemas import JobKind, JobStatus

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="full integration requires real Supabase",
)


def _xlsx_pr() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    for i in range(3):
        ws.append([f"INT-PR-{i}", "100200300", "IntegSupplier",
                   "2026-05-15", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _xlsx_sf() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Invoice Date",
               "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN"])
    for i in range(3):
        ws.append([f"INT-PR-{i}", "2026-05-15", 1000, 150, "111222333"])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


class _Upload:
    """Minimal stand-in for fastapi.UploadFile in tests."""
    def __init__(self, name: str, content: bytes, mime: str) -> None:
        self.filename = name
        self.content_type = mime
        self._buf = io.BytesIO(content)

    async def read(self) -> bytes:
        return self._buf.getvalue()


@pytest.mark.asyncio
async def test_full_happy_path(tenant_id, client_id, user_id):
    set_llm_adapter(StubLLMAdapter())

    # Upload 1: supplier export
    sf_resp = await svc.create_job(
        tenant_id=tenant_id, user_id=user_id, client_id=client_id,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        kind=JobKind.SUPPLIER_EXPORT,
        files=[_Upload("sf.xlsx", _xlsx_sf(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
    )

    # Wait for extraction
    for _ in range(30):
        j = await p.get_job(sf_resp.job_id, tenant_id=tenant_id)
        if j and j["status"] == JobStatus.READY_FOR_REVIEW.value:
            break
        await asyncio.sleep(1)
    assert j["status"] == JobStatus.READY_FOR_REVIEW.value
    assert j["rows_needs_review"] == 0  # canonical XLSX → auto-pass

    # Finalize SF
    await svc.finalize_job(job_id=sf_resp.job_id, tenant_id=tenant_id)

    # Upload 2: purchase register (sibling now exists)
    pr_resp = await svc.create_job(
        tenant_id=tenant_id, user_id=user_id, client_id=client_id,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        kind=JobKind.PURCHASE_REGISTER,
        files=[_Upload("pr.xlsx", _xlsx_pr(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
    )

    for _ in range(30):
        j = await p.get_job(pr_resp.job_id, tenant_id=tenant_id)
        if j and j["status"] == JobStatus.READY_FOR_REVIEW.value:
            break
        await asyncio.sleep(1)

    recon_id = await svc.finalize_job(job_id=pr_resp.job_id, tenant_id=tenant_id)
    assert recon_id is not None

    # Verify reconciliation_id stored on job
    j = await p.get_job(pr_resp.job_id, tenant_id=tenant_id)
    assert j["status"] == JobStatus.COMPLETED.value
    assert j["reconciliation_id"] == str(recon_id)
