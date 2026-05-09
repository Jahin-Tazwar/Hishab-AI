# Adaptive File Ingestion — Design

**Date:** 2026-05-10
**Author:** HishabAI team (brainstormed with Claude)
**Status:** Approved for planning
**Supersedes:** Nothing — additive to the existing reconciliation pipeline

---

## 1. Context & Problem

HishabAI's current reconciliation pipeline accepts only XLSX files with a rigid set of canonical column headers (`"invoice no"`, `"supplier bin"`, etc.). The parser at `backend/app/reconciliation/parser.py` fails hard on missing or renamed columns.

In real CA-firm operation:
- **Mushak 6.1 purchase registers** typically arrive as Excel.
- **Mushak 6.3 invoices and supplier exports** arrive in many shapes: born-digital PDFs from supplier ERPs, scans of invoice books, photos of paper invoices, hand-written or printed register tables, and mixed bags of all of the above.

CA staff currently spend hours per filing period **manually transcribing non-XLSX inputs into a canonical Excel** before they can run reconciliation. This is the largest hidden cost in the workflow today.

**User research signal (estimated by team):**
- ~20-30%: stack of separate Mushak 6.3 invoice PDFs
- ~20-30%: one bundled scan/PDF of an invoice book
- ~10%: scanned image of an already-tabulated register
- ~10%: phone photos of invoices
- **~50%+: mixed bag in a single upload session**

The dominant case is heterogeneous mixed input — so the new ingestion pipeline must be a per-file router, not a single-format importer.

## 2. Goals & Non-Goals

### Goals

1. Accept XLSX/CSV/PDF/image inputs (born-digital and scanned), in any combination, in a single upload session.
2. Extract structured data adaptively — tolerate renamed columns, Bangla headers, layout variation, extra/missing fields.
3. Bangla document support across every engine path.
4. Maintain a strict **reliability-over-automation** posture: anything OCR-touched must pass through human review before entering reconciliation.
5. Preserve the existing XLSX flow with **bit-for-bit backward compatibility** — zero regression risk on the path that's working today.
6. Production-ready: cost-aware, observable, scalable, recoverable from failures.

### Non-Goals (v1)

- Mobile-first upload UX (web-responsive only)
- Auto-learned per-supplier extraction templates
- Direct integration with NBR portal or supplier ERPs
- Multi-language UI strings beyond what the rest of the app already supports
- Tesseract local OCR (architectural slot reserved; not shipped)
- Storage cleanup / retention enforcement (deferred to a follow-up)
- Real-time co-editing of the review queue across multiple staff

## 3. Top-Level Decisions

These were the load-bearing choices made during brainstorming:

| Decision | Choice | Rationale |
|---|---|---|
| Input handling for non-XLSX | Per-file MIME router | Mixed-bag dominates (~50%+) |
| Trust model for extracted rows | **Two-tier by file type** — born-digital → auto-pass; OCR/vision → mandatory review | Deterministic trust signal beats probabilistic confidence; OCR is too risky to silently auto-trust |
| Wait-time UX | Hybrid: foreground progress page that's nav-safe, with in-app notification when done | Works for both single-task and multi-task workflows; one Realtime channel serves both views |
| Engine architecture | Layered: deterministic text extraction first, LLM for normalization + vision fallback | Cost scales with difficulty; debuggable; preserves current XLSX path unchanged |
| Worker model | In-process async workers with Postgres-backed job table | No new infra dependency (no Celery/Redis); simple migration path if we outgrow |
| LLM | Gemini 2.5 Flash (Vertex AI) — text mode and vision mode | Cheap, bilingual-native, structured-output support |

## 4. Architecture Overview

A new **ingestion service** sits in front of the existing reconciliation pipeline. It ends by producing the same canonical `PurchaseRow` / `SupplierRow` data that today comes from XLSX parsing — so the existing reconciliation engine is not modified.

