"""Round-trip test: confirmed rows → canonical XLSX bytes → existing parser
must produce identical PurchaseRow output. Pure-logic, no DB."""
from datetime import date
from decimal import Decimal

from app.ingestion.handoff import rows_to_canonical_xlsx
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.reconciliation.parser import parse_purchase_register, parse_supplier_export


def _row(**over):
    base = dict(
        invoice_no="INV-1",
        supplier_bin="123456789",
        supplier_name="ACME",
        invoice_date=date(2026, 5, 10),
        taxable_amount_bdt=Decimal("1000.00"),
        vat_amount_bdt=Decimal("150.00"),
    )
    base.update(over)
    return ExtractedRowData(**base)


def test_purchase_roundtrip_through_existing_parser():
    rows = [_row(), _row(invoice_no="INV-2", supplier_bin="987654321")]
    xlsx = rows_to_canonical_xlsx(rows, kind=JobKind.PURCHASE_REGISTER)
    parsed = parse_purchase_register(xlsx)
    assert len(parsed) == 2
    assert parsed[0].invoice_no == "INV-1"
    assert parsed[0].supplier_bin == "123456789"
    assert parsed[0].taxable_amount_bdt == Decimal("1000.00")


def test_supplier_export_roundtrip():
    rows = [
        ExtractedRowData(
            invoice_no="S-1", buyer_bin="999000111",
            invoice_date=date(2026, 5, 11),
            taxable_amount_bdt=Decimal("500.00"),
            vat_amount_bdt=Decimal("75.00"),
        )
    ]
    xlsx = rows_to_canonical_xlsx(rows, kind=JobKind.SUPPLIER_EXPORT)
    parsed = parse_supplier_export(xlsx)
    assert len(parsed) == 1
    assert parsed[0].buyer_bin == "999000111"
