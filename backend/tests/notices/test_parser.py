"""Parser tests using StubNoticeLLMAdapter."""
from datetime import date
from decimal import Decimal

import pytest

from app.notices.llm import LLMUnavailableError, StubNoticeLLMAdapter
from app.notices.parser import parse_notice
from app.notices.schemas import NoticeType, ParsedNotice


_CANNED = ParsedNotice(
    notice_no="NBR/VAT/1/2026",
    notice_date=date(2026, 5, 1),
    notice_type=NoticeType.INPUT_VAT_MISMATCH,
    taxpayer_bin="001234567",
    period_start=date(2026, 4, 1),
    period_end=date(2026, 4, 30),
    alleged_shortfall_bdt=Decimal("10000.00"),
    classification_confidence=0.95,
)


def _png(byte: int = 0) -> bytes:
    # Minimal PNG header so _normalize_image_to_png accepts it
    return b"\x89PNG\r\n\x1a\n" + bytes([byte] * 64)


def test_parse_image_returns_parsed_notice(monkeypatch):
    monkeypatch.setattr(
        "app.notices.parser._normalize_image_to_png",
        lambda b: b,
    )
    stub = StubNoticeLLMAdapter(parses={"fixed-key": _CANNED})
    out = parse_notice(
        _png(), mime="image/png", adapter=stub,
        lookup_key_override="fixed-key",
    )
    assert out.notice_no == "NBR/VAT/1/2026"
    assert out.notice_type == NoticeType.INPUT_VAT_MISMATCH


def test_parse_uses_hash_lookup_key_when_not_overridden(monkeypatch):
    monkeypatch.setattr(
        "app.notices.parser._normalize_image_to_png",
        lambda b: b"normalized",
    )
    import hashlib
    key = hashlib.sha256(b"normalized").hexdigest()[:16]
    stub = StubNoticeLLMAdapter(parses={key: _CANNED})
    out = parse_notice(_png(), mime="image/png", adapter=stub)
    assert out is not None


def test_parse_raises_for_unsupported_mime():
    from app.notices.exceptions import NoticeUnsupportedTypeError
    stub = StubNoticeLLMAdapter(parses={})
    with pytest.raises(NoticeUnsupportedTypeError):
        parse_notice(b"x", mime="application/zip", adapter=stub)


def test_parse_propagates_llm_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.notices.parser._normalize_image_to_png",
        lambda b: b,
    )
    stub = StubNoticeLLMAdapter(parses={})
    with pytest.raises(LLMUnavailableError):
        parse_notice(_png(), mime="image/png", adapter=stub)
