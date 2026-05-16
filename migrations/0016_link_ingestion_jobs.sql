-- 0016_link_ingestion_jobs.sql
-- Adds session linkage + reuse-prior-doc columns to ingestion_jobs so the
-- combined wizard can pair a PR job with its SF job and carry "reuse this
-- canonical doc instead of building one" intent across requests.

ALTER TABLE ingestion_jobs
  ADD COLUMN linked_pr_job_id uuid NULL
    REFERENCES ingestion_jobs(id) ON DELETE SET NULL,
  ADD COLUMN reuse_pr_doc_id  uuid NULL
    REFERENCES documents(id) ON DELETE SET NULL,
  ADD COLUMN reuse_sf_doc_id  uuid NULL
    REFERENCES documents(id) ON DELETE SET NULL;

-- Only SF jobs may carry a link to a PR job; only PR jobs may carry
-- reuse_sf_doc_id; only SF jobs may carry reuse_pr_doc_id.
ALTER TABLE ingestion_jobs
  ADD CONSTRAINT ingestion_jobs_linked_pr_kind_check CHECK (
    linked_pr_job_id IS NULL OR kind = 'supplier_export'
  ),
  ADD CONSTRAINT ingestion_jobs_reuse_pr_kind_check CHECK (
    reuse_pr_doc_id IS NULL OR kind = 'supplier_export'
  ),
  ADD CONSTRAINT ingestion_jobs_reuse_sf_kind_check CHECK (
    reuse_sf_doc_id IS NULL OR kind = 'purchase_register'
  );

-- Reverse-lookup index: given a PR job id, find the SF job that linked to it.
CREATE INDEX ix_ingestion_jobs_linked_pr
  ON ingestion_jobs(linked_pr_job_id)
  WHERE linked_pr_job_id IS NOT NULL;
