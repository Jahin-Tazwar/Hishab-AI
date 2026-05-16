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
from typing import Any, Optional
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


async def _build_and_register_canonical(
    *,
    tenant_id: UUID, client_id: UUID, user_id: UUID,
    job_id: str, kind: JobKind, rows: list[ExtractedRowData],
) -> UUID:
    """Build canonical XLSX from rows, upload to recon-files, insert documents row."""
    sb = get_supabase_admin()
    xlsx_bytes = rows_to_canonical_xlsx(rows, kind=kind)
    suffix = "purchase_register" if kind == JobKind.PURCHASE_REGISTER else "supplier_export"
    filename = f"ingested_{suffix}_{job_id}.xlsx"
    storage_path = f"{tenant_id}/{client_id}/ingestion/{job_id}/{filename}"
    doc_type = suffix

    def _up_and_register():
        sb.storage.from_(_RECON_BUCKET).upload(
            path=storage_path, file=xlsx_bytes,
            file_options={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "upsert": "false",
            },
        )
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

    return await asyncio.to_thread(_up_and_register)


async def _resolve_doc_ids(
    *, tenant_id, client_id, job, kind, rows, user_id,
) -> tuple[UUID, UUID, Optional[UUID]]:
    """Build/reuse PR + SF canonical docs and return (pr_doc_id, sf_doc_id, partner_job_id).

    `partner_job_id` is the linked PR job's id when this is an SF job with
    linked_pr_job_id set. Callers use it to mark the partner COMPLETED.
    """
    job_id = job["id"]
    linked_pr_job_id_raw = job.get("linked_pr_job_id")
    linked_pr_job_id = UUID(linked_pr_job_id_raw) if linked_pr_job_id_raw else None
    reuse_pr_doc_id_raw = job.get("reuse_pr_doc_id")
    reuse_pr_doc_id = UUID(reuse_pr_doc_id_raw) if reuse_pr_doc_id_raw else None
    reuse_sf_doc_id_raw = job.get("reuse_sf_doc_id")
    reuse_sf_doc_id = UUID(reuse_sf_doc_id_raw) if reuse_sf_doc_id_raw else None

    # Case 1: SF job linked to a PR job → build both canonicals from both jobs' rows.
    if kind == JobKind.SUPPLIER_EXPORT and linked_pr_job_id is not None:
        pr_job = await p.get_job(linked_pr_job_id, tenant_id=tenant_id)
        if pr_job is None:
            raise HandoffError(f"Linked PR job {linked_pr_job_id} disappeared")
        pr_rows_dicts = await p.list_confirmed_rows(linked_pr_job_id, tenant_id=tenant_id)
        if not pr_rows_dicts:
            raise HandoffError(f"Linked PR job {linked_pr_job_id} has no confirmed rows")
        pr_rows = [ExtractedRowData(**r["row_data"]) for r in pr_rows_dicts]
        pr_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=str(linked_pr_job_id), kind=JobKind.PURCHASE_REGISTER, rows=pr_rows,
        )
        sf_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=job_id, kind=JobKind.SUPPLIER_EXPORT, rows=rows,
        )
        return pr_doc_id, sf_doc_id, linked_pr_job_id

    # Case 2: SF job with reuse_pr_doc_id → build only SF, reuse PR doc id.
    if kind == JobKind.SUPPLIER_EXPORT and reuse_pr_doc_id is not None:
        sf_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=job_id, kind=JobKind.SUPPLIER_EXPORT, rows=rows,
        )
        return reuse_pr_doc_id, sf_doc_id, None

    # Case 3: PR job with reuse_sf_doc_id → build only PR, reuse SF doc id.
    if kind == JobKind.PURCHASE_REGISTER and reuse_sf_doc_id is not None:
        pr_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=job_id, kind=JobKind.PURCHASE_REGISTER, rows=rows,
        )
        return pr_doc_id, reuse_sf_doc_id, None

    # Case 4 (fallback, mostly for tests / legacy): build for this kind, look up
    # the most-recent sibling doc by client. This is the old behavior; the new
    # wizard never lands here because it always sets linked_pr_job_id or reuse_*.
    this_doc_id = await _build_and_register_canonical(
        tenant_id=tenant_id, client_id=client_id, user_id=user_id,
        job_id=job_id, kind=kind, rows=rows,
    )
    sb = get_supabase_admin()
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
        return this_doc_id, sibling_id, None
    return sibling_id, this_doc_id, None


async def run_handoff(
    *, job_id: UUID, tenant_id: UUID,
) -> UUID:
    """Returns the new reconciliation_id on success.

    Both the primary job and the linked partner job (if any) are marked
    COMPLETED with the same reconciliation_id before this returns.
    """
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HandoffError(f"Job {job_id} not found")
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

    pr_doc_id, sf_doc_id, partner_job_id = await _resolve_doc_ids(
        tenant_id=tenant_id, client_id=client_id, job=job, kind=kind, rows=rows,
        user_id=user_id,
    )

    log.info("ingestion.handoff.starting", job_id=str(job_id),
             partner_job_id=str(partner_job_id) if partner_job_id else None)

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

    await p.complete_jobs_pair(
        primary_job_id=job_id, partner_job_id=partner_job_id,
        tenant_id=tenant_id, reconciliation_id=recon_id,
    )

    log.info("ingestion.handoff.done", job_id=str(job_id), recon_id=str(recon_id))
    return recon_id
