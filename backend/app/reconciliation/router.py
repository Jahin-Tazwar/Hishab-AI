"""Reconciliation API endpoints."""
from __future__ import annotations

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_tenant_id, get_current_user_id

from .exporter import export_reconciliation
from .schemas import ReconciliationCreateRequest, ReconciliationCreateResponse
from .service import run_reconciliation

router = APIRouter(prefix="/api/v1/reconciliations", tags=["reconciliation"])

_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ReconciliationCreateResponse,
)
async def create_reconciliation(
    body: ReconciliationCreateRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> ReconciliationCreateResponse:
    """Run a synchronous VAT reconciliation. Returns the new reconciliation id."""
    new_id = await run_reconciliation(body, tenant_id=tenant_id, user_id=user_id)
    return ReconciliationCreateResponse(reconciliation_id=new_id)


@router.get("/{reconciliation_id}/export")
async def export_reconciliation_xlsx(
    reconciliation_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> StreamingResponse:
    """Download a reconciliation as a styled XLSX (Summary + Line Items)."""
    data = await export_reconciliation(
        reconciliation_id=reconciliation_id,
        tenant_id=tenant_id,
    )
    filename = f"reconciliation-{reconciliation_id}.xlsx"
    return StreamingResponse(
        BytesIO(data),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
