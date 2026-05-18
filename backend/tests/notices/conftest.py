"""Shared fixtures for notice tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

try:
    from app.notices.schemas import (
        CitationChunk, NoticeType, ParsedNotice, ReconSummary,
    )
except ImportError:
    pytest.skip(
        "app.notices.schemas not yet defined (Task 3.1); fixtures unavailable",
        allow_module_level=True,
    )


@pytest.fixture
def parsed_notice() -> ParsedNotice:
    return ParsedNotice(
        notice_no="NBR/VAT/12345/2026",
        notice_date=date(2026, 5, 1),
        notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567",
        taxpayer_tin=None,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        alleged_itc_claimed_bdt=Decimal("50000.00"),
        alleged_itc_allowed_bdt=Decimal("40000.00"),
        alleged_shortfall_bdt=Decimal("10000.00"),
        classification_confidence=0.95,
    )


@pytest.fixture
def recon_summary() -> ReconSummary:
    return ReconSummary(
        reconciliation_id="00000000-0000-0000-0000-000000000001",
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[
            {"supplier_name": "ACME Ltd", "supplier_bin": "987654321",
             "invoice_no": "INV-99", "vat_amount_bdt": "5000.00",
             "match_status": "no_match"},
        ],
    )


@pytest.fixture
def citation_chunk_en() -> CitationChunk:
    return CitationChunk(
        id="00000000-0000-0000-0000-0000000000aa",
        source="vat_act_2012",
        source_ref="Section 46",
        subsection=None,
        language="en",
        title="Conditions for input tax credit",
        body="A registered person shall be entitled to take an input tax credit…",
    )
