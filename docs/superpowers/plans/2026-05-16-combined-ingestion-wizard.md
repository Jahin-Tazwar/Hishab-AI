# Combined Ingestion Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-trip ingestion flow with a single sequential wizard (PR → SF, with reuse-of-prior-docs). Fold in the two backend bugs caught in the prior smoke test.

**Spec:** `docs/superpowers/specs/2026-05-16-combined-ingestion-wizard-design.md`

**Architecture:**
A *session* is a (PR, SF) job pair linked by `ingestion_jobs.linked_pr_job_id` on the SF row. Either half can be skipped at session start by reusing an existing canonical XLSX (persisted on the relevant job row as `reuse_pr_doc_id` / `reuse_sf_doc_id`). A new `POST /api/v1/ingestion/sessions/start` endpoint creates the right jobs (or runs reconciliation directly when both halves are reused). The handoff is refactored so that the *terminal* finalize call (on the SF job when fresh, on the PR job when SF is reused, or on neither when both reused) builds and registers both canonical XLSX docs in one shot and transitions both jobs to `completed`.

**Tech Stack:**
- Backend: FastAPI, Pydantic 2, Supabase (PostgreSQL + RLS + Storage), structlog, pytest, openpyxl
- Frontend: React 19 + TypeScript, Vite, TanStack Query 5, Zod, react-hook-form, shadcn/ui, Tailwind, vitest + RTL, axios-mock-adapter

---

## File Structure

### Backend — new files

| File | Responsibility |
|---|---|
| `migrations/0016_link_ingestion_jobs.sql` | New columns + check constraint + index on `ingestion_jobs` |
| `migrations/0017_cleanup_stranded_ingestion_jobs.sql` | Delete stranded PR jobs > 7d old + their unreferenced canonical docs |
| `backend/tests/ingestion/test_session_start.py` | API tests for new `POST /ingestion/sessions/start` |
| `backend/tests/ingestion/test_create_job_linking.py` | Validation tests for new `linked_pr_job_id` / `reuse_*_doc_id` fields on `POST /jobs` |
| `backend/tests/ingestion/test_handoff_combined.py` | Handoff tests covering all four path-matrix cases |
| `backend/tests/ingestion/test_documents_recent.py` | API tests for new `GET /documents/recent` |
| `backend/tests/test_event_loop_policy.py` | Skip-unless-Windows assertion that selector loop is installed |

### Backend — modified files

| File | Change |
|---|---|
| `backend/app/main.py` | Pin `WindowsSelectorEventLoopPolicy` on Windows |
| `backend/app/ingestion/schemas.py` | Extend `CreateJobRequest`, `JobOut`; add `SessionStartRequest`, `SessionStartResponse`, `RecentDocsOut` |
| `backend/app/ingestion/lifecycle.py` | Add `CONFIRMED → COMPLETED` transition |
| `backend/app/ingestion/persistence.py` | Extend `create_job` (accept new columns); extend `get_job` to compute `linked_sf_job_id` reverse lookup; add `find_recent_docs`, `find_doc_by_id`, `complete_jobs_pair` helpers |
| `backend/app/ingestion/service.py` | Extend `create_job` (validate new fields); refactor `finalize_job` (combined-handoff path); add `start_session`; helper `validate_linked_pr_job` and `validate_reuse_doc` |
| `backend/app/ingestion/handoff.py` | Refactor `_resolve_doc_ids` to: (a) build canonical for linked PR job when `linked_pr_job_id` is set on SF job, (b) use `reuse_*_doc_id` when set, (c) mark both jobs completed on success |
| `backend/app/ingestion/router.py` | Extend `POST /jobs` form fields; new `POST /sessions/start`; new `GET /documents/recent`; extend `_job_row_to_out` to include linkage fields |
| `backend/tests/ingestion/test_lifecycle.py` | New test for `CONFIRMED → COMPLETED` transition |
| `backend/tests/ingestion/test_handoff.py` | Keep round-trip test; add row-based canonical-build helper test |

### Frontend — new files

| File | Responsibility |
|---|---|
| `frontend/src/components/ingestion/SetupStep.tsx` | The new entry form: period + reuse checkboxes + Start button |
| `frontend/src/components/ingestion/HalfHeader.tsx` | "Purchase register · Extracting" / "Reusing prior PR" banner |
| `frontend/src/components/ingestion/PurchaseHalf.tsx` | Owns PR sub-stepper (upload/extract/review/continue) |
| `frontend/src/components/ingestion/SupplierHalf.tsx` | Owns SF sub-stepper (upload/extract/review/finalize) |
| `frontend/src/hooks/usePriorDocs.ts` | Queries `GET /ingestion/documents/recent` |
| `frontend/src/hooks/__tests__/usePriorDocs.test.tsx` | Test for usePriorDocs |
| `frontend/src/components/ingestion/__tests__/SetupStep.test.tsx` | Test for SetupStep render + submit |
| `frontend/src/components/ingestion/__tests__/IngestionWizard.test.tsx` | Test for step-routing matrix |
| `frontend/src/components/ingestion/__tests__/Stepper.test.tsx` | Test for 5-step `statusToStep(prJob, sfJob)` |
| `frontend/src/components/ingestion/__tests__/FinalizeStep.test.tsx` | Test for error_summary banner |

### Frontend — modified files

| File | Change |
|---|---|
| `frontend/src/types/ingestion.ts` | Extend `JobOut` (linkage + reuse fields); add `SessionStartRequest/Response`, `RecentDocsOut` |
| `frontend/src/lib/ingestion/api.ts` | Extend `createJob` (optional `linked_pr_job_id`, `reuse_*_doc_id`); add `startSession`, `fetchRecentDocs` |
| `frontend/src/hooks/useIngestion.ts` | Add `useStartSession` |
| `frontend/src/components/ingestion/Stepper.tsx` | 5 steps, new `statusToStep(prJob, sfJob)` |
| `frontend/src/components/ingestion/UploadStep.tsx` | Remove kind/period selectors; accept as props; optional `linkedPrJobId` & `reuseSfDocId` props |
| `frontend/src/components/ingestion/ReviewStep.tsx` | Dynamic button label ("Continue to supplier export" vs "Run reconciliation") via `confirmCtaLabel` prop |
| `frontend/src/components/ingestion/FinalizeStep.tsx` | Render `error_summary` banner; accept a `finalizeJobId` override prop |
| `frontend/src/components/ingestion/IngestionWizard.tsx` | Rewrite as combined PR+SF step router |
| `frontend/src/pages/IngestionNew.tsx` | Rewrite — renders `SetupStep` only |
| `frontend/src/pages/IngestionJob.tsx` | Pass through `prJobId` to wizard (unchanged in shape) |

---

## Working assumptions

- **Branch:** `phase-f-adaptive-ingestion` (work continues here; do NOT create a new branch unless the human asks).
- **Migration numbering:** the highest existing migration is `0015_ingestion_storage_bucket.sql`. New numbers are 0016 and 0017.
- **Commits:** small + frequent. One commit per task minimum; multi-step tasks may produce 2–3 commits where indicated.
- **Test gating:** the same `INGESTION_TEST_SUPABASE_URL`/`INGESTION_TEST_USER_JWT` env-var pack used by `tests/ingestion/test_api.py` gates every new live-DB test. Pure-logic tests (`test_lifecycle.py`, the canonical-XLSX round-trip) run unconditionally.
- **Naming:** Python `snake_case`, TS `camelCase` for vars, `PascalCase` for types/components. JSON field names are `snake_case` everywhere to match existing endpoints.

---

## Task 1: Migration 0016 — link & reuse columns

**Files:**
- Create: `migrations/0016_link_ingestion_jobs.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0016_link_ingestion_jobs.sql
-- Adds session linkage + reuse-prior-doc columns to ingestion_jobs so the
-- combined wizard can pair a PR job with its SF job and carry "reuse this
-- canonical doc instead of building one" intent across requests.

ALTER TABLE ingestion_jobs
  ADD COLUMN linked_pr_job_id uuid NULL
    REFERENCES ingestion_jobs(id) ON DELETE SET NULL,
  ADD COLUMN reuse_pr_doc_id  uuid NULL
    REFERENCES documents(id) ON DELETE SET NULL,
  ADD COLUMN reuse_sf_doc_id  uuid NULL
    REFERENCES documents(id) ON DELETE SET NULL;

-- Only SF jobs may carry a link to a PR job; only PR jobs may carry
-- reuse_sf_doc_id; only SF jobs may carry reuse_pr_doc_id.
ALTER TABLE ingestion_jobs
  ADD CONSTRAINT ingestion_jobs_linked_pr_kind_check CHECK (
    linked_pr_job_id IS NULL OR kind = 'supplier_export'
  ),
  ADD CONSTRAINT ingestion_jobs_reuse_pr_kind_check CHECK (
    reuse_pr_doc_id IS NULL OR kind = 'supplier_export'
  ),
  ADD CONSTRAINT ingestion_jobs_reuse_sf_kind_check CHECK (
    reuse_sf_doc_id IS NULL OR kind = 'purchase_register'
  );

-- Reverse-lookup index: given a PR job id, find the SF job that linked to it.
CREATE INDEX ix_ingestion_jobs_linked_pr
  ON ingestion_jobs(linked_pr_job_id)
  WHERE linked_pr_job_id IS NOT NULL;
```

- [ ] **Step 2: Apply migration via psql against the dev project (or paste into Supabase SQL editor)**

Expected: `ALTER TABLE` + `CREATE INDEX` all succeed; running it twice is intentionally not supported (use a fresh DB or drop the columns manually if re-running).

- [ ] **Step 3: Sanity-check via SQL**

Run:
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'ingestion_jobs'
  AND column_name IN ('linked_pr_job_id','reuse_pr_doc_id','reuse_sf_doc_id');
```
Expected: 3 rows, all `uuid`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0016_link_ingestion_jobs.sql
git commit -m "feat(db): add linkage + reuse-doc columns to ingestion_jobs"
```

---

## Task 2: Migration 0017 — stranded-job cleanup

**Files:**
- Create: `migrations/0017_cleanup_stranded_ingestion_jobs.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0017_cleanup_stranded_ingestion_jobs.sql
-- Removes PR-only ingestion jobs left over from the broken two-trip flow:
-- status confirmed/ready_for_review, > 7 days old, never reconciled, never
-- linked from an SF job. Their canonical XLSX docs (if any) are pruned too.
--
-- ingestion_files and extracted_rows cascade via existing FKs.

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

-- Orphan canonical XLSX rows: created by the old per-job finalize-then-fail
-- path, never referenced by a vat_reconciliations row.
DELETE FROM documents
WHERE doc_type = 'purchase_register'
  AND created_at < now() - interval '7 days'
  AND original_filename LIKE 'ingested_purchase_register_%'
  AND NOT EXISTS (
    SELECT 1 FROM vat_reconciliations r
    WHERE r.purchase_register_doc_id = documents.id
       OR r.supplier_data_doc_id     = documents.id
  );
```

- [ ] **Step 2: Apply migration**

Run against the dev project (Supabase SQL editor or psql).
Expected: `DELETE` count is small (≤ a handful) and the statement completes.

- [ ] **Step 3: Sanity-check**

Run:
```sql
SELECT COUNT(*) FROM ingestion_jobs
WHERE kind = 'purchase_register'
  AND status IN ('confirmed','ready_for_review')
  AND reconciliation_id IS NULL
  AND updated_at < now() - interval '7 days'
  AND NOT EXISTS (SELECT 1 FROM ingestion_jobs sf WHERE sf.linked_pr_job_id = ingestion_jobs.id);
```
Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0017_cleanup_stranded_ingestion_jobs.sql
git commit -m "chore(db): delete stranded confirmed PR jobs and their orphan docs"
```

---

## Task 3: Lifecycle — allow `CONFIRMED → COMPLETED`

**Files:**
- Modify: `backend/app/ingestion/lifecycle.py`
- Test: `backend/tests/ingestion/test_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/ingestion/test_lifecycle.py`:

```python
def test_confirmed_to_completed_allowed_for_linked_pr_completion():
    # When an SF finalize succeeds, the linked PR job is moved from
    # confirmed to completed without ever passing through reconciling.
    assert_can_transition(JobStatus.CONFIRMED, JobStatus.COMPLETED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/ingestion/test_lifecycle.py::test_confirmed_to_completed_allowed_for_linked_pr_completion -v`
Expected: FAIL with `InvalidStateTransitionError: confirmed → completed`.

- [ ] **Step 3: Extend the allowed map**

Edit `backend/app/ingestion/lifecycle.py`, replace the `_ALLOWED` dict:

```python
_ALLOWED: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING:           {JobStatus.EXTRACTING, JobStatus.FAILED},
    JobStatus.EXTRACTING:        {JobStatus.READY_FOR_REVIEW, JobStatus.FAILED},
    JobStatus.READY_FOR_REVIEW:  {JobStatus.CONFIRMED, JobStatus.FAILED},
    JobStatus.CONFIRMED:         {JobStatus.RECONCILING, JobStatus.FAILED, JobStatus.COMPLETED},
    JobStatus.RECONCILING:       {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CONFIRMED},
    JobStatus.COMPLETED:         set(),
    JobStatus.FAILED:            set(),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/ingestion/test_lifecycle.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/lifecycle.py backend/tests/ingestion/test_lifecycle.py
git commit -m "feat(ingestion): allow CONFIRMED to COMPLETED for linked-PR completion"
```

---

## Task 4: Schemas — extend `CreateJobRequest`, `JobOut`; add session + recent-docs schemas

**Files:**
- Modify: `backend/app/ingestion/schemas.py`

- [ ] **Step 1: Add the new fields and schemas**

Edit `backend/app/ingestion/schemas.py`:

1. Add to `CreateJobRequest` (after the existing fields, before the `_period_ordered` validator):

```python
    linked_pr_job_id: Optional[UUID] = None
    reuse_pr_doc_id: Optional[UUID] = None
    reuse_sf_doc_id: Optional[UUID] = None
```

2. Add to `JobOut` (after `reconciliation_id`):

```python
    linked_pr_job_id: Optional[UUID] = None
    linked_sf_job_id: Optional[UUID] = None
    reuse_pr_doc_id: Optional[UUID] = None
    reuse_sf_doc_id: Optional[UUID] = None
```

3. Append new schemas at the bottom of the file:

```python
# ── Session start (new combined wizard entry point) ──────────────────────


class SessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    period_start: date
    period_end: date
    reuse_pr_doc_id: Optional[UUID] = None
    reuse_sf_doc_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _period_ordered(self) -> "SessionStartRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class SessionStartResponse(BaseModel):
    """Exactly one of the three IDs (or only `reconciliation_id`) is set.

    - Both reuses: only `reconciliation_id`.
    - PR fresh: `pr_job_id` only.
    - PR reused, SF fresh: `sf_job_id` only (SF job carries reuse_pr_doc_id).
    - PR fresh, SF reused: `pr_job_id` only (PR job carries reuse_sf_doc_id).
    """

    pr_job_id: Optional[UUID] = None
    sf_job_id: Optional[UUID] = None
    reconciliation_id: Optional[UUID] = None


# ── Recent documents (drives the reuse UI) ───────────────────────────────


class RecentDoc(BaseModel):
    id: UUID
    doc_type: str  # 'purchase_register' | 'supplier_export'
    original_filename: str
    file_size_bytes: Optional[int] = None
    created_at: datetime


class RecentDocsOut(BaseModel):
    pr: Optional[RecentDoc] = None
    sf: Optional[RecentDoc] = None
```

- [ ] **Step 2: Verify Pydantic still imports cleanly**

Run: `cd backend && python -c "from app.ingestion.schemas import CreateJobRequest, JobOut, SessionStartRequest, SessionStartResponse, RecentDocsOut; print('ok')"`
Expected: prints `ok`. No `ImportError` or validation errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/ingestion/schemas.py
git commit -m "feat(ingestion): schemas for linkage, reuse, sessions, recent docs"
```

---

## Task 5: Persistence — extend `create_job` + `get_job`; add helpers

**Files:**
- Modify: `backend/app/ingestion/persistence.py`

- [ ] **Step 1: Extend `create_job` signature and insert payload**

Replace the existing `create_job` function (lines ~33–60) with:

```python
async def create_job(
    *,
    tenant_id: UUID,
    client_id: UUID,
    created_by: UUID,
    kind: JobKind,
    period_start: date,
    period_end: date,
    linked_pr_job_id: Optional[UUID] = None,
    reuse_pr_doc_id: Optional[UUID] = None,
    reuse_sf_doc_id: Optional[UUID] = None,
) -> UUID:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "client_id": str(client_id),
        "created_by": str(created_by),
        "kind": kind.value,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "status": JobStatus.PENDING.value,
    }
    if linked_pr_job_id is not None:
        payload["linked_pr_job_id"] = str(linked_pr_job_id)
    if reuse_pr_doc_id is not None:
        payload["reuse_pr_doc_id"] = str(reuse_pr_doc_id)
    if reuse_sf_doc_id is not None:
        payload["reuse_sf_doc_id"] = str(reuse_sf_doc_id)

    def _insert():
        return sb.table(_TBL_JOBS).insert(payload).execute()

    res = await asyncio.to_thread(_insert)
    return UUID(res.data[0]["id"])
```

- [ ] **Step 2: Add `find_linked_sf_job_id` helper**

Append after `get_job`:

```python
async def find_linked_sf_job_id(
    pr_job_id: UUID, *, tenant_id: UUID,
) -> Optional[UUID]:
    """Reverse lookup: given a PR job, find the SF job that linked to it."""
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_JOBS)
            .select("id")
            .eq("linked_pr_job_id", str(pr_job_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return UUID(res.data[0]["id"]) if res.data else None
```

- [ ] **Step 3: Add `find_recent_docs` helper**

Append further down:

```python
async def find_recent_docs(
    *, tenant_id: UUID, client_id: UUID,
    period_start: date, period_end: date,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Most-recent PR + SF documents matching the (client, period) tuple."""
    sb = get_supabase_admin()

    def _q(doc_type: str) -> Optional[dict[str, Any]]:
        res = (
            sb.table("documents")
            .select("id, doc_type, original_filename, file_size_bytes, created_at")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .eq("doc_type", doc_type)
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    pr = await asyncio.to_thread(_q, "purchase_register")
    sf = await asyncio.to_thread(_q, "supplier_export")
    return pr, sf
```

- [ ] **Step 4: Add `find_doc_by_id` helper**

Append after `find_recent_docs`:

```python
async def find_doc_by_id(
    doc_id: UUID, *, tenant_id: UUID, client_id: UUID,
) -> Optional[dict[str, Any]]:
    """Lookup a single document scoped to the caller's tenant + client."""
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("documents")
            .select("id, doc_type, tenant_id, client_id, storage_path, deleted_at")
            .eq("id", str(doc_id))
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None
```

- [ ] **Step 5: Add `complete_jobs_pair` helper**

Append after `find_doc_by_id`:

```python
async def complete_jobs_pair(
    *, primary_job_id: UUID, partner_job_id: Optional[UUID],
    tenant_id: UUID, reconciliation_id: UUID,
) -> None:
    """Atomic-ish: mark primary + partner (if set) as COMPLETED with the
    same reconciliation_id. Two updates; not wrapped in a DB transaction
    because supabase-py's PostgREST client does not expose one — the
    caller invokes this only after `run_reconciliation` has succeeded,
    so a partial failure here surfaces in logs and a manual re-run.
    """
    await update_job_status(
        primary_job_id, JobStatus.COMPLETED, tenant_id=tenant_id,
        reconciliation_id=reconciliation_id,
    )
    if partner_job_id is not None:
        await update_job_status(
            partner_job_id, JobStatus.COMPLETED, tenant_id=tenant_id,
            reconciliation_id=reconciliation_id,
        )
```

- [ ] **Step 6: Smoke-import**

Run: `cd backend && python -c "from app.ingestion.persistence import create_job, find_linked_sf_job_id, find_recent_docs, find_doc_by_id, complete_jobs_pair; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/ingestion/persistence.py
git commit -m "feat(ingestion): persistence helpers for linkage, reuse, recent docs"
```

---

## Task 6: Service — validation + finalize refactor + start_session

**Files:**
- Modify: `backend/app/ingestion/service.py`

- [ ] **Step 1: Add validation helpers**

Insert near the top of `backend/app/ingestion/service.py`, after the `_MAX_BYTES` line:

```python
from app.ingestion.exceptions import (
    FileTooLargeError,
    HandoffError,
    JobNotFoundError,
    IngestionError,
    UnsupportedFileTypeError,
)


async def _validate_linked_pr_job(
    *, linked_pr_job_id: UUID, kind: JobKind, tenant_id: UUID,
) -> None:
    if kind != JobKind.SUPPLIER_EXPORT:
        err = IngestionError(message="linked_pr_job_id only valid on supplier_export jobs")
        err.code = "INGESTION_BAD_LINKAGE"
        err.status_code = 422
        raise err
    linked = await p.get_job(linked_pr_job_id, tenant_id=tenant_id)
    if linked is None:
        err = IngestionError(message=f"linked PR job {linked_pr_job_id} not found")
        err.code = "INGESTION_BAD_LINKAGE"
        err.status_code = 422
        raise err
    if linked["kind"] != JobKind.PURCHASE_REGISTER.value:
        err = IngestionError(message="linked job must be a purchase_register")
        err.code = "INGESTION_BAD_LINKAGE"
        err.status_code = 422
        raise err
    existing = await p.find_linked_sf_job_id(linked_pr_job_id, tenant_id=tenant_id)
    if existing is not None:
        err = IngestionError(message=f"PR job {linked_pr_job_id} already linked to SF job {existing}")
        err.code = "INGESTION_DUPLICATE_LINKAGE"
        err.status_code = 422
        raise err


async def _validate_reuse_doc(
    *, doc_id: UUID, expected_type: str, tenant_id: UUID, client_id: UUID,
) -> None:
    doc = await p.find_doc_by_id(doc_id, tenant_id=tenant_id, client_id=client_id)
    if doc is None:
        err = IngestionError(message=f"reuse doc {doc_id} not found for this client")
        err.code = "INGESTION_BAD_REUSE"
        err.status_code = 422
        raise err
    if doc["doc_type"] != expected_type:
        err = IngestionError(
            message=f"reuse doc {doc_id} is {doc['doc_type']}, expected {expected_type}"
        )
        err.code = "INGESTION_BAD_REUSE"
        err.status_code = 422
        raise err
```

Then update the existing top-of-file `from app.ingestion.exceptions import …` block to remove the now-duplicate imports (the new import block above supersedes it).

- [ ] **Step 2: Extend `create_job` signature + validation**

Modify the `create_job` function (lines ~46–121). Change the signature to add the three new fields and add validation at the top:

```python
async def create_job(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    kind: JobKind,
    files: list[UploadFile],
    linked_pr_job_id: Optional[UUID] = None,
    reuse_pr_doc_id: Optional[UUID] = None,
    reuse_sf_doc_id: Optional[UUID] = None,
) -> CreateJobResponse:
    if not files:
        raise UnsupportedFileTypeError(filename="", mime="(no files)")
    if len(files) > _MAX_FILES:
        raise UnsupportedFileTypeError(
            filename=f"<{len(files)} files>",
            mime=f"max {_MAX_FILES} files per job",
        )

    # New validations — fail fast before creating the job row.
    if linked_pr_job_id is not None:
        await _validate_linked_pr_job(
            linked_pr_job_id=linked_pr_job_id, kind=kind, tenant_id=tenant_id,
        )
    if reuse_pr_doc_id is not None:
        if kind != JobKind.SUPPLIER_EXPORT:
            err = IngestionError(message="reuse_pr_doc_id only valid on supplier_export jobs")
            err.code = "INGESTION_BAD_REUSE"; err.status_code = 422
            raise err
        await _validate_reuse_doc(
            doc_id=reuse_pr_doc_id, expected_type="purchase_register",
            tenant_id=tenant_id, client_id=client_id,
        )
    if reuse_sf_doc_id is not None:
        if kind != JobKind.PURCHASE_REGISTER:
            err = IngestionError(message="reuse_sf_doc_id only valid on purchase_register jobs")
            err.code = "INGESTION_BAD_REUSE"; err.status_code = 422
            raise err
        await _validate_reuse_doc(
            doc_id=reuse_sf_doc_id, expected_type="supplier_export",
            tenant_id=tenant_id, client_id=client_id,
        )

    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=kind, period_start=period_start, period_end=period_end,
        linked_pr_job_id=linked_pr_job_id,
        reuse_pr_doc_id=reuse_pr_doc_id,
        reuse_sf_doc_id=reuse_sf_doc_id,
    )
    # ── (the rest of the existing body: per-file accept/reject loop +
    #     asyncio.create_task(claim_and_run(...)) — UNCHANGED)
```

Add `Optional` to the existing `from typing` line if not already present.

- [ ] **Step 3: Add the new `IngestionError.status_code` attribute support**

Check `backend/app/ingestion/exceptions.py` — the existing `IngestionError` already has `status_code` (used by the router for HTTPException mapping). If it does not, add it as a class attribute defaulting to 400 in that file. (Run `grep -n status_code backend/app/ingestion/exceptions.py` first — if found, skip this step.)

- [ ] **Step 4: Refactor `finalize_job` to handle the linked-job completion path**

Replace the existing `finalize_job` (lines ~124–170) with:

```python
async def finalize_job(*, job_id: UUID, tenant_id: UUID) -> UUID:
    """Idempotent. Validates needs_review == 0; runs combined handoff.

    The handoff (run_handoff) inspects the job's linkage / reuse fields to
    decide which canonical XLSX files to build, which to reuse, and which
    sibling job (if any) to also mark COMPLETED on success.
    """
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise JobNotFoundError(message=f"Job {job_id} not found")

    current = JobStatus(job["status"])
    if current == JobStatus.COMPLETED:
        if job["reconciliation_id"]:
            return UUID(job["reconciliation_id"])
        raise HandoffError(message="Completed job has no reconciliation_id")

    needs = await p.count_needs_review(job_id, tenant_id=tenant_id)
    if needs > 0:
        err = IngestionError(message=f"{needs} rows still need review")
        err.code = "INGESTION_REVIEW_INCOMPLETE"
        err.status_code = 422
        raise err

    if current == JobStatus.READY_FOR_REVIEW:
        assert_can_transition(current, JobStatus.CONFIRMED)
        await p.update_job_status(job_id, JobStatus.CONFIRMED, tenant_id=tenant_id)

    assert_can_transition(JobStatus.CONFIRMED, JobStatus.RECONCILING)
    await p.update_job_status(job_id, JobStatus.RECONCILING, tenant_id=tenant_id)

    try:
        recon_id = await run_handoff(job_id=job_id, tenant_id=tenant_id)
    except Exception as e:
        log.exception("ingestion.finalize.handoff_failed",
                      job_id=str(job_id), error=str(e))
        await p.update_job_status(
            job_id, JobStatus.CONFIRMED, tenant_id=tenant_id,
            error_summary=str(e)[:500],
        )
        raise

    # The handoff is responsible for marking *both* this job and its
    # linked partner (if any) COMPLETED with the same reconciliation_id.
    # We re-read here only as a safety net for the unlinked case.
    refreshed = await p.get_job(job_id, tenant_id=tenant_id)
    if refreshed and refreshed["status"] != JobStatus.COMPLETED.value:
        await p.update_job_status(
            job_id, JobStatus.COMPLETED, tenant_id=tenant_id,
            reconciliation_id=recon_id,
        )
    return recon_id
```

- [ ] **Step 5: Add `start_session` orchestration**

Append to `backend/app/ingestion/service.py`:

```python
async def start_session(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    reuse_pr_doc_id: Optional[UUID] = None,
    reuse_sf_doc_id: Optional[UUID] = None,
) -> dict[str, Optional[UUID]]:
    """Implements the four reuse-combinations from the spec.

    Returns a dict with exactly one of:
      - {'reconciliation_id': UUID}     when both reuses are set
      - {'pr_job_id': UUID}             when PR is fresh (regardless of SF reuse)
      - {'sf_job_id': UUID}             when PR is reused and SF is fresh
    """
    # Validate any reuse refs upfront.
    if reuse_pr_doc_id is not None:
        await _validate_reuse_doc(
            doc_id=reuse_pr_doc_id, expected_type="purchase_register",
            tenant_id=tenant_id, client_id=client_id,
        )
    if reuse_sf_doc_id is not None:
        await _validate_reuse_doc(
            doc_id=reuse_sf_doc_id, expected_type="supplier_export",
            tenant_id=tenant_id, client_id=client_id,
        )

    # Case A: both reused — run reconciliation directly.
    if reuse_pr_doc_id is not None and reuse_sf_doc_id is not None:
        from app.reconciliation.schemas import ReconciliationCreateRequest
        from app.reconciliation.service import run_reconciliation
        recon_id = await run_reconciliation(
            ReconciliationCreateRequest(
                client_id=client_id,
                period_start=period_start,
                period_end=period_end,
                purchase_register_doc_id=reuse_pr_doc_id,
                supplier_data_doc_id=reuse_sf_doc_id,
            ),
            tenant_id=tenant_id, user_id=user_id,
        )
        return {"reconciliation_id": recon_id, "pr_job_id": None, "sf_job_id": None}

    # Case B: PR reused, SF fresh — create the SF job carrying reuse_pr_doc_id.
    if reuse_pr_doc_id is not None and reuse_sf_doc_id is None:
        sf_job_id = await p.create_job(
            tenant_id=tenant_id, client_id=client_id, created_by=user_id,
            kind=JobKind.SUPPLIER_EXPORT,
            period_start=period_start, period_end=period_end,
            reuse_pr_doc_id=reuse_pr_doc_id,
        )
        return {"reconciliation_id": None, "pr_job_id": None, "sf_job_id": sf_job_id}

    # Case C: PR fresh, SF reused — create the PR job carrying reuse_sf_doc_id.
    if reuse_pr_doc_id is None and reuse_sf_doc_id is not None:
        pr_job_id = await p.create_job(
            tenant_id=tenant_id, client_id=client_id, created_by=user_id,
            kind=JobKind.PURCHASE_REGISTER,
            period_start=period_start, period_end=period_end,
            reuse_sf_doc_id=reuse_sf_doc_id,
        )
        return {"reconciliation_id": None, "pr_job_id": pr_job_id, "sf_job_id": None}

    # Case D: both fresh — create the PR job; SF job is created lazily by the
    # wizard's SF upload step once the user provides files.
    pr_job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=period_start, period_end=period_end,
    )
    return {"reconciliation_id": None, "pr_job_id": pr_job_id, "sf_job_id": None}
```

- [ ] **Step 6: Smoke-import**

Run: `cd backend && python -c "from app.ingestion.service import create_job, finalize_job, start_session, _validate_linked_pr_job, _validate_reuse_doc; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/ingestion/service.py
git commit -m "feat(ingestion): create_job + finalize_job + start_session for combined wizard"
```

---

## Task 7: Handoff — combined-doc build + dual completion

**Files:**
- Modify: `backend/app/ingestion/handoff.py`

- [ ] **Step 1: Add a helper for building+uploading+registering a single canonical XLSX**

In `backend/app/ingestion/handoff.py`, factor out the upload-and-register block from `_resolve_doc_ids` into a private helper. Insert before `_resolve_doc_ids`:

```python
async def _build_and_register_canonical(
    *,
    tenant_id: UUID, client_id: UUID, user_id: UUID,
    job_id: str, kind: JobKind, rows: list[ExtractedRowData],
) -> UUID:
    """Build canonical XLSX from rows, upload to recon-files, insert documents row."""
    sb = get_supabase_admin()
    xlsx_bytes = rows_to_canonical_xlsx(rows, kind=kind)
    suffix = "purchase_register" if kind == JobKind.PURCHASE_REGISTER else "supplier_export"
    filename = f"ingested_{suffix}_{job_id}.xlsx"
    storage_path = f"{tenant_id}/{client_id}/ingestion/{job_id}/{filename}"
    doc_type = suffix

    def _up_and_register():
        sb.storage.from_(_RECON_BUCKET).upload(
            path=storage_path, file=xlsx_bytes,
            file_options={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "upsert": "false",
            },
        )
        doc = sb.table("documents").insert({
            "tenant_id": str(tenant_id),
            "client_id": str(client_id),
            "uploaded_by": str(user_id),
            "doc_type": doc_type,
            "storage_path": storage_path,
            "original_filename": filename,
            "file_size_bytes": len(xlsx_bytes),
        }).execute()
        return UUID(doc.data[0]["id"])

    return await asyncio.to_thread(_up_and_register)
```

- [ ] **Step 2: Rewrite `_resolve_doc_ids` to dispatch on linkage / reuse**

Replace the entire `_resolve_doc_ids` function with:

```python
async def _resolve_doc_ids(
    *, tenant_id, client_id, job, kind, rows, user_id,
) -> tuple[UUID, UUID, Optional[UUID]]:
    """Build/reuse PR + SF canonical docs and return (pr_doc_id, sf_doc_id, partner_job_id).

    `partner_job_id` is the linked PR job's id when this is an SF job with
    linked_pr_job_id set. Callers use it to mark the partner COMPLETED.
    """
    job_id = job["id"]
    linked_pr_job_id_raw = job.get("linked_pr_job_id")
    linked_pr_job_id = UUID(linked_pr_job_id_raw) if linked_pr_job_id_raw else None
    reuse_pr_doc_id_raw = job.get("reuse_pr_doc_id")
    reuse_pr_doc_id = UUID(reuse_pr_doc_id_raw) if reuse_pr_doc_id_raw else None
    reuse_sf_doc_id_raw = job.get("reuse_sf_doc_id")
    reuse_sf_doc_id = UUID(reuse_sf_doc_id_raw) if reuse_sf_doc_id_raw else None

    # Case 1: SF job linked to a PR job → build both canonicals from both jobs' rows.
    if kind == JobKind.SUPPLIER_EXPORT and linked_pr_job_id is not None:
        pr_job = await p.get_job(linked_pr_job_id, tenant_id=tenant_id)
        if pr_job is None:
            raise HandoffError(f"Linked PR job {linked_pr_job_id} disappeared")
        pr_rows_dicts = await p.list_confirmed_rows(linked_pr_job_id, tenant_id=tenant_id)
        if not pr_rows_dicts:
            raise HandoffError(f"Linked PR job {linked_pr_job_id} has no confirmed rows")
        pr_rows = [ExtractedRowData(**r["row_data"]) for r in pr_rows_dicts]
        pr_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=str(linked_pr_job_id), kind=JobKind.PURCHASE_REGISTER, rows=pr_rows,
        )
        sf_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=job_id, kind=JobKind.SUPPLIER_EXPORT, rows=rows,
        )
        return pr_doc_id, sf_doc_id, linked_pr_job_id

    # Case 2: SF job with reuse_pr_doc_id → build only SF, reuse PR doc id.
    if kind == JobKind.SUPPLIER_EXPORT and reuse_pr_doc_id is not None:
        sf_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=job_id, kind=JobKind.SUPPLIER_EXPORT, rows=rows,
        )
        return reuse_pr_doc_id, sf_doc_id, None

    # Case 3: PR job with reuse_sf_doc_id → build only PR, reuse SF doc id.
    if kind == JobKind.PURCHASE_REGISTER and reuse_sf_doc_id is not None:
        pr_doc_id = await _build_and_register_canonical(
            tenant_id=tenant_id, client_id=client_id, user_id=user_id,
            job_id=job_id, kind=JobKind.PURCHASE_REGISTER, rows=rows,
        )
        return pr_doc_id, reuse_sf_doc_id, None

    # Case 4 (fallback, mostly for tests / legacy): build for this kind, look up
    # the most-recent sibling doc by client. This is the old behavior; the new
    # wizard never lands here because it always sets linked_pr_job_id or reuse_*.
    this_doc_id = await _build_and_register_canonical(
        tenant_id=tenant_id, client_id=client_id, user_id=user_id,
        job_id=job_id, kind=kind, rows=rows,
    )
    sb = get_supabase_admin()
    sibling_doc_type = (
        "supplier_export" if kind == JobKind.PURCHASE_REGISTER else "purchase_register"
    )

    def _lookup_sibling():
        return (
            sb.table("documents")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .eq("doc_type", sibling_doc_type)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

    sibling = await asyncio.to_thread(_lookup_sibling)
    if not sibling.data:
        raise HandoffError(
            f"No prior {sibling_doc_type} document found for client {client_id}. "
            f"Upload the matching file via ingestion before finalizing."
        )
    sibling_id = UUID(sibling.data[0]["id"])
    if kind == JobKind.PURCHASE_REGISTER:
        return this_doc_id, sibling_id, None
    return sibling_id, this_doc_id, None
```

- [ ] **Step 3: Update `run_handoff` to handle the partner-completion contract**

Replace the body of `run_handoff` (starting at the `# 2. Look up the most-recent…` section) with the new flow. The full new function:

```python
async def run_handoff(
    *, job_id: UUID, tenant_id: UUID,
) -> UUID:
    """Returns the new reconciliation_id on success.

    Both the primary job and the linked partner job (if any) are marked
    COMPLETED with the same reconciliation_id before this returns.
    """
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HandoffError(f"Job {job_id} not found")
    if job["status"] not in (
        JobStatus.CONFIRMED.value,
        JobStatus.RECONCILING.value,
    ):
        raise HandoffError(
            f"Job {job_id} is in {job['status']}, expected 'confirmed' or 'reconciling'"
        )

    client_id = UUID(job["client_id"])
    user_id = UUID(job["created_by"])
    kind = JobKind(job["kind"])

    rows_dicts = await p.list_confirmed_rows(job_id, tenant_id=tenant_id)
    rows = [ExtractedRowData(**r["row_data"]) for r in rows_dicts]
    if not rows:
        raise HandoffError("No confirmed rows to hand off")

    pr_doc_id, sf_doc_id, partner_job_id = await _resolve_doc_ids(
        tenant_id=tenant_id, client_id=client_id, job=job, kind=kind, rows=rows,
        user_id=user_id,
    )

    log.info("ingestion.handoff.starting", job_id=str(job_id),
             partner_job_id=str(partner_job_id) if partner_job_id else None)

    recon_id = await run_reconciliation(
        ReconciliationCreateRequest(
            client_id=client_id,
            period_start=job["period_start"],
            period_end=job["period_end"],
            purchase_register_doc_id=pr_doc_id,
            supplier_data_doc_id=sf_doc_id,
        ),
        tenant_id=tenant_id, user_id=user_id,
    )

    await p.complete_jobs_pair(
        primary_job_id=job_id, partner_job_id=partner_job_id,
        tenant_id=tenant_id, reconciliation_id=recon_id,
    )

    log.info("ingestion.handoff.done", job_id=str(job_id), recon_id=str(recon_id))
    return recon_id
```

Add the `Optional` import to the typing imports at the top if not already present.

- [ ] **Step 4: Run the existing handoff round-trip test to confirm nothing broke**

Run: `cd backend && pytest tests/ingestion/test_handoff.py -v`
Expected: PASS for the two existing round-trip tests (`test_purchase_roundtrip_through_existing_parser`, `test_supplier_export_roundtrip`). These don't touch the DB so they exercise only `rows_to_canonical_xlsx`, which is unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/handoff.py
git commit -m "refactor(ingestion): combined-handoff path matrix + dual-job completion"
```

---

## Task 8: Router — extend `POST /jobs`, add `POST /sessions/start` + `GET /documents/recent`

**Files:**
- Modify: `backend/app/ingestion/router.py`

- [ ] **Step 1: Extend `_job_row_to_out` to include linkage + reuse fields**

In `backend/app/ingestion/router.py`, replace `_job_row_to_out` (lines ~60–71) with:

```python
def _job_row_to_out(row: dict, *, linked_sf_job_id: Optional[UUID] = None) -> JobOut:
    return JobOut(**{
        "id": row["id"], "tenant_id": row["tenant_id"], "client_id": row["client_id"],
        "kind": row["kind"], "period_start": row["period_start"],
        "period_end": row["period_end"], "status": row["status"],
        "files_total": row["files_total"], "files_done": row["files_done"],
        "rows_total": row["rows_total"], "rows_needs_review": row["rows_needs_review"],
        "error_summary": row.get("error_summary"),
        "reconciliation_id": row.get("reconciliation_id"),
        "linked_pr_job_id": row.get("linked_pr_job_id"),
        "linked_sf_job_id": str(linked_sf_job_id) if linked_sf_job_id else None,
        "reuse_pr_doc_id": row.get("reuse_pr_doc_id"),
        "reuse_sf_doc_id": row.get("reuse_sf_doc_id"),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "completed_at": row.get("completed_at"),
    })
```

- [ ] **Step 2: Update `get_job_endpoint` to look up the partner**

Replace `get_job_endpoint` (lines ~86–98) with:

```python
@router.get("/jobs/{job_id}", response_model=JobDetailOut)
async def get_job_endpoint(
    job_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> JobDetailOut:
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # If this is a PR job, look up any SF job that linked back to it.
    linked_sf_job_id: Optional[UUID] = None
    if job["kind"] == "purchase_register":
        linked_sf_job_id = await p.find_linked_sf_job_id(job_id, tenant_id=tenant_id)
    files = await p.list_files(job_id, tenant_id=tenant_id)
    return JobDetailOut(
        job=_job_row_to_out(job, linked_sf_job_id=linked_sf_job_id),
        files=[_file_row_to_out(f) for f in files],
    )
```

- [ ] **Step 3: Extend `create_job_endpoint` Form params + service call**

Replace `create_job_endpoint` (lines ~35–54) with:

```python
@router.post(
    "/jobs", status_code=status.HTTP_201_CREATED,
    response_model=CreateJobResponse,
)
async def create_job_endpoint(
    client_id: UUID = Form(...),
    period_start: date = Form(...),
    period_end: date = Form(...),
    kind: JobKind = Form(...),
    files: list[UploadFile] = File(...),
    linked_pr_job_id: Optional[UUID] = Form(None),
    reuse_pr_doc_id: Optional[UUID] = Form(None),
    reuse_sf_doc_id: Optional[UUID] = Form(None),
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> CreateJobResponse:
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end < period_start")
    try:
        return await svc.create_job(
            tenant_id=tenant_id, user_id=user_id,
            client_id=client_id, period_start=period_start, period_end=period_end,
            kind=kind, files=files,
            linked_pr_job_id=linked_pr_job_id,
            reuse_pr_doc_id=reuse_pr_doc_id,
            reuse_sf_doc_id=reuse_sf_doc_id,
        )
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })
```

- [ ] **Step 4: Add `POST /sessions/start` endpoint**

Append to `backend/app/ingestion/router.py`:

```python
from app.ingestion.schemas import (
    RecentDoc,
    RecentDocsOut,
    SessionStartRequest,
    SessionStartResponse,
)


@router.post("/sessions/start", response_model=SessionStartResponse)
async def start_session_endpoint(
    body: SessionStartRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> SessionStartResponse:
    try:
        result = await svc.start_session(
            tenant_id=tenant_id, user_id=user_id,
            client_id=body.client_id,
            period_start=body.period_start, period_end=body.period_end,
            reuse_pr_doc_id=body.reuse_pr_doc_id,
            reuse_sf_doc_id=body.reuse_sf_doc_id,
        )
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })
    return SessionStartResponse(**result)


