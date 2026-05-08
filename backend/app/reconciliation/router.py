"""Reconciliation API endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_tenant_id, get_current_user_id

from .schemas import ReconciliationCreateRequest, ReconciliationCreateResponse
from .service import run_reconciliation

router = APIRouter(prefix="/api/v1/reconciliations", tags=["reconciliation"])


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
