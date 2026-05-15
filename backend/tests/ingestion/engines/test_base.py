"""Smoke tests for the engine base types."""
from app.ingestion.engines.base import (
    EXTRACTION_ENGINES,
    ExtractedFileResult,
    ExtractionContext,
)
from app.ingestion.schemas import ExtractedRowData
from datetime import date


def test_extraction_engines_constants_present():
    assert "pandas" in EXTRACTION_ENGINES
    assert "pandas+llm-mapper" in EXTRACTION_ENGINES
    assert "pdfplumber+llm" in EXTRACTION_ENGINES
    assert "gemini-vision" in EXTRACTION_ENGINES


def test_result_construction():
    res = ExtractedFileResult(
        rows=[ExtractedRowData(
            invoice_no="X", invoice_date=date(2026, 5, 1),
            taxable_amount_bdt="1", vat_amount_bdt="0.15",
        )],
        needs_review=False,
        extraction_engine="pandas",
        page_count=1,
        warnings=[],
    )
    assert res.rows[0].invoice_no == "X"


def test_context_carries_period_and_kind():
    from app.ingestion.schemas import JobKind
    ctx = ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )
    assert ctx.kind == JobKind.PURCHASE_REGISTER
