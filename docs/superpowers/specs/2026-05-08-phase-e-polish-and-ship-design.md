# Phase E — Polish + Ship (design)

**Date:** 2026-05-08
**Status:** Approved for planning
**Predecessors:** Phase D (Calendar + Dashboard) — tagged `phase-d-complete`

## 1. Goal

Get HishabAI to a state where:

1. A stranger CA can be handed the deployed URL with a 5-minute walkthrough.
2. A fresh `git clone` is up and running locally in under 10 minutes.
3. Production-style failures (network blip, 500 from API, mistyped URL) don't show users a blank screen.

This is the final phase of the MVP. Live deployment to Netlify (frontend) and Render (backend) is owned by the user, not by this phase — but every config artifact required for that deploy lives in the repo by end of phase.

## 2. Out of scope

- Live deploy to Netlify / Render (user handles).
- e2e Playwright suite — manual smoke test only.
- PWA, offline mode, analytics, telemetry.
- Marketing landing page (`/` keeps redirecting to `/login`).
- Error reporting integration (Sentry etc.) — left for post-MVP.

## 3. Deliverables (six)

| # | Deliverable | Where it lives |
|---|---|---|
| 1 | `seed_demo.py` script — one tenant, 3 demo clients, 1 reconciliation with realistic mismatches | `backend/scripts/seed_demo.py` + `backend/scripts/fixtures/*.xlsx` |
| 2 | Top-level `<ErrorBoundary>` + per-page boundaries | `frontend/src/components/ErrorBoundary.tsx`, mounted in `main.tsx` and `router.tsx` |
| 3 | Real `<NotFound />` page (replaces `*` → `/login` redirect) | `frontend/src/pages/NotFound.tsx` + `router.tsx` change |
| 4 | Consistent loading states — shared `<Spinner />` + `<PageLoading />` | `frontend/src/components/ui/Loading.tsx` + 4–5 page touch-ups |
| 5 | `/health` and `/ready` audit + version field + tests | `backend/app/main.py`, `backend/app/__init__.py`, `backend/tests/test_health.py` |
| 6 | Project root `README.md`, `render.yaml`, `netlify.toml`, `.env.example` audit | repo root + `frontend/.env.example` |

## 4. Sample data seeder (deliverable 1)

**File:** `backend/scripts/seed_demo.py`

**Invocation:**
```
python -m scripts.seed_demo --email demo@hishabai.test --password DemoPass123!
```

**Steps (idempotent on re-run):**

1. **Auth user** — calls Supabase Admin API (`auth.admin.create_user` via service-role) with `email_confirm=True`. If user exists, fetches the id and continues.
2. **Tenant** — `INSERT INTO tenants (name) VALUES ('Demo CA Firm')` (skip if exists by name).
3. **`user_profile`** — links the auth user to the tenant.
4. **3 clients** with deliberate variety:
   - **"Acme Textiles Ltd"** — Pvt Ltd, BIN `123456789`, TIN `123456789012`, VAT-registered, June 30 FY end.
   - **"Hossain & Co Partnership"** — Partnership, no BIN, TIN `987654321098`, not VAT-registered.
   - **"Rahman Trading"** — Individual, BIN `555666777`, TIN `111222333444`, VAT-registered.
5. **Compliance events** — calls existing `generate_compliance_events` RPC for each client over the next 90 days.
6. **One reconciliation** for Acme Textiles, period = previous calendar month:
   - Reads fixtures from `backend/scripts/fixtures/demo_register.xlsx` and `demo_supplier.xlsx` (committed, ~5KB each).
   - 30 rows with **8 deliberate mismatches**: 2 amount-mismatches, 2 missing in supplier export, 2 missing in register, 2 fuzzy-name matches.
   - Calls `reconciliation.service.run_reconciliation()` directly (no HTTP, no Storage).
   - Writes `reconciliations` row + `reconciliation_line_items` rows.

**Why fixtures committed (not generated at run time):** Determinism. A randomly-generated demo with different at-risk-ITC numbers each run makes the "stranger CA test" non-comparable.

**CLI flags:**
- `--email` (required)
- `--password` (required first run; ignored if user exists)
- `--reset` (optional) — deletes the demo tenant + everything cascading from it before reseeding.
- `--regenerate-fixtures` (optional, dev-only) — regenerates the two XLSX files from inline Python data, then exits without seeding.

**Test:** `backend/tests/scripts/test_seed_demo.py` — single integration test, marked `pytest.mark.integration`, skipped if `SEED_TEST_SUPABASE_URL` env var missing. Asserts the recon's at-risk ITC matches a known expected value.

## 5. Frontend polish (deliverables 2–4)

### 5.1 Error boundaries

`frontend/src/components/ErrorBoundary.tsx` — class component (React requires class for `componentDidCatch`).

