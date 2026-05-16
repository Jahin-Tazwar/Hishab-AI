"""Pydantic models for the ingestion module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Enums (mirror Postgres enum types from migration 0014) ────────────────


class JobKind(str, Enum):
    PURCHASE_REGISTER = "purchase_register"
    SUPPLIER_EXPORT = "supplier_export"


class JobStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    READY_FOR_REVIEW = "ready_for_review"
    CONFIRMED = "confirmed"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    FAILED = "failed"


class FileStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"
    SKIPPED = "skipped"


class RowStatus(str, Enum):
    AUTO_PASSED = "auto_passed"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EDITED = "edited"


# ── Inbound API ──────────────────────────────────────────────────────────


class CreateJobRequest(BaseModel):
    """Multipart form-data fields for POST /api/v1/ingestion/jobs.

    The actual file uploads come through FastAPI's UploadFile in the router;
    this model carries the non-file fields.
    """

    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    period_start: date
    period_end: date
    kind: JobKind
    linked_pr_job_id: Optional[UUID] = None
    reuse_pr_doc_id: Optional[UUID] = None
    reuse_sf_doc_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _period_ordered(self) -> "CreateJobRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class CreateJobFileSummary(BaseModel):
    file_id: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    accepted: bool
    rejection_reason: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: UUID
    files: list[CreateJobFileSummary]


# ── Internal: canonical extracted row shape (matches PurchaseRow/SupplierRow) ─


class ExtractedRowData(BaseModel):
    """Canonical shape for any extracted row, regardless of source engine.

    Mirrors the union of fields in reconciliation.schemas.PurchaseRow
    and SupplierRow. The `kind` of the parent job determines which fields
    are required at handoff time; both schemas tolerate the union here.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_no: str
    invoice_date: date
    taxable_amount_bdt: Decimal
    vat_amount_bdt: Decimal
    supplier_bin: Optional[str] = None
    supplier_name: Optional[str] = None
    buyer_bin: Optional[str] = None

    @field_validator("taxable_amount_bdt", "vat_amount_bdt", mode="before")
    @classmethod
    def _round(cls, v: object) -> Decimal:
        return _to_2dp(v)  # type: ignore[arg-type]


class FieldWarning(BaseModel):
    field: str
    code: str
    message: str


# ── Outbound API: list rows for review ────────────────────────────────────


class ExtractedRowOut(BaseModel):
    id: UUID
    file_id: UUID
    job_id: UUID
    source_page_no: Optional[int] = None
    row_data: ExtractedRowData
    row_data_original: ExtractedRowData
    status: RowStatus
    field_warnings: list[FieldWarning] = Field(default_factory=list)
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class JobOut(BaseModel):
    id: UUID
    tenant_id: UUID
    client_id: UUID
    kind: JobKind
    period_start: date
    period_end: date
    status: JobStatus
    files_total: int
    files_done: int
    rows_total: int
    rows_needs_review: int
    error_summary: Optional[str] = None
    reconciliation_id: Optional[UUID] = None
    linked_pr_job_id: Optional[UUID] = None
    linked_sf_job_id: Optional[UUID] = None
    reuse_pr_doc_id: Optional[UUID] = None
    reuse_sf_doc_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class IngestionFileOut(BaseModel):
    id: UUID
    job_id: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    engine: Optional[str] = None
    status: FileStatus
    rows_extracted: int
    needs_review: bool
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    extracted_at: Optional[datetime] = None


class JobDetailOut(BaseModel):
    job: JobOut
    files: list[IngestionFileOut]


class RowsListOut(BaseModel):
    rows: list[ExtractedRowOut]
    total: int
    has_more: bool


class FinalizeResponse(BaseModel):
    reconciliation_id: UUID


# ── Column mapping ───────────────────────────────────────────────────────


class ColumnMappingOut(BaseModel):
    id: UUID
    kind: JobKind
    header_signature: str
    mapping: dict[str, Optional[str]]
    confirmed_by: Optional[UUID] = None
    created_at: datetime


# ── Session start (new combined wizard entry point) ──────────────────────


class SessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    period_start: date
    period_end: date
    reuse_pr_doc_id: Optional[UUID] = None
    reuse_sf_doc_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _period_ordered(self) -> "SessionStartRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class SessionStartResponse(BaseModel):
    """Exactly one of the three IDs (or only `reconciliation_id`) is set.

    - Both reuses: only `reconciliation_id`.
    - PR fresh: `pr_job_id` only.
    - PR reused, SF fresh: `sf_job_id` only (SF job carries reuse_pr_doc_id).
    - PR fresh, SF reused: `pr_job_id` only (PR job carries reuse_sf_doc_id).
    """

    pr_job_id: Optional[UUID] = None
    sf_job_id: Optional[UUID] = None
    reconciliation_id: Optional[UUID] = None


# ── Recent documents (drives the reuse UI) ───────────────────────────────


class RecentDoc(BaseModel):
    id: UUID
    doc_type: str  # 'purchase_register' | 'supplier_export'
    original_filename: str
    file_size_bytes: Optional[int] = None
    created_at: datetime


class RecentDocsOut(BaseModel):
    pr: Optional[RecentDoc] = None
    sf: Optional[RecentDoc] = None
