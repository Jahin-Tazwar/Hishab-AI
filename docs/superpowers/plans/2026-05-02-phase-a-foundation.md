# Phase A — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the database schema (with RLS + audit trigger) to Supabase, clean up the existing backend scaffold, and build a frontend that lets a user sign up, create a tenant (CA firm), and land on an empty dashboard.

**Architecture:** Frontend (React 18 + TypeScript + Vite) talks to Supabase directly for auth and onboarding. FastAPI backend exists but is dormant in this phase (no business endpoints yet — those come in Phase C). Schema lives in versioned SQL migration files and is applied to the existing Supabase project (`qlrqbqisavkfxywkiuca`, Singapore region).

**Tech Stack:** Supabase (Auth + Postgres + Storage), FastAPI 0.115, Python 3.11+, React 18 + TypeScript + Vite, shadcn/ui + Tailwind, TanStack Query, Zustand, React Router 6, React Hook Form + Zod.

**Reference spec:** [`docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md`](../specs/2026-05-02-hishabai-mvp-design.md)

**Acceptance criteria for Phase A:**
1. User signs up via Supabase Auth on the deployed (or local) frontend → lands on `/onboard`.
2. User submits firm name + their full name → tenant + user_profile rows created → lands on empty `/dashboard`.
3. Refreshing the browser keeps the user signed in.
4. Cross-tenant access is blocked: querying another tenant's `clients` rows from a logged-in user returns 0 rows.
5. The audit trigger captures `user_id` correctly when the backend writes via the service-role (validated by the spike test in Task 18).
6. Backend has zero unused dependencies; existing sync-in-async bugs are fixed; tests pass.

---

## File structure (Phase A)

**New directories:**
- `migrations/` — SQL migration files (tracked in git, applied to Supabase via MCP or psql)
- `frontend/` — Vite + React + TypeScript app
- `backend/tests/` — pytest test suite

**New files:**
- `migrations/0001_public_schema.sql`
- `migrations/0002_tenant_tables.sql`
- `migrations/0003_indexes.sql`
- `migrations/0004_rls_policies.sql`
- `migrations/0005_audit_trigger.sql`
- `migrations/0006_set_request_user.sql`
- `migrations/0007_generate_compliance_events.sql`
- `migrations/0008_seed_obligations.sql`
- `migrations/README.md`
- `backend/Dockerfile`
- `backend/.env.example`
- `backend/pytest.ini`
- `backend/tests/__init__.py`
- `backend/tests/conftest.py`
- `backend/tests/test_health.py`
- `backend/tests/test_dependencies.py`
- `backend/tests/test_middleware.py`
- `backend/tests/integration/__init__.py`
- `backend/tests/integration/test_audit_trigger_spike.py`
- `frontend/` — entire scaffold (created by Vite)
- `README.md` — project setup instructions
- `.env.example` — root, points to backend/frontend env templates

**Files modified:**
- `backend/requirements.txt` — drop unused deps, add pytest + httpx
- `backend/app/config.py` — strip Vertex AI / Redis / Celery / MIS settings
- `backend/app/database.py` — remove SQLAlchemy section
- `backend/app/dependencies.py` — wrap sync supabase calls in `asyncio.to_thread`, add `set_request_user` helper
- `backend/app/main.py` — fix `/ready`, add request_id middleware

**Files deleted:**
- `backend/app/ai/` (entire folder — `__init__.py` and `gemini_client.py`)

---

## Task 1: Initialize git and add `.env.example`

**Files:**
- Create: `backend/.env.example`, `frontend/.env.example` (frontend file in Task 20)
- Modify: `.gitignore` (verify completeness)

- [ ] **Step 1: Initialize git repository**

```bash
cd "C:/project/Hishab AI"
git init
git config core.autocrlf false
git config core.eol lf
```

Expected: `Initialized empty Git repository`

- [ ] **Step 2: Verify `.gitignore` covers required patterns**

The existing `.gitignore` already covers `.env`, `__pycache__/`, `node_modules/`, `dist/`, `.vite/`. Verify by reading it. If anything is missing, add: `.idea/`, `.vscode/`, `*.local`, `coverage/`, `htmlcov/`, `.coverage`.

```bash
cat .gitignore
```

Expected: Contains at minimum `.env`, `__pycache__/`, `node_modules/`, `dist/`.

- [ ] **Step 3: Create `backend/.env.example`**

```bash
# backend/.env.example — copy to .env and fill in real values

# ── Supabase ──────────────────────────────────────────────────────────────
SUPABASE_URL=https://qlrqbqisavkfxywkiuca.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=

# ── App ───────────────────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=DEBUG
MAX_UPLOAD_SIZE_MB=20

# ── Storage ───────────────────────────────────────────────────────────────
STORAGE_BUCKET=documents
```

- [ ] **Step 4: Stage initial files (excluding `.env`)**

```bash
git add .gitignore backend/.env.example
git status
```

Expected: `.env` is NOT listed; `.env.example` IS listed.

- [ ] **Step 5: Initial commit**

```bash
git add CLAUDE.md PROJECT.md project_evaluation.md docs/ backend/
git status                          # verify .env is NOT staged
git commit -m "chore: initial repository state with existing scaffold and docs"
```

---

## Task 2: Migration 0001 — public schema

**Files:**
- Create: `migrations/0001_public_schema.sql`
- Create: `migrations/README.md`

- [ ] **Step 1: Create `migrations/README.md`**

```markdown
# Migrations

SQL migration files for the Supabase Postgres database. Applied in numerical order.

## Apply migrations

**Option A — Supabase MCP (preferred):**
Use `mcp__supabase__apply_migration` tool with the contents of each file.

**Option B — Supabase Dashboard:**
SQL Editor → paste each file's contents → Run.

**Option C — psql directly:**
```bash
psql "$DATABASE_URL" -f migrations/0001_public_schema.sql
psql "$DATABASE_URL" -f migrations/0002_tenant_tables.sql
# ...etc
```

## Order

1. `0001_public_schema.sql` — system tables (no RLS)
2. `0002_tenant_tables.sql` — tenant-scoped tables (RLS-ready, but RLS not yet enabled)
3. `0003_indexes.sql` — performance indexes
4. `0004_rls_policies.sql` — enable RLS + policies for tenant-scoped tables
5. `0005_audit_trigger.sql` — audit_log trigger function + applications
6. `0006_set_request_user.sql` — RPC for backend to set request user
7. `0007_generate_compliance_events.sql` — calendar event generator function
8. `0008_seed_obligations.sql` — seed `bd_obligation_definitions`

## Rollback

This MVP does not implement down-migrations. To roll back, drop the affected tables manually and re-apply from the desired migration onward.
```

- [ ] **Step 2: Write `migrations/0001_public_schema.sql`**

```sql
-- 0001_public_schema.sql
-- System-level tables (no RLS) — tenants, user_profiles, audit_log, bd_obligation_definitions

-- ============================================================
-- TENANTS — one row per CA firm
-- ============================================================

CREATE TABLE tenants (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_name     text NOT NULL,
  firm_name_bn  text,
  icab_reg_no   text UNIQUE,
  email         text NOT NULL,
  phone         text,
  address       text,
  plan          text NOT NULL DEFAULT 'starter',
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- USER_PROFILES — links auth.users to a tenant
-- ============================================================

CREATE TABLE user_profiles (
  id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  full_name   text NOT NULL,
  role        text NOT NULL DEFAULT 'firm_admin',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_profiles_tenant ON user_profiles(tenant_id);

-- ============================================================
-- AUDIT_LOG — append-only mutation log for tenant-scoped tables
-- ============================================================

CREATE TABLE audit_log (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  user_id     uuid,
  action      text NOT NULL CHECK (action IN ('insert', 'update', 'delete')),
  table_name  text NOT NULL,
  row_id      uuid NOT NULL,
  before      jsonb,
  after       jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_tenant_table ON audit_log(tenant_id, table_name, created_at DESC);

-- ============================================================
-- BD_OBLIGATION_DEFINITIONS — static seed of known BD obligations
-- ============================================================

CREATE TABLE bd_obligation_definitions (
  obligation_type   text PRIMARY KEY,
  display_name      text NOT NULL,
  applies_to        text[] NOT NULL,    -- entity_types: 'company','individual',etc.
  requires_vat_reg  boolean NOT NULL DEFAULT false,
  cadence           text NOT NULL CHECK (cadence IN ('monthly', 'quarterly', 'annual')),
  due_rule          text NOT NULL,      -- human-readable; actual logic in generate_compliance_events()
  law_reference     text,
  penalty_note      text
);
```

- [ ] **Step 3: Verify SQL is syntactically valid**

There's no easy lint locally without a Postgres connection. Verify by reading the file end-to-end and checking that:
- All `CREATE TABLE` statements have matching parentheses
- All `REFERENCES` point to tables defined earlier (or auth.users which is built-in)
- All `CHECK` constraints have valid syntax

- [ ] **Step 4: Commit**

```bash
git add migrations/0001_public_schema.sql migrations/README.md
git commit -m "feat(migrations): add public schema (tenants, user_profiles, audit_log, bd_obligation_definitions)"
```

---

## Task 3: Migration 0002 — tenant-scoped tables

**Files:**
- Create: `migrations/0002_tenant_tables.sql`

- [ ] **Step 1: Write `migrations/0002_tenant_tables.sql`**

