"""Live tests for GeminiLLMAdapter. Skipped unless GEMINI_API_KEY set
AND -m live flag passed (e.g. pytest -m live)."""
import os

import pytest

from app.ingestion.llm import GeminiLLMAdapter
from app.ingestion.schemas import JobKind

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set",
    ),
]


def test_map_columns_bangla_headers():
    adapter = GeminiLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    out = adapter.map_columns(
        headers=["বিল নং", "BIN", "তারিখ", "মোট", "VAT"],
        sample_rows=[
            ["INV-1", "123456789", "2026-05-10", "1000.00", "150.00"],
        ],
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert out["invoice_no"] == "বিল নং"
    assert out["supplier_bin"] == "BIN"
    assert out["taxable_amount_bdt"] == "মোট"
    assert out["vat_amount_bdt"] == "VAT"
    assert out["invoice_date"] == "তারিখ"


def test_extract_rows_text_mode():
    adapter = GeminiLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    text = (
        "Tax Invoice\n"
        "Mushak 6.3\n"
        "Invoice No: INV-2026-001\n"
        "Date: 15/05/2026\n"
        "Supplier: ACME Ltd, BIN 987654321\n"
        "Taxable: BDT 5,000.00\n"
        "VAT (15%): BDT 750.00\n"
    )
    rows = adapter.extract_rows(
        text=text, lookup_key="ignored-in-real",
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert len(rows) == 1
    assert rows[0]["invoice_no"] == "INV-2026-001"
    assert rows[0]["supplier_bin"] == "987654321"
