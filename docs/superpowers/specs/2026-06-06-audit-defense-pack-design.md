# Audit Defense Pack — Design Spec

**Date:** 2026-06-06
**Status:** Approved (design); pending implementation plan
**Author:** Founding-engineer session
**Depends on:** Working Papers Engine (`backend/app/working_papers/*`), At-Risk ITC Schedule recipe, Notice Drafter (`backend/app/notices/*`)

---

## 1. Goal

Add the second-and-third proof that the Working Papers Engine generalizes: a new recipe
`audit_defense_pack` that assembles, for **one received NBR notice**, a single
submission-ready rebuttal binder. The binder pulls together the notice, the
reconciled position (the At-Risk ITC working paper), the CA decision/override log,
the drafted reply with citations, and a numbered evidence index — and can also emit a
ZIP that bundles the actual evidence files.

This is the engine's first **recipe-composes-recipe** case: the reconciled-position
section is produced by calling the existing `AtRiskItcScheduleRecipe`, so the binder's
numbers tie out by construction and inherit every Phase-A correctness fix.

## 2. Anchor & scope (decided)

- **Anchor:** a specific NBR notice (`notice_id`). Everything else is derived.
- **Sections (all five required):** Notice summary · Reconciled position · Decision &
  override log · Drafted reply + citations · Evidence index.
- **Evidence set:** *linked artifacts only* — the reconciliation's two source files
  (purchase register + supplier data) and the NBR notice file itself. No client-wide
  document sweep in v0.
- **Output:** `.docx` binder is the default export; a separate **evidence-bundle ZIP**
  endpoint (binder + actual files) ships behind its own action.

## 3. Architecture (Approach C — snapshot structured, lazy binaries)

Snapshot **all structured content** into `composed_json` at compose time (immutable,
revisioned, frozen at finalize — identical to At-Risk ITC). **Never** put file bytes in
JSON: evidence binaries are referenced by `(bucket, storage_path)` and fetched from
Storage on-demand only when building the ZIP.

Why not the alternatives:
- *Reference/lazy (IDs only, resolve at export):* breaks the engine's immutability —
  a finalized legal binder could silently change, revisions become meaningless,
  staleness loses its anchor. Rejected.
- *Pure snapshot incl. file bytes:* bloats `composed_json` with binaries. Rejected; the
  ZIP carve-out keeps JSON small.

No new module. The feature is: one recipe + one renderer branch + one ZIP endpoint +
one kind-specific frontend view, all inside the existing `working_papers` package.

## 4. Data sources

| Section | Source |
|---|---|
| Notice summary | `notices` row: `notice_no, notice_date, notice_type, period_start/end, taxpayer_bin/tin, alleged_itc_claimed_bdt, alleged_itc_allowed_bdt, alleged_shortfall_bdt` |
| Reconciled position | `notices.linked_reconciliation_id` → call `AtRiskItcScheduleRecipe().compose(reconciliation_id=…)`; embed its `summary` + `supplier_groups` |
| Override log | `recon_line_items` where `ca_override is not null`, scoped to the linked recon: supplier, invoice, override, `ca_notes` |
| Drafted reply + citations | the **finalized** `notice_drafts` row for the notice if one exists, else the most recently `updated_at` draft: `body_html` (already sanitized at draft time), `citations` jsonb, `language`, `status` |
| Evidence index | recon source files (`vat_reconciliations.purchase_register_doc_id`, `supplier_data_doc_id` → `documents`) + the notice file (`notices.storage_path/original_filename`) |

**Evidence bucket hints (v0, deterministic):** recon source files live in the ingestion
bucket; the notice file lives in the notices bucket. Each evidence item carries an
explicit `bucket` so the ZIP builder downloads from the right place via
`sb.storage.from_(bucket).download(path)`.

## 5. Migration `0023_audit_defense_pack.sql`

```sql
ALTER TYPE working_paper_kind ADD VALUE 'audit_defense_pack';
ALTER TABLE working_papers
  ADD COLUMN notice_id uuid REFERENCES notices(id) ON DELETE SET NULL;
CREATE INDEX ix_working_papers_tenant_notice
  ON working_papers (tenant_id, notice_id) WHERE notice_id IS NOT NULL;
```

