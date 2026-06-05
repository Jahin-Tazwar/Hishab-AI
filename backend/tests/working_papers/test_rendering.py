"""Rendering tests for the at-risk ITC schedule .docx; .pdf gated on soffice."""
from __future__ import annotations

import io
import shutil
from uuid import uuid4

import pytest
from docx import Document

from app.working_papers.rendering import (
    PdfRendererUnavailableError,
    _fmt_bdt,
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
                        "sf_taxable_amount_bdt": None,
                        "sf_vat_amount_bdt": None,
                        "vat_variance_bdt": "750.00",
                        "discrepancy_reason": None,
                        "date_off_by_days": None,
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
                        "taxable_amount_bdt": "300000.00",
                        "vat_amount_bdt": "45000.00",
                        "sf_taxable_amount_bdt": "270000.00",
                        "sf_vat_amount_bdt": "40500.00",
                        "vat_variance_bdt": "4500.00",
                        "discrepancy_reason": "vat amount differs",
                        "date_off_by_days": 0,
                        "match_status": "partial",
                        "match_score": "0.72",
                        "ca_override": "disputed",
                        "ca_notes": "Pending VAT cert",
                        "recommended_action": "reverse_claim",
                    },
                ],
                "total_vat_at_risk_bdt": "45000.00",
                "line_count": 1,
            },
        ],
    }


TENANT_META = {
    "firm_name": "Demo CA Co.",
    "firm_name_bn": "ডেমো সিএ কোং",
    "icab_reg_no": "ICAB-1234",
    "address": "Dhaka, Bangladesh",
    "email": "info@demo-ca.com",
    "phone": "+8801700000000",
}

DOC_META = {
    "reference": "WP-1A2B3C4D-202604",
    "generated_on": "2026-06-06",
    "prepared_by": "Junior Staff",
    "reviewed_by": "Partner Sahib",
    "status": "finalized",
}


def _all_text(doc) -> str:
    paras = "\n".join(p.text for p in doc.paragraphs)
    cells = "\n".join(
        cell.text for t in doc.tables for row in t.rows for cell in row.cells
    )
    return paras + "\n" + cells


# ── F4: number formatting ─────────────────────────────────────────────────


def test_fmt_bdt_groups_south_asian():
    assert _fmt_bdt("50000.00") == "50,000.00"
    assert _fmt_bdt("12345678.5") == "1,23,45,678.50"
    assert _fmt_bdt("999.9") == "999.90"
    assert _fmt_bdt(None) == ""
    assert _fmt_bdt("-4500") == "-4,500.00"


def test_render_docx_formats_amounts_with_grouping():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = _all_text(doc)
    assert "50,000.00" in text   # summary total VAT claimed, grouped
    assert "45,000.00" in text   # Bravo supplier total, grouped
    assert "40,500.00" in text   # Bravo supplier-reported VAT, grouped
    assert "50000.00" not in text  # ungrouped form must be gone


# ── F4: totals / footing ──────────────────────────────────────────────────


def test_render_docx_has_grand_total_at_risk():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = _all_text(doc)
    assert "Total at-risk ITC" in text
    # 750 + 45000 = 45,750.00
    assert "45,750.00" in text


# ── F5: document identity + sign-off ──────────────────────────────────────


def test_render_docx_includes_identity_and_signoff_block():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = _all_text(doc)
    assert "WP-1A2B3C4D-202604" in text     # reference
    assert "2026-06-06" in text             # generated-on
    assert "Prepared by" in text
    assert "Junior Staff" in text
    assert "Reviewed by" in text
    assert "Partner Sahib" in text
    assert "ICAB-1234" in text              # firm registration on letterhead


def test_render_docx_signoff_shows_pending_when_no_reviewer():
    meta = {**DOC_META, "reviewed_by": None, "status": "draft"}
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=meta)
    doc = Document(io.BytesIO(out))
    text = _all_text(doc)
    assert "Reviewed by" in text
    assert "— pending —" in text


# ── F5: page numbers ──────────────────────────────────────────────────────


def test_render_docx_has_page_number_footer():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    footer_xml = doc.sections[0].footer._element.xml
    assert "PAGE" in footer_xml  # a PAGE field is present in the footer


# ── F4: multi-paragraph CA commentary must not collapse ───────────────────


def test_render_docx_preserves_multiple_note_paragraphs():
    notes = "<p>First paragraph of review.</p><p>Second distinct paragraph.</p>"
    out = render_docx(payload=_payload(), notes_html=notes, tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    para_texts = [p.text for p in doc.paragraphs]
    assert "First paragraph of review." in para_texts
    assert "Second distinct paragraph." in para_texts  # separate paragraph, not merged


def test_render_docx_renders_note_list_items():
    notes = "<ul><li>First bullet.</li><li>Second bullet.</li></ul>"
    out = render_docx(payload=_payload(), notes_html=notes, tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "First bullet." in text
    assert "Second bullet." in text


# ── existing structural / evidence coverage (kept) ────────────────────────


def test_render_docx_contains_client_summary_and_supplier_groups():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = _all_text(doc)
    assert "Demo CA Co." in text
    assert "At-Risk Input Tax Credit Schedule" in text
    assert "Demo Client Ltd" in text
    assert "Alpha Industries" in text
    assert "Bravo Traders" in text
    # F3: supplier-side comparison reaches the export
    assert "Claimed VAT (BDT)" in text
    assert "Supplier VAT (BDT)" in text
    assert "Variance (BDT)" in text
    assert "not filed" in text          # Alpha's no_match line
    assert "40,500.00" in text          # Bravo's supplier-reported VAT


def test_render_docx_includes_ca_commentary_when_notes_provided():
    notes = "<p>This is the CA review note.</p>"
    out = render_docx(payload=_payload(), notes_html=notes, tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "CA commentary" in text
    assert "This is the CA review note." in text


def test_render_docx_omits_ca_commentary_when_notes_empty():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    doc = Document(io.BytesIO(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "CA commentary" not in text


def test_render_docx_rejects_unknown_kind():
    bad = _payload()
    bad["kind"] = "unknown_kind"
    with pytest.raises(ValueError):
        render_docx(payload=bad, notes_html="", tenant=TENANT_META, meta=DOC_META)


def test_render_docx_works_without_meta():
    """meta is optional — renderer falls back to neutral defaults."""
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META)
    doc = Document(io.BytesIO(out))
    assert "At-Risk Input Tax Credit Schedule" in _all_text(doc)


@pytest.mark.skipif(
    shutil.which("soffice") is None and shutil.which("soffice.exe") is None,
    reason="LibreOffice (soffice) not on PATH; PDF rendering unavailable",
)
def test_render_pdf_emits_pdf_bytes():
    docx_bytes = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    pdf_bytes = render_pdf(docx_bytes)
    assert pdf_bytes[:4] == b"%PDF"


def test_render_pdf_raises_when_soffice_missing(monkeypatch):
    monkeypatch.setattr(
        "app.notices.rendering._soffice_path", lambda: None,
    )
    with pytest.raises(PdfRendererUnavailableError):
        render_pdf(b"not a real docx")
