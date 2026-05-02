-- 0006_set_request_user.sql
-- RPC the backend calls before service-role writes, so the audit trigger
-- can capture the correct user_id.
--
-- IMPORTANT: set_config(..., true) is transaction-local. Effective only within
-- the same transaction. Backend must call this and the subsequent write in the
-- same supabase-py call chain (i.e., same HTTP connection / transaction).
-- The Task 18 spike validates whether this works end-to-end with supabase-py.

CREATE OR REPLACE FUNCTION set_request_user(p_user_id uuid) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  PERFORM set_config('request.jwt.claim.sub', p_user_id::text, true);
END;
$$;

-- Allow authenticated and service_role to call it
GRANT EXECUTE ON FUNCTION set_request_user(uuid) TO authenticated, service_role;