@router.get("/documents/recent", response_model=RecentDocsOut)
async def list_recent_docs_endpoint(
    client_id: UUID,
    period_start: date,
    period_end: date,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> RecentDocsOut:
    pr_row, sf_row = await p.find_recent_docs(
        tenant_id=tenant_id, client_id=client_id,
        period_start=period_start, period_end=period_end,
    )
    return RecentDocsOut(
        pr=RecentDoc(**pr_row) if pr_row else None,
        sf=RecentDoc(**sf_row) if sf_row else None,
    )
```

- [ ] **Step 5: Smoke-import the router module**

Run: `cd backend && python -c "from app.ingestion.router import router; print(len(router.routes))"`
Expected: prints an integer larger than before (was 12; now 14 with the two new endpoints).

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/router.py
git commit -m "feat(ingestion): wire POST /sessions/start, GET /documents/recent, linkage on POST /jobs"
```

---

## Task 9: Windows asyncio selector loop

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_event_loop_policy.py`

- [ ] **Step 1: Add the policy pin to `main.py`**

At the very top of `backend/app/main.py` (above the existing `import asyncio` line), insert:

```python
import sys
import asyncio

# Python 3.14 on Windows defaults to ProactorEventLoop, which interacts
# poorly with httpx socket reads under load — symptom is intermittent
# `httpx.ReadError [WinError 10035] A non-blocking socket operation could
# not be completed immediately` when downloading XLSX from Supabase
# Storage during recon. The selector loop is stable.
# Refs:
#   https://docs.python.org/3.14/library/asyncio-eventloop.html#asyncio.WindowsSelectorEventLoopPolicy
#   https://github.com/encode/httpx/issues — Windows Proactor known-issues thread
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

The existing `import asyncio` further down is now redundant — delete it (the one on line 8). Leave all other imports untouched.

- [ ] **Step 2: Write a Windows-only test**

Create `backend/tests/test_event_loop_policy.py`:

```python
"""Verifies the Windows-only event-loop policy pin in app.main."""
from __future__ import annotations

import asyncio
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Selector policy pin only matters on Windows",
)


def test_main_module_pins_selector_event_loop_policy() -> None:
    # Importing app.main has the side effect of setting the policy at
    # module load. We re-import via importlib to make the assertion
    # robust if the test runner imports main earlier.
    import importlib
    import app.main as main_module
    importlib.reload(main_module)

    policy = asyncio.get_event_loop_policy()
    assert isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy), (
        f"Expected WindowsSelectorEventLoopPolicy, got {type(policy).__name__}"
    )
```

- [ ] **Step 3: Run the test**

Run: `cd backend && pytest tests/test_event_loop_policy.py -v`
Expected on Windows: PASS. Expected on Linux/macOS: SKIPPED.

- [ ] **Step 4: Smoke-boot the server**

Run: `cd backend && python -c "import app.main; print('main imports cleanly')"`
Expected: prints `main imports cleanly`. No errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_event_loop_policy.py
git commit -m "fix(main): pin WindowsSelectorEventLoopPolicy on Win32 to dodge httpx ReadError"
```

---

## Task 10: Backend tests — `test_create_job_linking.py`

**Files:**
- Create: `backend/tests/ingestion/test_create_job_linking.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/ingestion/test_create_job_linking.py`:

```python
"""Validation tests for the new linked_pr_job_id + reuse_*_doc_id fields.

Live-DB tests gated by INGESTION_TEST_SUPABASE_URL / INGESTION_TEST_USER_JWT
(same as test_api.py).
"""
from __future__ import annotations

import io
import os
import uuid as _uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Linking tests require live Supabase",
)


