"""Pandas canonical-headers engine tests."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.pandas_canonical import PandasCanonicalEngine
from app.ingestion.schemas import JobKind

FIXTURE = Path(__file__).parents[1] / "fixtures" / "canonical_register.xlsx"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_canonical_xlsx_is_handled_returns_two_rows():
    engine = PandasCanonicalEngine()
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert res.extraction_engine == "pandas"
    assert res.needs_review is False
    assert len(res.rows) == 2
    assert res.rows[0].invoice_no == "INV-1"
    assert res.rows[0].taxable_amount_bdt == Decimal("1000.00")
    assert res.rows[0].vat_amount_bdt == Decimal("150.00")


def test_canonical_handles_returns_true_only_for_canonical_headers():
    engine = PandasCanonicalEngine()
    assert engine.handles_headers([
        "Invoice No", "Supplier BIN", "Supplier Name",
        "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
    ], JobKind.PURCHASE_REGISTER) is True
    assert engine.handles_headers([
        "Bill No", "BIN", "Name", "Date", "Amount", "VAT",
    ], JobKind.PURCHASE_REGISTER) is False
