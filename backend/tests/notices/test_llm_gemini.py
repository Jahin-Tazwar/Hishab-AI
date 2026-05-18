"""Live Gemini smoke tests. Skipped unless GEMINI_API_KEY set AND -m live."""
import os
import pathlib

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set",
    ),
]

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "notice_input_vat_mismatch.jpg"


def test_parse_input_vat_mismatch_notice():
    from app.notices.llm import GeminiNoticeLLMAdapter
    from app.notices.parser import parse_notice

    adapter = GeminiNoticeLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    parsed = parse_notice(
        FIXTURE.read_bytes(), mime="image/jpeg", adapter=adapter,
    )
    assert parsed.notice_type.value == "input_vat_mismatch"
    assert parsed.classification_confidence >= 0.6
    assert parsed.taxpayer_bin == "001234567"
    if parsed.alleged_shortfall_bdt is not None:
        from decimal import Decimal
        assert parsed.alleged_shortfall_bdt == Decimal("10000.00")


def test_embed_query_returns_768d_vector():
    from app.notices.llm import GeminiNoticeLLMAdapter
    a = GeminiNoticeLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    v = a.embed_query("input VAT mismatch shortfall 10000 BDT")
    assert len(v) == 768
