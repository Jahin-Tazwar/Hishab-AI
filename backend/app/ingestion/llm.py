"""LLM adapter interface + StubLLMAdapter (CI) + GeminiLLMAdapter (real).

The real Gemini implementation is wired in Task 9. This task ships only the
interface and the test stub so all subsequent tasks can be developed and
tested without network access.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional, Protocol

from app.ingestion.schemas import JobKind


class LLMUnavailableError(Exception):
    """Raised by the stub when it has no canned response for the given input.

    The real adapter raises a different exception (network/quota); the stub
    raising LLMUnavailableError is purely a test-discipline tool — if a test
    triggers this, that test is missing a mock entry.
    """


def column_signature(headers: list[str]) -> str:
    """Order-independent, case-insensitive hash of a header set.

    Used as the cache key for column_mappings AND as the lookup key for
    StubLLMAdapter.column_mappings in tests.
    """
    norm = sorted({(h or "").strip().lower() for h in headers if h})
    return hashlib.sha256("|".join(norm).encode()).hexdigest()


class LLMAdapter(Protocol):
    """Two LLM-touching operations the ingestion module needs."""

    def map_columns(
        self,
        *,
        headers: list[str],
        sample_rows: list[list[str]],
        kind: JobKind,
    ) -> dict[str, Optional[str]]:
        """Return mapping from canonical_field -> source column name (or None)."""

    def extract_rows(
        self,
        *,
        text: str,
        lookup_key: str,
        kind: JobKind,
        images: Optional[list[bytes]] = None,
    ) -> list[dict[str, Any]]:
        """Extract rows from text+optional images. Returns list of dicts
        matching ExtractedRowData fields (as JSON-serializable values).
        """


class StubLLMAdapter:
    """Test double. Deterministic — given input X, returns canned Y or raises.

    Inject into tests via dependency injection; never used in production.
    """

    def __init__(
        self,
        *,
        column_mappings: Optional[dict[str, dict[str, Optional[str]]]] = None,
        extractions: Optional[dict[str, list[dict[str, Any]]]] = None,
    ) -> None:
        self._column_mappings = column_mappings or {}
        self._extractions = extractions or {}

    def map_columns(
        self,
        *,
        headers: list[str],
        sample_rows: list[list[str]],
        kind: JobKind,
    ) -> dict[str, Optional[str]]:
        sig = column_signature(headers)
        if sig not in self._column_mappings:
            raise LLMUnavailableError(
                f"Stub has no canned mapping for headers signature {sig[:12]}…"
            )
        return self._column_mappings[sig]

    def extract_rows(
        self,
        *,
        text: str,
        lookup_key: str,
        kind: JobKind,
        images: Optional[list[bytes]] = None,
    ) -> list[dict[str, Any]]:
        if lookup_key not in self._extractions:
            raise LLMUnavailableError(
                f"Stub has no canned extraction for lookup_key {lookup_key!r}"
            )
        return self._extractions[lookup_key]


# Module-level singleton plumbing so engines can ask for the adapter without
# having a hardcoded dependency on a specific impl. Tests override via
# `set_llm_adapter(StubLLMAdapter(...))`.

_adapter: LLMAdapter | None = None


def set_llm_adapter(adapter: LLMAdapter) -> None:
    global _adapter
    _adapter = adapter


def get_llm_adapter() -> LLMAdapter:
    if _adapter is None:
        raise RuntimeError(
            "LLM adapter not initialised. Call set_llm_adapter() at startup "
            "(production: GeminiLLMAdapter; tests: StubLLMAdapter)."
        )
    return _adapter


# ─────────────────────────────────────────────────────────────────────────
# Real Gemini implementation
# ─────────────────────────────────────────────────────────────────────────

import json as _json
from typing import cast

import google.generativeai as genai


_MODEL = "gemini-2.5-flash"

_SCHEMA_FIELDS = [
    "invoice_no", "supplier_bin", "supplier_name", "buyer_bin",
    "invoice_date", "taxable_amount_bdt", "vat_amount_bdt",
]


_COLUMN_MAP_PROMPT = """\
You map column headers from a tax invoice register to a canonical schema
used by HishabAI's reconciliation engine for Bangladesh VAT.

