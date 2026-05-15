"""Born-digital PDF engine tests — uses StubLLMAdapter."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.ingestion.schemas import JobKind

FIXTURE = Path(__file__).parents[1] / "fixtures" / "mushak_6.3_borndigital.pdf"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_borndigital_extracts_one_row(monkeypatch):
    set_llm_adapter(StubLLMAdapter(extractions={
        "test-key": [{
            "invoice_no": "INV-2026-001",
            "supplier_bin": "987654321",
            "supplier_name": "ACME Ltd",
            "invoice_date": "2026-05-15",
            "taxable_amount_bdt": "5000.00",
            "vat_amount_bdt": "750.00",
        }],
    }))
    engine = PdfBornDigitalEngine(lookup_key_for_test="test-key")
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert res.extraction_engine == "pdfplumber+llm"
    assert res.needs_review is False
    assert len(res.rows) == 1
    assert res.rows[0].invoice_no == "INV-2026-001"
    assert res.rows[0].taxable_amount_bdt == Decimal("5000.00")


def test_borndigital_text_density_heuristic_passes_for_textful_pdf():
    engine = PdfBornDigitalEngine()
    is_text = engine.has_extractable_text(FIXTURE.read_bytes())
    assert is_text is True
