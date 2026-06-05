"""Recipe tests — monkeypatch the Supabase admin client so we can exercise
the grouping / action-tagging / sorting logic without a live DB.

Key invariant under test (F1): the recipe's notion of "at-risk" is identical
to the reconciliation engine's `effective_bucket`, so the sum of per-supplier
`total_vat_at_risk_bdt` always ties exactly to the recon header's
`at_risk_itc_bdt`. fuzzy=safe, approved=safe, ignore=excluded all drop out.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.reconciliation.aggregates import aggregate_from_db_rows
from app.working_papers.recipes.at_risk_itc import AtRiskItcScheduleRecipe


TENANT_ID = uuid4()
RECON_ID = uuid4()
CLIENT_ID = uuid4()


def _recon_row(*, at_risk="10000.00", safe="40000.00", claimed="50000.00") -> dict:
    return {
        "id": str(RECON_ID),
        "client_id": str(CLIENT_ID),
        "tenant_id": str(TENANT_ID),
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "total_vat_claimed_bdt": claimed,
        "safe_itc_bdt": safe,
        "at_risk_itc_bdt": at_risk,
    }


def _client_row() -> dict:
    return {"id": str(CLIENT_ID), "name": "Demo Client", "bin": "987654321"}


def _line(
    *, supplier="ACME Ltd", bin_="123456789",
    invoice="INV-1", date_="2026-04-05",
    vat="150.00", taxable="1000.00",
    match_status="no_match", match_score=None,
    ca_override=None, ca_notes=None,
    sf_vat=None, sf_taxable=None, reason=None, date_off=None,
) -> dict:
    return {
        "id": str(uuid4()),
        "pr_invoice_no": invoice,
        "pr_supplier_bin": bin_,
        "pr_supplier_name": supplier,
        "pr_invoice_date": date_,
        "pr_taxable_amount_bdt": taxable,
        "pr_vat_amount_bdt": vat,
        "sf_vat_amount_bdt": sf_vat,
        "sf_taxable_amount_bdt": sf_taxable,
        "match_status": match_status,
        "match_score": match_score,
        "discrepancy_flags": {"reason": reason, "date_off_by_days": date_off},
        "ca_override": ca_override,
        "ca_notes": ca_notes,
    }


class _FakeSupabaseTable:
    def __init__(self, table_name: str, store: dict):
        self.table = table_name
        self.store = store
        self._filters: dict = {}
        self._single = False
        self._range: tuple[int, int] | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        data = self.store.get(self.table)
        if callable(data):
            data = data(self._filters)
        if isinstance(data, list) and self._range is not None:
            start, end = self._range
            data = data[start : end + 1]
        return SimpleNamespace(data=data)


class _FakeSupabase:
    def __init__(self, store: dict):
        self.store = store

    def table(self, name: str):
        return _FakeSupabaseTable(name, self.store)


def _patch_sb(monkeypatch, lines: list[dict], *, recon: dict | None = None):
    store = {
        "vat_reconciliations": recon or _recon_row(),
        "clients": _client_row(),
        "recon_line_items": lines,
    }
    fake = _FakeSupabase(store)
    monkeypatch.setattr(
        "app.working_papers.recipes.at_risk_itc.get_supabase_admin",
        lambda: fake,
    )


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def _compose(loop, lines, *, recon=None, monkeypatch=None):
    _patch_sb(monkeypatch, lines, recon=recon)
    return loop.run_until_complete(
        AtRiskItcScheduleRecipe().compose(
            tenant_id=TENANT_ID, reconciliation_id=RECON_ID,
        )
    )


# ── F1: the schedule ties out to the headline ────────────────────────────


def test_at_risk_sum_ties_to_headline_kpi(monkeypatch, loop):
    """Σ per-supplier at-risk VAT == recon header at_risk_itc_bdt, across a
    fixture that mixes every status that the OLD recipe mis-bucketed."""
    lines = [
        _line(invoice="EXACT", match_status="exact", vat="1000"),            # safe
        _line(invoice="FUZZY", match_status="fuzzy", vat="2000"),            # safe (engine!)
        _line(invoice="APPR",  match_status="partial", vat="3000",
              ca_override="approved"),                                       # safe (override)
        _line(invoice="IGN",   match_status="no_match", vat="4000",
              ca_override="ignore"),                                         # excluded
        _line(invoice="DISP",  match_status="exact", vat="500",
              ca_override="disputed"),                                       # at_risk
        _line(invoice="NM",    match_status="no_match", vat="700"),          # at_risk
        _line(invoice="PART",  match_status="partial", vat="800"),          # at_risk
    ]
    # Headline computed exactly as the recon engine does.
    agg = aggregate_from_db_rows(lines)
    assert agg.at_risk_itc_bdt == Decimal("2000.00")  # 500 + 700 + 800

    recon = _recon_row(
        at_risk=str(agg.at_risk_itc_bdt),
        safe=str(agg.safe_itc_bdt),
        claimed=str(agg.total_vat_claimed_bdt),
    )
    payload = _compose(loop, lines, recon=recon, monkeypatch=monkeypatch)

    supplier_sum = sum(
        Decimal(g["total_vat_at_risk_bdt"]) for g in payload["supplier_groups"]
    )
    assert supplier_sum == agg.at_risk_itc_bdt
    assert Decimal(payload["summary"]["at_risk_itc_bdt"]) == agg.at_risk_itc_bdt

    # Only the three genuinely at-risk invoices appear.
    invoices = {
        l["invoice_no"] for g in payload["supplier_groups"] for l in g["lines"]
    }
    assert invoices == {"DISP", "NM", "PART"}
    assert payload["summary"]["at_risk_line_count"] == 3
    assert payload["summary"]["total_lines"] == 7


# ── F2: no silent truncation past the 1000-row PostgREST cap ──────────────


def test_paginates_beyond_1000_rows(monkeypatch, loop):
    lines = [
        _line(invoice=f"NM{i}", bin_="111", supplier="Big Co",
              match_status="no_match", vat="1.00")
        for i in range(1500)
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    assert payload["summary"]["total_lines"] == 1500
    assert payload["summary"]["at_risk_line_count"] == 1500
    total_lines_emitted = sum(
        len(g["lines"]) for g in payload["supplier_groups"]
    )
    assert total_lines_emitted == 1500
    assert Decimal(payload["supplier_groups"][0]["total_vat_at_risk_bdt"]) == Decimal("1500.00")


# ── F3: supplier-side evidence + variance are carried into each line ──────


def test_lines_carry_supplier_side_figures_and_variance(monkeypatch, loop):
    lines = [
        _line(
            invoice="P1", match_status="partial", vat="1000.00",
            taxable="6666.67", sf_vat="900.00", sf_taxable="6000.00",
            reason="vat amount differs", date_off=2, match_score="0.80",
        ),
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    line = payload["supplier_groups"][0]["lines"][0]
    assert line["sf_vat_amount_bdt"] == "900.00"
    assert line["sf_taxable_amount_bdt"] == "6000.00"
    assert Decimal(line["vat_variance_bdt"]) == Decimal("100.00")  # 1000 - 900
    assert line["discrepancy_reason"] == "vat amount differs"
    assert line["date_off_by_days"] == 2


def test_no_match_line_variance_is_full_claim(monkeypatch, loop):
    """When the supplier never reported (no sf figures), the entire claimed
    VAT is the variance / exposure."""
    lines = [
        _line(invoice="NM", match_status="no_match", vat="500.00", sf_vat=None),
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    line = payload["supplier_groups"][0]["lines"][0]
    assert line["sf_vat_amount_bdt"] is None
    assert Decimal(line["vat_variance_bdt"]) == Decimal("500.00")


# ── Recommended-action taxonomy (every enum value reachable) ──────────────


def test_recommended_action_mapping(monkeypatch, loop):
    lines = [
        _line(invoice="A", bin_="111", supplier="A Co", match_status="no_match", vat="100"),
        _line(invoice="B", bin_="222", supplier="B Co", match_status="partial", vat="100"),
        _line(invoice="D", bin_="444", supplier="D Co", match_status="no_match", vat="100",
              ca_override="disputed"),
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    by_invoice = {
        line["invoice_no"]: line["recommended_action"]
        for grp in payload["supplier_groups"]
        for line in grp["lines"]
    }
    assert by_invoice["A"] == "chase_supplier"   # supplier never filed
    assert by_invoice["B"] == "partner_review"   # amounts differ → judgment
    assert by_invoice["D"] == "reverse_claim"    # CA disputed → reverse the ITC


def test_safe_lines_are_excluded(monkeypatch, loop):
    """fuzzy, approved-non-exact, and ignore never appear in the schedule."""
    lines = [
        _line(invoice="FUZ", match_status="fuzzy", vat="100"),
        _line(invoice="APP", match_status="partial", vat="100", ca_override="approved"),
        _line(invoice="IGN", match_status="no_match", vat="100", ca_override="ignore"),
        _line(invoice="NM",  match_status="no_match", vat="100"),
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    invoices = {
        l["invoice_no"] for g in payload["supplier_groups"] for l in g["lines"]
    }
    assert invoices == {"NM"}


# ── Grouping / sorting (unchanged behavior, re-verified) ──────────────────


def test_grouping_and_supplier_totals(monkeypatch, loop):
    lines = [
        _line(invoice="A1", supplier="Alpha", bin_="111", vat="100", match_status="no_match"),
        _line(invoice="A2", supplier="Alpha", bin_="111", vat="200", match_status="partial"),
        _line(invoice="B1", supplier="Bravo", bin_="222", vat="500", match_status="no_match"),
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    assert len(payload["supplier_groups"]) == 2
    # Sorted by descending at-risk total: Bravo (500) before Alpha (300)
    assert payload["supplier_groups"][0]["supplier_name"] == "Bravo"
    assert Decimal(payload["supplier_groups"][0]["total_vat_at_risk_bdt"]) == Decimal("500")
    assert payload["supplier_groups"][1]["supplier_name"] == "Alpha"
    assert Decimal(payload["supplier_groups"][1]["total_vat_at_risk_bdt"]) == Decimal("300")
    assert payload["supplier_groups"][1]["line_count"] == 2


def test_summary_aggregates_use_recon_header(monkeypatch, loop):
    lines = [
        _line(invoice="A", match_status="no_match", vat="50"),
        _line(invoice="B", match_status="exact", vat="50"),
    ]
    payload = _compose(loop, lines, monkeypatch=monkeypatch)
    assert payload["summary"]["total_vat_claimed_bdt"] == "50000.00"
    assert payload["summary"]["safe_itc_bdt"] == "40000.00"
    assert payload["summary"]["at_risk_itc_bdt"] == "10000.00"
    assert payload["summary"]["total_lines"] == 2
    assert payload["summary"]["at_risk_line_count"] == 1
    assert payload["summary"]["supplier_count_at_risk"] == 1
    assert payload["kind"] == "at_risk_itc_schedule"
    assert payload["recipe_version"] == "v1"
