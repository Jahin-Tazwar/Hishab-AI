"""High-level orchestration entry points called from the router.

Three operations:
  * create_job   — accept multipart files, persist, kick off worker
  * finalize     — verify zero needs_review then run handoff
  * confirm_row / reject_row / edit_row — row-level mutations
"""
from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import UploadFile

from app.ingestion import persistence as p
from app.ingestion import storage as st
from app.ingestion.handoff import run_handoff
from app.ingestion.lifecycle import assert_can_transition
from app.ingestion.router_engine import select_engine_name
from app.ingestion.schemas import (
    CreateJobFileSummary,
    CreateJobResponse,
    ExtractedRowData,
    JobKind,
    JobStatus,
    RowStatus,
)
from app.ingestion.worker import claim_and_run

log = structlog.get_logger()

_MAX_FILES = int(os.environ.get("INGESTION_MAX_FILES_PER_JOB", "200"))
_MAX_SIZE_MB = int(os.environ.get("INGESTION_MAX_FILE_SIZE_MB", "25"))
_MAX_BYTES = _MAX_SIZE_MB * 1024 * 1024

from app.ingestion.exceptions import (
    FileTooLargeError,
    HandoffError,
    JobNotFoundError,
    IngestionError,
    UnsupportedFileTypeError,
)


async def _validate_linked_pr_job(
    *, linked_pr_job_id: UUID, kind: JobKind, tenant_id: UUID,
) -> None:
    if kind != JobKind.SUPPLIER_EXPORT:
        err = IngestionError(message="linked_pr_job_id only valid on supplier_export jobs")
        err.code = "INGESTION_BAD_LINKAGE"
        err.status_code = 422
        raise err
    linked = await p.get_job(linked_pr_job_id, tenant_id=tenant_id)
    if linked is None:
        err = IngestionError(message=f"linked PR job {linked_pr_job_id} not found")
        err.code = "INGESTION_BAD_LINKAGE"
        err.status_code = 422
        raise err
    if linked["kind"] != JobKind.PURCHASE_REGISTER.value:
        err = IngestionError(message="linked job must be a purchase_register")
        err.code = "INGESTION_BAD_LINKAGE"
        err.status_code = 422
        raise err
    existing = await p.find_linked_sf_job_id(linked_pr_job_id, tenant_id=tenant_id)
    if existing is not None:
        err = IngestionError(message=f"PR job {linked_pr_job_id} already linked to SF job {existing}")
        err.code = "INGESTION_DUPLICATE_LINKAGE"
        err.status_code = 422
        raise err


async def _validate_reuse_doc(
    *, doc_id: UUID, expected_type: str, tenant_id: UUID, client_id: UUID,
) -> None:
    doc = await p.find_doc_by_id(doc_id, tenant_id=tenant_id, client_id=client_id)
    if doc is None:
        err = IngestionError(message=f"reuse doc {doc_id} not found for this client")
        err.code = "INGESTION_BAD_REUSE"
        err.status_code = 422
        raise err
    if doc["doc_type"] != expected_type:
        err = IngestionError(
            message=f"reuse doc {doc_id} is {doc['doc_type']}, expected {expected_type}"
        )
        err.code = "INGESTION_BAD_REUSE"
        err.status_code = 422
        raise err


