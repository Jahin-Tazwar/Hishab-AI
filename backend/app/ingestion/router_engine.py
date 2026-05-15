"""MIME → engine name router.

Pure logic; no I/O. Engine selection is deterministic from
(MIME, file bytes, kind). Selection happens BEFORE storage upload so
we record the chosen engine on `ingestion_files.engine` immediately.
"""
from __future__ import annotations

from app.ingestion.engines.pandas_canonical import PandasCanonicalEngine
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.exceptions import UnsupportedFileTypeError
from app.ingestion.schemas import JobKind


_XLSX_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "text/tab-separated-values",
}

_PDF_MIMES = {"application/pdf"}

_IMAGE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/tiff",
    "image/webp", "image/heic", "image/heif",
}


def _kind_enum(kind: str | JobKind) -> JobKind:
    return kind if isinstance(kind, JobKind) else JobKind(kind)


def select_engine_name(
    *, file_bytes: bytes, mime: str, kind: str | JobKind,
    filename: str = "<unknown>",
) -> str:
    k = _kind_enum(kind)

    if mime in _XLSX_MIMES:
        canonical = PandasCanonicalEngine()
        try:
            headers = canonical.headers_from_bytes(file_bytes)
        except Exception:
            return "pandas+llm-mapper"
        if canonical.handles_headers(headers, k):
            return "pandas"
        return "pandas+llm-mapper"

    if mime in _PDF_MIMES:
        bd = PdfBornDigitalEngine()
        try:
            return "pdfplumber+llm" if bd.has_extractable_text(file_bytes) else "gemini-vision"
        except Exception:
            return "gemini-vision"

    if mime in _IMAGE_MIMES:
        return "gemini-vision"

    raise UnsupportedFileTypeError(filename=filename, mime=mime)
