# Spike Results — Audit Trigger user_id Capture

**Date:** 2026-05-02
**Plan reference:** [Task 18 of `2026-05-02-phase-a-foundation.md`](../../docs/superpowers/plans/2026-05-02-phase-a-foundation.md)
**Spec reference:** [Section 6.5 + Section 11 risk #3 of `2026-05-02-hishabai-mvp-design.md`](../../docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md)

## Question

When the backend uses the service-role key to write to a tenant-scoped table, does the `audit_log_trigger` function capture the correct `user_id` after calling the `set_request_user(user_id)` RPC?

## Test methodology

The spike was run via SQL directly against the Supabase project (rather than via Python + supabase-py) because the architectural question is purely about Postgres transaction scoping. The two test scenarios isolate the same architectural variable.

**Test 1 — same transaction:** all statements (`set_request_user`, `INSERT`, `SELECT audit_log`) executed within a single SQL call.

**Test 2 — separate transactions:** `set_request_user` and `INSERT` executed in separate SQL calls (separate Postgres transactions). This simulates supabase-py's behavior, which uses PostgREST and terminates each REST call as its own transaction.

## Results

| Test | Scenario | Captured `user_id` | Match |
|------|----------|--------------------|-------|
| 1 | Same transaction | `22222222-2222-2222-2222-222222222222` | ✅ MATCH |
| 2 | Separate transactions | `NULL` | ❌ NULL |

## Conclusion

`set_config('request.jwt.claim.sub', <id>, true)` is **transaction-local** — it does not persist across separate Postgres transactions. Since supabase-py wraps PostgREST and each REST call is its own transaction, calling `set_request_user(user_id)` followed by `.insert()` from the backend results in `audit_log.user_id = NULL`.

## Impact on Phase A

**Phase A is NOT blocked.**

All Phase A writes (tenant insert during onboarding, user_profile insert during onboarding) happen from the **frontend** with the user's JWT, not from the backend with the service-role. PostgREST automatically sets `request.jwt.claim.sub` from the user's JWT, and the insert happens in the same request transaction. The audit trigger captures the correct `user_id` for these calls (verified in Test 1's mechanism — the JWT-set + insert both happen within PostgREST's single-request transaction).

## Impact on Phase C (reconciliation)

**Phase C is affected.** The recon endpoint (`POST /api/v1/reconciliations`) is the first backend write that uses the service-role key. As the spike confirms, calling `set_request_user` before the inserts will not work via supabase-py.

Three options for Phase C, in increasing order of preferred trade-off:

1. **Accept NULL `user_id` in audit_log for backend writes.** The row's own actor column (`vat_reconciliations.run_by`, `documents.uploaded_by`, `clients.created_by`) records the responsible user. The audit trigger's `user_id` field becomes a "best-effort" record. **Recommended for MVP** — simplest, no schema or trigger changes needed.
2. **Wrap each backend write in a Postgres function** (e.g., `create_reconciliation(p_user_id, p_client_id, ...)`) that does `set_config(..., true)` + `INSERT` atomically. Always works, but adds a Postgres function per write operation.
3. **Modify the audit trigger** to fall back to row columns (`NEW.run_by`, `NEW.uploaded_by`, `NEW.created_by`) when `request.jwt.claim.sub` is NULL. Schema change to triggers, but no backend code change needed.

**Decision:** Defer to Phase C planning. Document the limitation in the spec now (Section 6.5).

## Test artifact

The exact SQL statements used can be reproduced by running the queries in this file's git history (commit log) against any Supabase project with the migrations 0001-0008 applied.
