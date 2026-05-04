"""Tests for reconciliation Pydantic schemas."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.reconciliation.schemas import (
    ReconciliationCreateRequest,
    PurchaseRow,
    SupplierRow,
    MatchStatus,
)


def test_create_request_round_trips():
    payload = {
        "client_id": str(uuid4()),
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "purchase_register_doc_id": str(uuid4()),
        "supplier_data_doc_id": str(uuid4()),
    }
    req = ReconciliationCreateRequest.model_validate(payload)
    assert req.period_start == date(2024, 1, 1)
    assert req.period_end == date(2024, 1, 31)


def test_create_request_rejects_inverted_period():
    with pytest.raises(ValidationError):
        ReconciliationCreateRequest(
            client_id=uuid4(),
            period_start=date(2024, 2, 1),
            period_end=date(2024, 1, 1),
            purchase_register_doc_id=uuid4(),
            supplier_data_doc_id=uuid4(),
        )


def test_purchase_row_normalizes_amounts_to_decimal():
    row = PurchaseRow(
        invoice_no="INV-001",
        supplier_bin="123456789",
        supplier_name="Acme Ltd",
        invoice_date=date(2024, 1, 15),
        taxable_amount_bdt=1000.50,
        vat_amount_bdt=150.075,
    )
    assert isinstance(row.taxable_amount_bdt, Decimal)
    assert row.vat_amount_bdt == Decimal("150.08")  # rounded to 2dp


def test_supplier_row_minimal():
    row = SupplierRow(
        invoice_no="INV-001",
        invoice_date=date(2024, 1, 15),
        taxable_amount_bdt=Decimal("1000.50"),
        vat_amount_bdt=Decimal("150.08"),
        buyer_bin="987654321",
    )
    assert row.invoice_no == "INV-001"


def test_match_status_values():
    assert MatchStatus.EXACT.value == "exact"
    assert MatchStatus.FUZZY.value == "fuzzy"
    assert MatchStatus.PARTIAL.value == "partial"
    assert MatchStatus.NO_MATCH.value == "no_match"
