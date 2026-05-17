"""Tests for `override_line_item` — the service function that orchestrates
a CA override write plus aggregate recompute.

All Supabase calls are mocked; this exercises the orchestration logic
(404 checks, update + re-fetch + re-aggregate ordering, return shape).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.reconciliation import service as svc
from app.reconciliation.schemas import CAOverride


@pytest.fixture
def recon_id() -> UUID:
    return uuid4()


@pytest.fixture
def line_item_id() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def _mock_storage(monkeypatch, recon_id, line_item_id, tenant_id):
    """Wire up in-memory stand-ins for the four persistence calls the
    service makes. Returns a dict of captured kwargs so tests can assert."""
    state = {
        "header_exists": True,
        "line_item_exists": True,
        "rows": [
            {"match_status": "exact",    "pr_vat_amount_bdt": "100.00", "ca_override": None},
            {"match_status": "no_match", "pr_vat_amount_bdt": "200.00", "ca_override": None},
        ],
        "captured": {},
    }

    async def fake_fetch_header(rid, *, tenant_id):
        return {"id": str(rid), "tenant_id": str(tenant_id)} if state["header_exists"] else None

    async def fake_fetch_line_item(lid, *, reconciliation_id, tenant_id):
        return {"id": str(lid)} if state["line_item_exists"] else None

    async def fake_update_override(lid, *, reconciliation_id, tenant_id, ca_override, ca_notes):
        state["captured"]["update_override"] = {
            "lid": lid, "ca_override": ca_override, "ca_notes": ca_notes,
        }
        # Simulate the row's mutation in the in-memory state so the
        # subsequent re-fetch reflects the change.
        if state["rows"]:
            state["rows"][-1]["ca_override"] = ca_override
        return {"id": str(lid), "ca_override": ca_override, "ca_notes": ca_notes}

    async def fake_fetch_line_items(rid, *, tenant_id):
        return list(state["rows"])

    async def fake_update_aggregates(rid, *, tenant_id, aggregates):
        state["captured"]["aggregates"] = aggregates

    monkeypatch.setattr(svc, "fetch_reconciliation_header", fake_fetch_header)
    monkeypatch.setattr(svc, "fetch_line_item", fake_fetch_line_item)
    monkeypatch.setattr(svc, "update_line_item_override", fake_update_override)
    monkeypatch.setattr(svc, "fetch_line_items", fake_fetch_line_items)
    monkeypatch.setattr(svc, "update_reconciliation_aggregates", fake_update_aggregates)

    return state


@pytest.mark.asyncio
async def test_override_returns_recomputed_aggregates(
    _mock_storage, recon_id, line_item_id, tenant_id,
):
    """Happy path: approving the no_match row moves its 200 BDT into Safe."""
    result = await svc.override_line_item(
        reconciliation_id=recon_id,
        line_item_id=line_item_id,
        tenant_id=tenant_id,
        ca_override=CAOverride.APPROVED,
        ca_notes="Vendor confirmed by phone",
    )

    assert result.line_item_id == line_item_id
    assert result.ca_override == CAOverride.APPROVED
    assert result.ca_notes == "Vendor confirmed by phone"
    # 100 (exact) + 200 (now-approved no_match) = 300 safe; 0 at-risk.
    assert result.aggregates.safe_itc_bdt == Decimal("300.00")
    assert result.aggregates.at_risk_itc_bdt == Decimal("0.00")
    assert result.aggregates.total_vat_claimed_bdt == Decimal("300.00")
    # And the aggregates write actually happened.
    assert _mock_storage["captured"]["aggregates"].safe_itc_bdt == Decimal("300.00")


@pytest.mark.asyncio
async def test_clearing_override_passes_null(
    _mock_storage, recon_id, line_item_id, tenant_id,
):
    """Passing `ca_override=None` clears the override on the row."""
    await svc.override_line_item(
        reconciliation_id=recon_id,
        line_item_id=line_item_id,
        tenant_id=tenant_id,
        ca_override=None,
        ca_notes=None,
    )
    assert _mock_storage["captured"]["update_override"]["ca_override"] is None


@pytest.mark.asyncio
async def test_missing_reconciliation_raises(
    _mock_storage, recon_id, line_item_id, tenant_id,
):
    _mock_storage["header_exists"] = False
    with pytest.raises(svc.ReconciliationNotFound):
        await svc.override_line_item(
            reconciliation_id=recon_id,
            line_item_id=line_item_id,
            tenant_id=tenant_id,
            ca_override=CAOverride.APPROVED,
            ca_notes=None,
        )


@pytest.mark.asyncio
async def test_missing_line_item_raises(
    _mock_storage, recon_id, line_item_id, tenant_id,
):
    _mock_storage["line_item_exists"] = False
    with pytest.raises(svc.LineItemNotFound):
        await svc.override_line_item(
            reconciliation_id=recon_id,
            line_item_id=line_item_id,
            tenant_id=tenant_id,
            ca_override=CAOverride.DISPUTED,
            ca_notes=None,
        )


@pytest.mark.asyncio
async def test_ignore_excludes_from_totals(
    _mock_storage, recon_id, line_item_id, tenant_id,
):
    """An ignored row's VAT drops out of both safe and at_risk."""
    # Override the in-memory row directly to ignored before service runs.
    _mock_storage["rows"][-1]["ca_override"] = None  # will be re-set to ignore by service
    result = await svc.override_line_item(
        reconciliation_id=recon_id,
        line_item_id=line_item_id,
        tenant_id=tenant_id,
        ca_override=CAOverride.IGNORE,
        ca_notes=None,
    )
    # Only the exact row contributes: 100 safe, 0 at-risk, total 100.
    assert result.aggregates.safe_itc_bdt == Decimal("100.00")
    assert result.aggregates.at_risk_itc_bdt == Decimal("0.00")
    assert result.aggregates.total_vat_claimed_bdt == Decimal("100.00")
