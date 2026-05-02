# Migrations

SQL migration files for the Supabase Postgres database. Applied in numerical order.

## Apply migrations

**Option A — Supabase MCP (preferred):**
Use `mcp__supabase__apply_migration` tool with the contents of each file.

**Option B — Supabase Dashboard:**
SQL Editor → paste each file's contents → Run.

**Option C — psql directly:**
```bash
psql "$DATABASE_URL" -f migrations/0001_public_schema.sql
psql "$DATABASE_URL" -f migrations/0002_tenant_tables.sql
# ...etc
```

## Order

1. `0001_public_schema.sql` — system tables (no RLS)
2. `0002_tenant_tables.sql` — tenant-scoped tables (RLS-ready, but RLS not yet enabled)
3. `0003_indexes.sql` — performance indexes
4. `0004_rls_policies.sql` — enable RLS + policies for tenant-scoped tables
5. `0005_audit_trigger.sql` — audit_log trigger function + applications
6. `0006_set_request_user.sql` — RPC for backend to set request user
7. `0007_generate_compliance_events.sql` — calendar event generator function
8. `0008_seed_obligations.sql` — seed `bd_obligation_definitions`

## Rollback

This MVP does not implement down-migrations. To roll back, drop the affected tables manually and re-apply from the desired migration onward.
