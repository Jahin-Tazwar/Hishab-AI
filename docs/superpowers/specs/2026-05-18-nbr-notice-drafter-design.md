# NBR Notice Response Drafter — Design Spec

**Status:** Brainstormed, awaiting plan
**Branch:** `feat/nbr-notice-drafter`
**Worktree:** `.worktrees/notice-drafter`
**Author session:** 2026-05-18

## 1. Goal

Let a Bangladeshi CA upload an NBR notice PDF and receive a partner-ready Bangla reply letter — grounded in the firm's reconciled VAT data, citing only verified VAT Act / Rules / SRO clauses — in under 60 seconds. Reply is editable in-browser and exportable as `.docx` and PDF.

V1 supports exactly one notice category: **input VAT mismatch / ITC denial.** All other categories surface a polite "not yet supported" rather than draft a wrong-genre reply.

## 2. Why this, why now

HishabAI is pre-launch. The wedge that closes a first paid contract at first demo is not another reconciliation feature — it is something that *visibly removes hours of partner-level work in 90 seconds*. Notice drafting is that workflow:

- **Pain is partner-level and high-stakes.** Notices land on partners' desks; bookkeeping does not. Partners control buying decisions.
- **Pain is recurring.** A 50-client firm sees 3–15 notices a month across the portfolio. Per-notice fees are ৳5k–50k; saving even 2 hours per response is material.
- **HishabAI's existing reconciliation data is the unfair advantage.** No competing tool starts a draft with the actual reconciled position the notice is arguing about.
- **The notice drafter pulls users into the rest of the platform.** A CA who shows up with a notice for an un-reconciled period is routed through the existing combined-ingestion wizard, then back to the draft. One workflow recruits another.
- **A corpus moat compounds from day one.** Every notice + reply + (eventually) outcome we collect becomes proprietary training/eval data no foreign entrant can replicate.

## 3. Scope

### In scope (V1)

- Notice ingestion: PDF/image upload, Gemini Vision parsing into structured `ParsedNotice`
- One notice category: input VAT mismatch / ITC denial
- Auto-linking to existing reconciliations by `(client BIN, period)`
- Wedge fall-through: when no reconciliation exists, deep-link into the existing combined-ingestion wizard pre-filled with client + period, then re-drive the drafter when the wizard finishes
- Retrieval-grounded reply generation using a curated VAT Act 2012 / Rules 2016 / SRO seed corpus stored in pgvector
- Bangla letter body + English computation appendix
- Inline TipTap editor with autosave + revision history
- `.docx` export (python-docx + Noto Sans Bengali) and PDF export (LibreOffice headless render of the same .docx)
- Per-client `/notices` IA; per-client `Notices` tab inside the client view
- Cross-link from a reconciliation report showing linked notices
- Audit trail: every save creates an append-only `notice_draft_revisions` row

### Explicitly out of V1

- Other notice categories (output VAT understatement, BIN mismatch, audit invitation) — column exists in the model for forward-compat
- Firm-wide notices dashboard / partner queue
- Direct submission to NBR portal — CA prints/signs/files manually
- Per-firm letterhead templates — V1 ships a single neutral letterhead
- Multi-version drafts on the same notice (A/B reply strategies)
- Per-notice billing / metering — V1 unmetered, included in seat
- Outcome capture (won/settled/lost) — schema-ready but no UI yet
- Bangla legal-citation generation from scratch — citations are *only* what the retriever returns
- Email/Slack notifications when a draft is ready — uses the existing in-app toast pattern only