```
                         ┌─────────────────────────────┐
                         │      Frontend (React)       │
                         │  • Multi-file upload        │
                         │  • Live extraction progress │
                         │  • Review queue UI          │
                         └────────────┬────────────────┘
                                      │ REST + Supabase Realtime
                                      ▼
       ┌────────────────────────────────────────────────────────────┐
       │                  FastAPI service (existing)                │
       │                                                            │
       │   /api/v1/ingestion/jobs   ─── new ──┐                     │
       │   /api/v1/reconciliations  ─── existing, unchanged ──┐     │
       │                                      │               │     │
       │      ┌───────────────────────────────▼─────┐         │     │
       │      │     Ingestion Module (new)          │         │     │
       │      │  • job orchestrator                 │         │     │
       │      │  • file router by MIME              │         │     │
       │      │  • engine adapters                  │         │     │
       │      │  • normalizer → Purchase/SupplierRow│         │     │
       │      └────────────┬────────────────────────┘         │     │
       │                   │ on review-complete:              │     │
       │                   │ writes canonical XLSX → Storage  │     │
       │                   │ then calls existing service ─────┘     │
       │                                                            │
       │      ┌──────────────────────────────────────────────┐      │
       │      │   Reconciliation Module (existing)           │      │
       │      │   service.run_reconciliation(...)            │      │
       │      └──────────────────────────────────────────────┘      │
       └────────────────────┬───────────────────────────────────────┘
                            │
                  ┌─────────┴────────────┬──────────────────┐
                  ▼                      ▼                  ▼
        ┌──────────────────┐   ┌──────────────────┐  ┌──────────────┐
        │ Supabase Postgres │   │ Supabase Storage │  │ Gemini 2.5   │
        │ • new tables:     │   │ • recon-files    │  │ Flash        │
        │   ingestion_jobs  │   │ • ingestion-files │  │ (Vertex AI)  │
        │   ingestion_files │   │   (new bucket)    │  └──────────────┘
        │   extracted_rows  │   └──────────────────┘
        │ • RLS by tenant   │
        └──────────────────┘
```

### Architectural commitments

- **In-process async worker, Postgres-backed job table.** No Celery/Redis dependency. Workers in any FastAPI instance pull jobs via `SELECT ... FOR UPDATE SKIP LOCKED`. Lease re-claim on crash via timestamp comparison.
- **Ingestion is a separate FastAPI module** (`backend/app/ingestion/`) mirroring the existing `reconciliation/` module structure (router, service, schemas, etc.).
- **One-way handoff to reconciliation:** ingestion serializes confirmed rows to a canonical XLSX, uploads to existing `recon-files` bucket as a normal `documents` row, then calls existing `run_reconciliation()` in-process with that doc ID. Reconciliation does not know ingestion exists.
- **Realtime via Supabase Realtime** subscribed to `ingestion_jobs` and `ingestion_files`. RLS already gates by tenant. No WebSocket plumbing on the FastAPI side.
- **Existing `/api/v1/reconciliations` endpoint and pipeline are unchanged.** New flow is purely additive.

## 5. File Router & Extraction Engines

A single `extract_file(file_bytes, mime, original_filename)` entry point routes by MIME, runs one of the engines, and returns a uniform shape:

```python
class ExtractedFileResult:
    rows: list[ExtractedRow]   # always normalized to canonical schema
    needs_review: bool         # True if any branch involved OCR/vision
    extraction_engine: str     # "pandas" | "pandas+llm-mapper"
                               # | "pdfplumber+llm" | "gemini-vision"
                               # (Tesseract reserved for future: "tesseract+llm")
    page_count: int
    warnings: list[str]        # surface non-fatal issues to the review UI
```

### Routing decision table

