"""Recipe tests for audit_defense_pack — fake Supabase, no live DB."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.working_papers.recipes.audit_defense_pack import AuditDefensePackRecipe

TENANT = uuid4()
NOTICE = uuid4()
RECON = uuid4()
CLIENT = uuid4()
PR_DOC = uuid4()
SF_DOC = uuid4()


def _notice_row(linked=True):
    return {
        "id": str(NOTICE), "tenant_id": str(TENANT), "client_id": str(CLIENT),
        "notice_no": "NBR/4471", "notice_date": "2026-05-20",
        "notice_type": "input_vat_mismatch",
        "period_start": "2026-04-01", "period_end": "2026-04-30",
        "taxpayer_bin": "001234567-0101", "taxpayer_tin": "555000111",
        "alleged_itc_claimed_bdt": "2847500.00",
        "alleged_itc_allowed_bdt": "2412000.00",
        "alleged_shortfall_bdt": "435500.00",
        "storage_path": "t/c/notice.pdf", "original_filename": "notice.pdf",
        "linked_reconciliation_id": str(RECON) if linked else None,
    }


def _client_row():
    return {"id": str(CLIENT), "name": "Padma Textiles Ltd",
            "bin": "001234567-0101", "tin": "555000111"}


def _recon_row():
    return {
        "id": str(RECON), "client_id": str(CLIENT), "tenant_id": str(TENANT),
        "period_start": "2026-04-01", "period_end": "2026-04-30",
        "total_vat_claimed_bdt": "2847500.00", "safe_itc_bdt": "2412000.00",
        "at_risk_itc_bdt": "435500.00",
        "purchase_register_doc_id": str(PR_DOC),
        "supplier_data_doc_id": str(SF_DOC),
    }


def _line(invoice, status="no_match", vat="100", override=None, notes=None,
          supplier="ACME", bin_="111"):
    return {
        "id": str(uuid4()), "pr_invoice_no": invoice, "pr_supplier_bin": bin_,
        "pr_supplier_name": supplier, "pr_invoice_date": "2026-04-05",
        "pr_taxable_amount_bdt": "1000", "pr_vat_amount_bdt": vat,
        "sf_vat_amount_bdt": None, "sf_taxable_amount_bdt": None,
        "match_status": status, "match_score": None,
        "discrepancy_flags": {"reason": None, "date_off_by_days": None},
        "ca_override": override, "ca_notes": notes,
    }


def _draft_row():
    return {"language": "bn", "status": "finalized",
            "body_html": "<p>reply</p>", "citations": [{"source_ref": "Rule 21"}],
            "finalized_at": "2026-06-01T00:00:00Z", "updated_at": "2026-06-01T00:00:00Z"}


def _doc(did, fname, dtype):
    return {"id": str(did), "original_filename": fname,
            "storage_path": f"t/c/{fname}", "doc_type": dtype}


class _Tbl:
    def __init__(self, name, store):
        self.name, self.store, self._f, self._single = name, store, {}, False
        self._range = None

    def select(self, *_a, **_k): return self
    def eq(self, k, v): self._f[k] = v; return self
    def in_(self, k, v): self._f[k] = v; return self
    def order(self, *_a, **_k): return self
    def range(self, s, e): self._range = (s, e); return self
    def limit(self, *_a, **_k): return self
    def single(self): self._single = True; return self

    def execute(self):
        data = self.store.get(self.name)
        if callable(data):
            data = data(self._f)
        if isinstance(data, list) and self._range is not None:
            s, e = self._range
            data = data[s:e + 1]
        return SimpleNamespace(data=data)


class _SB:
    def __init__(self, store): self.store = store
    def table(self, n): return _Tbl(n, self.store)


@pytest.fixture
def loop():
    lo = asyncio.new_event_loop(); asyncio.set_event_loop(lo)
    yield lo; lo.close()


def _patch(monkeypatch, *, store):
    sb = _SB(store)
    # Both this recipe and the reused AtRiskItcScheduleRecipe read get_supabase_admin.
    monkeypatch.setattr(
        "app.working_papers.recipes.audit_defense_pack.get_supabase_admin", lambda: sb)
    monkeypatch.setattr(
        "app.working_papers.recipes.at_risk_itc.get_supabase_admin", lambda: sb)


def test_compose_assembles_all_sections(monkeypatch, loop):
    lines = [
        _line("NM1", "no_match", "300000"),
        _line("P1", "partial", "135500", override="disputed", notes="amend pending"),
        _line("EX1", "exact", "10000"),  # safe, excluded from at-risk & override log
    ]
    store = {
        "notices": _notice_row(),
        "clients": _client_row(),
        "vat_reconciliations": _recon_row(),
        "recon_line_items": lines,
        "notice_drafts": [_draft_row()],
        "documents": lambda f: [
            d for d in [_doc(PR_DOC, "pr.xlsx", "purchase_register"),
                        _doc(SF_DOC, "sf.xlsx", "supplier_export")]
            if d["id"] == f.get("id")],
    }
    _patch(monkeypatch, store=store)
    out = loop.run_until_complete(
        AuditDefensePackRecipe().compose(tenant_id=TENANT, notice_id=NOTICE))

    assert out["kind"] == "audit_defense_pack"
    assert out["client_name"] == "Padma Textiles Ltd"
    assert out["notice"]["alleged_shortfall_bdt"] == "435500.00"
    # reconciled position reused from at-risk recipe, ties to recon header
    assert out["reconciled_position"]["summary"]["at_risk_itc_bdt"] == "435500.00"
    # override log only includes overridden lines
    assert [e["invoice_no"] for e in out["override_log"]] == ["P1"]
    # drafted reply
    assert out["drafted_reply"]["body_html"] == "<p>reply</p>"
    # evidence index: PR + supplier + notice file
    refs = {(e["source_type"], e["bucket"]) for e in out["evidence_index"]}
    assert ("purchase_register", "recon-files") in refs
    assert ("supplier_export", "recon-files") in refs
    assert ("nbr_notice", "notices") in refs
    assert out["evidence_index"][0]["ref"] == "E-01"


def test_compose_degrades_without_linked_recon(monkeypatch, loop):
    store = {
        "notices": _notice_row(linked=False),
        "clients": _client_row(),
        "notice_drafts": [],   # no draft yet
    }
    _patch(monkeypatch, store=store)
    out = loop.run_until_complete(
        AuditDefensePackRecipe().compose(tenant_id=TENANT, notice_id=NOTICE))
    assert out["reconciled_position"] is None
    assert out["override_log"] == []
    assert out["drafted_reply"] is None
    # only the notice file is evidence
    assert [e["source_type"] for e in out["evidence_index"]] == ["nbr_notice"]
