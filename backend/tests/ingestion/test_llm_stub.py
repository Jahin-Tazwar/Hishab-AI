"""Tests for the StubLLMAdapter — the deterministic test double used in CI."""
from datetime import date

import pytest

from app.ingestion.llm import (
    StubLLMAdapter,
    LLMUnavailableError,
    column_signature,
)
from app.ingestion.schemas import JobKind


def test_column_signature_is_order_independent():
    a = column_signature(["Invoice No", "Supplier BIN", "Date"])
    b = column_signature(["date", "INVOICE NO", "supplier bin"])
    assert a == b


def test_stub_returns_canned_column_mapping():
    sig = column_signature(["বিল নং", "BIN", "তারিখ", "মোট", "VAT"])
    stub = StubLLMAdapter(
        column_mappings={
            sig: {
                "invoice_no": "বিল নং",
                "supplier_bin": "BIN",
                "supplier_name": None,
                "invoice_date": "তারিখ",
                "taxable_amount_bdt": "মোট",
                "vat_amount_bdt": "VAT",
            }
        }
    )
    out = stub.map_columns(
        headers=["বিল নং", "BIN", "তারিখ", "মোট", "VAT"],
        sample_rows=[],
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert out["invoice_no"] == "বিল নং"
    assert out["supplier_name"] is None


def test_stub_raises_when_unmocked_input():
    stub = StubLLMAdapter(column_mappings={})
    with pytest.raises(LLMUnavailableError):
        stub.map_columns(
            headers=["X"], sample_rows=[],
            kind=JobKind.PURCHASE_REGISTER,
        )


def test_stub_extract_rows_returns_canned():
    stub = StubLLMAdapter(
        extractions={
            "fake-payload-key": [
                {
                    "invoice_no": "INV-1",
                    "supplier_bin": "123456789",
                    "supplier_name": "ACME",
                    "invoice_date": "2026-05-10",
                    "taxable_amount_bdt": "1000.00",
                    "vat_amount_bdt": "150.00",
                }
            ]
        }
    )
    rows = stub.extract_rows(
        text="ignored", lookup_key="fake-payload-key",
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert len(rows) == 1
    assert rows[0]["invoice_no"] == "INV-1"