## 4. Architecture

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  Frontend (React + Vite + TanStack Query + shadcn/ui)            │
   │   /clients/:id/notices                       (list, upload)      │
   │   /clients/:id/notices/:noticeId             (parsed view)       │
   │   /clients/:id/notices/:noticeId/draft       (editor)            │
   └──────────────────────────────────────────────────────────────────┘
                                  │
   ┌──────────────────────────────▼───────────────────────────────────┐
   │  FastAPI router:  /api/v1/notices                                │
   │   POST   /                                  upload notice        │
   │   GET    /                                  list by client       │
   │   GET    /:notice_id                                              │
   │   POST   /:notice_id/relink                 manual client/period │
   │   POST   /:notice_id/draft                  (re)generate draft   │
   │   GET    /:notice_id/draft                                       │
   │   PUT    /:notice_id/draft                  autosave             │
   │   POST   /:notice_id/draft/finalize                              │
   │   GET    /:notice_id/draft/export?format=…  docx | pdf           │
   └──────────────────────────────────────────────────────────────────┘
                                  │
   ┌──────────────────────────────▼───────────────────────────────────┐
   │  backend/app/notices/                                            │
   │                                                                  │
   │   parser.py   →  GeminiVision + structured schema                │
   │                  produces ParsedNotice (notice_no, BIN, period,  │
   │                  alleged figures, notice_type classification)    │
   │                                                                  │
   │   linker.py   →  one of:                                         │
   │                    LinkedRecon(recon_id)                         │
   │                    NeedsIngestion(client_id, period)             │
   │                    NeedsManualLink(candidates=[])                │
   │                                                                  │
   │   retriever.py →  Gemini text-embedding-004 over                 │
   │                   citation_corpus_chunks, filtered by topic_tags │
   │                   returns top-K CitationChunk[] in BOTH bn+en    │
   │                                                                  │
   │   drafter.py  →  single Gemini call with retrieval-grounded      │
   │                  prompt + structured response schema             │
   │                  produces DraftReply (body_paragraphs,           │
   │                  computation_table_rows, cited_refs)             │
   │                                                                  │
   │   rendering.py →  body_html + appendix_json → .docx (python-docx)│
   │                   .docx → .pdf (libreoffice headless)            │
   │                                                                  │
   │   worker.py   →  process_notice(notice_id, tenant_id)            │
   │                  orchestrates phases, advances notices.status,   │
   │                  same lease/poll pattern as ingestion worker     │
   │                                                                  │
   │   service.py / router.py / schemas.py / persistence.py /         │
   │   exceptions.py — same layout as ingestion + reconciliation      │
   └──────────────────────────────────────────────────────────────────┘
                                  │
   ┌──────────────────────────────▼───────────────────────────────────┐
   │  Supabase (PostgreSQL with pgvector, RLS by tenant_id)           │
   │   notices                                                        │
   │   notice_drafts                                                  │
   │   notice_draft_revisions                                         │
   │   citation_corpus_chunks                  (global, read-only)    │
   │   notices-bucket                          (Storage)              │
   └──────────────────────────────────────────────────────────────────┘
