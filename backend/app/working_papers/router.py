"""FastAPI endpoints for working papers. Mounted at /api/v1/working-papers."""
from __future__ import annotations

import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_tenant_id, get_current_user_id
from app.working_papers import persistence as p
from app.working_papers import service as svc
from app.working_papers.exceptions import WorkingPaperNotFoundError
from app.working_papers.schemas import (
    ComposeWorkingPaperRequest,
    FinalizeWorkingPaperResponse,
    ReopenWorkingPaperRequest,
    UpdateNotesRequest,
    WorkingPaperKind,
    WorkingPaperOut,
    WorkingPaperStatus,
)

router = APIRouter(prefix="/api/v1/working-papers", tags=["working-papers"])


@router.post("/", status_code=201)
async def compose_working_paper(
    body: ComposeWorkingPaperRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    wp_id = await svc.compose_working_paper(
        tenant_id=tenant_id, user_id=user_id,
        kind=body.kind, reconciliation_id=body.reconciliation_id,
        notice_id=body.notice_id,
    )
    return {"working_paper_id": str(wp_id)}


@router.get("/", response_model=list[WorkingPaperOut])
async def list_working_papers(
    client_id: Optional[UUID] = Query(default=None),
    kind: Optional[WorkingPaperKind] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    rows = await svc.list_working_papers(
        tenant_id=tenant_id, client_id=client_id, kind=kind, limit=limit,
    )
    return [WorkingPaperOut.model_validate(r) for r in rows]


@router.get("/{wp_id}", response_model=WorkingPaperOut)
async def get_working_paper(
    wp_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    wp = await svc.get_working_paper(wp_id=wp_id, tenant_id=tenant_id)
    return WorkingPaperOut.model_validate(wp)


@router.put("/{wp_id}/notes")
async def update_notes(
    wp_id: UUID,
    body: UpdateNotesRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.update_notes(
        wp_id=wp_id, tenant_id=tenant_id, user_id=user_id,
        notes_html=body.notes_html,
    )
    return {"ok": True}


@router.post("/{wp_id}/regenerate", status_code=202)
async def regenerate(
    wp_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.regenerate_working_paper(
        wp_id=wp_id, tenant_id=tenant_id, user_id=user_id,
    )
    return {"ok": True}


@router.get("/{wp_id}/revisions")
async def list_revisions(
    wp_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    return await p.list_revisions(wp_id, tenant_id=tenant_id)


@router.post("/{wp_id}/finalize", response_model=FinalizeWorkingPaperResponse)
async def finalize(
    wp_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.finalize_working_paper(
        wp_id=wp_id, tenant_id=tenant_id, user_id=user_id,
    )
    return FinalizeWorkingPaperResponse(
        working_paper_id=wp_id, status=WorkingPaperStatus.FINALIZED,
    )


@router.post("/{wp_id}/reopen")
async def reopen(
    wp_id: UUID,
    body: ReopenWorkingPaperRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.reopen_working_paper_for_edit(
        wp_id=wp_id, tenant_id=tenant_id, user_id=user_id, reason=body.reason,
    )
    return {"ok": True}


@router.get("/{wp_id}/export")
async def export(
    wp_id: UUID,
    format: str = Query(..., regex="^(docx|pdf)$"),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    data, ctype, fname = await svc.export_working_paper(
        wp_id=wp_id, tenant_id=tenant_id, format=format,
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
