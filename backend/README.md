# HishabAI Backend

FastAPI service for the HishabAI platform. Phase A scope: health checks, JWT validation, and the audit-context RPC bridge. Subsequent phases add the reconciliation engine, document parsing, and notice drafting.

## Prerequisites

- Python 3.11+
- A Supabase project (URL, anon key, service-role key)

## Setup

```bash
# from the project root
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then fill in Supabase credentials
```

## Running the dev server

**ALWAYS run from the `backend/` directory, never from inside `backend/app/`.**

The app uses absolute package imports (`from app.config import settings`), which only resolve when Python's working directory is `backend/` so the `app` package is on `sys.path`.

Three valid options:

```bash
# 1. Recommended for development — uvicorn auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Run as a module — uses the __main__ block in app/main.py
python -m app.main

# 3. Same as #2 but explicit
python -m uvicorn app.main:app --reload
```

**Do not run `python app/main.py` or `python main.py` from inside `app/`.** Both fail with `ModuleNotFoundError: No module named 'app'` because Python treats `main.py` as a top-level script and cannot resolve sibling-module imports.

Once the server is up:

- API: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs> (development only)
- Health: <http://localhost:8000/health>
- Readiness (DB ping): <http://localhost:8000/ready>

## Tests

```bash
# from backend/
pytest              # unit tests only
pytest --run-integration   # includes Supabase integration tests
```

## Project layout

```
backend/
  app/
    __init__.py
    main.py          # FastAPI factory + middleware + health checks
    config.py        # Pydantic Settings (env vars)
    database.py      # Supabase client factories (admin + user-scoped)
    dependencies.py  # JWT validation, tenant resolution, set_request_user RPC
    core/
      exceptions.py  # HishabError hierarchy
      formatting.py  # BDT / TIN / BIN formatters
  tests/
    conftest.py      # pytest config + --run-integration flag
    test_*.py
    integration/
  Dockerfile
  requirements.txt
```
