# Combined Ingestion Wizard Design

**Status:** Approved — ready for implementation plan
**Date:** 2026-05-16
**Branch:** `phase-f-adaptive-ingestion`

## Goals

1. End the awful two-trip ingestion flow. The user uploads the purchase register (PR) and the supplier-filed export (SF) in **one continuous wizard** with no browser-back navigation between halves.
2. When a usable PR or SF document already exists for the same client + period, **offer to reuse it** instead of forcing a re-upload.
3. Fix the two backend issues caught in the prior smoke test:
   - `finalize_job`'s rollback-to-confirmed leaves the previous failure invisible in the UI.
   - `httpx.ReadError [WinError 10035]` on Python 3.14 + Windows under the default `ProactorEventLoop`.

## Non-goals

- No new doc types beyond PR + SF (a 3-doc flow would justify an `ingestion_sessions` table; not now).
- No persistent draft state for the entry-form (period + reuse choices). The user commits at the Start click.
- No bulk-upload / multi-period flows.

## Architecture

A *session* is a (PR, SF) pair, linked at the database level by `ingestion_jobs.linked_pr_job_id` on the SF row. The frontend wizard walks both halves sequentially:

```
Setup → Purchase register → Supplier export → Reconcile → Done
        (upload→extract→     (upload→extract→
         review→continue)     review→finalize)
```

Either half can be **skipped at session start** by reusing an existing canonical XLSX document. Reuse choices are persisted on the relevant job row (`reuse_pr_doc_id` / `reuse_sf_doc_id`) so the handoff can find them later.

If *both* halves are reused, no ingestion jobs are created at all — the `POST /ingestion/sessions/start` endpoint runs the reconciliation synchronously and returns the new `reconciliation_id`.

## Flow & URLs

| Step | URL | Backend state |
|---|---|---|
| 1 — Setup | `/clients/:id/ingestion/new` | nothing yet |
| 2 — Purchase register (skipped if reusing) | `/clients/:id/ingestion/:prJobId` | PR job `pending → extracting → ready_for_review → confirmed` |
| 3 — Supplier export (skipped if reusing) | same URL (or `/clients/:id/ingestion/:sfJobId` when PR is reused) | SF job `pending → … → confirmed` |
| 4 — Reconcile | same URL | SF finalize call → `RECONCILING`. PR `CONFIRMED → COMPLETED` on success. |
| 5 — Done | redirect to `/clients/:id/recon/:reconId` | both jobs `COMPLETED`, both carry the same `reconciliation_id` |

**Resume:** opening the wizard URL at any time reconstructs the active step from the combined state of the PR job + its `linked_sf_job_id` (looked up server-side).

## Backend changes

### Migration `0040_link_ingestion_jobs.sql`

```sql
ALTER TABLE ingestion_jobs
  ADD COLUMN linked_pr_job_id UUID NULL
    REFERENCES ingestion_jobs(id) ON DELETE SET NULL,
  ADD COLUMN reuse_pr_doc_id UUID NULL
    REFERENCES documents(id) ON DELETE SET NULL,
  ADD COLUMN reuse_sf_doc_id UUID NULL
    REFERENCES documents(id) ON DELETE SET NULL;

ALTER TABLE ingestion_jobs
  ADD CONSTRAINT linked_pr_job_kind_check
  CHECK (
    linked_pr_job_id IS NULL
    OR kind = 'supplier_export'
  );

CREATE INDEX ix_ingestion_jobs_linked_pr
  ON ingestion_jobs(linked_pr_job_id)
  WHERE linked_pr_job_id IS NOT NULL;
```

App-layer guards (in `service.create_job`) additionally ensure:
- The linked PR job is in the same tenant as the new SF job.
- The linked PR job is `kind = 'purchase_register'`.
- No other SF job already links to this PR job.

### Migration `0041_cleanup_stranded_ingestion_jobs.sql`

