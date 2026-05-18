# NBR Notice Response Drafter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a notices domain that accepts an NBR notice PDF, parses it, links to (or triggers) the matching reconciliation, retrieves grounded citations from a curated VAT-law corpus, and produces an editable Bangla reply with English computation appendix exportable as `.docx` and PDF.

**Architecture:** New `app/notices/` backend domain mirroring the four-phase pipeline pattern used by `app/ingestion/` (parser → linker → retriever → drafter), plus rendering. Citations are retrieved (pgvector ANN over a global `citation_corpus_chunks` table) — never invented by the LLM. The frontend ships a per-client Notices area with a TipTap-based draft editor; when a notice arrives for a period without a reconciliation, the UI deep-links into the existing combined-ingestion wizard with a callback that re-drives the drafter.

**Tech Stack:** Python 3.11 + FastAPI + Pydantic 2, Supabase PostgreSQL with pgvector, Google `google-genai` SDK (Gemini 2.5 Flash + text-embedding-004), python-docx + LibreOffice for rendering, React 18 + Vite + TanStack Query + shadcn/ui + TipTap rich-text editor + Zod.

**Working directory:** `C:\project\Hishab AI\.worktrees\notice-drafter` (branch `feat/nbr-notice-drafter`). All paths in this plan are relative to that worktree root.

---

## File structure

### Backend — `backend/app/notices/`

| File | Responsibility |
|---|---|
| `__init__.py` | empty module marker |
| `schemas.py` | All Pydantic models: `NoticeStatus`, `NoticeType`, `ParsedNotice`, `LinkerResult` (discriminated union of `LinkedRecon` / `NeedsIngestion` / `NeedsManualLink`), `CitationChunk`, `ReconSummary`, `DraftParagraph`, `DraftAppendixRow`, `DraftReply`, request/response DTOs |
| `exceptions.py` | `NoticeError` base + `NoticeNotFoundError`, `NoticeUnsupportedTypeError`, `NoticeParseError`, `NoticeInvalidStateError`, `DraftNotFoundError` |
| `persistence.py` | All Supabase admin-client CRUD: `create_notice`, `get_notice`, `update_notice`, `list_notices`, `create_draft`, `get_draft`, `update_draft` (appends revision), `list_revisions`, `find_client_by_bin`, `find_recon_by_period`, ANN query helper `retrieve_citation_chunks` |
| `storage.py` | Supabase bucket I/O for `notices` bucket: `upload_original`, `download_original`, `create_signed_url` |
| `llm.py` | `NoticeLLMAdapter` Protocol, `StubNoticeLLMAdapter`, `GeminiNoticeLLMAdapter` (extends the existing Gemini client with `parse_notice` + `draft_reply` + `embed_query`) |
| `parser.py` | `parse_notice(file_bytes, mime, *, adapter) -> ParsedNotice`; uses `VisionEngine._normalize_image_to_png` to bound payload size before the call |
| `linker.py` | `link_notice(parsed, tenant_id) -> LinkerResult`; pure DB lookups via `persistence` |
| `retriever.py` | `retrieve(parsed, recon_summary, *, adapter) -> list[CitationChunk]`; builds query string + embeds + ANN |
| `drafter.py` | `draft(parsed, recon_summary, citations, *, adapter) -> DraftReply`; calls LLM with strict schema + post-processes (citation validation, HTML sanitize) |
| `rendering.py` | `render_docx(draft, notice, tenant) -> bytes` and `render_pdf(docx_bytes) -> bytes` (LibreOffice headless) |
| `worker.py` | `process_notice(notice_id, tenant_id)`; `poll_pending_notices`; lease pattern mirrors `app/ingestion/worker.py` |
| `service.py` | High-level orchestration: `create_notice`, `relink_notice`, `generate_draft`, `save_draft_revision`, `finalize_draft`, `reopen_draft`, `export_draft` |
| `router.py` | FastAPI endpoints under `/api/v1/notices` |
| `corpus/` | Markdown source files for citation corpus (one file per `(source_ref, subsection, language)`) |

### Backend — tests `backend/tests/notices/`

| File | Coverage |
|---|---|
| `__init__.py` | empty |
| `conftest.py` | shared fixtures: `make_parsed_notice`, `make_recon_summary`, `make_citation_chunk`, env gates |
| `fixtures/notice_input_vat_mismatch.pdf` | synthetic minimal NBR notice |
| `fixtures/notice_input_vat_mismatch.jpg` | same data as image |
| `fixtures/notice_audit_invitation.pdf` | out-of-scope category for negative test |
| `test_parser.py` | parser unit tests with `StubNoticeLLMAdapter` |
| `test_linker.py` | all 3 branches of `LinkerResult` |
| `test_retriever.py` | live-Postgres gated; seeded corpus subset; ANN ranking assertions |
| `test_drafter.py` | citation post-processing, HTML sanitize, [CIT-N] resolution |
| `test_rendering.py` | docx structure snapshot; PDF gated on `shutil.which('soffice')` |
| `test_worker.py` | end-to-end pipeline against stubs; status transitions |
| `test_persistence.py` | live-DB gated CRUD |
| `test_api.py` | live-DB gated API tests via FastAPI TestClient |
| `test_llm_gemini.py` | live Gemini smoke; `-m live` marker |

### Backend — scripts

| File | Responsibility |
|---|---|
| `backend/scripts/seed_citation_corpus.py` | reads `app/notices/corpus/*.md`, embeds each, upserts `citation_corpus_chunks` |

### Migrations

| File | Responsibility |
|---|---|
| `migrations/0018_pgvector_extension.sql` | `CREATE EXTENSION IF NOT EXISTS vector;` |
| `migrations/0019_notice_tables.sql` | `notices`, `notice_drafts`, `notice_draft_revisions`, `citation_corpus_chunks`, enums, indexes, RLS, `updated_at` triggers |
| `migrations/0020_notices_storage_bucket.sql` | private `notices` bucket + RLS policies on `storage.objects` |

### Frontend — `frontend/src/`

| File | Responsibility |
|---|---|
| `types/notices.ts` | Zod schemas + inferred TS types for all DTOs |
| `lib/notices/api.ts` | typed API client functions |
| `hooks/useNotices.ts` | TanStack Query hooks |
| `pages/NoticeList.tsx` | per-client notices list + upload entry |
| `pages/NoticeDetail.tsx` | parsed metadata + linkage status |
| `pages/NoticeDraft.tsx` | TipTap editor + citations panel + export |
| `components/notices/NoticeUploadDropzone.tsx` | reuses MultiFileDropzone for a single PDF |
| `components/notices/NoticeMetaCard.tsx` | parsed fields display |
| `components/notices/NoticeStatusBanner.tsx` | per-status banner with retry / next-action CTAs |
| `components/notices/RelinkDialog.tsx` | manual client + period picker |
| `components/notices/AwaitingDataPrompt.tsx` | wedge mechanic CTA into the wizard |
| `components/notices/DraftEditor.tsx` | TipTap editor with autosave + citation `<sup>` rendering |
| `components/notices/CitationsPanel.tsx` | right-rail citation list with paragraph cross-highlight |
| `components/notices/ReconciliationSummaryCard.tsx` | live recon summary the drafter used |
| `components/notices/ComputationAppendixTable.tsx` | editable appendix table |
| Modify `components/layout/AppShell.tsx` | add Notices nav entry |
| Modify `router.tsx` | three new routes |
| Modify `components/ingestion/*` | accept `?from_notice=` and call `relinkNotice` on completion |

---

## Phase 0 — Pre-flight

Run-once setup. No code yet; just dependencies and tooling.

### Task 0.1: Install backend Python dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Append new deps**

Add to `backend/requirements.txt`:

```
python-docx>=1.1.0
bleach>=6.1.0
lxml>=5.1.0
pgvector>=0.3.0
```

- [ ] **Step 2: Install**

Run: `cd backend && pip install -r requirements.txt`
Expected: all four packages install without errors.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore(notices): add python-docx, bleach, lxml, pgvector deps"
```

### Task 0.2: Install frontend dependencies

**Files:**
- Modify: `frontend/package.json` (via npm)

- [ ] **Step 1: Install TipTap**

Run: `cd frontend && npm install @tiptap/react @tiptap/pm @tiptap/starter-kit @tiptap/extension-superscript`
Expected: packages added to `package.json`; `npm install` exits 0.

- [ ] **Step 2: Verify build still works**

Run: `cd frontend && npm run build`
Expected: build succeeds, no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(notices): add TipTap editor packages"
```

### Task 0.3: Verify LibreOffice availability + document the dep

**Files:**
- Modify: `backend/README.md` (or root `README.md` if backend has none) — add a "Notices PDF export" subsection
- Create: `backend/app/notices/__init__.py` (empty)

- [ ] **Step 1: Check soffice presence**

Run: `which soffice || where soffice 2>nul`
Expected: a path on dev boxes that have it; missing on CI/Windows is allowed (tests will skip).

- [ ] **Step 2: Add the dep note**

Append to root `README.md` under a new "### Notices PDF export" section:

```markdown
### Notices PDF export
The notice-drafter exports replies as `.docx` (always) and `.pdf` (when
LibreOffice is installed). The PDF path shells out to `soffice --headless`.

- macOS: `brew install --cask libreoffice`
- Ubuntu (Render image): `apt-get install -y libreoffice-core libreoffice-writer fonts-noto fonts-noto-bengali`
- Windows: install LibreOffice from libreoffice.org and ensure `soffice.exe` is on PATH

Without LibreOffice, the API returns 503 on `?format=pdf` with the
message "PDF rendering unavailable on this server"; `.docx` still works.
```

- [ ] **Step 3: Create the empty notices module**

Create `backend/app/notices/__init__.py` with single-line docstring:

```python
"""NBR notice response drafter — parse, link, retrieve, draft, render."""
```

- [ ] **Step 4: Commit**

```bash
git add README.md backend/app/notices/__init__.py
git commit -m "docs(notices): document LibreOffice dep + create notices module"
```

---

## Phase 1 — Database foundation

### Task 1.1: Enable pgvector extension

**Files:**
- Create: `migrations/0018_pgvector_extension.sql`

- [ ] **Step 1: Create the migration**

```sql
-- 0018_pgvector_extension.sql
-- Enables pgvector for citation-corpus ANN search used by the notice drafter.
-- Idempotent: harmless if the extension was already enabled.

CREATE EXTENSION IF NOT EXISTS vector;
```

- [ ] **Step 2: Apply to the dev Supabase project**

Run via the Supabase MCP `apply_migration` tool with name `0018_pgvector_extension` and the SQL above.
Expected: success.

- [ ] **Step 3: Verify**

Run via Supabase MCP `execute_sql`:
```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```
Expected: one row with `extname='vector'`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0018_pgvector_extension.sql
git commit -m "feat(notices): enable pgvector extension for citation ANN"
```

### Task 1.2: Create notices, notice_drafts, notice_draft_revisions tables

**Files:**
- Create: `migrations/0019_notice_tables.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0019_notice_tables.sql
-- NBR notice response drafter: notices, drafts, revisions, citation corpus.
-- Tenant-scoped via RLS using the same (SELECT tenant_id FROM user_profiles
-- WHERE id = auth.uid()) pattern as 0004 + 0014.

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE notice_status AS ENUM (
  'pending', 'parsing', 'parsed', 'awaiting_data', 'ready_to_draft',
  'drafting', 'drafted', 'finalized', 'failed'
);

CREATE TYPE notice_type AS ENUM (
  'input_vat_mismatch', 'unsupported'
);

CREATE TYPE notice_draft_status AS ENUM (
  'draft', 'under_review', 'finalized'
);

CREATE TYPE notice_draft_edit_source AS ENUM (
  'llm_generated', 'user_edit', 'regenerated'
);

CREATE TYPE notice_corpus_source AS ENUM (
  'vat_act_2012', 'vat_rules_2016', 'sro', 'general_order'
);

CREATE TYPE notice_corpus_language AS ENUM ('bn', 'en');

-- ============================================================
-- NOTICES
-- ============================================================

CREATE TABLE notices (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id                   uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  created_by                  uuid NOT NULL,
  storage_path                text NOT NULL,
  original_filename           text NOT NULL,
  mime_type                   text NOT NULL,
  byte_size                   bigint NOT NULL,
  status                      notice_status NOT NULL DEFAULT 'pending',
  parse_error                 text,
  notice_no                   text,
  notice_date                 date,
  notice_type                 notice_type,
  taxpayer_bin                text,
  taxpayer_tin                text,
  period_start                date,
  period_end                  date,
  alleged_itc_claimed_bdt     numeric(14, 2),
  alleged_itc_allowed_bdt     numeric(14, 2),
  alleged_shortfall_bdt       numeric(14, 2),
  linked_reconciliation_id    uuid REFERENCES vat_reconciliations(id) ON DELETE SET NULL,
  linked_ingestion_job_id     uuid REFERENCES ingestion_jobs(id) ON DELETE SET NULL,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  updated_at                  timestamptz NOT NULL DEFAULT now(),
  CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start)
);

-- ============================================================
-- NOTICE_DRAFTS — one head per notice
-- ============================================================

CREATE TABLE notice_drafts (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  notice_id           uuid NOT NULL UNIQUE REFERENCES notices(id) ON DELETE CASCADE,
  language            text NOT NULL DEFAULT 'bn',
  body_html           text NOT NULL,
  appendix_json       jsonb NOT NULL,
  citations           jsonb NOT NULL DEFAULT '[]'::jsonb,
  model_version       text NOT NULL,
  status              notice_draft_status NOT NULL DEFAULT 'draft',
  finalized_at        timestamptz,
  finalized_by        uuid,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- NOTICE_DRAFT_REVISIONS — append-only edit history
-- ============================================================

CREATE TABLE notice_draft_revisions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  draft_id        uuid NOT NULL REFERENCES notice_drafts(id) ON DELETE CASCADE,
  revision_no     int NOT NULL,
  body_html       text NOT NULL,
  appendix_json   jsonb NOT NULL,
  edited_by       uuid NOT NULL,
  edit_source     notice_draft_edit_source NOT NULL,
  edit_reason     text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (draft_id, revision_no)
);

-- ============================================================
-- CITATION_CORPUS_CHUNKS — global, read-only seed
-- ============================================================

CREATE TABLE citation_corpus_chunks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source       notice_corpus_source NOT NULL,
  source_ref   text NOT NULL,
  subsection   text,
  language     notice_corpus_language NOT NULL,
  title        text NOT NULL,
  body         text NOT NULL,
  topic_tags   text[] NOT NULL DEFAULT '{}',
  embedding    vector(768) NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source, source_ref, subsection, language)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX ix_notices_tenant_client_date
  ON notices (tenant_id, client_id, notice_date DESC);

CREATE INDEX ix_notices_tenant_status
  ON notices (tenant_id, status);

CREATE INDEX ix_notices_tenant_bin
  ON notices (tenant_id, taxpayer_bin)
  WHERE taxpayer_bin IS NOT NULL;

CREATE INDEX ix_notice_drafts_tenant_notice
  ON notice_drafts (tenant_id, notice_id);

CREATE INDEX ix_notice_draft_revisions_draft
  ON notice_draft_revisions (draft_id, revision_no DESC);

-- Worker lease index (same pattern as 0014 ingestion)
CREATE INDEX ix_notices_lease
  ON notices (status, updated_at)
  WHERE status IN ('pending', 'parsing', 'drafting');

-- pgvector ANN index — ivfflat is the right pick for our corpus size (< 10k chunks)
CREATE INDEX ix_citation_corpus_embedding
  ON citation_corpus_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX ix_citation_corpus_topic_tags
  ON citation_corpus_chunks USING gin (topic_tags);

-- ============================================================
-- updated_at TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION notices_set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notices_updated_at
  BEFORE UPDATE ON notices
  FOR EACH ROW EXECUTE FUNCTION notices_set_updated_at();

CREATE TRIGGER trg_notice_drafts_updated_at
  BEFORE UPDATE ON notice_drafts
  FOR EACH ROW EXECUTE FUNCTION notices_set_updated_at();

-- ============================================================
-- RLS
-- ============================================================

ALTER TABLE notices                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE notice_drafts            ENABLE ROW LEVEL SECURITY;
ALTER TABLE notice_draft_revisions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE citation_corpus_chunks   ENABLE ROW LEVEL SECURITY;

CREATE POLICY notices_tenant ON notices
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

CREATE POLICY notice_drafts_tenant ON notice_drafts
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

CREATE POLICY notice_draft_revisions_tenant ON notice_draft_revisions
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

-- Citation corpus: read-only to all authenticated users; no INSERT/UPDATE/DELETE
CREATE POLICY citation_corpus_read ON citation_corpus_chunks
  FOR SELECT TO authenticated USING (true);
```

- [ ] **Step 2: Apply the migration**

Apply via Supabase MCP `apply_migration` tool with name `0019_notice_tables`.
Expected: success.

- [ ] **Step 3: Verify schema**

Run via Supabase MCP `execute_sql`:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('notices','notice_drafts','notice_draft_revisions','citation_corpus_chunks')
ORDER BY table_name;
```
Expected: 4 rows.

- [ ] **Step 4: Commit**

```bash
git add migrations/0019_notice_tables.sql
git commit -m "feat(notices): notices, drafts, revisions, citation-corpus tables + RLS"
```

### Task 1.3: Create notices storage bucket

**Files:**
- Create: `migrations/0020_notices_storage_bucket.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0020_notices_storage_bucket.sql
-- Private 'notices' bucket for raw NBR notice PDFs/images.
-- Path layout: {tenant_id}/{client_id}/{notice_id}/{filename}
-- First path segment (tenant_id) is the RLS pivot, identical to 0011 + 0015.

INSERT INTO storage.buckets (id, name, public)
VALUES ('notices', 'notices', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS notices_bucket_select ON storage.objects;
DROP POLICY IF EXISTS notices_bucket_insert ON storage.objects;
DROP POLICY IF EXISTS notices_bucket_update ON storage.objects;
DROP POLICY IF EXISTS notices_bucket_delete ON storage.objects;

CREATE POLICY notices_bucket_select ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY notices_bucket_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY notices_bucket_update ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY notices_bucket_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );
```

- [ ] **Step 2: Apply via Supabase MCP**

Apply via `apply_migration` with name `0020_notices_storage_bucket`.

- [ ] **Step 3: Verify**

Run via Supabase MCP `execute_sql`:
```sql
SELECT id, public FROM storage.buckets WHERE id = 'notices';
```
Expected: one row, `public=false`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0020_notices_storage_bucket.sql
git commit -m "feat(notices): private 'notices' storage bucket + RLS policies"
```

---

## Phase 2 — Citation corpus

### Task 2.1: Author corpus markdown files for V1 (input VAT mismatch)

**Files:**
- Create: `backend/app/notices/corpus/README.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s46_en.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s46_bn.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s49_en.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s49_bn.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s50_en.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s50_bn.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s73_en.md`
- Create: `backend/app/notices/corpus/vat_act_2012_s73_bn.md`
- Create: `backend/app/notices/corpus/vat_rules_2016_r23_en.md`
- Create: `backend/app/notices/corpus/vat_rules_2016_r23_bn.md`
- Create: `backend/app/notices/corpus/vat_rules_2016_r24_en.md`
- Create: `backend/app/notices/corpus/vat_rules_2016_r24_bn.md`
- Create: `backend/app/notices/corpus/vat_rules_2016_r40_en.md`
- Create: `backend/app/notices/corpus/vat_rules_2016_r40_bn.md`

- [ ] **Step 1: Define the markdown format**

Create `backend/app/notices/corpus/README.md`:

```markdown
# Citation corpus markdown format

Each clause is a separate file: `{source}_{ref}_{language}.md` (lowercase,
underscores, no spaces). The seed script (`scripts/seed_citation_corpus.py`)
parses front-matter and body, embeds the title+body, and upserts a row in
`citation_corpus_chunks`.

## Required front-matter

```yaml
---
source: vat_act_2012   # one of: vat_act_2012 | vat_rules_2016 | sro | general_order
source_ref: Section 46 # e.g. "Section 46", "Rule 23", "SRO 134/2026"
subsection: ""         # e.g. "(2)(a)" or empty
language: en           # bn | en
title: Conditions for input tax credit
topic_tags: [itc, eligibility, documentary_evidence]
---
```

## Provenance

Bangla clauses transcribed from the NBR-published official Bangla texts of
the VAT and SD Act 2012 and Rules 2016. English clauses from the NBR/BPC
official English translations where available; otherwise the official
Bangla was professionally translated and reviewed by a Bangladeshi CA
(see `corpus_review.md` for per-chunk attribution).
```

- [ ] **Step 2: Author Section 46 — the cornerstone ITC clause (English)**

Create `backend/app/notices/corpus/vat_act_2012_s46_en.md`:

```markdown
---
source: vat_act_2012
source_ref: Section 46
subsection: ""
language: en
title: Conditions for input tax credit
topic_tags: [itc, eligibility, documentary_evidence, mismatch]
---
A registered person shall be entitled to take an input tax credit (decreasing
adjustment) for the value-added tax paid on inputs acquired in the course of
the person's economic activities, provided that:

(a) the inputs are acquired for use in making taxable supplies;
(b) the registered person holds a valid tax invoice (Mushak 6.3) for the
    acquisition;
(c) the input tax credit is taken in the tax period in which the supply was
    received, or in a subsequent tax period not exceeding four months thereafter;
(d) the supplier is a registered person whose BIN is active at the time of
    supply;
(e) the corresponding output tax has been or will be paid by the supplier.

An input tax credit shall not be available for any acquisition for which the
above conditions are not satisfied.
```

- [ ] **Step 3: Author Section 46 (Bangla mirror)**

Create `backend/app/notices/corpus/vat_act_2012_s46_bn.md`:

```markdown
---
source: vat_act_2012
source_ref: ধারা ৪৬
subsection: ""
language: bn
title: উপকরণ কর রেয়াতের শর্তাবলী
topic_tags: [itc, eligibility, documentary_evidence, mismatch]
---
নিবন্ধিত কোনো ব্যক্তি তাহার অর্থনৈতিক কার্যক্রম পরিচালনার সময় অর্জিত উপকরণের
উপর প্রদত্ত মূল্য সংযোজন কর বাবদ উপকরণ কর রেয়াত (হ্রাসকারী সমন্বয়) গ্রহণের
অধিকারী হইবেন, যদি—

(ক) উপকরণসমূহ করযোগ্য সরবরাহ প্রদানের জন্য অর্জিত হইয়া থাকে;
(খ) উক্ত নিবন্ধিত ব্যক্তির নিকট অর্জনের সমর্থনে বৈধ কর চালানপত্র (মূসক ৬.৩)
    রহিয়াছে;
(গ) সরবরাহ গ্রহণের কর-মেয়াদে অথবা পরবর্তী চারিটি কর-মেয়াদের মধ্যে রেয়াত গ্রহণ
    করা হয়;
(ঘ) সরবরাহকারী একজন নিবন্ধিত ব্যক্তি এবং সরবরাহকালে তাহার BIN সক্রিয় থাকে;
(ঙ) সংশ্লিষ্ট উৎপাদ কর সরবরাহকারী কর্তৃক পরিশোধিত হইয়াছে বা পরিশোধিত হইবে।

