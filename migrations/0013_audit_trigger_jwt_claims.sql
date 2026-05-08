-- 0013_audit_trigger_jwt_claims.sql
-- Audit trigger v3: also read request.jwt.claims (the modern PostgREST
-- format — a JSONB object containing every claim) before falling back
-- to row-level actor columns.
--
-- Why this exists: discovered during Phase D acceptance testing that
-- frontend-originated UPDATEs against compliance_events landed in
-- audit_log with user_id=NULL. The legacy single-claim setting
-- `request.jwt.claim.sub` is no longer set by PostgREST when the JWT
-- is asymmetric (ES256). Instead PostgREST sets `request.jwt.claims`
-- to the full JSON of the verified token. We now check both.
--
-- Order of precedence:
--   1. request.jwt.claim.sub   (legacy / explicit via set_request_user)
--   2. request.jwt.claims->>sub (modern PostgREST)
--   3. NEW.run_by / uploaded_by / created_by (backend writes that omit
--      set_request_user — Phase A spike "Option 3")

CREATE OR REPLACE FUNCTION audit_log_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id  uuid;
  v_claim    text;
  v_claims   jsonb;
  v_row      jsonb;
BEGIN
  -- 1a. Try the legacy single-claim setting (set_request_user, older PostgREST)
  v_claim := current_setting('request.jwt.claim.sub', true);
  IF v_claim IS NOT NULL AND v_claim <> '' THEN
    BEGIN
      v_user_id := v_claim::uuid;
    EXCEPTION WHEN OTHERS THEN
      v_user_id := NULL;
    END;
  END IF;

  -- 1b. Try the modern claims JSON (PostgREST 11+ with asymmetric JWTs)
  IF v_user_id IS NULL THEN
    v_claim := current_setting('request.jwt.claims', true);
    IF v_claim IS NOT NULL AND v_claim <> '' THEN
      BEGIN
        v_claims := v_claim::jsonb;
        v_user_id := (v_claims->>'sub')::uuid;
      EXCEPTION WHEN OTHERS THEN
        v_user_id := NULL;
      END;
    END IF;
  END IF;

  -- 2. Fall back to the row's own actor column (backend-originated writes)
  IF v_user_id IS NULL THEN
    v_row := CASE TG_OP WHEN 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    BEGIN
      v_user_id := COALESCE(
        (v_row->>'run_by')::uuid,
        (v_row->>'uploaded_by')::uuid,
        (v_row->>'created_by')::uuid
      );
    EXCEPTION WHEN OTHERS THEN
      v_user_id := NULL;
    END;
  END IF;

  IF (TG_OP = 'INSERT') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (NEW.tenant_id, v_user_id, 'insert', TG_TABLE_NAME, NEW.id, NULL, to_jsonb(NEW));
    RETURN NEW;
  ELSIF (TG_OP = 'UPDATE') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (NEW.tenant_id, v_user_id, 'update', TG_TABLE_NAME, NEW.id, to_jsonb(OLD), to_jsonb(NEW));
    RETURN NEW;
  ELSIF (TG_OP = 'DELETE') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (OLD.tenant_id, v_user_id, 'delete', TG_TABLE_NAME, OLD.id, to_jsonb(OLD), NULL);
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$;

COMMENT ON FUNCTION audit_log_trigger() IS
  'Audit trigger v3: prefers request.jwt.claim.sub (legacy / set_request_user), '
  'then request.jwt.claims->>sub (PostgREST 11+ with asymmetric JWTs), '
  'then NEW.run_by/uploaded_by/created_by.';