Canonical fields:
  - invoice_no            (Mushak invoice / bill number; the unique reference)
  - supplier_bin          (BIN of the supplier — for purchase registers)
  - supplier_name         (supplier business name)
  - buyer_bin             (BIN of the buyer — for supplier-export filings)
  - invoice_date          (date of the invoice; any locale date format)
  - taxable_amount_bdt    (the pre-VAT taxable value, in Bangladeshi Taka)
  - vat_amount_bdt        (the VAT charged, in Bangladeshi Taka)

The headers may be in English, Bangla, or mixed. Common Bangla forms:
  বিল নং / চালান নং (invoice no), সরবরাহকারী BIN (supplier_bin),
  তারিখ (date), মোট মূল্য / করযোগ্য মূল্য (taxable), মূসক / VAT (vat).

Headers: {headers}

Sample rows (first 3):
{samples}

Job kind: {kind}

Return a JSON object mapping each canonical field to the EXACT source
column name (string) or null if no plausible source exists. Do not invent
columns. Do not include any field that is not in the canonical list above.
"""


_EXTRACT_PROMPT = """\
You extract Bangladesh VAT invoice data into a strict JSON schema.

Job kind: {kind}

Canonical fields per row:
{fields}

For dates, return ISO 8601 (YYYY-MM-DD).
For amounts, return numeric strings with 2 decimals (e.g. "1234.50").
For BINs, return digit strings of 9-13 chars or null.

If you can identify multiple distinguishable invoices in the input, return
one row per invoice. If the input is unreadable or contains no invoice
data, return an empty array.

Do not include keys outside the canonical list. Do not return null
where a string is required (invoice_no, invoice_date,
taxable_amount_bdt, vat_amount_bdt).

Input:
---
{text}
---
"""


class GeminiLLMAdapter:
    """Production LLM adapter using Google's google-generativeai SDK
    against the Gemini 2.5 Flash model.

    Configured with an API key (the simplest auth path). For Vertex AI,
    swap in `vertexai.generative_models.GenerativeModel` with the same
    method shape and a service-account credential.
    """

    def __init__(self, *, api_key: str, model_name: str = _MODEL) -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)

    # ── public API ──

    def map_columns(
        self,
        *,
        headers: list[str],
        sample_rows: list[list[str]],
        kind: JobKind,
    ) -> dict[str, Optional[str]]:
        prompt = _COLUMN_MAP_PROMPT.format(
            headers=_json.dumps(headers, ensure_ascii=False),
            samples=_json.dumps(sample_rows[:3], ensure_ascii=False, indent=2),
            kind=kind.value,
        )
        out = self._call_json(prompt)
        # Normalize: ensure all canonical fields present, default to None
        return {f: out.get(f) for f in _SCHEMA_FIELDS}

    def extract_rows(
        self,
        *,
        text: str,
        lookup_key: str,  # ignored in production; for stub-API parity
        kind: JobKind,
        images: Optional[list[bytes]] = None,
    ) -> list[dict[str, Any]]:
        prompt = _EXTRACT_PROMPT.format(
            kind=kind.value,
            fields="  - " + "\n  - ".join(_SCHEMA_FIELDS),
            text=text,
        )
        if images:
            parts: list[Any] = [prompt]
            for img in images:
                parts.append({"mime_type": "image/png", "data": img})
            res = self._model.generate_content(
                parts,
                generation_config={"response_mime_type": "application/json"},
            )
        else:
            res = self._model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
        try:
            data = _json.loads(res.text)
        except Exception as e:
            raise RuntimeError(f"Gemini returned non-JSON: {res.text[:200]}") from e
        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]
        if not isinstance(data, list):
            raise RuntimeError(f"Gemini returned non-array: {data!r}")
        return cast(list[dict[str, Any]], data)

    # ── helpers ──

    def _call_json(self, prompt: str) -> dict[str, Any]:
        res = self._model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        try:
            return cast(dict[str, Any], _json.loads(res.text))
        except Exception as e:
            raise RuntimeError(f"Gemini returned non-JSON: {res.text[:200]}") from e
