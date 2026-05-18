"""LLM adapter for the notices module.

Two LLM-touching operations:
  * parse_notice — Gemini Vision call returning a ParsedNotice
  * draft_reply  — Gemini text call returning a DraftReply
Plus an embedding call:
  * embed_query  — gemini-embedding-001 (768-dim) over the retrieval query string

Protocol + StubNoticeLLMAdapter mirror app/ingestion/llm.py exactly. The
real Gemini implementation is in this file; both adapters are interchangeable
at the import boundary.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional, Protocol

from app.notices.schemas import DraftReply, NoticeType, ParsedNotice


class LLMUnavailableError(Exception):
    """Raised by the stub when no canned response exists for the lookup key."""


# ── Adapter Protocol ─────────────────────────────────────────────────────


class NoticeLLMAdapter(Protocol):
    def parse_notice(
        self, *, images: list[bytes], lookup_key: str,
    ) -> ParsedNotice: ...

    def draft_reply(
        self, *, prompt: str, lookup_key: str,
    ) -> DraftReply: ...

    def embed_query(self, text: str) -> list[float]: ...


# ── Test stub ────────────────────────────────────────────────────────────


class StubNoticeLLMAdapter:
    def __init__(
        self,
        *,
        parses: Optional[dict[str, ParsedNotice]] = None,
        drafts: Optional[dict[str, DraftReply]] = None,
        embeddings: Optional[dict[str, list[float]]] = None,
    ) -> None:
        self._parses = parses or {}
        self._drafts = drafts or {}
        self._embeddings = embeddings or {}

    def parse_notice(self, *, images: list[bytes], lookup_key: str) -> ParsedNotice:
        if lookup_key not in self._parses:
            raise LLMUnavailableError(f"no canned parse for {lookup_key!r}")
        return self._parses[lookup_key]

    def draft_reply(self, *, prompt: str, lookup_key: str) -> DraftReply:
        if lookup_key not in self._drafts:
            raise LLMUnavailableError(f"no canned draft for {lookup_key!r}")
        return self._drafts[lookup_key]

    def embed_query(self, text: str) -> list[float]:
        if text not in self._embeddings:
            raise LLMUnavailableError(f"no canned embedding for query {text!r}")
        return self._embeddings[text]


# ── Module-level singleton (same pattern as app/ingestion/llm.py) ────────


_adapter: NoticeLLMAdapter | None = None


def set_notice_llm_adapter(adapter: NoticeLLMAdapter) -> None:
    global _adapter
    _adapter = adapter


def get_notice_llm_adapter() -> NoticeLLMAdapter:
    if _adapter is None:
        raise RuntimeError(
            "Notice LLM adapter not initialised. Call set_notice_llm_adapter() "
            "at startup (production: GeminiNoticeLLMAdapter; tests: stub)."
        )
    return _adapter


# ── Real Gemini implementation ───────────────────────────────────────────


_MODEL = "gemini-2.5-flash"
# `text-embedding-004` was retired from the v1beta API in late 2025; the
# current model is `gemini-embedding-001`, which defaults to 3072 dim. We
# explicitly request 768 dim so the result fits our `vector(768)` column.
_EMBED_MODEL = "gemini-embedding-001"
_EMBED_DIM = 768


_PARSE_PROMPT = """\
You extract structured metadata from a Bangladeshi NBR VAT notice.

The attached image(s) are pages of a notice — possibly in Bangla, English,
or both. Notices typically demand additional VAT, allege ITC mismatch, or
schedule an audit.

For each field, return null if not present. Decimal amounts as numeric
strings with 2 decimals (e.g. "12345.00"). Dates as YYYY-MM-DD. BIN/TIN
as digit strings only (strip punctuation).

Classify `notice_type` as ONE of:
  - "input_vat_mismatch" : alleges the taxpayer's claimed input VAT
    exceeds what suppliers reported / what NBR accepts.
  - "unsupported" : any other category (audit invitation, output VAT
    understatement, BIN registration, general inquiry, demand for non-VAT
    matter). Use this if you are unsure or the notice is for a category
    other than input VAT mismatch.

