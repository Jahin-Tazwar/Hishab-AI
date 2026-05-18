"""Pydantic models for the notices module.

Mirrors the conventions in app/ingestion/schemas.py:
- Enum string values exactly match the corresponding Postgres enums (0019).
- Money fields are Decimal at runtime, serialized as "1234.50" strings.
- Discriminated unions use `kind` literals so the frontend can switch on them.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import (
    BaseModel, ConfigDict, Field, field_serializer, field_validator,
    model_validator,
)


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Enums (mirror Postgres types from migration 0019) ────────────────────


class NoticeStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    AWAITING_DATA = "awaiting_data"
    READY_TO_DRAFT = "ready_to_draft"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    FINALIZED = "finalized"
    FAILED = "failed"


class NoticeType(str, Enum):
    INPUT_VAT_MISMATCH = "input_vat_mismatch"
    UNSUPPORTED = "unsupported"


class NoticeDraftStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    FINALIZED = "finalized"


class NoticeDraftEditSource(str, Enum):
    LLM_GENERATED = "llm_generated"
    USER_EDIT = "user_edit"
    REGENERATED = "regenerated"


# ── Parsed notice (parser output) ─────────────────────────────────────────


class ParsedNotice(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    notice_no: Optional[str] = None
    notice_date: Optional[date] = None
    notice_type: NoticeType
    taxpayer_bin: Optional[str] = None
    taxpayer_tin: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    alleged_itc_claimed_bdt: Optional[Decimal] = None
    alleged_itc_allowed_bdt: Optional[Decimal] = None
    alleged_shortfall_bdt: Optional[Decimal] = None
    classification_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("taxpayer_bin", "taxpayer_tin", mode="before")
    @classmethod
    def _digits_only(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return re.sub(r"\D+", "", str(v))

    @model_validator(mode="after")
    def _check_period(self) -> "ParsedNotice":
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")
        return self

    @field_serializer(
        "alleged_itc_claimed_bdt", "alleged_itc_allowed_bdt", "alleged_shortfall_bdt",
        when_used="json",
    )
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(_to_2dp(v)) if v is not None else None


# ── Linker discriminated union ────────────────────────────────────────────


class LinkedRecon(BaseModel):
    kind: Literal["linked_recon"] = "linked_recon"
    reconciliation_id: UUID
    client_id: UUID


class NeedsIngestion(BaseModel):
    kind: Literal["needs_ingestion"] = "needs_ingestion"
    client_id: UUID
    period_start: date
    period_end: date


class NeedsManualLink(BaseModel):
    kind: Literal["needs_manual_link"] = "needs_manual_link"
    candidate_clients: list[UUID] = Field(default_factory=list)


LinkerResult = Annotated[
    Union[LinkedRecon, NeedsIngestion, NeedsManualLink],
    Field(discriminator="kind"),
]


# ── Retrieval / drafter inputs ────────────────────────────────────────────


class CitationChunk(BaseModel):
    id: UUID
    source: str
    source_ref: str
    subsection: Optional[str] = None
    language: Literal["bn", "en"]
    title: str
    body: str


class ReconSummary(BaseModel):
    reconciliation_id: UUID
    safe_itc_bdt: Decimal
    at_risk_itc_bdt: Decimal
    total_vat_claimed_bdt: Decimal
    matched_exact: int
    matched_fuzzy: int
    partial_match: int
    no_match: int
    disputed_rows: list[dict[str, Any]] = Field(default_factory=list)

    @field_serializer(
        "safe_itc_bdt", "at_risk_itc_bdt", "total_vat_claimed_bdt",
        when_used="json",
    )
    def _money(self, v: Decimal) -> str:
        return str(_to_2dp(v))


# ── Drafter output ────────────────────────────────────────────────────────


class DraftParagraph(BaseModel):
    text: str
    citation_tags: list[str] = Field(default_factory=list)


class DraftAppendixRow(BaseModel):
    label: str
    value_bdt: Optional[Decimal] = None
    note: Optional[str] = None

    @field_serializer("value_bdt", when_used="json")
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(_to_2dp(v)) if v is not None else None


class DraftReply(BaseModel):
    body_paragraphs: list[DraftParagraph]
    computation_table_rows: list[DraftAppendixRow]
    cited_refs: list[str] = Field(default_factory=list)


# ── API request/response DTOs ─────────────────────────────────────────────


class NoticeOut(BaseModel):
    id: UUID
    tenant_id: UUID
    client_id: UUID
    created_by: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    status: NoticeStatus
    parse_error: Optional[str] = None
    notice_no: Optional[str] = None
    notice_date: Optional[date] = None
    notice_type: Optional[NoticeType] = None
    taxpayer_bin: Optional[str] = None
    taxpayer_tin: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    alleged_itc_claimed_bdt: Optional[Decimal] = None
    alleged_itc_allowed_bdt: Optional[Decimal] = None
    alleged_shortfall_bdt: Optional[Decimal] = None
    linked_reconciliation_id: Optional[UUID] = None
    linked_ingestion_job_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "alleged_itc_claimed_bdt", "alleged_itc_allowed_bdt", "alleged_shortfall_bdt",
        when_used="json",
    )
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(_to_2dp(v)) if v is not None else None


class CitationOut(BaseModel):
    corpus_chunk_id: UUID
    source_ref: str
    snippet: str
    paragraph_idx: int


class NoticeDraftOut(BaseModel):
    # `model_version` starts with `model_` which Pydantic 2 reserves for its
    # own attributes; opt out of the protected-namespace warning.
    model_config = ConfigDict(protected_namespaces=())

    id: UUID
    notice_id: UUID
    language: str
    body_html: str
    appendix_json: dict[str, Any]
    citations: list[CitationOut]
    model_version: str
    status: NoticeDraftStatus
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class RelinkRequest(BaseModel):
    client_id: UUID
    period_start: date
    period_end: date
    reconciliation_id: Optional[UUID] = None


class SaveDraftRequest(BaseModel):
    body_html: str
    appendix_json: dict[str, Any]


class FinalizeDraftResponse(BaseModel):
    notice_id: UUID
    draft_id: UUID
    status: NoticeDraftStatus


class ReopenDraftRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