```sql
-- 0002_tenant_tables.sql
-- Tenant-scoped tables. Every table has tenant_id. RLS will be enabled in 0004.

-- ============================================================
-- CLIENTS — the CA firm's clients (companies, individuals, etc.)
-- ============================================================

CREATE TABLE clients (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name              text NOT NULL,
  name_bn           text,
  tin               text CHECK (tin ~ '^\d{12}$' OR tin IS NULL),
  bin               text CHECK (bin ~ '^\d{9}$'  OR bin IS NULL),
  entity_type       text NOT NULL CHECK (entity_type IN ('company','individual','partnership','ngo','bank')),
  industry          text,
  fiscal_year_end   text NOT NULL DEFAULT '06-30',
  is_vat_registered boolean NOT NULL DEFAULT false,
  contact_email     text,
  contact_phone     text,
  notes             text,
  deleted_at        timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  created_by        uuid NOT NULL
);

-- ============================================================
-- COMPLIANCE_OBLIGATIONS — which obligations apply per client
-- ============================================================

CREATE TABLE compliance_obligations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  obligation_type text NOT NULL REFERENCES bd_obligation_definitions(obligation_type),
  is_active       boolean NOT NULL DEFAULT true,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- COMPLIANCE_EVENTS — concrete due dates per (client, obligation, period)
-- ============================================================

CREATE TABLE compliance_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  obligation_type text NOT NULL,
  period_start    date NOT NULL,
  period_end      date NOT NULL,
  due_date        date NOT NULL,
  status          text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','filed','overdue','waived','na')),
  filed_date      date,
  notes           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, obligation_type, period_start)
);

-- ============================================================
-- DOCUMENTS — files uploaded to Supabase Storage (XLSX inputs, recon exports)
-- ============================================================

CREATE TABLE documents (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id         uuid REFERENCES clients(id) ON DELETE SET NULL,
  original_filename text NOT NULL,
  storage_path      text NOT NULL,
  file_size_bytes   integer,
  mime_type         text,
  doc_type          text CHECK (doc_type IN
                    ('purchase_register','supplier_export','recon_export','other')),
  uploaded_by       uuid NOT NULL,
  deleted_at        timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- VAT_RECONCILIATIONS — one per recon run
-- ============================================================

CREATE TABLE vat_reconciliations (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id                uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  period_start             date NOT NULL,
  period_end               date NOT NULL,
  status                   text NOT NULL DEFAULT 'running'
                           CHECK (status IN ('running','completed','error')),
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
  started_at               timestamptz NOT NULL DEFAULT now(),
  completed_at             timestamptz,
  UNIQUE (client_id, period_start, period_end)
);

-- ============================================================
-- RECON_LINE_ITEMS — per-invoice match results
-- ============================================================

CREATE TABLE recon_line_items (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
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
  match_status          text NOT NULL CHECK (match_status IN ('exact','fuzzy','partial','no_match')),
  match_score           numeric(3, 2),
  discrepancy_flags     jsonb,
  ca_override           text CHECK (ca_override IN ('approved','disputed','ignore') OR ca_override IS NULL),
  ca_notes              text,
  created_at            timestamptz NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Verify foreign-key references**

Read the file. Confirm: every `REFERENCES` points to a table that exists (either in 0001 or earlier in 0002).

- [ ] **Step 3: Commit**

```bash
git add migrations/0002_tenant_tables.sql
git commit -m "feat(migrations): add tenant-scoped tables (clients, obligations, events, documents, recons, line_items)"
```

---

## Task 4: Migration 0003 — indexes

**Files:**
- Create: `migrations/0003_indexes.sql`

- [ ] **Step 1: Write `migrations/0003_indexes.sql`**

```sql
-- 0003_indexes.sql — performance indexes for common access paths

CREATE INDEX idx_clients_tenant_active     ON clients(tenant_id, deleted_at);
CREATE INDEX idx_clients_tenant_name       ON clients(tenant_id, name);

CREATE INDEX idx_obligations_client        ON compliance_obligations(client_id, is_active);

CREATE INDEX idx_events_tenant_due         ON compliance_events(tenant_id, due_date, status);
CREATE INDEX idx_events_client_status      ON compliance_events(client_id, status);

CREATE INDEX idx_documents_tenant          ON documents(tenant_id, client_id, deleted_at);

CREATE INDEX idx_recons_client_period      ON vat_reconciliations(client_id, period_start DESC);

CREATE INDEX idx_recon_items_recon         ON recon_line_items(reconciliation_id, match_status);
CREATE INDEX idx_recon_items_supplier_bin  ON recon_line_items(pr_supplier_bin);
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0003_indexes.sql
git commit -m "feat(migrations): add performance indexes for tenant-scoped tables"
```

---

## Task 5: Migration 0004 — RLS policies

**Files:**
- Create: `migrations/0004_rls_policies.sql`

- [ ] **Step 1: Write `migrations/0004_rls_policies.sql`**

```sql
-- 0004_rls_policies.sql
-- Enable RLS and apply tenant_isolation policy on every tenant-scoped table.
-- Pattern: tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid())

-- ============================================================
-- USER_PROFILES — special: users can only read their own profile
-- ============================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_profile_self_read ON user_profiles
  FOR SELECT USING (id = auth.uid());

CREATE POLICY user_profile_self_insert ON user_profiles
  FOR INSERT WITH CHECK (id = auth.uid());

CREATE POLICY user_profile_self_update ON user_profiles
  FOR UPDATE USING (id = auth.uid()) WITH CHECK (id = auth.uid());

-- ============================================================
-- TENANTS — users can read/update their own tenant
-- ============================================================

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_member_read ON tenants
  FOR SELECT USING (
    id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid())
  );

CREATE POLICY tenant_member_update ON tenants
  FOR UPDATE
  USING      (id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

-- INSERT into tenants is done during onboarding via a Postgres function (see 0007 area)
-- or directly with the user's session JWT. For MVP, allow authenticated users to insert
-- a tenant (they can only create their own first one).
CREATE POLICY tenant_self_insert ON tenants
  FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);

-- ============================================================
-- TENANT-SCOPED TABLES — same isolation pattern for all
-- ============================================================

-- Helper: the policy expression. Repeated for clarity.
-- USING (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON clients
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE compliance_obligations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON compliance_obligations
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE compliance_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON compliance_events
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON documents
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE vat_reconciliations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON vat_reconciliations
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE recon_line_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON recon_line_items
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

-- ============================================================
-- AUDIT_LOG — read-only for tenant members; writes only via trigger (security definer)
-- ============================================================

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_log_tenant_read ON audit_log
  FOR SELECT USING (
    tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid())
  );
-- No INSERT/UPDATE/DELETE policy — only the trigger (SECURITY DEFINER) writes here.
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0004_rls_policies.sql
git commit -m "feat(migrations): enable RLS and tenant isolation policies on all tables"
```

---

## Task 6: Migration 0005 — audit trigger

**Files:**
- Create: `migrations/0005_audit_trigger.sql`

- [ ] **Step 1: Write `migrations/0005_audit_trigger.sql`**

```sql
-- 0005_audit_trigger.sql
-- Generic audit trigger: writes every insert/update/delete on tenant-scoped tables
-- to audit_log. user_id pulled from current_setting('request.jwt.claim.sub', true).

CREATE OR REPLACE FUNCTION audit_log_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id  uuid;
  v_claim    text;
BEGIN
  -- Try to read the JWT subject claim. May be NULL when called by:
  -- - the backend with service-role key (unless set_request_user was called first)
  -- - a Postgres function not in a user-initiated transaction
  v_claim := current_setting('request.jwt.claim.sub', true);
  IF v_claim IS NOT NULL AND v_claim <> '' THEN
    BEGIN
      v_user_id := v_claim::uuid;
    EXCEPTION WHEN OTHERS THEN
      v_user_id := NULL;
    END;
  END IF;

  IF (TG_OP = 'INSERT') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (NEW.tenant_id, v_user_id, 'insert', TG_TABLE_NAME, NEW.id, NULL, to_jsonb(NEW));
    RETURN NEW;
  ELSIF (TG_OP = 'UPDATE') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (NEW.tenant_id, v_user_id, 'update', TG_TABLE_NAME, NEW.id, to_jsonb(OLD), to_jsonb(NEW));
    RETURN NEW;
  ELSIF (TG_OP = 'DELETE') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (OLD.tenant_id, v_user_id, 'delete', TG_TABLE_NAME, OLD.id, to_jsonb(OLD), NULL);
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$;

-- Apply to every tenant-scoped table

CREATE TRIGGER audit_clients
  AFTER INSERT OR UPDATE OR DELETE ON clients
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_compliance_obligations
  AFTER INSERT OR UPDATE OR DELETE ON compliance_obligations
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_compliance_events
  AFTER INSERT OR UPDATE OR DELETE ON compliance_events
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_documents
  AFTER INSERT OR UPDATE OR DELETE ON documents
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_vat_reconciliations
  AFTER INSERT OR UPDATE OR DELETE ON vat_reconciliations
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_recon_line_items
  AFTER INSERT OR UPDATE OR DELETE ON recon_line_items
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0005_audit_trigger.sql
git commit -m "feat(migrations): add audit trigger function and apply to tenant-scoped tables"
```

---

## Task 7: Migration 0006 — `set_request_user` RPC

**Files:**
- Create: `migrations/0006_set_request_user.sql`

- [ ] **Step 1: Write `migrations/0006_set_request_user.sql`**

```sql
-- 0006_set_request_user.sql
-- RPC the backend calls before service-role writes, so the audit trigger
-- can capture the correct user_id.
--
-- IMPORTANT: set_config(..., true) is transaction-local. Effective only within
-- the same transaction. Backend must call this and the subsequent write in the
-- same supabase-py call chain (i.e., same HTTP connection / transaction).
-- The Task 18 spike validates whether this works end-to-end with supabase-py.

CREATE OR REPLACE FUNCTION set_request_user(p_user_id uuid) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  PERFORM set_config('request.jwt.claim.sub', p_user_id::text, true);
END;
$$;

