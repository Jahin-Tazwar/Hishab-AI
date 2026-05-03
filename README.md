# HishabAI

Multi-tenant SaaS that automates the pre-advisory workflow of Bangladeshi Chartered Accountancy firms. The MVP focuses on **VAT reconciliation** — uploading purchase register + supplier export XLSX files and computing ITC risk in BDT.

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the design spec and [`docs/superpowers/plans/`](docs/superpowers/plans/) for implementation plans.

## Stack

- **Frontend:** React 18 + TypeScript + Vite + Tailwind + shadcn/ui (deployed to Vercel)
- **Backend:** FastAPI 0.115 (Python 3.11+) (deployed to Cloud Run)
- **Database / Auth / Storage:** Supabase (PostgreSQL, GoTrue, Storage)
- **AI:** Deferred to Phase 2 (no LLM in MVP)

## Local development

### Prerequisites
- Python 3.11+
- Node.js 20+
- A Supabase project (existing: `qlrqbqisavkfxywkiuca`, Singapore)
- Supabase service-role key, anon key, JWT secret

### 1. Apply database migrations

See [`migrations/README.md`](migrations/README.md) for instructions. Apply files `0001` through `0008` in order to your Supabase project.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with real Supabase credentials
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/health` — should return `{"status":"healthy",...}`.

Run tests:
```bash
pytest
```

Run integration tests (requires real Supabase):
```bash
pytest --run-integration
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local with real Supabase URL + anon key + backend URL
npm run dev
```

Visit `http://localhost:5173`.

## Deployment

- **Frontend:** Push to GitHub → connect to Vercel → set env vars (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`) → auto-deploys on push.
- **Backend:** Build with `gcloud run deploy` against `backend/Dockerfile`. Set env vars from `backend/.env.example`. Region: `asia-southeast1` (Singapore, same as Supabase).

## Phases

- ✅ **Phase A** — Foundation (schema, RLS, audit, auth, onboarding) — current
- ⏳ **Phase B** — Clients module
- ⏳ **Phase C** — Reconciliation engine + report (the hero)
- ⏳ **Phase D** — Compliance calendar + dashboard
- ⏳ **Phase E** — Polish + ship

## Naming conventions (Bangladesh-specific)

- `tin` — 12-digit Taxpayer ID
- `bin` — 9-digit Business ID (VAT)
- `mushak_no` — MushaK form number
- `nbr` — National Board of Revenue (always uppercase)
- `bdt` — suffix for BDT-denominated monetary fields
- Currency: `৳ 12,34,567.89` (South Asian grouping, lakh/crore)
- Dates: DD/MM/YYYY (display) / ISO 8601 (storage)
- Fiscal year: July 1 — June 30 (e.g., FY2024-25)
