"""Database CRUD for ingestion. Uses the supabase admin client.

All callers are expected to have already validated tenant scope (typically
via `get_current_tenant_id`); the `tenant_id` arg is a defense-in-depth
filter on every query.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin
from app.ingestion.schemas import (
    ExtractedRowData,
    FieldWarning,
    FileStatus,
    JobKind,
    JobStatus,
    RowStatus,
)

_TBL_JOBS = "ingestion_jobs"
_TBL_FILES = "ingestion_files"
_TBL_ROWS = "extracted_rows"
_TBL_MAPPINGS = "ingestion_column_mappings"


# ── Jobs ────────────────────────────────────────────────────────────────


async def create_job(
    *,
    tenant_id: UUID,
    client_id: UUID,
    created_by: UUID,
    kind: JobKind,
    period_start: date,
    period_end: date,
) -> UUID:
    sb = get_supabase_admin()

    def _insert():
        return (
            sb.table(_TBL_JOBS)
            .insert({
                "tenant_id": str(tenant_id),
                "client_id": str(client_id),
                "created_by": str(created_by),
                "kind": kind.value,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "status": JobStatus.PENDING.value,
            })
            .execute()
        )

    res = await asyncio.to_thread(_insert)
    return UUID(res.data[0]["id"])


async def get_job(job_id: UUID, *, tenant_id: UUID) -> Optional[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_JOBS)
            .select("*")
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def update_job_status(
    job_id: UUID, status: JobStatus, *, tenant_id: UUID,
    error_summary: Optional[str] = None,
    reconciliation_id: Optional[UUID] = None,
) -> None:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {"status": status.value}
    if error_summary is not None:
        payload["error_summary"] = error_summary
    if reconciliation_id is not None:
        payload["reconciliation_id"] = str(reconciliation_id)
    if status == JobStatus.COMPLETED:
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()

    def _u():
        return (
            sb.table(_TBL_JOBS)
            .update(payload)
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def increment_files_done(job_id: UUID, *, tenant_id: UUID) -> None:
    """Atomic +1 on files_done via Postgres function call."""
    sb = get_supabase_admin()

    def _rpc():
        cur = (
            sb.table(_TBL_JOBS)
            .select("files_done")
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .single()
            .execute()
        )
        new_val = (cur.data["files_done"] or 0) + 1
        return (
            sb.table(_TBL_JOBS)
            .update({"files_done": new_val})
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_rpc)


async def recompute_row_counts(job_id: UUID, *, tenant_id: UUID) -> None:
    """Refresh rows_total and rows_needs_review on the job from extracted_rows."""
    sb = get_supabase_admin()

    def _q():
        total = (
            sb.table(_TBL_ROWS)
            .select("id", count="exact")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )
        needs = (
            sb.table(_TBL_ROWS)
            .select("id", count="exact")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .eq("status", RowStatus.NEEDS_REVIEW.value)
            .execute()
        )
        return total.count or 0, needs.count or 0

    rows_total, rows_needs_review = await asyncio.to_thread(_q)

    def _u():
        return (
            sb.table(_TBL_JOBS)
            .update({
                "rows_total": rows_total,
                "rows_needs_review": rows_needs_review,
            })
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Files ───────────────────────────────────────────────────────────────


async def add_file(
    *,
    job_id: UUID,
    tenant_id: UUID,
    storage_path: str,
    original_filename: str,
    mime_type: str,
    byte_size: int,
) -> UUID:
    sb = get_supabase_admin()

    def _insert():
        res = (
            sb.table(_TBL_FILES)
            .insert({
                "job_id": str(job_id),
                "tenant_id": str(tenant_id),
                "storage_path": storage_path,
                "original_filename": original_filename,
                "mime_type": mime_type,
                "byte_size": byte_size,
                "status": FileStatus.QUEUED.value,
            })
            .execute()
        )
        cur = (
            sb.table(_TBL_JOBS)
            .select("files_total")
            .eq("id", str(job_id))
            .single()
            .execute()
        )
        new_total = (cur.data["files_total"] or 0) + 1
        sb.table(_TBL_JOBS).update({"files_total": new_total}).eq(
            "id", str(job_id)
        ).execute()
        return res

    res = await asyncio.to_thread(_insert)
    return UUID(res.data[0]["id"])


async def list_files(job_id: UUID, *, tenant_id: UUID) -> list[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_FILES)
            .select("*")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .order("created_at")
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


async def update_file(
    file_id: UUID,
    *,
    tenant_id: UUID,
    status: Optional[FileStatus] = None,
    engine: Optional[str] = None,
    rows_extracted: Optional[int] = None,
    needs_review: Optional[bool] = None,
    warnings: Optional[list[dict[str, Any]]] = None,
    error: Optional[str] = None,
    extracted_at: Optional[datetime] = None,
    extraction_started_at: Optional[datetime] = None,
) -> None:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status.value
    if engine is not None:
        payload["engine"] = engine
    if rows_extracted is not None:
        payload["rows_extracted"] = rows_extracted
    if needs_review is not None:
        payload["needs_review"] = needs_review
    if warnings is not None:
        payload["warnings"] = warnings
    if error is not None:
        payload["error"] = error
    if extracted_at is not None:
        payload["extracted_at"] = extracted_at.isoformat()
    if extraction_started_at is not None:
        payload["extraction_started_at"] = extraction_started_at.isoformat()
    if not payload:
        return

    def _u():
        return (
            sb.table(_TBL_FILES)
            .update(payload)
            .eq("id", str(file_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Extracted rows ──────────────────────────────────────────────────────


async def insert_extracted_rows(
    *,
    job_id: UUID,
    file_id: UUID,
    tenant_id: UUID,
    rows: list[ExtractedRowData],
    status: RowStatus,
    field_warnings_per_row: list[list[FieldWarning]],
    source_pages: Optional[list[Optional[int]]] = None,
) -> list[UUID]:
    if len(rows) != len(field_warnings_per_row):
        raise ValueError("rows and field_warnings_per_row must be same length")
    if source_pages is not None and len(source_pages) != len(rows):
        raise ValueError("source_pages must match rows length")

    sb = get_supabase_admin()
    payload = []
    for i, row in enumerate(rows):
        rec = {
            "job_id": str(job_id),
            "file_id": str(file_id),
            "tenant_id": str(tenant_id),
            "row_data": row.model_dump(mode="json"),
            "row_data_original": row.model_dump(mode="json"),
            "status": status.value,
            "field_warnings": [w.model_dump() for w in field_warnings_per_row[i]],
        }
        if source_pages is not None:
            rec["source_page_no"] = source_pages[i]
        payload.append(rec)

    if not payload:
        return []

    def _ins():
        return sb.table(_TBL_ROWS).insert(payload).execute()

    res = await asyncio.to_thread(_ins)
    return [UUID(r["id"]) for r in (res.data or [])]


async def list_rows(
    job_id: UUID,
    *,
    tenant_id: UUID,
    only_needs_review: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        q = (
            sb.table(_TBL_ROWS)
            .select("*")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .order("created_at")
            .range(offset, offset + limit - 1)
        )
        if only_needs_review:
            q = q.eq("status", RowStatus.NEEDS_REVIEW.value)
        return q.execute()

    res = await asyncio.to_thread(_q)
    return res.data or []


async def count_needs_review(job_id: UUID, *, tenant_id: UUID) -> int:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_ROWS)
            .select("id", count="exact")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .eq("status", RowStatus.NEEDS_REVIEW.value)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.count or 0


async def update_row(
    row_id: UUID,
    *,
    tenant_id: UUID,
    row_data: Optional[ExtractedRowData] = None,
    status: Optional[RowStatus] = None,
    reviewed_by: Optional[UUID] = None,
) -> None:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {}
    if row_data is not None:
        payload["row_data"] = row_data.model_dump(mode="json")
    if status is not None:
        payload["status"] = status.value
    if reviewed_by is not None:
        payload["reviewed_by"] = str(reviewed_by)
        payload["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if not payload:
        return

    def _u():
        return (
            sb.table(_TBL_ROWS)
            .update(payload)
            .eq("id", str(row_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def list_confirmed_rows(
    job_id: UUID, *, tenant_id: UUID
) -> list[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_ROWS)
            .select("*")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .in_("status", [
                RowStatus.AUTO_PASSED.value,
                RowStatus.CONFIRMED.value,
                RowStatus.EDITED.value,
            ])
            .order("created_at")
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


# ── Column mappings cache ────────────────────────────────────────────────


async def get_cached_mapping(
    *, tenant_id: UUID, kind: JobKind, header_signature: str
) -> Optional[dict[str, Optional[str]]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_MAPPINGS)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("kind", kind.value)
            .eq("header_signature", header_signature)
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    if res.data:
        return res.data[0]["mapping"]
    return None


async def upsert_mapping(
    *,
    tenant_id: UUID,
    kind: JobKind,
    header_signature: str,
    mapping: dict[str, Optional[str]],
    confirmed_by: Optional[UUID] = None,
) -> UUID:
    sb = get_supabase_admin()
    payload = {
        "tenant_id": str(tenant_id),
        "kind": kind.value,
        "header_signature": header_signature,
        "mapping": mapping,
    }
    if confirmed_by is not None:
        payload["confirmed_by"] = str(confirmed_by)

    def _up():
        return (
            sb.table(_TBL_MAPPINGS)
            .upsert(payload, on_conflict="tenant_id,kind,header_signature")
            .execute()
        )

    res = await asyncio.to_thread(_up)
    return UUID(res.data[0]["id"])
