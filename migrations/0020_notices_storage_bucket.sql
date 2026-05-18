-- 0020_notices_storage_bucket.sql
-- Private 'notices' bucket for raw NBR notice PDFs/images.
-- Path layout: {tenant_id}/{client_id}/{notice_id}/{filename}
-- First path segment (tenant_id) is the RLS pivot, identical to 0011 + 0015.

INSERT INTO storage.buckets (id, name, public)
VALUES ('notices', 'notices', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS notices_bucket_select ON storage.objects;
DROP POLICY IF EXISTS notices_bucket_insert ON storage.objects;
DROP POLICY IF EXISTS notices_bucket_update ON storage.objects;
DROP POLICY IF EXISTS notices_bucket_delete ON storage.objects;

CREATE POLICY notices_bucket_select ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY notices_bucket_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY notices_bucket_update ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY notices_bucket_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'notices'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );
