# HishabAI MVP — Design Spec

**Date:** 2026-05-02
**Status:** Approved (brainstorming complete; ready for implementation planning)
**Owner:** Solo + AI-assisted build
**Target audience for the product:** Anonymous Dhaka CA firms (no first user lined up; optimize for "convince a stranger CA in 5 minutes")
**Estimated build time:** 6 weeks

---

## 1. One-line description

HishabAI MVP is a thin-backend SaaS where a Bangladeshi CA firm manages clients and runs Excel-based VAT reconciliations to surface ITC risk in BDT.

## 2. Why this scope

The previous spec (`PROJECT.md`, 1800 lines) targeted ~10 weeks of work across document OCR, NBR notice AI, and reporting. This MVP cuts to the single feature with the strongest "hours saved → BDT impact" pitch for a CA evaluating the product cold: VAT reconciliation. Everything else is supporting cast or deferred.

The hero moment is: *upload purchase register XLSX + supplier export XLSX → see "৳47,000 of ITC risk in 30 seconds" with a clean color-coded report.*

## 3. Scope

### 3.1 In MVP

| # | Feature | Notes |
|---|---------|-------|
| 1 | Auth + onboarding | Supabase email/password. First-time user creates a tenant (CA firm). |
| 2 | Clients CRUD | Add/edit/soft-delete clients with name, BIN/TIN, entity type, fiscal year end. Search + filter. Frontend → Supabase direct (RLS-enforced). |
| 3 | **Reconciliation (the hero)** | Upload purchase register XLSX + supplier export XLSX → backend matches → results report with match types, ITC risk in BDT, line-item drilldown, CA override per line, XLSX export. Single FastAPI endpoint, **synchronous**. |
| 4 | Document storage | Every recon's input XLSX files attached to the client for audit trail. Frontend uploads directly to Supabase Storage. |
| 5 | Compliance calendar (read-only) | When a client is added, system auto-populates upcoming BD deadlines (VAT return 15th, TDS return 20th, IT return) based on entity type. Dashboard shows next 30 days across all clients. CA can mark events as `filed`. |
| 6 | Audit log | Postgres trigger writes every mutation on tenant-scoped tables to `audit_log` for regulatory defense. |

### 3.2 Out of MVP (Phase 2+)

- Document extraction / OCR (Tesseract, Gemini multimodal, anything that reads photos/PDFs)
- NBR Notice AI module (entire `notices/` subtree)
- MIS reports / PDF generation with AI narratives
- Email or SMS notifications/reminders
- Multi-user team management (single user per tenant in MVP — no invites, no roles beyond `firm_admin`)
- Bangla UI translation (Bangla *content* renders correctly; UI strings stay English)
- TDS-specific obligations beyond appearing on the calendar
- Bank statement parsing
- Separate client portal app
- Tally / NBR portal integrations
- Custom obligations beyond the standard BD set
- Photo upload of any kind
- Pixel-polish UI (animations, marketing landing page, dark mode, mobile-first)

## 4. Architecture

### 4.1 System diagram

```
┌──────────────────────────────────────────────────────────────┐
│  FRONTEND (React 18 + TS + Vite)  —  hosted on Vercel        │
│                                                              │
│  Pages: /login  /onboard  /dashboard                         │
│         /clients  /clients/:id                               │
│         /clients/:id/recon/new  /clients/:id/recon/:id       │
│                                                              │
│  Data layer:                                                 │
│   ├── @supabase/supabase-js  ← auth, reads, simple writes,  │
│   │                            storage uploads (~95% of      │
│   │                            data ops)                     │
│   └── axios → ONE call: POST /api/v1/reconciliations         │
└─────────────────────┬─────────────────────┬──────────────────┘
                      │                     │
                      │ JWT + RLS           │ JWT + service-role
                      ▼                     ▼
        ┌───────────────────────┐  ┌─────────────────────────┐
        │  SUPABASE             │  │  FASTAPI (Python 3.11+) │
        │  ────────             │  │  ────────────           │
        │  • Postgres (RLS)     │  │  Endpoints:             │
        │  • Auth (GoTrue)      │  │   POST /reconciliations │
        │  • Storage            │  │   GET  /health  /ready  │
        │  • Postgres functions │  │                         │
        │    (calendar gen)     │  │  Stack:                 │
        │                       │  │   • FastAPI (async)     │
        │  Region: Singapore    │  │   • supabase-py         │
        └───────────────────────┘  │   • pandas + openpyxl   │
                                   │   • structlog + pydantic│
                                   │   • pytest              │
                                   │                         │
                                   │  Hosted: Cloud Run      │
                                   │   (Singapore region)    │
                                   └─────────────────────────┘
```

### 4.2 Architectural choice: thin backend

**Decision:** Frontend talks to Supabase directly for ~95% of operations. FastAPI exists only to run the reconciliation engine.

**Why:**
- Clients CRUD, document listing, calendar reads, recon report rendering all reduce to Postgres queries that RLS already protects. Wrapping them in FastAPI routes adds ~2000 lines of CRUD plumbing for zero functional gain.
- Cuts ~3 weeks of backend work from the original plan.
- Recon is the only operation that genuinely needs server-side compute (XLSX parsing, matching algorithm, bulk inserts).
- Trade-off accepted: business logic is split (some in Postgres functions, some in React, the recon engine in Python). Acceptable because the MVP barely has logic outside the recon engine.

**When to revisit:** If we add a non-web client (mobile app, Tally plugin, CLI), or if recon-related side effects start needing centralized validation, move toward a hybrid (frontend reads → Supabase direct, writes → FastAPI).

### 4.3 Architectural choice: synchronous reconciliation

**Decision:** Recon endpoint is synchronous. No Celery, no Redis, no worker process.

**Why:**
- XLSX-only input caps the size at "what fits in an Excel a CA actually opens." Real registers are 100-1500 rows. A pandas-based matcher runs in <1 second on 1500 rows.
- Drops Celery, Redis, Docker Compose, worker deployment, task tracking, polling/realtime UI, and dead-letter handling from the entire stack.
- Risk: a 50,000-row register would time out the HTTP request. For target users (small/medium CA firms), unlikely. If we hit it, the fix is straightforward (move to async + Supabase Realtime for status).

### 4.4 Architectural choice: Bangladesh-first content, English-first UI

**Decision:** All UI labels, buttons, navigation, and error messages in English. All UI strings hard-coded (no i18n framework). Bangla content (supplier names, MushaK form titles, NBR notice text) renders verbatim using UTF-8.

**Why:**
- BD CAs work bilingually but their professional vocabulary is English ("reconciliation", "Input Tax Credit", "purchase register"). They do not need a Bangla-translated button to understand the workflow.
- Half-translated UI without a native Bangla copywriter reads worse than English-only.
- BDT formatting (`৳ 12,34,567.89`), DD/MM/YYYY dates, fiscal year labels (FY2024-25), and South Asian numbering are still Bangladesh-specific and **must** be implemented correctly. Existing `app/core/formatting.py` already handles this.

## 5. Tech stack

### 5.1 Backend

| Concern | Choice | Notes |
|---------|--------|-------|
| Web framework | FastAPI 0.115 | unchanged from current scaffold |
| Python | 3.11+ | unchanged |
| DB access | `supabase-py` (sync, wrapped via `asyncio.to_thread`) | Drop SQLAlchemy/asyncpg. With one endpoint + RLS via service-role, supabase-py is enough. |
| XLSX parsing/writing | pandas 2.2 + openpyxl 3.1 | For both input parsing and report export |
| Logging | structlog | Add request_id middleware. Never log file content or PII. |
| Validation | pydantic 2.9 | All I/O typed |
| Tests | pytest + pytest-asyncio | 85%+ coverage on `reconciliation/engine.py` and `compliance/deadlines.py` |
| Auth validation | PyJWT against `SUPABASE_JWT_SECRET` (HS256) | unchanged |
| Container | Single-stage Dockerfile (Python slim) | Deployed to Cloud Run |
| Process model | Single Uvicorn process | No worker, no Celery, no Redis |

### 5.2 Frontend

