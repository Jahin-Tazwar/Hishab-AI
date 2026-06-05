"""Rendering tests for the audit_defense_pack .docx."""
from __future__ import annotations

import io
from uuid import uuid4

import pytest
from docx import Document

from app.working_papers.rendering import render_docx

TENANT_META = {"firm_name": "Rahman & Co.", "icab_reg_no": "ICAB-F-0421",
               "address": "Dhaka", "email": "a@b.bd", "phone": "+880"}
DOC_META = {"reference": "WP-AAAA1111-202604", "generated_on": "2026-06-06",
            "prepared_by": "Staff", "reviewed_by": "Partner FCA", "status": "finalized"}


def _payload():
    return {
        "kind": "audit_defense_pack", "recipe_version": "v1",
        "client_id": str(uuid4()), "client_name": "Padma Textiles Ltd",
        "client_bin": "001234567-0101", "client_tin": "555000111",
        "notice_id": str(uuid4()),
        "notice": {
            "notice_no": "NBR/4471", "notice_date": "2026-05-20",
            "notice_type": "input_vat_mismatch",
            "period_start": "2026-04-01", "period_end": "2026-04-30",
            "taxpayer_bin": "001234567-0101", "taxpayer_tin": "555000111",
            "alleged_itc_claimed_bdt": "2847500.00",
            "alleged_itc_allowed_bdt": "2412000.00",
            "alleged_shortfall_bdt": "435500.00"},
        "reconciliation_id": str(uuid4()),
        "reconciled_position": {
            "kind": "at_risk_itc_schedule", "recipe_version": "v1",
            "client_id": str(uuid4()), "client_name": "Padma Textiles Ltd",
            "client_bin": "001234567-0101", "reconciliation_id": str(uuid4()),
            "period_start": "2026-04-01", "period_end": "2026-04-30",
            "summary": {"total_vat_claimed_bdt": "2847500.00",
                        "safe_itc_bdt": "2412000.00", "at_risk_itc_bdt": "435500.00",
                        "total_lines": 128, "at_risk_line_count": 2,
                        "supplier_count_at_risk": 1},
            "supplier_groups": [{
                "supplier_name": "Meghna", "supplier_bin": "0044",
                "total_vat_at_risk_bdt": "435500.00", "line_count": 1,
                "lines": [{"line_id": str(uuid4()), "invoice_no": "MP-7798",
                           "invoice_date": "2026-04-22",
                           "taxable_amount_bdt": "2903333.33",
                           "vat_amount_bdt": "435500.00",
                           "sf_vat_amount_bdt": None, "vat_variance_bdt": "435500.00",
                           "discrepancy_reason": "supplier did not file",
                           "date_off_by_days": None, "match_status": "no_match",
                           "match_score": None, "ca_override": None, "ca_notes": None,
                           "recommended_action": "chase_supplier"}]}]},
        "override_log": [{"supplier_name": "Meghna", "supplier_bin": "0044",
                          "invoice_no": "MP-7798", "ca_override": "disputed",
                          "ca_notes": "Awaiting amended Mushak 6.3"}],
        "drafted_reply": {"language": "bn", "status": "finalized",
                          "body_html": "<p>আমরা আপত্তি জানাই।</p>",
                          "citations": [{"source_ref": "Rule 21", "snippet": "ITC docs"}]},
        "evidence_index": [
            {"ref": "E-01", "document_id": str(uuid4()), "filename": "pr.xlsx",
             "source_type": "purchase_register", "bucket": "recon-files",
             "storage_path": "t/c/pr.xlsx"},
            {"ref": "E-02", "document_id": None, "filename": "notice.pdf",
             "source_type": "nbr_notice", "bucket": "notices",
             "storage_path": "t/c/notice.pdf"}],
    }


def _all_text(doc):
    paras = "\n".join(p.text for p in doc.paragraphs)
    cells = "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    return paras + "\n" + cells


def test_render_audit_pack_has_all_sections():
    out = render_docx(payload=_payload(), notes_html="", tenant=TENANT_META, meta=DOC_META)
    text = _all_text(Document(io.BytesIO(out)))
    assert "Audit Defense Pack" in text
    assert "WP-AAAA1111-202604" in text
    assert "Padma Textiles Ltd" in text
    assert "NBR/4471" in text
    assert "4,35,500.00" in text
    assert "At-risk ITC (BDT)" in text
    assert "Decision" in text and "Awaiting amended Mushak 6.3" in text
    assert "আমরা আপত্তি জানাই।" in text
    assert "Rule 21" in text
    assert "Evidence" in text and "E-01" in text and "pr.xlsx" in text


def test_render_audit_pack_degrades_without_recon_or_reply():
    p = _payload()
    p["reconciled_position"] = None
    p["override_log"] = []
    p["drafted_reply"] = None
    out = render_docx(payload=p, notes_html="", tenant=TENANT_META, meta=DOC_META)
    text = _all_text(Document(io.BytesIO(out)))
    assert "Audit Defense Pack" in text
    assert "No reconciliation is linked" in text
    assert "No reply has been drafted" in text