Notes:
- `ADD VALUE` is not *used* within this migration, so running it inside Supabase's
  transactional `apply_migration` is safe (PG only forbids using a new enum value in the
  same tx that adds it).
- `reconciliation_id` stays populated for the linked recon so the existing staleness
  check (`composed_json` aggregates vs live recon header) keeps working unchanged.

## 6. Payload model (`AuditDefensePackPayload`)

New Pydantic models in `working_papers/schemas.py`; mirrored Zod in
`frontend/src/types/workingPapers.ts`. All money fields serialize as decimal strings.

```
AuditDefensePackPayload:
  kind: Literal["audit_defense_pack"]
  recipe_version: str
  client_id, client_name, client_bin, client_tin
  notice_id
  notice: NoticeSummary            # no, date, type, period, alleged_{claimed,allowed,shortfall}_bdt
  reconciliation_id: UUID | None
  reconciled_position: AtRiskItcSchedulePayload | None   # reuse existing model; None if no linked recon
  override_log: list[OverrideLogEntry]   # supplier_name, supplier_bin, invoice_no, ca_override, ca_notes
  drafted_reply: DraftedReplyBlock | None  # language, status, body_html, citations[]
  evidence_index: list[EvidenceItem]      # ref ("E-01"), document_id|None, filename, source_type, bucket, storage_path
```

`reconciled_position` reuses `AtRiskItcSchedulePayload` verbatim — single source of
truth for the recon numbers. `drafted_reply` and `reconciled_position` are nullable so a
pack can be composed before a reply is drafted or for a notice with no linked recon
(degraded but valid).

Add `audit_defense_pack` to `WorkingPaperPayload` discriminated union and the
`_PAYLOAD_VALIDATORS` map in `service.py`.

## 7. Recipe (`recipes/audit_defense_pack.py`)

`AuditDefensePackRecipe` with `id="audit_defense_pack"`, `version="v1"`.
`compose(*, tenant_id, notice_id, **_)`:

1. Fetch the notice (tenant-scoped). If missing → raise (maps to compose error).
2. Fetch the client for name/BIN/TIN.
3. If `notice.linked_reconciliation_id`: `reconciled_position = await
   AtRiskItcScheduleRecipe().compose(tenant_id=…, reconciliation_id=…)`; build the
   override log from that recon's line items (single fetch, paginated like At-Risk ITC).
   Else both are empty.
4. Drafted reply for the notice → `drafted_reply`: the finalized `notice_drafts` row if
   one exists, else the most recently `updated_at` draft (sanitize defensively; it is
   already bleached at draft time). `None` if no draft exists yet.
5. Build `evidence_index`: recon PR file, recon supplier file, notice file — each with
   `E-0N` ref, filename, `source_type`, `bucket`, `storage_path`.
6. Return the payload dict; service validates against `AuditDefensePackPayload`.

Register in `recipes/__init__.py` so `get_recipe("audit_defense_pack")` resolves.

## 8. Service & router

- `ComposeWorkingPaperRequest` gains optional `notice_id`. Per-kind validation in
  `compose_working_paper`: `audit_defense_pack` requires `notice_id` (else
  `WorkingPaperInvalidStateError`); `at_risk_itc_schedule` still requires
  `reconciliation_id`.
- Persistence `create_working_paper` gains optional `notice_id`, written to the new
  column.
- New endpoint `GET /api/v1/working-papers/{wp_id}/evidence-bundle` → `StreamingResponse`
  of `application/zip`.

## 9. Evidence-bundle ZIP

`service.export_evidence_bundle(wp_id, tenant_id)`:
- Render the binder `.docx` (reuse `export_working_paper` docx path) → `00_binder.docx`.
- For each `evidence_index` item: `download(bucket, storage_path)`; add as
  `E-0N_<safe_filename>`. On failure, skip and record the reason.
- Always add `MANIFEST.txt`: each evidence ref, filename, included/missing + reason.
- Enforce a cumulative size cap (50 MB) → `WorkingPaperInvalidStateError` mapped to 413
  if exceeded.
