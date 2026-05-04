"""XLSX parsers for the purchase register and supplier export formats."""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from app.core.exceptions import InvalidXlsxFormatError

from .schemas import PurchaseRow, SupplierRow


# Required columns are matched case-insensitively after stripping whitespace.
_PURCHASE_COLUMNS = {
    "invoice no":            "invoice_no",
    "supplier bin":          "supplier_bin",
    "supplier name":         "supplier_name",
    "invoice date":          "invoice_date",
    "taxable amount (bdt)":  "taxable_amount_bdt",
    "vat amount (bdt)":      "vat_amount_bdt",
}

_SUPPLIER_COLUMNS = {
    "invoice no":            "invoice_no",
    "invoice date":          "invoice_date",
    "taxable amount (bdt)":  "taxable_amount_bdt",
    "vat amount (bdt)":      "vat_amount_bdt",
    "buyer bin":             "buyer_bin",
}

# Original-cased column labels for error messages
_PRETTY = {
    "invoice no": "Invoice No",
    "supplier bin": "Supplier BIN",
    "supplier name": "Supplier Name",
    "invoice date": "Invoice Date",
    "taxable amount (bdt)": "Taxable Amount (BDT)",
    "vat amount (bdt)": "VAT Amount (BDT)",
    "buyer bin": "Buyer BIN",
}


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _check_columns(df: pd.DataFrame, required: dict[str, str], label: str) -> None:
    missing = [_PRETTY[k] for k in required if k not in df.columns]
    if missing:
        raise InvalidXlsxFormatError(file_label=label, missing_columns=missing)


def _coerce_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Could not parse date: {value!r}")


def _coerce_str(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).strip() or None


def parse_purchase_register(file_bytes: bytes) -> list[PurchaseRow]:
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    df = _normalize_headers(df)
    _check_columns(df, _PURCHASE_COLUMNS, label="purchase register")

    out: list[PurchaseRow] = []
    for _, row in df.iterrows():
        out.append(PurchaseRow(
            invoice_no=str(row["invoice no"]).strip(),
            supplier_bin=_coerce_str(row["supplier bin"]),
            supplier_name=_coerce_str(row["supplier name"]),
            invoice_date=_coerce_date(row["invoice date"]),
            taxable_amount_bdt=row["taxable amount (bdt)"],
            vat_amount_bdt=row["vat amount (bdt)"],
        ))
    return out


def parse_supplier_export(file_bytes: bytes) -> list[SupplierRow]:
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    df = _normalize_headers(df)
    _check_columns(df, _SUPPLIER_COLUMNS, label="supplier export")

    out: list[SupplierRow] = []
    for _, row in df.iterrows():
        out.append(SupplierRow(
            invoice_no=str(row["invoice no"]).strip(),
            invoice_date=_coerce_date(row["invoice date"]),
            taxable_amount_bdt=row["taxable amount (bdt)"],
            vat_amount_bdt=row["vat amount (bdt)"],
            buyer_bin=_coerce_str(row["buyer bin"]),
        ))
    return out