-- Allow authenticated and service_role to call it
GRANT EXECUTE ON FUNCTION set_request_user(uuid) TO authenticated, service_role;
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0006_set_request_user.sql
git commit -m "feat(migrations): add set_request_user RPC for backend audit context"
```

---

## Task 8: Migration 0007 — `generate_compliance_events`

**Files:**
- Create: `migrations/0007_generate_compliance_events.sql`

- [ ] **Step 1: Write `migrations/0007_generate_compliance_events.sql`**

```sql
-- 0007_generate_compliance_events.sql
-- Generates compliance_events rows for a client based on their entity_type
-- and is_vat_registered status. Idempotent: skips (client, obligation, period_start)
-- combinations that already exist (uses ON CONFLICT DO NOTHING via the table's UNIQUE).

CREATE OR REPLACE FUNCTION generate_compliance_events(
  p_client_id uuid,
  p_from_date date,
  p_to_date   date
) RETURNS integer  -- count of events inserted
LANGUAGE plpgsql
SECURITY INVOKER  -- runs as the calling user; RLS still applies
AS $$
DECLARE
  v_client            clients%ROWTYPE;
  v_obligation        bd_obligation_definitions%ROWTYPE;
  v_period_start      date;
  v_period_end        date;
  v_due_date          date;
  v_inserted_count    integer := 0;
BEGIN
  -- Fetch the client row (RLS-filtered: caller must own this client)
  SELECT * INTO v_client FROM clients WHERE id = p_client_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Client % not found or not accessible', p_client_id;
  END IF;

  -- Loop over applicable obligations
  FOR v_obligation IN
    SELECT *
    FROM bd_obligation_definitions
    WHERE v_client.entity_type = ANY(applies_to)
      AND (NOT requires_vat_reg OR v_client.is_vat_registered)
  LOOP
    -- Generate periods + due dates based on cadence
    IF v_obligation.cadence = 'monthly' THEN
      v_period_start := date_trunc('month', p_from_date)::date;
      WHILE v_period_start <= p_to_date LOOP
        v_period_end := (v_period_start + interval '1 month - 1 day')::date;
        -- Due date depends on obligation_type
        v_due_date := CASE v_obligation.obligation_type
          WHEN 'vat_return'   THEN (v_period_end + interval '15 days')::date
          WHEN 'tds_return'   THEN (v_period_end + interval '20 days')::date
          WHEN 'tds_deposit'  THEN (v_period_end + interval '7 days')::date
          ELSE (v_period_end + interval '15 days')::date
        END;

        INSERT INTO compliance_events
          (tenant_id, client_id, obligation_type, period_start, period_end, due_date)
        VALUES
          (v_client.tenant_id, v_client.id, v_obligation.obligation_type,
           v_period_start, v_period_end, v_due_date)
        ON CONFLICT (client_id, obligation_type, period_start) DO NOTHING;

        IF FOUND THEN v_inserted_count := v_inserted_count + 1; END IF;

        v_period_start := (v_period_start + interval '1 month')::date;
      END LOOP;

    ELSIF v_obligation.cadence = 'annual' THEN
      -- BD fiscal year: July 1 — June 30
      -- Compute the FY start that falls within (or before) the range
      v_period_start := CASE
        WHEN extract(month FROM p_from_date) >= 7 THEN
          make_date(extract(year FROM p_from_date)::int, 7, 1)
        ELSE
          make_date(extract(year FROM p_from_date)::int - 1, 7, 1)
      END;

      WHILE v_period_start <= p_to_date LOOP
        v_period_end := (v_period_start + interval '1 year - 1 day')::date;

        v_due_date := CASE v_obligation.obligation_type
          -- Company IT return: 15 January after FY end (FY ends June 30)
          WHEN 'income_tax_company' THEN
            make_date(extract(year FROM v_period_end)::int + 1, 1, 15)
          -- Individual IT return: 30 November of FY end year
          WHEN 'income_tax_individual' THEN
            make_date(extract(year FROM v_period_end)::int, 11, 30)
          -- RJSC annual return: default 21 days after FY end (proxy for AGM)
          WHEN 'rjsc_annual' THEN
            (v_period_end + interval '21 days')::date
          ELSE
            (v_period_end + interval '60 days')::date
        END;

        INSERT INTO compliance_events
          (tenant_id, client_id, obligation_type, period_start, period_end, due_date)
        VALUES
          (v_client.tenant_id, v_client.id, v_obligation.obligation_type,
           v_period_start, v_period_end, v_due_date)
        ON CONFLICT (client_id, obligation_type, period_start) DO NOTHING;

        IF FOUND THEN v_inserted_count := v_inserted_count + 1; END IF;

        v_period_start := (v_period_start + interval '1 year')::date;
      END LOOP;
    END IF;
    -- 'quarterly' cadence not yet supported (no MVP obligations use it)
  END LOOP;

  RETURN v_inserted_count;
END;
$$;

GRANT EXECUTE ON FUNCTION generate_compliance_events(uuid, date, date) TO authenticated;
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0007_generate_compliance_events.sql
git commit -m "feat(migrations): add generate_compliance_events function for calendar generation"
```

---

## Task 9: Migration 0008 — seed `bd_obligation_definitions`

**Files:**
- Create: `migrations/0008_seed_obligations.sql`

- [ ] **Step 1: Write `migrations/0008_seed_obligations.sql`**

```sql
-- 0008_seed_obligations.sql — seed bd_obligation_definitions

INSERT INTO bd_obligation_definitions
  (obligation_type, display_name, applies_to, requires_vat_reg, cadence, due_rule, law_reference, penalty_note)
VALUES
  ('vat_return',
   'VAT Return (Mushak 9.1)',
   ARRAY['company','partnership'],
   true,
   'monthly',
   '15th of the month following the period',
   'VAT Act 2012, Section 64',
   'BDT 250 per day late'),

  ('tds_return',
   'TDS Return',
   ARRAY['company','partnership','individual'],
   false,
   'monthly',
   '20th of the month following the period',
   'ITO 1984, Section 75A',
   'BDT 5,000 per month default'),

  ('tds_deposit',
   'TDS Challan Deposit',
   ARRAY['company','partnership','individual'],
   false,
   'monthly',
   '7th of the month following the period',
   'ITO 1984, Section 58',
   '2% per month interest on delayed amount'),

  ('income_tax_company',
   'Company Income Tax Return',
   ARRAY['company'],
   false,
   'annual',
   '15th January following June 30 fiscal year end',
   'ITO 1984, Section 75',
   '1% per month of tax payable'),

  ('income_tax_individual',
   'Individual Income Tax Return',
   ARRAY['individual'],
   false,
   'annual',
   '30 November annually',
   'ITO 1984, Section 75',
   '1% per month of tax payable'),

  ('rjsc_annual',
   'RJSC Annual Return',
   ARRAY['company'],
   false,
   'annual',
   '21 days after AGM (proxy: 21 days after FY end)',
   'Companies Act 1994, Section 190',
   'BDT 500 per day default')
ON CONFLICT (obligation_type) DO NOTHING;
```

- [ ] **Step 2: Commit**

```bash
git add migrations/0008_seed_obligations.sql
git commit -m "feat(migrations): seed bd_obligation_definitions with known BD compliance obligations"
```

---

## Task 10: Apply migrations to Supabase

**Files:** None modified (operational task).

- [ ] **Step 1: Verify Supabase project is reachable**

If using Supabase MCP (the user has these tools available), test with:

```
Use mcp tool: mcp__<supabase-mcp>__get_project with project_id "qlrqbqisavkfxywkiuca"
```

Expected: project metadata returned. If the MCP isn't available, use Supabase Dashboard SQL Editor instead.

- [ ] **Step 2: Apply migrations 0001 through 0008 in order**

Using Supabase MCP (preferred):

```
For each file in 0001..0008:
  Read the file contents.
  Use mcp__<supabase-mcp>__apply_migration with name=<filename> and query=<contents>.
```

Or via Supabase Dashboard SQL Editor: paste each file's contents and run, in order.

- [ ] **Step 3: Verify tables exist**

```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Expected output (10 tables):
```
audit_log
bd_obligation_definitions
clients
compliance_events
compliance_obligations
documents
recon_line_items
tenants
user_profiles
vat_reconciliations
```

- [ ] **Step 4: Verify RLS is enabled**

```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('clients','compliance_obligations','compliance_events',
                    'documents','vat_reconciliations','recon_line_items',
                    'audit_log','user_profiles','tenants')
ORDER BY tablename;
```

Expected: `rowsecurity = true` on all 9 rows.

- [ ] **Step 5: Verify seed data is present**

```sql
SELECT obligation_type, display_name, cadence FROM bd_obligation_definitions ORDER BY obligation_type;
```

Expected: 6 rows (vat_return, tds_return, tds_deposit, income_tax_company, income_tax_individual, rjsc_annual).

- [ ] **Step 6: Create the Storage bucket**

Using Supabase Dashboard → Storage → New bucket. Name: `documents`. Public: false.

Or via SQL:
```sql
INSERT INTO storage.buckets (id, name, public) VALUES ('documents', 'documents', false)
ON CONFLICT (id) DO NOTHING;
```

(No commit — this task only modifies the remote Supabase project.)

---

## Task 11: Backend cleanup — drop unused dependencies and `ai/` folder

**Files:**
- Modify: `backend/requirements.txt`
- Delete: `backend/app/ai/__init__.py`, `backend/app/ai/gemini_client.py`

- [ ] **Step 1: Replace `backend/requirements.txt`**

Replace the entire file with:

```
# Core
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.9.0
pydantic-settings==2.5.0

# Supabase
supabase==2.10.0
PyJWT==2.9.0

# Data processing
pandas==2.2.0
openpyxl==3.1.5

# Utilities
python-multipart==0.0.9
structlog==24.4.0
httpx==0.27.0
python-dateutil==2.9.0

# Tests
pytest==8.3.0
pytest-asyncio==0.24.0
pytest-cov==5.0.0
respx==0.21.1
```

Removed: `celery[redis]`, `redis`, `pytesseract`, `opencv-python-headless`, `pdfplumber`, `pdf2image`, `Pillow`, `google-cloud-aiplatform`, `google-generativeai`, `sqlalchemy[asyncio]`, `asyncpg`, `greenlet`.
Added: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (HTTP mocking).

- [ ] **Step 2: Delete the `ai/` folder**

```bash
rm -rf "backend/app/ai"
```

- [ ] **Step 3: Verify no remaining imports of deleted modules**

```bash
grep -rn "from app.ai" backend/app/ || echo "no references"
grep -rn "import sqlalchemy" backend/app/ || echo "no references"
grep -rn "celery" backend/app/ || echo "no references"
```

Expected: each prints `no references`.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git add -u backend/app/ai/
git commit -m "chore(backend): drop unused deps (sqlalchemy/celery/redis/ocr/vertex-ai) and remove ai/ module"
```

---

## Task 12: Backend — simplify `config.py`

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Replace the entire contents of `backend/app/config.py`**

```python
"""
HishabAI Backend — Application Settings

All configuration via environment variables.
Uses Supabase for auth, database, and storage.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Supabase ──────────────────────────────────────────────────────────
    SUPABASE_URL: str = "https://qlrqbqisavkfxywkiuca.supabase.co"
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # Server-side only, never expose
    SUPABASE_JWT_SECRET: str = ""        # For JWT validation

    # ── App ───────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 20
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"

    # ── Supabase Storage ──────────────────────────────────────────────────
    STORAGE_BUCKET: str = "documents"

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "refactor(config): drop Vertex AI / Redis / Celery / MIS settings (out of MVP scope)"
```

---

## Task 13: Backend — simplify `database.py`

**Files:**
- Modify: `backend/app/database.py`

- [ ] **Step 1: Replace the entire contents of `backend/app/database.py`**

```python
"""
HishabAI Backend — Supabase Client Factory

Single access pattern: supabase-py.
- get_supabase_admin(): service-role client (bypasses RLS) — backend-only.
- get_supabase_user(token): user-scoped client (RLS-enforced via the user's JWT).
"""

from supabase import Client as SupabaseClient
from supabase import create_client

from app.config import settings

_admin_client: SupabaseClient | None = None


def get_supabase_admin() -> SupabaseClient:
    """
    Returns a Supabase client using the service-role key.
    BYPASSES RLS — use only in backend code that has independently validated tenant scope.
    Never expose the service-role key to the frontend.
    """
    global _admin_client
    if _admin_client is None:
        _admin_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _admin_client


def get_supabase_user(access_token: str) -> SupabaseClient:
    """
    Returns a Supabase client authenticated as a specific user.
    RLS policies will be enforced based on the user's JWT.
    """
    client = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )
    client.auth.set_session(access_token, "")
    return client
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/database.py
git commit -m "refactor(database): drop SQLAlchemy/asyncpg; supabase-py is the single DB access path"
```

---

## Task 14: Backend — pytest configuration + first health test

**Files:**
- Create: `backend/pytest.ini`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Create `backend/pytest.ini`**

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -ra --strict-markers --tb=short
markers =
    integration: tests that hit real external services (Supabase). Skipped unless --run-integration.
```

- [ ] **Step 2: Create `backend/tests/__init__.py`**

Empty file.

```bash
touch backend/tests/__init__.py
```

- [ ] **Step 3: Create `backend/tests/conftest.py`**

```python
"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Synchronous TestClient for FastAPI app."""
    return TestClient(app)
```

- [ ] **Step 4: Create `backend/tests/test_health.py` (the failing test first)**

```python
"""Tests for health and readiness endpoints."""

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "hishabai-api"
```

- [ ] **Step 5: Run the test — it should pass (the endpoint already exists)**

```bash
cd backend
pytest tests/test_health.py -v
```

Expected: `1 passed`. If it fails with import errors, install requirements first: `pip install -r requirements.txt`.

- [ ] **Step 6: Commit**

```bash
cd ..
git add backend/pytest.ini backend/tests/
git commit -m "test(backend): set up pytest with conftest and first health endpoint test"
```

---

## Task 15: Backend bug fix — sync supabase calls inside async functions in `dependencies.py`

**Files:**
- Modify: `backend/app/dependencies.py`
- Create: `backend/tests/test_dependencies.py`

The bug: `supabase-py` is sync. Calling `.execute()` inside an `async def` blocks the event loop. Fix by wrapping with `asyncio.to_thread`.

- [ ] **Step 1: Write the test that will drive the fix**

Create `backend/tests/test_dependencies.py`:

```python
"""Tests for FastAPI auth/tenant dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.dependencies import (
    get_current_tenant_id,
    get_current_user,
    get_current_user_id,
)


def _make_jwt(sub: str) -> str:
    return jwt.encode(
        {"sub": sub, "aud": "authenticated", "exp": 9999999999},
        settings.SUPABASE_JWT_SECRET or "test-secret",
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "test-secret")


@pytest.mark.asyncio
async def test_get_current_user_decodes_valid_jwt() -> None:
    user_id = str(uuid4())
    token = _make_jwt(user_id)
    payload = await get_current_user(authorization=f"Bearer {token}")
    assert payload["sub"] == user_id


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_bearer() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization="not-a-bearer")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_returns_uuid() -> None:
    payload = {"sub": str(uuid4())}
    user_uuid = await get_current_user_id(user=payload)
    assert isinstance(user_uuid, UUID)


@pytest.mark.asyncio
async def test_get_current_tenant_id_does_not_block_event_loop() -> None:
    """
    Regression test: get_current_tenant_id calls the sync supabase-py client.
    It MUST wrap that call in asyncio.to_thread (or similar) to avoid blocking.
    We assert this by mocking asyncio.to_thread and verifying it gets invoked.
    """
    user_id = uuid4()
    tenant_id = uuid4()

    # Mock supabase chain: .table().select().eq().single().execute()
    mock_result = MagicMock()
    mock_result.data = {"tenant_id": str(tenant_id)}
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().single().execute.return_value = mock_result

    with patch("app.dependencies.get_supabase_admin", return_value=mock_supabase), \
         patch("app.dependencies.asyncio.to_thread", new=AsyncMock(return_value=mock_result)) as to_thread:
        result = await get_current_tenant_id(user_id=user_id)
        assert result == tenant_id
        assert to_thread.called, "Expected asyncio.to_thread to wrap the sync supabase call"
```

- [ ] **Step 2: Run the test — verify it FAILS**

```bash
cd backend
pytest tests/test_dependencies.py -v
```

Expected: `test_get_current_tenant_id_does_not_block_event_loop` FAILS with `AssertionError: Expected asyncio.to_thread to wrap the sync supabase call` (or similar — the existing code calls `.execute()` directly without `to_thread`).

- [ ] **Step 3: Replace the entire contents of `backend/app/dependencies.py`**

```python
"""
HishabAI Backend — FastAPI Dependencies

Shared dependencies for auth, tenant resolution, and database access.
Auth is validated against Supabase JWT.

IMPORTANT: supabase-py is sync. Every supabase client call inside an async
function MUST be wrapped in asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings
from app.database import get_supabase_admin


async def get_current_user(
    authorization: str = Header(..., description="Bearer <supabase_jwt>"),
) -> dict[str, Any]:
    """Validates the Supabase JWT from the Authorization header. Returns decoded payload."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing Bearer token"},
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Token expired"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": f"Invalid token: {exc}"},
        )

    return payload


async def get_current_user_id(
    user: dict[str, Any] = Depends(get_current_user),
) -> UUID:
    """Extracts the user UUID from the validated Supabase JWT."""
    return UUID(user["sub"])


async def get_current_tenant_id(
    user_id: UUID = Depends(get_current_user_id),
) -> UUID:
    """
    Looks up the tenant_id for the authenticated user from user_profiles.
    Raises 403 if user has no tenant association.

    The supabase-py call is sync, so we wrap it in asyncio.to_thread.
    """
    supabase = get_supabase_admin()

    def _query() -> Any:
        return (
            supabase.table("user_profiles")
            .select("tenant_id")
            .eq("id", str(user_id))
            .single()
            .execute()
        )

    result = await asyncio.to_thread(_query)

    if not result.data or not result.data.get("tenant_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_NOT_FOUND",
                "message": "User is not associated with any firm. Complete onboarding first.",
            },
        )

    return UUID(result.data["tenant_id"])


def require_role(*allowed_roles: str):
    """Dependency factory: restricts endpoint to specific user roles."""

    async def _check_role(
        user_id: UUID = Depends(get_current_user_id),
    ) -> str:
        supabase = get_supabase_admin()

        def _query() -> Any:
            return (
                supabase.table("user_profiles")
                .select("role")
                .eq("id", str(user_id))
                .single()
                .execute()
            )

        result = await asyncio.to_thread(_query)

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "User profile not found"},
            )

        role = result.data["role"]
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": (
                        f"Role '{role}' does not have access. "
                        f"Required: {', '.join(allowed_roles)}"
                    ),
                },
            )
        return role

    return _check_role
```

- [ ] **Step 4: Run the test — verify it PASSES**

```bash
pytest tests/test_dependencies.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add backend/app/dependencies.py backend/tests/test_dependencies.py
git commit -m "fix(deps): wrap sync supabase-py calls in asyncio.to_thread to avoid event-loop blocking"
```

---

## Task 16: Backend — fix `/ready` endpoint async bug + add request_id middleware

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_middleware.py`

- [ ] **Step 1: Write tests for the new behavior (failing)**

Create `backend/tests/test_middleware.py`:

```python
"""Tests for request_id middleware and updated /ready endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def test_response_has_request_id_header(client: TestClient) -> None:
    """Every response should carry an X-Request-ID header."""
    response = client.get("/health")
    assert "x-request-id" in {k.lower() for k in response.headers.keys()}
    request_id = response.headers["x-request-id"]
    assert len(request_id) > 0


def test_request_id_is_unique_per_request(client: TestClient) -> None:
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_ready_uses_async_supabase_call(client: TestClient) -> None:
    """
    /ready must wrap its sync supabase call in asyncio.to_thread.
    Same regression as get_current_tenant_id.
    """
    mock_supabase = MagicMock()
    mock_supabase.table().select().limit().execute.return_value = MagicMock(data=[])

    with patch("app.main.get_supabase_admin", return_value=mock_supabase), \
         patch("app.main.asyncio.to_thread", new=AsyncMock(return_value=MagicMock(data=[]))) as to_thread:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert to_thread.called, "Expected asyncio.to_thread to wrap the sync supabase call"
```

- [ ] **Step 2: Run the tests — verify they FAIL**

```bash
cd backend
pytest tests/test_middleware.py -v
```

Expected: All 3 tests fail (no middleware yet, /ready uses sync call).

- [ ] **Step 3: Replace the entire contents of `backend/app/main.py`**

```python
"""
HishabAI Backend — FastAPI Application Factory

Main entry point. Registers routers, middleware, exception handlers, and health checks.
"""

import asyncio
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.exceptions import HishabError
from app.database import get_supabase_admin

logger = structlog.get_logger()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to every request and response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        # Bind to structlog context so all logs in this request carry the id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="HishabAI API",
        description="Automated CA workflow platform for Bangladesh",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    )

    # ── Middleware (registered in reverse order of execution) ─────────────
    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://localhost:3000",   # Alt dev port
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ────────────────────────────────────────────────

    @app.exception_handler(HishabError)
    async def hishab_error_handler(request: Request, exc: HishabError) -> JSONResponse:
        logger.warning(
            "api_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_error",
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                    "details": {},
                },
            },
        )

    # ── Health Checks ─────────────────────────────────────────────────────

    @app.get("/health", tags=["system"])
    async def health_check():
        """Basic health check — returns 200 if the server is running."""
        return {"status": "healthy", "service": "hishabai-api"}

    @app.get("/ready", tags=["system"])
    async def readiness_check():
        """Readiness check — verifies database connectivity (async-safe)."""
        try:
            supabase = get_supabase_admin()
            # Wrap sync supabase call in to_thread to avoid blocking the event loop
            await asyncio.to_thread(
                lambda: supabase.table("tenants").select("id").limit(1).execute()
            )
            return {"status": "ready", "database": "connected"}
        except Exception as exc:
            logger.error("readiness_check_failed", error=str(exc))
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": "disconnected"},
            )

    return app


