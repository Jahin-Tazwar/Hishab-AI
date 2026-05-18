"""Notice parser — turns raw upload bytes into a ParsedNotice.

Reuses `VisionEngine._normalize_image_to_png` so we get the same
downscaling discipline (longest edge ≤ 2048px, payload ≤ 7MB) that
the ingestion path already uses. For PDFs we render each page with
pypdfium2 and pass all pages to a single LLM call.
"""
from __future__ import annotations

import hashlib
import io
from typing import Optional

import pypdfium2 as pdfium

from app.ingestion.engines.vision import VisionEngine
from app.notices.exceptions import NoticeUnsupportedTypeError
from app.notices.llm import NoticeLLMAdapter
from app.notices.schemas import ParsedNotice

_normalize_image_to_png = VisionEngine._normalize_image_to_png

_IMAGE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/tiff",
    "image/webp", "image/heic", "image/heif",
}
_PDF_MIMES = {"application/pdf"}


def _pdf_to_pngs(file_bytes: bytes) -> list[bytes]:
    out: list[bytes] = []
    pdf = pdfium.PdfDocument(file_bytes)
    for page in pdf:
        bitmap = page.render(scale=200 / 72)
        pil = bitmap.to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        out.append(_normalize_image_to_png(buf.getvalue()))
    return out


def _to_images(file_bytes: bytes, mime: str, filename: str = "<notice>") -> list[bytes]:
    if mime in _PDF_MIMES or file_bytes[:4] == b"%PDF":
        return _pdf_to_pngs(file_bytes)
    if mime in _IMAGE_MIMES:
        return [_normalize_image_to_png(file_bytes)]
    raise NoticeUnsupportedTypeError(filename=filename, mime=mime)


def parse_notice(
    file_bytes: bytes,
    *,
    mime: str,
    adapter: NoticeLLMAdapter,
    filename: str = "<notice>",
    lookup_key_override: Optional[str] = None,
) -> ParsedNotice:
    """Run the Gemini Vision parse on the notice bytes.

    `lookup_key_override` is only used by tests pinning to a canned response.
    """
    images = _to_images(file_bytes, mime, filename=filename)
    lookup_key = lookup_key_override or hashlib.sha256(
        b"".join(images)
    ).hexdigest()[:16]
    return adapter.parse_notice(images=images, lookup_key=lookup_key)
