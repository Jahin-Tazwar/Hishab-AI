"""Aggregate match results into headline numbers for the recon report."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from .buckets import effective_bucket
from .schemas import AggregatesDTO, MatchResult, MatchStatus


def aggregate(matches: Iterable[MatchResult]) -> AggregatesDTO:
    """Aggregate raw matcher output (no CA overrides yet) for the initial
    persist. After overrides happen, call `aggregate_from_db_rows` instead.
    """
    matches = list(matches)
    total = len(matches)
    counts = {s: 0 for s in MatchStatus}
    safe = Decimal("0.00")
    at_risk = Decimal("0.00")

    for m in matches:
        counts[m.status] += 1
        bucket = effective_bucket(m.status.value, ca_override=None)
        if bucket == "safe":
            safe += m.pr_row.vat_amount_bdt
        elif bucket == "at_risk":
            at_risk += m.pr_row.vat_amount_bdt
        # bucket == "ignored" — excluded (impossible here since ca_override=None,
        # but kept for symmetry with aggregate_from_db_rows)

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


def aggregate_from_db_rows(rows: Iterable[dict[str, Any]]) -> AggregatesDTO:
    """Recompute aggregates from persisted `recon_line_items` rows, honoring
    CA overrides.

    `match_status` counts always reflect what the engine produced — that's
    the user's view of how the matcher classified the period and shouldn't
    silently shift when a CA marks a row approved. Only the VAT bucket
    sums (`safe_itc_bdt`, `at_risk_itc_bdt`) and the running total respond
    to overrides.

    Rows with `ca_override = 'ignore'` are excluded from `total_vat_claimed_bdt`
    so it always equals `safe + at_risk`.
    """
    rows = list(rows)
    total = len(rows)
    counts = {s: 0 for s in MatchStatus}
    safe = Decimal("0.00")
    at_risk = Decimal("0.00")

    for r in rows:
        ms = r.get("match_status")
        try:
            counts[MatchStatus(ms)] += 1
        except ValueError:
            # Defensive: skip unknown statuses rather than KeyError-crash a
            # save path. (Should never happen — the column has a CHECK
            # constraint — but worth being kind to ourselves.)
            pass
        bucket = effective_bucket(ms, r.get("ca_override"))
        vat = Decimal(str(r.get("pr_vat_amount_bdt") or "0"))
        if bucket == "safe":
            safe += vat
        elif bucket == "at_risk":
            at_risk += vat
        # bucket == "ignored" → excluded

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
