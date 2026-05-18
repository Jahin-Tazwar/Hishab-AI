"""Retriever tests — unit tests stub the embedder; live ANN test is gated."""
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.notices.llm import StubNoticeLLMAdapter
from app.notices.retriever import build_query_text, retrieve
from app.notices.schemas import CitationChunk, NoticeType, ParsedNotice, ReconSummary


def _parsed() -> ParsedNotice:
    return ParsedNotice(
        notice_no="X", notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567", period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        alleged_itc_claimed_bdt=Decimal("50000.00"),
        alleged_itc_allowed_bdt=Decimal("40000.00"),
        alleged_shortfall_bdt=Decimal("10000.00"),
        classification_confidence=0.95,
    )


def _summary() -> ReconSummary:
    return ReconSummary(
        reconciliation_id=UUID("00000000-0000-0000-0000-000000000001"),
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[],
    )


def test_build_query_text_includes_key_signals():
    q = build_query_text(_parsed(), _summary())
    assert "input VAT" in q.lower() or "input_vat_mismatch" in q
    assert "10000" in q or "10,000" in q
    assert "no_match" in q or "no-match" in q


@pytest.mark.asyncio
async def test_retrieve_uses_embedder_then_db(monkeypatch):
    canned_chunk = CitationChunk(
        id=UUID("00000000-0000-0000-0000-0000000000aa"),
        source="vat_act_2012", source_ref="Section 46", subsection=None,
        language="en", title="Conditions for input tax credit",
        body="A registered person shall be entitled…",
    )
    stub = StubNoticeLLMAdapter(embeddings={})
    q = build_query_text(_parsed(), _summary())
    stub._embeddings[q] = [0.1] * 768

    async def fake_db(*, embedding, topic_tags, k):
        assert len(embedding) == 768
        assert "itc" in topic_tags or "mismatch" in topic_tags
        return [canned_chunk]
    monkeypatch.setattr("app.notices.retriever.retrieve_citation_chunks", fake_db)

    out = await retrieve(_parsed(), _summary(), adapter=stub)
    assert len(out) == 1
    assert out[0].source_ref == "Section 46"
