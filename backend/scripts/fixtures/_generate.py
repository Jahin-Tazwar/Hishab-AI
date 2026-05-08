"""
Generates the two demo fixture XLSX files used by seed_demo.py.

Run once (or on schema change) via:
    python -m scripts.seed_demo --regenerate-fixtures

The generated files are committed to git — this script exists so we can
re-derive them from a single source of truth.

The 30 register rows include 8 deliberate mismatches:
  - Rows 23-24: amount mismatch (supplier has higher VAT)
  - Rows 25-26: missing in supplier export entirely
  - Rows 27-28: register missing — supplier export has these but register doesn't
  - Rows 29-30: fuzzy-name match (slight name variation)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

# Header rows must match the parser exactly. See parser.py.
PR_HEADERS = [
    "Invoice No",
    "Supplier BIN",
    "Supplier Name",
    "Invoice Date",
    "Taxable Amount (BDT)",
    "VAT Amount (BDT)",
]
SF_HEADERS = [
    "Invoice No",
    "Buyer BIN",
    "Invoice Date",
    "Taxable Amount (BDT)",
    "VAT Amount (BDT)",
]

# Period: previous calendar month relative to seeder run. Generator uses a
# fixed date so the fixture is reproducible; the seeder picks period_start /
# period_end at run time and doesn't read these dates from the XLSX itself.
PERIOD_START = date(2026, 4, 1)
SUPPLIERS = [
    ("123456789", "Bashundhara Industries Ltd"),
    ("234567890", "Square Textiles"),
    ("345678901", "Beximco Pharmaceuticals"),
    ("456789012", "Apex Footwear"),
    ("567890123", "Pran-RFL Group"),
]


def _build_register_rows() -> list[list[object]]:
    rows: list[list[object]] = [PR_HEADERS]
    for i in range(1, 31):
        sup_bin, sup_name = SUPPLIERS[(i - 1) % len(SUPPLIERS)]
        invoice_date = PERIOD_START + timedelta(days=i)
        taxable = Decimal("10000") + Decimal(i) * Decimal("250")
        vat = (taxable * Decimal("0.15")).quantize(Decimal("0.01"))
        # Rows 25/26: use a supplier_bin that does NOT appear in the SF pool
        # at all. This produces NO_MATCH (matcher: "supplier_bin_not_filed").
        if i == 25:
            sup_bin = "888777666"
            sup_name = "Off-Pool Supplier A"
        elif i == 26:
            sup_bin = "888777555"
            sup_name = "Off-Pool Supplier B"
        # Rows 29/30 fuzzy name: tweak the supplier name slightly so the supplier
        # export will have the canonical version. Match still happens via BIN
        # + amount but with status=fuzzy.
        if i in (29, 30):
            sup_name = sup_name.replace("Ltd", "Limited").replace("Group", "Grp.")
        rows.append([
            f"INV-{i:04d}",
            sup_bin,
            sup_name,
            invoice_date.isoformat(),
            float(taxable),
            float(vat),
        ])
    return rows


def _build_supplier_rows() -> list[list[object]]:
    """
    Build the supplier-filed export.

    NOTE on the `Buyer BIN` column: the matcher indexes the supplier-export
    pool by `buyer_bin` and looks up `pr.supplier_bin` against it. So for a
    row to be matchable, the SF row's buyer_bin MUST equal the PR row's
    supplier_bin. (The earlier fixture used a single hardcoded BUYER_BIN,
    which produced 30/30 NO_MATCH at run time — fixed here.)
    """
    rows: list[list[object]] = [SF_HEADERS]
    for i in range(1, 31):
        # Skip 25, 26 — these stay only in the register (and use an off-pool
        # BIN there) => no_match.
        if i in (25, 26):
            continue
        sup_bin, _ = SUPPLIERS[(i - 1) % len(SUPPLIERS)]
        invoice_date = PERIOD_START + timedelta(days=i)
        taxable = Decimal("10000") + Decimal(i) * Decimal("250")
        vat = (taxable * Decimal("0.15")).quantize(Decimal("0.01"))
        # Rows 23, 24: filed under a *different* invoice_no — same BIN, same
        # supplier, slightly different identifier. Matcher will report
        # PARTIAL ("bin matched but invoice did not").
        invoice_no = f"INV-{i:04d}"
        if i in (23, 24):
            invoice_no = f"INV-{i:04d}-A"
        # Rows 29, 30: supplier filed the invoice 1 day later than register.
        # Same invoice_no, same BIN, same amounts, date off by 1 → FUZZY.
        if i in (29, 30):
            invoice_date = invoice_date + timedelta(days=1)
        rows.append([
            invoice_no,
            sup_bin,
            invoice_date.isoformat(),
            float(taxable),
            float(vat),
        ])
    # Rows 27, 28: present only in supplier (register missed them).
    # The matcher's input is register-driven, so these don't appear as
    # separate match rows in the demo recon — but they make total counts
    # asymmetric, which is realistic.
    for i in (27, 28):
        sup_bin, _ = SUPPLIERS[(i - 1) % len(SUPPLIERS)]
        invoice_date = PERIOD_START + timedelta(days=i)
        taxable = Decimal("10000") + Decimal(i) * Decimal("250")
        vat = (taxable * Decimal("0.15")).quantize(Decimal("0.01"))
        rows.append([
            f"INV-{i:04d}",
            sup_bin,
            invoice_date.isoformat(),
            float(taxable),
            float(vat),
        ])
    return rows


def _write_xlsx(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> None:
    here = Path(__file__).resolve().parent
    _write_xlsx(here / "demo_register.xlsx", _build_register_rows())
    _write_xlsx(here / "demo_supplier.xlsx", _build_supplier_rows())
    print(f"Wrote {here / 'demo_register.xlsx'}")
    print(f"Wrote {here / 'demo_supplier.xlsx'}")


if __name__ == "__main__":
    main()