| MIME / extension | Engine path | Review required? | Typical latency | Cost/file |
|---|---|---|---|---|
| `.xlsx`, `.xls`, `.csv`, `.tsv` with **canonical headers** | pandas (existing parser) | ❌ auto-pass | <1s | $0 |
| Same, with **non-canonical headers** | pandas + Gemini Flash text-mode column mapper | ❌ auto-pass | 1-3s | ~$0.0001 |
| **Born-digital PDF** (extractable text via pdfplumber heuristic) | pdfplumber → text+layout → Gemini Flash text → schema | ❌ auto-pass | 2-5s | ~$0.0002 |
| **Scanned PDF, image PDF** (no extractable text) | render pages → Gemini Flash vision → schema | ✅ review queue | 10-30s | ~$0.001-0.003 |
| **`.png`, `.jpg`, `.jpeg`, `.tiff`, `.webp`, `.heic`** | (HEIC/WEBP→PNG via Pillow if needed) → Gemini Flash vision → schema | ✅ review queue | 10-20s | ~$0.001-0.002 |
| **Unknown / unsupported** | Reject at upload with clear error; log MIME | n/a | n/a | n/a |

### Engine details

**1. Pandas (existing, unchanged).** Same `parse_purchase_register` / `parse_supplier_export` from the existing parser, reused as-is. Canonical-vs-non-canonical detection happens at the router level by inspecting headers BEFORE engine selection.

**2. LLM Column Mapper (new, shared across XLSX-non-canonical and PDF-text branches).** Single Gemini Flash call with structured output (JSON schema). Maps each canonical field to the source column or `null`. Result cached per `(tenant_id, kind, header_signature)` in `column_mappings`. Surfaces inferred mapping for first-time confirmation; subsequent uploads skip the LLM call entirely.

**3. pdfplumber + LLM normalizer (born-digital PDFs).** pdfplumber extracts text per page with layout. Raw text + extracted tables fed to Gemini Flash with canonical schema as structured output. Single-invoice PDFs → 1 row out; multi-invoice PDFs → N rows. Bangla preserved natively (Unicode end-to-end).

**4. Gemini Flash Vision (scans, photos, image PDFs).** Image PDFs rendered with `pypdfium2` at 200 DPI to PNG (no Poppler dep). Multi-page docs sent in a single multi-part vision request when ≤10 pages; chunked + merged for longer. Prompt enforces: extract every distinguishable invoice into one row matching canonical schema; flag unreadable areas in `warnings`. **Always feeds review queue.**

**5. Tesseract Bangla — DEFERRED.** Architectural slot reserved (engine adapter interface). Not shipped in v1. Rationale: Gemini Flash vision is already cheap and beats Tesseract on quality, especially Bangla. Avoids `tesseract-ocr-ben` apt install bloat.

### Format conversion utilities

- **HEIC/HEIF**: `pillow-heif` → PNG before vision call.
- **WEBP**: Pillow native.
- **Born-digital vs scanned PDF detection**: per-page text density heuristic via pdfplumber. `< 50 chars total per page` → treat as scanned. Handles text-layered scans by per-page evaluation.

### Multi-invoice / multi-page handling

LLM prompts always say "extract every distinguishable invoice." A 5-page bundled scan = potentially 5 rows out. A 2-page Mushak 6.3 = 1 row. The job tracks rows per file (`extracted_rows.source_file_id`, `source_page_no`) so the review UI can show originating page next to each row.

### Field-level validation warnings

Run **after** extraction, **before** review. Deterministic — not confidence scores:

- "Page N was unreadable" → row possibly missing; banner on file.
- "BIN format invalid: 'X' (expected 9-13 digits)" → row surfaces with field flagged red.
- "Date 'X' not parseable" → row surfaces with date flagged.
- "Amount and VAT don't reconcile (15% rule)" → soft warning (some Mushak categories use other rates).

These guide the reviewer's eye but never auto-reject.

## 6. Data Model

### New tables

**`ingestion_jobs`**

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | RLS scope |
| `client_id` | uuid FK | |
| `created_by` | uuid FK | |
| `kind` | enum | `purchase_register` \| `supplier_export` |
| `period_start` | date | |
| `period_end` | date | |
| `status` | enum | `pending` \| `extracting` \| `ready_for_review` \| `confirmed` \| `reconciling` \| `completed` \| `failed` |
| `files_total` | int | |
| `files_done` | int | atomically incremented as workers finish |
| `rows_total` | int | |
| `rows_needs_review` | int | |
| `created_at`, `updated_at`, `completed_at` | timestamptz | |
| `error_summary` | text NULL | aggregate; per-file errors live in `ingestion_files` |
| `reconciliation_id` | uuid NULL | set on handoff |

