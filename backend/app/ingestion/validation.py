"""Deterministic field-level validators run AFTER extraction, BEFORE review.

These produce field-level warnings to guide the reviewer's eye. They never
auto-reject a row — that's a deliberate design choice (see spec §5).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.ingestion.schemas import ExtractedRowData, FieldWarning, JobKind

_BIN_RE = re.compile(r"^\d{9,13}$")


def _bin_warning(field: str, value: str | None) -> list[FieldWarning]:
    if value is None or value == "":
        return [FieldWarning(
            field=field, code="BIN_MISSING",
            message=f"{field} is empty",
        )]
    if not _BIN_RE.match(value):
        return [FieldWarning(
            field=field, code="BIN_FORMAT",
            message=f"{field}='{value}' is not 9-13 digits",
        )]
    return []


def _date_warning(value: date, period_start: date, period_end: date) -> list[FieldWarning]:
    if value < period_start or value > period_end:
        return [FieldWarning(
            field="invoice_date", code="DATE_OUT_OF_PERIOD",
            message=f"invoice_date {value} is outside {period_start}..{period_end}",
        )]
    return []


def _vat_ratio_warning(taxable: Decimal, vat: Decimal) -> list[FieldWarning]:
    if taxable <= 0:
        return []
    ratio = vat / taxable
    # Standard NBR rate is 15%; many goods/services use other reduced rates
    # (5%, 7.5%, 10%). Soft-flag when ratio is below 4% or above 16%.
    if ratio < Decimal("0.04") or ratio > Decimal("0.16"):
        pct = float(ratio) * 100
        return [FieldWarning(
            field="vat_amount_bdt", code="VAT_RATIO_UNUSUAL",
            message=f"VAT/Taxable = {pct:.1f}% (outside 4-16% sanity band)",
        )]
    return []


def validate_row(
    row: ExtractedRowData,
    *,
    kind: JobKind,
    period_start: date,
    period_end: date,
) -> list[FieldWarning]:
    """Return a list of field warnings for this row. Empty list = clean."""
    warnings: list[FieldWarning] = []

    if kind == JobKind.PURCHASE_REGISTER:
        warnings += _bin_warning("supplier_bin", row.supplier_bin)
    elif kind == JobKind.SUPPLIER_EXPORT:
        warnings += _bin_warning("buyer_bin", row.buyer_bin)

    warnings += _date_warning(row.invoice_date, period_start, period_end)
    warnings += _vat_ratio_warning(row.taxable_amount_bdt, row.vat_amount_bdt)

    return warnings
