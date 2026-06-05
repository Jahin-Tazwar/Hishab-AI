-- 0022_working_papers.sql
-- Generalized working papers engine: composed artifacts produced by named
-- recipes from input ledger data (today: reconciliations; future: notices
-- migrate here, audit packs, VDS recon, annual files all add as kinds).
--
-- The first kind shipped is 'at_risk_itc_schedule' — the monthly client-
-- facing deliverable derived from a vat_reconciliations row.

CREATE TYPE working_paper_kind AS ENUM (
  'at_risk_itc_schedule'
);

CREATE TYPE working_paper_status AS ENUM (
  'draft', 'finalized'
);

CREATE TYPE working_paper_edit_source AS ENUM (
  'recipe_composed', 'user_edit', 'recipe_regenerated'
);

CREATE TABLE working_papers (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id            uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  kind                 working_paper_kind NOT NULL,
  reconciliation_id    uuid REFERENCES vat_reconciliations(id) ON DELETE SET NULL,
  period_start         date,
  period_end           date,
  recipe_version       text NOT NULL,
  composed_json        jsonb NOT NULL,
  notes_html           text NOT NULL DEFAULT '',
  status               working_paper_status NOT NULL DEFAULT 'draft',
  finalized_at         timestamptz,
  finalized_by         uuid,
  composed_by          uuid NOT NULL,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_working_papers_tenant_client_created
  ON working_papers (tenant_id, client_id, created_at DESC);

CREATE INDEX ix_working_papers_tenant_recon
  ON working_papers (tenant_id, reconciliation_id)
  WHERE reconciliation_id IS NOT NULL;

CREATE INDEX ix_working_papers_tenant_kind_period
  ON working_papers (tenant_id, kind, period_end DESC NULLS LAST);

CREATE TABLE working_paper_revisions (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  working_paper_id     uuid NOT NULL REFERENCES working_papers(id) ON DELETE CASCADE,
  revision_no          int NOT NULL,
  composed_json        jsonb NOT NULL,
  notes_html           text NOT NULL,
  edited_by            uuid NOT NULL,
  edit_source          working_paper_edit_source NOT NULL,
  edit_reason          text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (working_paper_id, revision_no)
);

CREATE INDEX ix_working_paper_revisions_wp
  ON working_paper_revisions (working_paper_id, revision_no DESC);

CREATE OR REPLACE FUNCTION working_papers_set_updated_at()
  RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_working_papers_updated_at
  BEFORE UPDATE ON working_papers
  FOR EACH ROW EXECUTE FUNCTION working_papers_set_updated_at();

ALTER TABLE working_papers           ENABLE ROW LEVEL SECURITY;
ALTER TABLE working_paper_revisions  ENABLE ROW LEVEL SECURITY;

CREATE POLICY working_papers_tenant ON working_papers
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

CREATE POLICY working_paper_revisions_tenant ON working_paper_revisions
  FOR ALL TO authenticated
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));
