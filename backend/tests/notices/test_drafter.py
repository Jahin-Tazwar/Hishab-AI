"""Drafter tests: prompt construction, citation validation, HTML sanitize."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.notices.drafter import (
    build_draft_prompt, finalize_draft_output, _validate_citation_tags,
)
from app.notices.llm import StubNoticeLLMAdapter
from app.notices.schemas import (
    CitationChunk, DraftAppendixRow, DraftParagraph, DraftReply,
    NoticeType, ParsedNotice, ReconSummary,
)


def _p() -> ParsedNotice:
    return ParsedNotice(
        notice_type=NoticeType.INPUT_VAT_MISMATCH, taxpayer_bin="001234567",
        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        alleged_shortfall_bdt=Decimal("10000.00"),
        classification_confidence=0.95,
    )


def _s() -> ReconSummary:
    return ReconSummary(
        reconciliation_id=UUID("00000000-0000-0000-0000-000000000001"),
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[],
    )


def _cit() -> list[CitationChunk]:
    return [
        CitationChunk(
            id=UUID("00000000-0000-0000-0000-0000000000aa"),
            source="vat_act_2012", source_ref="Section 46",
            language="bn", title="ITC শর্ত", body="… ধারা ৪৬ …",
        ),
    ]


def test_prompt_includes_citations_tagged():
    p = build_draft_prompt(_p(), _s(), _cit())
    assert "[CIT-1]" in p
    assert "Section 46" in p
    assert "40000.00" in p  # recon summary present


def test_validate_strips_unknown_citation_tags():
    body = "Real cite [CIT-1]. Fake cite [CIT-9]. Plain text."
    cleaned = _validate_citation_tags(body, allowed_tags={"CIT-1"})
    assert "[CIT-1]" in cleaned
    assert "[CIT-9]" not in cleaned
    assert "[citation needed — review]" in cleaned


def test_finalize_draft_output_produces_html_and_citations():
    raw = DraftReply(
        body_paragraphs=[
            DraftParagraph(text="প্যারা ১ [CIT-1].", citation_tags=["CIT-1"]),
            DraftParagraph(text="প্যারা ২ <script>alert(1)</script>", citation_tags=[]),
        ],
        computation_table_rows=[
            DraftAppendixRow(label="Claimed", value_bdt=Decimal("50000.00"), note=None),
        ],
        cited_refs=["CIT-1"],
    )
    out = finalize_draft_output(raw, retrieved_chunks=_cit())
    assert "<p>" in out["body_html"]
    assert "<script>" not in out["body_html"]
    assert '<sup class="citation"' in out["body_html"]
    assert len(out["citations"]) == 1
    assert out["citations"][0]["source_ref"] == "Section 46"


def test_finalize_replaces_unknown_tag_with_placeholder():
    raw = DraftReply(
        body_paragraphs=[
            DraftParagraph(text="ভুল cite [CIT-99].", citation_tags=["CIT-99"]),
        ],
        computation_table_rows=[],
        cited_refs=["CIT-99"],
    )
    out = finalize_draft_output(raw, retrieved_chunks=_cit())
    assert "citation needed" in out["body_html"]
