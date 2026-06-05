"""Pydantic models for working papers.

The composed_json shape is recipe-specific; each recipe defines its own
discriminated payload model. The umbrella WorkingPaperOut model exposes
the persisted row + the active payload.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class WorkingPaperKind(str, Enum):
    AT_RISK_ITC_SCHEDULE = "at_risk_itc_schedule"


class WorkingPaperStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"


class WorkingPaperEditSource(str, Enum):
    RECIPE_COMPOSED = "recipe_composed"
    USER_EDIT = "user_edit"
    RECIPE_REGENERATED = "recipe_regenerated"


# ── At-Risk ITC Schedule payload ──────────────────────────────────────────


class AtRiskLine(BaseModel):
    line_id: UUID
    supplier_name: Optional[str] = None
    supplier_bin: Optional[str] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[date] = None
    taxable_amount_bdt: Optional[Decimal] = None
    vat_amount_bdt: Optional[Decimal] = None
    match_status: Literal["exact", "fuzzy", "partial", "no_match"]
    match_score: Optional[Decimal] = None
    ca_override: Optional[Literal["approved", "disputed", "ignore"]] = None
    ca_notes: Optional[str] = None
    recommended_action: Literal[
        "chase_supplier", "reverse_claim", "partner_review",
        "approved_by_ca", "no_action",
    ]

    @field_serializer(
        "taxable_amount_bdt", "vat_amount_bdt", "match_score",
        when_used="json",
    )
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None


class AtRiskSupplierGroup(BaseModel):
    supplier_name: Optional[str] = None
    supplier_bin: Optional[str] = None
    lines: list[AtRiskLine]
    total_vat_at_risk_bdt: Decimal = Decimal("0.00")
    line_count: int = 0

    @field_serializer("total_vat_at_risk_bdt", when_used="json")
    def _money(self, v: Decimal) -> str:
        return str(_to_2dp(v))


class AtRiskSummary(BaseModel):
    total_vat_claimed_bdt: Decimal
    safe_itc_bdt: Decimal
    at_risk_itc_bdt: Decimal
    total_lines: int
    at_risk_line_count: int
    supplier_count_at_risk: int

    @field_serializer(
        "total_vat_claimed_bdt", "safe_itc_bdt", "at_risk_itc_bdt",
        when_used="json",
    )
    def _money(self, v: Decimal) -> str:
        return str(_to_2dp(v))


class AtRiskItcSchedulePayload(BaseModel):
    kind: Literal["at_risk_itc_schedule"] = "at_risk_itc_schedule"
    recipe_version: str
    client_id: UUID
    client_name: str
    client_bin: Optional[str] = None
    reconciliation_id: UUID
    period_start: date
    period_end: date
    summary: AtRiskSummary
    supplier_groups: list[AtRiskSupplierGroup]


# Future kinds added to this union; discriminator on `kind`.
WorkingPaperPayload = Annotated[
    Union[AtRiskItcSchedulePayload],
    Field(discriminator="kind"),
]


# ── API DTOs ───────────────────────────────────────────────────────────────


class WorkingPaperOut(BaseModel):
    id: UUID
    tenant_id: UUID
    client_id: UUID
    kind: WorkingPaperKind
    reconciliation_id: Optional[UUID] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    recipe_version: str
    composed_json: dict[str, Any]
    notes_html: str
    status: WorkingPaperStatus
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[UUID] = None
    composed_by: UUID
    created_at: datetime
    updated_at: datetime


class ComposeWorkingPaperRequest(BaseModel):
    kind: WorkingPaperKind
    reconciliation_id: UUID  # required for at_risk_itc_schedule


class UpdateNotesRequest(BaseModel):
    notes_html: str


class ReopenWorkingPaperRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class FinalizeWorkingPaperResponse(BaseModel):
    working_paper_id: UUID
    status: WorkingPaperStatus
