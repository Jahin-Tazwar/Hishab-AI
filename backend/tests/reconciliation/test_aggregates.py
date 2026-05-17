"""Tests for aggregate computation across match results."""
from datetime import date
from decimal import Decimal

from app.reconciliation.aggregates import aggregate, aggregate_from_db_rows
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


# ── aggregate_from_db_rows: override-aware recompute ─────────────────────


def _db_row(
    *, match_status: str, vat: str, ca_override: str | None = None,
) -> dict:
    """Minimal recon_line_items row shape for aggregator tests."""
    return {
        "match_status": match_status,
        "pr_vat_amount_bdt": vat,
        "ca_override": ca_override,
    }


def test_aggregate_from_db_rows_matches_engine_when_no_overrides():
    """Without any overrides, the recompute should yield the same buckets
    as the original `aggregate(matches)` would."""
    rows = [
        _db_row(match_status="exact",    vat="100.00"),
        _db_row(match_status="fuzzy",    vat="150.00"),
        _db_row(match_status="partial",  vat="50.00"),
        _db_row(match_status="no_match", vat="25.00"),
    ]
    agg = aggregate_from_db_rows(rows)
    assert agg.total_invoices == 4
    assert agg.matched_exact == 1
    assert agg.matched_fuzzy == 1
    assert agg.partial_match == 1
    assert agg.no_match == 1
    assert agg.safe_itc_bdt == Decimal("250.00")
    assert agg.at_risk_itc_bdt == Decimal("75.00")
    assert agg.total_vat_claimed_bdt == Decimal("325.00")


def test_aggregate_from_db_rows_approved_moves_to_safe():
    """A CA approving a no_match row should shift its VAT into Safe ITC,
    even though the engine flagged it as no_match."""
    rows = [
        _db_row(match_status="no_match", vat="500.00", ca_override="approved"),
        _db_row(match_status="partial",  vat="100.00"),
    ]
    agg = aggregate_from_db_rows(rows)
    assert agg.safe_itc_bdt == Decimal("500.00")
    assert agg.at_risk_itc_bdt == Decimal("100.00")
    # match_status counts are unchanged — the engine still classified it.
    assert agg.no_match == 1
    assert agg.partial_match == 1


def test_aggregate_from_db_rows_disputed_moves_to_at_risk():
    """Conversely, a CA disputing an exact match should pull it into At-risk."""
    rows = [
        _db_row(match_status="exact", vat="200.00", ca_override="disputed"),
        _db_row(match_status="exact", vat="300.00"),
    ]
    agg = aggregate_from_db_rows(rows)
    assert agg.safe_itc_bdt == Decimal("300.00")
    assert agg.at_risk_itc_bdt == Decimal("200.00")
    assert agg.matched_exact == 2  # both still counted as exact matches


def test_aggregate_from_db_rows_ignore_excludes_from_totals():
    """Ignored rows drop out of both safe and at_risk, so
    `total_vat_claimed_bdt = safe + at_risk` remains true."""
    rows = [
        _db_row(match_status="exact",    vat="100.00"),
        _db_row(match_status="no_match", vat="999.00", ca_override="ignore"),
    ]
    agg = aggregate_from_db_rows(rows)
    assert agg.safe_itc_bdt == Decimal("100.00")
    assert agg.at_risk_itc_bdt == Decimal("0.00")
    assert agg.total_vat_claimed_bdt == Decimal("100.00")
    assert agg.no_match == 1


def test_aggregate_from_db_rows_empty():
    agg = aggregate_from_db_rows([])
    assert agg.total_invoices == 0
    assert agg.safe_itc_bdt == Decimal("0.00")
    assert agg.at_risk_itc_bdt == Decimal("0.00")
    assert agg.total_vat_claimed_bdt == Decimal("0.00")


def test_aggregate_from_db_rows_handles_missing_vat_field():
    """Defensive: a row with `pr_vat_amount_bdt = None` shouldn't crash —
    treat it as zero."""
    rows = [_db_row(match_status="exact", vat="100.00")]
    rows[0]["pr_vat_amount_bdt"] = None
    agg = aggregate_from_db_rows(rows)
    assert agg.total_invoices == 1
    assert agg.safe_itc_bdt == Decimal("0.00")
