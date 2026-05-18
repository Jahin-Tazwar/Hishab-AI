"""FastAPI endpoints for notices. Mounted at /api/v1/notices."""
from __future__ import annotations

import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_tenant_id, get_current_user_id
from app.notices import persistence as p
from app.notices import service as svc
from app.notices.schemas import (
    NoticeDraftOut, NoticeOut, RelinkRequest, ReopenDraftRequest,
    SaveDraftRequest, FinalizeDraftResponse,
)

router = APIRouter(prefix="/api/v1/notices", tags=["notices"])


@router.post("/", status_code=201)
async def upload_notice(
    client_id: UUID,
    file: UploadFile = File(...),
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    nid = await svc.create_notice(
        tenant_id=tenant_id, user_id=user_id,
        client_id=client_id, file=file,
    )
    return {"notice_id": str(nid)}


@router.get("/", response_model=list[NoticeOut])
async def list_notices(
    client_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    rows = await p.list_notices(tenant_id=tenant_id, client_id=client_id)
    return [NoticeOut.model_validate(r) for r in rows]


@router.get("/{notice_id}", response_model=NoticeOut)
async def get_notice(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    n = await p.get_notice(notice_id, tenant_id=tenant_id)
    if not n:
        from app.notices.exceptions import NoticeNotFoundError
        raise NoticeNotFoundError(f"Notice {notice_id} not found")
    return NoticeOut.model_validate(n)


@router.post("/{notice_id}/relink", status_code=202)
async def relink(
    notice_id: UUID,
    body: RelinkRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    await svc.relink_notice(
        notice_id=notice_id, tenant_id=tenant_id,
        client_id=body.client_id,
        period_start=body.period_start, period_end=body.period_end,
        reconciliation_id=body.reconciliation_id,
    )
    return {"ok": True}


@router.post("/{notice_id}/draft", status_code=202)
async def generate_draft(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    await svc.generate_draft(notice_id=notice_id, tenant_id=tenant_id)
    return {"ok": True}


@router.get("/{notice_id}/draft", response_model=NoticeDraftOut)
async def get_draft(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    d = await p.get_draft(notice_id, tenant_id=tenant_id)
    if not d:
        from app.notices.exceptions import DraftNotFoundError
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    return NoticeDraftOut.model_validate(d)


@router.put("/{notice_id}/draft")
async def save_draft(
    notice_id: UUID,
    body: SaveDraftRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.save_draft_revision(
        notice_id=notice_id, tenant_id=tenant_id, user_id=user_id,
        body_html=body.body_html, appendix_json=body.appendix_json,
    )
    return {"ok": True}


@router.get("/{notice_id}/draft/revisions")
async def list_draft_revisions(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    d = await p.get_draft(notice_id, tenant_id=tenant_id)
    if not d:
        return []
    return await p.list_revisions(UUID(d["id"]), tenant_id=tenant_id)


@router.post("/{notice_id}/draft/finalize", response_model=FinalizeDraftResponse)
async def finalize(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    draft_id = await svc.finalize_draft(
        notice_id=notice_id, tenant_id=tenant_id, user_id=user_id,
    )
    return FinalizeDraftResponse(
        notice_id=notice_id, draft_id=draft_id,
        status="finalized",
    )


@router.post("/{notice_id}/draft/reopen")
async def reopen(
    notice_id: UUID,
    body: ReopenDraftRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.reopen_draft_for_edit(
        notice_id=notice_id, tenant_id=tenant_id, user_id=user_id,
        reason=body.reason,
    )
    return {"ok": True}


@router.get("/{notice_id}/draft/export")
async def export(
    notice_id: UUID,
    format: str = Query(..., regex="^(docx|pdf)$"),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    data, ctype, fname = await svc.export_draft(
        notice_id=notice_id, tenant_id=tenant_id, format=format,
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
