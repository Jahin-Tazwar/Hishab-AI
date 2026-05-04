-- 0011_storage_buckets.sql
-- Private bucket 'recon-files' for purchase register / supplier export / recon export XLSX.
-- Path layout: {tenant_id}/{client_id}/{recon_uuid}/{filename}.xlsx
-- The first path segment (tenant_id) is the RLS pivot.

INSERT INTO storage.buckets (id, name, public)
VALUES ('recon-files', 'recon-files', false)
ON CONFLICT (id) DO NOTHING;

-- Helper: pull tenant_id from the storage object path's first segment
-- storage.foldername returns text[] of path segments before the filename.

DROP POLICY IF EXISTS recon_files_tenant_select ON storage.objects;
DROP POLICY IF EXISTS recon_files_tenant_insert ON storage.objects;
DROP POLICY IF EXISTS recon_files_tenant_update ON storage.objects;
DROP POLICY IF EXISTS recon_files_tenant_delete ON storage.objects;

CREATE POLICY recon_files_tenant_select ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY recon_files_tenant_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY recon_files_tenant_update ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  )
  WITH CHECK (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY recon_files_tenant_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

-- Service role bypasses RLS automatically; backend doesn't need a policy.
