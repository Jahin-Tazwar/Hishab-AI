"""Render a working paper to .docx and .pdf.

Today supports `at_risk_itc_schedule`. Each recipe-kind has a dedicated
docx builder. PDF rendering reuses `app.notices.rendering.render_pdf`
which already handles LibreOffice headless conversion.
"""
from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

from docx import Document
from docx.shared import Pt

from app.notices.rendering import PdfRendererUnavailableError, render_pdf


def render_docx(*, payload: dict[str, Any], notes_html: str, tenant: dict[str, Any]) -> bytes:
    kind = payload.get("kind")
    if kind == "at_risk_itc_schedule":
        return _render_at_risk_itc_schedule(payload, notes_html, tenant)
    raise ValueError(f"Unknown working paper kind: {kind!r}")


def _render_at_risk_itc_schedule(payload: dict, notes_html: str, tenant: dict) -> bytes:
    doc = Document()
    # Letterhead
    p = doc.add_paragraph()
    r = p.add_run(tenant.get("firm_name", "Chartered Accountants"))
    r.bold = True
    r.font.size = Pt(14)
    if tenant.get("address"):
        ap = doc.add_paragraph(tenant["address"])
        ap.runs[0].font.size = Pt(10)
    doc.add_paragraph("")

    # Title
    t = doc.add_paragraph()
    tr = t.add_run("At-Risk Input Tax Credit Schedule")
    tr.bold = True
    tr.font.size = Pt(16)

    # Subhead
    sh = doc.add_paragraph()
    sh.add_run(
        f"Client: {payload['client_name']}"
        + (f" (BIN {payload['client_bin']})" if payload.get("client_bin") else "")
    )
    sh2 = doc.add_paragraph()
    sh2.add_run(f"Period: {payload['period_start']} to {payload['period_end']}")

    # Summary
    doc.add_paragraph("")
    sh3 = doc.add_paragraph()
    sh3.add_run("Summary").bold = True
    s = payload["summary"]
    summary_table = doc.add_table(rows=4, cols=2)
    summary_table.style = "Light List"
    pairs = [
        ("Total VAT claimed (BDT)", str(s["total_vat_claimed_bdt"])),
        ("Safe ITC (BDT)", str(s["safe_itc_bdt"])),
        ("At-risk ITC (BDT)", str(s["at_risk_itc_bdt"])),
        (
            "Lines flagged",
            f"{s['at_risk_line_count']} of {s['total_lines']} "
            f"(across {s['supplier_count_at_risk']} supplier(s))",
        ),
    ]
    for i, (k, v) in enumerate(pairs):
        summary_table.rows[i].cells[0].text = k
        summary_table.rows[i].cells[1].text = v

    # Per-supplier detail
    doc.add_paragraph("")
    sh4 = doc.add_paragraph()
    sh4.add_run("At-risk lines by supplier").bold = True

    for grp in payload["supplier_groups"]:
        gh = doc.add_paragraph()
        gr = gh.add_run(
            f"{grp.get('supplier_name') or '(unknown supplier)'}"
            + (f" — BIN {grp['supplier_bin']}" if grp.get('supplier_bin') else "")
            + f"   ·   VAT at risk: BDT {grp['total_vat_at_risk_bdt']}"
            + f"   ·   {grp['line_count']} line(s)"
        )
        gr.bold = True

        table = doc.add_table(rows=1 + len(grp["lines"]), cols=6)
        table.style = "Light List"
        hdr = table.rows[0].cells
        hdr[0].text = "Invoice no"
        hdr[1].text = "Invoice date"
        hdr[2].text = "Taxable (BDT)"
        hdr[3].text = "VAT (BDT)"
        hdr[4].text = "Match"
        hdr[5].text = "Recommended action"
        for i, line in enumerate(grp["lines"], start=1):
            row = table.rows[i].cells
            row[0].text = str(line.get("invoice_no") or "")
            row[1].text = str(line.get("invoice_date") or "")
            row[2].text = str(line.get("taxable_amount_bdt") or "")
            row[3].text = str(line.get("vat_amount_bdt") or "")
            override = line.get("ca_override")
            ms = line["match_status"]
            row[4].text = ms if not override else f"{ms} ({override})"
            row[5].text = (line["recommended_action"] or "").replace("_", " ")

    # CA commentary (notes_html is bleached/sanitized at edit time; we strip
    # tags here for plain-text docx insertion to keep this simple — a future
    # iteration can do proper HTML→docx walking like notices/rendering does)
    if notes_html and notes_html.strip():
        doc.add_paragraph("")
        nh = doc.add_paragraph()
        nh.add_run("CA commentary").bold = True
        from lxml import html as lxml_html
        try:
            text = lxml_html.fromstring(f"<div>{notes_html}</div>").text_content()
        except Exception:
            text = notes_html
        for para in (p.strip() for p in text.split("\n")):
            if para:
                doc.add_paragraph(para)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


__all__ = ["render_docx", "render_pdf", "PdfRendererUnavailableError"]