**`ingestion_files`**

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `job_id` | uuid FK | |
| `tenant_id` | uuid | denormalized for RLS perf |
| `storage_path` | text | in `ingestion-files` bucket |
| `original_filename` | text | |
| `mime_type` | text | |
| `byte_size` | bigint | |
| `engine` | text NULL | set after routing |
| `status` | enum | `queued` \| `extracting` \| `extracted` \| `failed` \| `skipped` |
| `rows_extracted` | int | |
| `needs_review` | bool | determined by engine choice |
| `warnings` | jsonb | list of `{code, message, page?}` |
| `error` | text NULL | |
| `extracted_at` | timestamptz | |

**`extracted_rows`**

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `file_id` | uuid FK | |
| `job_id` | uuid FK | denormalized for review queries |
| `tenant_id` | uuid | denormalized for RLS |
| `source_page_no` | int NULL | for vision branch |
| `row_data` | jsonb | canonical fields (matches `PurchaseRow` / `SupplierRow`) |
| `row_data_original` | jsonb | immutable copy of extraction output |
| `status` | enum | `auto_passed` \| `needs_review` \| `confirmed` \| `rejected` \| `edited` |
| `field_warnings` | jsonb | per-field validation issues |
| `reviewed_by` | uuid NULL | |
| `reviewed_at` | timestamptz NULL | |
| `created_at` | timestamptz | |

**`column_mappings`**

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid FK | |
| `kind` | enum | `purchase_register` \| `supplier_export` |
| `header_signature` | text | canonicalized header set (sorted, lowercase, hashed) |
| `mapping` | jsonb | `{ invoice_no: "Bill No", supplier_bin: "BIN", ... }` |
| `confirmed_by` | uuid NULL | set when user confirms |
| `created_at` | timestamptz | |
| **UNIQUE** | | `(tenant_id, kind, header_signature)` |

### Indexes

- `ingestion_jobs (tenant_id, status, created_at DESC)` — recent jobs view
- `ingestion_files (job_id, status)` — progress tracking
- `extracted_rows (job_id, status)` — review queue listing
- `extracted_rows (job_id) WHERE status = 'needs_review'` — partial index for the most common query
- `column_mappings` unique constraint already covers the lookup

### RLS

All four tables: `tenant_id = (auth.jwt() ->> 'tenant_id')::uuid`. Service-role bypass for the worker (operates inside FastAPI service which already uses the admin client for system operations).

### Storage buckets

- **`ingestion-files`** (new): original uploads. 90-day retention via cleanup job — deferred post-v1.
- **`recon-files`** (existing): canonical XLSX written by handoff step.

## 7. Job Lifecycle

```
              ┌──────────┐
              │ pending  │  ← created when files uploaded
              └─────┬────┘
                    │ worker picks up (SELECT ... FOR UPDATE SKIP LOCKED)
                    ▼
              ┌──────────────┐
              │ extracting   │  ← per-file workers run in parallel (bounded concurrency)
              └─────┬────────┘
                    │ all files done (succeeded or failed)
                    ▼
            ┌──────────────────┐
            │ ready_for_review │  ← user opens review UI
            └─────┬─────┬──────┘
                  │     │ user reviews + confirms
                  ▼     ▼
              ┌──────────────┐
              │ confirmed    │  ← all needs_review rows resolved
              └─────┬────────┘
                    │ trigger reconciliation handoff
                    ▼
              ┌──────────────┐
              │ reconciling  │
              └─────┬────────┘
                    │ run_reconciliation() returns
                    ▼
              ┌──────────────┐
              │ completed    │  ← reconciliation_id set on the job
              └──────────────┘

  (any unrecoverable error → failed; per-file failures don't fail the job)
```

### Invariants