Set `classification_confidence` between 0.0 and 1.0 reflecting how certain
you are about `notice_type`.
"""


_DRAFT_SYSTEM = """\
You draft formal Bangla replies to NBR VAT notices for a Bangladeshi
Chartered Accountancy firm. Follow NBR formal-letter conventions:
"প্রসঙ্গ:" reference line, "প্রিয় মহোদয়," opening, numbered factual
paragraphs, a closing courtesy, and the CA firm signature block.

Hard rules:
  - You MAY only cite from the provided citations list, referencing each
    by its tag e.g. [CIT-1]. Never invent section numbers or rule numbers.
  - If you cannot find a citation supporting a point, omit the citation —
    do NOT make one up.
  - The body MUST be in Bangla. Numbers and BDT amounts may appear in
    Western digits.
  - Use the reconciliation data provided as the ground truth for what the
    taxpayer's actual position is. Do not invent supplier names or amounts.
"""


class GeminiNoticeLLMAdapter:
    def __init__(self, *, api_key: str, model_name: str = _MODEL) -> None:
        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=api_key)
        self._types = types
        self._model_name = model_name

    # ── Parse ────

    def parse_notice(self, *, images: list[bytes], lookup_key: str) -> ParsedNotice:
        Type = self._types.Type
        schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "notice_no": self._types.Schema(type=Type.STRING, nullable=True),
                "notice_date": self._types.Schema(type=Type.STRING, nullable=True),
                "notice_type": self._types.Schema(
                    type=Type.STRING,
                    enum=["input_vat_mismatch", "unsupported"],
                ),
                "taxpayer_bin": self._types.Schema(type=Type.STRING, nullable=True),
                "taxpayer_tin": self._types.Schema(type=Type.STRING, nullable=True),
                "period_start": self._types.Schema(type=Type.STRING, nullable=True),
                "period_end": self._types.Schema(type=Type.STRING, nullable=True),
                "alleged_itc_claimed_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "alleged_itc_allowed_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "alleged_shortfall_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "classification_confidence": self._types.Schema(type=Type.NUMBER),
            },
            required=["notice_type", "classification_confidence"],
        )

        parts: list[Any] = [_PARSE_PROMPT]
        for img in images:
            parts.append(self._types.Part.from_bytes(data=img, mime_type="image/png"))

        res = self._client.models.generate_content(
            model=self._model_name,
            contents=parts,
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        data = json.loads(res.text)
        return ParsedNotice(**data)

    # ── Draft ────

    def draft_reply(self, *, prompt: str, lookup_key: str) -> DraftReply:
        Type = self._types.Type
        paragraph_schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "text": self._types.Schema(type=Type.STRING),
                "citation_tags": self._types.Schema(
                    type=Type.ARRAY,
                    items=self._types.Schema(type=Type.STRING),
                ),
            },
            required=["text"],
        )
        appendix_row_schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "label": self._types.Schema(type=Type.STRING),
                "value_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "note": self._types.Schema(type=Type.STRING, nullable=True),
            },
            required=["label"],
        )
        schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "body_paragraphs": self._types.Schema(
                    type=Type.ARRAY, items=paragraph_schema,
                ),
                "computation_table_rows": self._types.Schema(
                    type=Type.ARRAY, items=appendix_row_schema,
                ),
                "cited_refs": self._types.Schema(
                    type=Type.ARRAY,
                    items=self._types.Schema(type=Type.STRING),
                ),
            },
            required=["body_paragraphs", "computation_table_rows"],
        )

        res = self._client.models.generate_content(
            model=self._model_name,
            contents=[_DRAFT_SYSTEM, prompt],
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        data = json.loads(res.text)
        # Convert money strings to Decimals via Pydantic
        return DraftReply(**data)

    # ── Embed ────

    def embed_query(self, text: str) -> list[float]:
        res = self._client.models.embed_content(
            model=_EMBED_MODEL,
            contents=text,
            config=self._types.EmbedContentConfig(
                output_dimensionality=_EMBED_DIM,
            ),
        )
        return list(res.embeddings[0].values)