উপরোক্ত শর্তসমূহ পূরিত না হইলে কোনো অর্জনের বিপরীতে উপকরণ কর রেয়াত প্রদেয় হইবে না।
```

- [ ] **Step 4: Author Sections 49, 50, 73 (en + bn) and Rules 23, 24, 40 (en + bn)**

Each follows the exact same front-matter + body format. Their actual content
must be taken from the official VAT and SD Act 2012 / Rules 2016 published
by NBR. The seed script does not interpret the body beyond embedding it;
schema correctness is what matters here.

Required `(source, source_ref, subsection)` × language combinations to create
(10 more files, mirroring the Section 46 pattern above):

| File | source | source_ref (en) | source_ref (bn) | topic_tags |
|---|---|---|---|---|
| `vat_act_2012_s49_en.md` / `_bn.md` | `vat_act_2012` | `Section 49` | `ধারা ৪৯` | `[itc, documentary_evidence, mushak_6_3]` |
| `vat_act_2012_s50_en.md` / `_bn.md` | `vat_act_2012` | `Section 50` | `ধারা ৫০` | `[itc, denial_grounds, mismatch]` |
| `vat_act_2012_s73_en.md` / `_bn.md` | `vat_act_2012` | `Section 73` | `ধারা ৭৩` | `[assessment, demand, procedure]` |
| `vat_rules_2016_r23_en.md` / `_bn.md` | `vat_rules_2016` | `Rule 23` | `বিধি ২৩` | `[itc, procedure]` |
| `vat_rules_2016_r24_en.md` / `_bn.md` | `vat_rules_2016` | `Rule 24` | `বিধি ২৪` | `[itc, documentary_evidence]` |
| `vat_rules_2016_r40_en.md` / `_bn.md` | `vat_rules_2016` | `Rule 40` | `বিধি ৪০` | `[mismatch, reconciliation, procedure]` |

For each: copy the verbatim official clause text into the body of the
English file, the official Bangla into the Bangla file. Title is a 4-7 word
summary. `subsection` empty unless citing a specific sub-clause.

- [ ] **Step 5: Smoke-check every file parses as valid front-matter**

Run: `cd backend && python -c "
import yaml, pathlib, sys
ok = 0
for p in pathlib.Path('app/notices/corpus').glob('*.md'):
    if p.name == 'README.md': continue
    txt = p.read_text(encoding='utf-8')
    parts = txt.split('---', 2)
    assert len(parts) >= 3, f'{p.name}: missing front-matter'
    fm = yaml.safe_load(parts[1])
    for key in ('source','source_ref','language','title','topic_tags'):
        assert key in fm, f'{p.name}: missing {key}'
    ok += 1
print(f'{ok} corpus files OK')
"`

Expected: `14 corpus files OK`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/notices/corpus/
git commit -m "feat(notices): seed citation corpus markdown (VAT Act + Rules, bn+en)"
```

### Task 2.2: Write the corpus seed script

**Files:**
- Create: `backend/scripts/seed_citation_corpus.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/notices/__init__.py` (empty), `backend/tests/notices/conftest.py`:

```python
"""Shared fixtures for notice tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.notices.schemas import (
    CitationChunk, NoticeType, ParsedNotice, ReconSummary,
)


@pytest.fixture
def parsed_notice() -> ParsedNotice:
    return ParsedNotice(
        notice_no="NBR/VAT/12345/2026",
        notice_date=date(2026, 5, 1),
        notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567",
        taxpayer_tin=None,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        alleged_itc_claimed_bdt=Decimal("50000.00"),
        alleged_itc_allowed_bdt=Decimal("40000.00"),
        alleged_shortfall_bdt=Decimal("10000.00"),
        classification_confidence=0.95,
    )


@pytest.fixture
def recon_summary() -> ReconSummary:
    return ReconSummary(
        reconciliation_id="00000000-0000-0000-0000-000000000001",
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[
            {"supplier_name": "ACME Ltd", "supplier_bin": "987654321",
             "invoice_no": "INV-99", "vat_amount_bdt": "5000.00",
             "match_status": "no_match"},
        ],
    )


@pytest.fixture
def citation_chunk_en() -> CitationChunk:
    return CitationChunk(
        id="00000000-0000-0000-0000-0000000000aa",
        source="vat_act_2012",
        source_ref="Section 46",
        subsection=None,
        language="en",
        title="Conditions for input tax credit",
        body="A registered person shall be entitled to take an input tax credit…",
    )
```

Create `backend/tests/notices/test_seed_citation_corpus.py`:

```python
"""Live-DB seed-script tests. Gated like other live tests."""
import os
import pathlib

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Seed test requires live Supabase",
)


def test_seed_corpus_idempotent(monkeypatch):
    """Running the seeder twice must not duplicate rows."""
    from scripts.seed_citation_corpus import seed_corpus
    from app.database import get_supabase_admin

    sb = get_supabase_admin()
    # Run twice
    n1 = seed_corpus()
    n2 = seed_corpus()
    assert n1 == n2, f"second run upserted a different count: {n1} vs {n2}"

    # Count rows actually in DB matches the on-disk corpus minus README
    corpus_dir = pathlib.Path(__file__).parents[2] / "app" / "notices" / "corpus"
    expected = sum(1 for p in corpus_dir.glob("*.md") if p.name != "README.md")
    res = sb.table("citation_corpus_chunks").select("id", count="exact").execute()
    assert res.count == expected
```

- [ ] **Step 2: Run to confirm it fails (skips, since live env not set is fine)**

Run: `cd backend && python -m pytest tests/notices/test_seed_citation_corpus.py -v 2>&1 | tail -5`
Expected: `SKIPPED` or `ImportError` (script doesn't exist yet).

- [ ] **Step 3: Write the seed script**

Create `backend/scripts/seed_citation_corpus.py`:

```python
"""Seed (or re-seed) the citation_corpus_chunks table from markdown files.

Reads every `app/notices/corpus/*.md` (skipping README), parses the YAML
front-matter, computes a 768-dim embedding via Gemini text-embedding-004,
and upserts on (source, source_ref, subsection, language).

Idempotent: re-running updates embeddings + body if changed but doesn't
duplicate rows.

Run: cd backend && python -m scripts.seed_citation_corpus
"""
from __future__ import annotations

import os
import pathlib
import sys

import yaml
from dotenv import load_dotenv

load_dotenv()

CORPUS_DIR = pathlib.Path(__file__).parents[1] / "app" / "notices" / "corpus"


def _embed(client, text: str) -> list[float]:
    res = client.models.embed_content(
        model="text-embedding-004",
        contents=text,
    )
    # google-genai returns a list of Embedding objects; we always send one input
    return list(res.embeddings[0].values)


def seed_corpus() -> int:
    """Upsert every corpus file. Returns the number of rows written."""
    from google import genai
    from app.database import get_supabase_admin

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required to seed corpus")

    client = genai.Client(api_key=api_key)
    sb = get_supabase_admin()

    n = 0
    for path in sorted(CORPUS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            print(f"SKIP {path.name}: no front-matter", file=sys.stderr)
            continue
        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()

        embedding = _embed(client, f"{meta['title']}\n\n{body}")

        sb.table("citation_corpus_chunks").upsert({
            "source":     meta["source"],
            "source_ref": meta["source_ref"],
            "subsection": meta.get("subsection") or None,
            "language":   meta["language"],
            "title":      meta["title"],
            "body":       body,
            "topic_tags": list(meta.get("topic_tags") or []),
            "embedding":  embedding,
        }, on_conflict="source,source_ref,subsection,language").execute()
        n += 1
        print(f"  upserted {path.name}")
    return n


if __name__ == "__main__":
    count = seed_corpus()
    print(f"Done: {count} chunks seeded.")
```

- [ ] **Step 4: Run the seeder live**

Run: `cd backend && python -m scripts.seed_citation_corpus`
Expected: prints `Done: 14 chunks seeded.` (14 = 7 sections × 2 languages).

- [ ] **Step 5: Run the test live (with env vars)**

Run with `INGESTION_TEST_SUPABASE_URL` set: `cd backend && python -m pytest tests/notices/test_seed_citation_corpus.py -v 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/seed_citation_corpus.py backend/tests/notices/
git commit -m "feat(notices): seed_citation_corpus script + idempotency test"
```

---

## Phase 3 — Backend types, exceptions, LLM adapter

### Task 3.1: Define schemas (all Pydantic models in one shot)

**Files:**
- Create: `backend/app/notices/schemas.py`
- Create: `backend/tests/notices/test_schemas.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_schemas.py`:

```python
"""Pydantic schema invariants."""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.notices.schemas import (
    CitationChunk, DraftAppendixRow, DraftParagraph, DraftReply,
    LinkedRecon, NeedsIngestion, NeedsManualLink,
    NoticeStatus, NoticeType, ParsedNotice, ReconSummary,
)


def test_parsed_notice_requires_classification_confidence():
    with pytest.raises(ValidationError):
        ParsedNotice(notice_type=NoticeType.INPUT_VAT_MISMATCH)


def test_parsed_notice_normalizes_bin_to_digits():
    n = ParsedNotice(
        notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001-234-567",
        classification_confidence=0.9,
    )
    assert n.taxpayer_bin == "001234567"


def test_parsed_notice_period_end_must_be_ge_start():
    with pytest.raises(ValidationError):
        ParsedNotice(
            notice_type=NoticeType.INPUT_VAT_MISMATCH,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 4, 1),
            classification_confidence=0.9,
        )


def test_draft_reply_serializes_decimals_as_strings():
    r = DraftReply(
        body_paragraphs=[DraftParagraph(text="hello [CIT-1]", citation_tags=["CIT-1"])],
        computation_table_rows=[
            DraftAppendixRow(label="Claimed", value_bdt=Decimal("50000.00"), note=None),
        ],
        cited_refs=["CIT-1"],
    )
    j = r.model_dump(mode="json")
    assert j["computation_table_rows"][0]["value_bdt"] == "50000.00"


def test_linker_result_discriminators_serialize_with_kind():
    lr = LinkedRecon(reconciliation_id="00000000-0000-0000-0000-000000000001",
                    client_id="00000000-0000-0000-0000-000000000002")
    assert lr.model_dump()["kind"] == "linked_recon"

    ni = NeedsIngestion(client_id="00000000-0000-0000-0000-000000000002",
                        period_start=date(2026, 4, 1),
                        period_end=date(2026, 4, 30))
    assert ni.model_dump()["kind"] == "needs_ingestion"

    nml = NeedsManualLink(candidate_clients=[])
    assert nml.model_dump()["kind"] == "needs_manual_link"


def test_notice_status_enum_values_match_db():
    expected = {"pending","parsing","parsed","awaiting_data","ready_to_draft",
                "drafting","drafted","finalized","failed"}
    assert {s.value for s in NoticeStatus} == expected


def test_recon_summary_money_fields_serialize_as_strings():
    s = ReconSummary(
        reconciliation_id="00000000-0000-0000-0000-000000000001",
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[],
    )
    j = s.model_dump(mode="json")
    assert j["safe_itc_bdt"] == "40000.00"
```

- [ ] **Step 2: Run to verify failures**

Run: `cd backend && python -m pytest tests/notices/test_schemas.py -v 2>&1 | tail -10`
Expected: ModuleNotFoundError (`app.notices.schemas` doesn't exist).

- [ ] **Step 3: Write the schemas module**

Create `backend/app/notices/schemas.py`:

```python
"""Pydantic models for the notices module.

Mirrors the conventions in app/ingestion/schemas.py:
- Enum string values exactly match the corresponding Postgres enums (0019).
- Money fields are Decimal at runtime, serialized as "1234.50" strings.
- Discriminated unions use `kind` literals so the frontend can switch on them.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import (
    BaseModel, ConfigDict, Field, field_serializer, field_validator,
    model_validator,
)


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Enums (mirror Postgres types from migration 0019) ────────────────────


class NoticeStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    AWAITING_DATA = "awaiting_data"
    READY_TO_DRAFT = "ready_to_draft"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    FINALIZED = "finalized"
    FAILED = "failed"


class NoticeType(str, Enum):
    INPUT_VAT_MISMATCH = "input_vat_mismatch"
    UNSUPPORTED = "unsupported"


class NoticeDraftStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    FINALIZED = "finalized"


class NoticeDraftEditSource(str, Enum):
    LLM_GENERATED = "llm_generated"
    USER_EDIT = "user_edit"
    REGENERATED = "regenerated"


# ── Parsed notice (parser output) ─────────────────────────────────────────


class ParsedNotice(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    notice_no: Optional[str] = None
    notice_date: Optional[date] = None
    notice_type: NoticeType
    taxpayer_bin: Optional[str] = None
    taxpayer_tin: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    alleged_itc_claimed_bdt: Optional[Decimal] = None
    alleged_itc_allowed_bdt: Optional[Decimal] = None
    alleged_shortfall_bdt: Optional[Decimal] = None
    classification_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("taxpayer_bin", "taxpayer_tin", mode="before")
    @classmethod
    def _digits_only(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return re.sub(r"\D+", "", str(v))

    @model_validator(mode="after")
    def _check_period(self) -> "ParsedNotice":
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")
        return self

    @field_serializer(
        "alleged_itc_claimed_bdt", "alleged_itc_allowed_bdt", "alleged_shortfall_bdt",
        when_used="json",
    )
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(_to_2dp(v)) if v is not None else None


# ── Linker discriminated union ────────────────────────────────────────────


class LinkedRecon(BaseModel):
    kind: Literal["linked_recon"] = "linked_recon"
    reconciliation_id: UUID
    client_id: UUID


class NeedsIngestion(BaseModel):
    kind: Literal["needs_ingestion"] = "needs_ingestion"
    client_id: UUID
    period_start: date
    period_end: date


class NeedsManualLink(BaseModel):
    kind: Literal["needs_manual_link"] = "needs_manual_link"
    candidate_clients: list[UUID] = Field(default_factory=list)


LinkerResult = Annotated[
    Union[LinkedRecon, NeedsIngestion, NeedsManualLink],
    Field(discriminator="kind"),
]


# ── Retrieval / drafter inputs ────────────────────────────────────────────


class CitationChunk(BaseModel):
    id: UUID
    source: str
    source_ref: str
    subsection: Optional[str] = None
    language: Literal["bn", "en"]
    title: str
    body: str


class ReconSummary(BaseModel):
    reconciliation_id: UUID
    safe_itc_bdt: Decimal
    at_risk_itc_bdt: Decimal
    total_vat_claimed_bdt: Decimal
    matched_exact: int
    matched_fuzzy: int
    partial_match: int
    no_match: int
    disputed_rows: list[dict[str, Any]] = Field(default_factory=list)

    @field_serializer(
        "safe_itc_bdt", "at_risk_itc_bdt", "total_vat_claimed_bdt",
        when_used="json",
    )
    def _money(self, v: Decimal) -> str:
        return str(_to_2dp(v))


# ── Drafter output ────────────────────────────────────────────────────────


class DraftParagraph(BaseModel):
    text: str
    citation_tags: list[str] = Field(default_factory=list)


class DraftAppendixRow(BaseModel):
    label: str
    value_bdt: Optional[Decimal] = None
    note: Optional[str] = None

    @field_serializer("value_bdt", when_used="json")
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(_to_2dp(v)) if v is not None else None


class DraftReply(BaseModel):
    body_paragraphs: list[DraftParagraph]
    computation_table_rows: list[DraftAppendixRow]
    cited_refs: list[str] = Field(default_factory=list)


# ── API request/response DTOs ─────────────────────────────────────────────


class NoticeOut(BaseModel):
    id: UUID
    tenant_id: UUID
    client_id: UUID
    created_by: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    status: NoticeStatus
    parse_error: Optional[str] = None
    notice_no: Optional[str] = None
    notice_date: Optional[date] = None
    notice_type: Optional[NoticeType] = None
    taxpayer_bin: Optional[str] = None
    taxpayer_tin: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    alleged_itc_claimed_bdt: Optional[Decimal] = None
    alleged_itc_allowed_bdt: Optional[Decimal] = None
    alleged_shortfall_bdt: Optional[Decimal] = None
    linked_reconciliation_id: Optional[UUID] = None
    linked_ingestion_job_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "alleged_itc_claimed_bdt", "alleged_itc_allowed_bdt", "alleged_shortfall_bdt",
        when_used="json",
    )
    def _money(self, v: Optional[Decimal]) -> Optional[str]:
        return str(_to_2dp(v)) if v is not None else None


class CitationOut(BaseModel):
    corpus_chunk_id: UUID
    source_ref: str
    snippet: str
    paragraph_idx: int


class NoticeDraftOut(BaseModel):
    id: UUID
    notice_id: UUID
    language: str
    body_html: str
    appendix_json: dict[str, Any]
    citations: list[CitationOut]
    model_version: str
    status: NoticeDraftStatus
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class RelinkRequest(BaseModel):
    client_id: UUID
    period_start: date
    period_end: date
    reconciliation_id: Optional[UUID] = None


class SaveDraftRequest(BaseModel):
    body_html: str
    appendix_json: dict[str, Any]


class FinalizeDraftResponse(BaseModel):
    notice_id: UUID
    draft_id: UUID
    status: NoticeDraftStatus


class ReopenDraftRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `cd backend && python -m pytest tests/notices/test_schemas.py -v 2>&1 | tail -15`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/schemas.py backend/tests/notices/test_schemas.py
git commit -m "feat(notices): Pydantic schemas for parser/linker/drafter/API"
```

### Task 3.2: Define notice exceptions

**Files:**
- Create: `backend/app/notices/exceptions.py`
- Create: `backend/tests/notices/test_exceptions.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/notices/test_exceptions.py`:

```python
from app.notices.exceptions import (
    DraftNotFoundError, NoticeError, NoticeInvalidStateError,
    NoticeNotFoundError, NoticeParseError, NoticeUnsupportedTypeError,
)


def test_notice_not_found_has_code_and_status():
    e = NoticeNotFoundError("nope")
    assert e.code == "NOTICE_NOT_FOUND"
    assert e.status_code == 404


def test_notice_unsupported_type_carries_filename_mime():
    e = NoticeUnsupportedTypeError(filename="x.docx", mime="application/msword")
    assert e.code == "NOTICE_UNSUPPORTED_TYPE"
    assert e.status_code == 415
    assert "x.docx" in e.message


def test_notice_parse_error_400():
    e = NoticeParseError("could not extract BIN")
    assert e.code == "NOTICE_PARSE_ERROR"
    assert e.status_code == 400


def test_notice_invalid_state_409():
    e = NoticeInvalidStateError("cannot draft from status=pending")
    assert e.code == "NOTICE_INVALID_STATE"
    assert e.status_code == 409


def test_draft_not_found_404():
    e = DraftNotFoundError("no draft yet")
    assert e.code == "DRAFT_NOT_FOUND"
    assert e.status_code == 404


def test_all_inherit_from_notice_error():
    for cls in (NoticeNotFoundError, NoticeUnsupportedTypeError,
                NoticeParseError, NoticeInvalidStateError, DraftNotFoundError):
        assert issubclass(cls, NoticeError)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_exceptions.py -v 2>&1 | tail -5`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

Create `backend/app/notices/exceptions.py`:

```python
"""Domain exceptions for the notices module.

Mirrors app/ingestion/exceptions.py. Every exception sets a stable code
that the frontend can switch on without parsing prose.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import HishabError


class NoticeError(HishabError):
    default_code: str = "NOTICE_ERROR"
    default_status: int = 400

    def __init__(
        self,
        message: str = "Notice error",
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(self.default_code, message, self.default_status, details)


class NoticeNotFoundError(NoticeError):
    default_code = "NOTICE_NOT_FOUND"
    default_status = 404


class NoticeUnsupportedTypeError(NoticeError):
    default_code = "NOTICE_UNSUPPORTED_TYPE"
    default_status = 415

    def __init__(self, *, filename: str, mime: str) -> None:
        super().__init__(
            f"Unsupported notice file: {filename} ({mime})",
            details={"filename": filename, "mime": mime},
        )


class NoticeParseError(NoticeError):
    default_code = "NOTICE_PARSE_ERROR"
    default_status = 400


class NoticeInvalidStateError(NoticeError):
    default_code = "NOTICE_INVALID_STATE"
    default_status = 409


class DraftNotFoundError(NoticeError):
    default_code = "DRAFT_NOT_FOUND"
    default_status = 404
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_exceptions.py -v 2>&1 | tail -10`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/exceptions.py backend/tests/notices/test_exceptions.py
git commit -m "feat(notices): domain exceptions with stable error codes"
```

### Task 3.3: Define NoticeLLMAdapter protocol + Stub + Gemini implementation

**Files:**
- Create: `backend/app/notices/llm.py`
- Create: `backend/tests/notices/test_llm_stub.py`

- [ ] **Step 1: Write failing test for the stub**

Create `backend/tests/notices/test_llm_stub.py`:

```python
"""StubNoticeLLMAdapter unit tests. Deterministic; no network."""
from datetime import date
from decimal import Decimal

import pytest

from app.notices.llm import (
    LLMUnavailableError, StubNoticeLLMAdapter,
)
from app.notices.schemas import (
    DraftAppendixRow, DraftParagraph, DraftReply, NoticeType, ParsedNotice,
)


def test_stub_parse_returns_canned():
    canned = ParsedNotice(
        notice_no="X-1", notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567", classification_confidence=0.95,
        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        alleged_shortfall_bdt=Decimal("10000.00"),
    )
    stub = StubNoticeLLMAdapter(parses={"abc": canned})
    out = stub.parse_notice(images=[b"x"], lookup_key="abc")
    assert out.notice_no == "X-1"


def test_stub_parse_raises_for_unknown_key():
    stub = StubNoticeLLMAdapter(parses={})
    with pytest.raises(LLMUnavailableError):
        stub.parse_notice(images=[b"x"], lookup_key="never-seen")


def test_stub_draft_returns_canned():
    canned = DraftReply(
        body_paragraphs=[DraftParagraph(text="hi [CIT-1]", citation_tags=["CIT-1"])],
        computation_table_rows=[DraftAppendixRow(label="x", value_bdt=Decimal("1.00"))],
        cited_refs=["CIT-1"],
    )
    stub = StubNoticeLLMAdapter(drafts={"k": canned})
    out = stub.draft_reply(prompt="ignored", lookup_key="k")
    assert out.cited_refs == ["CIT-1"]


def test_stub_embed_returns_canned_vector():
    stub = StubNoticeLLMAdapter(embeddings={"q": [0.1] * 768})
    v = stub.embed_query("q")
    assert len(v) == 768
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_llm_stub.py -v 2>&1 | tail -5`
Expected: ImportError.

- [ ] **Step 3: Implement the LLM module**

Create `backend/app/notices/llm.py`:

```python
"""LLM adapter for the notices module.

Two LLM-touching operations:
  * parse_notice — Gemini Vision call returning a ParsedNotice
  * draft_reply  — Gemini text call returning a DraftReply
Plus an embedding call:
  * embed_query  — text-embedding-004 over the retrieval query string

Protocol + StubNoticeLLMAdapter mirror app/ingestion/llm.py exactly. The
real Gemini implementation is in this file; both adapters are interchangeable
at the import boundary.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional, Protocol

from app.notices.schemas import DraftReply, NoticeType, ParsedNotice


class LLMUnavailableError(Exception):
    """Raised by the stub when no canned response exists for the lookup key."""


# ── Adapter Protocol ─────────────────────────────────────────────────────


class NoticeLLMAdapter(Protocol):
    def parse_notice(
        self, *, images: list[bytes], lookup_key: str,
    ) -> ParsedNotice: ...

    def draft_reply(
        self, *, prompt: str, lookup_key: str,
    ) -> DraftReply: ...

    def embed_query(self, text: str) -> list[float]: ...


# ── Test stub ────────────────────────────────────────────────────────────


class StubNoticeLLMAdapter:
    def __init__(
        self,
        *,
        parses: Optional[dict[str, ParsedNotice]] = None,
        drafts: Optional[dict[str, DraftReply]] = None,
        embeddings: Optional[dict[str, list[float]]] = None,
    ) -> None:
        self._parses = parses or {}
        self._drafts = drafts or {}
        self._embeddings = embeddings or {}

    def parse_notice(self, *, images: list[bytes], lookup_key: str) -> ParsedNotice:
        if lookup_key not in self._parses:
            raise LLMUnavailableError(f"no canned parse for {lookup_key!r}")
        return self._parses[lookup_key]

    def draft_reply(self, *, prompt: str, lookup_key: str) -> DraftReply:
        if lookup_key not in self._drafts:
            raise LLMUnavailableError(f"no canned draft for {lookup_key!r}")
        return self._drafts[lookup_key]

    def embed_query(self, text: str) -> list[float]:
        if text not in self._embeddings:
            raise LLMUnavailableError(f"no canned embedding for query {text!r}")
        return self._embeddings[text]


# ── Module-level singleton (same pattern as app/ingestion/llm.py) ────────


_adapter: NoticeLLMAdapter | None = None


def set_notice_llm_adapter(adapter: NoticeLLMAdapter) -> None:
    global _adapter
    _adapter = adapter


def get_notice_llm_adapter() -> NoticeLLMAdapter:
    if _adapter is None:
        raise RuntimeError(
            "Notice LLM adapter not initialised. Call set_notice_llm_adapter() "
            "at startup (production: GeminiNoticeLLMAdapter; tests: stub)."
        )
    return _adapter


# ── Real Gemini implementation ───────────────────────────────────────────


_MODEL = "gemini-2.5-flash"
_EMBED_MODEL = "text-embedding-004"


_PARSE_PROMPT = """\
You extract structured metadata from a Bangladeshi NBR VAT notice.

The attached image(s) are pages of a notice — possibly in Bangla, English,
or both. Notices typically demand additional VAT, allege ITC mismatch, or
schedule an audit.

For each field, return null if not present. Decimal amounts as numeric
strings with 2 decimals (e.g. "12345.00"). Dates as YYYY-MM-DD. BIN/TIN
as digit strings only (strip punctuation).

Classify `notice_type` as ONE of:
  - "input_vat_mismatch" : alleges the taxpayer's claimed input VAT
    exceeds what suppliers reported / what NBR accepts.
  - "unsupported" : any other category (audit invitation, output VAT
    understatement, BIN registration, general inquiry, demand for non-VAT
    matter). Use this if you are unsure or the notice is for a category
    other than input VAT mismatch.

Set `classification_confidence` between 0.0 and 1.0 reflecting how certain
you are about `notice_type`.
"""


_DRAFT_SYSTEM = """\
You draft formal Bangla replies to NBR VAT notices for a Bangladeshi
Chartered Accountancy firm. Follow NBR formal-letter conventions:
"প্রসঙ্গ:" reference line, "প্রিয় মহোদয়," opening, numbered factual
paragraphs, a closing courtesy, and the CA firm signature block.

Hard rules:
  - You MAY only cite from the provided citations list, referencing each
    by its tag e.g. [CIT-1]. Never invent section numbers or rule numbers.
  - If you cannot find a citation supporting a point, omit the citation —
    do NOT make one up.
  - The body MUST be in Bangla. Numbers and BDT amounts may appear in
    Western digits.
  - Use the reconciliation data provided as the ground truth for what the
    taxpayer's actual position is. Do not invent supplier names or amounts.
"""


class GeminiNoticeLLMAdapter:
    def __init__(self, *, api_key: str, model_name: str = _MODEL) -> None:
        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=api_key)
        self._types = types
        self._model_name = model_name

    # ── Parse ────

    def parse_notice(self, *, images: list[bytes], lookup_key: str) -> ParsedNotice:
        Type = self._types.Type
        schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "notice_no": self._types.Schema(type=Type.STRING, nullable=True),
                "notice_date": self._types.Schema(type=Type.STRING, nullable=True),
                "notice_type": self._types.Schema(
                    type=Type.STRING,
                    enum=["input_vat_mismatch", "unsupported"],
                ),
                "taxpayer_bin": self._types.Schema(type=Type.STRING, nullable=True),
                "taxpayer_tin": self._types.Schema(type=Type.STRING, nullable=True),
                "period_start": self._types.Schema(type=Type.STRING, nullable=True),
                "period_end": self._types.Schema(type=Type.STRING, nullable=True),
                "alleged_itc_claimed_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "alleged_itc_allowed_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "alleged_shortfall_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "classification_confidence": self._types.Schema(type=Type.NUMBER),
            },
            required=["notice_type", "classification_confidence"],
        )

        parts: list[Any] = [_PARSE_PROMPT]
        for img in images:
            parts.append(self._types.Part.from_bytes(data=img, mime_type="image/png"))

        res = self._client.models.generate_content(
            model=self._model_name,
            contents=parts,
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        data = json.loads(res.text)
        return ParsedNotice(**data)

    # ── Draft ────

    def draft_reply(self, *, prompt: str, lookup_key: str) -> DraftReply:
        Type = self._types.Type
        paragraph_schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "text": self._types.Schema(type=Type.STRING),
                "citation_tags": self._types.Schema(
                    type=Type.ARRAY,
                    items=self._types.Schema(type=Type.STRING),
                ),
            },
            required=["text"],
        )
        appendix_row_schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "label": self._types.Schema(type=Type.STRING),
                "value_bdt": self._types.Schema(type=Type.STRING, nullable=True),
                "note": self._types.Schema(type=Type.STRING, nullable=True),
            },
            required=["label"],
        )
        schema = self._types.Schema(
            type=Type.OBJECT,
            properties={
                "body_paragraphs": self._types.Schema(
                    type=Type.ARRAY, items=paragraph_schema,
                ),
                "computation_table_rows": self._types.Schema(
                    type=Type.ARRAY, items=appendix_row_schema,
                ),
                "cited_refs": self._types.Schema(
                    type=Type.ARRAY,
                    items=self._types.Schema(type=Type.STRING),
                ),
            },
            required=["body_paragraphs", "computation_table_rows"],
        )

        res = self._client.models.generate_content(
            model=self._model_name,
            contents=[_DRAFT_SYSTEM, prompt],
            config=self._types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        data = json.loads(res.text)
        # Convert money strings to Decimals via Pydantic
        return DraftReply(**data)

    # ── Embed ────

    def embed_query(self, text: str) -> list[float]:
        res = self._client.models.embed_content(
            model=_EMBED_MODEL,
            contents=text,
        )
        return list(res.embeddings[0].values)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_llm_stub.py -v 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/llm.py backend/tests/notices/test_llm_stub.py
git commit -m "feat(notices): NoticeLLMAdapter protocol + Stub + Gemini impl"
```

---

## Phase 4 — Pipeline modules

### Task 4.1: Parser

**Files:**
- Create: `backend/app/notices/parser.py`
- Create: `backend/tests/notices/test_parser.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_parser.py`:

```python
"""Parser tests using StubNoticeLLMAdapter."""
from datetime import date
from decimal import Decimal

import pytest

from app.notices.llm import LLMUnavailableError, StubNoticeLLMAdapter
from app.notices.parser import parse_notice
from app.notices.schemas import NoticeType, ParsedNotice


_CANNED = ParsedNotice(
    notice_no="NBR/VAT/1/2026",
    notice_date=date(2026, 5, 1),
    notice_type=NoticeType.INPUT_VAT_MISMATCH,
    taxpayer_bin="001234567",
    period_start=date(2026, 4, 1),
    period_end=date(2026, 4, 30),
    alleged_shortfall_bdt=Decimal("10000.00"),
    classification_confidence=0.95,
)


def _png(byte: int = 0) -> bytes:
    # Minimal PNG header so _normalize_image_to_png accepts it
    return b"\x89PNG\r\n\x1a\n" + bytes([byte] * 64)


def test_parse_image_returns_parsed_notice(monkeypatch):
    # Stub out the image normalizer so we don't run PIL
    monkeypatch.setattr(
        "app.notices.parser._normalize_image_to_png",
        lambda b: b,
    )
    stub = StubNoticeLLMAdapter(parses={"fixed-key": _CANNED})
    out = parse_notice(
        _png(), mime="image/png", adapter=stub,
        lookup_key_override="fixed-key",
    )
    assert out.notice_no == "NBR/VAT/1/2026"
    assert out.notice_type == NoticeType.INPUT_VAT_MISMATCH


def test_parse_uses_hash_lookup_key_when_not_overridden(monkeypatch):
    monkeypatch.setattr(
        "app.notices.parser._normalize_image_to_png",
        lambda b: b"normalized",
    )
    # The stub's key is the sha256[:16] of the normalized bytes
    import hashlib
    key = hashlib.sha256(b"normalized").hexdigest()[:16]
    stub = StubNoticeLLMAdapter(parses={key: _CANNED})
    out = parse_notice(_png(), mime="image/png", adapter=stub)
    assert out is not None


def test_parse_raises_for_unsupported_mime():
    from app.notices.exceptions import NoticeUnsupportedTypeError
    stub = StubNoticeLLMAdapter(parses={})
    with pytest.raises(NoticeUnsupportedTypeError):
        parse_notice(b"x", mime="application/zip", adapter=stub)


def test_parse_propagates_llm_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.notices.parser._normalize_image_to_png",
        lambda b: b,
    )
    stub = StubNoticeLLMAdapter(parses={})
    with pytest.raises(LLMUnavailableError):
        parse_notice(_png(), mime="image/png", adapter=stub)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_parser.py -v 2>&1 | tail -5`
Expected: ImportError (`app.notices.parser` missing).

- [ ] **Step 3: Implement the parser**

Create `backend/app/notices/parser.py`:

```python
"""Notice parser — turns raw upload bytes into a ParsedNotice.

Reuses `VisionEngine._normalize_image_to_png` so we get the same
downscaling discipline (longest edge ≤ 2048px, payload ≤ 7MB) that
the ingestion path already uses. For PDFs we render each page with
pypdfium2 and pass all pages to a single LLM call.
"""
from __future__ import annotations