- Auto-pass rows are written with `status = auto_passed` immediately on file extraction. They're confirmed by default — review UI only shows `needs_review` rows.
- `confirmed → reconciling` requires zero rows in `needs_review`. Auto-pass rows never block.
- Per-file failures degrade gracefully: failed file marks itself with error message; job continues; review UI surfaces failed files but doesn't block confirming the rows that did extract.
- `reconciling → completed` calls existing `run_reconciliation()` with canonical XLSX docs.

### Handoff to reconciliation (the bridge)

When job transitions `confirmed → reconciling`:

1. Collect confirmed/edited rows for the job, separated by `kind`.
2. Serialize each set into a canonical XLSX matching the format the existing parser expects.
3. Upload each XLSX to existing `recon-files` bucket; insert a row into existing `documents` table.
4. Construct a `ReconciliationCreateRequest` with new doc IDs + `client_id` + period; call existing `run_reconciliation()` in-process.
5. Set `ingestion_jobs.reconciliation_id` to the returned reconciliation ID.

The existing reconciliation pipeline is unaware of ingestion. Rollback to "old way" is trivial.

## 8. API Surface

All under `/api/v1/ingestion`. RLS-scoped via existing `get_current_tenant_id` / `get_current_user_id` dependencies.

| Method | Path | Purpose | Returns |
|---|---|---|---|
| `POST` | `/jobs` | Create ingestion job (multipart). Body: `client_id`, `period_start`, `period_end`, `kind`, `files[]`. Validates synchronously; persists job + files; kicks off background extraction. | `201 { job_id, files: [...] }` |
| `GET` | `/jobs/{id}` | Fetch full job state — job + files + counts. Initial render + Realtime fallback. | `200 { job, files, rows_summary }` |
| `GET` | `/jobs/{id}/rows` | List extracted rows. `?filter=needs_review\|all`. Default `needs_review`. Paginated. | `200 { rows: [...], page_info }` |
| `PATCH` | `/jobs/{id}/rows/{row_id}` | Edit row. Body: full `row_data`. Sets `status = edited`. | `200 { row }` |
| `POST` | `/jobs/{id}/rows/{row_id}/confirm` | Confirm as-extracted. | `200 { row }` |
| `POST` | `/jobs/{id}/rows/{row_id}/reject` | Drop row. Sets `status = rejected`. | `200 { row }` |
| `POST` | `/jobs/{id}/rows/bulk-confirm` | Body: `{ row_ids: [...] }`. Confirms only the listed IDs (only ever called for `needs_review` rows by the UI). | `200 { confirmed_count }` |
| `POST` | `/jobs/{id}/finalize` | Idempotent. Validates zero `needs_review` remain → triggers handoff + reconciliation. | `200 { reconciliation_id }` |
| `GET` | `/jobs/{id}/files/{file_id}/preview` | Stream original file bytes for review viewer. RLS-gated. | `200` file bytes |
| `GET` | `/column-mappings/pending` | Lists mapping inferences awaiting confirmation. | `200 { mappings: [...] }` |
| `POST` | `/column-mappings/{id}/confirm` | User approves inferred mapping. Becomes cached default. | `200 { mapping }` |

### Realtime channels

- `ingestion_jobs:id=eq.{job_id}` — job-level status + counters
- `ingestion_files:job_id=eq.{job_id}` — per-file progress

## 9. Frontend UX

### Route map

```
/ingestion                      — list of recent ingestion jobs
/ingestion/new                  — multi-file upload form (client + period + drag-drop)
/ingestion/jobs/:id             — auto-routes by job.status:
  ├─ /progress                  — live progress with per-file status
  ├─ /review                    — split-pane review queue (only when ready_for_review)
  ├─ /reconciling               — spinner + status
  ├─ /completed                 — link to resulting reconciliation report
  └─ /failed                    — error summary + retry / re-upload
```

