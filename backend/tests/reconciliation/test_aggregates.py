"""Tests for aggregate computation across match results."""
from datetime import date
from decimal import Decimal

from app.reconciliation.aggregates import aggregate
from app.reconciliation.schemas import (
    AggregatesDTO, DiscrepancyFlags, MatchResult, MatchStatus,
    PurchaseRow,
)


def _row(status: MatchStatus, vat: float = 100.0) -> MatchResult:
    return MatchResult(
        pr_row=PurchaseRow(
            invoice_no="X", supplier_bin="111", supplier_name=None,
            invoice_date=date(2024, 1, 1),
            taxable_amount_bdt=Decimal("0.00"),
            vat_amount_bdt=Decimal(str(vat)),
        ),
        sf_row=None,
        status=status,
        score=Decimal("0.00"),
        flags=DiscrepancyFlags(),
    )


def test_aggregate_counts_each_status():
    matches = [
        _row(MatchStatus.EXACT,    100),
        _row(MatchStatus.EXACT,    200),
        _row(MatchStatus.FUZZY,    150),
        _row(MatchStatus.PARTIAL,   50),
        _row(MatchStatus.NO_MATCH,  25),
    ]
    agg = aggregate(matches)
    assert isinstance(agg, AggregatesDTO)
    assert agg.total_invoices == 5
    assert agg.matched_exact == 2
    assert agg.matched_fuzzy == 1
    assert agg.partial_match == 1
    assert agg.no_match == 1


def test_aggregate_safe_itc_is_exact_plus_fuzzy_vat():
    matches = [
        _row(MatchStatus.EXACT, 100),
        _row(MatchStatus.FUZZY, 150),
        _row(MatchStatus.PARTIAL, 50),
        _row(MatchStatus.NO_MATCH, 25),
    ]
    agg = aggregate(matches)
    assert agg.safe_itc_bdt == Decimal("250.00")
    assert agg.at_risk_itc_bdt == Decimal("75.00")
    assert agg.total_vat_claimed_bdt == Decimal("325.00")


def test_aggregate_empty():
    agg = aggregate([])
    assert agg.total_invoices == 0
    assert agg.safe_itc_bdt == Decimal("0.00")
    assert agg.at_risk_itc_bdt == Decimal("0.00")