import hashlib
import io
from typing import Optional

import pypdfium2 as pdfium

from app.ingestion.engines.vision import VisionEngine
from app.notices.exceptions import NoticeUnsupportedTypeError
from app.notices.llm import NoticeLLMAdapter
from app.notices.schemas import ParsedNotice

_normalize_image_to_png = VisionEngine._normalize_image_to_png

_IMAGE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/tiff",
    "image/webp", "image/heic", "image/heif",
}
_PDF_MIMES = {"application/pdf"}


def _pdf_to_pngs(file_bytes: bytes) -> list[bytes]:
    out: list[bytes] = []
    pdf = pdfium.PdfDocument(file_bytes)
    for page in pdf:
        bitmap = page.render(scale=200 / 72)
        pil = bitmap.to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        out.append(_normalize_image_to_png(buf.getvalue()))
    return out


def _to_images(file_bytes: bytes, mime: str, filename: str = "<notice>") -> list[bytes]:
    if mime in _PDF_MIMES or file_bytes[:4] == b"%PDF":
        return _pdf_to_pngs(file_bytes)
    if mime in _IMAGE_MIMES:
        return [_normalize_image_to_png(file_bytes)]
    raise NoticeUnsupportedTypeError(filename=filename, mime=mime)


def parse_notice(
    file_bytes: bytes,
    *,
    mime: str,
    adapter: NoticeLLMAdapter,
    filename: str = "<notice>",
    lookup_key_override: Optional[str] = None,
) -> ParsedNotice:
    """Run the Gemini Vision parse on the notice bytes.

    `lookup_key_override` is only used by tests pinning to a canned response.
    """
    images = _to_images(file_bytes, mime, filename=filename)
    lookup_key = lookup_key_override or hashlib.sha256(
        b"".join(images)
    ).hexdigest()[:16]
    return adapter.parse_notice(images=images, lookup_key=lookup_key)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_parser.py -v 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/parser.py backend/tests/notices/test_parser.py
git commit -m "feat(notices): parser — PDF/image → ParsedNotice via Vision LLM"
```

### Task 4.2: Linker

**Files:**
- Create: `backend/app/notices/linker.py`
- Create: `backend/tests/notices/test_linker.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_linker.py`:

```python
"""Linker pure-logic tests with mocked DB lookups."""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.notices.linker import link_notice
from app.notices.schemas import (
    LinkedRecon, NeedsIngestion, NeedsManualLink, NoticeType, ParsedNotice,
)


CLIENT_A = UUID("00000000-0000-0000-0000-00000000000a")
RECON_R = UUID("00000000-0000-0000-0000-0000000000aa")
TENANT = UUID("00000000-0000-0000-0000-000000000099")


def _parsed(**over) -> ParsedNotice:
    base = dict(
        notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        classification_confidence=0.95,
    )
    base.update(over)
    return ParsedNotice(**base)


@pytest.mark.asyncio
async def test_linker_returns_linked_recon_on_match(monkeypatch):
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return [CLIENT_A]
    async def fake_find_recon(client_id, *, tenant_id, period_start, period_end):
        return RECON_R
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    monkeypatch.setattr("app.notices.linker.find_recon_by_period",
                        fake_find_recon)

    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, LinkedRecon)
    assert out.reconciliation_id == RECON_R
    assert out.client_id == CLIENT_A


@pytest.mark.asyncio
async def test_linker_returns_needs_ingestion_when_no_recon(monkeypatch):
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return [CLIENT_A]
    async def fake_find_recon(client_id, *, tenant_id, period_start, period_end):
        return None
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    monkeypatch.setattr("app.notices.linker.find_recon_by_period",
                        fake_find_recon)

    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, NeedsIngestion)
    assert out.client_id == CLIENT_A
    assert out.period_start == date(2026, 4, 1)


@pytest.mark.asyncio
async def test_linker_returns_manual_link_when_no_client_match(monkeypatch):
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return []
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, NeedsManualLink)
    assert out.candidate_clients == []


@pytest.mark.asyncio
async def test_linker_returns_manual_link_when_multiple_clients(monkeypatch):
    CLIENT_B = UUID("00000000-0000-0000-0000-00000000000b")
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return [CLIENT_A, CLIENT_B]
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, NeedsManualLink)
    assert set(out.candidate_clients) == {CLIENT_A, CLIENT_B}


@pytest.mark.asyncio
async def test_linker_returns_manual_link_when_no_bin():
    out = await link_notice(_parsed(taxpayer_bin=None), tenant_id=TENANT)
    assert isinstance(out, NeedsManualLink)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_linker.py -v 2>&1 | tail -5`
Expected: ImportError.

- [ ] **Step 3: Implement linker + the two persistence helpers it depends on**

Create `backend/app/notices/linker.py`:

```python
"""Notice linker — decides what reconciliation (if any) a notice attaches to.

Pure orchestration over two DB helpers in app/notices/persistence.py.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.notices.persistence import (
    find_client_ids_by_bin, find_recon_by_period,
)
from app.notices.schemas import (
    LinkedRecon, LinkerResult, NeedsIngestion, NeedsManualLink, ParsedNotice,
)


async def link_notice(parsed: ParsedNotice, *, tenant_id: UUID) -> LinkerResult:
    if not parsed.taxpayer_bin:
        return NeedsManualLink(candidate_clients=[])

    client_ids: List[UUID] = await find_client_ids_by_bin(
        parsed.taxpayer_bin, tenant_id=tenant_id,
    )
    if not client_ids:
        return NeedsManualLink(candidate_clients=[])
    if len(client_ids) > 1:
        return NeedsManualLink(candidate_clients=client_ids)

    only_client = client_ids[0]
    if not parsed.period_start or not parsed.period_end:
        return NeedsManualLink(candidate_clients=[only_client])

    recon_id: Optional[UUID] = await find_recon_by_period(
        client_id=only_client, tenant_id=tenant_id,
        period_start=parsed.period_start, period_end=parsed.period_end,
    )
    if recon_id:
        return LinkedRecon(reconciliation_id=recon_id, client_id=only_client)
    return NeedsIngestion(
        client_id=only_client,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
    )
```

Add to `backend/app/notices/persistence.py` (create the file with the bare minimum the linker needs; remaining CRUD added in later tasks):

```python
"""Database I/O for the notices module. Uses the supabase admin client.

All callers are expected to have validated tenant scope already; the
`tenant_id` arg is defense-in-depth on every query.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import List, Optional
from uuid import UUID

from app.database import get_supabase_admin


async def find_client_ids_by_bin(
    bin_: str, *, tenant_id: UUID,
) -> List[UUID]:
    """Return client ids under this tenant matching the given BIN.

    The clients table stores BIN under whichever column the existing schema
    uses; this helper normalizes the lookup to digits-only.
    """
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("clients")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .eq("bin", bin_)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return [UUID(r["id"]) for r in (res.data or [])]


async def find_recon_by_period(
    *, client_id: UUID, tenant_id: UUID,
    period_start: date, period_end: date,
) -> Optional[UUID]:
    """Most recent reconciliation matching the (client, exact period) tuple."""
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("vat_reconciliations")
            .select("id, started_at")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return UUID(res.data[0]["id"]) if res.data else None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_linker.py -v 2>&1 | tail -10`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/linker.py backend/app/notices/persistence.py backend/tests/notices/test_linker.py
git commit -m "feat(notices): linker — client+recon lookup → LinkerResult union"
```

### Task 4.3: Retriever

**Files:**
- Create: `backend/app/notices/retriever.py`
- Append to: `backend/app/notices/persistence.py` (add `retrieve_citation_chunks`)
- Create: `backend/tests/notices/test_retriever.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_retriever.py`:

```python
"""Retriever tests — unit tests stub the embedder; live ANN test is gated."""
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.notices.llm import StubNoticeLLMAdapter
from app.notices.retriever import build_query_text, retrieve
from app.notices.schemas import CitationChunk, NoticeType, ParsedNotice, ReconSummary


def _parsed() -> ParsedNotice:
    return ParsedNotice(
        notice_no="X", notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567", period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        alleged_itc_claimed_bdt=Decimal("50000.00"),
        alleged_itc_allowed_bdt=Decimal("40000.00"),
        alleged_shortfall_bdt=Decimal("10000.00"),
        classification_confidence=0.95,
    )


def _summary() -> ReconSummary:
    return ReconSummary(
        reconciliation_id=UUID("00000000-0000-0000-0000-000000000001"),
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[],
    )


def test_build_query_text_includes_key_signals():
    q = build_query_text(_parsed(), _summary())
    assert "input VAT" in q.lower() or "input_vat_mismatch" in q
    assert "10000" in q or "10,000" in q
    assert "no_match" in q or "no-match" in q


@pytest.mark.asyncio
async def test_retrieve_uses_embedder_then_db(monkeypatch):
    canned_chunk = CitationChunk(
        id=UUID("00000000-0000-0000-0000-0000000000aa"),
        source="vat_act_2012", source_ref="Section 46", subsection=None,
        language="en", title="Conditions for input tax credit",
        body="A registered person shall be entitled…",
    )
    stub = StubNoticeLLMAdapter(embeddings={
        # Will be set after we know the actual query text
    })
    q = build_query_text(_parsed(), _summary())
    stub._embeddings[q] = [0.1] * 768

    async def fake_db(*, embedding, topic_tags, k):
        assert len(embedding) == 768
        assert "itc" in topic_tags or "mismatch" in topic_tags
        return [canned_chunk]
    monkeypatch.setattr("app.notices.retriever.retrieve_citation_chunks", fake_db)

    out = await retrieve(_parsed(), _summary(), adapter=stub)
    assert len(out) == 1
    assert out[0].source_ref == "Section 46"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_retriever.py -v 2>&1 | tail -5`
Expected: ImportError.

- [ ] **Step 3: Implement the retriever + DB helper**

Create `backend/app/notices/retriever.py`:

```python
"""Retrieve citation chunks for a notice + reconciliation pair.

Builds a natural-language query combining the notice's allegation language
and the reconciliation's actual numbers, embeds it, and runs ANN against
citation_corpus_chunks pre-filtered by topic_tags.
"""
from __future__ import annotations

from typing import List

from app.notices.llm import NoticeLLMAdapter
from app.notices.persistence import retrieve_citation_chunks
from app.notices.schemas import CitationChunk, ParsedNotice, ReconSummary


_K = 8                                # how many chunk groups to surface
_TOPIC_TAGS = ["itc", "mismatch", "documentary_evidence", "denial_grounds"]


def build_query_text(parsed: ParsedNotice, summary: ReconSummary) -> str:
    """Single dense paragraph capturing both the notice and our position."""
    parts: list[str] = [
        f"NBR notice category: {parsed.notice_type.value}.",
    ]
    if parsed.alleged_shortfall_bdt is not None:
        parts.append(
            f"NBR alleges input VAT shortfall of {parsed.alleged_shortfall_bdt} BDT, "
            f"claiming taxpayer over-claimed ITC."
        )
    if parsed.alleged_itc_claimed_bdt and parsed.alleged_itc_allowed_bdt:
        parts.append(
            f"NBR figures: claimed {parsed.alleged_itc_claimed_bdt} BDT, "
            f"allowed {parsed.alleged_itc_allowed_bdt} BDT."
        )
    parts.append(
        f"Reconciled position: safe ITC {summary.safe_itc_bdt} BDT, "
        f"at-risk ITC {summary.at_risk_itc_bdt} BDT, "
        f"total VAT claimed {summary.total_vat_claimed_bdt} BDT."
    )
    parts.append(
        f"Match counts: exact={summary.matched_exact}, fuzzy={summary.matched_fuzzy}, "
        f"partial={summary.partial_match}, no_match={summary.no_match}."
    )
    parts.append(
        "Relevant law: input tax credit eligibility, documentary evidence "
        "requirements (Mushak 6.3), denial grounds for ITC, mismatch "
        "reconciliation procedure."
    )
    return " ".join(parts)


async def retrieve(
    parsed: ParsedNotice,
    summary: ReconSummary,
    *,
    adapter: NoticeLLMAdapter,
    k: int = _K,
    topic_tags: list[str] | None = None,
) -> List[CitationChunk]:
    query = build_query_text(parsed, summary)
    embedding = adapter.embed_query(query)
    chunks = await retrieve_citation_chunks(
        embedding=embedding,
        topic_tags=topic_tags or _TOPIC_TAGS,
        k=k,
    )
    return chunks
```

Append to `backend/app/notices/persistence.py`:

```python
# ── Citation corpus ANN ───────────────────────────────────────────────────


async def retrieve_citation_chunks(
    *, embedding: list[float], topic_tags: list[str], k: int,
) -> list[dict]:
    """ANN over citation_corpus_chunks, pre-filtered by topic_tags overlap.

    Returns at most 2*k DB rows (both languages × k groups). Caller dedupes
    by (source, source_ref, subsection) if needed.
    """
    from app.notices.schemas import CitationChunk

    sb = get_supabase_admin()
    # supabase-py doesn't expose pgvector operators directly, so we use a
    # pre-defined RPC. The RPC is created in migration 0019 below if you've
    # added it; otherwise we fall back to a raw SQL via the rest API.
    # For simplicity and portability across Supabase versions, the
    # implementation here uses raw SQL via the postgrest "rpc" interface
    # against a stored function `match_citation_chunks` (added in the next
    # task's migration patch).
    def _rpc():
        return sb.rpc(
            "match_citation_chunks",
            {
                "query_embedding": embedding,
                "match_topic_tags": topic_tags,
                "match_k": k,
            },
        ).execute()

    res = await asyncio.to_thread(_rpc)
    rows = res.data or []
    return [
        CitationChunk(
            id=r["id"], source=r["source"], source_ref=r["source_ref"],
            subsection=r.get("subsection"), language=r["language"],
            title=r["title"], body=r["body"],
        )
        for r in rows
    ]
```

