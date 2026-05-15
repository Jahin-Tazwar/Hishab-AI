"""MIME router tests — pure logic, no DB, no LLM."""
from app.ingestion.router_engine import select_engine_name


def _xlsx_bytes_with_headers(headers: list[str]) -> bytes:
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append(headers)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_canonical_xlsx_routes_to_pandas():
    headers = ["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"]
    name = select_engine_name(
        file_bytes=_xlsx_bytes_with_headers(headers),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        kind="purchase_register",
    )
    assert name == "pandas"


def test_non_canonical_xlsx_routes_to_mapper():
    headers = ["বিল নং", "BIN", "তারিখ", "মোট", "VAT"]
    name = select_engine_name(
        file_bytes=_xlsx_bytes_with_headers(headers),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        kind="purchase_register",
    )
    assert name == "pandas+llm-mapper"


def test_pdf_with_text_routes_to_borndigital():
    from pathlib import Path
    p = Path("tests/ingestion/fixtures/mushak_6.3_borndigital.pdf").read_bytes()
    name = select_engine_name(
        file_bytes=p, mime="application/pdf", kind="purchase_register",
    )
    assert name == "pdfplumber+llm"


def test_scanned_pdf_routes_to_vision():
    from pathlib import Path
    p = Path("tests/ingestion/fixtures/mushak_6.3_scan.pdf").read_bytes()
    name = select_engine_name(
        file_bytes=p, mime="application/pdf", kind="purchase_register",
    )
    assert name == "gemini-vision"


def test_image_routes_to_vision():
    from pathlib import Path
    p = Path("tests/ingestion/fixtures/phone_photo_invoice.jpg").read_bytes()
    name = select_engine_name(
        file_bytes=p, mime="image/jpeg", kind="purchase_register",
    )
    assert name == "gemini-vision"


def test_unsupported_mime_raises():
    import pytest
    from app.ingestion.exceptions import UnsupportedFileTypeError
    with pytest.raises(UnsupportedFileTypeError):
        select_engine_name(
            file_bytes=b"hi", mime="application/zip",
            kind="purchase_register",
        )
