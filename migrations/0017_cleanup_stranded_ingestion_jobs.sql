-- 0017_cleanup_stranded_ingestion_jobs.sql
-- Removes PR-only ingestion jobs left over from the broken two-trip flow:
-- status confirmed/ready_for_review, > 7 days old, never reconciled, never
-- linked from an SF job. Their canonical XLSX docs (if any) are pruned too.
--
-- ingestion_files and extracted_rows cascade via existing FKs.

WITH stranded AS (
  SELECT j.id FROM ingestion_jobs j
  WHERE j.kind = 'purchase_register'
    AND j.status IN ('confirmed','ready_for_review')
    AND j.reconciliation_id IS NULL
    AND j.updated_at < now() - interval '7 days'
    AND NOT EXISTS (
      SELECT 1 FROM ingestion_jobs sf
      WHERE sf.linked_pr_job_id = j.id
    )
)
DELETE FROM ingestion_jobs WHERE id IN (SELECT id FROM stranded);

-- Orphan canonical XLSX rows: created by the old per-job finalize-then-fail
-- path, never referenced by a vat_reconciliations row.
DELETE FROM documents
WHERE doc_type = 'purchase_register'
  AND created_at < now() - interval '7 days'
  AND original_filename LIKE 'ingested_purchase_register_%'
  AND NOT EXISTS (
    SELECT 1 FROM vat_reconciliations r
    WHERE r.purchase_register_doc_id = documents.id
       OR r.supplier_data_doc_id     = documents.id
  );