| Concern | Choice | Notes |
|---------|--------|-------|
| Framework | React 18 + TypeScript + Vite | |
| Routing | React Router 6 | |
| Data layer | `@supabase/supabase-js` for ~95% of ops; axios for the one POST | |
| State | Zustand (auth/session only) | Most state lives in Supabase queries |
| Server state | TanStack Query | Caches Supabase reads, uniform loading/error |
| UI kit | shadcn/ui + Tailwind (defaults, no custom theme) | "Clean and credible" polish level |
| Forms | React Hook Form + Zod | |
| Charts | Recharts | For recon report breakdown card |
| XLSX | None client-side — backend generates exports | Frontend gets a signed download URL |
| Container | Static build deployed to Vercel | |

### 5.3 Removed from current scaffold

**Dependencies to delete from `requirements.txt`:**
- `celery[redis]`, `redis`
- `pytesseract`, `opencv-python-headless`, `pdfplumber`, `pdf2image`, `Pillow`
- `google-cloud-aiplatform`, `google-generativeai`
- `sqlalchemy[asyncio]`, `asyncpg`, `greenlet`

**Files to delete:**
- `backend/app/ai/` (entire folder — no LLM in MVP)
- The async SQLAlchemy section of `backend/app/database.py` (`engine`, `async_session_factory`, `Base`, `get_db`)

**Files to keep & extend:**
- `backend/app/main.py` — add request_id middleware, fix `/ready` to use async-safe Supabase call
- `backend/app/config.py` — strip Redis/Vertex AI/Celery/MIS settings
- `backend/app/dependencies.py` — wrap sync supabase-py calls in `asyncio.to_thread`
- `backend/app/core/exceptions.py` — keep all error classes; add `INVALID_XLSX_FORMAT`
- `backend/app/core/formatting.py` — keep all (BDT, dates, fiscal year, BIN/TIN already correct)

### 5.4 Hosting & deployment

| Layer | Host | Notes |
|-------|------|-------|
| Frontend | Vercel (free tier, auto-deploys from GitHub) | `*.vercel.app` URL acceptable for MVP |
| Backend | Cloud Run (Singapore region, same as Supabase) | `min_instances=1` during demo period to avoid cold starts |
| Database / Auth / Storage | Supabase (existing project `qlrqbqisavkfxywkiuca`, Singapore) | |
| Custom domain | Deferred until post-MVP | |

## 6. Data model

### 6.1 Public schema (no RLS — system-level)

```sql
CREATE TABLE tenants (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_name     text NOT NULL,
  firm_name_bn  text,
  icab_reg_no   text UNIQUE,
  email         text NOT NULL,
  phone         text,
  address       text,
  plan          text DEFAULT 'starter',
  is_active     boolean DEFAULT true,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

CREATE TABLE user_profiles (
  id          uuid PRIMARY KEY REFERENCES auth.users(id),
  tenant_id   uuid NOT NULL REFERENCES tenants(id),
  full_name   text NOT NULL,
  role        text DEFAULT 'firm_admin',
  created_at  timestamptz DEFAULT now()
);

CREATE TABLE audit_log (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  user_id     uuid,
  action      text NOT NULL,        -- 'insert' | 'update' | 'delete'
  table_name  text NOT NULL,
  row_id      uuid NOT NULL,
  before      jsonb,
  after       jsonb,
  created_at  timestamptz DEFAULT now()
);

CREATE TABLE bd_obligation_definitions (
  obligation_type   text PRIMARY KEY,
  display_name      text NOT NULL,
  applies_to        text[] NOT NULL,    -- entity_types
  requires_vat_reg  boolean DEFAULT false,
  cadence           text NOT NULL,      -- 'monthly' | 'quarterly' | 'annual'
  due_rule          text NOT NULL,      -- human-readable description (e.g. "15th of month following period")
  law_reference     text,
  penalty_note      text
);
-- Note: actual due-date computation is hardcoded per obligation_type inside the
-- generate_compliance_events() function (section 8). due_rule is documentation,
-- not a parsed field.
```

### 6.2 Tenant-scoped (RLS enforced)

```sql
CREATE TABLE clients (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id),
  name              text NOT NULL,
  name_bn           text,
  tin               text CHECK (tin ~ '^\d{12}$' OR tin IS NULL),
  bin               text CHECK (bin ~ '^\d{9}$'  OR bin IS NULL),
  entity_type       text NOT NULL,        -- 'company'|'individual'|'partnership'|'ngo'|'bank'
  industry          text,
  fiscal_year_end   text DEFAULT '06-30', -- MM-DD
  is_vat_registered boolean DEFAULT false,
  contact_email     text,
  contact_phone     text,
  notes             text,
  deleted_at        timestamptz,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  created_by        uuid NOT NULL
);

CREATE TABLE compliance_obligations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  obligation_type text NOT NULL,
  is_active       boolean DEFAULT true,
  created_at      timestamptz DEFAULT now()
);

CREATE TABLE compliance_events (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  client_id         uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  obligation_type   text NOT NULL,
  period_start      date NOT NULL,
  period_end        date NOT NULL,
  due_date          date NOT NULL,
  status            text DEFAULT 'pending',  -- 'pending'|'filed'|'overdue'|'waived'|'na'
  filed_date        date,
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  UNIQUE (client_id, obligation_type, period_start)
);

CREATE TABLE documents (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  client_id         uuid REFERENCES clients(id) ON DELETE SET NULL,
  original_filename text NOT NULL,
  storage_path      text NOT NULL,
  file_size_bytes   integer,
  mime_type         text,
  doc_type          text,                  -- 'purchase_register'|'supplier_export'|'recon_export'|'other'
  uploaded_by       uuid NOT NULL,
  deleted_at        timestamptz,
  created_at        timestamptz DEFAULT now()
);

CREATE TABLE vat_reconciliations (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL,
  client_id                uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  period_start             date NOT NULL,
  period_end               date NOT NULL,
  status                   text DEFAULT 'running',  -- 'running'|'completed'|'error'
  total_invoices           integer,
  matched_exact            integer,
  matched_fuzzy            integer,
  partial_match            integer,
  no_match                 integer,
  total_vat_claimed_bdt    numeric(15, 2),
  safe_itc_bdt             numeric(15, 2),
  at_risk_itc_bdt          numeric(15, 2),
  purchase_register_doc_id uuid REFERENCES documents(id),
  supplier_data_doc_id     uuid REFERENCES documents(id),
  notes                    text,
  run_by                   uuid NOT NULL,
  started_at               timestamptz DEFAULT now(),
  completed_at             timestamptz,
  UNIQUE (client_id, period_start, period_end)
);

CREATE TABLE recon_line_items (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             uuid NOT NULL,
  reconciliation_id     uuid NOT NULL REFERENCES vat_reconciliations(id) ON DELETE CASCADE,
  -- purchase register data
  pr_invoice_no         text,
  pr_supplier_bin       text,
  pr_supplier_name      text,
  pr_invoice_date       date,
  pr_taxable_amount_bdt numeric(15, 2),
  pr_vat_amount_bdt     numeric(15, 2),
  -- supplier-filed data (if matched)
  sf_invoice_no         text,
  sf_invoice_date       date,
  sf_taxable_amount_bdt numeric(15, 2),
  sf_vat_amount_bdt     numeric(15, 2),
  -- match result
  match_status          text NOT NULL,  -- 'exact'|'fuzzy'|'partial'|'no_match'
  match_score           numeric(3, 2),
  discrepancy_flags     jsonb,
  ca_override           text,           -- 'approved'|'disputed'|'ignore'
  ca_notes              text,
  created_at            timestamptz DEFAULT now()
);
```

### 6.3 Indexes

```sql
CREATE INDEX idx_clients_tenant_active ON clients(tenant_id, deleted_at);
CREATE INDEX idx_events_tenant_due     ON compliance_events(tenant_id, due_date, status);
CREATE INDEX idx_events_client         ON compliance_events(client_id, status);
CREATE INDEX idx_documents_tenant      ON documents(tenant_id, client_id, deleted_at);
CREATE INDEX idx_recons_client         ON vat_reconciliations(client_id, period_start DESC);
CREATE INDEX idx_recon_items_recon     ON recon_line_items(reconciliation_id, match_status);
CREATE INDEX idx_recon_items_bin       ON recon_line_items(pr_supplier_bin);
```

### 6.4 RLS pattern (applied to every tenant-scoped table)

```sql
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON clients
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));
```

### 6.5 Audit log trigger

A single Postgres trigger function fires on insert/update/delete for every tenant-scoped table and writes to `audit_log`. `tenant_id` comes from the row; `user_id` comes from `current_setting('request.jwt.claim.sub', true)`. Defined once, attached to every tenant-scoped table.

When the backend uses the service-role to write on the user's behalf, it must explicitly set the JWT claim before the transaction so the trigger captures the correct `user_id`:

```python
await supabase.rpc("set_request_user", {"user_id": str(user_id)}).execute()
```

(Or equivalent `SET LOCAL request.jwt.claim.sub = ...` via a wrapper RPC.) Worth a 2-hour spike in week 1 to confirm the pattern works end-to-end.

## 7. The reconciliation flow

### 7.1 End-to-end sequence

```
1. CA opens /clients/:id/recon/new
2. CA uploads purchase_register.xlsx
   → frontend uploads directly to Supabase Storage at:
     tenants/{tenant_id}/clients/{client_id}/recons/{uuid}/purchase_register.xlsx
   → frontend inserts a row into `documents`
     (doc_type='purchase_register') → gets doc_id_pr
3. CA uploads supplier_export.xlsx → same flow → doc_id_sf
4. CA picks period (period_start, period_end) and clicks "Run reconciliation"
5. Frontend POSTs to FastAPI:
     POST /api/v1/reconciliations
     Authorization: Bearer <supabase_jwt>
     {
       "client_id": "...",
       "period_start": "2024-01-01",
       "period_end": "2024-01-31",
       "purchase_register_doc_id": "...",
       "supplier_data_doc_id": "..."
     }
6. Backend:
   a. Validates JWT, extracts tenant_id, user_id
   b. Validates that both doc_ids belong to the same tenant + client (defensive)
   c. Inserts `vat_reconciliations` row with status='running'
   d. Downloads both XLSX files from Supabase Storage (signed URLs)
   e. Parses with pandas. Validates required columns.
      On column mismatch → 400 INVALID_XLSX_FORMAT with specific missing column names.
   f. Runs matching engine (see 7.2)
   g. Bulk inserts recon_line_items
   h. Updates vat_reconciliations row with totals + status='completed'
   i. Returns { reconciliation_id }
7. Frontend redirects to /clients/:id/recon/:reconciliation_id
8. Report page reads `vat_reconciliations` + `recon_line_items` directly from Supabase
```

### 7.2 Matching engine

```
# Match priority — first match wins, evaluated per purchase-register row

EXACT  (score 1.00):
  supplier_bin matches
  AND normalize(pr_invoice_no) == normalize(sf_invoice_no)
  AND pr_invoice_date == sf_invoice_date
  AND |pr_taxable_amount_bdt - sf_taxable_amount_bdt| < 0.01
  AND |pr_vat_amount_bdt - sf_vat_amount_bdt| < 0.01

FUZZY  (score 0.80):
  supplier_bin matches
  AND normalize(pr_invoice_no) == normalize(sf_invoice_no)
  AND |pr_invoice_date - sf_invoice_date| <= 3 days
  AND |pr_taxable - sf_taxable| / sf_taxable <= 0.005    -- 0.5% tolerance

PARTIAL (score 0.40):
  supplier_bin appears in supplier pool,
  but no invoice_no match found

NO_MATCH (score 0.00):
  supplier_bin NOT present in supplier pool at all
```

**Invoice number normalization:**
- Lowercase
- Strip spaces and hyphens
- Strip leading zeros from each numeric segment
- e.g., `"INV-0023/2024"` → `"inv23/2024"`

**Aggregates:**
- `safe_itc_bdt` = sum of `pr_vat_amount_bdt` where `match_status IN ('exact', 'fuzzy')`
- `at_risk_itc_bdt` = sum of `pr_vat_amount_bdt` where `match_status IN ('partial', 'no_match')`
- `total_vat_claimed_bdt` = `safe_itc_bdt + at_risk_itc_bdt`

**Discrepancy flags (JSONB on each line item):**
- For FUZZY matches, populate `{ "date_off_by_days": int, "amount_diff_bdt": decimal, "amount_diff_pct": float }`
- For PARTIAL matches: `{ "reason": "no_invoice_no_match" }`
- For NO_MATCH: `{ "reason": "supplier_bin_not_filed" }`

