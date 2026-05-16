"""FastAPI endpoints for ingestion. Mounted at /api/v1/ingestion."""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_tenant_id, get_current_user_id
from app.ingestion import persistence as p
from app.ingestion import service as svc
from app.ingestion.exceptions import IngestionError, JobNotFoundError
from app.ingestion.schemas import (
    CreateJobResponse,
    ExtractedRowData,
    ExtractedRowOut,
    FieldWarning,
    FinalizeResponse,
    IngestionFileOut,
    JobDetailOut,
    JobKind,
    JobOut,
    RowsListOut,
)
from app.ingestion.storage import create_signed_url, download_original

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


# ── POST /jobs ─────────────────────────────────────────────────────────


@router.post(
    "/jobs", status_code=status.HTTP_201_CREATED,
    response_model=CreateJobResponse,
)
async def create_job_endpoint(
    client_id: UUID = Form(...),
    period_start: date = Form(...),
    period_end: date = Form(...),
    kind: JobKind = Form(...),
    files: list[UploadFile] = File(...),
    linked_pr_job_id: Optional[UUID] = Form(None),
    reuse_pr_doc_id: Optional[UUID] = Form(None),
    reuse_sf_doc_id: Optional[UUID] = Form(None),
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> CreateJobResponse:
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end < period_start")
    try:
        return await svc.create_job(
            tenant_id=tenant_id, user_id=user_id,
            client_id=client_id, period_start=period_start, period_end=period_end,
            kind=kind, files=files,
            linked_pr_job_id=linked_pr_job_id,
            reuse_pr_doc_id=reuse_pr_doc_id,
            reuse_sf_doc_id=reuse_sf_doc_id,
        )
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })


# ── GET /jobs/{id} ─────────────────────────────────────────────────────


def _job_row_to_out(row: dict, *, linked_sf_job_id: Optional[UUID] = None) -> JobOut:
    return JobOut(**{
        "id": row["id"], "tenant_id": row["tenant_id"], "client_id": row["client_id"],
        "kind": row["kind"], "period_start": row["period_start"],
        "period_end": row["period_end"], "status": row["status"],
        "files_total": row["files_total"], "files_done": row["files_done"],
        "rows_total": row["rows_total"], "rows_needs_review": row["rows_needs_review"],
        "error_summary": row.get("error_summary"),
        "reconciliation_id": row.get("reconciliation_id"),
        "linked_pr_job_id": row.get("linked_pr_job_id"),
        "linked_sf_job_id": str(linked_sf_job_id) if linked_sf_job_id else None,
        "reuse_pr_doc_id": row.get("reuse_pr_doc_id"),
        "reuse_sf_doc_id": row.get("reuse_sf_doc_id"),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "completed_at": row.get("completed_at"),
    })