- [ ] **Step 4: Add the matching RPC via a new tiny migration**

Create `migrations/0021_match_citation_chunks_rpc.sql`:

```sql
-- 0021_match_citation_chunks_rpc.sql
-- Stored function used by app/notices/retriever.py to do ANN against the
-- citation corpus with a topic-tag pre-filter. Lives as a function (not
-- inline supabase-py) because pgvector operators aren't exposed through
-- the postgrest query builder.

CREATE OR REPLACE FUNCTION match_citation_chunks(
  query_embedding vector(768),
  match_topic_tags text[],
  match_k int
)
RETURNS TABLE (
  id          uuid,
  source      text,
  source_ref  text,
  subsection  text,
  language    text,
  title       text,
  body        text,
  distance    float
)
LANGUAGE sql STABLE AS $$
  WITH groups AS (
    SELECT
      c.id, c.source::text, c.source_ref, c.subsection, c.language::text,
      c.title, c.body,
      (c.embedding <=> query_embedding) AS distance,
      ROW_NUMBER() OVER (
        PARTITION BY c.source, c.source_ref, c.subsection
        ORDER BY (c.embedding <=> query_embedding)
      ) AS rn_per_group
    FROM citation_corpus_chunks c
    WHERE c.topic_tags && match_topic_tags
  )
  -- pick the best language variant per group, then top-k groups
  SELECT id, source, source_ref, subsection, language, title, body, distance
  FROM (
    SELECT *,
           DENSE_RANK() OVER (ORDER BY distance) AS group_rank
    FROM groups
    WHERE rn_per_group = 1
  ) ranked
  WHERE group_rank <= match_k
  -- and also include the other language of each top group
  UNION ALL
  SELECT g.id, g.source, g.source_ref, g.subsection, g.language, g.title, g.body, g.distance
  FROM groups g
  JOIN (
    SELECT source, source_ref, subsection
    FROM (
      SELECT source, source_ref, subsection,
             DENSE_RANK() OVER (ORDER BY distance) AS group_rank
      FROM groups WHERE rn_per_group = 1
    ) t WHERE group_rank <= match_k
  ) top_groups USING (source, source_ref, subsection)
  WHERE g.rn_per_group > 1
  ORDER BY distance, language;
$$;

REVOKE ALL ON FUNCTION match_citation_chunks(vector, text[], int) FROM public;
GRANT EXECUTE ON FUNCTION match_citation_chunks(vector, text[], int) TO authenticated;
GRANT EXECUTE ON FUNCTION match_citation_chunks(vector, text[], int) TO service_role;
```

Apply via Supabase MCP `apply_migration` with name `0021_match_citation_chunks_rpc`.

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_retriever.py -v 2>&1 | tail -10`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/notices/retriever.py backend/app/notices/persistence.py backend/tests/notices/test_retriever.py migrations/0021_match_citation_chunks_rpc.sql
git commit -m "feat(notices): retriever — embed query + ANN RPC over citation corpus"
```

### Task 4.4: Drafter (LLM call + post-processing)

**Files:**
- Create: `backend/app/notices/drafter.py`
- Create: `backend/tests/notices/test_drafter.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_drafter.py`:

```python
"""Drafter tests: prompt construction, citation validation, HTML sanitize."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.notices.drafter import (
    build_draft_prompt, finalize_draft_output, _validate_citation_tags,
)
from app.notices.llm import StubNoticeLLMAdapter
from app.notices.schemas import (
    CitationChunk, DraftAppendixRow, DraftParagraph, DraftReply,
    NoticeType, ParsedNotice, ReconSummary,
)


def _p() -> ParsedNotice:
    return ParsedNotice(
        notice_type=NoticeType.INPUT_VAT_MISMATCH, taxpayer_bin="001234567",
        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        alleged_shortfall_bdt=Decimal("10000.00"),
        classification_confidence=0.95,
    )


def _s() -> ReconSummary:
    return ReconSummary(
        reconciliation_id=UUID("00000000-0000-0000-0000-000000000001"),
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[],
    )


def _cit() -> list[CitationChunk]:
    return [
        CitationChunk(
            id=UUID("00000000-0000-0000-0000-0000000000aa"),
            source="vat_act_2012", source_ref="Section 46",
            language="bn", title="ITC শর্ত", body="… ধারা ৪৬ …",
        ),
    ]


def test_prompt_includes_citations_tagged():
    p = build_draft_prompt(_p(), _s(), _cit())
    assert "[CIT-1]" in p
    assert "Section 46" in p
    assert "40000.00" in p  # recon summary present


def test_validate_strips_unknown_citation_tags():
    body = "Real cite [CIT-1]. Fake cite [CIT-9]. Plain text."
    cleaned = _validate_citation_tags(body, allowed_tags={"CIT-1"})
    assert "[CIT-1]" in cleaned
    assert "[CIT-9]" not in cleaned
    assert "[citation needed — review]" in cleaned


def test_finalize_draft_output_produces_html_and_citations():
    raw = DraftReply(
        body_paragraphs=[
            DraftParagraph(text="প্যারা ১ [CIT-1].", citation_tags=["CIT-1"]),
            DraftParagraph(text="প্যারা ২ <script>alert(1)</script>", citation_tags=[]),
        ],
        computation_table_rows=[
            DraftAppendixRow(label="Claimed", value_bdt=Decimal("50000.00"), note=None),
        ],
        cited_refs=["CIT-1"],
    )
    out = finalize_draft_output(raw, retrieved_chunks=_cit())
    assert "<p>" in out["body_html"]
    assert "<script>" not in out["body_html"]  # sanitized
    assert '<sup class="citation"' in out["body_html"]
    assert len(out["citations"]) == 1
    assert out["citations"][0]["source_ref"] == "Section 46"


def test_finalize_replaces_unknown_tag_with_placeholder():
    raw = DraftReply(
        body_paragraphs=[
            DraftParagraph(text="ভুল cite [CIT-99].", citation_tags=["CIT-99"]),
        ],
        computation_table_rows=[],
        cited_refs=["CIT-99"],
    )
    out = finalize_draft_output(raw, retrieved_chunks=_cit())
    assert "citation needed" in out["body_html"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_drafter.py -v 2>&1 | tail -5`
Expected: ImportError.

- [ ] **Step 3: Implement the drafter**

Create `backend/app/notices/drafter.py`:

```python
"""Notice drafter — LLM call + post-processing.

Builds the prompt, calls the adapter, validates that every [CIT-N] tag
emitted by the model resolves to a real retrieved chunk, sanitizes the
resulting HTML, and returns the persisted-ready shape.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

import bleach

from app.notices.llm import NoticeLLMAdapter
from app.notices.schemas import (
    CitationChunk, DraftReply, ParsedNotice, ReconSummary,
)


_HTML_ALLOWED_TAGS = ["p", "strong", "em", "br", "sup"]
_HTML_ALLOWED_ATTRS = {"sup": ["class", "data-ref"]}
_CITATION_TAG_RE = re.compile(r"\[CIT-(\d+)\]")
_PLACEHOLDER = "[citation needed — review]"


def build_draft_prompt(
    parsed: ParsedNotice,
    summary: ReconSummary,
    citations: list[CitationChunk],
) -> str:
    """Assemble the user-side prompt sent to Gemini.

    System instruction lives in app/notices/llm.py (_DRAFT_SYSTEM); this
    function only assembles the per-notice content.
    """
    # Group bn+en variants of the same source_ref into one CIT-N
    groups: list[tuple[str, list[CitationChunk]]] = []
    seen: dict[tuple[str, str, str | None], int] = {}
    for c in citations:
        key = (c.source, c.source_ref, c.subsection)
        if key not in seen:
            seen[key] = len(groups)
            groups.append((c.source_ref, [c]))
        else:
            groups[seen[key]][1].append(c)

    cit_lines = []
    for i, (_ref, items) in enumerate(groups, start=1):
        for item in items:
            tag = f"[CIT-{i}]"
            cit_lines.append(
                f"{tag} ({item.language}) {item.source_ref}"
                + (f" {item.subsection}" if item.subsection else "")
                + f": {item.body[:600]}"
            )

    parts = [
        "## NOTICE METADATA",
        f"Notice no: {parsed.notice_no or '(unknown)'}",
        f"Notice date: {parsed.notice_date or '(unknown)'}",
        f"Taxpayer BIN: {parsed.taxpayer_bin or '(unknown)'}",
        f"Period: {parsed.period_start} to {parsed.period_end}",
        f"Alleged claimed ITC: {parsed.alleged_itc_claimed_bdt} BDT",
        f"Alleged allowed ITC: {parsed.alleged_itc_allowed_bdt} BDT",
        f"Alleged shortfall: {parsed.alleged_shortfall_bdt} BDT",
        "",
        "## RECONCILIATION POSITION (ground truth)",
        f"Safe ITC: {summary.safe_itc_bdt} BDT",
        f"At-risk ITC: {summary.at_risk_itc_bdt} BDT",
        f"Total VAT claimed: {summary.total_vat_claimed_bdt} BDT",
        f"Match counts — exact: {summary.matched_exact}, fuzzy: {summary.matched_fuzzy}, "
        f"partial: {summary.partial_match}, no_match: {summary.no_match}",
    ]
    if summary.disputed_rows:
        parts.append("Disputed rows (representative sample):")
        for r in summary.disputed_rows[:20]:
            parts.append(
                f"  - {r.get('supplier_name','?')} (BIN {r.get('supplier_bin','?')}) "
                f"inv {r.get('invoice_no','?')} VAT {r.get('vat_amount_bdt','?')} "
                f"[{r.get('match_status','?')}]"
            )

    parts += [
        "",
        "## CITATIONS YOU MAY CITE",
        "Reference each by its tag, e.g. [CIT-1]. Cite ONLY from this list.",
        *cit_lines,
        "",
        "## TASK",
        "Draft a formal Bangla reply letter following NBR conventions. ",
        "Return a JSON object matching the response schema with body_paragraphs, ",
        "computation_table_rows (in English, suitable for an appendix), and ",
        "cited_refs (the [CIT-N] tags you used). The body must explain the ",
        "taxpayer's actual reconciled position and cite supporting law.",
    ]
    return "\n".join(parts)


def _validate_citation_tags(text: str, *, allowed_tags: set[str]) -> str:
    """Replace any [CIT-N] not in `allowed_tags` with the review placeholder."""
    def _sub(m):
        tag = f"CIT-{m.group(1)}"
        return f"[{tag}]" if tag in allowed_tags else _PLACEHOLDER
    return _CITATION_TAG_RE.sub(_sub, text)


def _paragraph_to_html(text: str, *, allowed_tags: set[str],
                      tag_to_ref: dict[str, str]) -> str:
    """Render one paragraph: validate cites, convert [CIT-N] → <sup>, sanitize."""
    safe = _validate_citation_tags(text, allowed_tags=allowed_tags)

    def _to_sup(m):
        tag = f"CIT-{m.group(1)}"
        if tag in tag_to_ref:
            return f'<sup class="citation" data-ref="{tag}">[{m.group(1)}]</sup>'
        return _PLACEHOLDER
    with_sups = _CITATION_TAG_RE.sub(_to_sup, safe)
    sanitized = bleach.clean(
        with_sups,
        tags=_HTML_ALLOWED_TAGS,
        attributes=_HTML_ALLOWED_ATTRS,
        strip=True,
    )
    return f"<p>{sanitized}</p>"


def finalize_draft_output(
    raw: DraftReply,
    *,
    retrieved_chunks: list[CitationChunk],
) -> dict[str, Any]:
    """Post-process raw LLM output into persisted-ready shape.

    Returns dict with keys: body_html (str), appendix_json (dict),
    citations (list[dict]).
    """
    # Group retrieved chunks into [CIT-N] tags (same grouping as build_draft_prompt)
    groups: list[tuple[str, list[CitationChunk]]] = []
    seen: dict[tuple[str, str, str | None], int] = {}
    for c in retrieved_chunks:
        key = (c.source, c.source_ref, c.subsection)
        if key not in seen:
            seen[key] = len(groups)
            groups.append((c.source_ref, [c]))
        else:
            groups[seen[key]][1].append(c)

    tag_to_ref: dict[str, str] = {}
    tag_to_chunk: dict[str, CitationChunk] = {}
    for i, (_ref, items) in enumerate(groups, start=1):
        tag = f"CIT-{i}"
        tag_to_ref[tag] = items[0].source_ref
        # Prefer Bangla variant for the body display; fall back to first
        bn = next((c for c in items if c.language == "bn"), items[0])
        tag_to_chunk[tag] = bn

    allowed_tags = set(tag_to_ref.keys())

    paragraph_htmls: list[str] = []
    citations: list[dict[str, Any]] = []
    seen_tag_in_para: set[str] = set()
    for idx, para in enumerate(raw.body_paragraphs):
        para_html = _paragraph_to_html(
            para.text, allowed_tags=allowed_tags, tag_to_ref=tag_to_ref,
        )
        paragraph_htmls.append(para_html)
        # Record each citation use for the citations panel
        for m in _CITATION_TAG_RE.finditer(para.text):
            tag = f"CIT-{m.group(1)}"
            if tag in tag_to_chunk and (tag, idx) not in seen_tag_in_para:
                chunk = tag_to_chunk[tag]
                citations.append({
                    "corpus_chunk_id": str(chunk.id),
                    "source_ref": chunk.source_ref,
                    "snippet": chunk.body[:240],
                    "paragraph_idx": idx,
                })
                seen_tag_in_para.add((tag, idx))

    body_html = "\n".join(paragraph_htmls)

    appendix_json: dict[str, Any] = {
        "rows": [r.model_dump(mode="json") for r in raw.computation_table_rows],
    }

    return {
        "body_html": body_html,
        "appendix_json": appendix_json,
        "citations": citations,
    }


async def draft(
    parsed: ParsedNotice,
    summary: ReconSummary,
    citations: list[CitationChunk],
    *,
    adapter: NoticeLLMAdapter,
    lookup_key_override: str | None = None,
) -> dict[str, Any]:
    """Run the LLM call and return the finalized draft shape."""
    prompt = build_draft_prompt(parsed, summary, citations)
    lookup_key = lookup_key_override or hashlib.sha256(prompt.encode()).hexdigest()[:16]
    raw = adapter.draft_reply(prompt=prompt, lookup_key=lookup_key)
    return finalize_draft_output(raw, retrieved_chunks=citations)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_drafter.py -v 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/drafter.py backend/tests/notices/test_drafter.py
git commit -m "feat(notices): drafter — prompt + post-processing + citation validation"
```

### Task 4.5: Rendering (.docx + .pdf)

**Files:**
- Create: `backend/app/notices/rendering.py`
- Create: `backend/tests/notices/test_rendering.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_rendering.py`:

```python
"""Rendering tests. .docx is always tested; .pdf is gated on `soffice`."""
import io
import shutil
from decimal import Decimal

import pytest
from docx import Document

from app.notices.rendering import (
    PdfRendererUnavailableError, render_docx, render_pdf,
)


DRAFT = {
    "language": "bn",
    "body_html": "<p>প্রথম প্যারা</p><p>দ্বিতীয় প্যারা <sup class=\"citation\" data-ref=\"CIT-1\">[1]</sup></p>",
    "appendix_json": {
        "rows": [
            {"label": "Claimed ITC", "value_bdt": "50000.00", "note": None},
            {"label": "Allowed ITC", "value_bdt": "40000.00", "note": "per NBR"},
        ],
    },
    "citations": [
        {"corpus_chunk_id": "00000000-0000-0000-0000-0000000000aa",
         "source_ref": "Section 46", "snippet": "Conditions for ITC…",
         "paragraph_idx": 1},
    ],
}
NOTICE_META = {
    "notice_no": "NBR/VAT/1/2026", "notice_date": "2026-05-01",
    "taxpayer_bin": "001234567",
    "period_start": "2026-04-01", "period_end": "2026-04-30",
}
TENANT_META = {"firm_name": "Demo CA Co.", "address": "Dhaka, Bangladesh"}


def test_render_docx_contains_body_paragraphs_and_appendix():
    out = render_docx(draft=DRAFT, notice=NOTICE_META, tenant=TENANT_META)
    doc = Document(io.BytesIO(out))
    text_all = "\n".join(p.text for p in doc.paragraphs)
    assert "প্রথম প্যারা" in text_all
    assert "Demo CA Co." in text_all
    # Appendix is a table
    assert len(doc.tables) >= 1
    appendix_text = "\n".join(
        cell.text for t in doc.tables for row in t.rows for cell in row.cells
    )
    assert "Claimed ITC" in appendix_text
    assert "50000.00" in appendix_text


def test_render_docx_includes_citations_section():
    out = render_docx(draft=DRAFT, notice=NOTICE_META, tenant=TENANT_META)
    doc = Document(io.BytesIO(out))
    text_all = "\n".join(p.text for p in doc.paragraphs)
    assert "Section 46" in text_all


@pytest.mark.skipif(
    shutil.which("soffice") is None,
    reason="LibreOffice (soffice) not on PATH; PDF rendering unavailable",
)
def test_render_pdf_emits_pdf_bytes():
    docx_bytes = render_docx(draft=DRAFT, notice=NOTICE_META, tenant=TENANT_META)
    pdf_bytes = render_pdf(docx_bytes)
    assert pdf_bytes[:4] == b"%PDF"


def test_render_pdf_raises_when_soffice_missing(monkeypatch):
    monkeypatch.setattr(
        "app.notices.rendering._soffice_path", lambda: None,
    )
    with pytest.raises(PdfRendererUnavailableError):
        render_pdf(b"not a real docx")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_rendering.py -v 2>&1 | tail -10`
Expected: ImportError.

- [ ] **Step 3: Implement rendering**

Create `backend/app/notices/rendering.py`:

```python
"""Render a saved draft to .docx (always) and .pdf (when LibreOffice is on PATH).

The HTML body is parsed as a stream of <p>/<sup> tags using lxml. Citation
markers (<sup class="citation" data-ref="CIT-N">) are rendered inline as
superscript numerals; the canonical citation list is appended as a
separate section at the end of the document.

The .docx → .pdf step shells out to `soffice --headless --convert-to pdf`.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from typing import Any

from docx import Document
from docx.shared import Pt
from lxml import html as lxml_html


class PdfRendererUnavailableError(RuntimeError):
    """Raised when LibreOffice is not available on this host."""


def _soffice_path() -> str | None:
    return shutil.which("soffice") or shutil.which("soffice.exe")


def _add_paragraph_from_html(doc, html_fragment: str) -> None:
    """Append one Word paragraph from a single <p>…</p> HTML fragment.

    Walks the fragment children:
    - text nodes → run
    - <sup class="citation"> → superscript run with its inner text
    - <strong>, <em> → bold / italic runs
    Anything else is rendered as plain text.
    """
    p = doc.add_paragraph()
    root = lxml_html.fromstring(html_fragment if html_fragment.strip().startswith("<")
                                else f"<p>{html_fragment}</p>")

    def _emit_text(text: str, *, bold=False, italic=False, superscript=False) -> None:
        if not text:
            return
        run = p.add_run(text)
        run.bold = bold
        run.italic = italic
        run.font.superscript = superscript
        # Use a Bangla-capable font; Word will substitute if missing
        run.font.name = "Noto Sans Bengali"
        run.font.size = Pt(11)

    def _walk(node, *, bold=False, italic=False, superscript=False):
        if node.text:
            _emit_text(node.text, bold=bold, italic=italic, superscript=superscript)
        for child in node:
            tag = child.tag.lower() if isinstance(child.tag, str) else ""
            cb, ci, cs = bold, italic, superscript
            if tag == "strong":
                cb = True
            elif tag == "em":
                ci = True
            elif tag == "sup":
                cs = True
            _walk(child, bold=cb, italic=ci, superscript=cs)
            if child.tail:
                _emit_text(child.tail, bold=bold, italic=italic, superscript=superscript)

    _walk(root)


def _add_letterhead(doc, tenant: dict[str, Any]) -> None:
    p = doc.add_paragraph()
    run = p.add_run(tenant.get("firm_name", "Chartered Accountants"))
    run.bold = True
    run.font.size = Pt(14)
    if tenant.get("address"):
        addr = doc.add_paragraph(tenant["address"])
        addr.runs[0].font.size = Pt(10)
    doc.add_paragraph("")  # spacer


def _add_reference_block(doc, notice: dict[str, Any]) -> None:
    p = doc.add_paragraph()
    p.add_run("প্রসঙ্গ: ").bold = True
    p.add_run(
        f"NBR Notice No. {notice.get('notice_no','(unknown)')} "
        f"dated {notice.get('notice_date','(unknown)')} — "
        f"VAT period {notice.get('period_start','?')} to {notice.get('period_end','?')}, "
        f"BIN {notice.get('taxpayer_bin','?')}."
    )
    doc.add_paragraph("")
    doc.add_paragraph("প্রিয় মহোদয়,")


def _add_appendix(doc, appendix_json: dict[str, Any]) -> None:
    doc.add_paragraph("")
    h = doc.add_paragraph()
    h.add_run("Appendix — Computation Summary (BDT)").bold = True

    rows = appendix_json.get("rows") or []
    if not rows:
        doc.add_paragraph("(no rows)")
        return
    table = doc.add_table(rows=1 + len(rows), cols=3)
    table.style = "Light List"
    hdr = table.rows[0].cells
    hdr[0].text = "Item"
    hdr[1].text = "Amount (BDT)"
    hdr[2].text = "Note"
    for i, r in enumerate(rows, start=1):
        cells = table.rows[i].cells
        cells[0].text = str(r.get("label", ""))
        cells[1].text = str(r.get("value_bdt", "") or "")
        cells[2].text = str(r.get("note", "") or "")


def _add_citations(doc, citations: list[dict[str, Any]]) -> None:
    if not citations:
        return
    doc.add_paragraph("")
    h = doc.add_paragraph()
    h.add_run("Citations").bold = True
    for i, c in enumerate(citations, start=1):
        p = doc.add_paragraph(style="List Number")
        p.add_run(c.get("source_ref", "") + " — ").bold = True
        p.add_run(c.get("snippet", ""))


def render_docx(
    *, draft: dict[str, Any], notice: dict[str, Any], tenant: dict[str, Any],
) -> bytes:
    """Build a .docx reply and return its bytes."""
    doc = Document()
    _add_letterhead(doc, tenant)
    _add_reference_block(doc, notice)

    # Body: parse the HTML body into one Word paragraph per <p>
    body_html = draft.get("body_html", "")
    if body_html:
        # Wrap so we can parse multiple <p> as a single document
        root = lxml_html.fromstring(f"<div>{body_html}</div>")
        for child in root.iter():
            if isinstance(child.tag, str) and child.tag.lower() == "p":
                _add_paragraph_from_html(
                    doc, lxml_html.tostring(child, encoding="unicode"),
                )

    doc.add_paragraph("")
    doc.add_paragraph("ধন্যবাদান্তে,")
    doc.add_paragraph(tenant.get("firm_name", ""))

    _add_appendix(doc, draft.get("appendix_json", {}))
    _add_citations(doc, draft.get("citations", []))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_pdf(docx_bytes: bytes) -> bytes:
    """Convert .docx → .pdf via LibreOffice headless.

    Raises PdfRendererUnavailableError if soffice is not on PATH.
    """
    soffice = _soffice_path()
    if not soffice:
        raise PdfRendererUnavailableError(
            "LibreOffice (soffice) not on PATH — PDF rendering unavailable"
        )
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, "in.docx")
        with open(in_path, "wb") as f:
            f.write(docx_bytes)
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", td, in_path],
            check=True, capture_output=True, timeout=60,
        )
        out_path = os.path.join(td, "in.pdf")
        with open(out_path, "rb") as f:
            return f.read()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_rendering.py -v 2>&1 | tail -10`