### 7.3 XLSX input contract

**Purchase register columns** (case-insensitive):
- `Invoice No`
- `Supplier BIN`
- `Supplier Name`
- `Invoice Date`
- `Taxable Amount (BDT)`
- `VAT Amount (BDT)`

**Supplier export columns** (case-insensitive):
- `Invoice No`
- `Invoice Date`
- `Taxable Amount (BDT)`
- `VAT Amount (BDT)`
- `Buyer BIN`

If any required column is missing → backend returns `400 INVALID_XLSX_FORMAT` with a message naming exactly which column is missing in which file. Sample template XLSX files are downloadable from the upload UI's "How to export from NBR" help link.

## 8. Compliance calendar

A static Postgres function `generate_compliance_events(client_id uuid, from_date date, to_date date)` is called via Supabase RPC from the frontend in two cases:
1. When a client is created.
2. When a client's `entity_type` or `is_vat_registered` changes (frontend re-invokes after the update).

The function is idempotent — it skips any (obligation, period) row that already exists.

It:

1. Reads the client's `entity_type`, `is_vat_registered`, `fiscal_year_end`.
2. Looks up applicable obligations from `bd_obligation_definitions`.
3. For each obligation, computes the due dates in the range using known BD rules:
   - **VAT return (Mushak 9.1):** 15th of the month following the period
   - **TDS return:** 20th of the month following the period
   - **TDS challan deposit:** 7th of the month following the period
   - **Company income tax return:** 15th January following June 30 FY end
   - **Individual income tax return:** 30th November annually
   - **RJSC annual return:** 21 days after AGM (default: 18 months from incorporation, then annually)
4. Inserts one row per (obligation, period) into `compliance_events`, idempotent (skip on conflict).

Frontend reads `compliance_events` directly via Supabase. Dashboard query: events where `due_date BETWEEN today AND today + 30 days` ordered by `due_date`.

CA can update `status` to `filed` (with `filed_date`) inline from the calendar view; this writes to Supabase directly (RLS-protected).

## 9. UI screens

| Route | Purpose | Engineering shape |
|-------|---------|-------------------|
| `/login` | Supabase Auth email/password | shadcn Card + Form, supabase-js auth methods |
| `/onboard` | Create tenant + user_profile (first-time only) | One form, redirects to `/dashboard` after submit. Guard: only rendered if user has no `user_profile` yet. |
| `/dashboard` | Across-clients view: next 30 days of deadlines, recent recons, total at-risk ITC | All reads via Supabase + TanStack Query |
| `/clients` | Table list with search, "Add client" modal | Direct Supabase query |
| `/clients/:id` | Client profile + tabs: Reconciliations, Documents, Calendar | Tab content lazy-loaded |
| `/clients/:id/recon/new` | Two file dropzones, period picker, "Run" button. Sample template downloads. | Uploads to Supabase Storage, then POST to FastAPI |
| `/clients/:id/recon/:id` | **The hero report screen.** Hero card with at-risk ITC in BDT, breakdown donut chart, line items table with match-status color coding, drilldown panel, CA override controls, "Export to XLSX" button | Reads from Supabase. Color coding: green=exact, yellow=fuzzy, orange=partial, red=no_match. |

**Half of the frontend time budget goes to the recon report screen.** Everything else is supporting cast.

## 10. Phasing