app = create_app()
```

- [ ] **Step 4: Run the tests — verify they PASS**

```bash
pytest tests/test_middleware.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Run all backend tests to confirm no regressions**

```bash
pytest -v
```

Expected: All tests pass (health, dependencies, middleware).

- [ ] **Step 6: Commit**

```bash
cd ..
git add backend/app/main.py backend/tests/test_middleware.py
git commit -m "feat(backend): add request_id middleware and fix /ready async-blocking bug"
```

---

## Task 17: Backend — `set_request_user` helper

**Files:**
- Modify: `backend/app/dependencies.py` (append new function)
- Modify: `backend/tests/test_dependencies.py` (append test)

- [ ] **Step 1: Append the test (failing)**

Add to the bottom of `backend/tests/test_dependencies.py`:

```python
@pytest.mark.asyncio
async def test_set_request_user_calls_rpc_via_to_thread() -> None:
    """set_request_user must call the Supabase RPC asynchronously."""
    from app.dependencies import set_request_user

    user_id = uuid4()
    mock_supabase = MagicMock()
    mock_supabase.rpc.return_value.execute.return_value = MagicMock()

    # Side effect that actually invokes the wrapped callable, mirroring real asyncio.to_thread.
    # Without this, the inner closure never runs and mock_supabase.rpc is never called.
    async def _side_effect(fn, *args, **kwargs):
        fn()

    with patch("app.dependencies.get_supabase_admin", return_value=mock_supabase), \
         patch("app.dependencies.asyncio.to_thread", new=AsyncMock(side_effect=_side_effect)) as to_thread:
        await set_request_user(user_id)
        assert to_thread.called
        # The wrapped function should call .rpc("set_request_user", {"p_user_id": ...})
        call = mock_supabase.rpc.call_args
        assert call.args[0] == "set_request_user"
        assert call.args[1] == {"p_user_id": str(user_id)}
```

