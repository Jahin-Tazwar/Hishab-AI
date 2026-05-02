-- 0001_public_schema.sql
-- System-level tables (no RLS) — tenants, user_profiles, audit_log, bd_obligation_definitions

-- ============================================================
-- TENANTS — one row per CA firm
-- ============================================================

CREATE TABLE tenants (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  firm_name     text NOT NULL,
  firm_name_bn  text,
  icab_reg_no   text UNIQUE,
  email         text NOT NULL,
  phone         text,
  address       text,
  plan          text NOT NULL DEFAULT 'starter',
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- USER_PROFILES — links auth.users to a tenant
-- ============================================================

CREATE TABLE user_profiles (
  id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  full_name   text NOT NULL,
  role        text NOT NULL DEFAULT 'firm_admin',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_profiles_tenant ON user_profiles(tenant_id);

-- ============================================================
-- AUDIT_LOG — append-only mutation log for tenant-scoped tables
-- ============================================================

CREATE TABLE audit_log (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  user_id     uuid,
  action      text NOT NULL CHECK (action IN ('insert', 'update', 'delete')),
  table_name  text NOT NULL,
  row_id      uuid NOT NULL,
  before      jsonb,
  after       jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_tenant_table ON audit_log(tenant_id, table_name, created_at DESC);

-- ============================================================
-- BD_OBLIGATION_DEFINITIONS — static seed of known BD obligations
-- ============================================================

CREATE TABLE bd_obligation_definitions (
  obligation_type   text PRIMARY KEY,
  display_name      text NOT NULL,
  applies_to        text[] NOT NULL,    -- entity_types: 'company','individual',etc.
  requires_vat_reg  boolean NOT NULL DEFAULT false,
  cadence           text NOT NULL CHECK (cadence IN ('monthly', 'quarterly', 'annual')),
  due_rule          text NOT NULL,      -- human-readable; actual logic in generate_compliance_events()
  law_reference     text,
  penalty_note      text
);