```sql
WITH stranded AS (
  SELECT j.id FROM ingestion_jobs j
  WHERE j.kind = 'purchase_register'
    AND j.status IN ('confirmed','ready_for_review')
    AND j.reconciliation_id IS NULL
    AND j.updated_at < now() - interval '7 days'
    AND NOT EXISTS (
      SELECT 1 FROM ingestion_jobs sf
      WHERE sf.linked_pr_job_id = j.id
    )
)
DELETE FROM ingestion_jobs WHERE id IN (SELECT id FROM stranded);

DELETE FROM documents
  WHERE doc_type = 'purchase_register'
    AND reconciliation_id IS NULL
    AND created_at < now() - interval '7 days'
    AND original_filename LIKE 'ingested_purchase_register_%';
```

Idempotent. `ingestion_files` and `ingestion_rows` cascade via existing FKs. Orphan canonical XLSX rows in `documents` are caught by the second DELETE.

### API changes

| Endpoint | Change |
|---|---|
| `POST /api/v1/ingestion/jobs` | New optional fields: `linked_pr_job_id`, `reuse_pr_doc_id`, `reuse_sf_doc_id`. Server validates linkage + reuse constraints. |
| `GET /api/v1/ingestion/jobs/:id` | Response gains `linked_pr_job_id` and computed `linked_sf_job_id` (reverse lookup). |
| `POST /api/v1/ingestion/sessions/start` *(new)* | Body: `{ client_id, period_start, period_end, reuse_pr_doc_id?, reuse_sf_doc_id? }`. Response: `{ pr_job_id?, sf_job_id?, reconciliation_id? }`. Both reuses set → runs handoff synchronously and returns `reconciliation_id`. PR reused only → creates SF job (with `reuse_pr_doc_id`) and returns `sf_job_id`. SF reused only → creates PR job (with `reuse_sf_doc_id`) and returns `pr_job_id`. Neither reused → creates PR job and returns `pr_job_id`. |
| `GET /api/v1/documents/recent` *(new — or extend existing list)* | Returns the most recent PR and SF docs for `client_id + period_start + period_end`. Drives the setup-step reuse UI. |

### Handoff path matrix

| Trigger | linked_pr_job_id | reuse_pr_doc_id (on SF job) | reuse_sf_doc_id (on PR job) | Behavior |
|---|---|---|---|---|
| Fresh both | set on SF | NULL | NULL | Build PR + SF canonical from both jobs' confirmed rows. Register both as documents. Run recon. Mark both jobs completed. |
| Reuse PR, fresh SF | NULL | set on SF | NULL | Build only SF canonical, register it, use existing PR doc id, run recon, mark SF completed. |
| Fresh PR, reuse SF | NULL | NULL | set on PR | Symmetric: build only PR canonical, use existing SF doc id. (PR finalize triggers this path.) |
| Reuse both | n/a (no jobs) | n/a | n/a | `sessions/start` runs `run_reconciliation` directly. |

In the "fresh PR, reuse SF" case the PR job's finalize endpoint becomes the trigger. The PR `ReviewStep`'s confirm button thus has two possible labels — "Continue to supplier export" (normal path) or "Run reconciliation" (when `reuse_sf_doc_id` is set on the PR job).

### Lifecycle change

In `app/ingestion/lifecycle.py`:

```python
_ALLOWED[JobStatus.CONFIRMED] = {
    JobStatus.RECONCILING,
    JobStatus.FAILED,
    JobStatus.COMPLETED,   # new: SF finalize completes the linked PR
}
```

`run_handoff` is extended so that when finalizing an SF job with `linked_pr_job_id`, it updates **both** jobs to `COMPLETED` and writes the same `reconciliation_id` to both rows in the success branch.

## Frontend changes

### New / changed files