**Behavior:**
- Catches render-time errors below it.
- Fallback UI: centered card with title "Something went wrong", one-line message, two buttons — "Try again" (calls `resetErrorBoundary` to remount children via `key` reset) and "Go to dashboard".
- Logs to `console.error` in dev. Production swallows the stack trace from the user's view.

**Mount points (two layers):**
- **Root boundary** wraps `<RouterProvider>` in `main.tsx`. Catches anything that bypasses route-level boundaries.
- **Page boundary** (`<RouteBoundary>` wrapper) wraps each authenticated route's children inside `AppShell`. So a crash in `<Dashboard />` doesn't blank the whole app — shell + nav stay rendered, only the page slot shows the fallback.

**Doesn't catch:** async errors in queries/mutations (those are TanStack Query's `error` state — already handled per-hook). Boundaries are for unexpected throws during render.

### 5.2 NotFound page

`frontend/src/pages/NotFound.tsx` — replaces the current `* → /login` redirect.

**Content:**
- Heading "Page not found"
- Body: "The page you're looking for doesn't exist or has been moved."
- Button: "Back to dashboard" (authed) or "Back to login" (unauthed)

**Shell selection:** read auth store at render time and wrap output in `<AppShell>` or `<AuthLayout>` accordingly.

**Router change:** in `router.tsx`, replace `{ path: "*", element: <Navigate to="/login" replace /> }` with the NotFound element.

### 5.3 Loading states

`frontend/src/components/ui/Loading.tsx` exports two pieces:

- `<Spinner />` — small inline spinner (Lucide `Loader2` with `animate-spin`). For inline indicators in buttons, table rows, widget cards.
- `<PageLoading label?: string />` — full-page skeleton: centered spinner with optional label below in `text-sm text-slate-500` (default "Loading…").

**Touch-ups (replace ad-hoc `"Loading…"` text):**
- `ReconReport.tsx` — swap to `<PageLoading label="Loading reconciliation…" />`.
- `ClientDetail.tsx` — same swap.
- `Clients.tsx` / `ClientsTable.tsx` — inline `<Spinner />` + label.
- `UpcomingDeadlinesWidget.tsx` / `OverdueClientsWidget.tsx` / `RecentReconciliationsWidget.tsx` — inline `<Spinner />` in card body when `isLoading`.

**Goal:** consistency, not redesign. Same colors, same sizes, one place to tweak later.

### 5.4 Tests

- `frontend/src/components/__tests__/ErrorBoundary.test.tsx` — renders a child that throws, asserts fallback appears + "Try again" remounts children when the throw is removed.
- `frontend/src/pages/__tests__/NotFound.test.tsx` — renders the page, asserts "Back to dashboard" link points to `/dashboard` when authed, `/login` when not. Mock the Zustand auth store.
- No tests for `<Spinner>` / `<PageLoading>` — trivial markup.

## 6. Backend audit (deliverable 5)

### 6.1 `/health` and `/ready`

Current `/ready` already pings `tenants` table via `supabase-py`. Correct as-is — fails (503) if SUPABASE_URL is wrong, key is wrong, or project is paused.

**Two small improvements:**
- Add `version` field to both responses. Source: `backend/app/__init__.py` `__version__ = "0.1.0"` (create file if missing).
- Add `backend/tests/test_health.py` with two cases: `/health` returns 200, `/ready` returns 200 when DB reachable. Use existing FastAPI test-client pattern; mock `get_supabase_admin` to return a stub.

### 6.2 CORS hygiene

In `backend/app/main.py`:
- Remove the trailing-whitespace artifact in `allow_origins` list.
- Add an env-driven production origin: read `os.environ.get("FRONTEND_ORIGIN", "")` and append to the list if non-empty. So setting `FRONTEND_ORIGIN=https://hishabai.netlify.app` on Render adds the prod frontend without a code change.

## 7. Docs + deploy config (deliverable 6)

### 7.1 `.env.example` audit

- `backend/.env.example` — already exists. Diff against `backend/app/config.py` Settings model and add any missing keys with one-line comments.
- `frontend/.env.example` — create if missing. Contains `VITE_SUPABASE_URL=...` and `VITE_SUPABASE_ANON_KEY=...` with placeholder values.

### 7.2 `render.yaml`

Repo root. Blueprint defining one web service:

```yaml
services:
  - type: web
    name: hishabai-api
    runtime: docker
    rootDir: backend
    dockerfilePath: ./Dockerfile
    healthCheckPath: /health
    plan: starter
    region: singapore
    numInstances: 1
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: SUPABASE_ANON_KEY
        sync: false
      - key: JWT_SECRET
        sync: false
      - key: FRONTEND_ORIGIN
        sync: false
```

(Keys with `sync: false` prompt Render to ask for values on first deploy. Final list confirmed against `backend/app/config.py` during execution.)

