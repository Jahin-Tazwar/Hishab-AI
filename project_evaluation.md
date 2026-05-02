# HishabAI PROJECT.md — Full Evaluation

## Executive Summary

This is a **well-conceived product spec** for a Bangladesh-specific CA automation SaaS. The domain knowledge is excellent — MushaK forms, BIN/TIN validation, ITC reconciliation, and ICAB context are all correctly referenced. However, the document has **significant structural and technical issues** that will hurt execution velocity if left as-is.

> [!IMPORTANT]
> **Overall Verdict:** The *what* is strong. The *how* needs a rewrite. I'm recommending a restructured document that separates concerns, fixes architectural pitfalls, and gives you a realistic execution path.

---

## Category 1: Document Structure & Quality

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | **Garbled formatting throughout** — Sections 5–9 have interleaved content. Database DDL for `nbr_notices` is placed inside "API Design — 6.2 Authentication". Code blocks for reconciliation specs break mid-section. The calendar deadlines code appears inside the "AI Integration" section. | 🔴 Critical |
| 2 | **PDF-to-Markdown conversion artifacts** — Spaced-out text like `D o c u m e n t P r o c e s s i n g P i p e l i n e`, `Te n a n t = CA F i r m`, truncated lines like `100.` instead of `100.00`. This makes it unreliable as a reference document. | 🔴 Critical |
| 3 | **1,800 lines in a single file** — Far too long for a working reference. Should be split into focused documents. | 🟡 Moderate |
| 4 | **Mixing pseudocode with spec** — Half-written Python classes (e.g., `OCREngine`, `VATReconciliationEngine`) mix implementation detail with specification, creating ambiguity about what's prescribed vs. suggested. | 🟡 Moderate |
| 5 | **Repetitive preamble** — Lines 1–50 are motivational instructions to an AI. Wastes context window and adds no technical value. | 🟢 Minor |

### Recommendation
Split into 5 focused documents:
1. `PRODUCT.md` — Vision, core loop, regulatory context (Parts 1–2)
2. `ARCHITECTURE.md` — Stack, structure, DB schema (Parts 3–5)
3. `API_SPEC.md` — Endpoints, auth, response format (Part 6)
4. `BUSINESS_LOGIC.md` — Engine specs, AI integration (Parts 7–8)
5. `EXECUTION_PLAN.md` — Phases, acceptance criteria, scope guard (Parts 10–13)

---

## Category 2: Architecture Decisions

### What's Good
- FastAPI + async SQLAlchemy is a solid choice for I/O-bound workloads
- Schema-per-tenant isolation is the right call for financial data
- Celery for async OCR/processing is correct
- Feature flags for external integrations (Google Vision, SMS) — good practice

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | **Schema-per-tenant doesn't scale** — Creating a PostgreSQL schema per CA firm means every new tenant requires DDL execution (`CREATE SCHEMA`, then creating ~10 tables). At 100+ tenants, migrations become a nightmare. Each Alembic migration must be applied to *every* schema independently. | 🔴 Critical |
| 2 | **No WebSocket / SSE spec** — The doc mentions "websocket or polling" for notifications (line 1001) but specifies nothing. Document processing status *requires* real-time updates — polling the DB every 2 seconds per client is wasteful. | 🟡 Moderate |
| 3 | **Celery + Redis as both cache and queue** — Viable, but no separation of concerns. Redis failure takes out both caching and task processing. Should use separate Redis databases (db 0 for cache, db 1 for Celery broker). | 🟡 Moderate |
| 4 | **No deployment architecture specified** — "Kubernetes / ECS (production — decide at deployment)" is a non-decision. This choice affects how you design health checks, config injection, log routing, secrets management, and scaling policy. | 🟡 Moderate |
| 5 | **No API gateway / load balancer spec** — Multi-tenant SaaS needs rate limiting at the infrastructure level, not just application level. | 🟢 Minor |

### Critical Recommendation: Multi-Tenancy

**Replace schema-per-tenant with Row-Level Security (RLS) + `tenant_id` column.**

Why:
- Single set of tables, single Alembic migration applies everywhere
- PostgreSQL RLS policies enforce isolation at the database engine level (stronger than application-level `SET search_path`)
- Dramatically simpler ops: one schema to backup, index, vacuum, migrate
- Supabase natively supports RLS — if you ever move to Supabase managed, it's a natural fit

