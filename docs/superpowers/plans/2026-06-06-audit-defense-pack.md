# Audit Defense Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new Working Papers recipe `audit_defense_pack` that composes a per-NBR-notice rebuttal binder (notice summary, reconciled position, CA override log, drafted reply + citations, evidence index), exports it as a `.docx`, and offers an evidence-bundle ZIP.

**Architecture:** A new recipe in the existing `working_papers` package. It derives everything from a `notice_id`, reusing `AtRiskItcScheduleRecipe` for the reconciled-position section (recipe-composes-recipe). Structured content is snapshotted into `composed_json`; evidence binaries are referenced by `(bucket, storage_path)` and fetched from Storage only when building the ZIP. No new module — one recipe + a renderer branch + a ZIP endpoint + a kind-specific frontend view.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic 2 · Supabase (PostgREST + Storage) · python-docx · React 18 + TypeScript + Zod + TanStack Query.

**Spec:** `docs/superpowers/specs/2026-06-06-audit-defense-pack-design.md`

**Conventions in this codebase (read before starting):**
- Recipes are pure: `async compose(*, tenant_id, **inputs) -> dict`. Registered in `backend/app/working_papers/recipes/__init__.py`.
- DB access via `app.database.get_supabase_admin()`, every query filtered by `tenant_id`, sync calls wrapped in `await asyncio.to_thread(...)`.
- Money fields are `Decimal` in models, serialized to strings via `@field_serializer(..., when_used="json")`.
- Tests use a fake-Supabase harness (see `backend/tests/working_papers/test_recipe_at_risk_itc.py`); event loop via the `loop` fixture.
- Buckets: recon source files → `recon-files` (doc_types `purchase_register`, `supplier_export`); notice files → `notices`.
- Run backend tests from `backend/`: `python -m pytest`. Run frontend from `frontend/`: `npx vitest run` and `npm run build`.

---

## Task 1: Migration 0023 — enum value + notice_id column

**Files:**
- Create: `migrations/0023_audit_defense_pack.sql`
- Apply: via Supabase MCP `apply_migration` (project `qlrqbqisavkfxywkiuca`)

- [ ] **Step 1: Write the migration file**

```sql
-- 0023_audit_defense_pack.sql
-- Adds the audit_defense_pack working-paper kind and a nullable notice_id
-- link so a pack can be tied to (and queried by) the NBR notice it defends.

ALTER TYPE working_paper_kind ADD VALUE IF NOT EXISTS 'audit_defense_pack';

ALTER TABLE working_papers
  ADD COLUMN IF NOT EXISTS notice_id uuid REFERENCES notices(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_working_papers_tenant_notice
  ON working_papers (tenant_id, notice_id)
  WHERE notice_id IS NOT NULL;
```

- [ ] **Step 2: Apply via MCP**

Use `mcp__<supabase>__apply_migration` with `project_id=qlrqbqisavkfxywkiuca`, `name=audit_defense_pack`, `query=<file contents>`.
Expected: `{"success": true}`.

- [ ] **Step 3: Verify enum + column exist**

Use `execute_sql`:
```sql
select unnest(enum_range(NULL::working_paper_kind))::text as kind;
select column_name from information_schema.columns
 where table_name='working_papers' and column_name='notice_id';
```
Expected: kinds include `audit_defense_pack`; one row `notice_id`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0023_audit_defense_pack.sql
git commit -m "feat(working-papers): migration for audit_defense_pack kind + notice_id"
```

---

## Task 2: Payload schemas

**Files:**
- Modify: `backend/app/working_papers/schemas.py`
- Test: `backend/tests/working_papers/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/working_papers/test_schemas.py`:

```python
def test_audit_defense_pack_payload_round_trips():
    from app.working_papers.schemas import AuditDefensePackPayload
    from uuid import uuid4

    payload = {
        "kind": "audit_defense_pack",
        "recipe_version": "v1",
        "client_id": str(uuid4()),
        "client_name": "Padma Textiles Ltd",
        "client_bin": "001234567-0101",
        "client_tin": "555000111",
        "notice_id": str(uuid4()),
        "notice": {
            "notice_no": "NBR/VAT/2026/4471",
            "notice_date": "2026-05-20",
            "notice_type": "input_vat_mismatch",
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "taxpayer_bin": "001234567-0101",
            "taxpayer_tin": "555000111",
            "alleged_itc_claimed_bdt": "2847500.00",
            "alleged_itc_allowed_bdt": "2412000.00",
            "alleged_shortfall_bdt": "435500.00",
        },
        "reconciliation_id": str(uuid4()),
        "reconciled_position": None,
        "override_log": [
            {"supplier_name": "Meghna", "supplier_bin": "0044",
             "invoice_no": "MP-7798", "ca_override": "disputed",
             "ca_notes": "Awaiting amended Mushak 6.3"},
        ],
        "drafted_reply": {
            "language": "bn", "status": "finalized",
            "body_html": "<p>reply</p>", "citations": [{"source_ref": "Rule 21"}],
        },
        "evidence_index": [
            {"ref": "E-01", "document_id": str(uuid4()),
             "filename": "pr.xlsx", "source_type": "purchase_register",
             "bucket": "recon-files", "storage_path": "t/c/pr.xlsx"},
        ],
    }
    model = AuditDefensePackPayload.model_validate(payload)
    dumped = model.model_dump(mode="json")
    assert dumped["notice"]["alleged_shortfall_bdt"] == "435500.00"
    assert dumped["evidence_index"][0]["ref"] == "E-01"
    assert dumped["override_log"][0]["ca_override"] == "disputed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/working_papers/test_schemas.py::test_audit_defense_pack_payload_round_trips -v`
Expected: FAIL with `ImportError: cannot import name 'AuditDefensePackPayload'`.

- [ ] **Step 3: Add the models**

In `backend/app/working_papers/schemas.py`, add the enum value to `WorkingPaperKind`:

```python
class WorkingPaperKind(str, Enum):
    AT_RISK_ITC_SCHEDULE = "at_risk_itc_schedule"
    AUDIT_DEFENSE_PACK = "audit_defense_pack"
```

Then add these models (after the At-Risk models, before `WorkingPaperPayload`):

```python
class NoticeSummary(BaseModel):
    notice_no: Optional[str] = None
    notice_date: Optional[date] = None
    notice_type: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    taxpayer_bin: Optional[str] = None
    taxpayer_tin: Optional[str] = None
    alleged_itc_claimed_bdt: Optional[Decimal] = None
    alleged_itc_allowed_bdt: Optional[Decimal] = None
    alleged_shortfall_bdt: Optional[Decimal] = None

    @field_serializer(
        "alleged_itc_claimed_bdt", "alleged_itc_allowed_bdt",
        "alleged_shortfall_bdt", when_used="json",
    )
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None


class OverrideLogEntry(BaseModel):
    supplier_name: Optional[str] = None
    supplier_bin: Optional[str] = None
    invoice_no: Optional[str] = None
    ca_override: Optional[Literal["approved", "disputed", "ignore"]] = None
    ca_notes: Optional[str] = None


class DraftedReplyBlock(BaseModel):
    language: Optional[str] = None
    status: Optional[str] = None
    body_html: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    ref: str
    document_id: Optional[UUID] = None
    filename: str
    source_type: str
    bucket: str
    storage_path: str


class AuditDefensePackPayload(BaseModel):
    kind: Literal["audit_defense_pack"] = "audit_defense_pack"
    recipe_version: str
    client_id: UUID
    client_name: str
    client_bin: Optional[str] = None
    client_tin: Optional[str] = None
    notice_id: UUID
    notice: NoticeSummary
    reconciliation_id: Optional[UUID] = None
    reconciled_position: Optional[AtRiskItcSchedulePayload] = None
    override_log: list[OverrideLogEntry] = Field(default_factory=list)
    drafted_reply: Optional[DraftedReplyBlock] = None
    evidence_index: list[EvidenceItem] = Field(default_factory=list)
```

Update the union:

```python
WorkingPaperPayload = Annotated[
    Union[AtRiskItcSchedulePayload, AuditDefensePackPayload],
    Field(discriminator="kind"),
]
```

(`Any` is already imported at the top of the file.)

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/working_papers/test_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/working_papers/schemas.py backend/tests/working_papers/test_schemas.py
git commit -m "feat(working-papers): AuditDefensePackPayload schemas"
```

---

## Task 3: The recipe

**Files:**
- Create: `backend/app/working_papers/recipes/audit_defense_pack.py`
- Modify: `backend/app/working_papers/recipes/__init__.py`
- Test: `backend/tests/working_papers/test_recipe_audit_defense_pack.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/working_papers/test_recipe_audit_defense_pack.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/working_papers/test_recipe_audit_defense_pack.py -v`
Expected: FAIL with `ModuleNotFoundError: ...audit_defense_pack`.

- [ ] **Step 3: Write the recipe**

Create `backend/app/working_papers/recipes/audit_defense_pack.py`:

```python
"""Audit Defense Pack recipe — composes a per-notice rebuttal binder.

Anchored on a notice_id. Derives the linked reconciliation, reuses the
At-Risk ITC recipe for the reconciled-position section (so numbers tie out),
builds the CA override log, pulls the drafted reply, and indexes the linked
evidence artifacts (recon source files + the notice file).
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin
from app.working_papers.recipes.at_risk_itc import AtRiskItcScheduleRecipe

_PAGE = 1000


class AuditDefensePackRecipe:
    id: str = "audit_defense_pack"
    version: str = "v1"

    async def compose(self, *, tenant_id: UUID, notice_id: UUID, **_: Any) -> dict[str, Any]:
        sb = get_supabase_admin()

        def _q_notice():
            return (sb.table("notices").select("*")
                    .eq("id", str(notice_id)).eq("tenant_id", str(tenant_id))
                    .single().execute())

        notice = (await asyncio.to_thread(_q_notice)).data

        def _q_client(cid):
            return (sb.table("clients").select("id, name, bin, tin")
                    .eq("id", cid).eq("tenant_id", str(tenant_id))
                    .single().execute())

        client = (await asyncio.to_thread(_q_client, notice["client_id"])).data

        recon_id = notice.get("linked_reconciliation_id")
        reconciled_position = None
        override_log: list[dict[str, Any]] = []
        evidence_index: list[dict[str, Any]] = []
        seq = 0

        def _ref():
            nonlocal seq
            seq += 1
            return f"E-{seq:02d}"

        if recon_id:
            reconciled_position = await AtRiskItcScheduleRecipe().compose(
                tenant_id=tenant_id, reconciliation_id=UUID(str(recon_id)))

            def _q_recon():
                return (sb.table("vat_reconciliations")
                        .select("purchase_register_doc_id, supplier_data_doc_id")
                        .eq("id", str(recon_id)).eq("tenant_id", str(tenant_id))
                        .single().execute())

            recon = (await asyncio.to_thread(_q_recon)).data

            # Override log: only lines where the CA recorded a decision.
            def _q_overrides(offset, limit):
                return (sb.table("recon_line_items")
                        .select("pr_supplier_name, pr_supplier_bin, pr_invoice_no, "
                                "ca_override, ca_notes")
                        .eq("tenant_id", str(tenant_id))
                        .eq("reconciliation_id", str(recon_id))
                        .order("pr_supplier_name")
                        .range(offset, offset + limit - 1).execute())

            rows: list[dict] = []
            while True:
                batch = (await asyncio.to_thread(_q_overrides, len(rows), _PAGE)).data or []
                rows.extend(batch)
                if len(batch) < _PAGE:
                    break
            for r in rows:
                if r.get("ca_override"):
                    override_log.append({
                        "supplier_name": r.get("pr_supplier_name"),
                        "supplier_bin": r.get("pr_supplier_bin"),
                        "invoice_no": r.get("pr_invoice_no"),
                        "ca_override": r.get("ca_override"),
                        "ca_notes": r.get("ca_notes"),
                    })

            # Evidence: recon source files (bucket recon-files).
            for col, kind in (("purchase_register_doc_id", "purchase_register"),
                              ("supplier_data_doc_id", "supplier_export")):
                did = recon.get(col)
                if not did:
                    continue

                def _q_doc(d=did):
                    return (sb.table("documents")
                            .select("id, original_filename, storage_path, doc_type")
                            .eq("id", str(d)).eq("tenant_id", str(tenant_id))
                            .single().execute())

                doc = (await asyncio.to_thread(_q_doc)).data
                if doc:
                    evidence_index.append({
                        "ref": _ref(), "document_id": doc["id"],
                        "filename": doc.get("original_filename") or "document",
                        "source_type": kind, "bucket": "recon-files",
                        "storage_path": doc["storage_path"],
                    })

        # Drafted reply: finalized if present, else most recently updated.
        def _q_drafts():
            return (sb.table("notice_drafts")
                    .select("language, status, body_html, citations, "
                            "finalized_at, updated_at")
                    .eq("notice_id", str(notice_id)).eq("tenant_id", str(tenant_id))
                    .order("updated_at", desc=True).execute())

        drafts = (await asyncio.to_thread(_q_drafts)).data or []
        drafted_reply = None
        if drafts:
            chosen = next((d for d in drafts if d.get("status") == "finalized"), drafts[0])
            drafted_reply = {
                "language": chosen.get("language"),
                "status": chosen.get("status"),
                "body_html": chosen.get("body_html") or "",
                "citations": list(chosen.get("citations") or []),
            }

        # Evidence: the notice file itself (bucket notices).
        if notice.get("storage_path"):
            evidence_index.append({
                "ref": _ref(), "document_id": None,
                "filename": notice.get("original_filename") or "notice.pdf",
                "source_type": "nbr_notice", "bucket": "notices",
                "storage_path": notice["storage_path"],
            })

        return {
            "kind": self.id,
            "recipe_version": self.version,
            "client_id": client["id"],
            "client_name": client["name"],
            "client_bin": client.get("bin"),
            "client_tin": client.get("tin"),
            "notice_id": str(notice_id),
            "notice": {
                "notice_no": notice.get("notice_no"),
                "notice_date": notice.get("notice_date"),
                "notice_type": notice.get("notice_type"),
                "period_start": notice.get("period_start"),
                "period_end": notice.get("period_end"),
                "taxpayer_bin": notice.get("taxpayer_bin"),
                "taxpayer_tin": notice.get("taxpayer_tin"),
                "alleged_itc_claimed_bdt": notice.get("alleged_itc_claimed_bdt"),
                "alleged_itc_allowed_bdt": notice.get("alleged_itc_allowed_bdt"),
                "alleged_shortfall_bdt": notice.get("alleged_shortfall_bdt"),
            },
            "reconciliation_id": str(recon_id) if recon_id else None,
            "reconciled_position": reconciled_position,
            "override_log": override_log,
            "drafted_reply": drafted_reply,
            "evidence_index": evidence_index,
        }
```

- [ ] **Step 4: Register the recipe**

In `backend/app/working_papers/recipes/__init__.py`:

```python
from app.working_papers.recipes.at_risk_itc import AtRiskItcScheduleRecipe
from app.working_papers.recipes.audit_defense_pack import AuditDefensePackRecipe
from app.working_papers.recipes.base import Recipe


_REGISTRY: dict[str, Recipe] = {
    AtRiskItcScheduleRecipe.id: AtRiskItcScheduleRecipe(),
    AuditDefensePackRecipe.id: AuditDefensePackRecipe(),
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/working_papers/test_recipe_audit_defense_pack.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/working_papers/recipes/audit_defense_pack.py backend/app/working_papers/recipes/__init__.py backend/tests/working_papers/test_recipe_audit_defense_pack.py
git commit -m "feat(working-papers): audit_defense_pack recipe (reuses At-Risk ITC)"
```

---

## Task 4: Service + persistence + request wiring

**Files:**
- Modify: `backend/app/working_papers/schemas.py` (ComposeWorkingPaperRequest)
- Modify: `backend/app/working_papers/persistence.py` (create_working_paper)
- Modify: `backend/app/working_papers/service.py` (compose validation + validators map)
- Test: `backend/tests/working_papers/test_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/working_papers/test_service.py`:

```python
def test_compose_audit_defense_pack_requires_notice_id(monkeypatch):
    from app.working_papers.schemas import WorkingPaperKind
    from app.working_papers.exceptions import WorkingPaperInvalidStateError

    with pytest.raises(WorkingPaperInvalidStateError):
        _run(svc.compose_working_paper(
            tenant_id=TENANT, user_id=PREPARER,
            kind=WorkingPaperKind.AUDIT_DEFENSE_PACK, notice_id=None,
        ))


def test_compose_audit_defense_pack_persists_notice_id(monkeypatch):
    from app.working_papers.schemas import WorkingPaperKind
    from uuid import uuid4
    captured = {}
    notice_id = uuid4()

    class _Recipe:
        id = "audit_defense_pack"
        version = "v1"
        async def compose(self, *, tenant_id, **inputs):
            captured["inputs"] = inputs
            return {
                "kind": "audit_defense_pack", "recipe_version": "v1",
                "client_id": str(uuid4()), "client_name": "X",
                "notice_id": str(notice_id),
                "notice": {}, "reconciliation_id": None,
                "reconciled_position": None, "override_log": [],
                "drafted_reply": None, "evidence_index": [],
            }

    async def _create(**kw):
        captured["create"] = kw
        return uuid4()

    monkeypatch.setattr(svc, "get_recipe", lambda rid: _Recipe())
    monkeypatch.setattr(svc.p, "create_working_paper", _create)

    _run(svc.compose_working_paper(
        tenant_id=TENANT, user_id=PREPARER,
        kind=WorkingPaperKind.AUDIT_DEFENSE_PACK, notice_id=notice_id,
    ))
    assert captured["inputs"] == {"notice_id": notice_id}
    assert captured["create"]["notice_id"] == notice_id
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/working_papers/test_service.py -k audit_defense -v`
Expected: FAIL (`compose_working_paper` has no `notice_id` param / no validator entry).

- [ ] **Step 3: Add `notice_id` to the request DTO**

In `backend/app/working_papers/schemas.py`, update `ComposeWorkingPaperRequest`:

```python
class ComposeWorkingPaperRequest(BaseModel):
    kind: WorkingPaperKind
    reconciliation_id: Optional[UUID] = None  # required for at_risk_itc_schedule
    notice_id: Optional[UUID] = None           # required for audit_defense_pack
```

- [ ] **Step 4: Add `notice_id` to persistence**

In `backend/app/working_papers/persistence.py`, add a `notice_id` parameter to `create_working_paper` (after `reconciliation_id`):

```python
async def create_working_paper(
    *,
    tenant_id: UUID,
    client_id: UUID,
    kind: WorkingPaperKind,
    reconciliation_id: Optional[UUID],
    notice_id: Optional[UUID] = None,
    period_start: Optional[date],
    period_end: Optional[date],
    recipe_version: str,
    composed_json: Dict[str, Any],
    composed_by: UUID,
) -> UUID:
```

And add to the head insert dict (inside `_ins_wp`):

```python
            "reconciliation_id": str(reconciliation_id) if reconciliation_id else None,
            "notice_id": str(notice_id) if notice_id else None,
```

- [ ] **Step 5: Wire the service**

In `backend/app/working_papers/service.py`:

Update `_PAYLOAD_VALIDATORS`:

```python
from app.working_papers.schemas import (
    AtRiskItcSchedulePayload,
    AuditDefensePackPayload,
    WorkingPaperEditSource,
    WorkingPaperKind,
    WorkingPaperStatus,
)

_PAYLOAD_VALIDATORS = {
    WorkingPaperKind.AT_RISK_ITC_SCHEDULE: AtRiskItcSchedulePayload,
    WorkingPaperKind.AUDIT_DEFENSE_PACK: AuditDefensePackPayload,
}
```

Update `compose_working_paper` signature and the per-kind input block:

```python
async def compose_working_paper(
    *,
    tenant_id: UUID,
    user_id: UUID,
    kind: WorkingPaperKind,
    reconciliation_id: Optional[UUID] = None,
    notice_id: Optional[UUID] = None,
) -> UUID:
    recipe = get_recipe(kind.value)

    if kind == WorkingPaperKind.AT_RISK_ITC_SCHEDULE:
        if reconciliation_id is None:
            raise WorkingPaperInvalidStateError(
                "reconciliation_id is required for at_risk_itc_schedule")
        inputs: Dict[str, Any] = {"reconciliation_id": reconciliation_id}
    elif kind == WorkingPaperKind.AUDIT_DEFENSE_PACK:
        if notice_id is None:
            raise WorkingPaperInvalidStateError(
                "notice_id is required for audit_defense_pack")
        inputs = {"notice_id": notice_id}
    else:
        inputs = {}
```

And pass `notice_id` to the persistence call (add the kwarg):

```python
    wp_id = await p.create_working_paper(
        tenant_id=tenant_id,
        client_id=UUID(str(validated.client_id)),
        kind=kind,
        reconciliation_id=getattr(validated, "reconciliation_id", None),
        notice_id=getattr(validated, "notice_id", None),
        period_start=getattr(validated, "period_start", None),
        period_end=getattr(validated, "period_end", None),
        recipe_version=recipe.version,
        composed_json=composed_json,
        composed_by=user_id,
    )
```

Note: `AuditDefensePackPayload` has no `period_start`/`period_end` field, so `getattr` returns `None` — that is correct; the pack row's period stays null (the notice's period lives inside `composed_json.notice`).

Finally, update the router `compose_working_paper` endpoint in `backend/app/working_papers/router.py` to forward `notice_id`:

```python
    wp_id = await svc.compose_working_paper(
        tenant_id=tenant_id, user_id=user_id,
        kind=body.kind, reconciliation_id=body.reconciliation_id,
        notice_id=body.notice_id,
    )
```

- [ ] **Step 6: Run to verify it passes**

Run: `python -m pytest tests/working_papers/test_service.py -v`
Expected: PASS (all, including the new two).

- [ ] **Step 7: Commit**

```bash
git add backend/app/working_papers/schemas.py backend/app/working_papers/persistence.py backend/app/working_papers/service.py backend/app/working_papers/router.py backend/tests/working_papers/test_service.py
git commit -m "feat(working-papers): compose audit_defense_pack via notice_id"
```

---

## Task 5: Refactor At-Risk renderer into shared section emitters

**Files:**
- Modify: `backend/app/working_papers/rendering.py`
- Test: existing `backend/tests/working_papers/test_rendering.py` (guards behavior — no new test)

- [ ] **Step 1: Confirm existing tests pass (baseline)**

Run: `python -m pytest tests/working_papers/test_rendering.py -v`
Expected: PASS (14 passed, 1 skipped).

- [ ] **Step 2: Extract two private helpers**

In `backend/app/working_papers/rendering.py`, add these helpers (above `_render_at_risk_itc_schedule`). They are the exact emitters currently inlined:

```python
def _emit_summary_table(doc, s: dict) -> None:
    summary_table = doc.add_table(rows=4, cols=2)
    summary_table.style = "Light List"
    pairs = [
        ("Total VAT claimed (BDT)", _fmt_bdt(s["total_vat_claimed_bdt"])),
        ("Safe ITC (BDT)", _fmt_bdt(s["safe_itc_bdt"])),
        ("At-risk ITC (BDT)", _fmt_bdt(s["at_risk_itc_bdt"])),
        ("Lines flagged",
         f"{s['at_risk_line_count']} of {s['total_lines']} "
         f"(across {s['supplier_count_at_risk']} supplier(s))"),
    ]
    for i, (k, v) in enumerate(pairs):
        summary_table.rows[i].cells[0].text = k
        summary_table.rows[i].cells[1].text = v
        _right(summary_table.rows[i].cells[1])


def _emit_supplier_section(doc, supplier_groups: list) -> Decimal:
    grand_total = Decimal("0.00")
    for grp in supplier_groups:
        grand_total += Decimal(str(grp.get("total_vat_at_risk_bdt") or "0"))
        gh = doc.add_paragraph()
        gr = gh.add_run(
            f"{grp.get('supplier_name') or '(unknown supplier)'}"
            + (f" — BIN {grp['supplier_bin']}" if grp.get("supplier_bin") else "")
            + f"   ·   VAT at risk: BDT {_fmt_bdt(grp['total_vat_at_risk_bdt'])}"
            + f"   ·   {grp['line_count']} line(s)")
        gr.bold = True

        lines = grp["lines"]
        table = doc.add_table(rows=2 + len(lines), cols=7)
        table.style = "Light List"
        headers = ["Invoice no", "Invoice date", "Claimed VAT (BDT)",
                   "Supplier VAT (BDT)", "Variance (BDT)", "Match",
                   "Recommended action"]
        for c, label in enumerate(headers):
            table.rows[0].cells[c].text = label
        for c in (2, 3, 4):
            _right(table.rows[0].cells[c])
        for i, line in enumerate(lines, start=1):
            row = table.rows[i].cells
            row[0].text = str(line.get("invoice_no") or "")
            row[1].text = str(line.get("invoice_date") or "")
            row[2].text = _fmt_bdt(line.get("vat_amount_bdt"))
            sf_vat = line.get("sf_vat_amount_bdt")
            row[3].text = _fmt_bdt(sf_vat) if sf_vat else "not filed"
            row[4].text = _fmt_bdt(line.get("vat_variance_bdt"))
            override = line.get("ca_override")
            ms = line["match_status"]
            match_txt = ms if not override else f"{ms} ({override})"
            reason = line.get("discrepancy_reason")
            row[5].text = f"{match_txt}\n{reason}" if reason else match_txt
            row[6].text = (line["recommended_action"] or "").replace("_", " ")
            for c in (2, 3, 4):
                _right(row[c])
        foot = table.rows[1 + len(lines)].cells
        foot[1].text = "Subtotal"
        _bold_cell(foot[1])
        foot[4].text = _fmt_bdt(grp["total_vat_at_risk_bdt"])
        _right(foot[4]); _bold_cell(foot[4])
    return grand_total
```

- [ ] **Step 3: Replace the inlined blocks in `_render_at_risk_itc_schedule`**

Replace the summary-table block (from `summary_table = doc.add_table(rows=4, cols=2)` through the `for i, (k, v) in enumerate(pairs):` loop) with:

```python
    s = payload["summary"]
    _emit_summary_table(doc, s)
```

Replace the per-supplier loop (from `grand_total = Decimal("0.00")` through the end of the `for grp in payload["supplier_groups"]:` body, i.e. just before the grand-total paragraph) with:

```python
    grand_total = _emit_supplier_section(doc, payload["supplier_groups"])
```

(Keep the heading paragraphs "Summary" and "At-risk lines by supplier", and the grand-total paragraph, exactly as they are.)

- [ ] **Step 4: Run to verify behavior unchanged**

Run: `python -m pytest tests/working_papers/test_rendering.py -v`
Expected: PASS (same 14 passed, 1 skipped).

- [ ] **Step 5: Commit**

```bash
git add backend/app/working_papers/rendering.py
git commit -m "refactor(working-papers): extract shared docx section emitters"
```

---

## Task 6: Audit Defense Pack renderer

**Files:**
- Modify: `backend/app/working_papers/rendering.py`
- Test: `backend/tests/working_papers/test_rendering_audit_pack.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/working_papers/test_rendering_audit_pack.py`:

```python
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
    assert "NBR/4471" in text                  # notice summary
    assert "4,35,500.00" in text               # alleged shortfall, grouped
    assert "At-risk ITC (BDT)" in text         # reconciled position reused
    assert "Decision" in text and "Awaiting amended Mushak 6.3" in text  # override log
    assert "আমরা আপত্তি জানাই।" in text          # drafted reply
    assert "Rule 21" in text                   # citation
    assert "Evidence" in text and "E-01" in text and "pr.xlsx" in text   # evidence index


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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/working_papers/test_rendering_audit_pack.py -v`
Expected: FAIL (`render_docx` raises ValueError on unknown kind `audit_defense_pack`).

- [ ] **Step 3: Add the dispatch + renderer**

In `backend/app/working_papers/rendering.py`, update `render_docx`:

```python
def render_docx(*, payload, notes_html, tenant, meta=None) -> bytes:
    kind = payload.get("kind")
    if kind == "at_risk_itc_schedule":
        return _render_at_risk_itc_schedule(payload, notes_html, tenant, meta or {})
    if kind == "audit_defense_pack":
        return _render_audit_defense_pack(payload, notes_html, tenant, meta or {})
    raise ValueError(f"Unknown working paper kind: {kind!r}")
```

Add the renderer (after `_render_at_risk_itc_schedule`). Reuse the existing helpers `_fmt_bdt`, `_right`, `_bold_cell`, `_notes_blocks`, `_page_number_footer`, `_emit_summary_table`, `_emit_supplier_section`:

```python
def _render_audit_defense_pack(payload, notes_html, tenant, meta) -> bytes:
    doc = Document()

    # Letterhead (same as at-risk)
    firm = tenant.get("firm_name") or "Chartered Accountants"
    p = doc.add_paragraph(); r = p.add_run(firm); r.bold = True; r.font.size = Pt(14)
    contact_bits = [tenant.get("address"),
                    f"ICAB Reg: {tenant['icab_reg_no']}" if tenant.get("icab_reg_no") else None,
                    tenant.get("email"), tenant.get("phone")]
    contact = "  ·  ".join(b for b in contact_bits if b)
    if contact:
        cp = doc.add_paragraph(contact); cp.runs[0].font.size = Pt(9)

    ref_line = []
    if meta.get("reference"): ref_line.append(f"Ref: {meta['reference']}")
    if meta.get("generated_on"): ref_line.append(f"Generated: {meta['generated_on']}")
    if meta.get("status"): ref_line.append(f"Status: {str(meta['status']).upper()}")
    if ref_line:
        rp = doc.add_paragraph("   ·   ".join(ref_line))
        rp.runs[0].font.size = Pt(9); rp.runs[0].italic = True

    # Title + cover facts
    doc.add_paragraph("")
    t = doc.add_paragraph(); tr = t.add_run("Audit Defense Pack")
    tr.bold = True; tr.font.size = Pt(16)
    n = payload["notice"]
    doc.add_paragraph().add_run(
        f"Client: {payload['client_name']}"
        + (f" (BIN {payload['client_bin']})" if payload.get("client_bin") else "")
        + (f", TIN {payload['client_tin']}" if payload.get("client_tin") else ""))
    doc.add_paragraph().add_run(
        f"In response to Notice {n.get('notice_no') or '(unknown)'} "
        f"dated {n.get('notice_date') or '(unknown)'}")
    demand = doc.add_paragraph()
    dr = demand.add_run(f"Alleged shortfall: BDT {_fmt_bdt(n.get('alleged_shortfall_bdt'))}")
    dr.bold = True; dr.font.size = Pt(12)

    # 1. Notice summary
    doc.add_paragraph("")
    doc.add_paragraph().add_run("1. Notice summary").bold = True
    nt = doc.add_table(rows=5, cols=2); nt.style = "Light List"
    nrows = [
        ("Notice type", str(n.get("notice_type") or "")),
        ("Period", f"{n.get('period_start') or '?'} to {n.get('period_end') or '?'}"),
        ("Alleged ITC claimed (BDT)", _fmt_bdt(n.get("alleged_itc_claimed_bdt"))),
        ("Alleged ITC allowed (BDT)", _fmt_bdt(n.get("alleged_itc_allowed_bdt"))),
        ("Alleged shortfall (BDT)", _fmt_bdt(n.get("alleged_shortfall_bdt"))),
    ]
    for i, (k, v) in enumerate(nrows):
        nt.rows[i].cells[0].text = k; nt.rows[i].cells[1].text = v
        _right(nt.rows[i].cells[1])

    # 2. Reconciled position (reused emitters)
    doc.add_paragraph("")
    doc.add_paragraph().add_run("2. Reconciled position").bold = True
    rp_section = payload.get("reconciled_position")
    if rp_section:
        _emit_summary_table(doc, rp_section["summary"])
        doc.add_paragraph().add_run("At-risk lines by supplier").bold = True
        grand = _emit_supplier_section(doc, rp_section["supplier_groups"])
        gt = doc.add_paragraph()
        gtr = gt.add_run(f"Total at-risk ITC: BDT {_fmt_bdt(grand)}")
        gtr.bold = True; gtr.font.size = Pt(12)
    else:
        doc.add_paragraph("No reconciliation is linked to this notice.")

    # 3. Decision & override log
    doc.add_paragraph("")
    doc.add_paragraph().add_run("3. Decision & override log").bold = True
    log = payload.get("override_log") or []
    if log:
        lt = doc.add_table(rows=1 + len(log), cols=4); lt.style = "Light List"
        for c, h in enumerate(["Supplier", "Invoice", "Decision", "Note"]):
            lt.rows[0].cells[c].text = h
        for i, e in enumerate(log, start=1):
            cells = lt.rows[i].cells
            cells[0].text = str(e.get("supplier_name") or "")
            cells[1].text = str(e.get("invoice_no") or "")
            cells[2].text = str(e.get("ca_override") or "")
            cells[3].text = str(e.get("ca_notes") or "")
    else:
        doc.add_paragraph("No CA overrides were recorded for this period.")

    # 4. Drafted reply + citations
    doc.add_paragraph("")
    doc.add_paragraph().add_run("4. Drafted reply").bold = True
    reply = payload.get("drafted_reply")
    if reply and (reply.get("body_html") or "").strip():
        for block in _notes_blocks(reply["body_html"]):
            doc.add_paragraph(block)
        cits = reply.get("citations") or []
        if cits:
            doc.add_paragraph().add_run("Citations").bold = True
            for c in cits:
                ref = c.get("source_ref") or c.get("source") or "citation"
                snip = c.get("snippet")
                doc.add_paragraph(f"• {ref}" + (f" — {snip}" if snip else ""))
    else:
        doc.add_paragraph("No reply has been drafted for this notice yet.")

    # 5. Evidence index
    doc.add_paragraph("")
    doc.add_paragraph().add_run("5. Evidence index").bold = True
    ev = payload.get("evidence_index") or []
    if ev:
        et = doc.add_table(rows=1 + len(ev), cols=3); et.style = "Light List"
        for c, h in enumerate(["Ref", "Document", "Source type"]):
            et.rows[0].cells[c].text = h
        for i, e in enumerate(ev, start=1):
            cells = et.rows[i].cells
            cells[0].text = e.get("ref") or ""
            cells[1].text = e.get("filename") or ""
            cells[2].text = (e.get("source_type") or "").replace("_", " ")
        doc.add_paragraph(
            "Files are provided in the evidence bundle (.zip), named to match "
            "the reference column.").runs[0].font.size = Pt(9)
    else:
        doc.add_paragraph("No evidence artifacts are linked.")

    # CA commentary (shared behavior)
    blocks = _notes_blocks(notes_html) if notes_html else []
    if blocks:
        doc.add_paragraph("")
        doc.add_paragraph().add_run("CA commentary").bold = True
        for b in blocks:
            doc.add_paragraph(b)

    # Sign-off + page numbers (same as at-risk)
    doc.add_paragraph("")
    signoff = doc.add_table(rows=2, cols=2); signoff.style = "Light List"
    signoff.rows[0].cells[0].text = "Prepared by"; signoff.rows[0].cells[1].text = "Reviewed by"
    _bold_cell(signoff.rows[0].cells[0]); _bold_cell(signoff.rows[0].cells[1])
    signoff.rows[1].cells[0].text = meta.get("prepared_by") or "— pending —"
    signoff.rows[1].cells[1].text = meta.get("reviewed_by") or "— pending —"

    _page_number_footer(doc)
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/working_papers/test_rendering_audit_pack.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full rendering suite (no regression)**

Run: `python -m pytest tests/working_papers/test_rendering.py tests/working_papers/test_rendering_audit_pack.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/working_papers/rendering.py backend/tests/working_papers/test_rendering_audit_pack.py
git commit -m "feat(working-papers): audit_defense_pack docx renderer"
```

---

## Task 7: Evidence-bundle ZIP service + endpoint

**Files:**
- Create: `backend/app/working_papers/bundle.py`
- Modify: `backend/app/working_papers/service.py` (export_evidence_bundle)
- Modify: `backend/app/working_papers/router.py` (endpoint)
- Test: `backend/tests/working_papers/test_evidence_bundle.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/working_papers/test_evidence_bundle.py`:

```python
"""Tests for the evidence-bundle ZIP builder."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.working_papers.bundle import build_evidence_zip, EvidenceBundleTooLargeError


