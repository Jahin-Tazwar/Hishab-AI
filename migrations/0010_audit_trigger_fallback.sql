-- 0010_audit_trigger_fallback.sql
-- Audit trigger: when request.jwt.claim.sub is NULL (e.g. backend writes via service-role),
-- fall back to the row's own actor column (run_by / uploaded_by / created_by).
-- This means audit_log.user_id is correct without backend ceremony.
-- Spike: migrations/spike_results/audit_trigger_user_id_capture.md (Option 3).

CREATE OR REPLACE FUNCTION audit_log_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id  uuid;
  v_claim    text;
  v_row      jsonb;
BEGIN
  -- 1. Try the JWT claim first (frontend-originated writes)
  v_claim := current_setting('request.jwt.claim.sub', true);
  IF v_claim IS NOT NULL AND v_claim <> '' THEN
    BEGIN
      v_user_id := v_claim::uuid;
    EXCEPTION WHEN OTHERS THEN
      v_user_id := NULL;
    END;
  END IF;

  -- 2. Fall back to the row's own actor column (backend-originated writes).
  --    Each tenant-scoped table names the actor differently:
  --      clients.created_by | documents.uploaded_by
  --      vat_reconciliations.run_by | recon_line_items: inherit from parent recon (NULL ok)
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
  'Audit trigger v2: prefers JWT claim, falls back to NEW.run_by/uploaded_by/created_by '
  'so backend writes via service-role still produce non-NULL audit_log.user_id.';
