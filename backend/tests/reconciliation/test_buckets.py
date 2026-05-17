"""Tests for `effective_bucket` — the single source of truth for ITC
bucket assignment. Mirrored on the frontend in
`frontend/src/lib/reconciliation/buckets.ts`; if these tests change, that
file likely needs updating too.
"""
from __future__ import annotations

import pytest

from app.reconciliation.buckets import effective_bucket


# ── No override → match_status decides ───────────────────────────────────

@pytest.mark.parametrize("status,expected", [
    ("exact",    "safe"),
    ("fuzzy",    "safe"),
    ("partial",  "at_risk"),
    ("no_match", "at_risk"),
])
def test_no_override_uses_match_status(status: str, expected: str) -> None:
    assert effective_bucket(status, None) == expected


# ── Override always wins, regardless of match_status ─────────────────────

@pytest.mark.parametrize("status", ["exact", "fuzzy", "partial", "no_match"])
def test_approved_override_forces_safe(status: str) -> None:
    assert effective_bucket(status, "approved") == "safe"


@pytest.mark.parametrize("status", ["exact", "fuzzy", "partial", "no_match"])
def test_disputed_override_forces_at_risk(status: str) -> None:
    assert effective_bucket(status, "disputed") == "at_risk"


@pytest.mark.parametrize("status", ["exact", "fuzzy", "partial", "no_match"])
def test_ignore_override_excludes(status: str) -> None:
    assert effective_bucket(status, "ignore") == "ignored"


# ── Unknown override string falls through to match_status ────────────────

def test_unknown_override_value_falls_through() -> None:
    """A typo in `ca_override` shouldn't crash the aggregator — fall back to
    the match_status default. The DB CHECK constraint prevents this in
    practice, but the function should be tolerant."""
    assert effective_bucket("exact", "maybe") == "safe"
    assert effective_bucket("no_match", "maybe") == "at_risk"