| Week | Phase | Deliverables | Acceptance test |
|------|-------|--------------|-----------------|
| **1** | **A. Foundation** | Apply schema + RLS + audit trigger to Supabase via migrations checked into repo. Seed `bd_obligation_definitions`. Clean up backend scaffold (delete `ai/`, drop dropped deps from requirements, fix sync-in-async bugs in `dependencies.py`, fix `/ready` endpoint). Move `.env` to `.gitignore`, add `.env.example`. Vite + React + TS scaffold with Supabase client, React Router, TanStack Query, shadcn init, base layout. Supabase Auth login/signup pages. `/onboard` page. Dockerfile + Cloud Run deploy script. | Sign up → land on `/onboard` → create firm → land on empty dashboard. Refresh stays logged in. Cross-tenant access via raw SQL on Supabase returns 0 rows. |
| **2** | **B. Clients** | Clients list page (table, search, "Add client" modal). Client detail page (profile + tab scaffolding). Add/edit form with BIN/TIN validation (Zod). Soft delete. On client create, frontend calls `generate_compliance_events` Postgres function. | Add 5 clients with mixed entity types. Each client's calendar populates with correct deadlines. Edit/delete works. Trigger writes to `audit_log`. |
| **3-4** | **C. Reconciliation (the hero)** | **Backend:** `POST /api/v1/reconciliations` endpoint (sync). XLSX parser with column validation + clear errors. Matching engine module (pure functions, fully unit-tested). Bulk insert of line items. Pytest fixtures: synthetic 200-row register + supplier export with intentional mismatches. **Frontend:** `/clients/:id/recon/new` upload page. `/clients/:id/recon/:id` report page with hero card, donut chart, color-coded line items table, drilldown panel, CA override dropdowns, XLSX export. List view of all recons under a client. | Sample register with 200 rows + supplier export → recon completes in <3s. At-risk ITC matches manually-computed expected value. CA override on a row updates and persists. Export XLSX downloads correctly. |
| **5** | **D. Calendar + Dashboard** | `/dashboard` with next 30 days grouped by week, count of overdue per client, recent recons. Calendar tab on client detail (table view, filter by status). Inline status update on a calendar event. Polish empty states across the app. | Dashboard shows correct upcoming events for a firm with 5 clients. Marking VAT return as 'filed' updates Supabase + audit log. Empty states render clean copy on a fresh tenant. |
| **6** | **E. Polish + ship** | Sample data seeder (one tenant, 3 demo clients, 1 sample recon with realistic mismatches). Loading states, error boundaries, 404 page. `/health` and `/ready` actually verify Supabase connectivity. Deploy frontend to Vercel, backend to Cloud Run with `min_instances=1`. Smoke test on deployed env. README with setup instructions. `/` redirects to `/login` (no marketing page in MVP). | Stranger CA can sign up on the deployed URL, follow a 5-min walkthrough, see a recon report with realistic numbers, feel "I'd pay for this." |

## 11. Risks to watch

1. **The XLSX column contract is friction.** Real CAs export different column shapes from Tally / NBR. We're shipping a strict contract and sample template files. If user testing reveals adoption friction, week 7 work is "fuzzy column matching" or a manual column-mapping UI.

2. **First-time deadline generation correctness.** The BD deadline rules are well-known but lightly sourced in the spec. Before shipping, sanity-check 3-4 specific deadlines (e.g., FY2024-25 company IT return for a June-30 FY-end company) against an authoritative source (NBR website, ICAB practitioner if accessible).

3. **`auth.uid()` in audit trigger when backend uses service-role.** When the backend writes on the user's behalf, RLS won't apply, but `auth.uid()` won't be set either — the audit trigger would store NULL for `user_id`. Solution: backend explicitly sets `request.jwt.claim.sub` via `SET LOCAL` before each transaction. **Worth a 2-hour spike in week 1 to confirm the pattern works end-to-end.**

4. **Cloud Run cold starts.** First request after idle could take 3-5s. For the demo "stranger CA" test, a cold-starting recon endpoint on first click would be a bad first impression. Mitigation: `min_instances=1` on Cloud Run during demo period (~$5/month).

## 12. Success criteria for the MVP

A stranger Bangladeshi CA can:

1. Sign up and create a firm in <60 seconds.
2. Add a client with valid BIN/TIN in <30 seconds.
3. Upload a sample purchase register XLSX + supplier export XLSX.
4. See a recon report within 3 seconds showing:
   - Total invoices reconciled
   - Match-type breakdown (exact / fuzzy / partial / no match) with color coding
   - **At-risk ITC amount in BDT, prominently displayed.**
5. Drill into a no-match line item and see why it failed.
6. Mark a line item as "approved" via CA override.
7. Export the report to XLSX.
8. See the client's upcoming compliance deadlines on the dashboard.

If a stranger CA can do all of this on the deployed URL without help and walks away thinking "I'd pay for this monthly," the MVP succeeded.