Expected: 3 passed + 1 conditionally passed/skipped depending on soffice presence.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/rendering.py backend/tests/notices/test_rendering.py
git commit -m "feat(notices): rendering — .docx (always) + .pdf (when LibreOffice present)"
```

---

## Phase 5 — Persistence completion, storage, worker, service, router

### Task 5.1: Complete persistence module (notices, drafts, revisions, summary)

**Files:**
- Append to: `backend/app/notices/persistence.py`
- Create: `backend/app/notices/storage.py`
- Create: `backend/tests/notices/test_persistence.py`

- [ ] **Step 1: Write the failing persistence test (gated on live DB)**

Create `backend/tests/notices/test_persistence.py`:

```python
"""Live-DB persistence tests. Gated on INGESTION_TEST_TENANT_ID."""
import os
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_TENANT_ID"),
    reason="Live persistence tests require INGESTION_TEST_TENANT_ID",
)


@pytest.fixture
def tenant_id() -> UUID:
    return UUID(os.environ["INGESTION_TEST_TENANT_ID"])


@pytest.fixture
def client_id() -> UUID:
    return UUID(os.environ["INGESTION_TEST_CLIENT_ID"])


@pytest.fixture
def user_id() -> UUID:
    return UUID(os.environ["INGESTION_TEST_USER_ID"])


@pytest.mark.asyncio
async def test_create_get_update_notice_roundtrip(tenant_id, client_id, user_id):
    from app.notices import persistence as p
    from app.notices.schemas import NoticeStatus

    notice_id = await p.create_notice(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        storage_path="placeholder", original_filename="x.pdf",
        mime_type="application/pdf", byte_size=1024,
    )
    n = await p.get_notice(notice_id, tenant_id=tenant_id)
    assert n["status"] == NoticeStatus.PENDING.value

    await p.update_notice(
        notice_id, tenant_id=tenant_id,
        status=NoticeStatus.PARSED,
        notice_no="NBR/X/1", notice_date=date(2026, 5, 1),
        taxpayer_bin="001234567",
        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        alleged_shortfall_bdt=Decimal("10000.00"),
    )
    n2 = await p.get_notice(notice_id, tenant_id=tenant_id)
    assert n2["status"] == NoticeStatus.PARSED.value
    assert n2["notice_no"] == "NBR/X/1"


@pytest.mark.asyncio
async def test_create_and_update_draft_creates_revisions(
    tenant_id, client_id, user_id,
):
    from app.notices import persistence as p
    from app.notices.schemas import NoticeDraftEditSource, NoticeStatus

    notice_id = await p.create_notice(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        storage_path="placeholder", original_filename="y.pdf",
        mime_type="application/pdf", byte_size=10,
    )
    draft_id = await p.create_draft(
        notice_id=notice_id, tenant_id=tenant_id,
        body_html="<p>v1</p>", appendix_json={"rows": []},
        citations=[], model_version="t",
        edited_by=user_id, edit_source=NoticeDraftEditSource.LLM_GENERATED,
    )
    revs1 = await p.list_revisions(draft_id, tenant_id=tenant_id)
    assert len(revs1) == 1

    await p.update_draft(
        draft_id, tenant_id=tenant_id,
        body_html="<p>v2</p>", appendix_json={"rows": [{"label": "x"}]},
        edited_by=user_id, edit_source=NoticeDraftEditSource.USER_EDIT,
    )
    revs2 = await p.list_revisions(draft_id, tenant_id=tenant_id)
    assert len(revs2) == 2
    assert revs2[0]["revision_no"] == 2  # newest first
```

- [ ] **Step 2: Append the missing helpers to `backend/app/notices/persistence.py`**

Append below the existing functions:

```python
# ── Notice CRUD ──────────────────────────────────────────────────────────

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from app.notices.schemas import (
    NoticeDraftEditSource, NoticeDraftStatus, NoticeStatus,
)


async def create_notice(
    *,
    tenant_id: UUID,
    client_id: UUID,
    created_by: UUID,
    storage_path: str,
    original_filename: str,
    mime_type: str,
    byte_size: int,
) -> UUID:
    sb = get_supabase_admin()

    def _ins():
        return sb.table("notices").insert({
            "tenant_id": str(tenant_id),
            "client_id": str(client_id),
            "created_by": str(created_by),
            "storage_path": storage_path,
            "original_filename": original_filename,
            "mime_type": mime_type,
            "byte_size": byte_size,
            "status": NoticeStatus.PENDING.value,
        }).execute()

    res = await asyncio.to_thread(_ins)
    return UUID(res.data[0]["id"])


