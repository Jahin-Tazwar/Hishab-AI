-- 0023_audit_defense_pack.sql
-- Adds the audit_defense_pack working-paper kind and a nullable notice_id
-- link so a pack can be tied to (and queried by) the NBR notice it defends.

ALTER TYPE working_paper_kind ADD VALUE IF NOT EXISTS 'audit_defense_pack';

ALTER TABLE working_papers
  ADD COLUMN IF NOT EXISTS notice_id uuid REFERENCES notices(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_working_papers_tenant_notice
  ON working_papers (tenant_id, notice_id)
  WHERE notice_id IS NOT NULL;