def _canonical_pr() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    ws.append(["INV-LNK", "111222333", "Lnk Supplier",
               "2026-05-10", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


@pytest.fixture
def client():
    set_llm_adapter(StubLLMAdapter())
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = os.environ.get("INGESTION_TEST_USER_JWT")
    if not token:
        pytest.skip("INGESTION_TEST_USER_JWT required")
    return {"Authorization": f"Bearer {token}"}


def _create_pr_job(client, auth_headers, client_id) -> str:
    files = [("files", ("pr.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "purchase_register",
        },
        files=files, headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["job_id"]


def test_linked_pr_job_id_must_point_to_a_purchase_register_job(
    client, auth_headers, client_id,
):
    # Create an SF job first, then try to link a second SF job to it (wrong kind).
    sf_id = _create_pr_job(client, auth_headers, client_id)  # reuse helper — but actually create SF
    # Override: create an SF job directly.
    files = [("files", ("sf.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
        },
        files=files, headers=auth_headers,
    )
    bogus_sf_id = res.json()["job_id"]

    # Now try to link a NEW SF job to the bogus_sf_id (kind=supplier_export) — must fail.
    files2 = [("files", ("sf2.xlsx", _canonical_pr(),
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res2 = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "linked_pr_job_id": bogus_sf_id,
        },
        files=files2, headers=auth_headers,
    )
    assert res2.status_code == 422
    body = res2.json()
    assert body["detail"]["code"] == "INGESTION_BAD_LINKAGE"


def test_linked_pr_job_id_rejected_on_pr_kind(
    client, auth_headers, client_id,
):
    pr_id = _create_pr_job(client, auth_headers, client_id)
    files = [("files", ("pr2.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "purchase_register",
            "linked_pr_job_id": pr_id,
        },
        files=files, headers=auth_headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INGESTION_BAD_LINKAGE"


def test_linked_pr_job_id_rejected_when_already_linked(
    client, auth_headers, client_id,
):
    pr_id = _create_pr_job(client, auth_headers, client_id)
    # First SF link should succeed.
    files = [("files", ("sf.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    ok = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "linked_pr_job_id": pr_id,
        },
        files=files, headers=auth_headers,
    )
    assert ok.status_code == 201, ok.text

    # Second SF link to the same PR must fail.
    files2 = [("files", ("sf2.xlsx", _canonical_pr(),
               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    dup = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "linked_pr_job_id": pr_id,
        },
        files=files2, headers=auth_headers,
    )
    assert dup.status_code == 422
    assert dup.json()["detail"]["code"] == "INGESTION_DUPLICATE_LINKAGE"


def test_reuse_doc_id_unknown_doc_rejected(
    client, auth_headers, client_id,
):
    fake_doc = str(_uuid.uuid4())
    files = [("files", ("sf.xlsx", _canonical_pr(),
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "kind": "supplier_export",
            "reuse_pr_doc_id": fake_doc,
        },
        files=files, headers=auth_headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INGESTION_BAD_REUSE"
```

- [ ] **Step 2: Run the new tests**

Run (locally with the live-DB env set, otherwise expect SKIPPED): `cd backend && pytest tests/ingestion/test_create_job_linking.py -v`
Expected: 4 PASS (or SKIPPED when the env isn't set).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/ingestion/test_create_job_linking.py
git commit -m "test(ingestion): validation tests for linked_pr_job_id + reuse_*_doc_id"
```

---

## Task 11: Backend tests — `test_session_start.py`

**Files:**
- Create: `backend/tests/ingestion/test_session_start.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/ingestion/test_session_start.py`:

```python
"""API tests for POST /api/v1/ingestion/sessions/start."""
from __future__ import annotations

import os
import uuid as _uuid

import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Session-start tests require live Supabase",
)


@pytest.fixture
def client():
    set_llm_adapter(StubLLMAdapter())
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = os.environ.get("INGESTION_TEST_USER_JWT")
    if not token:
        pytest.skip("INGESTION_TEST_USER_JWT required")
    return {"Authorization": f"Bearer {token}"}


def test_fresh_both_returns_pr_job_id(client, auth_headers, client_id):
    res = client.post(
        "/api/v1/ingestion/sessions/start",
        json={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pr_job_id"] is not None
    assert body["sf_job_id"] is None
    assert body["reconciliation_id"] is None


def test_reuse_doc_id_validates_kind(client, auth_headers, client_id):
    # Pass a fake doc id as reuse_pr_doc_id — must 422.
    res = client.post(
        "/api/v1/ingestion/sessions/start",
        json={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "reuse_pr_doc_id": str(_uuid.uuid4()),
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INGESTION_BAD_REUSE"


def test_period_end_before_start_rejected(client, auth_headers, client_id):
    res = client.post(
        "/api/v1/ingestion/sessions/start",
        json={
            "client_id": str(client_id),
            "period_start": "2026-05-31",
            "period_end": "2026-05-01",
        },
        headers=auth_headers,
    )
    assert res.status_code == 422  # Pydantic validator error
```

- [ ] **Step 2: Run the tests**

Run: `cd backend && pytest tests/ingestion/test_session_start.py -v`
Expected: 3 PASS (or SKIPPED).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/ingestion/test_session_start.py
git commit -m "test(ingestion): API tests for POST /sessions/start"
```

---

## Task 12: Backend tests — `test_documents_recent.py`

**Files:**
- Create: `backend/tests/ingestion/test_documents_recent.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/ingestion/test_documents_recent.py`:

```python
"""API test for GET /api/v1/ingestion/documents/recent."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Recent-docs test requires live Supabase",
)


@pytest.fixture
def client():
    set_llm_adapter(StubLLMAdapter())
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = os.environ.get("INGESTION_TEST_USER_JWT")
    if not token:
        pytest.skip("INGESTION_TEST_USER_JWT required")
    return {"Authorization": f"Bearer {token}"}


def test_recent_docs_endpoint_returns_pr_and_sf_keys(
    client, auth_headers, client_id,
):
    res = client.get(
        "/api/v1/ingestion/documents/recent",
        params={
            "client_id": str(client_id),
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # Keys are always present; values may be null.
    assert "pr" in body
    assert "sf" in body


def test_recent_docs_rejects_missing_client_id(client, auth_headers):
    res = client.get(
        "/api/v1/ingestion/documents/recent",
        params={"period_start": "2026-05-01", "period_end": "2026-05-31"},
        headers=auth_headers,
    )
    assert res.status_code == 422  # FastAPI missing-query-param error
```

- [ ] **Step 2: Run the tests**

Run: `cd backend && pytest tests/ingestion/test_documents_recent.py -v`
Expected: PASS (or SKIPPED).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/ingestion/test_documents_recent.py
git commit -m "test(ingestion): API test for GET /documents/recent"
```

---

## Task 13: Backend tests — `test_handoff_combined.py`

**Files:**
- Create: `backend/tests/ingestion/test_handoff_combined.py`

- [ ] **Step 1: Write the test**

Create `backend/tests/ingestion/test_handoff_combined.py`:

```python
"""End-to-end handoff tests for the combined-doc path matrix.

Live-DB; seeds two confirmed jobs (PR + SF linked), finalizes the SF, and
asserts both jobs end at status=completed with the same reconciliation_id.
"""
from __future__ import annotations

import io
import os

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Handoff tests require live Supabase",
)


def _canonical_pr() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    ws.append(["INV-HC", "111222333", "HC Supplier",
               "2026-05-10", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _canonical_sf() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Invoice Date",
               "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN"])
    ws.append(["INV-HC", "2026-05-10", 1000, 150, "999000111"])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


@pytest.fixture
def client():
    set_llm_adapter(StubLLMAdapter())
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = os.environ.get("INGESTION_TEST_USER_JWT")
    if not token:
        pytest.skip("INGESTION_TEST_USER_JWT required")
    return {"Authorization": f"Bearer {token}"}


def _confirm_all_rows(client, auth_headers, job_id: str) -> None:
    # List rows then bulk-confirm them.
    res = client.get(
        f"/api/v1/ingestion/jobs/{job_id}/rows",
        params={"filter": "all"}, headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    row_ids = [r["id"] for r in res.json()["rows"]]
    if not row_ids:
        return
    bulk = client.post(
        f"/api/v1/ingestion/jobs/{job_id}/rows/bulk-confirm",
        json={"row_ids": row_ids}, headers=auth_headers,
    )
    assert bulk.status_code == 200, bulk.text


def _wait_extracted(client, auth_headers, job_id: str, timeout_s: int = 30) -> None:
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = client.get(f"/api/v1/ingestion/jobs/{job_id}", headers=auth_headers)
        if res.json()["job"]["status"] == "ready_for_review":
            return
        time.sleep(0.5)
    pytest.fail(f"Job {job_id} did not reach ready_for_review in {timeout_s}s")


def test_combined_finalize_completes_both_jobs(client, auth_headers, client_id):
    # 1. Create PR job, wait, confirm rows.
    files_pr = [("files", ("pr.xlsx", _canonical_pr(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    pr_res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-06-01", "period_end": "2026-06-30",
            "kind": "purchase_register",
        },
        files=files_pr, headers=auth_headers,
    )
    assert pr_res.status_code == 201, pr_res.text
    pr_job_id = pr_res.json()["job_id"]
    _wait_extracted(client, auth_headers, pr_job_id)
    _confirm_all_rows(client, auth_headers, pr_job_id)

    # 2. Create SF job linked to PR, wait, confirm rows.
    files_sf = [("files", ("sf.xlsx", _canonical_sf(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    sf_res = client.post(
        "/api/v1/ingestion/jobs",
        data={
            "client_id": str(client_id),
            "period_start": "2026-06-01", "period_end": "2026-06-30",
            "kind": "supplier_export",
            "linked_pr_job_id": pr_job_id,
        },
        files=files_sf, headers=auth_headers,
    )
    assert sf_res.status_code == 201, sf_res.text
    sf_job_id = sf_res.json()["job_id"]
    _wait_extracted(client, auth_headers, sf_job_id)
    _confirm_all_rows(client, auth_headers, sf_job_id)

    # 3. Finalize SF — must succeed and complete both jobs with the same recon id.
    fin = client.post(
        f"/api/v1/ingestion/jobs/{sf_job_id}/finalize",
        headers=auth_headers,
    )
    assert fin.status_code == 200, fin.text
    recon_id = fin.json()["reconciliation_id"]

    pr_after = client.get(
        f"/api/v1/ingestion/jobs/{pr_job_id}", headers=auth_headers,
    ).json()["job"]
    sf_after = client.get(
        f"/api/v1/ingestion/jobs/{sf_job_id}", headers=auth_headers,
    ).json()["job"]
    assert pr_after["status"] == "completed"
    assert sf_after["status"] == "completed"
    assert pr_after["reconciliation_id"] == recon_id
    assert sf_after["reconciliation_id"] == recon_id
    assert pr_after["linked_sf_job_id"] == sf_job_id  # reverse lookup populated
```

- [ ] **Step 2: Run the test**

Run: `cd backend && pytest tests/ingestion/test_handoff_combined.py -v`
Expected: PASS (or SKIPPED). Test takes ~30–60s due to the extract wait loop.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/ingestion/test_handoff_combined.py
git commit -m "test(ingestion): combined-handoff completes both PR + SF jobs"
```

---

## Task 14: Frontend types — extend Zod schemas

**Files:**
- Modify: `frontend/src/types/ingestion.ts`

- [ ] **Step 1: Extend `JobOutSchema`**

In `frontend/src/types/ingestion.ts`, replace `JobOutSchema` (lines ~65–82) with:

```ts
export const JobOutSchema = z.object({
  id: Uuid,
  tenant_id: Uuid,
  client_id: Uuid,
  kind: JobKindEnum,
  period_start: IsoDate,
  period_end: IsoDate,
  status: JobStatusEnum,
  files_total: z.number().int(),
  files_done: z.number().int(),
  rows_total: z.number().int(),
  rows_needs_review: z.number().int(),
  error_summary: z.string().nullable().optional(),
  reconciliation_id: Uuid.nullable().optional(),
  linked_pr_job_id: Uuid.nullable().optional(),
  linked_sf_job_id: Uuid.nullable().optional(),
  reuse_pr_doc_id: Uuid.nullable().optional(),
  reuse_sf_doc_id: Uuid.nullable().optional(),
  created_at: IsoDateTime,
  updated_at: IsoDateTime,
  completed_at: IsoDateTime.nullable().optional(),
})
export type JobOut = z.infer<typeof JobOutSchema>
```

- [ ] **Step 2: Add session + recent-docs schemas**

Append to `frontend/src/types/ingestion.ts`:

```ts
// ── Session start ─────────────────────────────────────────────────────────

export const SessionStartRequestSchema = z.object({
  client_id: Uuid,
  period_start: IsoDate,
  period_end: IsoDate,
  reuse_pr_doc_id: Uuid.nullable().optional(),
  reuse_sf_doc_id: Uuid.nullable().optional(),
})
export type SessionStartRequest = z.infer<typeof SessionStartRequestSchema>

export const SessionStartResponseSchema = z.object({
  pr_job_id: Uuid.nullable().optional(),
  sf_job_id: Uuid.nullable().optional(),
  reconciliation_id: Uuid.nullable().optional(),
})
export type SessionStartResponse = z.infer<typeof SessionStartResponseSchema>

// ── Recent documents ──────────────────────────────────────────────────────

export const RecentDocSchema = z.object({
  id: Uuid,
  doc_type: z.enum(["purchase_register", "supplier_export"]),
  original_filename: z.string(),
  file_size_bytes: z.number().int().nullable().optional(),
  created_at: IsoDateTime,
})
export type RecentDoc = z.infer<typeof RecentDocSchema>

export const RecentDocsOutSchema = z.object({
  pr: RecentDocSchema.nullable().optional(),
  sf: RecentDocSchema.nullable().optional(),
})
export type RecentDocsOut = z.infer<typeof RecentDocsOutSchema>
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -30`
Expected: no errors related to `ingestion.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/ingestion.ts
git commit -m "feat(ingestion): zod schemas for sessions, recent docs, linkage"
```

---

## Task 15: Frontend API — `createJob` extension + `startSession` + `fetchRecentDocs`

**Files:**
- Modify: `frontend/src/lib/ingestion/api.ts`

- [ ] **Step 1: Extend `CreateJobInput` and `createJob`**

In `frontend/src/lib/ingestion/api.ts`, replace the `CreateJobInput` interface and `createJob` function (lines ~20–39) with:

```ts
export interface CreateJobInput {
  client_id: string
  period_start: string
  period_end: string
  kind: JobKind
  files: File[]
  linked_pr_job_id?: string
  reuse_pr_doc_id?: string
  reuse_sf_doc_id?: string
}

export async function createJob(input: CreateJobInput): Promise<CreateJobResponse> {
  const fd = new FormData()
  fd.append("client_id", input.client_id)
  fd.append("period_start", input.period_start)
  fd.append("period_end", input.period_end)
  fd.append("kind", JobKindEnum.parse(input.kind))
  if (input.linked_pr_job_id) fd.append("linked_pr_job_id", input.linked_pr_job_id)
  if (input.reuse_pr_doc_id)  fd.append("reuse_pr_doc_id",  input.reuse_pr_doc_id)
  if (input.reuse_sf_doc_id)  fd.append("reuse_sf_doc_id",  input.reuse_sf_doc_id)
  for (const f of input.files) fd.append("files", f, f.name)
  const { data } = await api.post("/api/v1/ingestion/jobs", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return CreateJobResponseSchema.parse(data)
}
```

- [ ] **Step 2: Add `startSession`**

Append to `frontend/src/lib/ingestion/api.ts` (after `finalizeJob`):

```ts
import {
  SessionStartRequestSchema,
  SessionStartResponseSchema,
  RecentDocsOutSchema,
  type SessionStartRequest,
  type SessionStartResponse,
  type RecentDocsOut,
} from "@/types/ingestion"

export async function startSession(input: SessionStartRequest): Promise<SessionStartResponse> {
  const validated = SessionStartRequestSchema.parse(input)
  const { data } = await api.post("/api/v1/ingestion/sessions/start", validated)
  return SessionStartResponseSchema.parse(data)
}

export async function fetchRecentDocs(params: {
  client_id: string; period_start: string; period_end: string;
}): Promise<RecentDocsOut> {
  const { data } = await api.get("/api/v1/ingestion/documents/recent", { params })
  return RecentDocsOutSchema.parse(data)
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -30`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/ingestion/api.ts
git commit -m "feat(ingestion): API client for sessions/start, documents/recent, linked createJob"
```

---

## Task 16: Frontend hooks — `useStartSession` + `usePriorDocs`

**Files:**
- Modify: `frontend/src/hooks/useIngestion.ts`
- Create: `frontend/src/hooks/usePriorDocs.ts`
- Create: `frontend/src/hooks/__tests__/usePriorDocs.test.tsx`

- [ ] **Step 1: Add `useStartSession` to `useIngestion.ts`**

Append to `frontend/src/hooks/useIngestion.ts`:

```ts
import { startSession } from "@/lib/ingestion/api"
import type { SessionStartRequest } from "@/types/ingestion"

export function useStartSession() {
  return useMutation({
    mutationFn: (input: SessionStartRequest) => startSession(input),
  })
}
```

(Add `startSession` to the existing top-of-file import from `@/lib/ingestion/api` if not already present.)

- [ ] **Step 2: Create `usePriorDocs`**

Create `frontend/src/hooks/usePriorDocs.ts`:

```ts
import { useQuery } from "@tanstack/react-query"

import { fetchRecentDocs } from "@/lib/ingestion/api"

export const priorDocsKeys = {
  forPeriod: (clientId: string, start: string, end: string) =>
    ["ingestion", "documents", "recent", clientId, start, end] as const,
}

/**
 * Looks up the most recent PR + SF documents for (client, period). Drives
 * the "Reuse prior PR/SF" checkboxes on the SetupStep.
 *
 * Disabled until all three params are non-empty (the period inputs start blank).
 */
export function usePriorDocs(clientId: string | undefined, periodStart: string, periodEnd: string) {
  const enabled = Boolean(clientId && periodStart && periodEnd)
  return useQuery({
    queryKey: priorDocsKeys.forPeriod(clientId ?? "", periodStart, periodEnd),
    enabled,
    queryFn: () => fetchRecentDocs({
      client_id: clientId!, period_start: periodStart, period_end: periodEnd,
    }),
    staleTime: 30_000,
  })
}
```

- [ ] **Step 3: Write the failing test**

Create `frontend/src/hooks/__tests__/usePriorDocs.test.tsx`:

```tsx
import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { usePriorDocs } from "@/hooks/usePriorDocs"
import { api } from "@/lib/api"

let mock: MockAdapter
function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

const CLIENT = "11111111-1111-1111-1111-111111111111"

describe("usePriorDocs", () => {
  it("is disabled when params are missing", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePriorDocs(undefined, "", ""), { wrapper: wrapper(qc) })
    // 'enabled: false' leaves status as 'pending' with no fetch fired.
    expect(result.current.fetchStatus).toBe("idle")
  })

  it("returns parsed pr+sf when API responds", async () => {
    mock.onGet("/api/v1/ingestion/documents/recent").reply(200, {
      pr: {
        id: "22222222-2222-2222-2222-222222222222",
        doc_type: "purchase_register",
        original_filename: "pr.xlsx",
        file_size_bytes: 1024,
        created_at: "2026-05-10T00:00:00+00:00",
      },
      sf: null,
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(
      () => usePriorDocs(CLIENT, "2026-05-01", "2026-05-31"),
      { wrapper: wrapper(qc) },
    )
    await waitFor(() => expect(result.current.data?.pr?.original_filename).toBe("pr.xlsx"))
    expect(result.current.data?.sf).toBeNull()
  })
})
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/hooks/__tests__/usePriorDocs.test.tsx`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useIngestion.ts frontend/src/hooks/usePriorDocs.ts frontend/src/hooks/__tests__/usePriorDocs.test.tsx
git commit -m "feat(ingestion): useStartSession + usePriorDocs"
```

---

## Task 17: Frontend — rewrite `Stepper`

**Files:**
- Modify: `frontend/src/components/ingestion/Stepper.tsx`
- Create: `frontend/src/components/ingestion/__tests__/Stepper.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ingestion/__tests__/Stepper.test.tsx`:

```tsx
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import { Stepper, statusToStep } from "@/components/ingestion/Stepper"
import type { JobOut } from "@/types/ingestion"

function pr(status: JobOut["status"], extras: Partial<JobOut> = {}): JobOut {
  return {
    id: "p", tenant_id: "t", client_id: "c", kind: "purchase_register",
    period_start: "2026-05-01", period_end: "2026-05-31",
    status, files_total: 0, files_done: 0,
    rows_total: 0, rows_needs_review: 0,
    error_summary: null, reconciliation_id: null,
    linked_pr_job_id: null, linked_sf_job_id: null,
    reuse_pr_doc_id: null, reuse_sf_doc_id: null,
    created_at: "2026-05-10T00:00:00+00:00",
    updated_at: "2026-05-10T00:00:00+00:00",
    completed_at: null,
    ...extras,
  } as JobOut
}

function sf(status: JobOut["status"], extras: Partial<JobOut> = {}): JobOut {
  return pr(status, { kind: "supplier_export", ...extras })
}

describe("statusToStep", () => {
  it("returns 1 (Setup) when neither half exists", () => {
    expect(statusToStep(undefined, undefined)).toBe(1)
  })

  it("returns 2 (Purchase register) for an active PR job before SF exists", () => {
    expect(statusToStep(pr("extracting"), undefined)).toBe(2)
  })

  it("returns 3 (Supplier export) once SF job exists", () => {
    expect(statusToStep(pr("confirmed"), sf("extracting"))).toBe(3)
  })

  it("returns 4 (Reconcile) for SF reconciling", () => {
    expect(statusToStep(pr("confirmed"), sf("reconciling"))).toBe(4)
  })

  it("returns 5 (Done) when SF is completed", () => {
    expect(statusToStep(pr("completed"), sf("completed"))).toBe(5)
  })

  it("PR with reuse_sf_doc_id and confirmed → step 4 (Reconcile pending)", () => {
    expect(statusToStep(pr("confirmed", { reuse_sf_doc_id: "doc" }), undefined)).toBe(4)
  })

  it("SF-only session (PR reused) extracting → step 3", () => {
    expect(statusToStep(undefined, sf("extracting", { reuse_pr_doc_id: "doc" }))).toBe(3)
  })
})

describe("<Stepper />", () => {
  it("renders 5 step labels", () => {
    render(<Stepper activeStep={1} />)
    expect(screen.getByText("Setup")).toBeInTheDocument()
    expect(screen.getByText("Purchase register")).toBeInTheDocument()
    expect(screen.getByText("Supplier export")).toBeInTheDocument()
    expect(screen.getByText("Reconcile")).toBeInTheDocument()
    expect(screen.getByText("Done")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to confirm it fails**

Run: `cd frontend && npx vitest run src/components/ingestion/__tests__/Stepper.test.tsx`
Expected: FAIL (statusToStep is currently typed for a single status).

- [ ] **Step 3: Rewrite `Stepper.tsx`**

Replace `frontend/src/components/ingestion/Stepper.tsx`:

```tsx
/* eslint-disable react-refresh/only-export-components */
import { Check } from "lucide-react"

import { cn } from "@/lib/utils"
import type { JobOut } from "@/types/ingestion"

const STEPS = ["Setup", "Purchase register", "Supplier export", "Reconcile", "Done"] as const
export type StepIndex = 1 | 2 | 3 | 4 | 5

/**
 * Derive the active wizard step from the combined PR + SF job state.
 *
 *   undefined + undefined            → 1  Setup
 *   active PR + no SF                → 2  Purchase register
 *   PR confirmed + active SF         → 3  Supplier export
 *   SF reconciling                   → 4  Reconcile
 *   PR confirmed with reuse_sf       → 4  Reconcile (no SF job created)
 *   SF completed (terminal)          → 5  Done
 */
export function statusToStep(
  prJob: JobOut | undefined,
  sfJob: JobOut | undefined,
): StepIndex {
  if (!prJob && !sfJob) return 1

  // SF-only session (PR reused at session start, no PR job exists).
  if (!prJob && sfJob) {
    if (sfJob.status === "completed") return 5
    if (sfJob.status === "reconciling") return 4
    if (sfJob.status === "confirmed") return 4
    return 3 // pending | extracting | ready_for_review | failed
  }

  // PR exists. Decide whether the wizard is still on the PR half or has moved on.
  const pr = prJob!
  const prIsTerminal = pr.status === "confirmed" || pr.status === "completed"

  // Combined-completion: both halves done.
  if (pr.status === "completed" && (!sfJob || sfJob.status === "completed")) return 5

  if (!prIsTerminal) return 2

  // PR is confirmed/completed. If PR was created with reuse_sf_doc_id and SF
  // job was therefore never spawned, finalize runs from the PR job itself.
  if (!sfJob) {
    if (pr.reuse_sf_doc_id) {
      if (pr.status === "reconciling") return 4
      return 4 // ready to finalize
    }
    return 3 // PR confirmed, awaiting SF upload
  }

  // SF job exists.
  if (sfJob.status === "reconciling") return 4
  if (sfJob.status === "completed") return 5
  if (sfJob.status === "confirmed") return 4
  return 3
}

interface Props {
  activeStep: StepIndex
}

export function Stepper({ activeStep }: Props) {
  return (
    <ol className="flex w-full items-center" aria-label="Ingestion progress">
      {STEPS.map((label, idx) => {
        const step = (idx + 1) as StepIndex
        const done = step < activeStep
        const active = step === activeStep
        const isLast = idx === STEPS.length - 1
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={cn("flex items-center", !isLast && "flex-1")}
          >
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-7 items-center justify-center rounded-full border text-xs font-medium",
                  done && "bg-primary text-primary-foreground border-primary",
                  active && "border-primary text-primary",
                  !done && !active && "border-border text-muted-foreground",
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : step}
              </span>
              <span
                className={cn(
                  "text-sm",
                  active ? "text-foreground font-medium" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </div>
            {!isLast && (
              <div
                className={cn(
                  "mx-3 h-px flex-1",
                  done ? "bg-primary" : "bg-border",
                )}
                aria-hidden
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/ingestion/__tests__/Stepper.test.tsx`
Expected: All PASS.

- [ ] **Step 5: Update callers that import the old `statusToStep(jobStatus)`**

Find them:
```bash
cd frontend && grep -rn "statusToStep" src
```
Replace `statusToStep(job.status)` with `statusToStep(prJob, sfJob)` in `IngestionWizard.tsx` and `UploadStep.tsx`. (UploadStep also passes the literal value `1` — leave that as-is; only the wizard call is changing.) These will be fully rewritten in later tasks; for now just adjust the existing call sites so the project compiles.

If `UploadStep.tsx` calls `<Stepper activeStep={1} />` literally, leave it alone. If it calls `statusToStep(...)`, replace with the literal `1` for now.

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -30`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ingestion/Stepper.tsx frontend/src/components/ingestion/__tests__/Stepper.test.tsx frontend/src/components/ingestion/UploadStep.tsx frontend/src/components/ingestion/IngestionWizard.tsx
git commit -m "feat(ingestion): 5-step stepper + combined statusToStep(prJob, sfJob)"
```

---

## Task 18: Frontend — `HalfHeader` component

**Files:**
- Create: `frontend/src/components/ingestion/HalfHeader.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/ingestion/HalfHeader.tsx`:

```tsx
import { cn } from "@/lib/utils"

interface Props {
  half: "purchase_register" | "supplier_export"
  subState: "upload" | "extract" | "review" | "reused"
  filename?: string
  className?: string
}

const HALF_LABEL = {
  purchase_register: "Purchase register",
  supplier_export: "Supplier-filed export",
} as const

const SUB_LABEL = {
  upload: "Upload",
  extract: "Extracting",
  review: "Review",
  reused: "Reusing prior document",
} as const

/**
 * Small in-card banner shown above an active half's content. Tells the
 * user which half they're on and what sub-state ("Extracting", "Review",
 * etc.) — the top-of-page Stepper only shows the 5 high-level steps so
 * this fills in the detail.
 */
export function HalfHeader({ half, subState, filename, className }: Props) {
  return (
    <div className={cn("flex items-baseline gap-2 text-sm", className)}>
      <span className="font-medium text-foreground">{HALF_LABEL[half]}</span>
      <span className="text-muted-foreground" aria-hidden>·</span>
      <span className="text-muted-foreground">
        {SUB_LABEL[subState]}{filename ? ` (${filename})` : ""}
      </span>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -10`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ingestion/HalfHeader.tsx
git commit -m "feat(ingestion): HalfHeader banner for sub-states inside each half"
```

---

## Task 19: Frontend — refactor `UploadStep` to accept `kind` + `period` + optional linkage

**Files:**
- Modify: `frontend/src/components/ingestion/UploadStep.tsx`

- [ ] **Step 1: Rewrite the component**

Replace `frontend/src/components/ingestion/UploadStep.tsx`:

```tsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { MultiFileDropzone } from "@/components/ingestion/MultiFileDropzone"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useCreateJob } from "@/hooks/useIngestion"
import { ApiError } from "@/lib/api"
import type { JobKind } from "@/types/ingestion"

const ACCEPT = ".xlsx,.pdf,.jpg,.jpeg,.png,.heic"
const MAX_BYTES = 25 * 1024 * 1024

interface Props {
  clientId: string
  kind: JobKind
  periodStart: string
  periodEnd: string
  /** When set, the new job is linked to this PR job (only on kind=supplier_export). */
  linkedPrJobId?: string
  /** When set, persisted on the job; handoff will reuse the existing canonical XLSX. */
  reuseSfDocId?: string
  /** Called with the new job id after a successful upload. */
  onCreated: (jobId: string) => void
}

export function UploadStep({
  clientId, kind, periodStart, periodEnd,
  linkedPrJobId, reuseSfDocId, onCreated,
}: Props) {
  const navigate = useNavigate()
  const createJob = useCreateJob()

  const [files, setFiles] = useState<File[]>([])
  const oversize = files.find((f) => f.size > MAX_BYTES)
  const canSubmit = files.length > 0 && !oversize

  async function handleSubmit() {
    if (!canSubmit) return
    try {
      const res = await createJob.mutateAsync({
        client_id: clientId,
        period_start: periodStart,
        period_end: periodEnd,
        kind,
        files,
        linked_pr_job_id: linkedPrJobId,
        reuse_sf_doc_id: reuseSfDocId,
      })
      const rejected = res.files.filter((f) => !f.accepted)
      if (rejected.length === res.files.length) {
        toast.error("All files were rejected.")
        return
      } else if (rejected.length > 0) {
        toast.warning(`${rejected.length} file(s) rejected; proceeding with the rest.`)
      } else {
        toast.success("Upload received. Extracting…")
      }
      onCreated(res.job_id)
      // The wizard reads the new job ID via the parent; navigate only when
      // the parent didn't already handle the URL.
      if (!linkedPrJobId) {
        navigate(`/clients/${clientId}/ingestion/${res.job_id}`)
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      toast.error(msg)
    }
  }

  const title = kind === "purchase_register"
    ? "Upload purchase register"
    : "Upload supplier-filed export"

  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <MultiFileDropzone
          files={files}
          onChange={setFiles}
          accept={ACCEPT}
          disabled={createJob.isPending}
          maxBytes={MAX_BYTES}
          rejectedReasons={
            oversize ? { [oversize.name]: `exceeds ${MAX_BYTES / 1024 / 1024} MB` } : {}
          }
        />
        <div className="flex items-center gap-3">
          <Button onClick={handleSubmit} disabled={!canSubmit || createJob.isPending}>
            {createJob.isPending ? "Uploading…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`.trim()}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -30`
Expected: errors only in callers (we'll fix them in the next tasks).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ingestion/UploadStep.tsx
git commit -m "refactor(ingestion): UploadStep accepts kind/period/linkage as props"
```

---

## Task 20: Frontend — refactor `ReviewStep` for dynamic CTA label

**Files:**
- Modify: `frontend/src/components/ingestion/ReviewStep.tsx`

- [ ] **Step 1: Add `confirmCtaLabel` prop**

In `frontend/src/components/ingestion/ReviewStep.tsx`, change the `Props` interface to:

```tsx
interface Props {
  job: JobOut
  files: IngestionFileOut[]
  onFinalize: () => void
  /** Defaults to "Finalize → run reconciliation". */
  confirmCtaLabel?: string
}
```

Update the function signature:

```tsx
export function ReviewStep({ job, files, onFinalize, confirmCtaLabel }: Props) {
```

And the button text (line ~104) from:

```tsx
              Finalize → run reconciliation
```

to:

```tsx
              {confirmCtaLabel ?? "Finalize → run reconciliation"}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -10`
Expected: no errors in this file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ingestion/ReviewStep.tsx
git commit -m "feat(ingestion): ReviewStep accepts a custom confirm CTA label"
```

---

## Task 21: Frontend — `FinalizeStep` surfaces `error_summary` + supports SF-job target

**Files:**
- Modify: `frontend/src/components/ingestion/FinalizeStep.tsx`
- Create: `frontend/src/components/ingestion/__tests__/FinalizeStep.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ingestion/__tests__/FinalizeStep.test.tsx`:

```tsx
import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import type { JobOut } from "@/types/ingestion"

function job(overrides: Partial<JobOut> = {}): JobOut {
  return {
    id: "j1", tenant_id: "t", client_id: "c", kind: "supplier_export",
    period_start: "2026-05-01", period_end: "2026-05-31",
    status: "confirmed",
    files_total: 1, files_done: 1, rows_total: 4, rows_needs_review: 0,
    error_summary: null, reconciliation_id: null,
    linked_pr_job_id: null, linked_sf_job_id: null,
    reuse_pr_doc_id: null, reuse_sf_doc_id: null,
    created_at: "2026-05-15T00:00:00+00:00",
    updated_at: "2026-05-15T00:00:00+00:00",
    completed_at: null,
    ...overrides,
  } as JobOut
}

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe("<FinalizeStep />", () => {
  it("renders the error banner when status=confirmed and error_summary is set", () => {
    render(withClient(
      <FinalizeStep
        job={job({ status: "confirmed", error_summary: "BOOM" })}
        clientId="c"
      />,
    ))
    expect(screen.getByText(/Last attempt failed/i)).toBeInTheDocument()
    expect(screen.getByText("BOOM")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeInTheDocument()
  })

  it("does not render the banner on a clean confirmed job", () => {
    render(withClient(
      <FinalizeStep
        job={job({ status: "confirmed", error_summary: null })}
        clientId="c"
      />,
    ))
    expect(screen.queryByText(/Last attempt failed/i)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to confirm it fails**

Run: `cd frontend && npx vitest run src/components/ingestion/__tests__/FinalizeStep.test.tsx`
Expected: FAIL on the banner expectation.

- [ ] **Step 3: Update `FinalizeStep.tsx`**

Replace `frontend/src/components/ingestion/FinalizeStep.tsx`:

```tsx
// frontend/src/components/ingestion/FinalizeStep.tsx
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react"
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useFinalize } from "@/hooks/useIngestion"
import type { JobOut } from "@/types/ingestion"

interface Props {
  job: JobOut
  clientId: string
  /** Override the job whose `finalize` endpoint gets called. Defaults to `job.id`.
   *  Set this when the wizard is showing the SF job but finalize should target the PR job, or vice versa. */
  finalizeJobId?: string
}

export function FinalizeStep({ job, clientId, finalizeJobId }: Props) {
  const navigate = useNavigate()
  const targetId = finalizeJobId ?? job.id
  const finalize = useFinalize(targetId)

  // Auto-navigate when reconciliation completes
  useEffect(() => {
    if (job.status === "completed" && job.reconciliation_id) {
      toast.success("Reconciliation complete")
      navigate(`/clients/${clientId}/recon/${job.reconciliation_id}`, { replace: true })
    }
  }, [job.status, job.reconciliation_id, clientId, navigate])

  async function handleFinalize() {
    try {
      await finalize.mutateAsync()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  if (job.status === "reconciling") {
    return (
      <Card>
        <CardHeader><CardTitle>Reconciling…</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 text-sm">
            <Loader2 className="size-5 animate-spin text-primary" aria-hidden />
            <p>Matching invoices against the supplier-filed export.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (job.status === "completed") {
    return (
      <Card>
        <CardHeader><CardTitle>Done</CardTitle></CardHeader>
        <CardContent className="flex items-center gap-3 text-sm">
          <CheckCircle2 className="size-5 text-green-600 dark:text-green-500" aria-hidden />
          <p>Redirecting to the reconciliation report…</p>
        </CardContent>
      </Card>
    )
  }

  if (job.status === "failed") {
    return (
      <Card>
        <CardHeader><CardTitle>Reconciliation failed</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            <XCircle className="size-5 text-destructive" aria-hidden />
            <p>{job.error_summary || "An unexpected error occurred."}</p>
          </div>
          <Button onClick={handleFinalize} disabled={finalize.isPending}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  // status === "confirmed": ready to finalize, optionally with a previous-attempt error banner.
  return (
    <Card>
      <CardHeader><CardTitle>Ready to finalize</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {job.error_summary && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
          >
            <AlertTriangle className="size-4 mt-0.5 text-destructive" aria-hidden />
            <div>
              <p className="font-medium text-destructive">Last attempt failed</p>
              <p className="text-foreground/80">{job.error_summary}</p>
            </div>
          </div>
        )}
        <p className="text-sm text-muted-foreground">
          {job.rows_total} row(s) confirmed. Click below to run reconciliation.
        </p>
        <Button onClick={handleFinalize} disabled={finalize.isPending}>
          {finalize.isPending ? "Submitting…" : "Run reconciliation"}
        </Button>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/ingestion/__tests__/FinalizeStep.test.tsx`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ingestion/FinalizeStep.tsx frontend/src/components/ingestion/__tests__/FinalizeStep.test.tsx
git commit -m "fix(ingestion): surface error_summary on FinalizeStep + finalizeJobId prop"
```

---

## Task 22: Frontend — `PurchaseHalf` + `SupplierHalf`

**Files:**
- Create: `frontend/src/components/ingestion/PurchaseHalf.tsx`
- Create: `frontend/src/components/ingestion/SupplierHalf.tsx`

- [ ] **Step 1: Create `PurchaseHalf`**

Create `frontend/src/components/ingestion/PurchaseHalf.tsx`:

```tsx
import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { HalfHeader } from "@/components/ingestion/HalfHeader"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { UploadStep } from "@/components/ingestion/UploadStep"
import type { JobOut, IngestionFileOut } from "@/types/ingestion"

interface Props {
  clientId: string
  periodStart: string
  periodEnd: string
  prJob?: JobOut
  files: IngestionFileOut[]
  /** Called when the PR confirm CTA fires. The wizard then flips to the SF half. */
  onContinueToSupplier: () => void
  /** Called when no PR job exists yet and the user uploads files. */
  onJobCreated: (jobId: string) => void
}

export function PurchaseHalf({
  clientId, periodStart, periodEnd, prJob, files,
  onContinueToSupplier, onJobCreated,
}: Props) {
  if (!prJob) {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="upload" />
        <UploadStep
          clientId={clientId}
          kind="purchase_register"
          periodStart={periodStart}
          periodEnd={periodEnd}
          onCreated={onJobCreated}
        />
      </div>
    )
  }

  if (prJob.status === "pending" || prJob.status === "extracting") {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="extract" />
        <ExtractingStep
          files={files}
          filesDone={prJob.files_done}
          filesTotal={prJob.files_total}
        />
      </div>
    )
  }

  if (prJob.status === "ready_for_review") {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="review" />
        <ReviewStep
          job={prJob}
          files={files}
          onFinalize={onContinueToSupplier}
          confirmCtaLabel="Continue to supplier export"
        />
      </div>
    )
  }

  // confirmed (waiting for the user to click into SF half) — show a small "done" affordance.
  return (
    <div className="space-y-3">
      <HalfHeader half="purchase_register" subState="review" />
      <ReviewStep
        job={prJob}
        files={files}
        onFinalize={onContinueToSupplier}
        confirmCtaLabel="Continue to supplier export"
      />
    </div>
  )
}
```

- [ ] **Step 2: Create `SupplierHalf`**

Create `frontend/src/components/ingestion/SupplierHalf.tsx`:

```tsx
import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import { HalfHeader } from "@/components/ingestion/HalfHeader"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { UploadStep } from "@/components/ingestion/UploadStep"
import type { JobOut, IngestionFileOut } from "@/types/ingestion"

interface Props {
  clientId: string
  periodStart: string
  periodEnd: string
  sfJob?: JobOut
  files: IngestionFileOut[]
  /** PR job id to link the new SF job to. Required when sfJob is undefined. */
  linkedPrJobId?: string
  onJobCreated: (jobId: string) => void
}

export function SupplierHalf({
  clientId, periodStart, periodEnd, sfJob, files, linkedPrJobId, onJobCreated,
}: Props) {
  if (!sfJob) {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="upload" />
        <UploadStep
          clientId={clientId}
          kind="supplier_export"
          periodStart={periodStart}
          periodEnd={periodEnd}
          linkedPrJobId={linkedPrJobId}
          onCreated={onJobCreated}
        />
      </div>
    )
  }

  if (sfJob.status === "pending" || sfJob.status === "extracting") {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="extract" />
        <ExtractingStep
          files={files}
          filesDone={sfJob.files_done}
          filesTotal={sfJob.files_total}
        />
      </div>
    )
  }

  if (sfJob.status === "ready_for_review") {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="review" />
        <ReviewStep
          job={sfJob}
          files={files}
          onFinalize={() => { /* FinalizeStep takes over via wizard step-routing */ }}
          confirmCtaLabel="Run reconciliation"
        />
      </div>
    )
  }

  // confirmed | reconciling | completed | failed → FinalizeStep.
  return (
    <div className="space-y-3">
      <HalfHeader half="supplier_export" subState="review" />
      <FinalizeStep job={sfJob} clientId={clientId} />
    </div>
  )
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: errors only in `IngestionWizard.tsx` (to be rewritten next).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ingestion/PurchaseHalf.tsx frontend/src/components/ingestion/SupplierHalf.tsx
git commit -m "feat(ingestion): PurchaseHalf + SupplierHalf sub-step containers"
```

---

## Task 23: Frontend — rewrite `IngestionWizard`

**Files:**
- Modify: `frontend/src/components/ingestion/IngestionWizard.tsx`
- Create: `frontend/src/components/ingestion/__tests__/IngestionWizard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ingestion/__tests__/IngestionWizard.test.tsx`:

```tsx
import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { IngestionWizard } from "@/components/ingestion/IngestionWizard"
import { api } from "@/lib/api"

let mock: MockAdapter
beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const PR_ID = "11111111-1111-1111-1111-111111111111"
const SF_ID = "22222222-2222-2222-2222-222222222222"

function jobJson(over: Record<string, unknown>) {
  return {
    id: PR_ID, tenant_id: PR_ID, client_id: "c",
    kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
    status: "ready_for_review",
    files_total: 1, files_done: 1, rows_total: 4, rows_needs_review: 0,
    error_summary: null, reconciliation_id: null,
    linked_pr_job_id: null, linked_sf_job_id: null,
    reuse_pr_doc_id: null, reuse_sf_doc_id: null,
    created_at: "2026-05-15T00:00:00+00:00",
    updated_at: "2026-05-15T00:00:00+00:00",
    completed_at: null,
    ...over,
  }
}

describe("<IngestionWizard /> step routing", () => {
  it("renders the PurchaseHalf review when PR is ready_for_review with no SF", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}`).reply(200, {
      job: jobJson({}),
      files: [],
    })
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}/rows`).reply(200, { rows: [], total: 0, has_more: false })
    render(withClient(<IngestionWizard prJobId={PR_ID} clientId="c" />))
    await waitFor(() => expect(screen.getByText("Purchase register")).toBeInTheDocument())
    expect(screen.getByRole("button", { name: /continue to supplier export/i })).toBeInTheDocument()
  })

  it("renders SupplierHalf upload when PR is confirmed and no SF exists", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}`).reply(200, {
      job: jobJson({ status: "confirmed", linked_sf_job_id: null }),
      files: [],
    })
    render(withClient(<IngestionWizard prJobId={PR_ID} clientId="c" />))
    await waitFor(() => expect(screen.getByText("Supplier-filed export")).toBeInTheDocument())
    expect(screen.getByText(/upload/i)).toBeInTheDocument()
  })

  it("fetches the linked SF job and shows FinalizeStep when SF is confirmed", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}`).reply(200, {
      job: jobJson({ status: "confirmed", linked_sf_job_id: SF_ID }),
      files: [],
    })
    mock.onGet(`/api/v1/ingestion/jobs/${SF_ID}`).reply(200, {
      job: jobJson({ id: SF_ID, kind: "supplier_export", status: "confirmed", linked_pr_job_id: PR_ID }),
      files: [],
    })
    render(withClient(<IngestionWizard prJobId={PR_ID} clientId="c" />))
    await waitFor(() => expect(screen.getByText(/Ready to finalize/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Rewrite the wizard**

Replace `frontend/src/components/ingestion/IngestionWizard.tsx`:

```tsx
import { useQueryClient } from "@tanstack/react-query"

import { PurchaseHalf } from "@/components/ingestion/PurchaseHalf"
import { Stepper, statusToStep } from "@/components/ingestion/Stepper"
import { SupplierHalf } from "@/components/ingestion/SupplierHalf"
import { Card, CardContent } from "@/components/ui/card"
import { ingestionKeys, useJob } from "@/hooks/useIngestion"

interface Props {
  /** The PR job id (or, in the SF-only / PR-reused case, the SF job id). */
  prJobId: string
  clientId: string
}

export function IngestionWizard({ prJobId, clientId }: Props) {
  const qc = useQueryClient()
  const primary = useJob(prJobId)

  // Derive the secondary job id BEFORE the loading guard so the useJob
  // hook call below is unconditional (Rules of Hooks).
  const primaryJob = primary.data?.job
  const isSfOnlySession =
    primaryJob?.kind === "supplier_export" && Boolean(primaryJob?.reuse_pr_doc_id)
  const secondaryJobId =
    (!isSfOnlySession && primaryJob?.linked_sf_job_id) || undefined
  const secondary = useJob(secondaryJobId)

  if (primary.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading job…</p>
  }
  if (primary.isError || !primary.data) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {(primary.error as Error)?.message ?? "Failed to load job."}
        </CardContent>
      </Card>
    )
  }

  const primaryFiles = primary.data.files

  // SF-only path: the "primary" job IS the SF job. No PR job exists.
  if (isSfOnlySession) {
    const step = statusToStep(undefined, primary.data.job)
    return (
      <div className="space-y-6">
        <Stepper activeStep={step} />
        <SupplierHalf
          clientId={clientId}
          periodStart={primary.data.job.period_start}
          periodEnd={primary.data.job.period_end}
          sfJob={primary.data.job}
          files={primaryFiles}
          onJobCreated={() => { /* SF job already exists in this path */ }}
        />
      </div>
    )
  }

  // Standard path: PR job is primary. SF job (if any) was already fetched
  // via `secondary` above.
  const prJob = primary.data.job
  const sfJob = secondary.data?.job
  const sfFiles = secondary.data?.files ?? []

  const step = statusToStep(prJob, sfJob)

  function handleSfCreated(newSfJobId: string) {
    // Refetch PR so its linked_sf_job_id reverse-lookup updates, plus prime the SF cache.
    qc.invalidateQueries({ queryKey: ingestionKeys.job(prJob.id) })
    qc.invalidateQueries({ queryKey: ingestionKeys.job(newSfJobId) })
  }

  return (
    <div className="space-y-6">
      <Stepper activeStep={step} />

      {/* Half 1: Purchase register — shown while PR is not yet confirmed,
          OR while it is confirmed but no SF job has been created yet. */}
      {(prJob.status !== "confirmed" && prJob.status !== "completed") && (
        <PurchaseHalf
          clientId={clientId}
          periodStart={prJob.period_start}
          periodEnd={prJob.period_end}
          prJob={prJob}
          files={primaryFiles}
          onContinueToSupplier={async () => {
            // PR is ready_for_review here; ReviewStep's onFinalize fires when
            // the user hits "Continue to supplier export" after bulk-confirm.
            // The wizard's role: advance PR to 'confirmed' via the finalize
            // endpoint dry-run? No — we keep PR in ready_for_review until the
            // user has uploaded SF and finalized. Just re-fetch.
            qc.invalidateQueries({ queryKey: ingestionKeys.job(prJob.id) })
          }}
          onJobCreated={() => { /* PR job already exists in this branch */ }}
        />
      )}

      {/* Half 2: Supplier export — shown once PR is confirmed/completed
          (or when linked SF exists already). */}
      {(prJob.status === "confirmed" || prJob.status === "completed") && (
        <SupplierHalf
          clientId={clientId}
          periodStart={prJob.period_start}
          periodEnd={prJob.period_end}
          sfJob={sfJob}
          files={sfFiles}
          linkedPrJobId={prJob.id}
          onJobCreated={handleSfCreated}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Update `IngestionJob.tsx` to use the new prop name**

In `frontend/src/pages/IngestionJob.tsx`, change the `<IngestionWizard jobId={...}` line to `<IngestionWizard prJobId={...}` (the param being passed is the URL `jobId`, which in the standard path IS the PR job id and in the SF-only path is the SF job id — either way it's the wizard's "primary" job).

```tsx
<IngestionWizard prJobId={jobId} clientId={clientId} />
```

- [ ] **Step 4: Resolve the PR-confirm transition gap**

`ReviewStep`'s `onFinalize` callback fires on the "Continue to supplier export" button click but does NOT itself move PR from `ready_for_review` to `confirmed`. We need the PR job to flip to `confirmed` so the wizard's step-routing renders the SF half.

Update `ReviewStep`'s "Continue to supplier export" path to call the existing `bulk-confirm` for any auto-passed rows? No — the existing flow already requires `rows_needs_review === 0` before the button enables. The actual transition happens via a real finalize call.

Since we never want to actually finalize the PR alone (it would attempt handoff and fail), we add a **lightweight "confirm" endpoint** on the backend that does only `ready_for_review → confirmed` without invoking handoff.

Backend: add to `app/ingestion/service.py`:

```python
async def confirm_job_review(*, job_id: UUID, tenant_id: UUID) -> None:
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise JobNotFoundError(message=f"Job {job_id} not found")
    needs = await p.count_needs_review(job_id, tenant_id=tenant_id)
    if needs > 0:
        err = IngestionError(message=f"{needs} rows still need review")
        err.code = "INGESTION_REVIEW_INCOMPLETE"; err.status_code = 422
        raise err
    current = JobStatus(job["status"])
    if current == JobStatus.CONFIRMED:
        return  # idempotent
    assert_can_transition(current, JobStatus.CONFIRMED)
    await p.update_job_status(job_id, JobStatus.CONFIRMED, tenant_id=tenant_id)
```

Backend: add to `app/ingestion/router.py`:

```python
@router.post("/jobs/{job_id}/confirm-review")
async def confirm_review_endpoint(
    job_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> dict:
    try:
        await svc.confirm_job_review(job_id=job_id, tenant_id=tenant_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })
    return {"ok": True}
```

Frontend: add to `frontend/src/lib/ingestion/api.ts`:

```ts
export async function confirmJobReview(jobId: string): Promise<void> {
  await api.post(`/api/v1/ingestion/jobs/${jobId}/confirm-review`)
}
```

Frontend: add to `frontend/src/hooks/useIngestion.ts`:

```ts
import { confirmJobReview } from "@/lib/ingestion/api"

export function useConfirmJobReview(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => confirmJobReview(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) }),
  })
}
```

Frontend: wire it into `PurchaseHalf` — replace the `onFinalize={onContinueToSupplier}` line in the `ready_for_review` branch with an inline handler that calls confirmJobReview, then onContinueToSupplier:

```tsx
import { useConfirmJobReview } from "@/hooks/useIngestion"

// inside PurchaseHalf, before the return statements:
const confirmReview = useConfirmJobReview(prJob?.id ?? "")

// inside the ready_for_review branch:
<ReviewStep
  job={prJob}
  files={files}
  onFinalize={async () => {
    try {
      await confirmReview.mutateAsync()
      onContinueToSupplier()
    } catch (e) {
      // toast handled by parent's mutation error; surface here for safety
      const { toast } = await import("sonner")
      toast.error((e as Error).message)
    }
  }}
  confirmCtaLabel="Continue to supplier export"
/>
```

- [ ] **Step 5: Run the wizard test**

Run: `cd frontend && npx vitest run src/components/ingestion/__tests__/IngestionWizard.test.tsx`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/service.py backend/app/ingestion/router.py frontend/src/lib/ingestion/api.ts frontend/src/hooks/useIngestion.ts frontend/src/components/ingestion/IngestionWizard.tsx frontend/src/components/ingestion/PurchaseHalf.tsx frontend/src/components/ingestion/__tests__/IngestionWizard.test.tsx frontend/src/pages/IngestionJob.tsx
git commit -m "feat(ingestion): combined PR+SF wizard with confirm-review handoff"
```

---

## Task 24: Frontend — `SetupStep` + new `IngestionNew`

**Files:**
- Create: `frontend/src/components/ingestion/SetupStep.tsx`
- Modify: `frontend/src/pages/IngestionNew.tsx`
- Create: `frontend/src/components/ingestion/__tests__/SetupStep.test.tsx`

- [ ] **Step 1: Create `SetupStep`**

Create `frontend/src/components/ingestion/SetupStep.tsx`:

```tsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { PeriodPicker } from "@/components/reconciliation/PeriodPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useStartSession } from "@/hooks/useIngestion"
import { usePriorDocs } from "@/hooks/usePriorDocs"
import { ApiError } from "@/lib/api"

interface Props {
  clientId: string
}

export function SetupStep({ clientId }: Props) {
  const navigate = useNavigate()
  const startSession = useStartSession()

  const [period, setPeriod] = useState({ start: "", end: "" })
  const [reusePr, setReusePr] = useState(false)
  const [reuseSf, setReuseSf] = useState(false)

  const periodError = period.start && period.end && period.end < period.start
    ? "Period end must be on or after period start" : undefined
  const periodComplete = Boolean(period.start && period.end && !periodError)

  const prior = usePriorDocs(clientId, period.start, period.end)
  const priorPr = prior.data?.pr ?? null
  const priorSf = prior.data?.sf ?? null

  async function handleStart() {
    if (!periodComplete) return
    try {
      const res = await startSession.mutateAsync({
        client_id: clientId,
        period_start: period.start,
        period_end: period.end,
        reuse_pr_doc_id: reusePr && priorPr ? priorPr.id : undefined,
        reuse_sf_doc_id: reuseSf && priorSf ? priorSf.id : undefined,
      })
      if (res.reconciliation_id) {
        toast.success("Reconciliation complete")
        navigate(`/clients/${clientId}/recon/${res.reconciliation_id}`, { replace: true })
        return
      }
      // The wizard URL always points at whichever job exists (PR if any,
      // otherwise the SF job).
      const wizardJobId = res.pr_job_id ?? res.sf_job_id
      if (!wizardJobId) {
        toast.error("Session start returned no job id")
        return
      }
      navigate(`/clients/${clientId}/ingestion/${wizardJobId}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      toast.error(msg)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Period</CardTitle></CardHeader>
        <CardContent>
          <PeriodPicker
            start={period.start}
            end={period.end}
            onChange={setPeriod}
            disabled={startSession.isPending}
            errorMessage={periodError}
          />
        </CardContent>
      </Card>

      {periodComplete && (priorPr || priorSf) && (
        <Card>
          <CardHeader><CardTitle>Reuse prior documents?</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {priorPr && (
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reusePr}
                  onChange={(e) => setReusePr(e.target.checked)}
                  disabled={startSession.isPending}
                  className="mt-1"
                />
                <span className="text-sm">
                  <span className="font-medium">Reuse purchase register</span>
                  <span className="block text-muted-foreground">
                    {priorPr.original_filename} · {new Date(priorPr.created_at).toLocaleDateString()}
                  </span>
                </span>
              </label>
            )}
            {priorSf && (
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reuseSf}
                  onChange={(e) => setReuseSf(e.target.checked)}
                  disabled={startSession.isPending}
                  className="mt-1"
                />
                <span className="text-sm">
                  <span className="font-medium">Reuse supplier-filed export</span>
                  <span className="block text-muted-foreground">
                    {priorSf.original_filename} · {new Date(priorSf.created_at).toLocaleDateString()}
                  </span>
                </span>
              </label>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-3">
        <Button
          onClick={handleStart}
          disabled={!periodComplete || startSession.isPending}
        >
          {startSession.isPending ? "Starting…" : "Start"}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Rewrite `IngestionNew.tsx`**

Replace `frontend/src/pages/IngestionNew.tsx`:

```tsx
import { useParams } from "react-router-dom"

import { SetupStep } from "@/components/ingestion/SetupStep"
import { Stepper } from "@/components/ingestion/Stepper"
import { PageHeader } from "@/components/layout/PageHeader"
import { useClient } from "@/hooks/useClients"

export function IngestionNew() {
  const { id: clientId } = useParams<{ id: string }>()
  const { data: client } = useClient(clientId)
  if (!clientId) return <p className="text-muted-foreground">Missing client id.</p>
  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "Client", to: `/clients/${clientId}` },
          { label: "New ingestion" },
        ]}
        title="New ingestion"
        subtitle="Pick a period. We'll walk you through the purchase register and the supplier-filed export, then reconcile."
      />
      <Stepper activeStep={1} />
      <SetupStep clientId={clientId} />
    </div>
  )
}
```

- [ ] **Step 3: Write the SetupStep test**

Create `frontend/src/components/ingestion/__tests__/SetupStep.test.tsx`:

```tsx
import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import MockAdapter from "axios-mock-adapter"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { SetupStep } from "@/components/ingestion/SetupStep"
import { api } from "@/lib/api"

let mock: MockAdapter
beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const CLIENT = "33333333-3333-3333-3333-333333333333"

describe("<SetupStep />", () => {
  it("does not show reuse offers when there are no prior docs", async () => {
    mock.onGet("/api/v1/ingestion/documents/recent").reply(200, { pr: null, sf: null })
    render(withClient(<SetupStep clientId={CLIENT} />))
    const start = await screen.findByLabelText("Period start")
    const end = await screen.findByLabelText("Period end")
    await userEvent.type(start, "2026-05-01")
    await userEvent.type(end, "2026-05-31")
    await waitFor(() => expect(mock.history.get.length).toBeGreaterThanOrEqual(1))
    expect(screen.queryByText(/Reuse prior documents/i)).not.toBeInTheDocument()
  })

  it("shows a reuse offer for an existing PR doc", async () => {
    mock.onGet("/api/v1/ingestion/documents/recent").reply(200, {
      pr: {
        id: "44444444-4444-4444-4444-444444444444",
        doc_type: "purchase_register",
        original_filename: "old-pr.xlsx",
        file_size_bytes: 1024,
        created_at: "2026-04-15T00:00:00+00:00",
      },
      sf: null,
    })
    render(withClient(<SetupStep clientId={CLIENT} />))
    await userEvent.type(screen.getByLabelText("Period start"), "2026-05-01")
    await userEvent.type(screen.getByLabelText("Period end"), "2026-05-31")
    await waitFor(() => expect(screen.getByText("old-pr.xlsx", { exact: false })).toBeInTheDocument())
    expect(screen.getByText(/Reuse purchase register/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/ingestion/__tests__/SetupStep.test.tsx`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ingestion/SetupStep.tsx frontend/src/pages/IngestionNew.tsx frontend/src/components/ingestion/__tests__/SetupStep.test.tsx
git commit -m "feat(ingestion): SetupStep entry page with period + reuse-doc checkboxes"
```

---

## Task 25: Frontend — verify whole test suite + manual smoke

**Files:** (none directly — verification only)

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: All tests PASS (pre-existing + new). If a pre-existing test breaks because it imported `statusToStep(jobStatus)` with the old signature, update the caller.

- [ ] **Step 2: Run the full backend test suite**

Run: `cd backend && pytest -x`
Expected: PASS (live-DB tests SKIPPED if env not set; pure-logic tests PASS).

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Manual Playwright smoke (recorded as a checklist; not automated here)**

Run the dev stack (`uvicorn app.main:app --reload` and `npm run dev`), then walk through:

1. New client → start ingestion → Setup page shows period only.
2. Pick period (e.g. 2026-07-01 → 2026-07-31). No reuse offers (first time).
3. Click Start → land on `/clients/:id/ingestion/:prJobId` showing Stepper at step 2 + PurchaseHalf upload card.
4. Upload PR xlsx → extract → review → click **Continue to supplier export**.
5. Stepper advances to step 3, SupplierHalf upload card appears.
6. Upload SF xlsx → extract → review → click **Run reconciliation**.
7. Stepper advances to step 4 (Reconcile) → step 5 (Done) → auto-redirects to recon report.
8. Start a *second* ingestion for the same client/period → Setup page now shows both reuse checkboxes. Tick both. Click Start → goes straight to recon report (no upload steps).
9. Trigger a failure: in a third ingestion, finalize SF with zero confirmed rows (manually reject all) → confirm the new `Last attempt failed` error banner appears on the Ready-to-finalize card.

- [ ] **Step 5: Commit a no-op marker if you made any final lint/type adjustments; otherwise skip**

```bash
# Only if needed:
git add -A && git commit -m "chore(ingestion): post-suite housekeeping"
```

---

## Done

Once all 25 tasks are checked off, the combined-ingestion wizard is live on `phase-f-adaptive-ingestion`. Open a PR per the existing branch convention.
