"""Rendering tests for the at-risk ITC schedule .docx; .pdf gated on soffice."""
from __future__ import annotations

import io
import shutil
from uuid import uuid4

import pytest
from docx import Document

from app.working_papers.rendering import (
    PdfRendererUnavailableError,
    render_docx,
    render_pdf,
)


def _payload() -> dict:
    return {
        "kind": "at_risk_itc_schedule",
        "recipe_version": "v1",
        "client_id": str(uuid4()),
        "client_name": "Demo Client Ltd",
        "client_bin": "987654321",
        "reconciliation_id": str(uuid4()),
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "summary": {
            "total_vat_claimed_bdt": "50000.00",
            "safe_itc_bdt": "40000.00",
            "at_risk_itc_bdt": "10000.00",
            "total_lines": 10,
            "at_risk_line_count": 3,
            "supplier_count_at_risk": 2,
        },
        "supplier_groups": [
            {
                "supplier_name": "Alpha Industries",
                "supplier_bin": "111111111",
                "lines": [
                    {
                        "line_id": str(uuid4()),
                        "supplier_name": "Alpha Industries",
                        "supplier_bin": "111111111",
                        "invoice_no": "INV-1001",
                        "invoice_date": "2026-04-05",
                        "taxable_amount_bdt": "5000.00",
                        "vat_amount_bdt": "750.00",
                        "match_status": "no_match",
                        "match_score": None,
                        "ca_override": None,
                        "ca_notes": None,
                        "recommended_action": "chase_supplier",
                    },
                ],
                "total_vat_at_risk_bdt": "750.00",
                "line_count": 1,
            },
            {
                "supplier_name": "Bravo Traders",
                "supplier_bin": "222222222",
                "lines": [
                    {
                        "line_id": str(uuid4()),
                        "supplier_name": "Bravo Traders",
                        "supplier_bin": "222222222",
                        "invoice_no": "INV-2002",
                        "invoice_date": "2026-04-10",
                        "taxable_amount_bdt": "3000.00",
                        "vat_amount_bdt": "450.00",
                        "match_status": "partial",
                        "match_score": "0.72",
                        "ca_override": "disputed",
                        "ca_notes": "Pending VAT cert",
                        "recommended_action": "partner_review",
                    },
                ],
                "total_vat_at_risk_bdt": "450.00",
                "line_count": 1,
            },
        ],
    }


TENANT_META = {"firm_name": "Demo CA Co.", "address": "Dhaka, Bangladesh"}


def test_render_docx_contains_client_summary_and_supplier_groups():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META)
    doc = Document(io.BytesIO(out))
    text_all = "\n".join(p.text for p in doc.paragraphs)
    assert "Demo CA Co." in text_all
    assert "At-Risk Input Tax Credit Schedule" in text_all
    assert "Demo Client Ltd" in text_all
    assert "Alpha Industries" in text_all
    assert "Bravo Traders" in text_all
    # Summary table is 4 rows × 2 cols + per-supplier tables (1+N rows)
    # First table is summary.
    summary_table = doc.tables[0]
    assert len(summary_table.rows) == 4
    summary_text = "\n".join(
        cell.text for row in summary_table.rows for cell in row.cells
    )
    assert "Total VAT claimed (BDT)" in summary_text
    assert "50000.00" in summary_text
    assert "10000.00" in summary_text


def test_render_docx_includes_ca_commentary_when_notes_provided():
    notes = "<p>This is the CA review note.</p>"
    out = render_docx(payload=_payload(), notes_html=notes, tenant=TENANT_META)
    doc = Document(io.BytesIO(out))
    text_all = "\n".join(p.text for p in doc.paragraphs)
    assert "CA commentary" in text_all
    assert "This is the CA review note." in text_all


def test_render_docx_omits_ca_commentary_when_notes_empty():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META)
    doc = Document(io.BytesIO(out))
    text_all = "\n".join(p.text for p in doc.paragraphs)
    assert "CA commentary" not in text_all


def test_render_docx_rejects_unknown_kind():
    bad = _payload()
    bad["kind"] = "unknown_kind"
    with pytest.raises(ValueError):
        render_docx(payload=bad, notes_html="", tenant=TENANT_META)


@pytest.mark.skipif(
    shutil.which("soffice") is None and shutil.which("soffice.exe") is None,
    reason="LibreOffice (soffice) not on PATH; PDF rendering unavailable",
)
def test_render_pdf_emits_pdf_bytes():
    docx_bytes = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META)
    pdf_bytes = render_pdf(docx_bytes)
    assert pdf_bytes[:4] == b"%PDF"


def test_render_pdf_raises_when_soffice_missing(monkeypatch):
    monkeypatch.setattr(
        "app.notices.rendering._soffice_path", lambda: None,
    )
    with pytest.raises(PdfRendererUnavailableError):
        render_pdf(b"not a real docx")
