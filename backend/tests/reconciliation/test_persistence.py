"""Tests for the persistence layer."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.reconciliation.persistence import persist_reconciliation
from app.reconciliation.schemas import (
    AggregatesDTO, DiscrepancyFlags, MatchResult, MatchStatus, PurchaseRow,
)


def _match() -> MatchResult:
    return MatchResult(
        pr_row=PurchaseRow(
            invoice_no="INV-1", supplier_bin="111", supplier_name="X",
            invoice_date=date(2024, 1, 1),
            taxable_amount_bdt=Decimal("100"),
            vat_amount_bdt=Decimal("15"),
        ),
        sf_row=None,
        status=MatchStatus.NO_MATCH,
        score=Decimal("0.00"),
        flags=DiscrepancyFlags(reason="supplier_bin_not_filed"),
    )


@pytest.mark.asyncio
async def test_persist_reconciliation_calls_rpc(monkeypatch):
    new_id = uuid4()
    fake = MagicMock()
    fake.rpc.return_value.execute.return_value.data = str(new_id)

    monkeypatch.setattr(
        "app.reconciliation.persistence.get_supabase_admin",
        lambda: fake,
    )

    result = await persist_reconciliation(
        tenant_id=uuid4(),
        client_id=uuid4(),
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        run_by=uuid4(),
        pr_doc_id=uuid4(),
        sf_doc_id=uuid4(),
        aggregates=AggregatesDTO(
            total_invoices=1, matched_exact=0, matched_fuzzy=0,
            partial_match=0, no_match=1,
            total_vat_claimed_bdt=Decimal("15"),
            safe_itc_bdt=Decimal("0"),
            at_risk_itc_bdt=Decimal("15"),
        ),
        matches=[_match()],
    )

    assert str(result) == str(new_id)
    assert fake.rpc.call_args.args[0] == "persist_reconciliation"
    payload = fake.rpc.call_args.args[1]
    assert payload["p_total_invoices"] == 1
    assert payload["p_no_match"] == 1
    assert isinstance(payload["p_line_items"], list)
    assert payload["p_line_items"][0]["pr_invoice_no"] == "INV-1"
    assert payload["p_line_items"][0]["match_status"] == "no_match"
