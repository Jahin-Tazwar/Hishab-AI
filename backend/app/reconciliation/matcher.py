"""VAT reconciliation matching engine.

Per-row decision priority (first match wins):
    EXACT  > FUZZY > PARTIAL > NO_MATCH

EXACT:    same BIN, same normalized invoice_no, same date, same amounts (<0.01 BDT diff)
FUZZY:    same BIN, same normalized invoice_no, date within 3 days, amount within 0.5%
PARTIAL:  same BIN exists in supplier pool, but no invoice_no match
NO_MATCH: BIN not present in supplier pool at all
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from .normalize import normalize_invoice_no
from .schemas import (
    DiscrepancyFlags, MatchResult, MatchStatus,
    PurchaseRow, SupplierRow,
)

EXACT_AMOUNT_TOL = Decimal("0.01")        # BDT
FUZZY_DATE_TOL_DAYS = 3
FUZZY_AMOUNT_TOL_PCT = 0.005              # 0.5%


def _index_supplier_pool(rows: Iterable[SupplierRow]) -> dict[str, list[SupplierRow]]:
    """Group supplier rows by buyer_bin so we can do constant-time lookup."""
    out: dict[str, list[SupplierRow]] = defaultdict(list)
    for r in rows:
        if r.buyer_bin:
            out[r.buyer_bin].append(r)
    return dict(out)


def _amount_diff_pct(pr_amount: Decimal, sf_amount: Decimal) -> float:
    """Returns the absolute relative diff. Uses sf_amount as denominator."""
    if sf_amount == 0:
        return float("inf")
    return float(abs(pr_amount - sf_amount) / sf_amount)


def _try_exact(pr: PurchaseRow, sf: SupplierRow) -> bool:
    if pr.invoice_date != sf.invoice_date:
        return False
    if abs(pr.taxable_amount_bdt - sf.taxable_amount_bdt) >= EXACT_AMOUNT_TOL:
        return False
    if abs(pr.vat_amount_bdt - sf.vat_amount_bdt) >= EXACT_AMOUNT_TOL:
        return False
    return True


def _try_fuzzy(pr: PurchaseRow, sf: SupplierRow) -> bool:
    if abs((pr.invoice_date - sf.invoice_date).days) > FUZZY_DATE_TOL_DAYS:
        return False
    pct = _amount_diff_pct(pr.taxable_amount_bdt, sf.taxable_amount_bdt)
    if pct > FUZZY_AMOUNT_TOL_PCT:
        return False
    return True


def match_one(pr: PurchaseRow, by_bin: dict[str, list[SupplierRow]]) -> MatchResult:
    """Match one purchase row against the indexed supplier pool."""
    if not pr.supplier_bin or pr.supplier_bin not in by_bin:
        return MatchResult(
            pr_row=pr, sf_row=None,
            status=MatchStatus.NO_MATCH, score=Decimal("0.00"),
            flags=DiscrepancyFlags(reason="supplier_bin_not_filed"),
        )

    pool = by_bin[pr.supplier_bin]
    pr_norm = normalize_invoice_no(pr.invoice_no)

    invoice_candidates = [s for s in pool if normalize_invoice_no(s.invoice_no) == pr_norm]

    # EXACT
    for sf in invoice_candidates:
        if _try_exact(pr, sf):
            return MatchResult(
                pr_row=pr, sf_row=sf,
                status=MatchStatus.EXACT, score=Decimal("1.00"),
            )

    # FUZZY
    for sf in invoice_candidates:
        if _try_fuzzy(pr, sf):
            days_off = abs((pr.invoice_date - sf.invoice_date).days)
            amount_diff = pr.taxable_amount_bdt - sf.taxable_amount_bdt
            return MatchResult(
                pr_row=pr, sf_row=sf,
                status=MatchStatus.FUZZY, score=Decimal("0.80"),
                flags=DiscrepancyFlags(
                    date_off_by_days=days_off,
                    amount_diff_bdt=amount_diff,
                    amount_diff_pct=_amount_diff_pct(
                        pr.taxable_amount_bdt, sf.taxable_amount_bdt),
                ),
            )

    # PARTIAL — bin matched but invoice did not
    return MatchResult(
        pr_row=pr, sf_row=None,
        status=MatchStatus.PARTIAL, score=Decimal("0.40"),
        flags=DiscrepancyFlags(reason="no_invoice_no_match"),
    )


def match_register(
    pr_rows: list[PurchaseRow],
    sf_rows: list[SupplierRow],
) -> list[MatchResult]:
    """Match every purchase row against the supplier pool."""
    by_bin = _index_supplier_pool(sf_rows)
    return [match_one(pr, by_bin) for pr in pr_rows]
