"""Recipe tests — monkeypatch the Supabase admin client so we can exercise
the grouping / action-tagging / sorting logic without a live DB.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.working_papers.recipes.at_risk_itc import AtRiskItcScheduleRecipe


TENANT_ID = uuid4()
RECON_ID = uuid4()
CLIENT_ID = uuid4()


def _recon_row() -> dict:
    return {
        "id": str(RECON_ID),
        "client_id": str(CLIENT_ID),
        "tenant_id": str(TENANT_ID),
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "total_vat_claimed_bdt": "50000.00",
        "safe_itc_bdt": "40000.00",
        "at_risk_itc_bdt": "10000.00",
    }


def _client_row() -> dict:
    return {"id": str(CLIENT_ID), "name": "Demo Client", "bin": "987654321"}


def _line(
    *, supplier="ACME Ltd", bin_="123456789",
    invoice="INV-1", date_="2026-04-05",
    vat="150.00", taxable="1000.00",
    match_status="no_match", match_score=None,
    ca_override=None, ca_notes=None,
) -> dict:
    return {
        "id": str(uuid4()),
        "pr_invoice_no": invoice,
        "pr_supplier_bin": bin_,
        "pr_supplier_name": supplier,
        "pr_invoice_date": date_,
        "pr_taxable_amount_bdt": taxable,
        "pr_vat_amount_bdt": vat,
        "match_status": match_status,
        "match_score": match_score,
        "ca_override": ca_override,
        "ca_notes": ca_notes,
    }


class _FakeSupabaseTable:
    def __init__(self, table_name: str, store: dict):
        self.table = table_name
        self.store = store
        self._filters: dict = {}
        self._single = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        data = self.store.get(self.table)
        if callable(data):
            data = data(self._filters)
        if self._single:
            return SimpleNamespace(data=data)
        return SimpleNamespace(data=data)


class _FakeSupabase:
    def __init__(self, store: dict):
        self.store = store

    def table(self, name: str):
        return _FakeSupabaseTable(name, self.store)


def _patch_sb(monkeypatch, lines: list[dict]):
    store = {
        "vat_reconciliations": _recon_row(),
        "clients": _client_row(),
        "recon_line_items": lines,
    }
    fake = _FakeSupabase(store)
    monkeypatch.setattr(
        "app.working_papers.recipes.at_risk_itc.get_supabase_admin",
        lambda: fake,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def test_filters_exact_matches_without_override(monkeypatch, loop):
    lines = [
        _line(invoice="EX1", match_status="exact", vat="100"),  # filtered out
        _line(invoice="NM1", match_status="no_match", vat="200"),
    ]
    _patch_sb(monkeypatch, lines)
    payload = loop.run_until_complete(
        AtRiskItcScheduleRecipe().compose(
            tenant_id=TENANT_ID, reconciliation_id=RECON_ID,
        )
    )
    assert payload["summary"]["total_lines"] == 2
    assert payload["summary"]["at_risk_line_count"] == 1
    # Only one supplier group (the at-risk one)
    assert len(payload["supplier_groups"]) == 1
    assert payload["supplier_groups"][0]["lines"][0]["invoice_no"] == "NM1"


def test_exact_with_disputed_override_is_included(monkeypatch, loop):
    lines = [
        _line(invoice="EX1", match_status="exact", vat="100", ca_override="disputed"),
        _line(invoice="EX2", match_status="exact", vat="100"),  # filtered
    ]
    _patch_sb(monkeypatch, lines)
    payload = loop.run_until_complete(
        AtRiskItcScheduleRecipe().compose(
            tenant_id=TENANT_ID, reconciliation_id=RECON_ID,
        )
    )
    assert payload["summary"]["at_risk_line_count"] == 1
    assert payload["supplier_groups"][0]["lines"][0]["recommended_action"] == "partner_review"


def test_recommended_action_mapping(monkeypatch, loop):
    lines = [
        _line(invoice="A", bin_="111", supplier="A Co", match_status="no_match", vat="100"),
        _line(invoice="B", bin_="222", supplier="B Co", match_status="partial", vat="100"),
        _line(invoice="C", bin_="333", supplier="C Co", match_status="fuzzy", vat="100"),
        _line(invoice="D", bin_="444", supplier="D Co", match_status="fuzzy", vat="100",
              ca_override="approved"),
        _line(invoice="E", bin_="555", supplier="E Co", match_status="fuzzy", vat="100",
              ca_override="ignore"),
    ]
    _patch_sb(monkeypatch, lines)
    payload = loop.run_until_complete(
        AtRiskItcScheduleRecipe().compose(
            tenant_id=TENANT_ID, reconciliation_id=RECON_ID,
        )
    )
    by_invoice = {
        line["invoice_no"]: line["recommended_action"]
        for grp in payload["supplier_groups"]
        for line in grp["lines"]
    }
    assert by_invoice["A"] == "chase_supplier"
    assert by_invoice["B"] == "partner_review"
    assert by_invoice["C"] == "partner_review"
    assert by_invoice["D"] == "approved_by_ca"
    assert by_invoice["E"] == "no_action"


def test_grouping_and_supplier_totals(monkeypatch, loop):
    lines = [
        _line(invoice="A1", supplier="Alpha", bin_="111", vat="100", match_status="no_match"),
        _line(invoice="A2", supplier="Alpha", bin_="111", vat="200", match_status="partial"),
        _line(invoice="B1", supplier="Bravo", bin_="222", vat="500", match_status="no_match"),
    ]
    _patch_sb(monkeypatch, lines)
    payload = loop.run_until_complete(
        AtRiskItcScheduleRecipe().compose(
            tenant_id=TENANT_ID, reconciliation_id=RECON_ID,
        )
    )
    assert len(payload["supplier_groups"]) == 2
    # Sorted by descending at-risk total: Bravo (500) before Alpha (300)
    from decimal import Decimal as _D
    assert payload["supplier_groups"][0]["supplier_name"] == "Bravo"
    assert _D(payload["supplier_groups"][0]["total_vat_at_risk_bdt"]) == _D("500")
    assert payload["supplier_groups"][1]["supplier_name"] == "Alpha"
    assert _D(payload["supplier_groups"][1]["total_vat_at_risk_bdt"]) == _D("300")
    assert payload["supplier_groups"][1]["line_count"] == 2


def test_summary_aggregates_use_recon_header(monkeypatch, loop):
    lines = [
        _line(invoice="A", match_status="no_match", vat="50"),
        _line(invoice="B", match_status="exact", vat="50"),
    ]
    _patch_sb(monkeypatch, lines)
    payload = loop.run_until_complete(
        AtRiskItcScheduleRecipe().compose(
            tenant_id=TENANT_ID, reconciliation_id=RECON_ID,
        )
    )
    assert payload["summary"]["total_vat_claimed_bdt"] == "50000.00"
    assert payload["summary"]["safe_itc_bdt"] == "40000.00"
    assert payload["summary"]["at_risk_itc_bdt"] == "10000.00"
    assert payload["summary"]["total_lines"] == 2
    assert payload["summary"]["at_risk_line_count"] == 1
    assert payload["summary"]["supplier_count_at_risk"] == 1
    assert payload["kind"] == "at_risk_itc_schedule"
    assert payload["recipe_version"] == "v1"
