"""In-process async worker for ingestion jobs.

Two entry points:
  * `process_one_file(...)` — does the per-file work; called by the worker
    loop OR directly by tests.
  * `worker_loop()` — long-running asyncio task; polls Postgres for
    pending jobs, processes each file with bounded concurrency.

Uses a soft lease via `update_file(status=extracting, extraction_started_at=now)`.
On startup, the worker re-claims rows where status='extracting' AND
extraction_started_at < now() - 10 min (handled in `claim_pending_jobs`).
"""
from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog

from app.config import settings
from app.database import get_supabase_admin
from app.ingestion import persistence as p
from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext, Engine
from app.ingestion.engines.pandas_canonical import PandasCanonicalEngine
from app.ingestion.engines.pandas_mapper import PandasMapperEngine
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.engines.vision import VisionEngine
from app.ingestion.exceptions import ExtractionFailedError
from app.ingestion.lifecycle import next_status_for_extraction
from app.ingestion.router_engine import select_engine_name
from app.ingestion.schemas import (
    FileStatus, JobKind, JobStatus, RowStatus,
)
from app.ingestion.storage import download_original
from app.ingestion.validation import validate_row
from app.ingestion.rate_limit import RateLimitExceeded, TokenBucketRegistry

log = structlog.get_logger()

_CONCURRENCY = 8
_LEASE_TIMEOUT = timedelta(minutes=10)

_RATE = TokenBucketRegistry(
    per_min=int(os.environ.get("INGESTION_MAX_CALLS_PER_MIN", "30")),
    per_day=int(os.environ.get("INGESTION_MAX_CALLS_PER_DAY", "5000")),
)


def get_rate_limiter() -> TokenBucketRegistry:
    return _RATE


def _engine_for(name: str) -> Engine:
    return {
        "pandas":             PandasCanonicalEngine(),
        "pandas+llm-mapper":  PandasMapperEngine(),
        "pdfplumber+llm":     PdfBornDigitalEngine(),
        "gemini-vision":      VisionEngine(),
    }[name]


async def process_one_file(
    *,
    engine: Engine,
    file_bytes: bytes,
    file_id: UUID,
    job_id: UUID,
    tenant_id: UUID,
    ctx: ExtractionContext,
) -> None:
    started = datetime.now(timezone.utc)
    await p.update_file(
        file_id, tenant_id=tenant_id,
        status=FileStatus.EXTRACTING,
        engine=engine.name,
        extraction_started_at=started,
    )
    # Only LLM-touching engines need rate-limiting
    if engine.name in ("pandas+llm-mapper", "pdfplumber+llm", "gemini-vision"):
        try:
            _RATE.acquire(tenant_id)
        except RateLimitExceeded as e:
            await p.update_file(
                file_id, tenant_id=tenant_id,
                status=FileStatus.FAILED, error=f"rate_limited: {e}"[:500],
            )
            await p.increment_files_done(job_id, tenant_id=tenant_id)
            return
    try:
        result: ExtractedFileResult = await asyncio.to_thread(
            engine.extract, file_bytes, ctx
        )
    except Exception as e:
        log.exception("ingestion.file.extract_failed",
                      file_id=str(file_id), error=str(e))
        await p.update_file(
            file_id, tenant_id=tenant_id,
            status=FileStatus.FAILED,
            error=str(e)[:500],
        )
        await p.increment_files_done(job_id, tenant_id=tenant_id)
        return

    field_warnings_per_row = [
        validate_row(
            row, kind=ctx.kind,
            period_start=ctx.period_start, period_end=ctx.period_end,
        )
        for row in result.rows
    ]
    initial_status = (
        RowStatus.NEEDS_REVIEW if result.needs_review else RowStatus.AUTO_PASSED
    )
    await p.insert_extracted_rows(
        job_id=job_id, file_id=file_id, tenant_id=tenant_id,
        rows=result.rows, status=initial_status,
        field_warnings_per_row=field_warnings_per_row,
        source_pages=result.source_pages,
    )

    await p.update_file(
        file_id, tenant_id=tenant_id,
        status=FileStatus.EXTRACTED,
        rows_extracted=len(result.rows),
        needs_review=result.needs_review,
        warnings=result.warnings,
        extracted_at=datetime.now(timezone.utc),
    )
    await p.increment_files_done(job_id, tenant_id=tenant_id)
    await p.recompute_row_counts(job_id, tenant_id=tenant_id)