### 7.3 `netlify.toml`

Repo root:

```toml
[build]
  base = "frontend"
  publish = "frontend/dist"
  command = "npm run build"

[build.environment]
  NODE_VERSION = "20"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

The redirect block is required for React Router deep links to work on Netlify's static host.

### 7.4 `README.md`

Repo root, ~120-180 lines, runbook-style. Sections:

1. **What is HishabAI** — 3 sentences from CLAUDE.md.
2. **Architecture** — one paragraph + 4-line ASCII diagram (Browser → React/Vite → FastAPI → Supabase).
3. **Local setup** — numbered steps:
   1. Clone, install backend deps (`pip install -r backend/requirements.txt` in a venv).
   2. Install frontend deps (`cd frontend && npm install`).
   3. Copy `.env.example → .env` in both `backend/` and `frontend/`, fill values.
   4. Apply migrations to Supabase (Supabase dashboard SQL editor or `psql`).
   5. `cd backend && uvicorn app.main:app --reload`.
   6. `cd frontend && npm run dev`.
   7. Visit `http://localhost:5173`.
4. **Seeding demo data** — one paragraph + `seed_demo.py` invocation.
5. **Tests** — `pytest` (backend), `npm test` (frontend).
6. **Deploy** — two subsections:
   - *Frontend → Netlify:* connect repo; Netlify reads `netlify.toml`; set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in dashboard.
   - *Backend → Render:* create a Blueprint from `render.yaml`; set the `sync: false` env vars when prompted; on first deploy copy the generated URL into `FRONTEND_ORIGIN` on Netlify and `FRONTEND_ORIGIN` on Render.
7. **Tech stack** — table of stack components + versions.
8. **Project structure** — top 2 levels only.

## 8. Acceptance test (manual)

After all six deliverables land:

1. From a fresh clone, follow README's "Local setup" — should hit dashboard in <10 minutes.
2. Run `python -m scripts.seed_demo --email demo@hishabai.test --password DemoPass123!`. Log in as the demo user. Dashboard shows 3 clients, upcoming deadlines populated, one recent reconciliation with mismatches visible.
3. Manually trigger a render error (e.g. visit a client detail with a broken hook temporarily): see the page-level fallback card, not a blank screen. Click "Try again" — recovers.
4. Visit `/clients/this-uuid-does-not-exist-blah`: NotFound page renders with "Back to dashboard" button.
5. `curl http://localhost:8000/ready` → 200 with `version`. Stop Supabase project, retry → 503.
6. `npm test` and `pytest` both green.

## 9. Risks

- **Seed script breaks on schema change.** Mitigation: the script uses the same `service.run_reconciliation()` and `generate_compliance_events` paths as the real app, so schema drift breaks both at once and is caught by existing tests.
- **render.yaml syntax drift.** Render evolves Blueprints; we're pinning `runtime: docker` and only minimal options to reduce blast radius.
- **CORS env var overlooked on first deploy.** README's "Deploy" section explicitly calls out copying the URL into `FRONTEND_ORIGIN` after first deploy.

## 10. File-level deliverables (for the plan)

**New files:**
- `backend/scripts/__init__.py`
- `backend/scripts/seed_demo.py`
- `backend/scripts/fixtures/demo_register.xlsx`
- `backend/scripts/fixtures/demo_supplier.xlsx`
- `backend/tests/scripts/__init__.py`
- `backend/tests/scripts/test_seed_demo.py`
- `backend/tests/test_health.py`
- `frontend/src/components/ErrorBoundary.tsx`
- `frontend/src/components/__tests__/ErrorBoundary.test.tsx`
- `frontend/src/pages/NotFound.tsx`
- `frontend/src/pages/__tests__/NotFound.test.tsx`
- `frontend/src/components/ui/Loading.tsx`
- `README.md` (repo root)
- `render.yaml` (repo root)
- `netlify.toml` (repo root)

**Edited files:**
- `backend/app/__init__.py` (add `__version__`)
- `backend/app/main.py` (CORS hygiene + version field on health endpoints)
- `backend/.env.example` (audit + add missing keys)
- `frontend/.env.example` (audit if any keys missing)
- `frontend/src/main.tsx` (mount root ErrorBoundary)
- `frontend/src/router.tsx` (NotFound replaces `*`-redirect; RouteBoundary wraps authed routes)
- `frontend/src/pages/ReconReport.tsx` (PageLoading swap)
- `frontend/src/pages/ClientDetail.tsx` (PageLoading swap)
- `frontend/src/components/clients/ClientsTable.tsx` (Spinner swap)
- `frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx` (Spinner swap)
- `frontend/src/components/compliance/OverdueClientsWidget.tsx` (Spinner swap)
- `frontend/src/components/compliance/RecentReconciliationsWidget.tsx` (Spinner swap)
