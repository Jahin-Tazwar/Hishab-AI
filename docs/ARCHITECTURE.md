# HishabAI — Architecture

## 1. System Overview

```
┌──────────────────────────────────────────────────────┐
│         FRONTEND (React 18 + TypeScript)              │
│    CA Dashboard    │    Client Upload (email links)   │
└────────────────────┬─────────────────────────────────┘
                     │ REST / JSON + Supabase Realtime
                     ▼
┌──────────────────────────────────────────────────────┐
│           BACKEND (FastAPI, Python 3.11+)             │
│ Tenants │ Documents │ Reconciliation │ AI │ Calendar  │
│ Notices │ Reports │ Clients                           │
└────────┬──────────┬──────────────┬───────────────────┘
         │          │              │
   Supabase DB   Supabase       Supabase
   (PostgreSQL)  Storage        Auth (GoTrue)
         │
    Celery Workers (async OCR, AI tasks)
         │
    Vertex AI (Gemini 2.5 Flash)
```

## 2. Supabase as Platform Layer

HishabAI uses **Supabase** as the managed infrastructure layer:

| Concern | Solution |
|---------|----------|
| **Authentication** | Supabase Auth (GoTrue) — email/password, JWT tokens, session management |
| **Database** | Supabase PostgreSQL — accessed via `supabase-py` client + direct `asyncpg` for complex queries |
| **Storage** | Supabase Storage — document uploads with signed URLs |
| **Realtime** | Supabase Realtime — document processing status updates via WebSocket |
| **Row-Level Security** | Supabase RLS policies — tenant isolation enforced at database level |

**Project:** `qlrqbqisavkfxywkiuca`
**Region:** `ap-southeast-1` (Singapore — closest to Bangladesh)
**URL:** `https://qlrqbqisavkfxywkiuca.supabase.co`

## 3. Multi-Tenancy: Row-Level Security (RLS)

**Decision:** RLS with `tenant_id` column on all tenant-scoped tables.

Supabase Auth provides the user identity. A `user_profiles` table links
`auth.uid()` to a `tenant_id`. RLS policies use this to enforce isolation:

```sql
-- Example RLS policy on clients table
CREATE POLICY tenant_isolation ON clients
  FOR ALL USING (
    tenant_id = (
      SELECT tenant_id FROM user_profiles
      WHERE id = auth.uid()
    )
  );
```

## 4. Technology Stack

### Backend
- Language: Python 3.11+
- Framework: FastAPI (async)
- Supabase Client: supabase-py (auth, storage, simple queries)
- Direct DB: asyncpg + SQLAlchemy 2.0 (complex business logic queries)
- Migrations: Supabase MCP migrations (tracked in Supabase dashboard)
- Task Queue: Celery 5 + Redis (for async OCR/AI processing)
- Email: SendGrid API

### Frontend
- Framework: React 18 + TypeScript + Vite
- Supabase Client: @supabase/supabase-js (auth, realtime, storage)
- State: Zustand
- UI: shadcn/ui + Tailwind CSS
- Charts: Recharts
- Forms: React Hook Form + Zod
- HTTP: Axios with interceptors (for custom API calls to FastAPI)

### AI/ML
- LLM: **Google Vertex AI — Gemini 2.5 Flash** (document extraction, notice drafting, classification)
- OCR: Tesseract 5 with ben+eng language packs
- PDF parsing: pdfplumber (text PDFs) + pdf2image (scanned PDFs)
- Image preprocessing: OpenCV

### Infrastructure
- Database: Supabase PostgreSQL (managed)
- Auth: Supabase Auth (managed)
- Storage: Supabase Storage (managed)
- Task Queue: Redis (local or managed Redis service)
- Backend Hosting: Local dev → Cloud Run / Railway (production)

## 5. Project Structure

```
hishabai/
├── docs/                    # Specification documents
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory
│   │   ├── config.py        # Settings (pydantic-settings)
│   │   ├── database.py      # Supabase client + direct DB access
│   │   ├── dependencies.py  # FastAPI deps (auth, tenant, db)
│   │   ├── tenants/         # CA Firm management
│   │   ├── clients/         # CA's clients
│   │   ├── documents/       # Document ingestion + OCR
│   │   │   └── ocr/         # OCR engine + extractors
│   │   ├── reconciliation/  # VAT reconciliation engine
│   │   ├── notices/         # NBR notice AI
│   │   ├── calendar/        # Compliance calendar
│   │   ├── reports/         # Report generation
│   │   ├── ai/              # Vertex AI utilities
│   │   └── core/            # Formatting, exceptions, middleware
│   ├── tests/
│   └── requirements.txt
├── frontend/                # React + Vite app
└── README.md
```

## 6. Database Schema

Managed via Supabase migrations. Key tables:

**System tables (no RLS):** `user_profiles`, `tenants`, `audit_log`, `ai_token_usage`
**Tenant-scoped tables (RLS enforced):** `clients`, `compliance_obligations`,
`compliance_events`, `documents`, `document_extractions`, `vat_reconciliations`,
`recon_line_items`, `nbr_notices`

All tenant-scoped tables have a `tenant_id UUID NOT NULL REFERENCES tenants(id)` column
with RLS policies linking to the authenticated user's tenant via `user_profiles`.

## 7. Auth Flow

```
1. User signs up/logs in via Supabase Auth (frontend)
2. Supabase returns JWT with user ID
3. Frontend sends JWT to FastAPI backend in Authorization header
4. Backend validates JWT against Supabase JWKS
5. Backend looks up user's tenant_id from user_profiles
6. All DB queries are scoped to that tenant via RLS
```