```

### Invariants

- Each phase module exposes one pure-ish function with explicit types so it can be tested with a stub adapter (mirrors `LLMAdapter` / `StubLLMAdapter` from `app/ingestion/llm.py`).
- **Citations are never invented.** The drafter prompt receives a finite list of retrieved chunks; the post-processor rejects any `[CIT-X]` reference not in that list and replaces it with `[citation needed — review]`.
- The notice path does NOT fork the ingestion code. When a notice needs ingestion, the frontend deep-links into the existing combined-ingestion wizard with `?from_notice=<notice_id>`; the wizard's existing completion handler additionally writes `notices.linked_reconciliation_id` and re-enqueues the notice worker.
- pgvector inside the same Supabase Postgres — no separate vector DB. Adequate at corpus sizes < 10k chunks.
- Read paths from the frontend hit Supabase directly (RLS); write paths go through FastAPI for business logic + audit trails — same convention as `useReconciliations`.

## 5. Data model

All tenant-scoped tables have a `tenant_id uuid not null` column + an RLS policy `tenant_id = current_setting('app.current_tenant_id')::uuid`.

### `notices`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `tenant_id` | uuid not null | RLS |
| `client_id` | uuid not null fk → `clients` | |
| `created_by` | uuid not null fk → `users` | uploader |
| `storage_path` | text not null | `{tenant_id}/{client_id}/{notice_id}/{filename}` in `notices` bucket |
| `original_filename` | text not null | |
| `mime_type` | text not null | |
| `byte_size` | int not null | |
| `status` | text not null check in `('pending','parsing','parsed','awaiting_data','ready_to_draft','drafting','drafted','finalized','failed')` | |
| `parse_error` | text null | set only when status='failed' |
| `notice_no` | text null | extracted |
| `notice_date` | date null | |
| `notice_type` | text null check in `('input_vat_mismatch',NULL)` initially | future-proof for other categories |
| `taxpayer_bin` | text null | normalized digits-only |
| `taxpayer_tin` | text null | optional |
| `period_start` | date null | |
| `period_end` | date null | |
| `alleged_itc_claimed_bdt` | numeric(14,2) null | what NBR asserts the taxpayer claimed |
| `alleged_itc_allowed_bdt` | numeric(14,2) null | what NBR claims is allowable |
| `alleged_shortfall_bdt` | numeric(14,2) null | demand quantum |
| `linked_reconciliation_id` | uuid null fk → `vat_reconciliations` | set by linker |
| `linked_ingestion_job_id` | uuid null fk → `ingestion_jobs` | set when user is mid-ingestion-from-notice |
| `created_at` | timestamptz not null default now() | |
| `updated_at` | timestamptz not null default now() | |

Indexes:
- `(tenant_id, client_id, notice_date desc)` — client-portfolio listing
- `(tenant_id, status)` — worker queue + ops dashboards
- `(tenant_id, taxpayer_bin)` — linker BIN lookup

### `notice_drafts`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `tenant_id` | uuid not null | |
| `notice_id` | uuid not null unique fk → `notices` | one head per notice |
| `language` | text not null default `'bn'` | V1 always `'bn'` |
| `body_html` | text not null | sanitized TipTap output |
| `appendix_json` | jsonb not null | `{rows: [{label, value_bdt, note}], totals: {...}}` |
| `citations` | jsonb not null | `[{corpus_chunk_id, source_ref, snippet, paragraph_idx}]` |
| `model_version` | text not null | e.g. `"gemini-2.5-flash | prompt v1"` |
| `status` | text not null check in `('draft','under_review','finalized')` default `'draft'` | |
| `finalized_at` | timestamptz null | |
| `finalized_by` | uuid null fk → `users` | |
| `created_at` / `updated_at` | timestamptz | |

### `notice_draft_revisions`

Append-only edit history.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `tenant_id` | uuid not null | |
| `draft_id` | uuid not null fk → `notice_drafts` | |
| `revision_no` | int not null | monotonic per draft |
| `body_html` | text not null | snapshot |
| `appendix_json` | jsonb not null | snapshot |
| `edited_by` | uuid not null fk → `users` | |
| `edit_source` | text not null check in `('llm_generated','user_edit','regenerated')` | |
| `created_at` | timestamptz not null default now() | |
| `unique (draft_id, revision_no)` | | |

### `citation_corpus_chunks` (global, read-only seed; not tenant-scoped)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `source` | text not null check in `('vat_act_2012','vat_rules_2016','sro','general_order')` | |
| `source_ref` | text not null | e.g. `'Section 46'`, `'Rule 23'`, `'SRO 134/2026'` |
| `subsection` | text null | e.g. `'(2)(a)'` |
| `language` | text not null check in `('bn','en')` | both translations stored as separate rows |
| `title` | text not null | human-readable section title |
| `body` | text not null | clause text |
| `topic_tags` | text[] not null | e.g. `['itc','mismatch','documentary_evidence']` |
| `embedding` | vector(768) not null | Gemini `text-embedding-004` of `title || ' ' || body` |
| `created_at` | timestamptz not null default now() | |

Indexes:
- `ivfflat (embedding vector_cosine_ops) with (lists = 100)` — ANN search
- `gin (topic_tags)` — pre-filter by topic before ANN
- `(source, source_ref, subsection, language)` unique — dedupe

RLS:
- `notices`, `notice_drafts`, `notice_draft_revisions`: standard tenant policy
- `citation_corpus_chunks`: `SELECT` open to authenticated users; no INSERT/UPDATE/DELETE from API (seeded by migration only)

Storage bucket:
- `notices` bucket, separate from `ingestion-files`, same tenant-scoped path convention

## 6. Pipeline phases

All phases run inside `worker.process_notice(notice_id, tenant_id)`. The worker re-claims notices via the same lease/poll pattern as `app/ingestion/worker.py`.

### Phase 1 — Parser (`notices/parser.py`)

**Input:** raw bytes (PDF or image) + ParseContext (tenant_id, client_id_hint optional)
**Output:** `ParsedNotice` Pydantic model:

```python
class ParsedNotice(BaseModel):
    notice_no: str | None
    notice_date: date | None
    notice_type: Literal["input_vat_mismatch", "unsupported"]
    taxpayer_bin: str | None       # normalized digits-only
    taxpayer_tin: str | None
    period_start: date | None
    period_end: date | None
    alleged_itc_claimed_bdt: Decimal | None
    alleged_itc_allowed_bdt: Decimal | None
    alleged_shortfall_bdt: Decimal | None
    classification_confidence: float  # 0.0–1.0
