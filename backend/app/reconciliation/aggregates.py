"""Aggregate match results into headline numbers for the recon report."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .schemas import AggregatesDTO, MatchResult, MatchStatus

_SAFE = {MatchStatus.EXACT, MatchStatus.FUZZY}


def aggregate(matches: Iterable[MatchResult]) -> AggregatesDTO:
    matches = list(matches)
    total = len(matches)
    counts = {s: 0 for s in MatchStatus}
    safe = Decimal("0.00")
    at_risk = Decimal("0.00")

    for m in matches:
        counts[m.status] += 1
        if m.status in _SAFE:
            safe += m.pr_row.vat_amount_bdt
        else:
            at_risk += m.pr_row.vat_amount_bdt

    return AggregatesDTO(
        total_invoices=total,
        matched_exact=counts[MatchStatus.EXACT],
        matched_fuzzy=counts[MatchStatus.FUZZY],
        partial_match=counts[MatchStatus.PARTIAL],
        no_match=counts[MatchStatus.NO_MATCH],
        total_vat_claimed_bdt=safe + at_risk,
        safe_itc_bdt=safe,
        at_risk_itc_bdt=at_risk,
    )