| File | Type | Purpose |
|---|---|---|
| `frontend/src/pages/IngestionNew.tsx` | rewrite | Setup-step page |
| `frontend/src/components/ingestion/SetupStep.tsx` | new | Period picker + reuse-PR / reuse-SF checkboxes + Start button |
| `frontend/src/hooks/usePriorDocs.ts` | new | Queries `GET /documents/recent` for client+period |
| `frontend/src/hooks/useStartSession.ts` | new | `POST /ingestion/sessions/start`, routes the response |
| `frontend/src/components/ingestion/IngestionWizard.tsx` | rewrite | Step router from combined PR+SF state |
| `frontend/src/components/ingestion/Stepper.tsx` | rewrite | 5 high-level steps; `statusToStep(prJob, sfJob)` |
| `frontend/src/components/ingestion/PurchaseHalf.tsx` | new | Owns the PR sub-stepper |
| `frontend/src/components/ingestion/SupplierHalf.tsx` | new | Owns the SF sub-stepper |
| `frontend/src/components/ingestion/HalfHeader.tsx` | new | "Purchase register · Extracting" / "Reusing prior PR" banner |
| `frontend/src/components/ingestion/FinalizeStep.tsx` | edit | Render `error_summary` banner above Retry when `status=confirmed && error_summary != null`. Finalize calls the SF job. |
| `frontend/src/components/ingestion/UploadStep.tsx` | edit | Remove kind radio + period picker; both passed in as props |
| `frontend/src/components/ingestion/ReviewStep.tsx` | edit | Confirm-button label switches between "Continue to supplier export" and "Run reconciliation" |
| `frontend/src/hooks/useIngestion.ts` | edit | Add `useStartSession`; `useJob` returns new linkage fields |
| `frontend/src/types/ingestion.ts` | edit | Extend Zod schemas |
| `frontend/src/pages/IngestionJob.tsx` | edit | Page title shows session context |

### Combined state → step mapping

```
Inputs: prJob (or null if reused), sfJob (or null), reusePr, reuseSf

active_step =
  if prJob && !reusePr:
    sub('purchase_register', prJob.status)
  elif sfJob && !reuseSf:
    sub('supplier_export', sfJob.status)
  else:
    finalize

where sub(kind, status):
  pending|extracting     → ExtractingStep
  ready_for_review       → ReviewStep(half=kind)
  confirmed              → if kind == PR and prJob.reuse_sf_doc_id == null:
                              "Continue to supplier export" CTA
                            else:
                              FinalizeStep("Run reconciliation")
  reconciling|completed  → FinalizeStep
  failed                 → FinalizeStep failed-card with retry
```

### Wizard URL invariants

- When a PR job exists: URL is `/clients/:id/ingestion/:prJobId`. The wizard fetches the PR job; the server's `linked_sf_job_id` field tells the wizard whether an SF job has been created yet.
- When PR is reused: no PR job exists. URL is `/clients/:id/ingestion/:sfJobId`. The wizard detects this via `sfJob.reuse_pr_doc_id` being set, and renders only the SF half + finalize.

### State invariants

- **Half selection** is derived from server data — no client-only state for resume safety.
- **SF job creation is lazy** — the `Continue to supplier export` button only flips a local UI state. The SF job is created only when the user clicks Upload on the SF half (`POST /ingestion/jobs` with `linked_pr_job_id` set). This means a user who abandons after the PR confirm leaves no orphan SF job.
- The one piece of true client-only state is the in-progress `File[]` array before upload, kept in the half's own `useState`.

## Backend bug fixes

### Fix #1 — Surface `error_summary` after a failed finalize

`finalize_job` already writes `error_summary` and rolls back to `CONFIRMED` on `HandoffError`. The UI doesn't render it.

**Change:** `FinalizeStep.tsx` renders an error banner above the Retry button when `status === 'confirmed' && error_summary` is set. No backend lifecycle change — keeping the rollback-to-confirmed lets the user retry without an admin "FAILED → CONFIRMED" path.

### Fix #2 — Windows Python 3.14 `httpx.ReadError`

`backend/app/main.py`, at module top:

```python
import sys
import asyncio

# Python 3.14 on Windows defaults to ProactorEventLoop, which interacts poorly
# with httpx socket reads under load (intermittent [WinError 10035] non-blocking
# socket-op errors). Selector loop is stable.
# Refs: https://docs.python.org/3.14/library/asyncio-eventloop.html#asyncio.WindowsSelectorEventLoopPolicy
#       https://github.com/encode/httpx/issues (Windows known-issues thread)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

No-op on production (Linux). A skip-unless-Windows unit test asserts the policy is set after `main.py` import.

## Testing

### Backend (pytest)

| Test | Purpose |
|---|---|
| `test_session_start.py::test_reuse_both_runs_recon_synchronously` | Both reuses set → returns `reconciliation_id`, no jobs created |
| `…::test_fresh_pr_returns_pr_job_id` | No reuse → returns `pr_job_id` only |
| `…::test_reuse_pr_only_returns_sf_job_id` | `reuse_pr_doc_id` set → creates SF carrying it, returns its id |
| `…::test_reuse_sf_only_returns_pr_job_id` | Symmetric |
| `…::test_reuse_doc_id_validates_tenant` | Cross-tenant doc id → 403 |
| `…::test_reuse_doc_id_validates_kind` | PR id pointing to SF doc → 422 |
| `test_create_job_linking.py::test_linked_pr_job_id_must_be_pr` | Link to SF → 422 |
| `…::test_linked_pr_job_id_cross_tenant_rejected` | Cross-tenant link → 403 |
| `…::test_pr_job_with_linked_pr_job_id_rejected` | PR with linkage set → 422 (check constraint) |
| `…::test_double_link_rejected` | Two SF jobs link to same PR → 422 |
| `test_handoff_combined.py::test_handoff_builds_both_xlsx_from_linked_jobs` | SF finalize with linkage builds + registers both docs |
| `…::test_handoff_completes_both_jobs` | Both jobs → `completed` with same `reconciliation_id` |
| `…::test_handoff_reuse_pr_doc_id_uses_existing` | SF with `reuse_pr_doc_id` builds only SF canonical |
| `…::test_handoff_reuse_sf_doc_id_uses_existing` | Symmetric on PR finalize |
| `…::test_handoff_failure_writes_error_summary` | Existing test; verifies error_summary path still works |
| `test_lifecycle.py::test_confirmed_to_completed_allowed` | New transition allowed |
| `test_cleanup_stranded_migration.py` | Seed stranded + recent + linked-completed; only stranded deleted |
| `test_event_loop_policy.py::test_windows_selector_policy` | Skip-unless-Windows; policy is `WindowsSelectorEventLoopPolicy` after `main.py` import |

### Frontend (vitest + RTL)

| Test file | Cases |
|---|---|
| `IngestionNew.test.tsx` | No reuse offer when prior docs absent; reuse checkbox renders when present; both-reuse Start navigates to recon report; no-reuse Start navigates to wizard URL |
| `IngestionWizard.test.tsx` | Step routing matrix across all (prJob, sfJob, reuse flags) combinations |
| `Stepper.test.tsx` | 5-step labels + `statusToStep(prJob, sfJob)` |
| `FinalizeStep.test.tsx` | `status=confirmed && error_summary != null` → renders error banner |
| `PurchaseHalf.test.tsx` / `SupplierHalf.test.tsx` | Smoke render + "Continue" CTA flips half state without creating SF job |
| `usePriorDocs.test.ts` | Empty → null; populated → most recent per kind |

### Manual smoke (Playwright, post-implementation)

1. New ingestion (first run for client/period) → setup page shows period only.
2. Upload PR → extract → review → click "Continue to supplier export".
3. Upload SF (same URL, no browser-back) → extract → review → click "Run reconciliation".
4. Auto-redirect to recon report.
5. Start a second ingestion for the same client/period → setup page shows both reuse checkboxes → check both → Start → goes straight to recon report.
6. Force a handoff failure (e.g., empty confirmed rows) → confirm new error banner appears on Retry card.

## Rollout

- Single PR (frontend + backend together) on `phase-f-adaptive-ingestion`.
- Apply migrations 0040 + 0041 before deploy.
- No API-version bump — `POST /ingestion/jobs` extensions are backward-compatible.
- No feature flag. The only entry point (`/clients/:id/ingestion/new`) is replaced wholesale. The wizard URL `/clients/:id/ingestion/:jobId` continues to resume correctly because state is derived from server data.

## Open questions

None. All design decisions confirmed with user on 2026-05-16.
