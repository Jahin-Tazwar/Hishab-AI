"""Vision engine: scanned PDFs and photos via Gemini Flash multi-modal.

For PDFs: render each page to a PNG with pypdfium2 (no Poppler dep).
For images: HEIC/WEBP convert to PNG via Pillow, then send raw bytes.

Always flagged needs_review per spec §5.
"""
from __future__ import annotations

import hashlib
import io
from typing import Any, Optional

import pypdfium2 as pdfium
from PIL import Image

# Register HEIC support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.llm import get_llm_adapter
from app.ingestion.schemas import ExtractedRowData

_PDF_DPI = 200
_MAX_PAGES_PER_CALL = 10


class VisionEngine:
    name = "gemini-vision"

    def __init__(self, lookup_key_for_test: Optional[str] = None) -> None:
        self._test_key = lookup_key_for_test

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        images = self._to_png_pages(file_bytes)
        page_count = len(images)

        all_rows: list[dict[str, Any]] = []
        for chunk_start in range(0, page_count, _MAX_PAGES_PER_CALL):
            chunk = images[chunk_start:chunk_start + _MAX_PAGES_PER_CALL]
            lookup_key = self._test_key or hashlib.sha256(
                b"".join(chunk)
            ).hexdigest()[:16]
            rows = get_llm_adapter().extract_rows(
                text="",
                lookup_key=lookup_key,
                kind=ctx.kind,
                images=chunk,
            )
            all_rows.extend(rows)

        rows = [ExtractedRowData(**self._coerce(r)) for r in all_rows]

        return ExtractedFileResult(
            rows=rows,
            needs_review=True,  # MANDATORY per spec §5
            extraction_engine="gemini-vision",
            page_count=page_count,
            warnings=[],
        )

    def _to_png_pages(self, file_bytes: bytes) -> list[bytes]:
        """Return a list of PNG bytes — one per page (PDF) or one entry (image)."""
        if file_bytes[:4] == b"%PDF":
            return self._pdf_to_pngs(file_bytes)
        return [self._normalize_image_to_png(file_bytes)]

    @staticmethod
    def _pdf_to_pngs(file_bytes: bytes) -> list[bytes]:
        out: list[bytes] = []
        pdf = pdfium.PdfDocument(file_bytes)
        for page in pdf:
            bitmap = page.render(scale=_PDF_DPI / 72)
            pil = bitmap.to_pil()
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            out.append(buf.getvalue())
        return out

    @staticmethod
    def _normalize_image_to_png(file_bytes: bytes) -> bytes:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _coerce(d: dict[str, Any]) -> dict[str, Any]:
        return PdfBornDigitalEngine._coerce(d)
