"""Bridge from ingestion → existing reconciliation pipeline.

`rows_to_canonical_xlsx` is pure — produces the same XLSX shape the
existing parser expects.

`run_handoff` orchestrates the full flow: read confirmed rows, build
both XLSX files, upload to recon-files bucket, insert documents rows,
and call run_reconciliation in-process.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime
from typing import Any
from uuid import UUID

import openpyxl
import structlog

from app.database import get_supabase_admin
from app.ingestion import persistence as p
from app.ingestion.exceptions import HandoffError
from app.ingestion.schemas import ExtractedRowData, JobKind, JobStatus
from app.reconciliation.schemas import ReconciliationCreateRequest
from app.reconciliation.service import run_reconciliation

log = structlog.get_logger()


# ── Pure: rows → XLSX bytes in canonical schema ──────────────────────────


_PURCHASE_HEADERS = [
    "Invoice No", "Supplier BIN", "Supplier Name",
    "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
]
_SUPPLIER_HEADERS = [
    "Invoice No", "Invoice Date",
    "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN",
]


def rows_to_canonical_xlsx(
    rows: list[ExtractedRowData], *, kind: JobKind
) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    if kind == JobKind.PURCHASE_REGISTER:
        ws.append(_PURCHASE_HEADERS)
        for r in rows:
            ws.append([
                r.invoice_no, r.supplier_bin or "", r.supplier_name or "",
                r.invoice_date.isoformat(),
                float(r.taxable_amount_bdt), float(r.vat_amount_bdt),
            ])
    else:
        ws.append(_SUPPLIER_HEADERS)
        for r in rows:
            ws.append([
                r.invoice_no, r.invoice_date.isoformat(),
                float(r.taxable_amount_bdt), float(r.vat_amount_bdt),
                r.buyer_bin or "",
            ])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


# ── Orchestrated: full handoff to reconciliation ────────────────────────


_RECON_BUCKET = "recon-files"


async def run_handoff(
    *, job_id: UUID, tenant_id: UUID,
) -> UUID:
    """Returns the new reconciliation_id on success."""
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HandoffError(f"Job {job_id} not found")
    # finalize_job() flips status to RECONCILING immediately before calling
    # run_handoff(), so accept either: handoff is invoked DURING the
    # 'reconciling' window and once a job is CONFIRMED it is also valid to
    # re-run handoff (idempotent retry after a previous crash).
    if job["status"] not in (
        JobStatus.CONFIRMED.value,
        JobStatus.RECONCILING.value,
    ):
        raise HandoffError(
            f"Job {job_id} is in {job['status']}, expected 'confirmed' or 'reconciling'"
        )

    client_id = UUID(job["client_id"])
    user_id = UUID(job["created_by"])
    kind = JobKind(job["kind"])

    rows_dicts = await p.list_confirmed_rows(job_id, tenant_id=tenant_id)
    rows = [ExtractedRowData(**r["row_data"]) for r in rows_dicts]

    if not rows:
        raise HandoffError("No confirmed rows to hand off")

    pr_doc_id, sf_doc_id = await _resolve_doc_ids(
        tenant_id=tenant_id, client_id=client_id, job=job, kind=kind, rows=rows,
        user_id=user_id,
    )

    log.info("ingestion.handoff.starting", job_id=str(job_id))

    recon_id = await run_reconciliation(
        ReconciliationCreateRequest(
            client_id=client_id,
            period_start=job["period_start"],
            period_end=job["period_end"],
            purchase_register_doc_id=pr_doc_id,
            supplier_data_doc_id=sf_doc_id,
        ),
        tenant_id=tenant_id, user_id=user_id,
    )
    log.info("ingestion.handoff.done", job_id=str(job_id), recon_id=str(recon_id))
    return recon_id


async def _resolve_doc_ids(
    *, tenant_id, client_id, job, kind, rows, user_id,
) -> tuple[UUID, UUID]:
    """Build the canonical XLSX for THIS job and look up a sibling for the other kind."""
    sb = get_supabase_admin()
    period_start = job["period_start"]; period_end = job["period_end"]

    # 1. Build + upload XLSX for this job's kind
    xlsx_bytes = rows_to_canonical_xlsx(rows, kind=kind)
    suffix = "purchase_register" if kind == JobKind.PURCHASE_REGISTER else "supplier_export"
    filename = f"ingested_{suffix}_{job['id']}.xlsx"
    storage_path = f"{tenant_id}/{client_id}/ingestion/{job['id']}/{filename}"

    def _up_and_register():
        sb.storage.from_(_RECON_BUCKET).upload(
            path=storage_path, file=xlsx_bytes,
            file_options={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "upsert": "false",
            },
        )
        # doc_type values constrained by migration 0002: purchase_register | supplier_export | recon_export | other
        doc_type = "purchase_register" if kind == JobKind.PURCHASE_REGISTER else "supplier_export"
        doc = sb.table("documents").insert({
            "tenant_id": str(tenant_id),
            "client_id": str(client_id),
            "uploaded_by": str(user_id),
            "doc_type": doc_type,
            "storage_path": storage_path,
            "original_filename": filename,
            "file_size_bytes": len(xlsx_bytes),
        }).execute()
        return UUID(doc.data[0]["id"])

    this_doc_id = await asyncio.to_thread(_up_and_register)

    # 2. Look up the most-recent successful sibling-kind doc for this client+period
    sibling_doc_type = (
        "supplier_export" if kind == JobKind.PURCHASE_REGISTER else "purchase_register"
    )

    def _lookup_sibling():
        return (
            sb.table("documents")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .eq("doc_type", sibling_doc_type)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

    sibling = await asyncio.to_thread(_lookup_sibling)
    if not sibling.data:
        raise HandoffError(
            f"No prior {sibling_doc_type} document found for client {client_id}. "
            f"Upload the matching file via ingestion before finalizing."
        )
    sibling_id = UUID(sibling.data[0]["id"])

    if kind == JobKind.PURCHASE_REGISTER:
        return this_doc_id, sibling_id
    return sibling_id, this_doc_id
