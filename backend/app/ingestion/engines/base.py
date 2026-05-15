"""Engine protocol + result type + context type.

All engines have the same single entry point:
    extract(file_bytes: bytes, ctx: ExtractionContext) -> ExtractedFileResult
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.ingestion.schemas import ExtractedRowData, JobKind

# Allowed values for ExtractedFileResult.extraction_engine.
# Used by tests to guard against typo drift.
EXTRACTION_ENGINES: set[str] = {
    "pandas",
    "pandas+llm-mapper",
    "pdfplumber+llm",
    "gemini-vision",
    # Reserved for a future cost-saver path; not implemented in v1.
    "tesseract+llm",
}


@dataclass
class ExtractionContext:
    """Per-job context passed into every engine."""
    kind: JobKind
    period_start: date
    period_end: date
    tenant_id: str  # for cache lookups + structlog binding


@dataclass
class ExtractedFileResult:
    """Uniform shape every engine returns."""
    rows: list[ExtractedRowData]
    needs_review: bool
    extraction_engine: str
    page_count: int
    warnings: list[dict] = field(default_factory=list)
    # Optional engine-emitted source-page mapping aligned to `rows`.
    source_pages: list[int | None] | None = None


class Engine(Protocol):
    """Each engine exposes a single sync `extract` (called from to_thread)."""

    name: str

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult: ...
