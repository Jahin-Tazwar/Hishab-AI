"""Pandas LLM-mapper engine tests — uses StubLLMAdapter."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.pandas_mapper import PandasMapperEngine
from app.ingestion.llm import StubLLMAdapter, column_signature, set_llm_adapter
from app.ingestion.schemas import JobKind

FIXTURE = Path(__file__).parents[1] / "fixtures" / "bangla_headers.xlsx"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_mapper_uses_llm_to_remap_headers_then_parses():
    sig = column_signature(["বিল নং", "BIN", "নাম", "তারিখ", "মোট", "VAT"])
    set_llm_adapter(StubLLMAdapter(column_mappings={
        sig: {
            "invoice_no": "বিল নং",
            "supplier_bin": "BIN",
            "supplier_name": "নাম",
            "buyer_bin": None,
            "invoice_date": "তারিখ",
            "taxable_amount_bdt": "মোট",
            "vat_amount_bdt": "VAT",
        }
    }))
    engine = PandasMapperEngine(
        mapping_cache_get=lambda **kw: None,   # force cache miss
        mapping_cache_put=lambda **kw: None,   # no-op write
    )
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert res.extraction_engine == "pandas+llm-mapper"
    assert res.needs_review is False
    assert len(res.rows) == 2
    assert res.rows[0].invoice_no == "INV-A"
    assert res.rows[0].supplier_bin == "111222333"
    assert res.rows[0].supplier_name == "Bangla Supplier"
    assert res.rows[0].taxable_amount_bdt == Decimal("500.00")


def test_mapper_uses_cache_when_available():
    """When cache returns a mapping, LLM is not called."""
    sig = column_signature(["বিল নং", "BIN", "নাম", "তারিখ", "মোট", "VAT"])
    # Empty stub → would raise if called
    set_llm_adapter(StubLLMAdapter(column_mappings={}))
    engine = PandasMapperEngine(
        mapping_cache_get=lambda **kw: {
            "invoice_no": "বিল নং",
            "supplier_bin": "BIN",
            "supplier_name": "নাম",
            "buyer_bin": None,
            "invoice_date": "তারিখ",
            "taxable_amount_bdt": "মোট",
            "vat_amount_bdt": "VAT",
        },
        mapping_cache_put=lambda **kw: None,
    )
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert len(res.rows) == 2
    assert res.rows[1].invoice_no == "INV-B"