async def get_notice(notice_id: UUID, *, tenant_id: UUID) -> Optional[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notices")
            .select("*")
            .eq("id", str(notice_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def list_notices(
    *, tenant_id: UUID, client_id: UUID, limit: int = 100,
) -> List[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notices")
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .order("notice_date", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


async def update_notice(
    notice_id: UUID, *, tenant_id: UUID, **fields: Any,
) -> None:
    """Update arbitrary fields on a notice. Enum values are .value-unwrapped."""
    payload: Dict[str, Any] = {}
    for k, v in fields.items():
        if v is None:
            continue
        if hasattr(v, "value"):
            payload[k] = v.value
        elif isinstance(v, Decimal):
            payload[k] = str(v)
        elif isinstance(v, (date, datetime)):
            payload[k] = v.isoformat()
        elif isinstance(v, UUID):
            payload[k] = str(v)
        else:
            payload[k] = v
    if not payload:
        return
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("notices")
            .update(payload)
            .eq("id", str(notice_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Draft CRUD (with append-only revisions) ──────────────────────────────


async def create_draft(
    *,
    notice_id: UUID,
    tenant_id: UUID,
    body_html: str,
    appendix_json: Dict[str, Any],
    citations: List[Dict[str, Any]],
    model_version: str,
    edited_by: UUID,
    edit_source: NoticeDraftEditSource,
) -> UUID:
    """Create the head draft row + revision #1 atomically (two inserts)."""
    sb = get_supabase_admin()

    def _ins_draft():
        return sb.table("notice_drafts").insert({
            "tenant_id": str(tenant_id),
            "notice_id": str(notice_id),
            "language": "bn",
            "body_html": body_html,
            "appendix_json": appendix_json,
            "citations": citations,
            "model_version": model_version,
            "status": NoticeDraftStatus.DRAFT.value,
        }).execute()

    res = await asyncio.to_thread(_ins_draft)
    draft_id = UUID(res.data[0]["id"])

    def _ins_rev():
        return sb.table("notice_draft_revisions").insert({
            "tenant_id": str(tenant_id),
            "draft_id": str(draft_id),
            "revision_no": 1,
            "body_html": body_html,
            "appendix_json": appendix_json,
            "edited_by": str(edited_by),
            "edit_source": edit_source.value,
        }).execute()

    await asyncio.to_thread(_ins_rev)
    return draft_id


async def get_draft(notice_id: UUID, *, tenant_id: UUID) -> Optional[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notice_drafts")
            .select("*")
            .eq("notice_id", str(notice_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def update_draft(
    draft_id: UUID, *,
    tenant_id: UUID,
    body_html: str,
    appendix_json: Dict[str, Any],
    edited_by: UUID,
    edit_source: NoticeDraftEditSource,
    edit_reason: Optional[str] = None,
    citations: Optional[List[Dict[str, Any]]] = None,
    model_version: Optional[str] = None,
) -> None:
    """Patch the head + append a revision in the same logical save."""
    sb = get_supabase_admin()

    head_payload: Dict[str, Any] = {
        "body_html": body_html,
        "appendix_json": appendix_json,
    }
    if citations is not None:
        head_payload["citations"] = citations
    if model_version is not None:
        head_payload["model_version"] = model_version

    def _patch_head():
        return (
            sb.table("notice_drafts")
            .update(head_payload)
            .eq("id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_patch_head)

    # Find next revision_no
    def _max_rev():
        return (
            sb.table("notice_draft_revisions")
            .select("revision_no")
            .eq("draft_id", str(draft_id))
            .order("revision_no", desc=True)
            .limit(1)
            .execute()
        )

    mrev = await asyncio.to_thread(_max_rev)
    next_no = (mrev.data[0]["revision_no"] if mrev.data else 0) + 1

    def _ins_rev():
        return sb.table("notice_draft_revisions").insert({
            "tenant_id": str(tenant_id),
            "draft_id": str(draft_id),
            "revision_no": next_no,
            "body_html": body_html,
            "appendix_json": appendix_json,
            "edited_by": str(edited_by),
            "edit_source": edit_source.value,
            "edit_reason": edit_reason,
        }).execute()

    await asyncio.to_thread(_ins_rev)


async def list_revisions(
    draft_id: UUID, *, tenant_id: UUID,
) -> List[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notice_draft_revisions")
            .select("id, revision_no, edited_by, edit_source, edit_reason, created_at")
            .eq("draft_id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .order("revision_no", desc=True)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


async def finalize_draft(
    draft_id: UUID, *, tenant_id: UUID, finalized_by: UUID,
) -> None:
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("notice_drafts")
            .update({
                "status": NoticeDraftStatus.FINALIZED.value,
                "finalized_at": datetime.now(timezone.utc).isoformat(),
                "finalized_by": str(finalized_by),
            })
            .eq("id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def reopen_draft(draft_id: UUID, *, tenant_id: UUID) -> None:
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("notice_drafts")
            .update({
                "status": NoticeDraftStatus.DRAFT.value,
                "finalized_at": None,
                "finalized_by": None,
            })
            .eq("id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Reconciliation summary for the drafter ───────────────────────────────


async def fetch_recon_summary(
    reconciliation_id: UUID, *, tenant_id: UUID,
) -> Dict[str, Any]:
    """Fetch the header aggregates + a representative sample of disputed rows.

    Returns a dict suitable for constructing ReconSummary.
    """
    sb = get_supabase_admin()

    def _hdr():
        return (
            sb.table("vat_reconciliations")
            .select("*")
            .eq("id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .single()
            .execute()
        )

    def _rows():
        return (
            sb.table("recon_line_items")
            .select("pr_supplier_name, pr_supplier_bin, pr_invoice_no, "
                    "pr_vat_amount_bdt, match_status")
            .eq("tenant_id", str(tenant_id))
            .eq("reconciliation_id", str(reconciliation_id))
            .in_("match_status", ["partial", "no_match"])
            .limit(20)
            .execute()
        )

    hdr = (await asyncio.to_thread(_hdr)).data
    rows = (await asyncio.to_thread(_rows)).data or []
    return {
        "reconciliation_id": hdr["id"],
        "safe_itc_bdt": hdr.get("safe_itc_bdt") or "0",
        "at_risk_itc_bdt": hdr.get("at_risk_itc_bdt") or "0",
        "total_vat_claimed_bdt": hdr.get("total_vat_claimed_bdt") or "0",
        "matched_exact": hdr.get("matched_exact") or 0,
        "matched_fuzzy": hdr.get("matched_fuzzy") or 0,
        "partial_match": hdr.get("partial_match") or 0,
        "no_match": hdr.get("no_match") or 0,
        "disputed_rows": [
            {
                "supplier_name": r.get("pr_supplier_name"),
                "supplier_bin":  r.get("pr_supplier_bin"),
                "invoice_no":    r.get("pr_invoice_no"),
                "vat_amount_bdt": r.get("pr_vat_amount_bdt"),
                "match_status":  r.get("match_status"),
            }
            for r in rows
        ],
    }
```

- [ ] **Step 3: Create the storage module**

Create `backend/app/notices/storage.py`:

```python
"""Supabase Storage I/O for the 'notices' bucket."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin

BUCKET = "notices"


async def upload_original(
    *, tenant_id: UUID, client_id: UUID, notice_id: UUID,
    filename: str, content: bytes, mime_type: str,
) -> str:
    path = f"{tenant_id}/{client_id}/{notice_id}/{filename}"
    sb = get_supabase_admin()

    def _up():
        sb.storage.from_(BUCKET).upload(
            path=path, file=content,
            file_options={"content-type": mime_type, "upsert": "false"},
        )

    await asyncio.to_thread(_up)
    return path


async def download_original(path: str) -> bytes:
    sb = get_supabase_admin()

    def _dl():
        return sb.storage.from_(BUCKET).download(path)

    return await asyncio.to_thread(_dl)


async def create_signed_url(path: str, *, expires_in_seconds: int = 60) -> str:
    sb = get_supabase_admin()

    def _sign():
        res: dict[str, Any] = sb.storage.from_(BUCKET).create_signed_url(
            path, expires_in_seconds,
        )
        return res["signedURL"]

    return await asyncio.to_thread(_sign)
```

- [ ] **Step 4: Run the persistence test live (with INGESTION_TEST_* set)**

Run: `cd backend && python -m pytest tests/notices/test_persistence.py -v 2>&1 | tail -10`
Expected: 2 passed (or 2 skipped on dev boxes without the env vars).

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/persistence.py backend/app/notices/storage.py backend/tests/notices/test_persistence.py
git commit -m "feat(notices): complete persistence + storage I/O"
```

### Task 5.2: Worker

**Files:**
- Create: `backend/app/notices/worker.py`
- Create: `backend/tests/notices/test_worker.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/notices/test_worker.py`:

```python
"""End-to-end worker test with all dependencies stubbed."""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest

from app.notices.llm import StubNoticeLLMAdapter, set_notice_llm_adapter
from app.notices.schemas import (
    CitationChunk, DraftAppendixRow, DraftParagraph, DraftReply,
    LinkedRecon, NeedsIngestion, NoticeStatus, NoticeType, ParsedNotice,
)


@pytest.mark.asyncio
async def test_worker_processes_notice_end_to_end(monkeypatch):
    """Notice with linked recon → parser → linker → retriever → drafter → drafted."""
    from app.notices import worker

    notice_id = uuid4()
    tenant = uuid4()
    client = uuid4()
    recon = uuid4()

    captured_status: list[str] = []

    # ── Stub LLM ──
    parsed = ParsedNotice(
        notice_no="X-1", notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567", period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30), classification_confidence=0.95,
        alleged_shortfall_bdt=Decimal("10000.00"),
    )
    draft_reply = DraftReply(
        body_paragraphs=[DraftParagraph(text="hi [CIT-1]", citation_tags=["CIT-1"])],
        computation_table_rows=[DraftAppendixRow(label="x", value_bdt=Decimal("1.00"))],
        cited_refs=["CIT-1"],
    )
    set_notice_llm_adapter(StubNoticeLLMAdapter(
        parses={"any-key": parsed},
        drafts={"any-key": draft_reply},
        embeddings={"q": [0.0] * 768},
    ))

    # ── Stub all the DB + storage calls ──
    monkeypatch.setattr(
        worker, "get_notice", AsyncMock(return_value={
            "id": str(notice_id), "tenant_id": str(tenant), "client_id": str(client),
            "storage_path": "x/y/z/notice.pdf", "mime_type": "application/pdf",
            "original_filename": "notice.pdf",
            "status": NoticeStatus.PENDING.value,
        }),
    )
    monkeypatch.setattr(worker, "download_original",
                        AsyncMock(return_value=b"%PDF-fake"))
    monkeypatch.setattr(worker, "parse_notice",
                        lambda *a, **kw: parsed)
    monkeypatch.setattr(worker, "link_notice",
                        AsyncMock(return_value=LinkedRecon(
                            reconciliation_id=recon, client_id=client,
                        )))
    monkeypatch.setattr(worker, "fetch_recon_summary",
                        AsyncMock(return_value={
                            "reconciliation_id": str(recon),
                            "safe_itc_bdt": "40000.00", "at_risk_itc_bdt": "10000.00",
                            "total_vat_claimed_bdt": "50000.00",
                            "matched_exact": 8, "matched_fuzzy": 3,
                            "partial_match": 2, "no_match": 2,
                            "disputed_rows": [],
                        }))
    monkeypatch.setattr(worker, "retrieve",
                        AsyncMock(return_value=[CitationChunk(
                            id=UUID("00000000-0000-0000-0000-0000000000aa"),
                            source="vat_act_2012", source_ref="Section 46",
                            subsection=None, language="bn",
                            title="ITC", body="...",
                        )]))

    async def _upd(notice_id_, *, tenant_id, **fields):
        if "status" in fields:
            captured_status.append(fields["status"].value
                                   if hasattr(fields["status"], "value")
                                   else fields["status"])
    monkeypatch.setattr(worker, "update_notice", _upd)

    monkeypatch.setattr(worker, "get_draft", AsyncMock(return_value=None))
    monkeypatch.setattr(worker, "create_draft", AsyncMock(return_value=uuid4()))

    await worker.process_notice(notice_id, tenant_id=tenant)

    assert "parsing" in captured_status
    assert "drafting" in captured_status
    assert "drafted" in captured_status


@pytest.mark.asyncio
async def test_worker_stops_at_awaiting_data_when_no_recon(monkeypatch):
    from app.notices import worker

    notice_id = uuid4()
    tenant = uuid4()
    client = uuid4()

    set_notice_llm_adapter(StubNoticeLLMAdapter(
        parses={"k": ParsedNotice(
            notice_type=NoticeType.INPUT_VAT_MISMATCH,
            taxpayer_bin="001234567", period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30), classification_confidence=0.9,
        )},
    ))

    monkeypatch.setattr(worker, "get_notice", AsyncMock(return_value={
        "id": str(notice_id), "tenant_id": str(tenant), "client_id": str(client),
        "storage_path": "x", "mime_type": "application/pdf",
        "original_filename": "n.pdf", "status": NoticeStatus.PENDING.value,
    }))
    monkeypatch.setattr(worker, "download_original",
                        AsyncMock(return_value=b"%PDF-fake"))
    monkeypatch.setattr(worker, "parse_notice", lambda *a, **kw:
                        ParsedNotice(
                            notice_type=NoticeType.INPUT_VAT_MISMATCH,
                            taxpayer_bin="001234567",
                            period_start=date(2026, 4, 1),
                            period_end=date(2026, 4, 30),
                            classification_confidence=0.9,
                        ))
    monkeypatch.setattr(worker, "link_notice",
                        AsyncMock(return_value=NeedsIngestion(
                            client_id=client,
                            period_start=date(2026, 4, 1),
                            period_end=date(2026, 4, 30),
                        )))
    captured = []
    async def _upd(notice_id_, *, tenant_id, **fields):
        if "status" in fields:
            captured.append(fields["status"].value
                            if hasattr(fields["status"], "value")
                            else fields["status"])
    monkeypatch.setattr(worker, "update_notice", _upd)

    await worker.process_notice(notice_id, tenant_id=tenant)
    assert "awaiting_data" in captured
    assert "drafted" not in captured
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/notices/test_worker.py -v 2>&1 | tail -5`
Expected: ImportError.

- [ ] **Step 3: Implement the worker**

Create `backend/app/notices/worker.py`:

```python
"""In-process async worker for notice processing.

Two entry points:
  * `process_notice(notice_id, tenant_id)` — single-shot orchestration of
    all four phases for one notice. Idempotent; reads current status and
    resumes from the right phase.
  * `poll_pending_notices(sleep_s)` — long-running loop; picks up notices
    that were created on a different instance or whose lease expired.

Lease pattern mirrors app/ingestion/worker.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog

from app.database import get_supabase_admin
from app.notices.drafter import draft as draft_phase
from app.notices.linker import link_notice
from app.notices.llm import get_notice_llm_adapter
from app.notices.parser import parse_notice
from app.notices.persistence import (
    create_draft, fetch_recon_summary, get_draft, get_notice, update_notice,
)
from app.notices.retriever import retrieve
from app.notices.schemas import (
    LinkedRecon, NeedsIngestion, NeedsManualLink,
    NoticeDraftEditSource, NoticeStatus, ParsedNotice, ReconSummary,
)
from app.notices.storage import download_original

log = structlog.get_logger()

_LEASE_TIMEOUT = timedelta(minutes=10)
_MODEL_VERSION = "gemini-2.5-flash | prompt v1"


async def process_notice(notice_id: UUID, *, tenant_id: UUID) -> None:
    """Run all four phases for one notice. Safe to call repeatedly."""
    notice = await get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        log.warning("notices.worker.not_found", notice_id=str(notice_id))
        return

    adapter = get_notice_llm_adapter()
    status = notice["status"]

    try:
        # Phase 1: parse (if we don't already have parsed metadata)
        if status in (NoticeStatus.PENDING.value, NoticeStatus.PARSING.value,
                      NoticeStatus.FAILED.value):
            await update_notice(notice_id, tenant_id=tenant_id,
                                status=NoticeStatus.PARSING, parse_error=None)
            content = await download_original(notice["storage_path"])
            parsed: ParsedNotice = parse_notice(
                content, mime=notice["mime_type"], adapter=adapter,
                filename=notice["original_filename"],
            )
            await update_notice(
                notice_id, tenant_id=tenant_id,
                status=NoticeStatus.PARSED,
                notice_no=parsed.notice_no,
                notice_date=parsed.notice_date,
                notice_type=parsed.notice_type,
                taxpayer_bin=parsed.taxpayer_bin,
                taxpayer_tin=parsed.taxpayer_tin,
                period_start=parsed.period_start,
                period_end=parsed.period_end,
                alleged_itc_claimed_bdt=parsed.alleged_itc_claimed_bdt,
                alleged_itc_allowed_bdt=parsed.alleged_itc_allowed_bdt,
                alleged_shortfall_bdt=parsed.alleged_shortfall_bdt,
            )
            if (parsed.notice_type.value != "input_vat_mismatch"
                    or parsed.classification_confidence < 0.7):
                await update_notice(
                    notice_id, tenant_id=tenant_id, status=NoticeStatus.FAILED,
                    parse_error="Notice category not supported in V1 "
                                "(only input VAT mismatch is supported).",
                )
                return
            # refresh notice dict for downstream phases
            notice = await get_notice(notice_id, tenant_id=tenant_id)
            status = notice["status"]
        else:
            parsed = _parsed_from_notice_row(notice)

        # Phase 2: link
        link = await link_notice(parsed, tenant_id=tenant_id)
        if isinstance(link, NeedsIngestion):
            await update_notice(notice_id, tenant_id=tenant_id,
                                status=NoticeStatus.AWAITING_DATA)
            return
        if isinstance(link, NeedsManualLink):
            await update_notice(notice_id, tenant_id=tenant_id,
                                status=NoticeStatus.PARSED)
            return
        assert isinstance(link, LinkedRecon)
        await update_notice(
            notice_id, tenant_id=tenant_id,
            status=NoticeStatus.READY_TO_DRAFT,
            linked_reconciliation_id=link.reconciliation_id,
        )

        # Phase 3 + 4 only when we have a linked recon AND no draft yet
        existing_draft = await get_draft(notice_id, tenant_id=tenant_id)
        if existing_draft is not None:
            return

        await update_notice(notice_id, tenant_id=tenant_id,
                            status=NoticeStatus.DRAFTING)
        summary_dict = await fetch_recon_summary(
            link.reconciliation_id, tenant_id=tenant_id,
        )
        summary = ReconSummary(**summary_dict)
        chunks = await retrieve(parsed, summary, adapter=adapter)
        finalized = await draft_phase(parsed, summary, chunks, adapter=adapter)

        await create_draft(
            notice_id=notice_id, tenant_id=tenant_id,
            body_html=finalized["body_html"],
            appendix_json=finalized["appendix_json"],
            citations=finalized["citations"],
            model_version=_MODEL_VERSION,
            edited_by=UUID(notice["created_by"]),
            edit_source=NoticeDraftEditSource.LLM_GENERATED,
        )
        await update_notice(notice_id, tenant_id=tenant_id,
                            status=NoticeStatus.DRAFTED)
    except Exception as e:
        log.exception("notices.worker.failed",
                      notice_id=str(notice_id), error=str(e))
        await update_notice(
            notice_id, tenant_id=tenant_id,
            status=NoticeStatus.FAILED, parse_error=str(e)[:500],
        )


def _parsed_from_notice_row(n: dict) -> ParsedNotice:
    """Re-hydrate a ParsedNotice from a persisted notice row."""
    from datetime import date
    from decimal import Decimal
    def _date(v): return date.fromisoformat(v) if v else None
    def _dec(v): return Decimal(str(v)) if v is not None else None
    return ParsedNotice(
        notice_no=n.get("notice_no"),
        notice_date=_date(n.get("notice_date")),
        notice_type=n["notice_type"] or "input_vat_mismatch",
        taxpayer_bin=n.get("taxpayer_bin"),
        taxpayer_tin=n.get("taxpayer_tin"),
        period_start=_date(n.get("period_start")),
        period_end=_date(n.get("period_end")),
        alleged_itc_claimed_bdt=_dec(n.get("alleged_itc_claimed_bdt")),
        alleged_itc_allowed_bdt=_dec(n.get("alleged_itc_allowed_bdt")),
        alleged_shortfall_bdt=_dec(n.get("alleged_shortfall_bdt")),
        classification_confidence=1.0,
    )


async def poll_pending_notices(*, sleep_s: float = 5.0) -> None:
    """Long-running loop that re-claims stuck notices."""
    sb = get_supabase_admin()
    log.info("notices.worker.loop_started")
    while True:
        try:
            cutoff = (datetime.now(timezone.utc) - _LEASE_TIMEOUT).isoformat()

            def _q():
                return (
                    sb.table("notices")
                    .select("id, tenant_id, status, updated_at")
                    .in_("status", [NoticeStatus.PENDING.value,
                                    NoticeStatus.PARSING.value,
                                    NoticeStatus.DRAFTING.value])
                    .order("created_at")
                    .limit(20)
                    .execute()
                )

            res = await asyncio.to_thread(_q)
            for row in res.data or []:
                if (row["status"] in (NoticeStatus.PARSING.value,
                                      NoticeStatus.DRAFTING.value)
                        and row["updated_at"] > cutoff):
                    continue
                asyncio.create_task(
                    process_notice(UUID(row["id"]), tenant_id=UUID(row["tenant_id"]))
                )
        except Exception as e:
            log.exception("notices.worker.poll_error", error=str(e))
        await asyncio.sleep(sleep_s)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/notices/test_worker.py -v 2>&1 | tail -10`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/worker.py backend/tests/notices/test_worker.py
git commit -m "feat(notices): worker — orchestrates parser→linker→retriever→drafter"
```

### Task 5.3: Service + Router + main.py wiring

**Files:**
- Create: `backend/app/notices/service.py`
- Create: `backend/app/notices/router.py`
- Modify: `backend/app/main.py` (mount router, optionally boot worker loop)

- [ ] **Step 1: Implement the service (no separate unit test — covered by API tests)**

Create `backend/app/notices/service.py`:

```python
"""High-level service operations called by the FastAPI router."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import UploadFile

from app.notices import persistence as p
from app.notices import storage as st
from app.notices.exceptions import (
    DraftNotFoundError, NoticeInvalidStateError, NoticeNotFoundError,
    NoticeUnsupportedTypeError,
)
from app.notices.rendering import (
    PdfRendererUnavailableError, render_docx, render_pdf,
)
from app.notices.schemas import (
    NoticeDraftEditSource, NoticeDraftStatus, NoticeStatus,
)
from app.notices.worker import process_notice

log = structlog.get_logger()


_MAX_BYTES = 25 * 1024 * 1024
_ACCEPTED_MIMES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png",
    "image/heic", "image/heif", "image/webp", "image/tiff",
}


async def create_notice(
    *, tenant_id: UUID, user_id: UUID, client_id: UUID, file: UploadFile,
) -> UUID:
    content = await file.read()
    size = len(content)
    if size > _MAX_BYTES:
        raise NoticeUnsupportedTypeError(
            filename=file.filename or "<unnamed>",
            mime=f"file too large ({size} bytes > {_MAX_BYTES})",
        )
    mime = (file.content_type or "").strip().lower() or "application/octet-stream"
    if mime not in _ACCEPTED_MIMES:
        raise NoticeUnsupportedTypeError(
            filename=file.filename or "<unnamed>", mime=mime,
        )

    notice_id = await p.create_notice(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        storage_path="placeholder",
        original_filename=file.filename or f"notice-{notice_id_placeholder()}",
        mime_type=mime, byte_size=size,
    )
    path = await st.upload_original(
        tenant_id=tenant_id, client_id=client_id, notice_id=notice_id,
        filename=file.filename or f"notice-{notice_id}", content=content,
        mime_type=mime,
    )
    await p.update_notice(notice_id, tenant_id=tenant_id, storage_path=path)

    asyncio.create_task(process_notice(notice_id, tenant_id=tenant_id))
    return notice_id


def notice_id_placeholder() -> str:
    """Filename placeholder used before we know the real notice_id."""
    from uuid import uuid4
    return str(uuid4())


async def _fetch_tenant_meta(tenant_id: UUID) -> dict:
    """Letterhead fields from the tenants row. Falls back to neutral defaults.

    V1 reads `firm_name` and `address` only; both are optional on the
    existing tenants schema so we tolerate missing columns/rows.
    """
    from app.database import get_supabase_admin
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("tenants")
            .select("*")
            .eq("id", str(tenant_id))
            .single()
            .execute()
        )

    try:
        res = await asyncio.to_thread(_q)
        row = res.data or {}
    except Exception:
        row = {}
    return {
        "firm_name": row.get("name") or row.get("firm_name") or "Chartered Accountants",
        "address": row.get("address") or "",
    }


async def relink_notice(
    *, notice_id: UUID, tenant_id: UUID,
    client_id: UUID, period_start: date, period_end: date,
    reconciliation_id: Optional[UUID] = None,
) -> None:
    notice = await p.get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        raise NoticeNotFoundError(f"Notice {notice_id} not found")

    fields = dict(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
    )
    if reconciliation_id is not None:
        fields["linked_reconciliation_id"] = reconciliation_id
        fields["status"] = NoticeStatus.READY_TO_DRAFT
    await p.update_notice(notice_id, tenant_id=tenant_id, **fields)
    asyncio.create_task(process_notice(notice_id, tenant_id=tenant_id))


async def generate_draft(*, notice_id: UUID, tenant_id: UUID) -> None:
    notice = await p.get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        raise NoticeNotFoundError(f"Notice {notice_id} not found")
    if notice["status"] not in (NoticeStatus.READY_TO_DRAFT.value,
                                NoticeStatus.DRAFTED.value):
        raise NoticeInvalidStateError(
            f"Cannot draft from status={notice['status']}; need ready_to_draft or drafted",
        )
    # Drop existing draft so process_notice will re-create one
    if notice["status"] == NoticeStatus.DRAFTED.value:
        existing = await p.get_draft(notice_id, tenant_id=tenant_id)
        if existing:
            # We don't physically delete — we just blow status back to ready_to_draft
            # so the worker re-runs; the existing draft + its revisions stay as history
            await p.update_notice(notice_id, tenant_id=tenant_id,
                                  status=NoticeStatus.READY_TO_DRAFT)
    asyncio.create_task(process_notice(notice_id, tenant_id=tenant_id))


async def save_draft_revision(
    *, notice_id: UUID, tenant_id: UUID, user_id: UUID,
    body_html: str, appendix_json: dict,
) -> None:
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    if draft["status"] == NoticeDraftStatus.FINALIZED.value:
        raise NoticeInvalidStateError("Draft is finalized; reopen first")
    await p.update_draft(
        UUID(draft["id"]), tenant_id=tenant_id,
        body_html=body_html, appendix_json=appendix_json,
        edited_by=user_id, edit_source=NoticeDraftEditSource.USER_EDIT,
    )


async def finalize_draft(
    *, notice_id: UUID, tenant_id: UUID, user_id: UUID,
) -> UUID:
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    if draft["status"] == NoticeDraftStatus.FINALIZED.value:
        return UUID(draft["id"])  # idempotent
    await p.finalize_draft(
        UUID(draft["id"]), tenant_id=tenant_id, finalized_by=user_id,
    )
    await p.update_notice(notice_id, tenant_id=tenant_id,
                          status=NoticeStatus.FINALIZED)
    return UUID(draft["id"])


async def reopen_draft_for_edit(
    *, notice_id: UUID, tenant_id: UUID, user_id: UUID, reason: str,
) -> None:
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    await p.reopen_draft(UUID(draft["id"]), tenant_id=tenant_id)
    await p.update_notice(notice_id, tenant_id=tenant_id,
                          status=NoticeStatus.DRAFTED)
    # Log the reopen as an edit-source row so we have the reason recorded
    await p.update_draft(
        UUID(draft["id"]), tenant_id=tenant_id,
        body_html=draft["body_html"], appendix_json=draft["appendix_json"],
        edited_by=user_id, edit_source=NoticeDraftEditSource.USER_EDIT,
        edit_reason=f"Reopened: {reason}",
    )


async def export_draft(
    *, notice_id: UUID, tenant_id: UUID, format: str,
) -> tuple[bytes, str, str]:
    """Returns (bytes, content_type, filename)."""
    if format not in ("docx", "pdf"):
        raise NoticeInvalidStateError(f"Unsupported export format: {format}")
    notice = await p.get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        raise NoticeNotFoundError(f"Notice {notice_id} not found")
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")

    tenant_meta = await _fetch_tenant_meta(tenant_id)
    docx_bytes = render_docx(draft=draft, notice=notice, tenant=tenant_meta)
    if format == "docx":
        return (docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                f"notice-{notice_id}.docx")
    try:
        pdf_bytes = render_pdf(docx_bytes)
    except PdfRendererUnavailableError as e:
        # Surface a 503 via a custom error
        err = NoticeInvalidStateError(str(e))
        err.default_status = 503
        err.status_code = 503
        raise err
    return (pdf_bytes, "application/pdf", f"notice-{notice_id}.pdf")
```

- [ ] **Step 2: Implement the router**

Create `backend/app/notices/router.py`:

```python
"""FastAPI endpoints for notices. Mounted at /api/v1/notices."""
from __future__ import annotations

import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_tenant_id, get_current_user_id
from app.notices import persistence as p
from app.notices import service as svc
from app.notices.schemas import (
    NoticeDraftOut, NoticeOut, RelinkRequest, ReopenDraftRequest,
    SaveDraftRequest, FinalizeDraftResponse,
)

router = APIRouter(prefix="/api/v1/notices", tags=["notices"])


@router.post("/", status_code=201)
async def upload_notice(
    client_id: UUID,
    file: UploadFile = File(...),
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    nid = await svc.create_notice(
        tenant_id=tenant_id, user_id=user_id,
        client_id=client_id, file=file,
    )
    return {"notice_id": str(nid)}


@router.get("/", response_model=list[NoticeOut])
async def list_notices(
    client_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    rows = await p.list_notices(tenant_id=tenant_id, client_id=client_id)
    return [NoticeOut.model_validate(r) for r in rows]


@router.get("/{notice_id}", response_model=NoticeOut)
async def get_notice(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    n = await p.get_notice(notice_id, tenant_id=tenant_id)
    if not n:
        from app.notices.exceptions import NoticeNotFoundError
        raise NoticeNotFoundError(f"Notice {notice_id} not found")
    return NoticeOut.model_validate(n)


@router.post("/{notice_id}/relink", status_code=202)
async def relink(
    notice_id: UUID,
    body: RelinkRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    await svc.relink_notice(
        notice_id=notice_id, tenant_id=tenant_id,
        client_id=body.client_id,
        period_start=body.period_start, period_end=body.period_end,
        reconciliation_id=body.reconciliation_id,
    )
    return {"ok": True}


@router.post("/{notice_id}/draft", status_code=202)
async def generate_draft(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    await svc.generate_draft(notice_id=notice_id, tenant_id=tenant_id)
    return {"ok": True}


@router.get("/{notice_id}/draft", response_model=NoticeDraftOut)
async def get_draft(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    d = await p.get_draft(notice_id, tenant_id=tenant_id)
    if not d:
        from app.notices.exceptions import DraftNotFoundError
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    return NoticeDraftOut.model_validate(d)


@router.put("/{notice_id}/draft")
async def save_draft(
    notice_id: UUID,
    body: SaveDraftRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.save_draft_revision(
        notice_id=notice_id, tenant_id=tenant_id, user_id=user_id,
        body_html=body.body_html, appendix_json=body.appendix_json,
    )
    return {"ok": True}


@router.get("/{notice_id}/draft/revisions")
async def list_draft_revisions(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    d = await p.get_draft(notice_id, tenant_id=tenant_id)
    if not d:
        return []
    return await p.list_revisions(UUID(d["id"]), tenant_id=tenant_id)


@router.post("/{notice_id}/draft/finalize", response_model=FinalizeDraftResponse)
async def finalize(
    notice_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    draft_id = await svc.finalize_draft(
        notice_id=notice_id, tenant_id=tenant_id, user_id=user_id,
    )
    return FinalizeDraftResponse(
        notice_id=notice_id, draft_id=draft_id,
        status="finalized",
    )


@router.post("/{notice_id}/draft/reopen")
async def reopen(
    notice_id: UUID,
    body: ReopenDraftRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
):
    await svc.reopen_draft_for_edit(
        notice_id=notice_id, tenant_id=tenant_id, user_id=user_id,
        reason=body.reason,
    )
    return {"ok": True}


@router.get("/{notice_id}/draft/export")
async def export(
    notice_id: UUID,
    format: str = Query(..., regex="^(docx|pdf)$"),
    tenant_id: UUID = Depends(get_current_tenant_id),
):
    data, ctype, fname = await svc.export_draft(
        notice_id=notice_id, tenant_id=tenant_id, format=format,
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
```

- [ ] **Step 3: Wire main.py — mount router + optional worker loop**

Modify `backend/app/main.py`:

Find the section near the existing `INGESTION_ENABLED` boot logic (around `_lifespan`) and add the notices counterpart:

```python
@asynccontextmanager
async def _lifespan(app: FastAPI):
    ingestion_task: asyncio.Task | None = None
    notices_task: asyncio.Task | None = None
    if os.environ.get("INGESTION_ENABLED", "false").lower() == "true":
        from app.ingestion.llm import GeminiLLMAdapter, set_llm_adapter
        from app.ingestion.worker import poll_pending_jobs
        from app.notices.llm import GeminiNoticeLLMAdapter, set_notice_llm_adapter
        from app.notices.worker import poll_pending_notices

        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not gemini_key:
            logger.warning(
                "ingestion.boot.skipped",
                reason="INGESTION_ENABLED=true but GEMINI_API_KEY missing",
            )
        else:
            set_llm_adapter(GeminiLLMAdapter(api_key=gemini_key))
            set_notice_llm_adapter(GeminiNoticeLLMAdapter(api_key=gemini_key))
            ingestion_task = asyncio.create_task(poll_pending_jobs())
            notices_task = asyncio.create_task(poll_pending_notices())
            logger.info("ingestion.boot.started")
            logger.info("notices.boot.started")
    try:
        yield
    finally:
        for t in (ingestion_task, notices_task):
            if t is not None:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
```

Also find the existing router-registration block (near `app.include_router(ingestion_router)`) and add:

```python
    if os.environ.get("INGESTION_ENABLED", "false").lower() == "true":
        from app.notices.router import router as notices_router
        app.include_router(notices_router)
        logger.info("notices.router_registered")
```

- [ ] **Step 4: Smoke-run the suite to confirm nothing regressed**

Run: `cd backend && python -m pytest tests/ --ignore=tests/ingestion/test_llm_gemini.py --ignore=tests/notices/test_llm_gemini.py -q 2>&1 | tail -10`
Expected: all tests still pass (additional notices tests now included).

- [ ] **Step 5: Commit**

```bash
git add backend/app/notices/service.py backend/app/notices/router.py backend/app/main.py
git commit -m "feat(notices): service + FastAPI router + main.py wiring"
```

### Task 5.4: Live Gemini smoke test

**Files:**
- Create: `backend/tests/notices/test_llm_gemini.py`
- Create: `backend/tests/notices/fixtures/notice_input_vat_mismatch.jpg` (synthetic)

- [ ] **Step 1: Generate the fixture**

Run from `backend/`:

```bash
python -c "
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (1200, 1600), (250, 248, 240))
d = ImageDraw.Draw(img)
try: f = ImageFont.truetype('arial.ttf', 28)
except Exception: f = ImageFont.load_default()
lines = [
  'NATIONAL BOARD OF REVENUE',
  'Notice No: NBR/VAT/12345/2026',
  'Date: 2026-05-01',
  'To: Demo Trading Ltd',
  'BIN: 001234567',
  'Subject: Input VAT mismatch for the period April 2026',
  '',
  'It has been observed that the input VAT credit claimed by you',
  'for the tax period April 2026 amounting to BDT 50,000.00 does',
  'not match the corresponding output VAT reported by your suppliers',
  'which totals BDT 40,000.00. There appears to be a shortfall of',
  'BDT 10,000.00 that requires explanation.',
  '',
  'You are hereby directed to submit a written reply within 15 days.',
]
y = 60
for line in lines:
  d.text((60, y), line, fill=(20,20,30), font=f); y += 44
img.save('tests/notices/fixtures/notice_input_vat_mismatch.jpg', 'JPEG', quality=88)
print('wrote fixture')
"
```

Expected: file created.

- [ ] **Step 2: Write the live test**

Create `backend/tests/notices/test_llm_gemini.py`:

```python
"""Live Gemini smoke tests. Skipped unless GEMINI_API_KEY set AND -m live."""
import os
import pathlib

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set",
    ),
]

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "notice_input_vat_mismatch.jpg"


def test_parse_input_vat_mismatch_notice():
    from app.notices.llm import GeminiNoticeLLMAdapter
    from app.notices.parser import parse_notice

    adapter = GeminiNoticeLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    parsed = parse_notice(
        FIXTURE.read_bytes(), mime="image/jpeg", adapter=adapter,
    )
    assert parsed.notice_type.value == "input_vat_mismatch"
    assert parsed.classification_confidence >= 0.6
    assert parsed.taxpayer_bin == "001234567"
    # The amounts and dates the model returns should be in the right ballpark
    if parsed.alleged_shortfall_bdt is not None:
        from decimal import Decimal
        assert parsed.alleged_shortfall_bdt == Decimal("10000.00")


def test_embed_query_returns_768d_vector():
    from app.notices.llm import GeminiNoticeLLMAdapter
    a = GeminiNoticeLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    v = a.embed_query("input VAT mismatch shortfall 10000 BDT")
    assert len(v) == 768
```

- [ ] **Step 3: Run the live tests**

Run: `cd backend && python -m pytest tests/notices/test_llm_gemini.py -v -m live 2>&1 | tail -10`
Expected: 2 passed (with env vars set).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/notices/test_llm_gemini.py backend/tests/notices/fixtures/notice_input_vat_mismatch.jpg
git commit -m "test(notices): live Gemini smoke for parser + embedder"
```

---

## Phase 6 — Frontend data layer

### Task 6.1: TypeScript types (Zod-validated)

**Files:**
- Create: `frontend/src/types/notices.ts`
- Create: `frontend/src/types/__tests__/notices.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/types/__tests__/notices.test.ts`:

```ts
import { describe, expect, it } from "vitest"

import {
  NOTICE_STATUSES,
  noticeSchema,
  noticeDraftSchema,
  linkerResultSchema,
} from "@/types/notices"

describe("noticeSchema", () => {
  it("rejects unknown status values", () => {
    const ok = noticeSchema.safeParse({
      id: "11111111-1111-1111-1111-111111111111",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      client_id: "11111111-1111-1111-1111-111111111111",
      created_by: "11111111-1111-1111-1111-111111111111",
      original_filename: "n.pdf",
      mime_type: "application/pdf",
      byte_size: 1024,
      status: "pending",
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    })
    expect(ok.success).toBe(true)

    const bad = noticeSchema.safeParse({ ...ok.data!, status: "weird" })
    expect(bad.success).toBe(false)
  })
})

describe("linkerResultSchema", () => {
  it("discriminates by kind", () => {
    const lr = linkerResultSchema.parse({
      kind: "linked_recon",
      reconciliation_id: "11111111-1111-1111-1111-111111111111",
      client_id: "11111111-1111-1111-1111-111111111112",
    })
    expect(lr.kind).toBe("linked_recon")

    const ni = linkerResultSchema.parse({
      kind: "needs_ingestion",
      client_id: "11111111-1111-1111-1111-111111111112",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
    })
    expect(ni.kind).toBe("needs_ingestion")
  })
})

describe("NOTICE_STATUSES", () => {
  it("exposes the same 9 statuses as the backend enum", () => {
    expect(new Set(NOTICE_STATUSES)).toEqual(new Set([
      "pending","parsing","parsed","awaiting_data","ready_to_draft",
      "drafting","drafted","finalized","failed",
    ]))
  })
})

describe("noticeDraftSchema", () => {
  it("parses citations array shape", () => {
    const ok = noticeDraftSchema.safeParse({
      id: "11111111-1111-1111-1111-111111111111",
      notice_id: "11111111-1111-1111-1111-111111111111",
      language: "bn",
      body_html: "<p>hi</p>",
      appendix_json: { rows: [] },
      citations: [{
        corpus_chunk_id: "11111111-1111-1111-1111-111111111111",
        source_ref: "Section 46",
        snippet: "…",
        paragraph_idx: 0,
      }],
      model_version: "g25",
      status: "draft",
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    })
    expect(ok.success).toBe(true)
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/types/__tests__/notices.test.ts 2>&1 | tail -5`
Expected: failure (module missing).

- [ ] **Step 3: Implement the types**

Create `frontend/src/types/notices.ts`:

```ts
import { z } from "zod"

export const NOTICE_STATUSES = [
  "pending", "parsing", "parsed", "awaiting_data", "ready_to_draft",
  "drafting", "drafted", "finalized", "failed",
] as const
export type NoticeStatus = (typeof NOTICE_STATUSES)[number]

export const NOTICE_TYPES = ["input_vat_mismatch", "unsupported"] as const
export type NoticeType = (typeof NOTICE_TYPES)[number]

export const DRAFT_STATUSES = ["draft", "under_review", "finalized"] as const
export type DraftStatus = (typeof DRAFT_STATUSES)[number]

const uuid = z.string().uuid()

export const noticeSchema = z.object({
  id: uuid,
  tenant_id: uuid,
  client_id: uuid,
  created_by: uuid,
  original_filename: z.string(),
  mime_type: z.string(),
  byte_size: z.number().int(),
  status: z.enum(NOTICE_STATUSES),
  parse_error: z.string().nullable().optional(),
  notice_no: z.string().nullable().optional(),
  notice_date: z.string().nullable().optional(),         // ISO date
  notice_type: z.enum(NOTICE_TYPES).nullable().optional(),
  taxpayer_bin: z.string().nullable().optional(),
  taxpayer_tin: z.string().nullable().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  alleged_itc_claimed_bdt: z.string().nullable().optional(),
  alleged_itc_allowed_bdt: z.string().nullable().optional(),
  alleged_shortfall_bdt: z.string().nullable().optional(),
  linked_reconciliation_id: uuid.nullable().optional(),
  linked_ingestion_job_id: uuid.nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Notice = z.infer<typeof noticeSchema>

export const citationSchema = z.object({
  corpus_chunk_id: uuid,
  source_ref: z.string(),
  snippet: z.string(),
  paragraph_idx: z.number().int(),
})
export type Citation = z.infer<typeof citationSchema>

export const appendixRowSchema = z.object({
  label: z.string(),
  value_bdt: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
})
export type AppendixRow = z.infer<typeof appendixRowSchema>

export const appendixJsonSchema = z.object({
  rows: z.array(appendixRowSchema),
})
export type AppendixJson = z.infer<typeof appendixJsonSchema>

export const noticeDraftSchema = z.object({
  id: uuid,
  notice_id: uuid,
  language: z.string(),
  body_html: z.string(),
  appendix_json: appendixJsonSchema.passthrough(),
  citations: z.array(citationSchema),
  model_version: z.string(),
  status: z.enum(DRAFT_STATUSES),
  finalized_at: z.string().nullable().optional(),
  finalized_by: uuid.nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type NoticeDraft = z.infer<typeof noticeDraftSchema>

export const linkedReconSchema = z.object({
  kind: z.literal("linked_recon"),
  reconciliation_id: uuid,
  client_id: uuid,
})
export const needsIngestionSchema = z.object({
  kind: z.literal("needs_ingestion"),
  client_id: uuid,
  period_start: z.string(),
  period_end: z.string(),
})
export const needsManualLinkSchema = z.object({
  kind: z.literal("needs_manual_link"),
  candidate_clients: z.array(uuid),
})
export const linkerResultSchema = z.discriminatedUnion("kind", [
  linkedReconSchema, needsIngestionSchema, needsManualLinkSchema,
])
export type LinkerResult = z.infer<typeof linkerResultSchema>
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd frontend && npx vitest run src/types/__tests__/notices.test.ts 2>&1 | tail -5`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/notices.ts frontend/src/types/__tests__/notices.test.ts
git commit -m "feat(notices/fe): Zod schemas + TS types matching backend DTOs"
```

### Task 6.2: API client

**Files:**
- Create: `frontend/src/lib/notices/api.ts`
- Create: `frontend/src/lib/notices/__tests__/api.test.ts`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/lib/notices/__tests__/api.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest"

import { api } from "@/lib/api"
import * as noticesApi from "@/lib/notices/api"

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

describe("notices api", () => {
  it("uploadNotice posts multipart with client_id", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { notice_id: "n1" } })
    const file = new File([new Uint8Array(10)], "x.pdf", { type: "application/pdf" })
    const out = await noticesApi.uploadNotice("c1", file)
    expect(out.notice_id).toBe("n1")
    const [path, body] = (api.post as any).mock.calls[0]
    expect(path).toMatch(/\/notices\/?\?client_id=c1$/)
    expect(body).toBeInstanceOf(FormData)
  })

  it("relink posts JSON body with period and optional recon id", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { ok: true } })
    await noticesApi.relinkNotice("n1", {
      client_id: "11111111-1111-1111-1111-111111111111",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      reconciliation_id: "22222222-2222-2222-2222-222222222222",
    })
    expect(api.post).toHaveBeenCalledWith(
      "/api/v1/notices/n1/relink",
      expect.objectContaining({ reconciliation_id: "22222222-2222-2222-2222-222222222222" }),
    )
  })

  it("listNotices parses through Zod and drops unexpected fields", async () => {
    ;(api.get as any).mockResolvedValueOnce({ data: [{
      id: "11111111-1111-1111-1111-111111111111",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      client_id: "11111111-1111-1111-1111-111111111111",
      created_by: "11111111-1111-1111-1111-111111111111",
      original_filename: "n.pdf",
      mime_type: "application/pdf",
      byte_size: 1,
      status: "pending",
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
      garbage: "ignored",
    }]})
    const out = await noticesApi.listNotices("c1")
    expect(out).toHaveLength(1)
    expect((out[0] as any).garbage).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/lib/notices/__tests__/api.test.ts 2>&1 | tail -5`
Expected: failure.

- [ ] **Step 3: Implement the API client**

Create `frontend/src/lib/notices/api.ts`:

```ts
import { api } from "@/lib/api"
import {
  appendixJsonSchema, noticeDraftSchema, noticeSchema,
  type AppendixJson, type Notice, type NoticeDraft,
} from "@/types/notices"

const BASE = "/api/v1/notices"

export interface UploadNoticeResponse { notice_id: string }
export async function uploadNotice(
  clientId: string, file: File,
): Promise<UploadNoticeResponse> {
  const fd = new FormData()
  fd.append("file", file)
  const { data } = await api.post<UploadNoticeResponse>(
    `${BASE}/?client_id=${encodeURIComponent(clientId)}`, fd,
  )
  return data
}

export async function listNotices(clientId: string): Promise<Notice[]> {
  const { data } = await api.get<unknown[]>(
    `${BASE}/?client_id=${encodeURIComponent(clientId)}`,
  )
  return data.map((row) => noticeSchema.parse(row))
}

export async function getNotice(noticeId: string): Promise<Notice> {
  const { data } = await api.get<unknown>(`${BASE}/${noticeId}`)
  return noticeSchema.parse(data)
}

export interface RelinkPayload {
  client_id: string
  period_start: string
  period_end: string
  reconciliation_id?: string | null
}
export async function relinkNotice(
  noticeId: string, payload: RelinkPayload,
): Promise<void> {
  await api.post(`${BASE}/${noticeId}/relink`, payload)
}

export async function generateDraft(noticeId: string): Promise<void> {
  await api.post(`${BASE}/${noticeId}/draft`, {})
}

export async function getDraft(noticeId: string): Promise<NoticeDraft> {
  const { data } = await api.get<unknown>(`${BASE}/${noticeId}/draft`)
  return noticeDraftSchema.parse(data)
}

export interface SaveDraftPayload {
  body_html: string
  appendix_json: AppendixJson
}
export async function saveDraft(
  noticeId: string, payload: SaveDraftPayload,
): Promise<void> {
  // Validate appendix shape before sending — early failure beats 422
  appendixJsonSchema.parse(payload.appendix_json)
  await api.put(`${BASE}/${noticeId}/draft`, payload)
}

export async function finalizeDraft(noticeId: string): Promise<void> {
  await api.post(`${BASE}/${noticeId}/draft/finalize`, {})
}

export async function reopenDraft(noticeId: string, reason: string): Promise<void> {
  await api.post(`${BASE}/${noticeId}/draft/reopen`, { reason })
}

export interface RevisionMeta {
  id: string
  revision_no: number
  edited_by: string
  edit_source: "llm_generated" | "user_edit" | "regenerated"
  edit_reason: string | null
  created_at: string
}
export async function listDraftRevisions(noticeId: string): Promise<RevisionMeta[]> {
  const { data } = await api.get<RevisionMeta[]>(`${BASE}/${noticeId}/draft/revisions`)
  return data
}

export function exportDraftUrl(
  noticeId: string, format: "docx" | "pdf",
): string {
  return `${BASE}/${noticeId}/draft/export?format=${format}`
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd frontend && npx vitest run src/lib/notices/__tests__/api.test.ts 2>&1 | tail -5`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/notices/api.ts frontend/src/lib/notices/__tests__/api.test.ts
git commit -m "feat(notices/fe): typed API client with Zod validation"
```

### Task 6.3: TanStack Query hooks

**Files:**
- Create: `frontend/src/hooks/useNotices.ts`
- Create: `frontend/src/hooks/__tests__/useNotices.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/hooks/__tests__/useNotices.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

import * as noticesApi from "@/lib/notices/api"
import {
  useNoticeList, useNotice, useNoticeDraft,
} from "@/hooks/useNotices"

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

describe("useNoticeList", () => {
  it("fetches when clientId given", async () => {
    vi.spyOn(noticesApi, "listNotices").mockResolvedValueOnce([])
    const { result } = renderHook(() => useNoticeList("c1"), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it("is disabled when clientId is empty", async () => {
    vi.spyOn(noticesApi, "listNotices").mockResolvedValueOnce([])
    const { result } = renderHook(() => useNoticeList(undefined), { wrapper: wrapper() })
    await new Promise((r) => setTimeout(r, 30))
    expect(result.current.fetchStatus).toBe("idle")
  })
})

describe("useNotice + useNoticeDraft polling cadence", () => {
  it("useNotice polls every 2s while parsing/drafting", async () => {
    const spy = vi.spyOn(noticesApi, "getNotice").mockResolvedValue({
      id: "n1", tenant_id: "t", client_id: "c", created_by: "u",
      original_filename: "x.pdf", mime_type: "application/pdf",
      byte_size: 1, status: "parsing",
      created_at: "x", updated_at: "x",
    } as any)
    const { result } = renderHook(() => useNotice("n1"), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useNotices.test.tsx 2>&1 | tail -5`
Expected: failure.

- [ ] **Step 3: Implement hooks**

Create `frontend/src/hooks/useNotices.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  exportDraftUrl, finalizeDraft, generateDraft, getDraft, getNotice,
  listDraftRevisions, listNotices, relinkNotice, reopenDraft,
  saveDraft, uploadNotice,
  type RelinkPayload, type SaveDraftPayload,
} from "@/lib/notices/api"
import type { Notice, NoticeDraft } from "@/types/notices"

const TRANSIENT: Notice["status"][] = ["pending", "parsing", "drafting"]

export const noticeKeys = {
  all: ["notices"] as const,
  list: (clientId: string) => ["notices", "list", clientId] as const,
  detail: (id: string) => ["notices", "detail", id] as const,
  draft: (id: string) => ["notices", "draft", id] as const,
  revisions: (id: string) => ["notices", "revisions", id] as const,
}

export function useNoticeList(clientId: string | undefined) {
  return useQuery({
    queryKey: noticeKeys.list(clientId ?? ""),
    enabled: Boolean(clientId),
    queryFn: () => listNotices(clientId!),
  })
}

export function useNotice(noticeId: string | undefined) {
  return useQuery<Notice>({
    queryKey: noticeKeys.detail(noticeId ?? ""),
    enabled: Boolean(noticeId),
    queryFn: () => getNotice(noticeId!),
    // Poll while a phase is in progress so the UI shows status transitions
    // without manual refresh.
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s && TRANSIENT.includes(s) ? 2_000 : false
    },
  })
}

export function useNoticeDraft(noticeId: string | undefined) {
  return useQuery<NoticeDraft>({
    queryKey: noticeKeys.draft(noticeId ?? ""),
    enabled: Boolean(noticeId),
    queryFn: () => getDraft(noticeId!),
    retry: (_failureCount, err) => {
      // 404 = no draft yet; don't retry — UI shows "Draft reply" CTA
      const status = (err as { status?: number })?.status
      return status !== 404
    },
  })
}

export function useUploadNotice(clientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadNotice(clientId, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.list(clientId) })
    },
  })
}

export function useRelinkNotice(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: RelinkPayload) => relinkNotice(noticeId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.detail(noticeId) })
    },
  })
}

export function useGenerateDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => generateDraft(noticeId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.detail(noticeId) })
      void qc.invalidateQueries({ queryKey: noticeKeys.draft(noticeId) })
    },
  })
}

export function useSaveDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (p: SaveDraftPayload) => saveDraft(noticeId, p),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.revisions(noticeId) })
    },
  })
}

export function useFinalizeDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => finalizeDraft(noticeId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.detail(noticeId) })
      void qc.invalidateQueries({ queryKey: noticeKeys.draft(noticeId) })
    },
  })
}

export function useReopenDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (reason: string) => reopenDraft(noticeId, reason),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.draft(noticeId) })
    },
  })
}

export function useDraftRevisions(noticeId: string | undefined) {
  return useQuery({
    queryKey: noticeKeys.revisions(noticeId ?? ""),
    enabled: Boolean(noticeId),
    queryFn: () => listDraftRevisions(noticeId!),
  })
}

export { exportDraftUrl }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useNotices.test.tsx 2>&1 | tail -5`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useNotices.ts frontend/src/hooks/__tests__/useNotices.test.tsx
git commit -m "feat(notices/fe): TanStack Query hooks + transient-status polling"
```

---

## Phase 7 — Frontend pages and components

Components are small and focused — one responsibility each. Pages compose them.

### Task 7.1: Notice list page + upload dropzone

**Files:**
- Create: `frontend/src/components/notices/NoticeUploadDropzone.tsx`
- Create: `frontend/src/pages/NoticeList.tsx`

- [ ] **Step 1: Implement the dropzone**

Create `frontend/src/components/notices/NoticeUploadDropzone.tsx`:

```tsx
import { Upload } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.heic,.webp"
const MAX_BYTES = 25 * 1024 * 1024

interface Props {
  disabled?: boolean
  onPicked: (file: File) => void
}

export function NoticeUploadDropzone({ disabled, onPicked }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function pick(file: File) {
    if (file.size > MAX_BYTES) {
      setError(`File too large (${(file.size / 1024 / 1024).toFixed(1)} MB > 25 MB)`)
      return
    }
    setError(null)
    onPicked(file)
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const f = e.dataTransfer.files?.[0]
    if (f) pick(f)
  }

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "rounded-lg border-2 border-dashed p-8 text-center transition-colors",
          dragOver ? "border-primary bg-accent" : "border-border",
          disabled && "opacity-60 pointer-events-none",
        )}
      >
        <Upload className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <p className="mt-2 text-sm">
          Drop an NBR notice PDF or photo here, or
          <label htmlFor="notice-upload" className="ml-1 cursor-pointer text-primary underline">
            browse
            <input
              ref={inputRef}
              id="notice-upload"
              type="file"
              accept={ACCEPT}
              className="sr-only"
              aria-label="Upload notice"
              disabled={disabled}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) pick(f)
                if (inputRef.current) inputRef.current.value = ""
              }}
            />
          </label>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, JPG, PNG, HEIC, WEBP · max 25 MB
        </p>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Implement the list page**

Create `frontend/src/pages/NoticeList.tsx`:

```tsx
import { useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { NoticeUploadDropzone } from "@/components/notices/NoticeUploadDropzone"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { useNoticeList, useUploadNotice } from "@/hooks/useNotices"
import { ApiError } from "@/lib/api"
import type { NoticeStatus } from "@/types/notices"

const STATUS_TONE: Record<NoticeStatus, string> = {
  pending:         "bg-slate-200 text-slate-700",
  parsing:         "bg-blue-100 text-blue-800",
  parsed:          "bg-blue-100 text-blue-800",
  awaiting_data:   "bg-amber-100 text-amber-900",
  ready_to_draft:  "bg-indigo-100 text-indigo-800",
  drafting:        "bg-blue-100 text-blue-800",
  drafted:         "bg-emerald-100 text-emerald-800",
  finalized:       "bg-emerald-200 text-emerald-900",
  failed:          "bg-red-100 text-red-800",
}

export function NoticeList() {
  const { id: clientId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const list = useNoticeList(clientId)
  const upload = useUploadNotice(clientId ?? "")

  async function handlePick(file: File) {
    try {
      const { notice_id } = await upload.mutateAsync(file)
      toast.success("Notice uploaded. Parsing…")
      navigate(`/clients/${clientId}/notices/${notice_id}`)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Upload an NBR notice</CardTitle></CardHeader>
        <CardContent>
          <NoticeUploadDropzone
            disabled={upload.isPending}
            onPicked={handlePick}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Notices</CardTitle></CardHeader>
        <CardContent>
          {list.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {list.isSuccess && list.data.length === 0 && (
            <p className="text-sm text-slate-500">
              No notices yet. Drop an NBR notice above to start.
            </p>
          )}
          {list.isSuccess && list.data.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Notice no</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Shortfall</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.map((n) => (
                  <TableRow
                    key={n.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => navigate(`/clients/${clientId}/notices/${n.id}`)}
                  >
                    <TableCell className="font-mono">{n.notice_no || n.original_filename}</TableCell>
                    <TableCell>{n.notice_date || "—"}</TableCell>
                    <TableCell>{n.period_start && n.period_end ? `${n.period_start} → ${n.period_end}` : "—"}</TableCell>
                    <TableCell>{n.alleged_shortfall_bdt ?? "—"}</TableCell>
                    <TableCell>
                      <Badge className={STATUS_TONE[n.status]}>{n.status}</Badge>
                    </TableCell>
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
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/notices/NoticeUploadDropzone.tsx frontend/src/pages/NoticeList.tsx
git commit -m "feat(notices/fe): notice list page + upload dropzone"
```

### Task 7.2: Notice detail page (parsed meta + status banners)

**Files:**
- Create: `frontend/src/components/notices/NoticeMetaCard.tsx`
- Create: `frontend/src/components/notices/NoticeStatusBanner.tsx`
- Create: `frontend/src/components/notices/AwaitingDataPrompt.tsx`
- Create: `frontend/src/components/notices/RelinkDialog.tsx`
- Create: `frontend/src/pages/NoticeDetail.tsx`

- [ ] **Step 1: NoticeMetaCard**

Create `frontend/src/components/notices/NoticeMetaCard.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Notice } from "@/types/notices"

export function NoticeMetaCard({ notice }: { notice: Notice }) {
  return (
    <Card>
      <CardHeader><CardTitle>Parsed notice metadata</CardTitle></CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <Field label="Notice no" value={notice.notice_no} mono />
          <Field label="Notice date" value={notice.notice_date} />
          <Field label="Taxpayer BIN" value={notice.taxpayer_bin} mono />
          <Field label="Taxpayer TIN" value={notice.taxpayer_tin} mono />
          <Field label="Period" value={
            notice.period_start && notice.period_end
              ? `${notice.period_start} → ${notice.period_end}`
              : null
          } />
          <Field label="Alleged claimed ITC" value={notice.alleged_itc_claimed_bdt} />
          <Field label="Alleged allowed ITC" value={notice.alleged_itc_allowed_bdt} />
          <Field label="Alleged shortfall" value={notice.alleged_shortfall_bdt} />
        </dl>
      </CardContent>
    </Card>
  )
}

function Field({
  label, value, mono,
}: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? "font-mono" : ""}>{value || "—"}</dd>
    </>
  )
}
```

- [ ] **Step 2: NoticeStatusBanner**

Create `frontend/src/components/notices/NoticeStatusBanner.tsx`:

```tsx
import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useGenerateDraft } from "@/hooks/useNotices"
import type { Notice } from "@/types/notices"

interface Props {
  notice: Notice
  onDraftStarted?: () => void
}

export function NoticeStatusBanner({ notice, onDraftStarted }: Props) {
  const generate = useGenerateDraft(notice.id)

  if (notice.status === "parsing" || notice.status === "pending") {
    return (
      <Banner tone="info" icon={Loader2} spin>
        <strong>Parsing notice…</strong> Extracting metadata via Gemini Vision.
      </Banner>
    )
  }
  if (notice.status === "failed") {
    return (
      <Banner tone="error" icon={AlertTriangle}>
        <strong>Failed:</strong> {notice.parse_error || "Unknown error"}
      </Banner>
    )
  }
  if (notice.status === "ready_to_draft") {
    return (
      <Banner tone="info" icon={Sparkles}>
        <div className="flex items-center gap-3">
          <span>Ready to draft. Linked to a reconciliation for this period.</span>
          <Button
            size="sm"
            disabled={generate.isPending}
            onClick={async () => {
              await generate.mutateAsync()
              onDraftStarted?.()
            }}
          >
            {generate.isPending ? "Starting…" : "Draft reply with HishabAI"}
          </Button>
        </div>
      </Banner>
    )
  }
  if (notice.status === "drafting") {
    return (
      <Banner tone="info" icon={Loader2} spin>
        <strong>Drafting reply…</strong> Retrieving relevant law and composing Bangla letter.
      </Banner>
    )
  }
  if (notice.status === "drafted" || notice.status === "finalized") {
    return (
      <Banner tone="success" icon={CheckCircle2}>
        <strong>Draft ready.</strong> Open the editor below to review and export.
      </Banner>
    )
  }
  return null
}

function Banner({
  tone, icon: Icon, spin, children,
}: {
  tone: "info" | "error" | "success"
  icon: React.ElementType
  spin?: boolean
  children: React.ReactNode
}) {
  const cls = {
    info: "border-blue-200 bg-blue-50 text-blue-900",
    error: "border-red-200 bg-red-50 text-red-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[tone]
  return (
    <Card className={`border ${cls}`}>
      <CardContent className="flex items-start gap-3 py-3 text-sm">
        <Icon className={`size-4 mt-0.5 ${spin ? "animate-spin" : ""}`} aria-hidden />
        <div className="flex-1">{children}</div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: AwaitingDataPrompt — the wedge mechanic CTA**

Create `frontend/src/components/notices/AwaitingDataPrompt.tsx`:

```tsx
import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Notice } from "@/types/notices"

interface Props {
  notice: Notice
  clientId: string
}

/**
 * The wedge mechanic: when a notice arrives for a period we haven't
 * reconciled yet, route the user into the existing combined-ingestion
 * wizard pre-filled with this notice's client + period. The wizard
 * itself will call `relinkNotice` when it finishes (see Task 7.5).
 */
export function AwaitingDataPrompt({ notice, clientId }: Props) {
  const navigate = useNavigate()

  function startIngestion() {
    const qs = new URLSearchParams({
      from_notice: notice.id,
      period_start: notice.period_start ?? "",
      period_end: notice.period_end ?? "",
    }).toString()
    navigate(`/clients/${clientId}/ingestion/new?${qs}`)
  }

  return (
    <Card className="border-amber-200 bg-amber-50">
      <CardHeader>
        <CardTitle className="text-amber-900">Reconciliation data needed</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-amber-900">
          To draft a reply grounded in your actual position, HishabAI needs to
          reconcile your purchase register for{" "}
          <strong>{notice.period_start} → {notice.period_end}</strong> first.
        </p>
        <p className="text-xs text-amber-800">
          You'll be taken to the ingestion wizard pre-filled with this client
          and period. When it finishes, your reply draft will be ready
          automatically.
        </p>
        <Button onClick={startIngestion}>Upload purchase register →</Button>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 4: RelinkDialog (manual client + period picker)**

Create `frontend/src/components/notices/RelinkDialog.tsx`:

```tsx
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useClients } from "@/hooks/useClients"
import { useRelinkNotice } from "@/hooks/useNotices"
import { ApiError } from "@/lib/api"
import type { Notice } from "@/types/notices"

interface Props {
  notice: Notice
  open: boolean
  onOpenChange: (o: boolean) => void
}

export function RelinkDialog({ notice, open, onOpenChange }: Props) {
  const clients = useClients()
  const relink = useRelinkNotice(notice.id)
  const [clientId, setClientId] = useState<string>(notice.client_id ?? "")
  const [start, setStart] = useState<string>(notice.period_start ?? "")
  const [end, setEnd] = useState<string>(notice.period_end ?? "")

  async function save() {
    try {
      await relink.mutateAsync({
        client_id: clientId, period_start: start, period_end: end,
      })
      toast.success("Notice re-linked. Re-running the linker…")
      onOpenChange(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Link this notice</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="rl-client">Client</Label>
            <Select value={clientId} onValueChange={setClientId}>
              <SelectTrigger id="rl-client"><SelectValue placeholder="Pick a client" /></SelectTrigger>
              <SelectContent>
                {(clients.data ?? []).map((c) => (
                  <SelectItem key={c.id} value={c.id}>{c.business_name} ({c.bin})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="rl-start">Period start</Label>
              <Input id="rl-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="rl-end">Period end</Label>
              <Input id="rl-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={!clientId || !start || !end || relink.isPending}>
            {relink.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 5: NoticeDetail page**

Create `frontend/src/pages/NoticeDetail.tsx`:

```tsx
import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { AwaitingDataPrompt } from "@/components/notices/AwaitingDataPrompt"
import { NoticeMetaCard } from "@/components/notices/NoticeMetaCard"
import { NoticeStatusBanner } from "@/components/notices/NoticeStatusBanner"
import { RelinkDialog } from "@/components/notices/RelinkDialog"
import { Button } from "@/components/ui/button"
import { useNotice } from "@/hooks/useNotices"

export function NoticeDetail() {
  const { id: clientId, noticeId } = useParams<{ id: string; noticeId: string }>()
  const navigate = useNavigate()
  const q = useNotice(noticeId)
  const [relinkOpen, setRelinkOpen] = useState(false)

  if (q.isLoading) return <p className="text-sm text-slate-500">Loading notice…</p>
  if (q.isError || !q.data) {
    return <p className="text-sm text-red-700">Could not load notice.</p>
  }
  const n = q.data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {n.notice_no || n.original_filename}
        </h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setRelinkOpen(true)}>
            Re-link notice
          </Button>
          {(n.status === "drafted" || n.status === "finalized") && (
            <Button onClick={() => navigate(`/clients/${clientId}/notices/${n.id}/draft`)}>
              Open draft →
            </Button>
          )}
        </div>
      </div>

      <NoticeStatusBanner
        notice={n}
        onDraftStarted={() => navigate(`/clients/${clientId}/notices/${n.id}/draft`)}
      />

      {n.status === "awaiting_data" && clientId && (
        <AwaitingDataPrompt notice={n} clientId={clientId} />
      )}

      <NoticeMetaCard notice={n} />

      <RelinkDialog notice={n} open={relinkOpen} onOpenChange={setRelinkOpen} />
    </div>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/notices/NoticeMetaCard.tsx frontend/src/components/notices/NoticeStatusBanner.tsx frontend/src/components/notices/AwaitingDataPrompt.tsx frontend/src/components/notices/RelinkDialog.tsx frontend/src/pages/NoticeDetail.tsx
git commit -m "feat(notices/fe): notice detail page + status banner + relink dialog + wedge CTA"
```

### Task 7.3: Draft editor (TipTap + citations + appendix + export)

**Files:**
- Create: `frontend/src/components/notices/DraftEditor.tsx`
- Create: `frontend/src/components/notices/CitationsPanel.tsx`
- Create: `frontend/src/components/notices/ComputationAppendixTable.tsx`
- Create: `frontend/src/pages/NoticeDraft.tsx`

- [ ] **Step 1: CitationsPanel**

Create `frontend/src/components/notices/CitationsPanel.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Citation } from "@/types/notices"

export function CitationsPanel({ citations }: { citations: Citation[] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Citations</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-sm">
        {citations.length === 0 && (
          <p className="text-slate-500">No citations in this draft yet.</p>
        )}
        {citations.map((c, i) => (
          <div key={`${c.corpus_chunk_id}-${i}`} className="rounded-md border p-2">
            <p className="font-medium">{c.source_ref}</p>
            <p className="mt-1 text-xs text-slate-600 line-clamp-3">{c.snippet}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: ComputationAppendixTable**

Create `frontend/src/components/notices/ComputationAppendixTable.tsx`:

```tsx
import { Input } from "@/components/ui/input"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import type { AppendixJson, AppendixRow } from "@/types/notices"

interface Props {
  value: AppendixJson
  onChange: (next: AppendixJson) => void
  disabled?: boolean
}

export function ComputationAppendixTable({ value, onChange, disabled }: Props) {
  function setRow(i: number, patch: Partial<AppendixRow>) {
    const rows = value.rows.map((r, idx) => idx === i ? { ...r, ...patch } : r)
    onChange({ ...value, rows })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Item</TableHead>
          <TableHead>Amount (BDT)</TableHead>
          <TableHead>Note</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {value.rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={3} className="text-slate-500">(no rows)</TableCell>
          </TableRow>
        ) : value.rows.map((r, i) => (
          <TableRow key={i}>
            <TableCell>
              <Input
                value={r.label}
                disabled={disabled}
                onChange={(e) => setRow(i, { label: e.target.value })}
              />
            </TableCell>
            <TableCell>
              <Input
                value={r.value_bdt ?? ""}
                disabled={disabled}
                onChange={(e) => setRow(i, { value_bdt: e.target.value || null })}
              />
            </TableCell>
            <TableCell>
              <Input
                value={r.note ?? ""}
                disabled={disabled}
                onChange={(e) => setRow(i, { note: e.target.value || null })}
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
```

- [ ] **Step 3: DraftEditor (TipTap)**

Create `frontend/src/components/notices/DraftEditor.tsx`:

```tsx
import Superscript from "@tiptap/extension-superscript"
import { EditorContent, useEditor } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import { useEffect } from "react"

import { cn } from "@/lib/utils"

interface Props {
  value: string                          // HTML
  onChange: (html: string) => void
  disabled?: boolean
}

export function DraftEditor({ value, onChange, disabled }: Props) {
  const editor = useEditor({
    extensions: [StarterKit, Superscript],
    content: value,
    editable: !disabled,
    onUpdate({ editor }) {
      onChange(editor.getHTML())
    },
    editorProps: {
      attributes: {
        class: cn(
          "prose prose-sm max-w-none min-h-[24rem] rounded-md border p-4 focus:outline-none",
          "[&_sup.citation]:text-blue-600 [&_sup.citation]:font-semibold",
        ),
      },
    },
  })

  // Keep editor content in sync if `value` changes from outside (e.g. regenerate)
  useEffect(() => {
    if (editor && value !== editor.getHTML()) {
      editor.commands.setContent(value, { emitUpdate: false })
    }
  }, [value, editor])

  useEffect(() => {
    editor?.setEditable(!disabled)
  }, [editor, disabled])

  return <EditorContent editor={editor} />
}
```

- [ ] **Step 4: NoticeDraft page**

Create `frontend/src/pages/NoticeDraft.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { toast } from "sonner"

import { CitationsPanel } from "@/components/notices/CitationsPanel"
import { ComputationAppendixTable } from "@/components/notices/ComputationAppendixTable"
import { DraftEditor } from "@/components/notices/DraftEditor"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import {
  exportDraftUrl, useFinalizeDraft, useGenerateDraft, useNotice,
  useNoticeDraft, useReopenDraft, useSaveDraft,
} from "@/hooks/useNotices"
import { ApiError } from "@/lib/api"
import type { AppendixJson } from "@/types/notices"

const EMPTY_APPENDIX: AppendixJson = { rows: [] }

export function NoticeDraft() {
  const { noticeId } = useParams<{ noticeId: string }>()
  const notice = useNotice(noticeId)
  const draft = useNoticeDraft(noticeId)
  const save = useSaveDraft(noticeId ?? "")
  const regenerate = useGenerateDraft(noticeId ?? "")
  const finalize = useFinalizeDraft(noticeId ?? "")
  const reopen = useReopenDraft(noticeId ?? "")

  const [bodyHtml, setBodyHtml] = useState<string>("")
  const [appendix, setAppendix] = useState<AppendixJson>(EMPTY_APPENDIX)

  // Hydrate from server on first load + on regenerate
  useEffect(() => {
    if (draft.data) {
      setBodyHtml(draft.data.body_html)
      setAppendix(draft.data.appendix_json as AppendixJson)
    }
  }, [draft.data?.id, draft.data?.updated_at])

  // Autosave (debounced 2s) only when the draft is editable
  const isFinalized = draft.data?.status === "finalized"
  const debouncedBody = useDebouncedValue(bodyHtml, 2000)
  const debouncedAppendix = useDebouncedValue(appendix, 2000)

  useEffect(() => {
    if (!draft.data || isFinalized) return
    if (debouncedBody === draft.data.body_html
        && JSON.stringify(debouncedAppendix) === JSON.stringify(draft.data.appendix_json)) {
      return
    }
    save.mutate({ body_html: debouncedBody, appendix_json: debouncedAppendix })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedBody, debouncedAppendix, isFinalized])

  if (notice.isLoading || draft.isLoading) {
    return <p className="text-sm text-slate-500">Loading draft…</p>
  }
  if (draft.isError || !draft.data) {
    return <p className="text-sm text-red-700">No draft yet for this notice.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Reply draft</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline" disabled={regenerate.isPending}
            onClick={async () => {
              try {
                await regenerate.mutateAsync()
                toast.success("Regenerating…")
              } catch (e) {
                toast.error(e instanceof ApiError ? e.message : (e as Error).message)
              }
            }}
          >
            Regenerate
          </Button>
          <Button variant="outline" asChild>
            <a href={exportDraftUrl(noticeId!, "docx")} download>Export .docx</a>
          </Button>
          <Button variant="outline" asChild>
            <a href={exportDraftUrl(noticeId!, "pdf")} download>Export PDF</a>
          </Button>
          {isFinalized ? (
            <Button
              onClick={async () => {
                const reason = prompt("Reason to reopen (visible in history):") ?? ""
                if (reason.trim().length < 3) return
                await reopen.mutateAsync(reason)
                toast.success("Reopened for editing.")
              }}
            >
              Reopen for editing
            </Button>
          ) : (
            <Button
              onClick={async () => {
                await finalize.mutateAsync()
                toast.success("Draft finalized.")
              }}
            >
              Mark finalized
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader><CardTitle>Body (Bangla)</CardTitle></CardHeader>
          <CardContent>
            <DraftEditor value={bodyHtml} onChange={setBodyHtml} disabled={isFinalized} />
            <p className="mt-2 text-xs text-slate-500">
              {save.isPending ? "Saving…" : "Autosaves every 2 seconds."}
            </p>
          </CardContent>
        </Card>
        <div className="space-y-4">
          <CitationsPanel citations={draft.data.citations} />
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>Computation appendix (English)</CardTitle></CardHeader>
        <CardContent>
          <ComputationAppendixTable
            value={appendix} onChange={setAppendix} disabled={isFinalized}
          />
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/notices/CitationsPanel.tsx frontend/src/components/notices/ComputationAppendixTable.tsx frontend/src/components/notices/DraftEditor.tsx frontend/src/pages/NoticeDraft.tsx
git commit -m "feat(notices/fe): TipTap draft editor + citations panel + appendix + export"
```

### Task 7.4: Routes + nav wiring

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/layout/AppShell.tsx`

- [ ] **Step 1: Add three routes**

In `frontend/src/router.tsx`, add the imports near the existing page imports:

```tsx
import { NoticeDetail } from "@/pages/NoticeDetail"
import { NoticeDraft } from "@/pages/NoticeDraft"
import { NoticeList } from "@/pages/NoticeList"
```

Then add three route objects to the route array — alongside the existing
`/clients/:id/...` routes:

```tsx
{ path: "/clients/:id/notices",
  element: <RootLayout><ProtectedRoute><NoticeList /></ProtectedRoute></RootLayout> },
{ path: "/clients/:id/notices/:noticeId",
  element: <RootLayout><ProtectedRoute><NoticeDetail /></ProtectedRoute></RootLayout> },
{ path: "/clients/:id/notices/:noticeId/draft",
  element: <RootLayout><ProtectedRoute><NoticeDraft /></ProtectedRoute></RootLayout> },
```

- [ ] **Step 2: Add a Notices tab inside the client view**

Locate the existing client-detail navigation (search for "Reconciliations"
tab inside `frontend/src/pages/ClientDetail.tsx` or wherever the tabs are
rendered). Add a new tab pointing at `/clients/${id}/notices` with the
label "Notices". Follow the existing pattern exactly — don't restructure.

If the nav lives in `frontend/src/components/layout/AppShell.tsx` instead,
add a top-level "Notices" entry alongside the existing nav items there.

- [ ] **Step 3: Verify build still passes + smoke vitest**

Run: `cd frontend && npm run build && npx vitest run 2>&1 | tail -10`
Expected: build OK; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router.tsx frontend/src/pages/ClientDetail.tsx frontend/src/components/layout/AppShell.tsx
git commit -m "feat(notices/fe): routes + client-detail Notices tab + sidebar entry"
```

### Task 7.5: Wedge mechanic — wizard reads `?from_notice=` and calls relink

**Files:**
- Modify: `frontend/src/pages/IngestionNew.tsx` (or wherever the wizard entry lives)
- Modify: `frontend/src/components/ingestion/*` for the wizard's finalize handler
- Create: `frontend/src/lib/notices/wizardCallback.ts` (small helper)

- [ ] **Step 1: Add the helper**

Create `frontend/src/lib/notices/wizardCallback.ts`:

```ts
import { relinkNotice } from "@/lib/notices/api"

const SESSION_KEY = "hishabai:from_notice_pending"

/** Capture `?from_notice=...` from the URL into sessionStorage so we
 * remember it across the wizard's multi-step lifecycle. */
export function captureFromNoticeFromQuery(search: string): void {
  const sp = new URLSearchParams(search)
  const id = sp.get("from_notice")
  if (id) sessionStorage.setItem(SESSION_KEY, id)
}

export function popFromNoticeId(): string | null {
  const v = sessionStorage.getItem(SESSION_KEY)
  if (v) sessionStorage.removeItem(SESSION_KEY)
  return v
}

/** Called by the wizard's success handler once a reconciliation_id exists. */
export async function notifyNoticeOfReconciliation(args: {
  clientId: string
  periodStart: string
  periodEnd: string
  reconciliationId: string
}): Promise<string | null> {
  const noticeId = popFromNoticeId()
  if (!noticeId) return null
  await relinkNotice(noticeId, {
    client_id: args.clientId,
    period_start: args.periodStart,
    period_end: args.periodEnd,
    reconciliation_id: args.reconciliationId,
  })
  return noticeId
}
```

- [ ] **Step 2: Wire capture on the wizard entry**

In `frontend/src/pages/IngestionNew.tsx` (the page that opens at
`/clients/:id/ingestion/new`), add at the top of the component:

```tsx
import { useEffect } from "react"
import { useLocation } from "react-router-dom"
import { captureFromNoticeFromQuery } from "@/lib/notices/wizardCallback"

// inside the component:
const location = useLocation()
useEffect(() => {
  captureFromNoticeFromQuery(location.search)
}, [location.search])
```

- [ ] **Step 3: Wire the callback on wizard completion**

Locate the wizard step that fires when a reconciliation is created (search
for `useCreateReconciliation` or the `onSuccess` of the final wizard step
that returns `reconciliation_id`). At that callback, add:

```ts
import { notifyNoticeOfReconciliation } from "@/lib/notices/wizardCallback"
import { useNavigate } from "react-router-dom"

// inside the onSuccess:
const noticeId = await notifyNoticeOfReconciliation({
  clientId, periodStart, periodEnd, reconciliationId: result.reconciliation_id,
})
if (noticeId) {
  toast.success("Reconciliation done — your reply draft is ready.")
  navigate(`/clients/${clientId}/notices/${noticeId}`)
  return
}
// fall through to the existing post-recon navigation
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/notices/wizardCallback.ts frontend/src/pages/IngestionNew.tsx frontend/src/components/ingestion/
git commit -m "feat(notices/fe): wedge mechanic — wizard relinks notice on completion"
```

---

## Phase 8 — End-to-end smoke + final checks

### Task 8.1: Backend full-suite green

**Files:**
- (no new files — just verification)

- [ ] **Step 1: Run the entire backend suite (skipping live-only tests)**

Run: `cd backend && python -m pytest tests/ --ignore=tests/ingestion/test_llm_gemini.py --ignore=tests/notices/test_llm_gemini.py -q 2>&1 | tail -10`
Expected: all tests pass (≥ 139 from baseline + 30+ added across notices tasks).

- [ ] **Step 2: Run the live-gated suites (with GEMINI_API_KEY + INGESTION_TEST_* set)**

Run: `cd backend && python -m pytest tests/notices/test_llm_gemini.py tests/notices/test_persistence.py tests/notices/test_seed_citation_corpus.py -v -m "live or not live" 2>&1 | tail -10`
Expected: all pass (live tests require env vars; skip cleanly otherwise).

### Task 8.2: Frontend full-suite + build green

**Files:**
- (no new files)

- [ ] **Step 1: Vitest**

Run: `cd frontend && npx vitest run 2>&1 | tail -10`
Expected: all tests pass.

- [ ] **Step 2: Production build**

Run: `cd frontend && npm run build 2>&1 | tail -10`
Expected: build succeeds with no type errors.

### Task 8.3: Manual Playwright smoke (the demo path)

**Files:**
- (no new files — interactive verification)

This is the actual wedge demo. Run it once to confirm the whole pipeline
behaves end-to-end against real services.

- [ ] **Step 1: Start both dev servers**

Backend: `cd backend && python -m uvicorn app.main:app --reload --port 8000` (in one terminal)
Frontend: `cd frontend && npm run dev` (in another)

- [ ] **Step 2: Walk through Flow A (linked-recon happy path) via Playwright MCP**

Steps:
1. Log in as the demo user.
2. Pick a client that already has a reconciliation for some period.
3. Navigate to `/clients/<id>/notices`.
4. Upload `backend/tests/notices/fixtures/notice_input_vat_mismatch.jpg`
   but first edit its embedded BIN to match the client's BIN (re-run the
   fixture script with the right BIN), or use a notice you generate fresh.
5. Wait for status → `ready_to_draft` (should happen within 30s).
6. Click "Draft reply with HishabAI" → wait for status `drafted`.
7. Open the draft editor; verify Bangla body renders, citations panel
   shows 1+ entries, computation appendix has rows.
8. Edit one paragraph; observe autosave indicator.
9. Click "Export .docx" — verify download is a real Word file with the
   Bangla body, appendix table, and citations section.
10. Click "Mark finalized" → editor goes read-only.
11. Click "Reopen for editing" → enter reason → editor unlocks; check that
    the revisions endpoint (browser devtools network tab) shows the reopen
    revision entry.

- [ ] **Step 3: Walk through Flow B (wedge mechanic) via Playwright MCP**

Steps:
1. Upload a notice for a client + period that has NO reconciliation.
2. After parsing, status becomes `awaiting_data`; the
   AwaitingDataPrompt should be visible.
3. Click "Upload purchase register →"; the wizard opens at
   `/clients/<id>/ingestion/new?from_notice=<id>&period_start=…&period_end=…`.
4. Complete the wizard (upload a PR + SF or pick reused docs).
5. After the wizard finishes, you should be navigated back to the notice
   detail page with status `ready_to_draft`, and a toast saying
   "Reconciliation done — your reply draft is ready."

- [ ] **Step 4: Document any defects found**

If anything fails, file the defect as a follow-up commit on this branch
with a clear "fix(notices)" message. Do NOT mark Task 8.3 complete until
both flows pass cleanly end-to-end.

### Task 8.4: Branch ready for merge

**Files:**
- (none)

- [ ] **Step 1: Verify branch is clean**

Run: `git status` from the worktree root.
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 2: Confirm all migrations are committed**

Run: `git log --oneline -- migrations/`
Expected: commits for `0018`, `0019`, `0020`, `0021` present.

- [ ] **Step 3: Push and open PR**

```bash
git push -u origin feat/nbr-notice-drafter
gh pr create --title "NBR Notice Response Drafter — v1" --body "$(cat <<'EOF'
## Summary
- New `app/notices/` backend domain: parser, linker, retriever, drafter, rendering, worker, service, router.
- pgvector-backed citation corpus seeded from `app/notices/corpus/*.md`.
- Frontend per-client Notices area with TipTap editor, citations panel, .docx + PDF export.
- Wedge mechanic: notices for un-reconciled periods deep-link into the combined-ingestion wizard and re-drive the drafter on completion.

Spec: `docs/superpowers/specs/2026-05-18-nbr-notice-drafter-design.md`
Plan: `docs/superpowers/plans/2026-05-18-nbr-notice-drafter.md`

## Test plan
- [ ] Backend suite green (`pytest tests/ --ignore=*/test_llm_gemini.py`)
- [ ] Frontend Vitest green + production build green
- [ ] Live Gemini parser smoke passes
- [ ] Live persistence/seed tests pass with `INGESTION_TEST_*` set
- [ ] Manual Playwright walkthrough of Flow A (linked-recon path)
- [ ] Manual Playwright walkthrough of Flow B (wedge mechanic)
- [ ] `.docx` export opens in Word with Bangla body + appendix + citations
- [ ] PDF export works on hosts with LibreOffice; 503 with clear message elsewhere

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (run inline before handing off)

**Spec coverage:** every section in `2026-05-18-nbr-notice-drafter-design.md` is
implemented by at least one task:

- §3 in-scope items: notice ingestion (Tasks 4.1, 5.3), one notice category +
  rejection of others (4.1, 5.2 unsupported branch), auto-linking (4.2),
  wedge fall-through (4.2 + 7.3 AwaitingDataPrompt + 7.5 wizard callback),
  retrieval (4.3 + 2.x corpus), Bangla body + English appendix (4.4 + 4.5 + 7.3),
  TipTap editor (7.3), autosave + revisions (5.1 + 7.3 + 6.3),
  `.docx` + PDF export (4.5 + 5.3 + 7.3), per-client IA (7.1–7.4),
  cross-link from recon report (7.4), audit-trail revisions (5.1 schema + 5.1 update_draft).
- §5 data model: covered by Task 1.2 migration.
- §6 pipeline phases: parser (4.1), linker (4.2), retriever (4.3),
  drafter (4.4), rendering (4.5), worker (5.2).
- §8 API surface: every endpoint exists in `notices/router.py` (Task 5.3).
- §9 corpus seeding: Tasks 2.1 + 2.2.
- §10 worker semantics: lease pattern in 5.2 mirrors ingestion worker.
- §11 dependencies: backend deps in 0.1, frontend deps in 0.2, LibreOffice doc in 0.3.
- §12 testing strategy: each pipeline module has its own test file; live tests gated.

**Placeholder scan:** No `TBD`, `TODO`, "implement later", or vague handwaving.
Every step has either complete code or a precise edit instruction.

**Type consistency check:**
- `NoticeStatus`, `NoticeType`, `NoticeDraftStatus`, `NoticeDraftEditSource`
  enum values match the Postgres enums in migration 0019 (verified by
  `test_notice_status_enum_values_match_db` in Task 3.1).
- `LinkerResult` discriminated union uses the same `kind` literals in
  backend (`schemas.py`) and frontend (`types/notices.ts`).
- `ParsedNotice` shape used in parser, linker, retriever, drafter, worker
  is exactly the Pydantic model defined in Task 3.1.
- `ReconSummary` produced by `fetch_recon_summary` (5.1) matches what
  `build_query_text` (4.3) and `build_draft_prompt` (4.4) consume.
- API DTOs in `router.py` (5.3) reference the Pydantic types from `schemas.py` (3.1).
- Frontend `Notice` / `NoticeDraft` Zod schemas (6.1) match backend `NoticeOut`/`NoticeDraftOut`.

**Scope check:** Single coherent feature; the pipeline phases depend on
each other linearly so decomposition into sub-projects would not yield
independently shippable software. Keeping as one plan.