def test_build_zip_includes_binder_present_and_missing():
    evidence = [
        {"ref": "E-01", "filename": "pr.xlsx", "source_type": "purchase_register",
         "bucket": "recon-files", "storage_path": "t/c/pr.xlsx"},
        {"ref": "E-02", "filename": "notice.pdf", "source_type": "nbr_notice",
         "bucket": "notices", "storage_path": "t/c/missing.pdf"},
    ]

    def fake_download(bucket, path):
        if path == "t/c/pr.xlsx":
            return b"PR-BYTES"
        raise FileNotFoundError("not found")

    data = build_evidence_zip(
        binder_docx=b"DOCX-BYTES", evidence=evidence,
        download=fake_download, reference="WP-X")
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    assert "00_binder.docx" in names
    assert "E-01_pr.xlsx" in names
    assert "MANIFEST.txt" in names
    manifest = z.read("MANIFEST.txt").decode()
    assert "E-01" in manifest and "included" in manifest
    assert "E-02" in manifest and "MISSING" in manifest
    # the missing file is not added as an entry
    assert not any(name.startswith("E-02_") for name in names)


def test_build_zip_enforces_size_cap():
    evidence = [{"ref": "E-01", "filename": "big.bin", "source_type": "x",
                 "bucket": "recon-files", "storage_path": "t/c/big.bin"}]

    def fake_download(bucket, path):
        return b"x" * (60 * 1024 * 1024)  # 60 MB

    with pytest.raises(EvidenceBundleTooLargeError):
        build_evidence_zip(binder_docx=b"D", evidence=evidence,
                           download=fake_download, reference="WP-X",
                           max_bytes=50 * 1024 * 1024)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/working_papers/test_evidence_bundle.py -v`
Expected: FAIL (`ModuleNotFoundError: ...bundle`).

- [ ] **Step 3: Write the pure ZIP builder**

Create `backend/app/working_papers/bundle.py`:

```python
"""Pure evidence-bundle ZIP builder. Storage I/O is injected as `download`
so this is testable without Supabase."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Callable

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


class EvidenceBundleTooLargeError(Exception):
    pass


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "file")


def build_evidence_zip(
    *,
    binder_docx: bytes,
    evidence: list[dict[str, Any]],
    download: Callable[[str, str], bytes],
    reference: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> bytes:
    """Assemble a ZIP: 00_binder.docx + E-0N_<file> per available evidence +
    MANIFEST.txt. Missing files are recorded in the manifest, not fatal.
    Raises EvidenceBundleTooLargeError if cumulative bytes exceed max_bytes."""
    total = len(binder_docx)
    manifest_lines = [f"Audit Defense Pack evidence bundle — {reference}", ""]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_binder.docx", binder_docx)
        for e in evidence:
            ref, fname = e["ref"], e.get("filename") or "file"
            try:
                blob = download(e["bucket"], e["storage_path"])
            except Exception as exc:  # noqa: BLE001 — report, don't fail the bundle
                manifest_lines.append(f"{ref}  {fname}  [{e.get('source_type')}]  MISSING ({exc})")
                continue
            total += len(blob)
            if total > max_bytes:
                raise EvidenceBundleTooLargeError(
                    f"Evidence bundle exceeds {max_bytes} bytes")
            z.writestr(f"{ref}_{_safe(fname)}", blob)
            manifest_lines.append(f"{ref}  {fname}  [{e.get('source_type')}]  included")
        z.writestr("MANIFEST.txt", "\n".join(manifest_lines) + "\n")
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/working_papers/test_evidence_bundle.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Wire the service**

In `backend/app/working_papers/service.py`, add the export function and a bucket-aware download. Add imports at the top:

```python
from app.working_papers.bundle import (
    EvidenceBundleTooLargeError, build_evidence_zip,
)
```

Add near `export_working_paper`:

```python
def _download_evidence(bucket: str, path: str) -> bytes:
    from app.database import get_supabase_admin
    return get_supabase_admin().storage.from_(bucket).download(path)


async def export_evidence_bundle(
    *, wp_id: UUID, tenant_id: UUID,
) -> tuple[bytes, str, str]:
    """Returns (zip_bytes, content_type, filename) for an audit_defense_pack."""
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    if wp["kind"] != WorkingPaperKind.AUDIT_DEFENSE_PACK.value:
        raise WorkingPaperInvalidStateError(
            "Evidence bundle is only available for an audit defense pack")

    # Reuse the docx export (also resolves letterhead + sign-off meta).
    docx_bytes, _ctype, _fname = await export_working_paper(
        wp_id=wp_id, tenant_id=tenant_id, format="docx")

    payload = wp["composed_json"] or {}
    evidence = payload.get("evidence_index") or []
    reference = _working_paper_reference(wp)

    def _build() -> bytes:
        return build_evidence_zip(
            binder_docx=docx_bytes, evidence=evidence,
            download=_download_evidence, reference=reference)

    try:
        zip_bytes = await asyncio.to_thread(_build)
    except EvidenceBundleTooLargeError as e:
        err = WorkingPaperInvalidStateError(str(e))
        err.default_status = 413
        err.status_code = 413
        raise err
    return (zip_bytes, "application/zip", f"audit-defense-pack-{reference}.zip")
```

- [ ] **Step 6: Add the endpoint**

In `backend/app/working_papers/router.py`, add:

```python
@router.get("/{wp_id}/evidence-bundle")
async def evidence_bundle(
    wp_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    data, ctype, fname = await svc.export_evidence_bundle(
        wp_id=wp_id, tenant_id=tenant_id)
    return StreamingResponse(
        io.BytesIO(data), media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
```

- [ ] **Step 7: Run the full backend working_papers suite**

Run: `python -m pytest tests/working_papers -v`
Expected: PASS (all; 1 PDF test skipped if soffice absent).

- [ ] **Step 8: Commit**

```bash
git add backend/app/working_papers/bundle.py backend/app/working_papers/service.py backend/app/working_papers/router.py backend/tests/working_papers/test_evidence_bundle.py
git commit -m "feat(working-papers): evidence-bundle ZIP endpoint for audit defense pack"
```

---

## Task 8: Frontend types

**Files:**
- Modify: `frontend/src/types/workingPapers.ts`
- Test: `frontend/src/types/__tests__/workingPapers.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/types/__tests__/workingPapers.test.ts`:

```typescript
import { auditDefensePackPayloadSchema } from "@/types/workingPapers"

it("parses an audit_defense_pack payload", () => {
  const payload = {
    kind: "audit_defense_pack",
    recipe_version: "v1",
    client_id: "11111111-1111-1111-1111-111111111111",
    client_name: "Padma Textiles Ltd",
    client_bin: "001234567-0101",
    client_tin: "555000111",
    notice_id: "22222222-2222-2222-2222-222222222222",
    notice: {
      notice_no: "NBR/4471", notice_date: "2026-05-20",
      notice_type: "input_vat_mismatch",
      period_start: "2026-04-01", period_end: "2026-04-30",
      taxpayer_bin: "001234567-0101", taxpayer_tin: "555000111",
      alleged_itc_claimed_bdt: "2847500.00",
      alleged_itc_allowed_bdt: "2412000.00",
      alleged_shortfall_bdt: "435500.00",
    },
    reconciliation_id: "33333333-3333-3333-3333-333333333333",
    reconciled_position: null,
    override_log: [{ supplier_name: "Meghna", supplier_bin: "0044",
      invoice_no: "MP-7798", ca_override: "disputed", ca_notes: "pending" }],
    drafted_reply: { language: "bn", status: "finalized",
      body_html: "<p>x</p>", citations: [{ source_ref: "Rule 21" }] },
    evidence_index: [{ ref: "E-01", document_id: null, filename: "pr.xlsx",
      source_type: "purchase_register", bucket: "recon-files",
      storage_path: "t/c/pr.xlsx" }],
  }
  const parsed = auditDefensePackPayloadSchema.safeParse(payload)
  expect(parsed.success).toBe(true)
})
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/types/__tests__/workingPapers.test.ts`
Expected: FAIL (`auditDefensePackPayloadSchema` is undefined).

- [ ] **Step 3: Add the Zod schemas**

In `frontend/src/types/workingPapers.ts`:

Add `"audit_defense_pack"` to `WORKING_PAPER_KINDS`:

```typescript
export const WORKING_PAPER_KINDS = [
  "at_risk_itc_schedule", "audit_defense_pack",
] as const
```

Add (after the at-risk payload schema):

```typescript
export const noticeSummarySchema = z.object({
  notice_no: z.string().nullable().optional(),
  notice_date: z.string().nullable().optional(),
  notice_type: z.string().nullable().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  taxpayer_bin: z.string().nullable().optional(),
  taxpayer_tin: z.string().nullable().optional(),
  alleged_itc_claimed_bdt: z.string().nullable().optional(),
  alleged_itc_allowed_bdt: z.string().nullable().optional(),
  alleged_shortfall_bdt: z.string().nullable().optional(),
})

export const overrideLogEntrySchema = z.object({
  supplier_name: z.string().nullable().optional(),
  supplier_bin: z.string().nullable().optional(),
  invoice_no: z.string().nullable().optional(),
  ca_override: z.enum(WP_CA_OVERRIDES).nullable().optional(),
  ca_notes: z.string().nullable().optional(),
})

export const draftedReplyBlockSchema = z.object({
  language: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  body_html: z.string(),
  citations: z.array(z.record(z.unknown())).default([]),
})

export const evidenceItemSchema = z.object({
  ref: z.string(),
  document_id: z.string().uuid().nullable().optional(),
  filename: z.string(),
  source_type: z.string(),
  bucket: z.string(),
  storage_path: z.string(),
})

export const auditDefensePackPayloadSchema = z.object({
  kind: z.literal("audit_defense_pack"),
  recipe_version: z.string(),
  client_id: uuid,
  client_name: z.string(),
  client_bin: z.string().nullable().optional(),
  client_tin: z.string().nullable().optional(),
  notice_id: uuid,
  notice: noticeSummarySchema,
  reconciliation_id: uuid.nullable().optional(),
  reconciled_position: atRiskItcSchedulePayloadSchema.nullable().optional(),
  override_log: z.array(overrideLogEntrySchema).default([]),
  drafted_reply: draftedReplyBlockSchema.nullable().optional(),
  evidence_index: z.array(evidenceItemSchema).default([]),
})
export type AuditDefensePackPayload = z.infer<typeof auditDefensePackPayloadSchema>
export type OverrideLogEntry = z.infer<typeof overrideLogEntrySchema>
export type EvidenceItem = z.infer<typeof evidenceItemSchema>
export type NoticeSummary = z.infer<typeof noticeSummarySchema>
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/types/__tests__/workingPapers.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/workingPapers.ts frontend/src/types/__tests__/workingPapers.test.ts
git commit -m "feat(working-papers/fe): audit_defense_pack Zod types"
```

---

## Task 9: Frontend view component

**Files:**
- Create: `frontend/src/components/working-papers/AuditDefensePackView.tsx`
- Test: `frontend/src/components/working-papers/__tests__/AuditDefensePackView.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/working-papers/__tests__/AuditDefensePackView.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"

import { AuditDefensePackView } from "@/components/working-papers/AuditDefensePackView"
import type { AuditDefensePackPayload } from "@/types/workingPapers"

const payload: AuditDefensePackPayload = {
  kind: "audit_defense_pack", recipe_version: "v1",
  client_id: "11111111-1111-1111-1111-111111111111",
  client_name: "Padma Textiles Ltd", client_bin: "001234567-0101",
  client_tin: "555000111",
  notice_id: "22222222-2222-2222-2222-222222222222",
  notice: { notice_no: "NBR/4471", notice_date: "2026-05-20",
    notice_type: "input_vat_mismatch", period_start: "2026-04-01",
    period_end: "2026-04-30", taxpayer_bin: "001234567-0101",
    taxpayer_tin: "555000111", alleged_itc_claimed_bdt: "2847500.00",
    alleged_itc_allowed_bdt: "2412000.00", alleged_shortfall_bdt: "435500.00" },
  reconciliation_id: null, reconciled_position: null,
  override_log: [{ supplier_name: "Meghna", supplier_bin: "0044",
    invoice_no: "MP-7798", ca_override: "disputed", ca_notes: "pending" }],
  drafted_reply: { language: "bn", status: "finalized",
    body_html: "<p>reply text</p>", citations: [{ source_ref: "Rule 21" }] },
  evidence_index: [{ ref: "E-01", document_id: null, filename: "notice.pdf",
    source_type: "nbr_notice", bucket: "notices", storage_path: "t/c/n.pdf" }],
}

describe("AuditDefensePackView", () => {
  it("renders the notice, override log, reply and evidence", () => {
    render(<AuditDefensePackView payload={payload} />)
    expect(screen.getByText(/NBR\/4471/)).toBeInTheDocument()
    expect(screen.getByText(/MP-7798/)).toBeInTheDocument()
    expect(screen.getByText(/reply text/)).toBeInTheDocument()
    expect(screen.getByText(/E-01/)).toBeInTheDocument()
    expect(screen.getByText(/notice.pdf/)).toBeInTheDocument()
  })

  it("shows an empty-state when no reconciliation is linked", () => {
    render(<AuditDefensePackView payload={payload} />)
    expect(screen.getByText(/No reconciliation linked/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/components/working-papers/__tests__/AuditDefensePackView.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the component**

Create `frontend/src/components/working-papers/AuditDefensePackView.tsx`:

```typescript
/**
 * Read-only renderer for the audit_defense_pack composed payload.
 * Sections: notice summary, reconciled position (reuses AtRiskItcScheduleView),
 * override log, drafted reply + citations, evidence index.
 */
import { AtRiskItcScheduleView } from "@/components/working-papers/AtRiskItcScheduleView"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/formatBDT"
import type { AuditDefensePackPayload } from "@/types/workingPapers"

interface Props { payload: AuditDefensePackPayload }

export function AuditDefensePackView({ payload }: Props) {
  const n = payload.notice
  return (
    <div className="space-y-6">
      <div className="rounded-md border bg-white p-4">
        <p className="text-xs uppercase tracking-wide text-slate-500">In response to</p>
        <p className="text-base font-semibold text-slate-900">
          Notice {n.notice_no ?? "—"}{" "}
          <span className="text-sm font-normal text-slate-500">
            dated {n.notice_date ?? "—"}
          </span>
        </p>
        <p className="mt-1 text-sm text-slate-600">
          {payload.client_name}
          {payload.client_bin ? ` · BIN ${payload.client_bin}` : ""}
          {payload.client_tin ? ` · TIN ${payload.client_tin}` : ""}
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">1. Notice summary</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
            <Field label="Type" value={n.notice_type ?? "—"} />
            <Field label="Period" value={`${n.period_start ?? "?"} → ${n.period_end ?? "?"}`} />
            <Field label="Alleged claimed" value={formatBDT(n.alleged_itc_claimed_bdt ?? null)} />
            <Field label="Alleged allowed" value={formatBDT(n.alleged_itc_allowed_bdt ?? null)} />
            <Field label="Alleged shortfall"
                   value={formatBDT(n.alleged_shortfall_bdt ?? null)} tone="warn" />
          </dl>
        </CardContent>
      </Card>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">2. Reconciled position</h2>
        {payload.reconciled_position ? (
          <AtRiskItcScheduleView payload={payload.reconciled_position} />
        ) : (
          <Card><CardContent className="py-6 text-sm text-slate-500">
            No reconciliation linked to this notice.
          </CardContent></Card>
        )}
      </section>

      <Card>
        <CardHeader><CardTitle className="text-base">3. Decision &amp; override log</CardTitle></CardHeader>
        <CardContent>
          {payload.override_log.length === 0 ? (
            <p className="text-sm text-slate-500">No CA overrides recorded.</p>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Supplier</TableHead><TableHead>Invoice</TableHead>
                <TableHead>Decision</TableHead><TableHead>Note</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {payload.override_log.map((e, i) => (
                  <TableRow key={`${e.invoice_no ?? "?"}-${i}`}>
                    <TableCell>{e.supplier_name ?? "—"}</TableCell>
                    <TableCell className="font-medium">{e.invoice_no ?? "—"}</TableCell>
                    <TableCell><Badge variant="outline">{e.ca_override ?? "—"}</Badge></TableCell>
                    <TableCell className="text-slate-600">{e.ca_notes ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">4. Drafted reply</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {payload.drafted_reply?.body_html ? (
            <>
              <div className="prose prose-sm max-w-none"
                   dangerouslySetInnerHTML={{ __html: payload.drafted_reply.body_html }} />
              {payload.drafted_reply.citations.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Citations</p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-slate-600">
                    {payload.drafted_reply.citations.map((c, i) => (
                      <li key={i}>{String((c as Record<string, unknown>).source_ref ?? "citation")}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-slate-500">No reply drafted yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">5. Evidence index</CardTitle></CardHeader>
        <CardContent>
          {payload.evidence_index.length === 0 ? (
            <p className="text-sm text-slate-500">No evidence linked.</p>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Ref</TableHead><TableHead>Document</TableHead>
                <TableHead>Source type</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {payload.evidence_index.map((e) => (
                  <TableRow key={e.ref}>
                    <TableCell className="font-mono">{e.ref}</TableCell>
                    <TableCell>{e.filename}</TableCell>
                    <TableCell>{e.source_type.replace(/_/g, " ")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Field({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={tone === "warn" ? "font-semibold text-amber-700" : "text-slate-900"}>
        {value}
      </dd>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run src/components/working-papers/__tests__/AuditDefensePackView.test.tsx`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/working-papers/AuditDefensePackView.tsx frontend/src/components/working-papers/__tests__/AuditDefensePackView.test.tsx
git commit -m "feat(working-papers/fe): AuditDefensePackView component"
```

---

## Task 10: Frontend integration — API, detail page, header action, compose-from-notice

**Files:**
- Modify: `frontend/src/lib/working-papers/api.ts`
- Modify: `frontend/src/pages/WorkingPaperDetail.tsx`
- Modify: `frontend/src/components/working-papers/WorkingPaperHeader.tsx`
- Modify: the notice detail page (find with: `grep -rl "useNotice\|notices/" frontend/src/pages`)
- Test: `frontend/src/lib/working-papers/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing API test**

Append to `frontend/src/lib/working-papers/__tests__/api.test.ts` (follow the existing mock-axios pattern in that file):

```typescript
it("composeWorkingPaper sends notice_id for audit_defense_pack", async () => {
  const post = vi.fn().mockResolvedValue({ data: { working_paper_id: "wp-1" } })
  // Reuse the file's existing axios mock setup; assert the POST body:
  await composeWorkingPaper({ kind: "audit_defense_pack", notice_id: "n-1" })
  expect(post).toHaveBeenCalledWith(
    "/api/v1/working-papers/",
    { kind: "audit_defense_pack", notice_id: "n-1" },
  )
})

it("evidenceBundleUrl points at the bundle endpoint", () => {
  expect(evidenceBundleUrl("wp-1")).toContain("/api/v1/working-papers/wp-1/evidence-bundle")
})
```

(Match the existing test's mocking style; the key assertions are the request body and the URL.)

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/lib/working-papers/__tests__/api.test.ts`
Expected: FAIL (`composeWorkingPaper` rejects `notice_id` / `evidenceBundleUrl` undefined).

- [ ] **Step 3: Extend the API client**

In `frontend/src/lib/working-papers/api.ts`, update the compose request type and add the bundle URL helper:

```typescript
export interface ComposeWorkingPaperRequest {
  kind: "at_risk_itc_schedule" | "audit_defense_pack"
  reconciliation_id?: string
  notice_id?: string
}

export async function composeWorkingPaper(
  body: ComposeWorkingPaperRequest,
): Promise<{ working_paper_id: string }> {
  const { data } = await api.post("/api/v1/working-papers/", body)
  return data
}

export function evidenceBundleUrl(wpId: string): string {
  return `${API_BASE_URL}/api/v1/working-papers/${wpId}/evidence-bundle`
}
```

(Use the same base-URL/import the file already uses for `exportWorkingPaperUrl`. If `composeWorkingPaper` already exists, change its parameter to take the object above instead of positional args, and update existing callers — see Step 6.)

- [ ] **Step 4: Branch the detail page on kind**

In `frontend/src/pages/WorkingPaperDetail.tsx`, after the existing at-risk parse block, add an audit-pack branch. Replace the `payload`/render section so it dispatches on `kind`:

```typescript
import {
  atRiskItcSchedulePayloadSchema, auditDefensePackPayloadSchema,
  type AtRiskItcSchedulePayload, type AuditDefensePackPayload,
} from "@/types/workingPapers"
import { AuditDefensePackView } from "@/components/working-papers/AuditDefensePackView"

// ...inside the component, replacing the single-kind parse:
let body: React.ReactNode = null
let payloadError: string | null = null

if (workingPaper.kind === "at_risk_itc_schedule") {
  const parsed = atRiskItcSchedulePayloadSchema.safeParse(workingPaper.composed_json)
  if (parsed.success) {
    body = <AtRiskItcScheduleEditor workingPaper={workingPaper} payload={parsed.data} />
  } else {
    payloadError = parsed.error.issues.map(
      (i) => `${i.path.join(".") || "(root)"}: ${i.message}`).join("; ")
  }
} else if (workingPaper.kind === "audit_defense_pack") {
  const parsed = auditDefensePackPayloadSchema.safeParse(workingPaper.composed_json)
  if (parsed.success) {
    body = <AuditDefensePackView payload={parsed.data} />
  } else {
    payloadError = parsed.error.issues.map(
      (i) => `${i.path.join(".") || "(root)"}: ${i.message}`).join("; ")
  }
} else {
  payloadError = `Unsupported working paper kind: ${workingPaper.kind}`
}
```

Then render `{body ? body : <ErrorCard error={payloadError} />}` (reuse the existing error Card markup). Keep the header + staleness banner above it unchanged.

Note: the audit pack uses a read-only `AuditDefensePackView` (no editor in v0); CA commentary editing for packs is a future iteration. The header's notes/finalize/export still operate on the working paper.

- [ ] **Step 5: Add the evidence-bundle action + kind title in the header**

In `frontend/src/components/working-papers/WorkingPaperHeader.tsx`:

Add the title mapping:

```typescript
const KIND_TITLES: Record<string, string> = {
  at_risk_itc_schedule: "At-Risk ITC Schedule",
  audit_defense_pack: "Audit Defense Pack",
}
```

Import `evidenceBundleUrl` from the API module, and after the "Export PDF" anchor, add (only for packs):

```typescript
{workingPaper.kind === "audit_defense_pack" ? (
  <a
    href={evidenceBundleUrl(workingPaper.id)}
    download
    className={buttonVariants({ variant: "outline" })}
  >
    Evidence bundle (.zip)
  </a>
) : null}
```

- [ ] **Step 6: Add the compose-from-notice button + fix existing compose callers**

Find the notice detail page: `grep -rl "useNotice" frontend/src/pages`. On that page (mirror the "Generate At-Risk ITC Schedule" CTA pattern in `frontend/src/pages/ReconReport.tsx`), add a button:

```typescript
import { useNavigate, useParams } from "react-router-dom"
import { composeWorkingPaper } from "@/lib/working-papers/api"
import { toast } from "sonner"

// inside the component (clientId + noticeId from params/props):
async function handleGeneratePack() {
  try {
    const { working_paper_id } = await composeWorkingPaper({
      kind: "audit_defense_pack", notice_id: noticeId,
    })
    navigate(`/clients/${clientId}/working-papers/${working_paper_id}`)
  } catch (e) {
    toast.error((e as Error).message)
  }
}

// in JSX:
<Button onClick={handleGeneratePack}>Generate Audit Defense Pack</Button>
```

Update the existing At-Risk caller in `frontend/src/pages/ReconReport.tsx` to the new object form:

```typescript
const { working_paper_id } = await composeWorkingPaper({
  kind: "at_risk_itc_schedule", reconciliation_id: reconId,
})
```

- [ ] **Step 7: Run frontend tests + typecheck/build**

Run (from `frontend/`):
```bash
npx vitest run src/types src/lib/working-papers src/components/working-papers src/hooks
npm run build
```
Expected: all PASS; build succeeds (tsc clean).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/working-papers/api.ts frontend/src/pages/WorkingPaperDetail.tsx frontend/src/components/working-papers/WorkingPaperHeader.tsx frontend/src/pages/ReconReport.tsx frontend/src/lib/working-papers/__tests__/api.test.ts
# plus the notice detail page file found in Step 6
git commit -m "feat(working-papers/fe): wire audit defense pack — compose, view, evidence bundle"
```

---

## Task 11: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Backend full suite**

Run (from `backend/`): `python -m pytest -q`
Expected: all pass except the known pre-existing flaky live-Gemini test (`tests/ingestion/test_llm_gemini.py::test_map_columns_bangla_headers`), which passes on isolated re-run. Working-papers suite must be fully green.

- [ ] **Step 2: Frontend full suite + build**

Run (from `frontend/`): `npx vitest run && npm run build`
Expected: all pass; build clean.

- [ ] **Step 3: Manual sanity (optional, if a dev server + seeded data are available)**

Compose a pack from a notice that has a linked reconciliation; confirm the detail page renders all five sections, Export .docx works, and Evidence bundle (.zip) downloads with `00_binder.docx` + `MANIFEST.txt`.

- [ ] **Step 4: Push**

```bash
git push
```

---

## Notes for the implementer

- **Recipe-composes-recipe:** Task 3 calls `AtRiskItcScheduleRecipe().compose(...)`. In tests, patch `get_supabase_admin` on **both** `audit_defense_pack` and `at_risk_itc` modules (the provided test does this).
- **Staleness for packs:** the existing `get_working_paper` staleness check keys off a top-level `composed_json.summary`, which the pack payload does not have (its summary is nested under `reconciled_position`). So `is_stale` stays `false` for packs in v0 — acceptable and documented in the spec. Do not add pack-staleness in this plan.
- **No editor for packs in v0:** the detail page renders `AuditDefensePackView` read-only. Notes/finalize/export in the header still work because they operate on the generic working paper row.
- **Buckets are fixed in the recipe** (`recon-files`, `notices`); the evidence item carries `bucket` so the ZIP builder stays storage-agnostic.
