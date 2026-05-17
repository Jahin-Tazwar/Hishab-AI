"""Pydantic models for the reconciliation flow."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    """Round to 2 decimal places using banker-safe HALF_UP."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class MatchStatus(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    PARTIAL = "partial"
    NO_MATCH = "no_match"


class CAOverride(str, Enum):
    APPROVED = "approved"
    DISPUTED = "disputed"
    IGNORE = "ignore"


# ── Inbound API ──────────────────────────────────────────────────────────


class ReconciliationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    period_start: date
    period_end: date
    purchase_register_doc_id: UUID
    supplier_data_doc_id: UUID

    @model_validator(mode="after")
    def _period_ordered(self) -> "ReconciliationCreateRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ReconciliationCreateResponse(BaseModel):
    reconciliation_id: UUID


# ── Parser DTOs ──────────────────────────────────────────────────────────


class PurchaseRow(BaseModel):
    """One row from the purchase register XLSX."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_no: str
    supplier_bin: Optional[str] = None
    supplier_name: Optional[str] = None
    invoice_date: date
    taxable_amount_bdt: Decimal
    vat_amount_bdt: Decimal

    @field_validator("taxable_amount_bdt", "vat_amount_bdt", mode="before")
    @classmethod
    def _round(cls, v: object) -> Decimal:
        return _to_2dp(v)  # type: ignore[arg-type]


class SupplierRow(BaseModel):
    """One row from the supplier-filed export XLSX."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_no: str
    invoice_date: date
    taxable_amount_bdt: Decimal
    vat_amount_bdt: Decimal
    buyer_bin: Optional[str] = None

    @field_validator("taxable_amount_bdt", "vat_amount_bdt", mode="before")
    @classmethod
    def _round(cls, v: object) -> Decimal:
        return _to_2dp(v)  # type: ignore[arg-type]


# ── Matcher output DTOs ──────────────────────────────────────────────────


class DiscrepancyFlags(BaseModel):
    date_off_by_days: Optional[int] = None
    amount_diff_bdt: Optional[Decimal] = None
    amount_diff_pct: Optional[float] = None
    reason: Optional[str] = None


class MatchResult(BaseModel):
    """Result of matching one purchase row against the supplier pool."""
    pr_row: PurchaseRow
    sf_row: Optional[SupplierRow] = None
    status: MatchStatus
    score: Decimal
    flags: DiscrepancyFlags = Field(default_factory=DiscrepancyFlags)


class AggregatesDTO(BaseModel):
    total_invoices: int
    matched_exact: int
    matched_fuzzy: int
    partial_match: int
    no_match: int
    total_vat_claimed_bdt: Decimal
    safe_itc_bdt: Decimal
    at_risk_itc_bdt: Decimal


# ── Override endpoint ────────────────────────────────────────────────────


class LineItemOverrideRequest(BaseModel):
    """Body for POST /reconciliations/{id}/line-items/{line_id}/override.

    `ca_override` is nullable so callers can clear a previously-set override
    by passing `null`. `ca_notes` is independent — a CA can update notes
    without changing the decision.
    """
    model_config = ConfigDict(extra="forbid")

    ca_override: Optional[CAOverride] = None
    ca_notes: Optional[str] = None


class LineItemOverrideResponse(BaseModel):
    """Returns the refreshed line item plus the new aggregate totals so the
    client can update its caches with a single round-trip.
    """
    line_item_id: UUID
    ca_override: Optional[CAOverride]
    ca_notes: Optional[str]
    aggregates: AggregatesDTO
