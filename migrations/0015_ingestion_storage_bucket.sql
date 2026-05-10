-- 0015_ingestion_storage_bucket.sql
-- Private bucket 'ingestion-files' for raw uploaded XLSX/PDF/image originals
-- BEFORE extraction. Path layout: {tenant_id}/{job_id}/{file_id}/{filename}
-- The first path segment (tenant_id) is the RLS pivot, identical to 0011.

INSERT INTO storage.buckets (id, name, public)
VALUES ('ingestion-files', 'ingestion-files', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS ingestion_files_tenant_select ON storage.objects;
DROP POLICY IF EXISTS ingestion_files_tenant_insert ON storage.objects;
DROP POLICY IF EXISTS ingestion_files_tenant_update ON storage.objects;
DROP POLICY IF EXISTS ingestion_files_tenant_delete ON storage.objects;

CREATE POLICY ingestion_files_tenant_select ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY ingestion_files_tenant_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY ingestion_files_tenant_update ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  )
  WITH CHECK (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY ingestion_files_tenant_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );
