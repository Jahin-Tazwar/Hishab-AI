# HishabAI — Execution Plan

## Revised Timeline (Solo + AI-assisted)

| Phase | Scope | Weeks | Acceptance Criteria |
|-------|-------|-------|---------------------|
| A | Foundation (Docker, DB, Auth) | 1-2 | Register firm, login, JWT auth, tenant isolation via RLS |
| B | Client Management + Calendar | 2-3 | 10 clients with correct BD compliance deadlines |
| C | Document Upload + OCR (MushaK) | 3-5 | Upload MushaK 6.2, extract fields, confidence scoring |
| D | Reconciliation Engine | 5-7 | Reconcile 100 invoices in <30s, CA override works |
| E | Frontend (dashboard, upload, recon) | 7-9 | Full end-to-end flow in browser |
| F | Notice AI (Show Cause VAT only) | 9-10 | Upload SCN, classify, generate draft with legal citations |
| G | Polish + Email Notifications | 10-11 | Deadline reminders, error monitoring, production readiness |

## Phase A: Foundation (CURRENT)

### Deliverables
1. Docker Compose: PostgreSQL 16, Redis 7, Backend (FastAPI hot reload)
2. Database: Alembic setup, all tables with RLS policies, audit_log table
3. Auth: Register (creates tenant + admin user), Login (JWT), Refresh, Middleware
4. Tenant: RLS-based isolation, tenant profile endpoints
5. Health checks: `/health` and `/ready`

### Acceptance Test
- Register a firm → creates tenant record + admin user
- Login → receive JWT with tenant_id claim
- Make authenticated API calls → data scoped to tenant
- Attempt cross-tenant access → returns 403
- RLS policies prevent data leakage even with raw SQL

## Code Quality Standards

- Type hints on all Python functions (Pydantic models for all I/O)
- Async everywhere (DB calls, HTTP, file I/O)
- Pydantic validation on all user input
- Log errors internally, return safe error codes to API
- 85%+ test coverage on business logic modules
- Structured logging via structlog

## Naming Conventions

```python
tin          # Not 'taxpayer_id' or 'tax_number'
bin          # Not 'vat_reg' — always 'bin'
mushak_no    # The MushaK form number
nbr          # Always uppercase
bdt          # Suffix for all monetary fields in Taka
```
