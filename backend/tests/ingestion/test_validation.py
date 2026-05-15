"""Tests for deterministic field-level validators."""
from datetime import date
from decimal import Decimal

from app.ingestion.schemas import ExtractedRowData, JobKind
from app.ingestion.validation import validate_row


def _row(**over):
    base = dict(
        invoice_no="INV-1",
        supplier_bin="123456789",
        supplier_name="ACME",
        invoice_date=date(2026, 5, 10),
        taxable_amount_bdt=Decimal("1000.00"),
        vat_amount_bdt=Decimal("150.00"),
    )
    base.update(over)
    return ExtractedRowData(**base)


def test_clean_purchase_row_has_no_warnings():
    warnings = validate_row(
        _row(),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    assert warnings == []


def test_short_bin_is_flagged():
    warnings = validate_row(
        _row(supplier_bin="123"),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.field == "supplier_bin" and w.code == "BIN_FORMAT" for w in warnings)


def test_date_outside_period_flagged_soft():
    warnings = validate_row(
        _row(invoice_date=date(2026, 4, 15)),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.field == "invoice_date" and w.code == "DATE_OUT_OF_PERIOD" for w in warnings)


def test_vat_outside_15pct_band_flagged():
    # 4-16% sanity band: VAT of 30 (3%) falls below 4% lower bound
    warnings = validate_row(
        _row(vat_amount_bdt=Decimal("30.00")),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.code == "VAT_RATIO_UNUSUAL" for w in warnings)


def test_supplier_export_requires_buyer_bin():
    warnings = validate_row(
        _row(buyer_bin=None, supplier_bin=None),
        kind=JobKind.SUPPLIER_EXPORT,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.field == "buyer_bin" and w.code == "BIN_MISSING" for w in warnings)
