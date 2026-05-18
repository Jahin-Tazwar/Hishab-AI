"""StubNoticeLLMAdapter unit tests. Deterministic; no network."""
from datetime import date
from decimal import Decimal

import pytest

from app.notices.llm import (
    LLMUnavailableError, StubNoticeLLMAdapter,
)
from app.notices.schemas import (
    DraftAppendixRow, DraftParagraph, DraftReply, NoticeType, ParsedNotice,
)


def test_stub_parse_returns_canned():
    canned = ParsedNotice(
        notice_no="X-1", notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567", classification_confidence=0.95,
        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        alleged_shortfall_bdt=Decimal("10000.00"),
    )
    stub = StubNoticeLLMAdapter(parses={"abc": canned})
    out = stub.parse_notice(images=[b"x"], lookup_key="abc")
    assert out.notice_no == "X-1"


def test_stub_parse_raises_for_unknown_key():
    stub = StubNoticeLLMAdapter(parses={})
    with pytest.raises(LLMUnavailableError):
        stub.parse_notice(images=[b"x"], lookup_key="never-seen")


def test_stub_draft_returns_canned():
    canned = DraftReply(
        body_paragraphs=[DraftParagraph(text="hi [CIT-1]", citation_tags=["CIT-1"])],
        computation_table_rows=[DraftAppendixRow(label="x", value_bdt=Decimal("1.00"))],
        cited_refs=["CIT-1"],
    )
    stub = StubNoticeLLMAdapter(drafts={"k": canned})
    out = stub.draft_reply(prompt="ignored", lookup_key="k")
    assert out.cited_refs == ["CIT-1"]


def test_stub_embed_returns_canned_vector():
    stub = StubNoticeLLMAdapter(embeddings={"q": [0.1] * 768})
    v = stub.embed_query("q")
    assert len(v) == 768