def _file_row_to_out(row: dict) -> IngestionFileOut:
    return IngestionFileOut(**{
        "id": row["id"], "job_id": row["job_id"],
        "original_filename": row["original_filename"],
        "mime_type": row["mime_type"], "byte_size": row["byte_size"],
        "engine": row.get("engine"), "status": row["status"],
        "rows_extracted": row["rows_extracted"], "needs_review": row["needs_review"],
        "warnings": row.get("warnings") or [], "error": row.get("error"),
        "extracted_at": row.get("extracted_at"),
    })


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
async def get_job_endpoint(
    job_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> JobDetailOut:
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # If this is a PR job, look up any SF job that linked back to it.
    linked_sf_job_id: Optional[UUID] = None
    if job["kind"] == "purchase_register":
        linked_sf_job_id = await p.find_linked_sf_job_id(job_id, tenant_id=tenant_id)
    files = await p.list_files(job_id, tenant_id=tenant_id)
    return JobDetailOut(
        job=_job_row_to_out(job, linked_sf_job_id=linked_sf_job_id),
        files=[_file_row_to_out(f) for f in files],
    )


# ── GET /jobs/{id}/rows ─────────────────────────────────────────────────


def _row_to_out(row: dict) -> ExtractedRowOut:
    return ExtractedRowOut(
        id=row["id"], file_id=row["file_id"], job_id=row["job_id"],
        source_page_no=row.get("source_page_no"),
        row_data=ExtractedRowData(**row["row_data"]),
        row_data_original=ExtractedRowData(**row["row_data_original"]),
        status=row["status"],
        field_warnings=[FieldWarning(**w) for w in (row.get("field_warnings") or [])],
        reviewed_by=row.get("reviewed_by"),
        reviewed_at=row.get("reviewed_at"),
        created_at=row["created_at"],
    )


@router.get("/jobs/{job_id}/rows", response_model=RowsListOut)
async def list_rows_endpoint(
    job_id: UUID,
    filter: str = Query("needs_review", pattern="^(needs_review|all)$"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> RowsListOut:
    rows = await p.list_rows(
        job_id, tenant_id=tenant_id,
        only_needs_review=(filter == "needs_review"),
        limit=limit, offset=offset,
    )
    out = [_row_to_out(r) for r in rows]
    return RowsListOut(rows=out, total=len(out), has_more=len(out) == limit)


# ── Row mutations: PATCH / confirm / reject / bulk-confirm ─────────────


@router.patch("/jobs/{job_id}/rows/{row_id}", response_model=ExtractedRowOut)
async def edit_row_endpoint(
    job_id: UUID, row_id: UUID, body: ExtractedRowData,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> ExtractedRowOut:
    await svc.edit_row(
        row_id=row_id, tenant_id=tenant_id, user_id=user_id, new_data=body,
    )
    rows = await p.list_rows(job_id, tenant_id=tenant_id, only_needs_review=False)
    found = next((r for r in rows if r["id"] == str(row_id)), None)
    if not found:
        raise HTTPException(status_code=404, detail="Row not found")
    return _row_to_out(found)


@router.post("/jobs/{job_id}/rows/{row_id}/confirm")
async def confirm_row_endpoint(
    job_id: UUID, row_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    await svc.confirm_row(row_id=row_id, tenant_id=tenant_id, user_id=user_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/rows/{row_id}/reject")
async def reject_row_endpoint(
    job_id: UUID, row_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    await svc.reject_row(row_id=row_id, tenant_id=tenant_id, user_id=user_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/rows/bulk-confirm")
async def bulk_confirm_endpoint(
    job_id: UUID, body: dict,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    row_ids = [UUID(x) for x in body.get("row_ids") or []]
    n = await svc.bulk_confirm(row_ids=row_ids, tenant_id=tenant_id, user_id=user_id)
    return {"confirmed_count": n}


# ── POST /jobs/{id}/finalize ───────────────────────────────────────────


@router.post("/jobs/{job_id}/finalize", response_model=FinalizeResponse)
async def finalize_endpoint(
    job_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> FinalizeResponse:
    try:
        recon_id = await svc.finalize_job(job_id=job_id, tenant_id=tenant_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })
    return FinalizeResponse(reconciliation_id=recon_id)


# ── GET /jobs/{id}/files/{file_id}/preview ─────────────────────────────


@router.get("/jobs/{job_id}/files/{file_id}/preview")
async def preview_file_endpoint(
    job_id: UUID, file_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> StreamingResponse:
    files = await p.list_files(job_id, tenant_id=tenant_id)
    target = next((f for f in files if f["id"] == str(file_id)), None)
    if target is None:
        raise HTTPException(status_code=404, detail="File not found")
    content = await download_original(target["storage_path"])
    return StreamingResponse(
        iter([content]),
        media_type=target["mime_type"],
        headers={
            "Content-Disposition": f'inline; filename="{target["original_filename"]}"',
        },
    )


# ── Column mappings ────────────────────────────────────────────────────


@router.get("/column-mappings/pending")
async def list_pending_mappings_endpoint(
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> dict:
    from app.database import get_supabase_admin
    import asyncio as _aio
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("ingestion_column_mappings")
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .is_("confirmed_by", "null")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

    res = await _aio.to_thread(_q)
    return {"mappings": res.data or []}


@router.post("/column-mappings/{mapping_id}/confirm")
async def confirm_mapping_endpoint(
    mapping_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    from app.database import get_supabase_admin
    import asyncio as _aio
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("ingestion_column_mappings")
            .update({"confirmed_by": str(user_id)})
            .eq("id", str(mapping_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await _aio.to_thread(_u)
    return {"ok": True}


from app.ingestion.schemas import (
    RecentDoc,
    RecentDocsOut,
    SessionStartRequest,
    SessionStartResponse,
)


@router.post("/sessions/start", response_model=SessionStartResponse)
async def start_session_endpoint(
    body: SessionStartRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> SessionStartResponse:
    try:
        result = await svc.start_session(
            tenant_id=tenant_id, user_id=user_id,
            client_id=body.client_id,
            period_start=body.period_start, period_end=body.period_end,
            reuse_pr_doc_id=body.reuse_pr_doc_id,
            reuse_sf_doc_id=body.reuse_sf_doc_id,
        )
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })
    return SessionStartResponse(**result)


@router.get("/documents/recent", response_model=RecentDocsOut)
async def list_recent_docs_endpoint(
    client_id: UUID,
    period_start: date,
    period_end: date,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> RecentDocsOut:
    pr_row, sf_row = await p.find_recent_docs(
        tenant_id=tenant_id, client_id=client_id,
        period_start=period_start, period_end=period_end,
    )
    return RecentDocsOut(
        pr=RecentDoc(**pr_row) if pr_row else None,
        sf=RecentDoc(**sf_row) if sf_row else None,
    )