- Return `(zip_bytes, "application/zip", "audit-defense-pack-<ref>.zip")`.

A small bucket-aware download helper (or direct `sb.storage.from_(bucket).download(path)`
off-thread) is used; no new storage module.

## 10. Rendering (`rendering.py`)

`render_docx` kind-dispatch adds `audit_defense_pack` →
`_render_audit_defense_pack(payload, notes_html, tenant, meta)`. Reuses the shared
helpers (`_fmt_bdt`, letterhead, page-number footer, sign-off, structure-preserving
notes). Layout:

1. **Cover** — firm letterhead; title "Audit Defense Pack"; working-paper reference;
   client name/BIN/TIN; "In response to Notice {no} dated {date}"; demand (alleged
   shortfall) prominent; prepared/reviewed-by.
2. **Notice summary** — table of the alleged figures + period.
3. **Reconciled position** — the At-Risk ITC summary table + per-supplier tables
   (reuse the existing builder helpers, factored to take a payload section).
4. **Decision & override log** — table: supplier, invoice, decision, note.
5. **Drafted reply** — heading + the reply body (HTML→docx block walk) + a citations
   list.
6. **Evidence index** — numbered table: ref, filename, source type. Footer note that
   files are provided in the evidence bundle ZIP.

Refactor: extract the At-Risk per-supplier/summary table emitters into small private
functions so both `_render_at_risk_itc_schedule` and the pack's section 3 share them
(DRY; no behavior change to the existing renderer — covered by existing tests).

## 11. Frontend

- `frontend/src/types/workingPapers.ts`: add the Zod schemas + discriminated payload;
  extend the kind constants and labels.
- `frontend/src/components/working-papers/AuditDefensePackView.tsx`: read-only renderer
  for the five sections (reuse `AtRiskItcScheduleView` for the reconciled position).
- `WorkingPaperDetail.tsx`: branch on `kind` to pick the view/editor; the staleness
  banner and header are kind-agnostic and already work.
- `WorkingPaperHeader.tsx`: when `kind === "audit_defense_pack"`, add a "Download
  evidence bundle (.zip)" action (anchor to the new endpoint).
- Notice detail page: a "Generate Audit Defense Pack" button that composes with
  `{ kind: "audit_defense_pack", notice_id }` and routes to the new working paper.
- API client + hooks: `composeWorkingPaper` accepts `notice_id`; add
  `evidenceBundleUrl(wpId)`.

## 12. Testing

- **Recipe** (`tests/working_papers/test_recipe_audit_defense_pack.py`, fake-Supabase
  harness): full assembly notice→recon→sections; reconciled position ties to the
  At-Risk recipe output; override log only includes overridden lines; evidence index has
  the three linked artifacts with correct buckets; graceful degradation when no linked
  recon and when no draft exists.
- **Rendering** (`test_rendering.py`): golden-text assertions that each of the six
  blocks renders; cover shows notice ref + demand; evidence table numbering; existing
  At-Risk rendering tests still pass after the table-emitter refactor.
- **ZIP** (`test_evidence_bundle.py`): stubbed Storage with one present + one missing
  file → ZIP contains `00_binder.docx`, `E-01_*`, a `MANIFEST.txt` listing the missing
  one; size-cap path raises.
- **Frontend**: Zod parse of a sample payload; `AuditDefensePackView` renders sections;
  compose-from-notice wiring.

## 13. Known v0 limitations (documented, not blockers)

- **Override log** has no per-line actor/timestamp — the `recon_line_items` table doesn't
  store who/when an override was set, so the log shows decision + note only. (Future:
  add `overridden_by/at` columns.)
- **Evidence is linked-artifacts-only.** Per-line document attachments and a client-wide
  evidence sweep are out of scope; added later via explicit linkage.
- **Override log uses `ca_notes`** as the rationale; there is no separate structured
  reason code.
- **ZIP downloads files synchronously** within the request; fine for the three-file v0,
  but a large future evidence set would want a background job + signed URL.

## 14. Out of scope

Audit hearing scheduler, multi-notice consolidated packs, e-signature, direct NBR portal
submission, storing the finalized ZIP immutably (relates to deferred At-Risk F8).
