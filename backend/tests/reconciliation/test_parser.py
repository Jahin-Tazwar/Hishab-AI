"""Tests for XLSX parsers."""
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import InvalidXlsxFormatError
from app.reconciliation.parser import (
    parse_purchase_register,
    parse_supplier_export,
)
from app.reconciliation.schemas import PurchaseRow, SupplierRow


def test_parse_purchase_register_happy_path(valid_purchase_register_bytes: bytes):
    rows = parse_purchase_register(valid_purchase_register_bytes)

    assert len(rows) == 3
    assert isinstance(rows[0], PurchaseRow)
    assert rows[0].invoice_no == "INV-0023/2024"
    assert rows[0].supplier_bin == "123456789"
    assert rows[0].invoice_date == date(2024, 1, 15)
    assert rows[0].taxable_amount_bdt == Decimal("1000.00")
    assert rows[0].vat_amount_bdt == Decimal("150.00")


def test_parse_purchase_register_is_case_insensitive(valid_purchase_register_bytes: bytes):
    """The parser must accept 'invoice no' as well as 'Invoice No'."""
    import io, openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "invoice no", "supplier bin", "supplier name",
        "invoice date", "taxable amount (bdt)", "vat amount (bdt)",
    ])
    ws.append(["INV-1", "123456789", "X", date(2024, 1, 1), 100, 15])
    buf = io.BytesIO()
    wb.save(buf)

    rows = parse_purchase_register(buf.getvalue())
    assert len(rows) == 1
    assert rows[0].invoice_no == "INV-1"


def test_parse_purchase_register_missing_column_raises(
    purchase_register_missing_column_bytes: bytes,
):
    with pytest.raises(InvalidXlsxFormatError) as ei:
        parse_purchase_register(purchase_register_missing_column_bytes)
    assert "Supplier BIN" in ei.value.message
    assert ei.value.details["file_label"] == "purchase register"


def test_parse_purchase_register_empty_returns_empty_list(empty_xlsx_bytes: bytes):
    """An empty file (only header row exists but no required headers) raises."""
    with pytest.raises(InvalidXlsxFormatError):
        parse_purchase_register(empty_xlsx_bytes)


def test_parse_supplier_export_happy_path(valid_supplier_export_bytes: bytes):
    rows = parse_supplier_export(valid_supplier_export_bytes)
    assert len(rows) == 3
    assert isinstance(rows[0], SupplierRow)
    assert rows[0].invoice_no == "INV-0023/2024"
    assert rows[0].buyer_bin == "123456789"  # matches purchase row 1's supplier_bin
