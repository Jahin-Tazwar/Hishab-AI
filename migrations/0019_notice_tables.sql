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
