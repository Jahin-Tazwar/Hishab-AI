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
