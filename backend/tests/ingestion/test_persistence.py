"""Persistence-layer tests for ingestion jobs/files/rows."""
from datetime import date
from uuid import UUID, uuid4

import pytest

from app.ingestion import persistence as p
from app.ingestion.schemas import (
    ExtractedRowData,
    FileStatus,
    JobKind,
    JobStatus,
    RowStatus,
)


@pytest.mark.asyncio
async def test_create_job_starts_pending(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id,
        client_id=client_id,
        created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    job = await p.get_job(job_id, tenant_id=tenant_id)
    assert job is not None
    assert job["status"] == JobStatus.PENDING.value
    assert job["files_total"] == 0


@pytest.mark.asyncio
async def test_add_file_increments_counter(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id,
        client_id=client_id,
        created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    file_id = await p.add_file(
        job_id=job_id,
        tenant_id=tenant_id,
        storage_path=f"{tenant_id}/{job_id}/file1/x.pdf",
        original_filename="x.pdf",
        mime_type="application/pdf",
        byte_size=12345,
    )
    job = await p.get_job(job_id, tenant_id=tenant_id)
    assert job["files_total"] == 1
    assert isinstance(file_id, UUID)


@pytest.mark.asyncio
async def test_update_job_status_transitions(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    await p.update_job_status(job_id, JobStatus.EXTRACTING, tenant_id=tenant_id)
    j = await p.get_job(job_id, tenant_id=tenant_id)
    assert j["status"] == JobStatus.EXTRACTING.value


@pytest.mark.asyncio
async def test_insert_extracted_rows_and_count_review(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    file_id = await p.add_file(
        job_id=job_id, tenant_id=tenant_id,
        storage_path=f"{tenant_id}/{job_id}/f/y.pdf",
        original_filename="y.pdf", mime_type="application/pdf", byte_size=1,
    )
    rows = [
        ExtractedRowData(
            invoice_no="A1", invoice_date=date(2026, 5, 10),
            taxable_amount_bdt="100", vat_amount_bdt="15",
        ),
        ExtractedRowData(
            invoice_no="A2", invoice_date=date(2026, 5, 11),
            taxable_amount_bdt="200", vat_amount_bdt="30",
        ),
    ]
    await p.insert_extracted_rows(
        job_id=job_id, file_id=file_id, tenant_id=tenant_id,
        rows=rows, status=RowStatus.NEEDS_REVIEW,
        field_warnings_per_row=[[], []],
    )
    listed = await p.list_rows(job_id, tenant_id=tenant_id, only_needs_review=True)
    assert len(listed) == 2
    assert all(r["status"] == RowStatus.NEEDS_REVIEW.value for r in listed)


@pytest.mark.asyncio
async def test_count_needs_review(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    file_id = await p.add_file(
        job_id=job_id, tenant_id=tenant_id,
        storage_path=f"{tenant_id}/{job_id}/f/z.xlsx",
        original_filename="z.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size=1,
    )
    await p.insert_extracted_rows(
        job_id=job_id, file_id=file_id, tenant_id=tenant_id,
        rows=[ExtractedRowData(
            invoice_no="X", invoice_date=date(2026, 5, 1),
            taxable_amount_bdt="1", vat_amount_bdt="0.15",
        )],
        status=RowStatus.AUTO_PASSED,
        field_warnings_per_row=[[]],
    )
    n = await p.count_needs_review(job_id, tenant_id=tenant_id)
    assert n == 0