```

**How:**
- Reuses `VisionEngine._normalize_image_to_png` (PDF render or image downscale, capped at 2048px / 7MB; the path we just hardened on the parent branch).
- New `GeminiLLMAdapter.extract_notice` method calling Gemini 2.5 Flash with a notice-specific structured response schema. Same `responseSchema` discipline we use for invoice extraction.
- Bangla + English notices both handled; the prompt explicitly instructs the model to extract irrespective of language.
- If `notice_type != "input_vat_mismatch"` OR `classification_confidence < 0.7`, the worker sets `notices.status = 'failed'` with `parse_error = "Notice category not supported in V1"` — no draft attempted.

**Stub:** `StubNoticeParser` mirrors `StubLLMAdapter` for unit tests.

### Phase 2 — Linker (`notices/linker.py`)

**Input:** `ParsedNotice` + `tenant_id`
**Output:** one of:

```python
class LinkedRecon(BaseModel):
    reconciliation_id: UUID
    client_id: UUID

class NeedsIngestion(BaseModel):
    client_id: UUID
    period_start: date
    period_end: date

class NeedsManualLink(BaseModel):
    candidate_clients: list[UUID]    # may be empty
```

**How:**
1. Lookup client by `taxpayer_bin` under `tenant_id`. Zero matches → `NeedsManualLink([])`. >1 match → `NeedsManualLink(candidates)`.
2. One client matched, period extracted → look up `vat_reconciliations` by `(client_id, period_start, period_end)`. Found → `LinkedRecon`.
3. One client matched but no reconciliation → `NeedsIngestion`. Worker sets `notices.status = 'awaiting_data'` and stops; the frontend renders the "upload your purchase register" prompt.

### Phase 3 — Retriever (`notices/retriever.py`)

**Input:** `ParsedNotice` + reconciliation summary dict
**Output:** `list[CitationChunk]` (length 4–8)

```python
class CitationChunk(BaseModel):
    id: UUID
    source: str
    source_ref: str               # e.g. "Section 46"
    subsection: str | None
    language: Literal["bn", "en"]
    title: str
    body: str                     # clause text (truncated to ~600 chars)
```

**How:**
1. Build query: concatenate notice allegation summary + reconciliation summary into one string.
2. Embed via Gemini `text-embedding-004`.
3. Postgres query: pre-filter by `topic_tags && ARRAY['itc','mismatch']`, then ANN by cosine distance on `embedding`. Top 16 candidate chunks.
4. Group by `(source, source_ref, subsection)` and keep both `bn` and `en` variants per group.
5. Cap at 8 distinct citation groups.

### Phase 4 — Drafter (`notices/drafter.py`)

**Input:** `ParsedNotice` + reconciliation summary + retrieved citations
**Output:** `DraftReply` Pydantic model:

```python
class DraftParagraph(BaseModel):
    text: str                          # Bangla, may contain [CIT-N] markers
    citation_tags: list[str]           # parsed from [CIT-N] markers

