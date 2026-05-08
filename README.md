# HishabAI

Multi-tenant SaaS for Bangladeshi Chartered Accountancy firms — VAT
reconciliation, compliance deadline tracking, and NBR notice drafting.
This repo holds the backend (FastAPI + Supabase), the frontend (React +
Vite), and the SQL migrations.

## Architecture

```
  ┌────────┐   HTTPS    ┌──────────────┐    HTTPS    ┌──────────┐
  │ Browser│ ─────────▶ │ React + Vite │ ──────────▶ │ FastAPI  │
  └────────┘            └──────────────┘             └────┬─────┘
                                                          │
                                                          ▼
                                                   ┌────────────┐
                                                   │  Supabase  │
                                                   │ (Postgres, │
                                                   │  Auth,     │
                                                   │  Storage)  │
                                                   └────────────┘
```

The frontend talks to FastAPI for compute-heavy work (reconciliation
matching, XLSX export) and directly to Supabase via `@supabase/supabase-js`
for everything else (auth, reads, simple writes — RLS enforced).

## Tech stack

| Layer | Tools |
|------|------|
| Backend | Python 3.11, FastAPI, supabase-py, structlog, pytest |
| Frontend | React 18, TypeScript, Vite, TanStack Query, Zustand, shadcn/ui, Tailwind, Vitest |
| Database | Supabase (Postgres 15) with Row-Level Security |
| Storage | Supabase Storage (buckets `documents` and `recon-files`) |
| Auth | Supabase Auth (ES256 asymmetric JWTs) |
| Deploy | Render (backend, Docker), Netlify (frontend) |

## Local setup

Prerequisites: Python 3.11+, Node 20+, a Supabase project.

1. **Clone and install deps**
   ```bash
   git clone <this-repo>
   cd hishabai
   python -m venv backend/.venv
   source backend/.venv/bin/activate    # Windows: backend\.venv\Scripts\activate
   pip install -r backend/requirements.txt
   cd frontend && npm install && cd ..
   ```

2. **Configure environment variables**
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env.local
   ```
   Fill in `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   and `SUPABASE_JWT_SECRET` from your Supabase project settings.

3. **Apply migrations to Supabase**

   Apply every file in `migrations/` in lexical order (13 files, `0001` →
   `0013`). Easiest path is to paste each file into the SQL Editor on the
   Supabase dashboard. For automation, point `psql` at your project's
   connection string:
   ```bash
   for f in migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
   ```

4. **Run the backend**
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

5. **Run the frontend** (in a second shell)
   ```bash
   cd frontend
   npm run dev
   ```
   Visit http://localhost:5173.

## Seeding demo data

For walkthroughs and screenshots, the seeder creates one tenant, three
clients, 90 days of compliance events, and one reconciliation with eight
deliberate mismatches:

```bash
cd backend
python -m scripts.seed_demo --email demo@hishabai.test --password DemoPass123!
```

Re-running with the same email is idempotent. Pass `--reset` to wipe the
demo tenant and reseed from clean. Pass `--regenerate-fixtures` to re-derive
the two demo XLSX files from source.

## Tests

```bash
# Backend
cd backend && pytest -q

# Frontend
cd frontend && npm test
```

The seeder integration test (`tests/scripts/test_seed_demo.py`) is skipped
unless `SEED_TEST_SUPABASE_URL` and `SEED_TEST_SUPABASE_SERVICE_ROLE_KEY`
are set — point those at a disposable project, never prod.

## Deploy

### Frontend → Netlify

1. Connect this repo to Netlify. Netlify auto-detects `netlify.toml`.
2. In Site Settings → Environment, set `VITE_SUPABASE_URL`,
   `VITE_SUPABASE_ANON_KEY`, and `VITE_API_URL` (the Render-deployed
   backend URL — see below).
3. After the first successful deploy, copy the site URL.

### Backend → Render

1. In the Render dashboard → New → Blueprint, point at this repo. Render
   reads `render.yaml`.
2. Render will prompt for the secret env vars marked `sync: false`:
   `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_JWT_SECRET`, `FRONTEND_ORIGIN` (paste the Netlify URL).
3. After the first deploy, copy the Render service URL into `VITE_API_URL`
   on Netlify and redeploy the frontend.

`/health` and `/ready` are wired up — Render uses `/health` for its
liveness probe.

## Project structure

```
.
├── backend/        # FastAPI service
│   ├── app/        # Application code (auth, reconciliation, etc.)
│   ├── scripts/    # Operational scripts (seed_demo.py + demo fixtures)
│   └── tests/      # pytest suite
├── frontend/       # React + Vite app
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── pages/
│   │   └── store/
│   └── public/
├── migrations/     # SQL files applied in lexical order
└── docs/           # Specs and plans (Phase A–E)
```

## Documentation

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for design specs
and [`docs/superpowers/plans/`](docs/superpowers/plans/) for the
phase-by-phase implementation plans (A–E).
