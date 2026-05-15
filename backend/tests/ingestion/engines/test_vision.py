"""Vision engine tests — uses StubLLMAdapter; never hits real Gemini."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.vision import VisionEngine
from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.ingestion.schemas import JobKind

SCAN_PDF = Path(__file__).parents[1] / "fixtures" / "mushak_6.3_scan.pdf"
PHOTO_JPG = Path(__file__).parents[1] / "fixtures" / "phone_photo_invoice.jpg"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_vision_on_scanned_pdf_marks_review_required():
    set_llm_adapter(StubLLMAdapter(extractions={
        "vision-test-key": [{
            "invoice_no": "SCAN-001",
            "supplier_bin": "222333444",
            "buyer_bin": "111222333",
            "invoice_date": "2026-05-20",
            "taxable_amount_bdt": "3200.00",
            "vat_amount_bdt": "480.00",
        }],
    }))
    engine = VisionEngine(lookup_key_for_test="vision-test-key")
    res = engine.extract(SCAN_PDF.read_bytes(), _ctx())
    assert res.extraction_engine == "gemini-vision"
    assert res.needs_review is True
    assert len(res.rows) == 1
    assert res.rows[0].invoice_no == "SCAN-001"


def test_vision_on_jpeg_photo_works():
    set_llm_adapter(StubLLMAdapter(extractions={
        "photo-test-key": [{
            "invoice_no": "SCAN-001",
            "supplier_bin": "222333444",
            "buyer_bin": "111222333",
            "invoice_date": "2026-05-20",
            "taxable_amount_bdt": "3200.00",
            "vat_amount_bdt": "480.00",
        }],
    }))
    engine = VisionEngine(lookup_key_for_test="photo-test-key")
    res = engine.extract(PHOTO_JPG.read_bytes(), _ctx())
    assert res.needs_review is True
    assert len(res.rows) == 1
