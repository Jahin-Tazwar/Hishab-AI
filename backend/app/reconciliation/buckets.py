"""Single source of truth for ITC bucket assignment.

A line item ends up in one of three buckets, in priority order:

  1. The CA override (if set) — `approved` → safe, `disputed` → at_risk,
     `ignore` → excluded from totals.
  2. Otherwise, the engine's match_status — `exact`/`fuzzy` → safe,
     `partial`/`no_match` → at_risk.

The frontend mirrors this exact logic in
`frontend/src/lib/reconciliation/buckets.ts` so the badge a CA sees in the
table is the bucket the row will actually contribute to. Keep both in sync.
"""
from __future__ import annotations

from typing import Literal, Optional

from .schemas import CAOverride, MatchStatus

Bucket = Literal["safe", "at_risk", "ignored"]

_SAFE_MATCHES = {MatchStatus.EXACT.value, MatchStatus.FUZZY.value}


def effective_bucket(
    match_status: str, ca_override: Optional[str],
) -> Bucket:
    """Returns the bucket this row contributes to in the headline KPI totals.

    Accepts raw string values (as stored in `recon_line_items`) to avoid
    needing the caller to import the enum.
    """
    if ca_override == CAOverride.APPROVED.value:
        return "safe"
    if ca_override == CAOverride.DISPUTED.value:
        return "at_risk"
    if ca_override == CAOverride.IGNORE.value:
        return "ignored"
    return "safe" if match_status in _SAFE_MATCHES else "at_risk"