- [ ] **Step 2: Run the test — verify it FAILS**

```bash
cd backend
pytest tests/test_dependencies.py::test_set_request_user_calls_rpc_via_to_thread -v
```

Expected: FAIL with `ImportError: cannot import name 'set_request_user'`.

- [ ] **Step 3: Append `set_request_user` to `backend/app/dependencies.py`**

Add at the bottom of the file:

```python
async def set_request_user(user_id: UUID) -> None:
    """
    Sets the request.jwt.claim.sub Postgres setting via the set_request_user RPC.

    Backend MUST call this before any service-role write so the audit trigger
    captures the correct user_id. Effective only within the same transaction —
    keep the subsequent write in the same supabase-py client session.

    See migrations/0006_set_request_user.sql.
    """
    supabase = get_supabase_admin()

    def _call() -> None:
        supabase.rpc("set_request_user", {"p_user_id": str(user_id)}).execute()

    await asyncio.to_thread(_call)
```

- [ ] **Step 4: Run the test — verify it PASSES**

```bash
pytest tests/test_dependencies.py::test_set_request_user_calls_rpc_via_to_thread -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ..
git add backend/app/dependencies.py backend/tests/test_dependencies.py
git commit -m "feat(deps): add set_request_user helper for backend audit-trigger context"
```

---

## Task 18: SPIKE — verify audit trigger captures user_id end-to-end

**Files:**
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/test_audit_trigger_spike.py`

This is a **risk-validation spike** (Section 11 risk #3 of the spec). The goal is to confirm that when the backend uses the service-role to write to a tenant table, the audit trigger captures the correct `user_id`. If this pattern doesn't work cleanly with supabase-py (because `set_config(..., true)` is transaction-local and supabase-py may use a fresh connection per call), we need to switch strategy before building Phase B.

- [ ] **Step 1: Create `backend/tests/integration/__init__.py`**

Empty file.

```bash
touch backend/tests/integration/__init__.py
```

- [ ] **Step 2: Create `backend/tests/integration/test_audit_trigger_spike.py`**

```python
"""
SPIKE — verify audit_log captures the correct user_id when the backend writes
via the service-role after calling set_request_user.

Requires real Supabase project access. Run with:
    pytest tests/integration/ -v -s --run-integration

This test is gated by the `integration` marker so it doesn't run in CI by default.
"""

from uuid import uuid4

import pytest

from app.database import get_supabase_admin
from app.dependencies import set_request_user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_trigger_captures_user_id_after_set_request_user() -> None:
    """
    Setup:
      - Create a fresh tenant + user_profile via service-role.
      - Call set_request_user(user_id).
      - Insert a clients row.
    Verify:
      - The audit_log row for that insert has user_id = our user_id (NOT NULL).

    If user_id comes back NULL, the transaction-local set_config is not persisting
    across supabase-py calls. We must then switch to one of:
      - explicit audit log writes from the backend (no trigger)
      - Postgres function wrappers that take user_id and do both set_config + write atomically
    """
    supabase = get_supabase_admin()
    tenant_id = uuid4()
    user_id = uuid4()
    test_email = f"spike-{tenant_id}@hishab.test"

    # 1. Create a tenant
    supabase.table("tenants").insert({
        "id": str(tenant_id),
        "firm_name": "Spike Test Firm",
        "email": test_email,
    }).execute()

    # 2. Create an auth.users entry would normally happen via Supabase Auth.
    #    For this spike, we skip auth.users and directly fake a user_profile row
    #    that references a synthetic user_id. NOTE: user_profiles.id has a
    #    foreign key to auth.users(id), so this insert WILL FAIL unless the
    #    user_id exists in auth.users.
    #
    #    Workaround for the spike: use Supabase Admin API to create an auth user.

    auth_response = supabase.auth.admin.create_user({
        "email": test_email,
        "password": "spike-test-password-12345",
        "email_confirm": True,
    })
    real_user_id = auth_response.user.id

    supabase.table("user_profiles").insert({
        "id": real_user_id,
        "tenant_id": str(tenant_id),
        "full_name": "Spike Tester",
    }).execute()

    try:
        # 3. Call set_request_user
        from uuid import UUID
        await set_request_user(UUID(real_user_id))

        # 4. Insert a clients row IN THE SAME SESSION
        client_id = uuid4()
        supabase.table("clients").insert({
            "id": str(client_id),
            "tenant_id": str(tenant_id),
            "name": "Spike Test Client",
            "entity_type": "company",
            "created_by": real_user_id,
        }).execute()

        # 5. Read the audit_log row for that insert
        audit_rows = (
            supabase.table("audit_log")
            .select("*")
            .eq("table_name", "clients")
            .eq("row_id", str(client_id))
            .execute()
        )

        assert len(audit_rows.data) == 1, "Expected exactly 1 audit_log row"
        captured_user_id = audit_rows.data[0]["user_id"]

        assert captured_user_id is not None, (
            "audit_log.user_id is NULL — set_request_user did not persist across "
            "supabase-py calls. Switch to explicit audit writes or function wrappers."
        )
        assert captured_user_id == real_user_id, (
            f"audit_log.user_id mismatch. Expected {real_user_id}, got {captured_user_id}"
        )

    finally:
        # Cleanup
        supabase.table("clients").delete().eq("tenant_id", str(tenant_id)).execute()
        supabase.table("user_profiles").delete().eq("id", real_user_id).execute()
        supabase.auth.admin.delete_user(real_user_id)
        supabase.table("tenants").delete().eq("id", str(tenant_id)).execute()
        supabase.table("audit_log").delete().eq("tenant_id", str(tenant_id)).execute()
```

- [ ] **Step 3: Add the `--run-integration` flag to `conftest.py`**

Replace `backend/tests/conftest.py` with:

```python
"""Shared test fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that hit real Supabase",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(reason="Need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def client() -> TestClient:
    """Synchronous TestClient for FastAPI app."""
    return TestClient(app)
```

- [ ] **Step 4: Run the spike**

Ensure `backend/.env` has real values for `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Then:

```bash
cd backend
pytest tests/integration/ -v -s --run-integration
```

**Outcomes:**
- ✅ **PASS** → the trigger pattern works. Phase A is unblocked. No further action needed.
- ❌ **FAIL with `audit_log.user_id is NULL`** → `set_config(..., true)` doesn't persist across supabase-py calls. We need to refactor to one of:
  - **Option A:** Make every tenant write a Postgres function (e.g. `create_client(p_user_id, p_name, ...)`) that does `set_config` + insert atomically.
  - **Option B:** Drop the trigger; have the backend explicitly insert into `audit_log` after every mutation.
  - **Option C:** Modify `set_request_user` to use a stable `set_config(..., false)` (session-level) — risky in a connection pool, but acceptable for a single-process MVP.

  Document the chosen path in [`docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md`](../specs/2026-05-02-hishabai-mvp-design.md) Section 6.5 and update Phase B's plan accordingly.

- [ ] **Step 5: Commit (regardless of outcome — the spike result is documentation)**

```bash
cd ..
git add backend/tests/integration/ backend/tests/conftest.py
git commit -m "test(spike): verify audit trigger user_id capture pattern (Risk #3 from spec)"
```

If the spike failed, also commit a follow-up note:

```bash
# Edit docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md Section 6.5 with findings
git add docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md
git commit -m "docs(spec): document audit trigger spike findings (Section 6.5)"
```

---

## Task 19: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

- [ ] **Step 1: Create `backend/.dockerignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/
tests/
.env
.env.example
*.md
```

- [ ] **Step 2: Create `backend/Dockerfile`**

```dockerfile
# Single-stage Python slim image for Cloud Run deployment.
FROM python:3.11-slim

WORKDIR /app

# System packages: only what's needed for psycopg / cryptography (none for our deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Cloud Run injects PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

# Use uvicorn directly (no gunicorn — single worker is fine for MVP)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 3: Verify the image builds locally (optional but recommended)**

```bash
cd backend
docker build -t hishabai-backend:dev .
```

Expected: image builds successfully. Skip if Docker isn't installed locally — Cloud Run can build from source.

- [ ] **Step 4: Commit**

```bash
cd ..
git add backend/Dockerfile backend/.dockerignore
git commit -m "feat(backend): add Dockerfile for Cloud Run deployment"
```

---

## Task 20: Frontend — scaffold Vite + React + TypeScript

**Files:**
- Create: entire `frontend/` directory via Vite

- [ ] **Step 1: Run Vite scaffold**

```bash
cd "C:/project/Hishab AI"
npm create vite@latest frontend -- --template react-ts
```

When prompted, accept defaults. This creates `frontend/` with React + TypeScript + Vite.

- [ ] **Step 2: Install base dependencies**

```bash
cd frontend
npm install
```

Expected: `node_modules/` populated, no errors.

- [ ] **Step 3: Verify dev server starts**

```bash
npm run dev
```

Expected: Vite serves on `http://localhost:5173`. Open in browser to verify default Vite page renders. Stop with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(frontend): scaffold Vite + React 18 + TypeScript app"
```

---

## Task 21: Frontend — install Tailwind CSS

**Files:**
- Modify: `frontend/package.json`, `frontend/index.css`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/src/index.css`

- [ ] **Step 1: Install Tailwind and dependencies**

```bash
cd frontend
npm install -D tailwindcss@latest postcss@latest autoprefixer@latest
npx tailwindcss init -p
```

Expected: `tailwind.config.js` and `postcss.config.js` created.

- [ ] **Step 2: Configure `tailwind.config.js`**

Replace contents:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

- [ ] **Step 3: Replace `frontend/src/index.css` with Tailwind directives**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Verify Tailwind works**

Edit `frontend/src/App.tsx` temporarily to use a Tailwind class:

```tsx
function App() {
  return <h1 className="text-3xl font-bold underline">Tailwind works</h1>
}

export default App
```

Run `npm run dev`, open in browser, confirm the heading is large/bold/underlined. Then stop the server.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(frontend): install and configure Tailwind CSS"
```

---

## Task 22: Frontend — install runtime dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install all runtime deps**

```bash
cd frontend
npm install \
  @supabase/supabase-js@^2.45.0 \
  @tanstack/react-query@^5.59.0 \
  zustand@^4.5.0 \
  react-router-dom@^6.26.0 \
  react-hook-form@^7.53.0 \
  zod@^3.23.0 \
  @hookform/resolvers@^3.9.0 \
  axios@^1.7.0
```

- [ ] **Step 2: Install dev deps for typing**

```bash
npm install -D @types/node
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): install supabase-js, tanstack/query, zustand, router, hook-form, zod, axios"
```

---

## Task 23: Frontend — install and initialize shadcn/ui

**Files:**
- Modify: many frontend files via shadcn init
- Create: `frontend/src/components/ui/*`

- [ ] **Step 1: Configure path alias in `tsconfig.json`**

shadcn requires a `@/*` path alias. Edit `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 2: Configure path alias in `vite.config.ts`**

Replace `frontend/vite.config.ts`:

```typescript
import path from "node:path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
```

- [ ] **Step 3: Run shadcn init**

```bash
cd frontend
npx shadcn@latest init
```

Answer prompts:
- Style: **Default**
- Base color: **Slate**
- CSS variables: **Yes**

This creates `components.json`, updates `tailwind.config.js`, and sets up `src/components/ui/` and `src/lib/utils.ts`.

- [ ] **Step 4: Add base components**

```bash
npx shadcn@latest add button card input label form dialog dropdown-menu table sonner separator
```

Expected: components added to `src/components/ui/`.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(frontend): init shadcn/ui with base components (button, card, input, form, dialog, table, etc.)"
```

---

## Task 24: Frontend — Supabase client + TanStack Query + env validation

**Files:**
- Create: `frontend/src/lib/env.ts`
- Create: `frontend/src/lib/supabase.ts`
- Create: `frontend/src/lib/queryClient.ts`
- Create: `frontend/.env.example`
- Create: `frontend/src/vite-env.d.ts` (extend types)

- [ ] **Step 1: Create `frontend/.env.example`**

```bash
# frontend/.env.example — copy to .env.local and fill in
VITE_SUPABASE_URL=https://qlrqbqisavkfxywkiuca.supabase.co
VITE_SUPABASE_ANON_KEY=
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 2: Create `frontend/src/lib/env.ts`**

```typescript
import { z } from "zod"

const envSchema = z.object({
  VITE_SUPABASE_URL: z.string().url(),
  VITE_SUPABASE_ANON_KEY: z.string().min(1),
  VITE_API_URL: z.string().url(),
})

const parsed = envSchema.safeParse(import.meta.env)

if (!parsed.success) {
  console.error("Invalid environment variables:", parsed.error.flatten().fieldErrors)
  throw new Error("Missing or invalid environment variables. See .env.example.")
}

export const env = parsed.data
```

- [ ] **Step 3: Create `frontend/src/lib/supabase.ts`**

```typescript
import { createClient } from "@supabase/supabase-js"

import { env } from "./env"

export const supabase = createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
```

- [ ] **Step 4: Create `frontend/src/lib/queryClient.ts`**

```typescript
import { QueryClient } from "@tanstack/react-query"

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
```

- [ ] **Step 5: Create local `.env.local` (NOT committed) with real values**

```bash
cd frontend
cp .env.example .env.local
# Manually edit .env.local to set VITE_SUPABASE_ANON_KEY (copy from existing root .env)
```

- [ ] **Step 6: Commit (env.local is gitignored)**

```bash
cd ..
git add frontend/.env.example frontend/src/lib/
git commit -m "feat(frontend): add Supabase client, TanStack Query, and env validation"
```

---

## Task 25: Frontend — Zustand auth store + `useUserProfile` hook

**Files:**
- Create: `frontend/src/store/auth.ts`
- Create: `frontend/src/hooks/useUserProfile.ts`
- Create: `frontend/src/hooks/useSession.ts`

- [ ] **Step 1: Create `frontend/src/store/auth.ts`**

```typescript
import type { Session, User } from "@supabase/supabase-js"
import { create } from "zustand"

interface AuthState {
  session: Session | null
  user: User | null
  isLoading: boolean
  setSession: (session: Session | null) => void
  setLoading: (loading: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  session: null,
  user: null,
  isLoading: true,
  setSession: (session) => set({ session, user: session?.user ?? null, isLoading: false }),
  setLoading: (isLoading) => set({ isLoading }),
}))
```

- [ ] **Step 2: Create `frontend/src/hooks/useSession.ts`**

```typescript
import { useEffect } from "react"

import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"

/**
 * Initializes the auth store from Supabase on mount and subscribes to auth changes.
 * Call this once at the top of the app.
 */
export function useSessionInit(): void {
  const setSession = useAuthStore((s) => s.setSession)

  useEffect(() => {
    // 1. Initial session fetch
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
    })

    // 2. Subscribe to auth state changes
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })

    return () => {
      subscription.subscription.unsubscribe()
    }
  }, [setSession])
}
```

- [ ] **Step 3: Create `frontend/src/hooks/useUserProfile.ts`**

```typescript
import { useQuery } from "@tanstack/react-query"

import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"

export interface UserProfile {
  id: string
  tenant_id: string
  full_name: string
  role: string
  created_at: string
}

/**
 * Returns the user_profile row for the currently authenticated user.
 * Returns null (not undefined) if the user has no profile yet (pre-onboarding).
 */
export function useUserProfile() {
  const userId = useAuthStore((s) => s.user?.id)

  return useQuery({
    queryKey: ["user_profile", userId],
    enabled: Boolean(userId),
    queryFn: async (): Promise<UserProfile | null> => {
      if (!userId) return null
      const { data, error } = await supabase
        .from("user_profiles")
        .select("*")
        .eq("id", userId)
        .maybeSingle()
      if (error) throw error
      return (data as UserProfile | null) ?? null
    },
  })
}
```

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/src/store/ frontend/src/hooks/
git commit -m "feat(frontend): add Zustand auth store and useSession/useUserProfile hooks"
```

---

## Task 26: Frontend — router + layouts

**Files:**
- Create: `frontend/src/router.tsx`
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/layout/AuthLayout.tsx`
- Create: `frontend/src/components/RequireAuth.tsx`
- Create: `frontend/src/components/RequireTenant.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/components/layout/AuthLayout.tsx`**

```tsx
import type { ReactNode } from "react"

interface Props {
  children: ReactNode
}

export function AuthLayout({ children }: Props) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md">
        <h1 className="text-2xl font-bold text-center mb-6 text-slate-900">HishabAI</h1>
        {children}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/src/components/layout/AppShell.tsx`**

```tsx
import type { ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { supabase } from "@/lib/supabase"
import { useUserProfile } from "@/hooks/useUserProfile"

interface Props {
  children: ReactNode
}

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/clients", label: "Clients" },
]

export function AppShell({ children }: Props) {
  const location = useLocation()
  const { data: profile } = useUserProfile()

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r bg-slate-50 p-4 flex flex-col">
        <div className="mb-8">
          <h1 className="text-xl font-bold text-slate-900">HishabAI</h1>
          {profile && <p className="text-xs text-slate-500 mt-1">{profile.full_name}</p>}
        </div>
        <nav className="flex flex-col gap-1 flex-1">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`px-3 py-2 rounded text-sm ${
                location.pathname.startsWith(item.to)
                  ? "bg-slate-900 text-white"
                  : "text-slate-700 hover:bg-slate-200"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <Button variant="ghost" size="sm" onClick={() => supabase.auth.signOut()}>
          Sign out
        </Button>
      </aside>
      <main className="flex-1 p-8 bg-white">{children}</main>
    </div>
  )
}
```

- [ ] **Step 3: Create `frontend/src/components/RequireAuth.tsx`**

```tsx
import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"

import { useAuthStore } from "@/store/auth"

interface Props {
  children: ReactNode
}

export function RequireAuth({ children }: Props) {
  const session = useAuthStore((s) => s.session)
  const isLoading = useAuthStore((s) => s.isLoading)

  if (isLoading) return <div className="p-8 text-slate-500">Loading…</div>
  if (!session) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

- [ ] **Step 4: Create `frontend/src/components/RequireTenant.tsx`**

```tsx
import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"

import { useUserProfile } from "@/hooks/useUserProfile"

interface Props {
  children: ReactNode
}

/**
 * Wraps routes that require an onboarded user (one with a user_profile + tenant).
 * Redirects to /onboard if the user is logged in but has no profile yet.
 */
export function RequireTenant({ children }: Props) {
  const { data: profile, isLoading } = useUserProfile()

  if (isLoading) return <div className="p-8 text-slate-500">Loading…</div>
  if (!profile) return <Navigate to="/onboard" replace />
  return <>{children}</>
}
```

- [ ] **Step 5: Create `frontend/src/router.tsx`**

```tsx
import { createBrowserRouter, Navigate } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthLayout } from "@/components/layout/AuthLayout"
import { RequireAuth } from "@/components/RequireAuth"
import { RequireTenant } from "@/components/RequireTenant"
import { Dashboard } from "@/pages/Dashboard"
import { Login } from "@/pages/Login"
import { Onboard } from "@/pages/Onboard"
import { Signup } from "@/pages/Signup"

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/login", element: <AuthLayout><Login /></AuthLayout> },
  { path: "/signup", element: <AuthLayout><Signup /></AuthLayout> },
  {
    path: "/onboard",
    element: (
      <RequireAuth>
        <AuthLayout><Onboard /></AuthLayout>
      </RequireAuth>
    ),
  },
  {
    path: "/dashboard",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><Dashboard /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  // /clients route added in Phase B
  { path: "*", element: <Navigate to="/login" replace /> },
])
```

- [ ] **Step 6: Replace `frontend/src/main.tsx`**

```tsx
import { QueryClientProvider } from "@tanstack/react-query"
import React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider } from "react-router-dom"

import { queryClient } from "@/lib/queryClient"
import { router } from "@/router"
import { AppRoot } from "@/App"

import "./index.css"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppRoot>
        <RouterProvider router={router} />
      </AppRoot>
    </QueryClientProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 7: Replace `frontend/src/App.tsx`**

```tsx
import type { ReactNode } from "react"

import { useSessionInit } from "@/hooks/useSession"
import { Toaster } from "@/components/ui/sonner"

interface Props {
  children: ReactNode
}

/**
 * Root wrapper that initializes the auth session subscription.
 * Renders children + the global toast container.
 */
export function AppRoot({ children }: Props) {
  useSessionInit()
  return (
    <>
      {children}
      <Toaster />
    </>
  )
}
```

- [ ] **Step 8: Commit (pages don't exist yet — they'll error if dev server runs)**

```bash
cd ..
git add frontend/src/
git commit -m "feat(frontend): add router, layouts, RequireAuth/Tenant guards, and AppRoot"
```

---

## Task 27: Frontend — Login page

**Files:**
- Create: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: Create `frontend/src/pages/Login.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { supabase } from "@/lib/supabase"

const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
})

type LoginInput = z.infer<typeof loginSchema>

export function Login() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) })

  async function onSubmit(values: LoginInput) {
    setSubmitting(true)
    const { error } = await supabase.auth.signInWithPassword(values)
    setSubmitting(false)
    if (error) {
      toast.error(error.message)
      return
    }
    navigate("/dashboard")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>Welcome back to HishabAI.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" {...register("email")} />
            {errors.email && <p className="text-sm text-red-600">{errors.email.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" {...register("password")} />
            {errors.password && <p className="text-sm text-red-600">{errors.password.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-sm text-center text-slate-600">
            New here?{" "}
            <Link to="/signup" className="text-slate-900 underline">Create an account</Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd ..
git add frontend/src/pages/Login.tsx
git commit -m "feat(frontend): add Login page with Supabase auth"
```

---

## Task 28: Frontend — Signup page

**Files:**
- Create: `frontend/src/pages/Signup.tsx`

- [ ] **Step 1: Create `frontend/src/pages/Signup.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { supabase } from "@/lib/supabase"

const signupSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
})

type SignupInput = z.infer<typeof signupSchema>

export function Signup() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SignupInput>({ resolver: zodResolver(signupSchema) })

  async function onSubmit(values: SignupInput) {
    setSubmitting(true)
    const { error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
    })
    setSubmitting(false)
    if (error) {
      toast.error(error.message)
      return
    }
    toast.success("Account created. Let's set up your firm.")
    navigate("/onboard")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your firm account</CardTitle>
        <CardDescription>Start automating your CA workflow with HishabAI.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" {...register("email")} />
            {errors.email && <p className="text-sm text-red-600">{errors.email.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" {...register("password")} />
            {errors.password && <p className="text-sm text-red-600">{errors.password.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Creating account…" : "Create account"}
          </Button>
          <p className="text-sm text-center text-slate-600">
            Already have an account?{" "}
            <Link to="/login" className="text-slate-900 underline">Sign in</Link>
          </p>
        </form>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd ..
git add frontend/src/pages/Signup.tsx
git commit -m "feat(frontend): add Signup page with Supabase auth"
```

---

## Task 29: Frontend — Onboard page (creates tenant + user_profile)

**Files:**
- Create: `frontend/src/pages/Onboard.tsx`

- [ ] **Step 1: Create `frontend/src/pages/Onboard.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"

const onboardSchema = z.object({
  firmName: z.string().min(2, "Firm name is required"),
  fullName: z.string().min(2, "Your full name is required"),
})

type OnboardInput = z.infer<typeof onboardSchema>

export function Onboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [submitting, setSubmitting] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<OnboardInput>({ resolver: zodResolver(onboardSchema) })

  async function onSubmit(values: OnboardInput) {
    if (!user) {
      toast.error("Not signed in.")
      return
    }
    setSubmitting(true)

    // 1. Create the tenant. RLS allows authenticated users to insert.
    const { data: tenant, error: tenantError } = await supabase
      .from("tenants")
      .insert({
        firm_name: values.firmName,
        email: user.email!,
      })
      .select()
      .single()

    if (tenantError) {
      setSubmitting(false)
      toast.error(`Could not create firm: ${tenantError.message}`)
      return
    }

    // 2. Create the user_profile linking auth.user → tenant
    const { error: profileError } = await supabase
      .from("user_profiles")
      .insert({
        id: user.id,
        tenant_id: tenant.id,
        full_name: values.fullName,
        role: "firm_admin",
      })

    setSubmitting(false)

    if (profileError) {
      toast.error(`Could not create profile: ${profileError.message}`)
      return
    }

    toast.success(`Welcome, ${values.fullName}!`)
    queryClient.invalidateQueries({ queryKey: ["user_profile"] })
    navigate("/dashboard")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set up your firm</CardTitle>
        <CardDescription>
          Tell us about your CA firm. You can change these details later.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="firmName">Firm name</Label>
            <Input
              id="firmName"
              placeholder="e.g. Rahman & Associates"
              {...register("firmName")}
            />
            {errors.firmName && <p className="text-sm text-red-600">{errors.firmName.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="fullName">Your full name</Label>
            <Input
              id="fullName"
              placeholder="e.g. Anwar Rahman"
              {...register("fullName")}
            />
            {errors.fullName && <p className="text-sm text-red-600">{errors.fullName.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Setting up…" : "Continue to dashboard"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd ..
git add frontend/src/pages/Onboard.tsx
git commit -m "feat(frontend): add Onboard page that creates tenant + user_profile"
```

---

## Task 30: Frontend — Dashboard placeholder

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Create `frontend/src/pages/Dashboard.tsx`**

```tsx
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useUserProfile } from "@/hooks/useUserProfile"

export function Dashboard() {
  const { data: profile } = useUserProfile()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-600 mt-1">
          {profile?.full_name ? `Welcome back, ${profile.full_name}.` : "Welcome to HishabAI."}
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>You're all set</CardTitle>
          <CardDescription>
            Your firm is created. Next, add clients and run your first reconciliation.
            (Clients and Reconciliation modules ship in Phase B–C.)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-600">
            For now, this empty dashboard confirms that auth, tenant creation, and RLS
            isolation are all working.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Run the frontend end-to-end**

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. Expected flow:
1. Land on `/login`.
2. Click "Create an account" → fill email + password → submit.
3. Land on `/onboard` → fill firm name + your name → submit.
4. Land on `/dashboard` → see "Welcome back, [your name]" and the "You're all set" card.
5. Refresh the browser → still on `/dashboard`, still signed in.
6. Click "Sign out" → land on `/login`.

If any step fails: check the browser console + Supabase Dashboard logs.

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): add Dashboard placeholder page"
```

---

## Task 31: Vercel config + project README

**Files:**
- Create: `frontend/vercel.json`
- Create: `README.md` (root)

- [ ] **Step 1: Create `frontend/vercel.json`**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [
    { "source": "/((?!.*\\.).*)", "destination": "/index.html" }
  ]
}
```

This config:
- Builds with `npm run build` → outputs to `dist/`
- The rewrite makes the SPA's client-side router work for deep links (e.g., `/clients/123` returns `index.html`)

- [ ] **Step 2: Create root `README.md`**

```markdown
# HishabAI

Multi-tenant SaaS that automates the pre-advisory workflow of Bangladeshi Chartered Accountancy firms. The MVP focuses on **VAT reconciliation** — uploading purchase register + supplier export XLSX files and computing ITC risk in BDT.

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the design spec and [`docs/superpowers/plans/`](docs/superpowers/plans/) for implementation plans.

## Stack

- **Frontend:** React 18 + TypeScript + Vite + Tailwind + shadcn/ui (deployed to Vercel)
- **Backend:** FastAPI 0.115 (Python 3.11+) (deployed to Cloud Run)
- **Database / Auth / Storage:** Supabase (PostgreSQL, GoTrue, Storage)
- **AI:** Deferred to Phase 2 (no LLM in MVP)

## Local development

### Prerequisites
- Python 3.11+
- Node.js 20+
- A Supabase project (existing: `qlrqbqisavkfxywkiuca`, Singapore)
- Supabase service-role key, anon key, JWT secret

### 1. Apply database migrations

See [`migrations/README.md`](migrations/README.md) for instructions. Apply files `0001` through `0008` in order to your Supabase project.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with real Supabase credentials
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/health` — should return `{"status":"healthy",...}`.

Run tests:
```bash
pytest
```

Run integration tests (requires real Supabase):
```bash
pytest --run-integration
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local with real Supabase URL + anon key + backend URL
npm run dev
```

Visit `http://localhost:5173`.

## Deployment

- **Frontend:** Push to GitHub → connect to Vercel → set env vars (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`) → auto-deploys on push.
- **Backend:** Build with `gcloud run deploy` against `backend/Dockerfile`. Set env vars from `backend/.env.example`. Region: `asia-southeast1` (Singapore, same as Supabase).

## Phases

- ✅ **Phase A** — Foundation (schema, RLS, audit, auth, onboarding) — current
- ⏳ **Phase B** — Clients module
- ⏳ **Phase C** — Reconciliation engine + report (the hero)
- ⏳ **Phase D** — Compliance calendar + dashboard
- ⏳ **Phase E** — Polish + ship

## Naming conventions (Bangladesh-specific)

- `tin` — 12-digit Taxpayer ID
- `bin` — 9-digit Business ID (VAT)
- `mushak_no` — MushaK form number
- `nbr` — National Board of Revenue (always uppercase)
- `bdt` — suffix for BDT-denominated monetary fields
- Currency: `৳ 12,34,567.89` (South Asian grouping, lakh/crore)
- Dates: DD/MM/YYYY (display) / ISO 8601 (storage)
- Fiscal year: July 1 — June 30 (e.g., FY2024-25)
```

- [ ] **Step 3: Commit**

```bash
git add frontend/vercel.json README.md
git commit -m "docs: add Vercel config and project README with setup instructions"
```

---

## Task 32: Phase A acceptance test

**Files:** None modified — operational verification.

- [ ] **Step 1: Verify backend starts cleanly**

```bash
cd backend
source .venv/bin/activate    # adapt for OS
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000 &
sleep 3
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Expected:
- `/health` → `{"status":"healthy","service":"hishabai-api"}`
- `/ready` → `{"status":"ready","database":"connected"}`

- [ ] **Step 2: Run all backend tests**

```bash
pytest -v
```

Expected: all unit tests pass (integration spike already validated in Task 18).

- [ ] **Step 3: Verify frontend end-to-end signup flow**

```bash
cd ../frontend
npm run dev
```

In a browser:
1. `/login` renders, "Create an account" link works.
2. Sign up with a test email + password → redirected to `/onboard`.
3. Submit firm name + full name → redirected to `/dashboard`.
4. Dashboard shows "Welcome back, [name]" and the placeholder card.
5. Refresh — still signed in, still on dashboard.
6. Sign out — back to `/login`.

- [ ] **Step 4: Verify cross-tenant isolation (RLS)**

In Supabase Dashboard SQL Editor (or via service-role API):

```sql
-- Create a SECOND test tenant + user_profile manually
INSERT INTO tenants (id, firm_name, email) VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'Other Firm', 'other@hishab.test');

-- Create some test clients under both tenants
-- (use the tenant_ids of your real signed-up tenant + the fake one above)
```

Then in the browser as the signed-up user, query clients via the supabase-js client:

```javascript
const { data } = await supabase.from("clients").select("*")
console.log(data)  // Should ONLY show clients for the signed-up tenant
```

Expected: 0 rows from "Other Firm"; only your own tenant's data.

(Note: in Phase A we have no `/clients` UI yet, so this verification is via dev-tools console. This is acceptance criteria #4 from the plan header.)

- [ ] **Step 5: Tag the Phase A milestone**

```bash
cd ..
git tag -a phase-a-complete -m "Phase A foundation complete: schema, auth, onboarding, RLS verified"
```

- [ ] **Step 6: Done!**

Phase A is complete. Next: write the Phase B implementation plan (clients module).

---

## Self-review notes

**Spec coverage check (against [`docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md`](../specs/2026-05-02-hishabai-mvp-design.md)):**

- ✅ Sec 6.1 (public schema) → Task 2
- ✅ Sec 6.2 (tenant tables) → Task 3
- ✅ Sec 6.3 (indexes) → Task 4
- ✅ Sec 6.4 (RLS pattern) → Task 5
- ✅ Sec 6.5 (audit trigger) → Tasks 6, 17, 18
- ✅ Sec 8 (compliance calendar function) → Task 8
- ✅ Sec 5.3 (drop unused deps and ai/) → Tasks 11, 12, 13
- ✅ Sec 4.1 (auth flow + onboarding) → Tasks 27, 28, 29
- ✅ Sec 11 risk #3 (audit trigger spike) → Task 18
- ⏳ Sec 7 (recon flow) → Phase C
- ⏳ Sec 8 calendar UI → Phase D
- ⏳ Sec 9 UI screens (clients, recon, calendar) → Phase B–D
- ⏳ Sec 11 risk #1 (XLSX column contract) → Phase C
- ⏳ Sec 11 risk #2 (deadline correctness) → Phase D
- ⏳ Sec 11 risk #4 (Cloud Run cold starts) → Phase E

Out-of-scope items appropriately deferred to later phases.

**Type/method consistency:**
- `set_request_user(user_id: UUID)` defined in Task 17, called in Task 18 — signature matches.
- `useUserProfile` hook defined in Task 25, used in `RequireTenant`, `AppShell`, `Dashboard` — consistent.
- `useAuthStore` shape defined in Task 25, consumed in Tasks 26, 29, 30 — consistent.

**Placeholder scan:** none.
