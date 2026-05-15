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
