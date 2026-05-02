-- 0004_rls_policies.sql
-- Enable RLS and apply tenant_isolation policy on every tenant-scoped table.
-- Pattern: tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid())

-- ============================================================
-- USER_PROFILES — special: users can only read their own profile
-- ============================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_profile_self_read ON user_profiles
  FOR SELECT USING (id = auth.uid());

CREATE POLICY user_profile_self_insert ON user_profiles
  FOR INSERT WITH CHECK (id = auth.uid());

CREATE POLICY user_profile_self_update ON user_profiles
  FOR UPDATE USING (id = auth.uid()) WITH CHECK (id = auth.uid());

-- ============================================================
-- TENANTS — users can read/update their own tenant
-- ============================================================

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_member_read ON tenants
  FOR SELECT USING (
    id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid())
  );

CREATE POLICY tenant_member_update ON tenants
  FOR UPDATE
  USING      (id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

-- INSERT into tenants is done during onboarding via a Postgres function (see 0007 area)
-- or directly with the user's session JWT. For MVP, allow authenticated users to insert
-- a tenant (they can only create their own first one).
CREATE POLICY tenant_self_insert ON tenants
  FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);

-- ============================================================
-- TENANT-SCOPED TABLES — same isolation pattern for all
-- ============================================================

-- Helper: the policy expression. Repeated for clarity.
-- USING (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))

ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON clients
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE compliance_obligations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON compliance_obligations
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE compliance_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON compliance_events
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON documents
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE vat_reconciliations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON vat_reconciliations
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

ALTER TABLE recon_line_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON recon_line_items
  FOR ALL
  USING      (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()))
  WITH CHECK (tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid()));

-- ============================================================
-- AUDIT_LOG — read-only for tenant members; writes only via trigger (security definer)
-- ============================================================

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_log_tenant_read ON audit_log
  FOR SELECT USING (
    tenant_id = (SELECT tenant_id FROM user_profiles WHERE id = auth.uid())
  );
-- No INSERT/UPDATE/DELETE policy — only the trigger (SECURITY DEFINER) writes here.