class DraftAppendixRow(BaseModel):
    label: str                         # English
    value_bdt: Decimal | None
    note: str | None

class DraftReply(BaseModel):
    body_paragraphs: list[DraftParagraph]
    computation_table_rows: list[DraftAppendixRow]
    cited_refs: list[str]              # ["CIT-1","CIT-2",...]
```

**Prompt skeleton:**
- **System:** "You draft formal Bangla replies to NBR VAT notices. Follow Bangladeshi NBR formal-letter conventions: প্রসঙ্গ heading, প্রিয় মহোদয় opening, numbered factual paragraphs, formal closing. Cite ONLY from the provided citations list, referencing them as `[CIT-N]`. Never invent section numbers or rules. If you cannot cite a chunk, omit the citation."
- **Notice block:** parsed fields verbatim
- **Reconciliation block:** Safe/At-risk ITC totals, supplier-by-supplier breakdown of disputed rows (truncated to ≤20 rows), key match-status counts
- **Citations block:** numbered list `[CIT-1] … [CIT-N]` with `source_ref`, language tag, and the Bangla `body` text for each
- **Output schema:** the `DraftReply` schema above, enforced via `responseSchema` (same discipline as the invoice extractor)

**Post-processing:**
1. Validate every `[CIT-N]` marker in `body_paragraphs[].text` resolves to a chunk we actually retrieved; unresolved → replace with `[citation needed — review]`.
2. Convert paragraphs to HTML: wrap each in `<p>`, replace `[CIT-N]` markers with `<sup class="citation" data-ref="…">[N]</sup>`.
3. Sanitize HTML through a strict allowlist (`<p>`, `<strong>`, `<em>`, `<sup>`, `<br>` — no scripts, no inline styles).
4. Persist `notice_drafts` row + first `notice_draft_revisions` (revision_no=1, edit_source='llm_generated').

### Phase 5 — Rendering (`notices/rendering.py`)

Two pure functions:
- `render_docx(body_html, appendix_json, notice_meta) -> bytes` using `python-docx`. Embeds Noto Sans Bengali font. Letterhead is a neutral firm placeholder (logo slot, firm-name slot — populated from `tenant` row when available).
- `render_pdf(docx_bytes) -> bytes` via `subprocess.run(["soffice", "--headless", "--convert-to", "pdf", ...])`. Deterministic given input. LibreOffice is a new build-time dep — see §11.

## 7. UX flows

### Flow A — Happy path (reconciliation already exists)

1. CA at `/clients/:id/notices` → clicks Upload notice → dropzone
2. POST `/api/v1/notices` with the file → returns `notice_id`, status=`pending`
3. Frontend redirects to `/clients/:id/notices/:notice_id`; polls until status leaves `parsing`
4. Parser populates fields, linker finds reconciliation, status becomes `ready_to_draft`
5. CA clicks "Draft reply" → POST `/api/v1/notices/:id/draft`
6. Worker runs retriever + drafter; status `drafting` → `drafted`
7. Frontend renders editor at `/clients/:id/notices/:notice_id/draft` with body, appendix, citations panel
8. CA edits (autosave creates `notice_draft_revisions` rows debounced to 2s)
9. CA clicks Export .docx → server-side render → file downloads
10. CA clicks Mark finalized → status=`finalized`, draft locked

### Flow B — Wedge mechanic (no reconciliation yet)

1–4. As above, but linker returns `NeedsIngestion`; status=`awaiting_data`
5. UI shows "Upload your purchase register for Apr 2026 to draft this reply"
6. Clicking the CTA opens the existing combined-ingestion wizard with `?from_notice=<id>&client_id=<id>&period_start=...&period_end=...`
7. Wizard runs unchanged until reconciliation completes
8. Wizard's completion handler additionally calls `POST /api/v1/notices/:id/relink` with the new `reconciliation_id`
9. Worker re-runs from Phase 2; status → `ready_to_draft`
10. Frontend toast: "Reconciliation done — your reply draft is ready" with deep link back to the notice

### Flow C — Parser couldn't link

Linker returns `NeedsManualLink` → UI shows a client picker + period override → CA confirms → POST `/api/v1/notices/:id/relink` with manual values → re-runs from Phase 2

### Cross-cutting UI behaviors

- Long phases render an animated "indeterminate" progress bar with the current phase name underneath
- Every parser/drafter failure surfaces the actual `parse_error` text + a "Try again" button that re-enqueues the worker
- Edit autosave: debounced 2s; one revision per save, not per keystroke
- "Regenerate" creates a fresh revision with `edit_source='regenerated'`; previous revisions stay accessible in a side panel (read-only)
- Finalized drafts are locked; "Reopen for editing" requires the user to type a short reason captured in the next revision row

### Navigation / IA

- New top-level `Notices` in the left nav
- Inside a client view, a new `Notices` tab next to `Reconciliations`
- Reconciliation report header shows a `Notices linked (N) →` chip when any notice references it

## 8. API surface

All under `/api/v1/notices`. Tenant resolved from auth context.

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `POST` | `/` | Upload notice file (multipart). Returns `{notice_id}`. Enqueues worker. | required |
| `GET` | `/?client_id=…` | List notices for a client (RLS-scoped). Newest first. | required |
| `GET` | `/{notice_id}` | Notice detail with parsed fields + linkage. | required |
| `POST` | `/{notice_id}/relink` | Manually set `client_id` + period + (optional) `reconciliation_id`. Re-runs linker. | required |
| `POST` | `/{notice_id}/draft` | (Re)generate draft. 409 if `status not in ('ready_to_draft','drafted')`. | required |
| `GET` | `/{notice_id}/draft` | Latest draft. | required |
| `PUT` | `/{notice_id}/draft` | Autosave (`body_html`, `appendix_json`). Creates a new revision. | required |
| `GET` | `/{notice_id}/draft/revisions` | List revision metadata (no bodies) for the side panel. | required |
| `POST` | `/{notice_id}/draft/finalize` | Lock the draft. | required |
| `POST` | `/{notice_id}/draft/reopen` | Body: `{reason: str}`. Unlocks; logged in next revision. | required |
| `GET` | `/{notice_id}/draft/export?format=docx\|pdf` | Streams the rendered file. | required |

Standard JSON error envelope shared with the rest of the API. RLS at the DB; defense-in-depth tenant filters on every query.

## 9. Citation corpus seeding

V1 ships a curated seed of ~30–60 chunks covering the legal ground a typical input-VAT-mismatch reply needs. Source list:

- **VAT and SD Act 2012:** Sections 46 (input tax credit conditions), 49 (documentary evidence), 50 (denial grounds), 73 (assessment), 87 (recovery) — and any other sections cited by NBR demand notices in practice
- **VAT and SD Rules 2016:** Rules 23–26 (ITC procedures), Rule 40 (mismatch resolution)
- **SROs and general orders:** the 3–5 most-cited in real demand notices over the last 24 months

Bootstrap process (one-off, baked into the migration that creates `citation_corpus_chunks`):
1. Markdown files under `backend/app/notices/corpus/` with each clause in both Bangla and English (`section_46_bn.md`, `section_46_en.md`, …)
2. A `scripts/seed_citation_corpus.py` script reads the markdown, computes embeddings via Gemini `text-embedding-004`, and writes rows
3. Idempotent: re-running upserts on `(source, source_ref, subsection, language)`

Production migration runs the seeder once via the same admin-script pattern as `seed_demo`. Embedding cost is trivial (~60 chunks × 768d).

The Bangla translations are sourced from official NBR-published Bangla texts; English translations from BPC / NBR official translations where available, otherwise human-translated and reviewed (a separate `corpus_review.md` checklist tracks provenance per chunk).

## 10. Error handling & worker semantics

- **Lease:** worker takes a soft lease via `notices.updated_at` (mirrors ingestion worker); 10-minute timeout; expired leases get re-claimed.
- **Idempotency:** re-running a phase on the same notice is safe; `process_notice` reads the current status and resumes from the right phase.
- **Failure surfacing:** every failure writes `notices.parse_error` and sets `status='failed'` (or `awaiting_data` for the soft case). Frontend always renders the error text + retry button.
- **No silent retries.** Worker tries each phase exactly once per run; user-initiated retries are explicit.
- **Rate limiting:** reuses the existing `TokenBucketRegistry` from `app/ingestion/rate_limit.py` for Gemini calls (per-tenant per-min and per-day).
- **Cost discipline:** parser ≈ 1 Gemini call; retriever embed ≈ 1 small call; drafter ≈ 1 Gemini call. Worst-case 3 LLM calls + 1 embed per notice. Bounded.

## 11. Dependencies

New runtime deps (Python):
- `pgvector` Python bindings — already in the SDK; just need pgvector extension on Postgres
- `python-docx` — Word generation
- `lxml` — for HTML sanitization
- `bleach` — HTML allowlist sanitizer

New runtime deps (frontend):
- `@tiptap/react` + `@tiptap/starter-kit` — rich-text editor
- `@tiptap/extension-superscript` — for citation markers

New system deps:
- LibreOffice (`soffice`) for PDF rendering. Available on Render's standard image; documented as `apt-get install libreoffice-core libreoffice-writer fonts-noto fonts-noto-bengali`
- `pgvector` Postgres extension — enabled via Supabase project extensions toggle + migration `CREATE EXTENSION IF NOT EXISTS vector;`

No new infra services. No new vector DB. No new queue.

## 12. Testing strategy

| Layer | Approach |
|---|---|
| Parser | Stub adapter + fixture notice PDFs (5 representative samples — built from synthetic NBR template). Tests assert parsed fields match expected. |
| Linker | Pure logic; parametrized tests over all branches (`LinkedRecon`, `NeedsIngestion`, `NeedsManualLink`). |
| Retriever | Live Postgres + small fixture corpus (5–10 chunks) seeded per-test; tests assert top-K ordering for known query/corpus pairs. Live Gemini embedding gated behind `-m live` marker, like the existing `test_llm_gemini.py`. |
| Drafter | Stub LLM that returns canned `DraftReply` payloads; tests assert post-processing (citation validation, HTML sanitization, [CIT-N] → `<sup>` conversion). Plus a live `-m live` smoke test against real Gemini. |
| Rendering | Snapshot tests on .docx output structure (paragraph count, citation count, appendix table presence). PDF render gated on LibreOffice availability. |
| API | FastAPI TestClient + supabase test project; same gating pattern as `tests/ingestion/test_api.py`. |
| Worker | End-to-end test that walks a notice through all four phases against stubs and asserts final `notices.status='drafted'`. |
| Frontend | Vitest + Testing Library for editor / linker UI / autosave debouncing. Playwright smoke for the full upload → draft → export flow. |

Coverage target: ≥85% on the four pipeline modules (parser, linker, retriever, drafter) — matches the discipline you set for reconciliation.

## 13. Open questions to decide during plan execution

These don't change the architecture but need an answer before they're touched:

1. **TipTap collaboration mode?** No — single-editor only in V1; the autosave + revision model handles "two people editing" by last-write-wins with full history.
2. **PDF rendering on Windows dev boxes?** LibreOffice is a heavy dep. Document the `soffice` requirement; tests that need it gate on `shutil.which('soffice')` and skip with a clear message otherwise.
3. **Letterhead per firm?** V1 ships a neutral placeholder; a `tenants.letterhead_*` column set is a V1.1 follow-up. Spec'd as out of scope above.
4. **Notice deadline tracking?** Not in V1 (per UX section). Schema doesn't have a `respond_by` column yet; add when we ship the partner queue.

## 14. Non-goals worth restating

- This is not a general legal-research tool. It only drafts replies to a single category of NBR notice and refuses other categories.
- This is not a NBR-portal-submission integration. The CA prints/signs/files.
- This is not multi-language UX. Frontend strings remain English; only the drafted *letter content* is Bangla.
- This is not a permissions / signing-workflow product. "Finalized" means locked-for-edit, not "approved by partner." A real approval workflow is a V2 feature.