The `SET search_path` approach in the spec (line 1428) is also vulnerable to SQL injection if `schema` isn't properly sanitized — it's interpolated into a raw `text()` query.

---

## Category 3: Database Schema

### What's Good
- UUID primary keys everywhere — correct for multi-tenant
- BIN/TIN format validation with CHECK constraints
- JSONB for extracted_data — flexible for varying document types
- Good index coverage on high-query columns

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | **No `audit_log` table** — For a financial compliance product, every data mutation (create, update, delete) should have an immutable audit trail. CAs need this for regulatory defense. | 🔴 Critical |
| 2 | **No soft-delete pattern** — The spec mentions "soft delete" for documents (line 927) but the schema has no `deleted_at` column. Need `deleted_at TIMESTAMPTZ` on `documents`, `clients`, etc. | 🟡 Moderate |
| 3 | **`users` table in `public` schema** — With schema-per-tenant, this means cross-schema JOINs are needed for every "who did this" query. With RLS approach, this goes away. | 🟡 Moderate |
| 4 | **Missing `ai_token_usage` table** — The spec mentions "logs token usage for billing tracking" (line 1325) but there's no table for it. You need to track per-tenant Claude API costs. | 🟡 Moderate |
| 5 | **`compliance_events.period_label`** is `VARCHAR(32)` — Too loosely typed. Different formats ('2024-01', 'FY2023-24', 'Q1 FY2024') make querying a nightmare. Normalize to `period_start DATE` + `period_end DATE`. | 🟡 Moderate |
| 6 | **No file versioning** — Documents can be reprocessed (line 928) but there's no way to see previous extractions. Need `document_extractions` table with version tracking. | 🟢 Minor |

---

## Category 4: Security

### What's Good
- JWT with tenant_id in claims — correct pattern
- Presigned URLs with 15-min expiry
- Server-side encryption for documents
- Rate limiting specs are reasonable
- MIME type server-side validation

### Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | **SQL injection in tenant schema switching** — Line 1428: `f"SET search_path TO {schema}, public"` uses Python f-string interpolation in a SQL query. This is a **direct SQL injection vector**. If `schema_name` in the JWT is tampered with, an attacker can execute arbitrary SQL. | 🔴 Critical |
| 2 | **JWT secret rotation not addressed** — No mechanism to rotate `JWT_SECRET_KEY` without invalidating all sessions. Need a key-pair approach or at minimum a `JWT_PREVIOUS_SECRET` for graceful rotation. | 🟡 Moderate |
| 3 | **No CORS specification** — Multi-origin setup (CA dashboard + client portal) needs explicit CORS configuration. Missing entirely. | 🟡 Moderate |
| 4 | **Client portal token is a static `VARCHAR(64)`** — If this token is guessed or leaked, there's no expiry, no IP binding, no revocation mechanism. Should be a short-lived, signed token (like a JWT with limited claims). | 🟡 Moderate |
| 5 | **No CSP / security headers spec** — Financial SaaS needs Content-Security-Policy, X-Frame-Options, HSTS, etc. | 🟢 Minor |

---

## Category 5: Scope & Feasibility

### Honest Assessment

The MVP scope described here is realistically **4–6 months of full-time work for a 3-person team** (1 backend, 1 frontend, 1 DevOps/AI). As a solo AI-assisted build, it's **8–12 weeks of aggressive daily effort**.

### Scope Reduction Recommendations

| Feature | Recommendation |
|---------|---------------|
| Client Portal (Phase G) | **Defer entirely.** A separate Next.js app for clients to upload documents is overkill for MVP. A simple email-based upload link (S3 presigned URL via email) is sufficient. |
| SMS Notifications (SSL Wireless) | **Defer.** Email-only for MVP. SMS adds integration complexity for low marginal value. |
| Google Vision OCR Fallback | **Defer.** Start with Tesseract only. Add Vision API when you have real accuracy data showing Tesseract isn't enough. |
| MIS Report Generator | **Simplify.** Generate Excel exports, not formatted PDF reports with AI narratives. CAs already work in Excel. |
| Bank Statement Parser | **Simplify.** Support CSV/Excel upload with column mapping, not template-specific parsing for individual banks. |
| Notice AI Draft | **Keep but simplify.** This is a genuine differentiator. But start with a single notice type (Show Cause VAT) rather than all 6. |

