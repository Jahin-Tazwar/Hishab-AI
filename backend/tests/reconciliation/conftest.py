"""Shared fixtures for reconciliation tests."""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import openpyxl
import pytest


def _make_xlsx(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def valid_purchase_register_bytes() -> bytes:
    headers = [
        "Invoice No", "Supplier BIN", "Supplier Name",
        "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
    ]
    rows = [
        ["INV-0023/2024", "123456789", "Acme Ltd", date(2024, 1, 15), 1000.00, 150.00],
        ["INV-0024/2024", "123456789", "Acme Ltd", date(2024, 1, 20),  500.00,  75.00],
        ["INV-0001",      "987654321", "Beta Co",  date(2024, 1, 10), 2500.50, 375.08],
    ]
    return _make_xlsx(headers, rows)


@pytest.fixture
def valid_supplier_export_bytes() -> bytes:
    headers = [
        "Invoice No", "Invoice Date",
        "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN",
    ]
    rows = [
        # Exact match for purchase row 1 — same supplier_bin "123456789"
        ["INV-0023/2024", date(2024, 1, 15), 1000.00, 150.00, "123456789"],
        # Fuzzy match for purchase row 3: date off by 1 day, amount within 0.5%
        ["INV-0001",      date(2024, 1, 11), 2500.00, 375.00, "987654321"],
        # Unrelated row (different BIN)
        ["INV-9999",      date(2024, 1, 5),    50.00,   7.50, "555666777"],
    ]
    return _make_xlsx(headers, rows)


@pytest.fixture
def purchase_register_missing_column_bytes() -> bytes:
    # Drop "Supplier BIN"
    headers = [
        "Invoice No", "Supplier Name",
        "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
    ]
    return _make_xlsx(headers, [["INV-1", "X", date(2024, 1, 1), 100, 15]])


@pytest.fixture
def empty_xlsx_bytes() -> bytes:
    return _make_xlsx(["irrelevant"], [])