async def create_job(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    kind: JobKind,
    files: list[UploadFile],
    linked_pr_job_id: Optional[UUID] = None,
    reuse_pr_doc_id: Optional[UUID] = None,
    reuse_sf_doc_id: Optional[UUID] = None,
) -> CreateJobResponse:
    if not files:
        raise UnsupportedFileTypeError(filename="", mime="(no files)")
    if len(files) > _MAX_FILES:
        raise UnsupportedFileTypeError(
            filename=f"<{len(files)} files>",
            mime=f"max {_MAX_FILES} files per job",
        )

    # New validations — fail fast before creating the job row.
    if linked_pr_job_id is not None:
        await _validate_linked_pr_job(
            linked_pr_job_id=linked_pr_job_id, kind=kind, tenant_id=tenant_id,
        )
    if reuse_pr_doc_id is not None:
        if kind != JobKind.SUPPLIER_EXPORT:
            err = IngestionError(message="reuse_pr_doc_id only valid on supplier_export jobs")
            err.code = "INGESTION_BAD_REUSE"; err.status_code = 422
            raise err
        await _validate_reuse_doc(
            doc_id=reuse_pr_doc_id, expected_type="purchase_register",
            tenant_id=tenant_id, client_id=client_id,
        )
    if reuse_sf_doc_id is not None:
        if kind != JobKind.PURCHASE_REGISTER:
            err = IngestionError(message="reuse_sf_doc_id only valid on purchase_register jobs")
            err.code = "INGESTION_BAD_REUSE"; err.status_code = 422
            raise err
        await _validate_reuse_doc(
            doc_id=reuse_sf_doc_id, expected_type="supplier_export",
            tenant_id=tenant_id, client_id=client_id,
        )

    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=kind, period_start=period_start, period_end=period_end,
        linked_pr_job_id=linked_pr_job_id,
        reuse_pr_doc_id=reuse_pr_doc_id,
        reuse_sf_doc_id=reuse_sf_doc_id,
    )

    summaries: list[CreateJobFileSummary] = []
    for upload in files:
        content = await upload.read()
        size = len(content)
        try:
            if size > _MAX_BYTES:
                raise FileTooLargeError(
                    filename=upload.filename or "<unnamed>",
                    size=size, max_size=_MAX_BYTES,
                )
            mime = upload.content_type or "application/octet-stream"
            select_engine_name(
                file_bytes=content[:4096], mime=mime,
                kind=kind, filename=upload.filename or "<unnamed>",
            )
        except (UnsupportedFileTypeError, FileTooLargeError) as e:
            summaries.append(CreateJobFileSummary(
                file_id=UUID(int=0), original_filename=upload.filename or "<unnamed>",
                mime_type=upload.content_type or "", byte_size=size,
                accepted=False, rejection_reason=e.message,
            ))
            continue

        file_id = await p.add_file(
            job_id=job_id, tenant_id=tenant_id,
            storage_path="placeholder", original_filename=upload.filename or "<unnamed>",
            mime_type=mime, byte_size=size,
        )
        path = await st.upload_original(
            tenant_id=tenant_id, job_id=job_id, file_id=file_id,
            filename=upload.filename or f"file-{file_id}", content=content,
            mime_type=mime,
        )
        # Patch the real storage_path (add_file used a placeholder)
        from app.database import get_supabase_admin
        sb = get_supabase_admin()

        def _patch():
            sb.table("ingestion_files").update({"storage_path": path}).eq(
                "id", str(file_id)
            ).execute()

        await asyncio.to_thread(_patch)

        summaries.append(CreateJobFileSummary(
            file_id=file_id, original_filename=upload.filename or "<unnamed>",
            mime_type=mime, byte_size=size, accepted=True,
        ))

    # Kick off the worker for this specific job (parallel to the polling loop)
    asyncio.create_task(claim_and_run(job_id, tenant_id))

    return CreateJobResponse(job_id=job_id, files=summaries)


async def finalize_job(*, job_id: UUID, tenant_id: UUID) -> UUID:
    """Idempotent. Validates needs_review == 0; runs combined handoff.

    The handoff (run_handoff) inspects the job's linkage / reuse fields to
    decide which canonical XLSX files to build, which to reuse, and which
    sibling job (if any) to also mark COMPLETED on success.
    """
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise JobNotFoundError(message=f"Job {job_id} not found")

    current = JobStatus(job["status"])
    if current == JobStatus.COMPLETED:
        if job["reconciliation_id"]:
            return UUID(job["reconciliation_id"])
        raise HandoffError(message="Completed job has no reconciliation_id")

    needs = await p.count_needs_review(job_id, tenant_id=tenant_id)
    if needs > 0:
        err = IngestionError(message=f"{needs} rows still need review")
        err.code = "INGESTION_REVIEW_INCOMPLETE"
        err.status_code = 422
        raise err

    if current == JobStatus.READY_FOR_REVIEW:
        assert_can_transition(current, JobStatus.CONFIRMED)
        await p.update_job_status(job_id, JobStatus.CONFIRMED, tenant_id=tenant_id)

    assert_can_transition(JobStatus.CONFIRMED, JobStatus.RECONCILING)
    await p.update_job_status(job_id, JobStatus.RECONCILING, tenant_id=tenant_id)

    try:
        recon_id = await run_handoff(job_id=job_id, tenant_id=tenant_id)
    except Exception as e:
        log.exception("ingestion.finalize.handoff_failed",
                      job_id=str(job_id), error=str(e))
        await p.update_job_status(
            job_id, JobStatus.CONFIRMED, tenant_id=tenant_id,
            error_summary=str(e)[:500],
        )
        raise

    # The handoff is responsible for marking *both* this job and its
    # linked partner (if any) COMPLETED with the same reconciliation_id.
    # We re-read here only as a safety net for the unlinked case.
    refreshed = await p.get_job(job_id, tenant_id=tenant_id)
    if refreshed and refreshed["status"] != JobStatus.COMPLETED.value:
        await p.update_job_status(
            job_id, JobStatus.COMPLETED, tenant_id=tenant_id,
            reconciliation_id=recon_id,
        )
    return recon_id


async def confirm_row(
    *, row_id: UUID, tenant_id: UUID, user_id: UUID,
) -> None:
    await p.update_row(
        row_id, tenant_id=tenant_id,
        status=RowStatus.CONFIRMED, reviewed_by=user_id,
    )


async def reject_row(
    *, row_id: UUID, tenant_id: UUID, user_id: UUID,
) -> None:
    await p.update_row(
        row_id, tenant_id=tenant_id,
        status=RowStatus.REJECTED, reviewed_by=user_id,
    )


async def edit_row(
    *, row_id: UUID, tenant_id: UUID, user_id: UUID,
    new_data: ExtractedRowData,
) -> None:
    await p.update_row(
        row_id, tenant_id=tenant_id,
        row_data=new_data, status=RowStatus.EDITED, reviewed_by=user_id,
    )


async def bulk_confirm(
    *, row_ids: list[UUID], tenant_id: UUID, user_id: UUID,
) -> int:
    """Sequential to keep RLS audit trail clean; row count is small."""
    count = 0
    for rid in row_ids:
        await confirm_row(row_id=rid, tenant_id=tenant_id, user_id=user_id)
        count += 1
    return count


async def start_session(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    reuse_pr_doc_id: Optional[UUID] = None,
    reuse_sf_doc_id: Optional[UUID] = None,
) -> dict[str, Optional[UUID]]:
    """Implements the four reuse-combinations from the spec.

    Returns a dict with exactly one of:
      - {'reconciliation_id': UUID}     when both reuses are set
      - {'pr_job_id': UUID}             when PR is fresh (regardless of SF reuse)
      - {'sf_job_id': UUID}             when PR is reused and SF is fresh
    """
    # Validate any reuse refs upfront.
    if reuse_pr_doc_id is not None:
        await _validate_reuse_doc(
            doc_id=reuse_pr_doc_id, expected_type="purchase_register",
            tenant_id=tenant_id, client_id=client_id,
        )
    if reuse_sf_doc_id is not None:
        await _validate_reuse_doc(
            doc_id=reuse_sf_doc_id, expected_type="supplier_export",
            tenant_id=tenant_id, client_id=client_id,
        )

    # Case A: both reused — run reconciliation directly.
    if reuse_pr_doc_id is not None and reuse_sf_doc_id is not None:
        from app.reconciliation.schemas import ReconciliationCreateRequest
        from app.reconciliation.service import run_reconciliation
        recon_id = await run_reconciliation(
            ReconciliationCreateRequest(
                client_id=client_id,
                period_start=period_start,
                period_end=period_end,
                purchase_register_doc_id=reuse_pr_doc_id,
                supplier_data_doc_id=reuse_sf_doc_id,
            ),
            tenant_id=tenant_id, user_id=user_id,
        )
        return {"reconciliation_id": recon_id, "pr_job_id": None, "sf_job_id": None}

    # Case B: PR reused, SF fresh — create the SF job carrying reuse_pr_doc_id.
    if reuse_pr_doc_id is not None and reuse_sf_doc_id is None:
        sf_job_id = await p.create_job(
            tenant_id=tenant_id, client_id=client_id, created_by=user_id,
            kind=JobKind.SUPPLIER_EXPORT,
            period_start=period_start, period_end=period_end,
            reuse_pr_doc_id=reuse_pr_doc_id,
        )
        return {"reconciliation_id": None, "pr_job_id": None, "sf_job_id": sf_job_id}

    # Case C: PR fresh, SF reused — create the PR job carrying reuse_sf_doc_id.
    if reuse_pr_doc_id is None and reuse_sf_doc_id is not None:
        pr_job_id = await p.create_job(
            tenant_id=tenant_id, client_id=client_id, created_by=user_id,
            kind=JobKind.PURCHASE_REGISTER,
            period_start=period_start, period_end=period_end,
            reuse_sf_doc_id=reuse_sf_doc_id,
        )
        return {"reconciliation_id": None, "pr_job_id": pr_job_id, "sf_job_id": None}

    # Case D: both fresh — create the PR job; SF job is created lazily by the
    # wizard's SF upload step once the user provides files.
    pr_job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=period_start, period_end=period_end,
    )
    return {"reconciliation_id": None, "pr_job_id": pr_job_id, "sf_job_id": None}


async def confirm_job_review(*, job_id: UUID, tenant_id: UUID) -> None:
    """Idempotent ready_for_review → confirmed transition. Does NOT trigger handoff.

    Used by the combined wizard when the user has reviewed PR rows and wants to
    proceed to the SF upload step — the SF finalize will trigger the actual
    handoff.
    """
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise JobNotFoundError(message=f"Job {job_id} not found")
    needs = await p.count_needs_review(job_id, tenant_id=tenant_id)
    if needs > 0:
        err = IngestionError(message=f"{needs} rows still need review")
        err.code = "INGESTION_REVIEW_INCOMPLETE"; err.status_code = 422
        raise err
    current = JobStatus(job["status"])
    if current == JobStatus.CONFIRMED:
        return  # idempotent
    assert_can_transition(current, JobStatus.CONFIRMED)
    await p.update_job_status(job_id, JobStatus.CONFIRMED, tenant_id=tenant_id)