### Review UI — split-pane layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ABC Pharma Ltd · April 2026 · 47 of 50 rows ready · 3 need review       │
│  [Approve all visible]  [Save & exit]  [Finalize → run reconciliation]   │
├────────────────────────────────────┬─────────────────────────────────────┤
│                                    │ ⚠ NEEDS REVIEW (3)                  │
│   ╔════════════════════════╗       │ ┌─────────────────────────────────┐ │
│   ║                        ║       │ │ Row 1 of 3                      │ │
│   ║   [PDF page rendered]  ║       │ │ Source: invoice_042.pdf, page 1 │ │
│   ║   highlight = field    ║       │ │                                 │ │
│   ║   the right pane is    ║       │ │ Invoice No  [INV-042-A]         │ │
│   ║   focused on           ║       │ │ Supplier BIN [123456789]  ⚠ ?   │ │
│   ║                        ║       │ │ Supplier Name [আদিল এন্টারপ্রাইজ]│ │
│   ║                        ║       │ │ Invoice Date [2026-04-15]       │ │
│   ║                        ║       │ │ Taxable BDT  [12,500.00]        │ │
│   ║                        ║       │ │ VAT BDT      [1,875.00]         │ │
│   ║                        ║       │ │                                 │ │
│   ║                        ║       │ │ ⚠ BIN format invalid (need 9-13)│ │
│   ║                        ║       │ │                                 │ │
│   ╚════════════════════════╝       │ │ [Confirm] [Save edits] [Reject] │ │
│   ◀ page 1 of 1 ▶                  │ │ [Skip — review later]           │ │
│                                    │ └─────────────────────────────────┘ │
│                                    │                                     │
│                                    │ ▼ AUTO-PASSED (44) [collapsed]      │
└────────────────────────────────────┴─────────────────────────────────────┘
```

### Interaction rules

- Click a row in the right queue → left pane jumps to that file/page.
- Editing a field updates `row_data` locally; `[Save edits]` persists via PATCH and advances.
- `[Confirm]` accepts as-extracted; `[Reject]` drops; both advance.
- `[Approve all visible]` bulk-confirms only the rows currently filtered as needs-review — never silently auto-confirms anything in the auto-passed group.
- `[Skip]` keeps row in `needs_review`; finalize blocked until queue is empty.
- `[Finalize]` is **disabled** until `needs_review` count = 0; tooltip explains why.
- Auto-passed rows collapsed by default but **expandable + editable** — escape hatch if a born-digital PDF was wrong.

### Field-level affordances

- BIN field: green ✓ if valid format, red ⚠ if not.
- Date field: date picker fallback if parsed value is suspect.
- Amount fields: BDT-formatted display + raw extracted text in muted color underneath.
- Bangla text rendered in a Bangla-friendly font (Noto Sans Bengali); copy-paste preserves Unicode.

### Column-mapping confirmation modal

Inline in the review screen for non-canonical XLSX:

```
┌─────────────────────────────────────────────────────┐
│ We found unfamiliar column names in this file:      │
│                                                     │
│   "বিল নং"        →  Invoice No        ✓            │
│   "সরবরাহকারী BIN" →  Supplier BIN      ✓           │
│   "তারিখ"          →  Invoice Date      ✓           │
│   "মোট"            →  Taxable Amount    ?           │
│   "VAT"            →  VAT Amount        ✓           │
│                                                     │
│  [Looks right — save mapping]  [Adjust]  [Cancel]   │
└─────────────────────────────────────────────────────┘
```

Once saved, header signature → mapping cached per tenant. Future uploads skip this step.

### Empty / error states

- Job in `failed`: shows failed files with engine errors; "Upload replacements" creates a new job for just those files.
- Single failed file in OK job: yellow banner in review screen with re-upload / skip affordances; doesn't block finalize.
- Zero rows extracted from any file: review screen shows "We couldn't pull any usable data — [Upload different files]".

## 10. Backward Compatibility

| Concern | Status |
|---|---|
| `POST /api/v1/reconciliations` (existing endpoint) | Unchanged |
| Existing `documents` table & `recon-files` bucket | Unchanged — ingestion writes its canonical XLSX as normal docs |
| Existing `reconciliation/parser.py` | Unchanged — handoff writes XLSX in this exact format |
| Existing reconciliation pipeline | Unchanged — receives a doc ID, doesn't know it came from ingestion |
| Existing reconciliation tests | Must continue to pass |
| `seed_demo.py` and demo XLSX fixtures | Unchanged — still go through original flow |
| Frontend's existing "upload XLSX" page | Stays as a secondary entry point; new "Ingest files" page becomes the default surface |

### Rollout

New ingestion routes ship behind env-var feature flag `INGESTION_ENABLED` (default `false` in production for first deploy). Verified end-to-end on a staging tenant before flipping to `true`. No code branches inside reconciliation.

## 11. Error Handling

Per-file isolation is the core principle: one bad file never breaks a 30-file job.

| Failure point | Handling |
|---|---|
| Upload-time MIME rejected | Synchronous 400 at `/jobs` POST; nothing persisted; inline per-file error in upload form |
| Storage upload failed | File marked `failed` with `storage_error`; job continues |
| pdfplumber crash on malformed PDF | File marked `failed`; logged with filename + error; warning in review UI |
| Gemini API timeout / rate limit / 5xx | Per-file retry with exponential backoff (3 attempts: 5s, 30s, 2min); after 3 failures → `failed` with structured error |
| Gemini returns malformed JSON despite structured-output | Treated as extraction failure for that file (should be vanishingly rare) |
| LLM column mapper returns nonsense (sanity check fails) | Falls back to surfacing the file in review with all rows flagged for manual correction |
| Worker process crash mid-extraction | On restart, worker re-claims rows where `status = extracting` and `updated_at < now() - 10min` via SQL lease pattern |
| Reconciliation handoff fails | Job stays in `confirmed`; "Retry reconciliation" button on job page re-runs handoff without re-extracting |
| Persistent handoff failure | Manual escalation — `failed` with `error_summary`; original files + extracted rows preserved for debugging |

### Rate limiting & cost guardrails

- Gemini calls go through per-tenant token-bucket (default 30 calls/min, configurable via env). Prevents runaway tenant from rate-limiting others.
- Per-job hard limit on file count (env-configurable, default 200) — uploads beyond this rejected at `/jobs` POST with "split into multiple jobs" message.
- Per-file size limit (default 25 MB) — reject at upload.
- Daily per-tenant Gemini-call cap (default 5,000) — when crossed, new jobs queue with a soft warning. Operator can raise cap per tenant.

### Observability

- All extraction events go through `structlog` with `job_id`, `file_id`, `tenant_id`, `engine`, `duration_ms`, `gemini_tokens` bound. Single log line per file extraction = trivially queryable for cost and latency analysis.
- Job state changes emit one log line each — full state-machine timeline reconstructable from logs.
- New `/health/ingestion` sub-endpoint reports: queued jobs count, jobs stuck in `extracting > 15min`, last-hour failure rate.

## 12. Testing Strategy

### Unit tests (pytest, alongside existing tests)

- `tests/ingestion/test_router.py` — MIME → engine routing for 15+ MIME variants including edge cases (mislabeled MIME, empty file, oversize)
- `tests/ingestion/test_engines/test_pandas_canonical.py` — XLSX with canonical headers; goldens identical to existing parser tests (regression-proof)
- `tests/ingestion/test_engines/test_pandas_mapper.py` — XLSX with renamed/Bangla/extra columns; mocks Gemini Flash with deterministic stubs
- `tests/ingestion/test_engines/test_pdfplumber_normalizer.py` — born-digital PDF samples; mocks Gemini Flash
- `tests/ingestion/test_engines/test_vision.py` — mocks Gemini Vision; asserts prompt assembly + result parsing
- `tests/ingestion/test_lifecycle.py` — state machine transitions including all "should not transition" cases
- `tests/ingestion/test_handoff.py` — confirmed rows → canonical XLSX bytes → fed back through existing parser → identical PurchaseRow output (round-trip test)
- `tests/ingestion/test_failure_modes.py` — per-file failure isolation, lease re-claim after worker crash, retry/backoff

### Golden fixture files (`backend/tests/fixtures/ingestion/`)

- `canonical_register.xlsx` — happy path
- `bangla_headers.xlsx` — column-mapper exercise
- `mushak_6.3_borndigital.pdf` — pdfplumber path
- `mushak_6.3_scan.pdf` — vision path (synthetic, generated for repeatability)
- `phone_photo_invoice.jpg` — vision path with rough quality
- `bundled_scan_5pages.pdf` — multi-invoice extraction
- `unreadable_garbage.pdf` — failure path
- `mixed_bag/` — 8-file bag covering all branches at once for the integration test

### Integration tests (`tests/ingestion/integration/`, gated on `INGESTION_TEST_SUPABASE_URL`)

- One full happy path: 5 mixed files → job → extract → review → finalize → reconciliation runs → outputs match expected XLSX export.
- One mixed-failure path: 5 files where 1 fails → job completes → review queue lets user finalize the surviving 4.

### LLM mocking strategy

- Real Gemini calls wrapped behind a thin `app/ingestion/llm.py` adapter with two methods (`map_columns`, `extract_rows`).
- Tests inject a stub adapter via dependency injection — no network in CI.
- Stub adapter is **deterministic**: given input X, returns canned output Y (recorded once via real call, replayed in tests). When prompts change, regenerate goldens via `python -m scripts.regenerate_llm_goldens`.
- Optional `pytest -m live` marker for tests that hit real Gemini — opt-in, not in default CI.

### Coverage target

85%+ on ingestion module business logic (matches CLAUDE.md project standard). LLM adapter itself need not be heavily tested — the stub IS the test.

## 13. Operational / Cost

- **Gemini Flash pricing** (~$0.075/M input tokens, $0.30/M output for 2.5 Flash; vision tokens ~250 per image): typical 50-file mixed-bag job costs ~$0.05-0.15. Per CA firm doing 20 jobs/month: ~$1-3/month. Trivial.
- **Storage:** ~5MB avg × 50 files × 30 firms × 12 months = ~90 GB/year. Supabase Storage ~$0.021/GB/month → ~$22/year/firm at scale. 90-day retention cleanup keeps this bounded; deferred post-v1.
- **Worker capacity:** with per-tenant token bucket (30/min) and bounded per-file concurrency (8 concurrent vision calls per worker), one Render instance handles ~5 concurrent active jobs. Monitor `extracting > 15min` count; horizontal-scale when needed.

## 14. Open Questions for Implementation Phase

These are intentionally NOT decided in this design and will surface during planning:

- Exact prompt templates for the column-mapper and the schema-extraction calls — to be iterated against the golden fixture files.
- Concrete library choice for HEIC: `pillow-heif` is the leading candidate but verify Render image build time.
- Concrete RLS policy SQL — pattern is identical to existing tables but each table needs explicit migration.
- Worker dispatch: in-process `asyncio.create_task` pool vs a small dedicated `app/ingestion/worker.py` long-poll loop. Both work; pick during planning based on FastAPI startup integration.
- Frontend state-management choice for the review screen (Zustand store vs TanStack Query mutations) — to be decided alongside other frontend conventions.

## 15. Out of Scope (Reaffirmation)

- Tesseract local OCR
- Per-supplier learned templates
- Direct NBR portal integration
- Storage cleanup / retention enforcement
- Mobile-first UX
- Multi-staff concurrent review of a single job (last-write-wins is acceptable for v1)

## 16. Success Criteria

- A CA firm can upload a mixed bag of 30 files (XLSX + PDFs + photos) and reach a successfully-ran reconciliation in one session, without ever opening Excel.
- Existing XLSX-only flow runs identically to today (existing tests pass unchanged).
- For any non-canonical XLSX the system has seen before from the same tenant, no LLM call is made (cached mapping is reused).
- Per-file failures never block the rest of a job from completing.
- Cost per job for a typical 50-file mixed bag stays under $0.20 in Gemini fees.
- Review queue UX is fast enough that a 50-file job with 5 needs-review rows takes a staff member under 2 minutes to finalize.
