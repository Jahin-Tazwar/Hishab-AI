-- 0009_onboard_create_tenant_rpc.sql
-- Atomic onboarding: create the tenant AND the user_profile in one SECURITY DEFINER call.
-- Solves chicken-and-egg RLS during first-time onboarding (user has no tenant_id yet,
-- and a partial failure between tenant insert and profile insert leaves an orphan tenant).

CREATE OR REPLACE FUNCTION public.create_tenant_for_user(
  p_firm_name text,
  p_full_name text
)
RETURNS public.tenants
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_user_id uuid := auth.uid();
  v_email   text;
  v_tenant  public.tenants%ROWTYPE;
  v_existing_tenant_id uuid;
BEGIN
  -- 1. Auth check
  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'not authenticated' USING ERRCODE = '28000';
  END IF;

  -- 2. Validate inputs
  IF p_firm_name IS NULL OR length(trim(p_firm_name)) < 2 THEN
    RAISE EXCEPTION 'firm_name must be at least 2 characters' USING ERRCODE = '22023';
  END IF;
  IF p_full_name IS NULL OR length(trim(p_full_name)) < 2 THEN
    RAISE EXCEPTION 'full_name must be at least 2 characters' USING ERRCODE = '22023';
  END IF;

  -- 3. Idempotency: if a profile already exists, return its tenant
  SELECT tenant_id INTO v_existing_tenant_id
    FROM public.user_profiles
   WHERE id = v_user_id;

  IF v_existing_tenant_id IS NOT NULL THEN
    SELECT * INTO v_tenant FROM public.tenants WHERE id = v_existing_tenant_id;
    RETURN v_tenant;
  END IF;

  -- 4. Get the user's email from auth.users
  SELECT email INTO v_email FROM auth.users WHERE id = v_user_id;
  IF v_email IS NULL THEN
    RAISE EXCEPTION 'auth user has no email' USING ERRCODE = '22023';
  END IF;

  -- 5. Create the tenant
  INSERT INTO public.tenants (firm_name, email)
  VALUES (trim(p_firm_name), v_email)
  RETURNING * INTO v_tenant;

  -- 6. Link the user to the new tenant
  INSERT INTO public.user_profiles (id, tenant_id, full_name, role)
  VALUES (v_user_id, v_tenant.id, trim(p_full_name), 'firm_admin');

  RETURN v_tenant;
END;
$$;

-- Restrict execution to authenticated users only (service role + anon should not call this)
REVOKE ALL ON FUNCTION public.create_tenant_for_user(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.create_tenant_for_user(text, text) TO authenticated;

COMMENT ON FUNCTION public.create_tenant_for_user(text, text) IS
  'Atomic onboarding: creates a tenant and links the calling auth user as firm_admin. '
  'Idempotent — re-calling for an already-onboarded user returns their existing tenant.';
