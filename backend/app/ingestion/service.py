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
from app.ingestion.exceptions import (
    FileTooLargeError,
    JobNotFoundError,
    UnsupportedFileTypeError,
)
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


async def create_job(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    kind: JobKind,
    files: list[UploadFile],
) -> CreateJobResponse:
    if not files:
        raise UnsupportedFileTypeError(filename="", mime="(no files)")
    if len(files) > _MAX_FILES:
        raise UnsupportedFileTypeError(
            filename=f"<{len(files)} files>",
            mime=f"max {_MAX_FILES} files per job",
        )

    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=kind, period_start=period_start, period_end=period_end,
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
    """Idempotent. Validates needs_review == 0; runs handoff."""
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise JobNotFoundError(message=f"Job {job_id} not found")

    current = JobStatus(job["status"])
    if current == JobStatus.COMPLETED:
        if job["reconciliation_id"]:
            return UUID(job["reconciliation_id"])
        from app.ingestion.exceptions import HandoffError
        raise HandoffError(message="Completed job has no reconciliation_id")

    needs = await p.count_needs_review(job_id, tenant_id=tenant_id)
    if needs > 0:
        from app.ingestion.exceptions import IngestionError
        err = IngestionError(message=f"{needs} rows still need review")
        err.code = "INGESTION_REVIEW_INCOMPLETE"
        raise err

    if current == JobStatus.READY_FOR_REVIEW:
        assert_can_transition(current, JobStatus.CONFIRMED)
        await p.update_job_status(
            job_id, JobStatus.CONFIRMED, tenant_id=tenant_id,
        )

    assert_can_transition(JobStatus.CONFIRMED, JobStatus.RECONCILING)
    await p.update_job_status(
        job_id, JobStatus.RECONCILING, tenant_id=tenant_id,
    )

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
