-- 0005_audit_trigger.sql
-- Generic audit trigger: writes every insert/update/delete on tenant-scoped tables
-- to audit_log. user_id pulled from current_setting('request.jwt.claim.sub', true).

CREATE OR REPLACE FUNCTION audit_log_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id  uuid;
  v_claim    text;
BEGIN
  -- Try to read the JWT subject claim. May be NULL when called by:
  -- - the backend with service-role key (unless set_request_user was called first)
  -- - a Postgres function not in a user-initiated transaction
  v_claim := current_setting('request.jwt.claim.sub', true);
  IF v_claim IS NOT NULL AND v_claim <> '' THEN
    BEGIN
      v_user_id := v_claim::uuid;
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

-- Apply to every tenant-scoped table

CREATE TRIGGER audit_clients
  AFTER INSERT OR UPDATE OR DELETE ON clients
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_compliance_obligations
  AFTER INSERT OR UPDATE OR DELETE ON compliance_obligations
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_compliance_events
  AFTER INSERT OR UPDATE OR DELETE ON compliance_events
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_documents
  AFTER INSERT OR UPDATE OR DELETE ON documents
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_vat_reconciliations
  AFTER INSERT OR UPDATE OR DELETE ON vat_reconciliations
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();

CREATE TRIGGER audit_recon_line_items
  AFTER INSERT OR UPDATE OR DELETE ON recon_line_items
  FOR EACH ROW EXECUTE FUNCTION audit_log_trigger();
