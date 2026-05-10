-- 0014_ingestion_tables.sql
-- Adaptive file ingestion: jobs, per-file extraction state, extracted rows,
-- and the LLM column-mapping cache. All tenant-scoped via RLS using the same
-- pattern as 0004_rls_policies.sql.

-- ============================================================
-- INGESTION_JOBS — one row per upload session
-- ============================================================

CREATE TYPE ingestion_job_status AS ENUM (
  'pending', 'extracting', 'ready_for_review',
  'confirmed', 'reconciling', 'completed', 'failed'
);

CREATE TYPE ingestion_kind AS ENUM (
  'purchase_register', 'supplier_export'
);

CREATE TABLE ingestion_jobs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id          uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  created_by         uuid NOT NULL,
  kind               ingestion_kind NOT NULL,
  period_start       date NOT NULL,
  period_end         date NOT NULL,
  status             ingestion_job_status NOT NULL DEFAULT 'pending',
  files_total        int NOT NULL DEFAULT 0,
  files_done         int NOT NULL DEFAULT 0,
  rows_total         int NOT NULL DEFAULT 0,
  rows_needs_review  int NOT NULL DEFAULT 0,
  error_summary      text,
  reconciliation_id  uuid REFERENCES vat_reconciliations(id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  completed_at       timestamptz,
  CHECK (period_end >= period_start)
);

-- ============================================================
-- INGESTION_FILES — one row per uploaded file
-- ============================================================

CREATE TYPE ingestion_file_status AS ENUM (
  'queued', 'extracting', 'extracted', 'failed', 'skipped'
);

CREATE TABLE ingestion_files (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id             uuid NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  tenant_id          uuid NOT NULL,
  storage_path       text NOT NULL,
  original_filename  text NOT NULL,
  mime_type          text NOT NULL,
  byte_size          bigint NOT NULL,
  engine             text,
  status             ingestion_file_status NOT NULL DEFAULT 'queued',
  rows_extracted     int NOT NULL DEFAULT 0,
  needs_review       boolean NOT NULL DEFAULT false,
  warnings           jsonb NOT NULL DEFAULT '[]'::jsonb,
  error              text,
  extraction_started_at timestamptz,
  extracted_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- EXTRACTED_ROWS — one row per invoice extracted from any file
-- ============================================================

CREATE TYPE extracted_row_status AS ENUM (
  'auto_passed', 'needs_review', 'confirmed', 'rejected', 'edited'
);

CREATE TABLE extracted_rows (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id            uuid NOT NULL REFERENCES ingestion_files(id) ON DELETE CASCADE,
  job_id             uuid NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  tenant_id          uuid NOT NULL,
  source_page_no     int,
  row_data           jsonb NOT NULL,
  row_data_original  jsonb NOT NULL,
  status             extracted_row_status NOT NULL DEFAULT 'needs_review',
  field_warnings     jsonb NOT NULL DEFAULT '[]'::jsonb,
  reviewed_by        uuid,
  reviewed_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- COLUMN_MAPPINGS — cache for LLM-inferred header mappings
-- ============================================================

CREATE TABLE ingestion_column_mappings (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  kind               ingestion_kind NOT NULL,
  header_signature   text NOT NULL,
  mapping            jsonb NOT NULL,
  confirmed_by       uuid,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, kind, header_signature)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX ix_ingestion_jobs_tenant_status_created
  ON ingestion_jobs (tenant_id, status, created_at DESC);

CREATE INDEX ix_ingestion_files_job_status
  ON ingestion_files (job_id, status);

CREATE INDEX ix_extracted_rows_job_status
  ON extracted_rows (job_id, status);

CREATE INDEX ix_extracted_rows_needs_review
  ON extracted_rows (job_id)
  WHERE status = 'needs_review';

-- Lease index used by the worker's SELECT ... FOR UPDATE SKIP LOCKED
CREATE INDEX ix_ingestion_jobs_lease
  ON ingestion_jobs (status, updated_at)
  WHERE status IN ('pending', 'extracting');

-- ============================================================
-- updated_at trigger
-- ============================================================

CREATE OR REPLACE FUNCTION ingestion_set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ingestion_jobs_updated_at
  BEFORE UPDATE ON ingestion_jobs
  FOR EACH ROW EXECUTE FUNCTION ingestion_set_updated_at();

-- ============================================================
-- RLS — same pattern as 0004_rls_policies.sql
-- ============================================================

ALTER TABLE ingestion_jobs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_files           ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_rows            ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_column_mappings ENABLE ROW LEVEL SECURITY;

CREATE POLICY ingestion_jobs_tenant ON ingestion_jobs
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

CREATE POLICY ingestion_files_tenant ON ingestion_files
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

CREATE POLICY extracted_rows_tenant ON extracted_rows
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

CREATE POLICY ingestion_column_mappings_tenant ON ingestion_column_mappings
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));