### Revised Phase Order (Optimized for fastest time-to-value)

```
Phase A: Foundation (Docker, DB, Auth)          → Week 1-2
Phase B: Client Management + Calendar           → Week 2-3  
Phase C: Document Upload + OCR (MushaK only)    → Week 3-5
Phase D: Reconciliation Engine                  → Week 5-7
Phase E: Frontend (dashboard, upload, recon)    → Week 7-9
Phase F: Notice AI (Show Cause VAT only)        → Week 9-10
Phase G: Polish, email notifications            → Week 10-11
```

---

## Category 6: Technology Stack

### Good Choices
- FastAPI — excellent for async Python APIs
- SQLAlchemy 2.0 async — mature, well-typed
- React 18 + TypeScript — industry standard
- shadcn/ui + Tailwind — fast to build, professional look
- Zustand — simpler than Redux for this scale
- React Hook Form + Zod — strong form validation

### Questionable Choices

| Choice | Issue | Alternative |
|--------|-------|-------------|
| Tesseract 5 for Bengali OCR | Tesseract's Bengali accuracy is mediocre (~60-70% on real-world forms). You'll hit the Vision API fallback constantly. | **Start with Google Document AI** — it has much better Bengali support and structured form extraction. Tesseract as the fallback, not primary. |
| `python-jose` for JWT | `python-jose` is unmaintained (last release 2022). | Use `PyJWT` instead — actively maintained, widely used. |
| `pdfplumber` for text PDFs | Good choice, but specify version pinning. Recent versions had breaking changes. | Pin `pdfplumber>=0.10.0,<0.12.0` |
| MinIO for local dev | Reasonable, but adds Docker container overhead. | For dev, use local filesystem with S3-compatible interface abstracted. Deploy MinIO only in staging/prod. |
| Separate Next.js for client portal | Unnecessary build system for a simple upload page. | Simple React route within the main frontend, or even a standalone HTML page. |

---

## Category 7: Missing Specifications

These are things the spec doesn't address that you'll need before writing code:

| Missing Item | Impact |
|--------------|--------|
| **Error monitoring** (Sentry, etc.) | Will fly blind in production |
| **Database backup strategy** | Financial data with no backup spec is negligent |
| **CI/CD pipeline** | No mention of testing/deployment automation |
| **Logging strategy** (structured logging, log levels) | "Log but don't expose" is stated but not specified |
| **Health check endpoints** | Docker/K8s need `/health` and `/ready` endpoints |
| **API versioning migration plan** | `/api/v1` is specified but no plan for v2 transition |
| **Data retention policy** | How long to keep documents? Compliance requires retention rules |
| **Bangla font rendering in PDFs** | MIS report PDFs with BDT amounts need proper font support |
| **Timezone handling** | Bangladesh is UTC+6, but the spec doesn't mandate timezone-aware datetime storage (it uses TIMESTAMPTZ which is good, but the API should enforce Asia/Dhaka display) |

---

## Summary of Priority Actions

### 🔴 Must Fix Before Writing Code

1. **Fix document structure** — Split into focused files, fix garbled formatting
2. **Replace schema-per-tenant with RLS** — Eliminates migration nightmare and SQL injection risk
3. **Add audit logging table** — Non-negotiable for financial compliance
4. **Fix SQL injection in schema switching** — Even if you keep schema-per-tenant, parameterize the query
5. **Reduce scope** — Defer client portal, SMS, Google Vision fallback, bank-specific parsers

### 🟡 Fix During Phase A

6. Add soft-delete columns to all major tables
7. Add `ai_token_usage` table
8. Normalize `period_label` to date range
9. Switch from `python-jose` to `PyJWT`
10. Specify CORS, CSP, and security headers
11. Add health check endpoints

### 🟢 Address During Development

12. Add structured logging spec (use `structlog`)
13. Specify CI/CD pipeline
14. Add backup strategy
15. Consider Google Document AI as primary OCR for Bengali

---

## Next Steps

I recommend we proceed in this order:

1. **Restructure PROJECT.md** into the 5 focused documents
2. **Create the project scaffold** — Docker, FastAPI app factory, DB setup
3. **Implement Phase A** — Foundation with the corrected multi-tenancy approach

Want me to start with any of these?