async def process_job(job_id: UUID, *, tenant_id: UUID) -> None:
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        log.warning("ingestion.worker.job_not_found", job_id=str(job_id))
        return

    await p.update_job_status(job_id, JobStatus.EXTRACTING, tenant_id=tenant_id)
    files = await p.list_files(job_id, tenant_id=tenant_id)
    pending = [f for f in files if f["status"] in (
        FileStatus.QUEUED.value, FileStatus.EXTRACTING.value
    )]

    # Supabase returns date columns as ISO strings; ExtractionContext
    # (and downstream `validate_row`) require real `date` objects.
    def _as_date(v: object) -> date:
        if isinstance(v, date):
            return v
        return date.fromisoformat(str(v))

    ctx = ExtractionContext(
        kind=JobKind(job["kind"]),
        period_start=_as_date(job["period_start"]),
        period_end=_as_date(job["period_end"]),
        tenant_id=str(tenant_id),
    )

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(file_row):
        async with sem:
            try:
                content = await download_original(file_row["storage_path"])
            except Exception as e:
                await p.update_file(
                    UUID(file_row["id"]), tenant_id=tenant_id,
                    status=FileStatus.FAILED, error=f"storage: {e}"[:500],
                )
                await p.increment_files_done(job_id, tenant_id=tenant_id)
                return
            engine = _engine_for(select_engine_name(
                file_bytes=content, mime=file_row["mime_type"],
                kind=job["kind"], filename=file_row["original_filename"],
            ))
            await process_one_file(
                engine=engine, file_bytes=content,
                file_id=UUID(file_row["id"]),
                job_id=job_id, tenant_id=tenant_id, ctx=ctx,
            )

    await asyncio.gather(*[_one(f) for f in pending])

    await p.recompute_row_counts(job_id, tenant_id=tenant_id)
    refreshed = await p.get_job(job_id, tenant_id=tenant_id)
    needs = (refreshed or {}).get("rows_needs_review", 0)
    await p.update_job_status(
        job_id, next_status_for_extraction(any_needs_review=needs > 0),
        tenant_id=tenant_id,
    )


async def claim_and_run(job_id: UUID, tenant_id: UUID) -> None:
    """Single-shot: process one specific job.

    Called from the API handler that creates the job (kicks off in background)
    and from the worker loop's polling.
    """
    try:
        await process_job(job_id, tenant_id=tenant_id)
    except Exception as e:
        log.exception("ingestion.worker.job_crashed",
                      job_id=str(job_id), error=str(e))
        await p.update_job_status(
            job_id, JobStatus.FAILED, tenant_id=tenant_id,
            error_summary=str(e)[:500],
        )


async def poll_pending_jobs(*, sleep_s: float = 5.0) -> None:
    """Long-running loop. Picks up jobs that were created on a different
    instance OR jobs whose lease expired due to a worker crash."""
    sb = get_supabase_admin()
    log.info("ingestion.worker.loop_started")
    while True:
        try:
            cutoff = (datetime.now(timezone.utc) - _LEASE_TIMEOUT).isoformat()

            def _q():
                return (
                    sb.table("ingestion_jobs")
                    .select("id, tenant_id, status, updated_at")
                    .in_("status", [JobStatus.PENDING.value, JobStatus.EXTRACTING.value])
                    .order("created_at")
                    .limit(20)
                    .execute()
                )

            res = await asyncio.to_thread(_q)
            for row in res.data or []:
                if row["status"] == JobStatus.EXTRACTING.value and row["updated_at"] > cutoff:
                    continue
                asyncio.create_task(
                    claim_and_run(UUID(row["id"]), UUID(row["tenant_id"]))
                )
        except Exception as e:
            log.exception("ingestion.worker.poll_error", error=str(e))
        await asyncio.sleep(sleep_s)
