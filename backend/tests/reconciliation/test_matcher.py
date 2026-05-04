"""Tests for the matching engine."""
from datetime import date
from decimal import Decimal

from app.reconciliation.matcher import match_register, match_one
from app.reconciliation.schemas import (
    MatchStatus, PurchaseRow, SupplierRow,
)


def _pr(invoice_no: str = "INV-1", bin_: str | None = "111111111",
        d: date = date(2024, 1, 15), tax: float = 1000, vat: float = 150) -> PurchaseRow:
    return PurchaseRow(
        invoice_no=invoice_no, supplier_bin=bin_, supplier_name="X",
        invoice_date=d, taxable_amount_bdt=tax, vat_amount_bdt=vat,
    )


def _sf(invoice_no: str = "INV-1", buyer_bin: str | None = "999999999",
        d: date = date(2024, 1, 15), tax: float = 1000, vat: float = 150) -> SupplierRow:
    return SupplierRow(
        invoice_no=invoice_no, invoice_date=d,
        taxable_amount_bdt=tax, vat_amount_bdt=vat, buyer_bin=buyer_bin,
    )


# ── EXACT ───────────────────────────────────────────────────────────────


def test_exact_match_when_all_fields_align():
    pr = _pr("INV-0023", "111111111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-23", "x", date(2024, 1, 15), 1000, 150)]  # invoice_no normalized matches
    by_bin = {"111111111": pool}

    result = match_one(pr, by_bin)
    assert result.status == MatchStatus.EXACT
    assert result.score == Decimal("1.00")


def test_exact_normalizes_invoice_no():
    pr = _pr("INV-0023/2024")
    pool = [_sf("inv 23 / 2024")]
    by_bin = {pr.supplier_bin: pool}
    assert match_one(pr, by_bin).status == MatchStatus.EXACT


# ── FUZZY ───────────────────────────────────────────────────────────────


def test_fuzzy_when_date_off_by_3_days_and_amount_within_half_pct():
    pr = _pr("INV-1", "111", date(2024, 1, 15), 1000.00, 150.00)
    pool = [_sf("INV-1", "x", date(2024, 1, 18), 1003.00, 150.45)]  # within 0.5%
    by_bin = {"111": pool}

    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.FUZZY
    assert res.score == Decimal("0.80")
    assert res.flags.date_off_by_days == 3
    assert res.flags.amount_diff_pct is not None
    assert res.flags.amount_diff_pct < 0.005


def test_fuzzy_falls_through_when_date_off_by_4_days():
    pr = _pr("INV-1", "111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-1", "x", date(2024, 1, 19), 1000, 150)]
    by_bin = {"111": pool}
    assert match_one(pr, by_bin).status == MatchStatus.PARTIAL


def test_fuzzy_falls_through_when_amount_off_by_1pct():
    pr = _pr("INV-1", "111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-1", "x", date(2024, 1, 15), 1010, 151.5)]  # 1% off
    by_bin = {"111": pool}
    assert match_one(pr, by_bin).status == MatchStatus.PARTIAL


# ── PARTIAL ──────────────────────────────────────────────────────────────


def test_partial_when_bin_present_but_invoice_not_found():
    pr = _pr("INV-A", "111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-OTHER", "x", date(2024, 1, 15), 1000, 150)]
    by_bin = {"111": pool}

    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.PARTIAL
    assert res.score == Decimal("0.40")
    assert res.flags.reason == "no_invoice_no_match"


# ── NO_MATCH ─────────────────────────────────────────────────────────────


def test_no_match_when_bin_not_in_supplier_pool():
    pr = _pr("INV-A", "111", date(2024, 1, 15), 1000, 150)
    by_bin = {"222": []}

    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.NO_MATCH
    assert res.score == Decimal("0.00")
    assert res.flags.reason == "supplier_bin_not_filed"


def test_no_match_when_pr_has_null_bin():
    pr = _pr("INV-A", None, date(2024, 1, 15), 1000, 150)
    by_bin: dict[str, list[SupplierRow]] = {}
    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.NO_MATCH


# ── Whole register ───────────────────────────────────────────────────────


def test_match_register_returns_one_result_per_purchase_row(
    valid_purchase_register_bytes: bytes,
    valid_supplier_export_bytes: bytes,
):
    """Smoke test: 3 purchase rows in / 3 results out."""
    from app.reconciliation.parser import parse_purchase_register, parse_supplier_export
    pr_rows = parse_purchase_register(valid_purchase_register_bytes)
    sf_rows = parse_supplier_export(valid_supplier_export_bytes)
    results = match_register(pr_rows, sf_rows)
    assert len(results) == 3

    statuses = [r.status for r in results]
    # Row 1 (INV-0023/2024 vs INV-0023/2024 same date/amount, same bin) → EXACT
    # Row 2 (INV-0024/2024 BIN 123456789 — supplier pool has only INV-0023/2024 for that bin) → PARTIAL
    # Row 3 (INV-0001 fuzzy: date off by 1, amount within 0.5%, same bin) → FUZZY
    assert MatchStatus.EXACT in statuses
    assert MatchStatus.FUZZY in statuses
