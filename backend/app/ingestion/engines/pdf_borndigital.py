"""Engine for born-digital PDFs.

Uses pdfplumber to extract text+tables losslessly, then sends the text
to the LLM with the canonical schema for structured normalization.
Auto-passes (no review) because the text extraction itself is deterministic.
"""
from __future__ import annotations

import hashlib
import io
from typing import Any, Optional

import pdfplumber

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.llm import get_llm_adapter
from app.ingestion.schemas import ExtractedRowData


_TEXT_DENSITY_THRESHOLD = 50  # chars/page; below this we treat as scanned


class PdfBornDigitalEngine:
    name = "pdfplumber+llm"

    def __init__(self, lookup_key_for_test: Optional[str] = None) -> None:
        # Tests inject a fixed lookup_key so StubLLMAdapter responses are stable.
        self._test_key = lookup_key_for_test

    def has_extractable_text(self, file_bytes: bytes) -> bool:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if len(text) >= _TEXT_DENSITY_THRESHOLD:
                    return True
        return False

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        page_texts: list[str] = []
        page_count = 0
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                tbl_text = "\n".join(
                    "\n".join(" | ".join(str(c) if c else "" for c in row)
                              for row in t)
                    for t in tables
                )
                page_texts.append(text + ("\n\n" + tbl_text if tbl_text else ""))

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts)
        lookup_key = self._test_key or hashlib.sha256(file_bytes).hexdigest()[:16]

        raw_rows = get_llm_adapter().extract_rows(
            text=full_text,
            lookup_key=lookup_key,
            kind=ctx.kind,
            images=None,
        )
        rows = [ExtractedRowData(**self._coerce(r)) for r in raw_rows]

        return ExtractedFileResult(
            rows=rows,
            needs_review=False,
            extraction_engine="pdfplumber+llm",
            page_count=page_count,
            warnings=[],
        )

    @staticmethod
    def _coerce(d: dict[str, Any]) -> dict[str, Any]:
        keep = {
            "invoice_no", "supplier_bin", "supplier_name", "buyer_bin",
            "invoice_date", "taxable_amount_bdt", "vat_amount_bdt",
        }
        return {k: v for k, v in d.items() if k in keep}
