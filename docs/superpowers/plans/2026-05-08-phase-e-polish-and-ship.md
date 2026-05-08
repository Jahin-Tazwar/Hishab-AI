# Phase E — Polish + Ship Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship six MVP-finishing deliverables — sample data seeder, frontend error boundaries + 404 + loading polish, backend health-endpoint hardening, and deploy/setup docs (render.yaml, netlify.toml, README) — so a stranger CA can hit a deployed URL and a fresh clone is up in 10 minutes.

**Architecture:** Backend changes are localized: a new `backend/scripts/` package for the seeder (calls existing `service.run_reconciliation` end-to-end via Storage upload + document rows), `__version__` plumbed into health endpoints, and a CORS env-var hatch. Frontend gains one shared `ErrorBoundary`, one shared `Loading` module (Spinner + PageLoading), one real `NotFound` page; existing pages are touched lightly to swap their ad-hoc loading text. Repo gets `render.yaml`, `netlify.toml`, and a runbook `README.md`. No live deploy — user handles that.

**Tech Stack:** Python 3.11 + FastAPI + supabase-py + pytest (backend); React 18 + TS + Vitest + @testing-library/react + Lucide (frontend); openpyxl for fixture XLSX generation.

---

## File Structure

**New files (backend):**
- `backend/scripts/__init__.py` — package marker
- `backend/scripts/seed_demo.py` — entrypoint
- `backend/scripts/fixtures/demo_register.xlsx` — committed (~5KB)
- `backend/scripts/fixtures/demo_supplier.xlsx` — committed (~5KB)
- `backend/scripts/fixtures/_generate.py` — one-shot helper that produced the two XLSX files (kept for `--regenerate-fixtures` flag)
- `backend/tests/scripts/__init__.py`
- `backend/tests/scripts/test_seed_demo.py` — integration test, marked `pytest.mark.integration`
- `backend/tests/test_health.py` — `/health` and `/ready` unit tests

**New files (frontend):**
- `frontend/src/components/ErrorBoundary.tsx` — class component + `<RouteBoundary>` thin wrapper
- `frontend/src/components/__tests__/ErrorBoundary.test.tsx`
- `frontend/src/components/ui/Loading.tsx` — exports `<Spinner />` and `<PageLoading />`
- `frontend/src/pages/NotFound.tsx`
- `frontend/src/pages/__tests__/NotFound.test.tsx`

**New files (root):**
- `README.md` — runbook
- `render.yaml` — Render Blueprint
- `netlify.toml` — Netlify build config

**Edited files (backend):**
- `backend/app/__init__.py` — add `__version__ = "0.1.0"`
- `backend/app/main.py` — version on health responses, CORS whitespace fix, `FRONTEND_ORIGIN` env support
- `backend/.env.example` — add `FRONTEND_ORIGIN`

**Edited files (frontend):**
- `frontend/src/main.tsx` — wrap `<RouterProvider>` in root `<ErrorBoundary>`
- `frontend/src/router.tsx` — replace `*` redirect with `<NotFound />`, wrap each authed route in `<RouteBoundary>`
- `frontend/src/pages/ReconReport.tsx` — `<PageLoading />` swap
- `frontend/src/pages/ClientDetail.tsx` — `<PageLoading />` swap
- `frontend/src/components/clients/ClientsTable.tsx` — `<Spinner />` swap
- `frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx` — `<Spinner />` swap
- `frontend/src/components/compliance/OverdueClientsWidget.tsx` — `<Spinner />` swap
- `frontend/src/components/compliance/RecentReconciliationsWidget.tsx` — `<Spinner />` swap

---

## Task 1: Backend version field + health endpoint tests

**Why first:** Tiny, isolated, validates we can run the backend test suite cleanly before adding the bigger seeder code.

**Files:**
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/main.py` (lines around 104-124)
- Create: `backend/tests/test_health.py`

- [ ] **Step 1.1: Add `__version__` to `backend/app/__init__.py`**

Replace the file contents (currently a one-line comment) with:

```python
"""HishabAI Backend package."""

__version__ = "0.1.0"
```

- [ ] **Step 1.2: Write failing test for `/health` returning version**

Create `backend/tests/test_health.py`:

```python
"""Smoke tests for /health and /ready endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import __version__
from app.main import app


def test_health_returns_200_with_version() -> None:
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["service"] == "hishabai-api"
    assert body["version"] == __version__


def test_ready_returns_200_when_supabase_reachable() -> None:
    """When the Supabase ping succeeds, /ready returns 200 with version."""
    fake_supabase = MagicMock()
    fake_supabase.table.return_value.select.return_value.limit.return_value.execute.return_value = (
        MagicMock(data=[])
    )

    with patch("app.main.get_supabase_admin", return_value=fake_supabase):
        client = TestClient(app)
        res = client.get("/ready")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"
        assert body["version"] == __version__


def test_ready_returns_503_when_supabase_unreachable() -> None:
    """When the Supabase ping raises, /ready returns 503."""
    fake_supabase = MagicMock()
    fake_supabase.table.side_effect = RuntimeError("connection refused")

    with patch("app.main.get_supabase_admin", return_value=fake_supabase):
        client = TestClient(app)
        res = client.get("/ready")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "not_ready"
```

- [ ] **Step 1.3: Run tests — confirm they fail**

```bash
cd backend && pytest tests/test_health.py -v
```

Expected: 3 failures — first two assert `body["version"] == __version__` but the endpoints don't return `version` yet; the third asserts `503` but the endpoint currently uses `JSONResponse(status_code=503, ...)` so this one might already pass. The two version asserts must fail.

- [ ] **Step 1.4: Add `version` to both health responses in `backend/app/main.py`**

In `health_check()` (~line 105-107), change:

```python
    @app.get("/health", tags=["system"])
    async def health_check():
        """Basic health check — returns 200 if the server is running."""
        return {"status": "healthy", "service": "hishabai-api"}
```

to:

```python
    @app.get("/health", tags=["system"])
    async def health_check():
        """Basic health check — returns 200 if the server is running."""
        from app import __version__
        return {"status": "healthy", "service": "hishabai-api", "version": __version__}
```

In `readiness_check()` (~line 109-124), change the success branch:

```python
            return {"status": "ready", "database": "connected"}
```

to:

```python
            from app import __version__
            return {"status": "ready", "database": "connected", "version": __version__}
```

- [ ] **Step 1.5: Run tests — confirm they pass**

```bash
cd backend && pytest tests/test_health.py -v
```

Expected: 3 passes.

- [ ] **Step 1.6: Run the full backend suite to confirm nothing regressed**

```bash
cd backend && pytest -q
```

Expected: all green (existing 59 + 3 new = 62).

- [ ] **Step 1.7: Commit**

```bash
git add backend/app/__init__.py backend/app/main.py backend/tests/test_health.py
git commit -m "feat(health): /health and /ready return version field + tests"
```

---

## Task 2: CORS hygiene and FRONTEND_ORIGIN env support

**Files:**
- Modify: `backend/app/main.py` (lines 53-63)
- Modify: `backend/.env.example`

- [ ] **Step 2.1: Update CORS configuration in `backend/app/main.py`**

Replace the `app.add_middleware(CORSMiddleware, ...)` block (lines 53-63) with:

```python
    # Build allow-origins from a static dev list plus an optional production
    # origin set via FRONTEND_ORIGIN. Setting FRONTEND_ORIGIN on Render after
    # the first frontend deploy avoids a code change.
    import os
    cors_origins = [
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # Alt dev port
    ]
    prod_origin = os.environ.get("FRONTEND_ORIGIN", "").strip()
    if prod_origin:
        cors_origins.append(prod_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

(The trailing-whitespace artifact at the end of the old list goes away in the rewrite.)

- [ ] **Step 2.2: Add FRONTEND_ORIGIN to `backend/.env.example`**

Append after the `STORAGE_BUCKET=documents` line:

```
# ── Production deploy ─────────────────────────────────────────────────────
# Comma-separated production origins (frontend URL after deploy).
# Empty in dev — only used when running on Render.
FRONTEND_ORIGIN=
```

- [ ] **Step 2.3: Run backend suite to confirm no regression**

```bash
cd backend && pytest -q
```

Expected: all green (62 tests).

- [ ] **Step 2.4: Commit**

```bash
git add backend/app/main.py backend/.env.example
git commit -m "feat(cors): support FRONTEND_ORIGIN env var for production frontend"
```

---

## Task 3: Generate demo XLSX fixtures

**Why standalone:** The fixture files are inputs to the seeder. They must exist before the seeder code references them. We commit them to the repo for determinism.

**Files:**
- Create: `backend/scripts/__init__.py` (empty)
- Create: `backend/scripts/fixtures/_generate.py`
- Create: `backend/scripts/fixtures/demo_register.xlsx` (built from the script)
- Create: `backend/scripts/fixtures/demo_supplier.xlsx` (built from the script)

- [ ] **Step 3.1: Create `backend/scripts/__init__.py`**

```bash
touch backend/scripts/__init__.py
```

- [ ] **Step 3.2: Write `backend/scripts/fixtures/_generate.py`**

This builds two XLSX files with 30 rows of purchase data, of which 8 will produce deliberate mismatches when matched against the supplier export:

```python
"""
Generates the two demo fixture XLSX files used by seed_demo.py.

Run once (or on schema change) via:
    python -m scripts.seed_demo --regenerate-fixtures

The generated files are committed to git — this script exists so we can
re-derive them from a single source of truth.

The 30 rows include 8 deliberate mismatches:
  - Rows 23-24: amount mismatch (supplier has higher VAT)
  - Rows 25-26: missing in supplier export entirely
  - Rows 27-28: register missing — supplier export has these but register doesn't
  - Rows 29-30: fuzzy-name match (slight name variation)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

# Header rows must match the parser exactly. See parser.py.
PR_HEADERS = [
    "Invoice No",
    "Supplier BIN",
    "Supplier Name",
    "Invoice Date",
    "Taxable Amount BDT",
    "VAT Amount BDT",
]
SF_HEADERS = [
    "Invoice No",
    "Buyer BIN",
    "Invoice Date",
    "Taxable Amount BDT",
    "VAT Amount BDT",
]

PERIOD_START = date(2026, 4, 1)
SUPPLIERS = [
    ("123456789", "Bashundhara Industries Ltd"),
    ("234567890", "Square Textiles"),
    ("345678901", "Beximco Pharmaceuticals"),
    ("456789012", "Apex Footwear"),
    ("567890123", "Pran-RFL Group"),
]
BUYER_BIN = "999888777"


def _build_register_rows() -> list[list[object]]:
    rows: list[list[object]] = [PR_HEADERS]
    for i in range(1, 31):
        sup_bin, sup_name = SUPPLIERS[(i - 1) % len(SUPPLIERS)]
        invoice_date = PERIOD_START + timedelta(days=i)
        taxable = Decimal("10000") + Decimal(i) * Decimal("250")
        vat = (taxable * Decimal("0.15")).quantize(Decimal("0.01"))
        # Row-29/30 fuzzy name: tweak the supplier name slightly so the supplier
        # export will have the canonical version. Match still happens via BIN
        # + amount but with status=fuzzy.
        if i in (29, 30):
            sup_name = sup_name.replace("Ltd", "Limited").replace("Group", "Grp.")
        rows.append([
            f"INV-{i:04d}",
            sup_bin,
            sup_name,
            invoice_date.isoformat(),
            float(taxable),
            float(vat),
        ])
    return rows


def _build_supplier_rows() -> list[list[object]]:
    rows: list[list[object]] = [SF_HEADERS]
    for i in range(1, 31):
        # Skip 25, 26 — these stay only in the register => no_match
        if i in (25, 26):
            continue
        sup_bin, _ = SUPPLIERS[(i - 1) % len(SUPPLIERS)]
        invoice_date = PERIOD_START + timedelta(days=i)
        taxable = Decimal("10000") + Decimal(i) * Decimal("250")
        vat = (taxable * Decimal("0.15")).quantize(Decimal("0.01"))
        # Rows 23, 24: bump VAT 5% above register => partial/amount-mismatch
        if i in (23, 24):
            vat = (vat * Decimal("1.05")).quantize(Decimal("0.01"))
        rows.append([
            f"INV-{i:04d}",
            BUYER_BIN,
            invoice_date.isoformat(),
            float(taxable),
            float(vat),
        ])
    # Rows 27, 28: present only in supplier (register missed them).
    # The matcher's input is register-driven, so these don't appear as
    # separate match rows in the demo recon — but they make total counts
    # asymmetric, which is realistic.
    for i in (27, 28):
        sup_bin, _ = SUPPLIERS[(i - 1) % len(SUPPLIERS)]
        invoice_date = PERIOD_START + timedelta(days=i)
        taxable = Decimal("10000") + Decimal(i) * Decimal("250")
        vat = (taxable * Decimal("0.15")).quantize(Decimal("0.01"))
        rows.append([
            f"INV-{i:04d}",
            BUYER_BIN,
            invoice_date.isoformat(),
            float(taxable),
            float(vat),
        ])
    return rows


def _write_xlsx(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> None:
    here = Path(__file__).resolve().parent
    _write_xlsx(here / "demo_register.xlsx", _build_register_rows())
    _write_xlsx(here / "demo_supplier.xlsx", _build_supplier_rows())
    print(f"Wrote {here / 'demo_register.xlsx'}")
    print(f"Wrote {here / 'demo_supplier.xlsx'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.3: Run the generator to produce the XLSX files**

```bash
cd backend && python -m scripts.fixtures._generate
```

Expected output:
```
Wrote /path/to/backend/scripts/fixtures/demo_register.xlsx
Wrote /path/to/backend/scripts/fixtures/demo_supplier.xlsx
```

Verify both files exist:

```bash
ls -la backend/scripts/fixtures/*.xlsx
```

- [ ] **Step 3.4: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/fixtures/_generate.py backend/scripts/fixtures/demo_register.xlsx backend/scripts/fixtures/demo_supplier.xlsx
git commit -m "feat(seed): demo fixture XLSX files (30 rows, 8 deliberate mismatches)"
```

---

## Task 4: seed_demo.py — auth user + tenant + clients

**Files:**
- Create: `backend/scripts/seed_demo.py`

This task lays down the script skeleton + the first three idempotent seed steps (auth, tenant, user_profile, 3 clients). Compliance events and reconciliation come in Tasks 5-6.

- [ ] **Step 4.1: Create `backend/scripts/seed_demo.py`**

```python
"""
Seed demo data: one tenant, three clients with mixed entity types,
compliance events for each, and one reconciliation with realistic mismatches.

Usage:
    python -m scripts.seed_demo --email demo@example.test --password DemoPass123!
    python -m scripts.seed_demo --email demo@example.test --reset
    python -m scripts.seed_demo --regenerate-fixtures   # regen XLSX fixtures and exit

Idempotent: re-running with the same email is safe — existing tenant + clients
are reused.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import structlog

from app.database import get_supabase_admin

log = structlog.get_logger()

DEMO_TENANT_NAME = "Demo CA Firm"
DEMO_CLIENTS: list[dict] = [
    {
        "name": "Acme Textiles Ltd",
        "name_bn": None,
        "entity_type": "private_limited",
        "bin": "123456789",
        "tin": "123456789012",
        "is_vat_registered": True,
        "fiscal_year_end_month": 6,
        "fiscal_year_end_day": 30,
    },
    {
        "name": "Hossain & Co Partnership",
        "name_bn": None,
        "entity_type": "partnership",
        "bin": None,
        "tin": "987654321098",
        "is_vat_registered": False,
        "fiscal_year_end_month": 6,
        "fiscal_year_end_day": 30,
    },
    {
        "name": "Rahman Trading",
        "name_bn": None,
        "entity_type": "individual",
        "bin": "555666777",
        "tin": "111222333444",
        "is_vat_registered": True,
        "fiscal_year_end_month": 6,
        "fiscal_year_end_day": 30,
    },
]


def _ensure_auth_user(email: str, password: str | None) -> UUID:
    """Create or fetch the demo Supabase Auth user. Returns the user UUID."""
    supabase = get_supabase_admin()
    # admin.list_users returns an iterable of User objects. The supabase-py
    # client doesn't expose get_user_by_email, so we list and filter.
    page = supabase.auth.admin.list_users()
    for user in page:
        if getattr(user, "email", None) == email:
            log.info("seed.auth_user_exists", email=email, user_id=user.id)
            return UUID(user.id)
    if not password:
        raise SystemExit(
            f"No auth user with email {email!r} exists yet. "
            "Pass --password to create one."
        )
    created = supabase.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    log.info("seed.auth_user_created", email=email, user_id=created.user.id)
    return UUID(created.user.id)


def _ensure_tenant() -> UUID:
    """Create or fetch the demo tenant by name. Returns the tenant UUID."""
    supabase = get_supabase_admin()
    existing = (
        supabase.table("tenants")
        .select("id")
        .eq("name", DEMO_TENANT_NAME)
        .limit(1)
        .execute()
    )
    if existing.data:
        tid = UUID(existing.data[0]["id"])
        log.info("seed.tenant_exists", tenant_id=str(tid))
        return tid
    inserted = (
        supabase.table("tenants")
        .insert({"name": DEMO_TENANT_NAME})
        .execute()
    )
    tid = UUID(inserted.data[0]["id"])
    log.info("seed.tenant_created", tenant_id=str(tid))
    return tid


def _ensure_user_profile(user_id: UUID, tenant_id: UUID) -> None:
    """Link the auth user to the demo tenant. No-op if already linked."""
    supabase = get_supabase_admin()
    existing = (
        supabase.table("user_profile")
        .select("user_id")
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    if existing.data:
        log.info("seed.user_profile_exists", user_id=str(user_id))
        return
    supabase.table("user_profile").insert({
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "role": "owner",
    }).execute()
    log.info("seed.user_profile_created", user_id=str(user_id))


def _ensure_clients(tenant_id: UUID, created_by: UUID) -> list[UUID]:
    """Create or fetch the three demo clients. Returns their UUIDs in order."""
    supabase = get_supabase_admin()
    ids: list[UUID] = []
    for spec in DEMO_CLIENTS:
        existing = (
            supabase.table("clients")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .eq("name", spec["name"])
            .limit(1)
            .execute()
        )
        if existing.data:
            cid = UUID(existing.data[0]["id"])
            log.info("seed.client_exists", name=spec["name"], client_id=str(cid))
            ids.append(cid)
            continue
        payload = {**spec, "tenant_id": str(tenant_id), "created_by": str(created_by)}
        inserted = supabase.table("clients").insert(payload).execute()
        cid = UUID(inserted.data[0]["id"])
        log.info("seed.client_created", name=spec["name"], client_id=str(cid))
        ids.append(cid)
    return ids


async def seed(email: str, password: str | None) -> None:
    user_id = _ensure_auth_user(email, password)
    tenant_id = _ensure_tenant()
    _ensure_user_profile(user_id, tenant_id)
    client_ids = _ensure_clients(tenant_id, user_id)
    log.info(
        "seed.done",
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        client_ids=[str(c) for c in client_ids],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed HishabAI demo data.")
    parser.add_argument("--email", help="Demo user email")
    parser.add_argument("--password", help="Demo user password (only used on first run)")
    parser.add_argument("--reset", action="store_true", help="Delete demo tenant first")
    parser.add_argument(
        "--regenerate-fixtures",
        action="store_true",
        help="Regenerate the XLSX fixture files and exit",
    )
    args = parser.parse_args()

    if args.regenerate_fixtures:
        from scripts.fixtures._generate import main as gen_main
        gen_main()
        return 0

    if not args.email:
        parser.error("--email is required (unless --regenerate-fixtures)")

    asyncio.run(seed(args.email, args.password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4.2: Run the seeder against the dev Supabase project**

```bash
cd backend && python -m scripts.seed_demo --email demo@hishabai.test --password DemoPass123!
```

Expected: structured log output with `seed.auth_user_created`, `seed.tenant_created`, `seed.user_profile_created`, three `seed.client_created` lines, and `seed.done` at the end.

If a previous run left a `Demo CA Firm` tenant lying around, log lines say `_exists` instead of `_created` — that's the idempotency story working.

- [ ] **Step 4.3: Re-run the seeder; confirm idempotent**

```bash
cd backend && python -m scripts.seed_demo --email demo@hishabai.test
```

Expected: every step logs `_exists`, exit code 0, no errors.

- [ ] **Step 4.4: Commit**

```bash
git add backend/scripts/seed_demo.py
git commit -m "feat(seed): demo seeder — auth user, tenant, user_profile, 3 clients"
```

---

## Task 5: seed_demo.py — compliance events for each client

**Files:**
- Modify: `backend/scripts/seed_demo.py`

- [ ] **Step 5.1: Add a `_generate_events_for_client` helper**

Insert after `_ensure_clients` and before `async def seed`:

```python
def _generate_events_for_client(client_id: UUID, tenant_id: UUID) -> int:
    """
    Calls the generate_compliance_events RPC for one client over the
    next 90 days. Returns the number of events generated (or 0 if the
    RPC is idempotent and they already exist).
    """
    from datetime import date, timedelta
    supabase = get_supabase_admin()
    today = date.today()
    end = today + timedelta(days=90)
    res = supabase.rpc(
        "generate_compliance_events",
        {
            "p_client_id": str(client_id),
            "p_tenant_id": str(tenant_id),
            "p_window_start": today.isoformat(),
            "p_window_end": end.isoformat(),
        },
    ).execute()
    n = res.data if isinstance(res.data, int) else (res.data or 0)
    log.info(
        "seed.events_generated",
        client_id=str(client_id),
        count=n,
    )
    return int(n)
```

- [ ] **Step 5.2: Wire it into `seed()`**

Add after the `client_ids = _ensure_clients(...)` line:

```python
    for cid in client_ids:
        _generate_events_for_client(cid, tenant_id)
```

- [ ] **Step 5.3: Run the seeder; confirm events generated**

```bash
cd backend && python -m scripts.seed_demo --email demo@hishabai.test
```

Expected: three `seed.events_generated` lines (one per client) with non-zero counts on first run, then zero counts on re-run (the RPC is idempotent on conflict).

- [ ] **Step 5.4: Verify in Supabase**

Run a SQL check via the Supabase dashboard or psql:

```sql
SELECT client_id, COUNT(*)
FROM compliance_events
WHERE tenant_id = (SELECT id FROM tenants WHERE name = 'Demo CA Firm')
GROUP BY client_id;
```

Expected: 3 rows, each with a positive count.

- [ ] **Step 5.5: Commit**

```bash
git add backend/scripts/seed_demo.py
git commit -m "feat(seed): generate 90 days of compliance events per demo client"
```

---

## Task 6: seed_demo.py — reconciliation seeding

**Why this approach:** The seeded reconciliation must look identical to a real one (so demo users see the full report screen with download, line items, etc.). We upload the fixture XLSX files to the same `recon-files` Supabase bucket the production flow uses, create `documents` rows pointing at them, then call the existing `service.run_reconciliation()`. Same code path, same data shape.

**Files:**
- Modify: `backend/scripts/seed_demo.py`

- [ ] **Step 6.1: Add reconciliation helper functions**

Insert before `async def seed`:

```python
def _upload_fixture(
    *, tenant_id: UUID, client_id: UUID, user_id: UUID, file_kind: str, fixture_name: str
) -> UUID:
    """
    Upload one fixture XLSX to the recon-files bucket and create a documents row.
    Returns the document UUID.
    file_kind: 'purchase_register' or 'supplier_export'
    """
    from pathlib import Path

    fixture_path = Path(__file__).resolve().parent / "fixtures" / fixture_name
    if not fixture_path.exists():
        raise SystemExit(
            f"Fixture not found: {fixture_path}. "
            "Run with --regenerate-fixtures first."
        )

    supabase = get_supabase_admin()

    # Reuse an existing documents row if we've already seeded one for this client.
    existing = (
        supabase.table("documents")
        .select("id")
        .eq("tenant_id", str(tenant_id))
        .eq("client_id", str(client_id))
        .eq("file_kind", file_kind)
        .like("storage_path", "%/demo-seed/%")
        .limit(1)
        .execute()
    )
    if existing.data:
        return UUID(existing.data[0]["id"])

    storage_path = f"{tenant_id}/{client_id}/demo-seed/{fixture_name}"
    with open(fixture_path, "rb") as f:
        bytes_ = f.read()
    # supabase-py's storage upload is sync.
    supabase.storage.from_("recon-files").upload(
        path=storage_path,
        file=bytes_,
        file_options={"upsert": "true", "content-type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    inserted = supabase.table("documents").insert({
        "tenant_id": str(tenant_id),
        "client_id": str(client_id),
        "uploaded_by": str(user_id),
        "file_name": fixture_name,
        "file_kind": file_kind,
        "storage_path": storage_path,
        "size_bytes": len(bytes_),
        "mime_type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }).execute()
    doc_id = UUID(inserted.data[0]["id"])
    log.info(
        "seed.fixture_uploaded",
        client_id=str(client_id),
        kind=file_kind,
        doc_id=str(doc_id),
    )
    return doc_id


async def _seed_reconciliation(
    *, tenant_id: UUID, client_id: UUID, user_id: UUID
) -> UUID | None:
    """
    Run a reconciliation for the previous calendar month. Skips if a recon
    already exists for this (client, period). Returns the recon UUID or None.
    """
    from datetime import date
    from app.reconciliation.schemas import ReconciliationCreateRequest
    from app.reconciliation.service import run_reconciliation

    today = date.today()
    if today.month == 1:
        period_start = date(today.year - 1, 12, 1)
        period_end = date(today.year - 1, 12, 31)
    else:
        period_start = date(today.year, today.month - 1, 1)
        # Last day of previous month = day before today.replace(day=1)
        from calendar import monthrange
        last_day = monthrange(today.year, today.month - 1)[1]
        period_end = date(today.year, today.month - 1, last_day)

    supabase = get_supabase_admin()
    existing = (
        supabase.table("reconciliations")
        .select("id")
        .eq("tenant_id", str(tenant_id))
        .eq("client_id", str(client_id))
        .eq("period_start", period_start.isoformat())
        .eq("period_end", period_end.isoformat())
        .limit(1)
        .execute()
    )
    if existing.data:
        rid = UUID(existing.data[0]["id"])
        log.info("seed.recon_exists", reconciliation_id=str(rid))
        return rid

    pr_doc_id = _upload_fixture(
        tenant_id=tenant_id, client_id=client_id, user_id=user_id,
        file_kind="purchase_register", fixture_name="demo_register.xlsx",
    )
    sf_doc_id = _upload_fixture(
        tenant_id=tenant_id, client_id=client_id, user_id=user_id,
        file_kind="supplier_export", fixture_name="demo_supplier.xlsx",
    )

    req = ReconciliationCreateRequest(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
        purchase_register_doc_id=pr_doc_id,
        supplier_data_doc_id=sf_doc_id,
    )
    recon_id = await run_reconciliation(req, tenant_id=tenant_id, user_id=user_id)
    log.info("seed.recon_created", reconciliation_id=str(recon_id))
    return recon_id
```

- [ ] **Step 6.2: Wire it into `seed()`**

After the `for cid in client_ids: _generate_events_for_client(...)` loop, add:

```python
    # Only seed a recon for the first client (Acme Textiles)
    await _seed_reconciliation(
        tenant_id=tenant_id,
        client_id=client_ids[0],
        user_id=user_id,
    )
```

- [ ] **Step 6.3: Run the seeder; confirm a recon is created**

```bash
cd backend && python -m scripts.seed_demo --email demo@hishabai.test
```

Expected: log lines `seed.fixture_uploaded` (×2), `seed.recon_created` with a UUID. Re-running logs `seed.recon_exists`.

- [ ] **Step 6.4: Verify in Supabase**

```sql
SELECT id, total_invoices, matched_exact, matched_fuzzy, partial_match, no_match,
       at_risk_itc_bdt
FROM reconciliations
WHERE tenant_id = (SELECT id FROM tenants WHERE name = 'Demo CA Firm');
```

Expected: 1 row, `total_invoices=30`, non-zero counts in at least exact + fuzzy + partial + no_match buckets, non-zero `at_risk_itc_bdt`.

- [ ] **Step 6.5: Commit**

```bash
git add backend/scripts/seed_demo.py
git commit -m "feat(seed): seed one demo reconciliation with realistic mismatches"
```

---

## Task 7: seed_demo.py — `--reset` flag + integration test

**Files:**
- Modify: `backend/scripts/seed_demo.py`
- Create: `backend/tests/scripts/__init__.py`
- Create: `backend/tests/scripts/test_seed_demo.py`

- [ ] **Step 7.1: Add `_reset_demo` helper to `seed_demo.py`**

Insert before `async def seed`:

```python
def _reset_demo() -> None:
    """
    Delete the demo tenant and everything cascading from it (clients, events,
    reconciliations, documents, line items, audit_log entries via the trigger).
    Auth users are left alone — pass a different --email to seed against a
    different user, or delete via the Supabase dashboard.
    """
    supabase = get_supabase_admin()
    existing = (
        supabase.table("tenants")
        .select("id")
        .eq("name", DEMO_TENANT_NAME)
        .limit(1)
        .execute()
    )
    if not existing.data:
        log.info("seed.reset_no_tenant")
        return
    tenant_id = existing.data[0]["id"]
    # Cascade order — RLS-aware order to keep FK constraints happy.
    # Storage objects: best-effort cleanup of recon-files for this tenant.
    try:
        listing = supabase.storage.from_("recon-files").list(tenant_id)
        if listing:
            paths = [f"{tenant_id}/{item['name']}" for item in listing]
            if paths:
                supabase.storage.from_("recon-files").remove(paths)
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        log.warning("seed.reset_storage_cleanup_failed", error=str(exc))

    supabase.table("reconciliation_line_items").delete().eq("tenant_id", tenant_id).execute()
    supabase.table("reconciliations").delete().eq("tenant_id", tenant_id).execute()
    supabase.table("documents").delete().eq("tenant_id", tenant_id).execute()
    supabase.table("compliance_events").delete().eq("tenant_id", tenant_id).execute()
    supabase.table("clients").delete().eq("tenant_id", tenant_id).execute()
    supabase.table("user_profile").delete().eq("tenant_id", tenant_id).execute()
    supabase.table("tenants").delete().eq("id", tenant_id).execute()
    log.info("seed.reset_done", tenant_id=tenant_id)
```

- [ ] **Step 7.2: Wire `--reset` into `main()`**

In `main()`, after the `--regenerate-fixtures` block and before `if not args.email`, add:

```python
    if args.reset:
        _reset_demo()
        # If --email was also passed, fall through to seed; otherwise exit.
        if not args.email:
            return 0
```

- [ ] **Step 7.3: Run `--reset --email ... --password ...` end-to-end**

```bash
cd backend && python -m scripts.seed_demo --reset --email demo@hishabai.test --password DemoPass123!
```

Expected: `seed.reset_done`, then full creation flow (every step logs `_created`, not `_exists`), then `seed.done`.

- [ ] **Step 7.4: Create `backend/tests/scripts/__init__.py`**

```bash
touch backend/tests/scripts/__init__.py
```

- [ ] **Step 7.5: Write the integration test**

Create `backend/tests/scripts/test_seed_demo.py`:

```python
"""
Integration test for scripts.seed_demo.

Skipped unless SEED_TEST_SUPABASE_URL is set (it points at a disposable
Supabase project — never run this against prod).
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration

SKIP_REASON = "SEED_TEST_SUPABASE_URL not set — skipping live seeder integration test"


@pytest.fixture(autouse=True)
def _require_test_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.environ.get("SEED_TEST_SUPABASE_URL"):
        pytest.skip(SKIP_REASON)
    # Re-point app.config.settings to the disposable project.
    monkeypatch.setenv("SUPABASE_URL", os.environ["SEED_TEST_SUPABASE_URL"])
    monkeypatch.setenv(
        "SUPABASE_SERVICE_ROLE_KEY", os.environ["SEED_TEST_SUPABASE_SERVICE_ROLE_KEY"]
    )


def test_seed_demo_runs_end_to_end_and_is_idempotent() -> None:
    from scripts import seed_demo
    from app.database import get_supabase_admin

    email = f"seed-test-{uuid.uuid4()}@hishabai.test"
    password = "SeedTestPass123!"

    # First run — full creation
    seed_demo._reset_demo()
    import asyncio
    asyncio.run(seed_demo.seed(email, password))

    supabase = get_supabase_admin()
    tenant_row = (
        supabase.table("tenants").select("id").eq("name", seed_demo.DEMO_TENANT_NAME)
        .limit(1).execute().data
    )
    assert tenant_row, "tenant not created"
    tenant_id = tenant_row[0]["id"]

    clients = (
        supabase.table("clients").select("id,name").eq("tenant_id", tenant_id)
        .execute().data
    )
    assert len(clients) == 3
    assert {c["name"] for c in clients} == {
        "Acme Textiles Ltd", "Hossain & Co Partnership", "Rahman Trading"
    }

    recons = (
        supabase.table("reconciliations")
        .select("id,total_invoices,at_risk_itc_bdt")
        .eq("tenant_id", tenant_id).execute().data
    )
    assert len(recons) == 1
    assert recons[0]["total_invoices"] == 30
    assert Decimal(str(recons[0]["at_risk_itc_bdt"])) > 0

    # Second run — idempotent
    asyncio.run(seed_demo.seed(email, password))
    recons2 = (
        supabase.table("reconciliations").select("id").eq("tenant_id", tenant_id)
        .execute().data
    )
    assert len(recons2) == 1, "second run should not create a duplicate recon"

    # Cleanup
    seed_demo._reset_demo()
```

- [ ] **Step 7.6: Confirm the test is skipped in dev (no SEED_TEST_* env vars)**

```bash
cd backend && pytest tests/scripts/test_seed_demo.py -v
```

Expected: 1 skipped (reason: SEED_TEST_SUPABASE_URL not set).

- [ ] **Step 7.7: Confirm the full test suite still passes**

```bash
cd backend && pytest -q
```

Expected: all green, with 1 additional skipped test.

- [ ] **Step 7.8: Commit**

```bash
git add backend/scripts/seed_demo.py backend/tests/scripts/__init__.py backend/tests/scripts/test_seed_demo.py
git commit -m "feat(seed): --reset flag + integration test (gated on SEED_TEST_SUPABASE_URL)"
```

---

## Task 8: Loading.tsx — shared Spinner + PageLoading

**Files:**
- Create: `frontend/src/components/ui/Loading.tsx`

- [ ] **Step 8.1: Create `frontend/src/components/ui/Loading.tsx`**

```tsx
/**
 * Shared loading indicators. Two pieces:
 *
 *  <Spinner />        — small inline spinner. Use in buttons, table rows,
 *                       widget card bodies.
 *  <PageLoading />    — full-page skeleton with centered spinner + label.
 *                       Use for top-level page loads.
 */
import { Loader2 } from "lucide-react"

interface SpinnerProps {
  className?: string
}

export function Spinner({ className }: SpinnerProps) {
  return (
    <Loader2
      className={`h-4 w-4 animate-spin text-slate-500 ${className ?? ""}`}
      aria-label="Loading"
    />
  )
}

interface PageLoadingProps {
  label?: string
}

export function PageLoading({ label = "Loading…" }: PageLoadingProps) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2">
      <Loader2 className="h-6 w-6 animate-spin text-slate-500" aria-label="Loading" />
      <p className="text-sm text-slate-500">{label}</p>
    </div>
  )
}
```

- [ ] **Step 8.2: Type-check the new module**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean exit (no type errors).

- [ ] **Step 8.3: Commit**

```bash
git add frontend/src/components/ui/Loading.tsx
git commit -m "feat(ui): shared Spinner and PageLoading components"
```

---

## Task 9: ErrorBoundary component + tests

**Files:**
- Create: `frontend/src/components/ErrorBoundary.tsx`
- Create: `frontend/src/components/__tests__/ErrorBoundary.test.tsx`

- [ ] **Step 9.1: Write failing tests**

Create `frontend/src/components/__tests__/ErrorBoundary.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { ErrorBoundary } from "../ErrorBoundary"

function Throws() {
  throw new Error("kaboom")
}

function Maybe({ throws }: { throws: boolean }) {
  if (throws) throw new Error("kaboom")
  return <p>safe</p>
}

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <p>hello</p>
        </ErrorBoundary>
      </MemoryRouter>,
    )
    expect(screen.getByText("hello")).toBeInTheDocument()
  })

  it("renders fallback when child throws", () => {
    // Suppress React's expected console.error for the throw
    const orig = console.error
    console.error = () => {}
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Throws />
        </ErrorBoundary>
      </MemoryRouter>,
    )
    console.error = orig
    expect(screen.getByText("Something went wrong")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
  })

  it("recovers when 'Try again' is clicked and child no longer throws", () => {
    const orig = console.error
    console.error = () => {}
    let throws = true
    function Wrapper() {
      return (
        <ErrorBoundary>
          <Maybe throws={throws} />
        </ErrorBoundary>
      )
    }
    const { rerender } = render(
      <MemoryRouter>
        <Wrapper />
      </MemoryRouter>,
    )
    expect(screen.getByText("Something went wrong")).toBeInTheDocument()

    throws = false
    fireEvent.click(screen.getByRole("button", { name: /try again/i }))
    rerender(
      <MemoryRouter>
        <Wrapper />
      </MemoryRouter>,
    )
    console.error = orig
    expect(screen.getByText("safe")).toBeInTheDocument()
  })
})
```

- [ ] **Step 9.2: Run tests — confirm they fail**

```bash
cd frontend && npm test -- ErrorBoundary
```

Expected: failures (module not found).

- [ ] **Step 9.3: Implement `frontend/src/components/ErrorBoundary.tsx`**

```tsx
import { Component, type ErrorInfo, type ReactNode } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * Catches render-time errors in its subtree and renders a fallback card.
 * Async errors (in fetch / mutation callbacks) are NOT caught here — those are
 * handled by per-hook `error` states from TanStack Query.
 *
 * Mount one at the root (in main.tsx) and one per authenticated route
 * (via <RouteBoundary> in router.tsx) so a crash in one page slot doesn't
 * blank out the AppShell.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("ErrorBoundary caught:", error, info.componentStack)
    }
  }

  reset = (): void => {
    this.setState({ hasError: false, error: null })
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children
    return (
      <div className="flex min-h-[40vh] items-center justify-center p-6">
        <Card className="max-w-md w-full">
          <CardContent className="space-y-3 pt-6">
            <h2 className="text-lg font-semibold text-slate-900">
              Something went wrong
            </h2>
            <p className="text-sm text-slate-600">
              The page hit an unexpected error. You can try again, or head back
              to the dashboard.
            </p>
            <div className="flex gap-2 pt-1">
              <Button onClick={this.reset}>Try again</Button>
              <Link
                to="/dashboard"
                className="inline-flex items-center justify-center rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
              >
                Go to dashboard
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }
}

/**
 * Convenience wrapper for use inside <Route element={...}> entries — keeps
 * router.tsx readable.
 */
export function RouteBoundary({ children }: { children: ReactNode }) {
  return <ErrorBoundary>{children}</ErrorBoundary>
}
```

- [ ] **Step 9.4: Run tests — confirm they pass**

```bash
cd frontend && npm test -- ErrorBoundary
```

Expected: 3 passes.

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/components/ErrorBoundary.tsx frontend/src/components/__tests__/ErrorBoundary.test.tsx
git commit -m "feat(ui): ErrorBoundary catches render errors with reset + fallback UI"
```

---

## Task 10: Mount ErrorBoundary at root and per-route

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 10.1: Wrap `<RouterProvider>` in `<ErrorBoundary>` in `main.tsx`**

Replace the body of `ReactDOM.createRoot(...).render(...)` with:

```tsx
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppRoot>
          <RouterProvider router={router} />
        </AppRoot>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
```

And add the import at the top:

```tsx
import { ErrorBoundary } from "@/components/ErrorBoundary"
```

- [ ] **Step 10.2: Wrap each authed route in `<RouteBoundary>` in `router.tsx`**

For each authed entry (`/dashboard`, `/clients`, `/clients/:id`, `/clients/:id/recon/new`, `/clients/:id/recon/:reconId`), wrap the inner `<AppShell><Page /></AppShell>` in `<RouteBoundary>`:

```tsx
  {
    path: "/dashboard",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell>
            <RouteBoundary><Dashboard /></RouteBoundary>
          </AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
```

Apply the same shape to all five authed routes. Add the import:

```tsx
import { RouteBoundary } from "@/components/ErrorBoundary"
```

- [ ] **Step 10.3: Run frontend tests to confirm no regression**

```bash
cd frontend && npm test
```

Expected: all green (existing 25 + 3 new = 28).

- [ ] **Step 10.4: Smoke-test in the running dev server**

Start `npm run dev`, log in, navigate to `/dashboard`. App renders normally. Optional: temporarily edit one widget to throw (e.g. add `throw new Error("test")` at the top of `UpcomingDeadlinesWidget`), confirm the page-level fallback shows and the rest of `<AppShell>` (nav, sidebar) still renders. Revert the throw.

- [ ] **Step 10.5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/router.tsx
git commit -m "feat(ui): mount ErrorBoundary at root + per authed route"
```

---

## Task 11: NotFound page + replace `*` route + tests

**Files:**
- Create: `frontend/src/pages/NotFound.tsx`
- Create: `frontend/src/pages/__tests__/NotFound.test.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 11.1: Write failing tests**

Create `frontend/src/pages/__tests__/NotFound.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it } from "vitest"

import { NotFound } from "../NotFound"
import { useAuthStore } from "@/store/auth"

describe("NotFound", () => {
  beforeEach(() => {
    useAuthStore.setState({ session: null, user: null, isLoading: false })
  })

  it("shows 'Back to dashboard' when authenticated", () => {
    useAuthStore.setState({
      // @ts-expect-error -- partial Session is fine for this test
      session: { access_token: "x", user: { id: "u" } },
      // @ts-expect-error -- partial User is fine for this test
      user: { id: "u" },
      isLoading: false,
    })
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    )
    expect(screen.getByText(/page not found/i)).toBeInTheDocument()
    const link = screen.getByRole("link", { name: /back to dashboard/i })
    expect(link).toHaveAttribute("href", "/dashboard")
  })

  it("shows 'Back to login' when unauthenticated", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    )
    const link = screen.getByRole("link", { name: /back to login/i })
    expect(link).toHaveAttribute("href", "/login")
  })
})
```

- [ ] **Step 11.2: Run tests — confirm they fail**

```bash
cd frontend && npm test -- NotFound
```

Expected: failures (module not found).

- [ ] **Step 11.3: Implement `frontend/src/pages/NotFound.tsx`**

```tsx
import { Link } from "react-router-dom"

import { useAuthStore } from "@/store/auth"

/**
 * Catch-all 404 page rendered for any unrecognized route. Picks its target
 * link based on auth state — authenticated users go to /dashboard, others
 * to /login. We don't try to render this inside <AppShell> for authed users
 * because the route entry in router.tsx is the catch-all and isn't wrapped
 * in <RequireAuth>; rendering bare keeps the page reachable when auth is
 * uncertain.
 */
export function NotFound() {
  const session = useAuthStore((s) => s.session)
  const isAuthed = Boolean(session)

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 text-center shadow-sm">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Error 404
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Page not found</h1>
        <p className="mt-2 text-sm text-slate-600">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-5">
          <Link
            to={isAuthed ? "/dashboard" : "/login"}
            className="inline-flex items-center justify-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            {isAuthed ? "Back to dashboard" : "Back to login"}
          </Link>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 11.4: Replace `*` route in `frontend/src/router.tsx`**

Change:

```tsx
  { path: "*", element: <Navigate to="/login" replace /> },
```

to:

```tsx
  { path: "*", element: <NotFound /> },
```

Add the import:

```tsx
import { NotFound } from "@/pages/NotFound"
```

`Navigate` may now be unused — leave it or remove the import per ESLint feedback.

- [ ] **Step 11.5: Run tests — confirm they pass**

```bash
cd frontend && npm test -- NotFound
```

Expected: 2 passes. Then run the full suite:

```bash
cd frontend && npm test
```

Expected: all green (30 tests).

- [ ] **Step 11.6: Smoke-test**

Start `npm run dev`, visit `http://localhost:5173/this-route-does-not-exist`. NotFound page renders. Click "Back to login" or "Back to dashboard" — navigates correctly.

- [ ] **Step 11.7: Commit**

```bash
git add frontend/src/pages/NotFound.tsx frontend/src/pages/__tests__/NotFound.test.tsx frontend/src/router.tsx
git commit -m "feat(ui): real 404 page replaces silent /login redirect"
```

---

## Task 12: Loading-state touch-ups across pages and widgets

**Files:**
- Modify: `frontend/src/pages/ReconReport.tsx` (line 62-64)
- Modify: `frontend/src/pages/ClientDetail.tsx` (the `if (isLoading)` block + the `{itemsLoading ? ...}` block)
- Modify: `frontend/src/components/clients/ClientsTable.tsx` (the `if (isLoading)` block)
- Modify: `frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx`
- Modify: `frontend/src/components/compliance/OverdueClientsWidget.tsx`
- Modify: `frontend/src/components/compliance/RecentReconciliationsWidget.tsx`

- [ ] **Step 12.1: ReconReport — swap top-level loading text for `<PageLoading />`**

In `frontend/src/pages/ReconReport.tsx`, replace:

```tsx
  if (reconLoading) {
    return <div className="p-8 text-slate-500">Loading reconciliation…</div>
  }
```

with:

```tsx
  if (reconLoading) {
    return <PageLoading label="Loading reconciliation…" />
  }
```

Also replace the inner line-items loading text:

```tsx
            {itemsLoading ? (
              <p className="text-slate-500 text-sm">Loading line items…</p>
            ) : (
```

with:

```tsx
            {itemsLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Spinner /> Loading line items…
              </div>
            ) : (
```

Add the imports:

```tsx
import { PageLoading, Spinner } from "@/components/ui/Loading"
```

- [ ] **Step 12.2: ClientDetail — swap top-level loading text**

In `frontend/src/pages/ClientDetail.tsx`, replace:

```tsx
  if (isLoading) {
    return <div className="text-slate-500 p-8">Loading client…</div>
  }
```

with:

```tsx
  if (isLoading) {
    return <PageLoading label="Loading client…" />
  }
```

Add:

```tsx
import { PageLoading } from "@/components/ui/Loading"
```

- [ ] **Step 12.3: ClientsTable — swap loading row for inline Spinner**

In `frontend/src/components/clients/ClientsTable.tsx`, replace:

```tsx
  if (isLoading) {
    return <div className="text-slate-500 py-8 text-center">Loading clients…</div>
  }
```

with:

```tsx
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500">
        <Spinner /> Loading clients…
      </div>
    )
  }
```

Add:

```tsx
import { Spinner } from "@/components/ui/Loading"
```

- [ ] **Step 12.4: UpcomingDeadlinesWidget — swap "Loading…" text**

In `frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx`, replace:

```tsx
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (data ?? []).length === 0 ? (
```

with:

```tsx
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : (data ?? []).length === 0 ? (
```

Add:

```tsx
import { Spinner } from "@/components/ui/Loading"
```

- [ ] **Step 12.5: OverdueClientsWidget — same swap**

Open `frontend/src/components/compliance/OverdueClientsWidget.tsx`. Find the `isLoading` branch (renders a `<p>` with "Loading…"). Replace with the same `<Spinner /> Loading…` block as Step 12.4. Add the `Spinner` import.

- [ ] **Step 12.6: RecentReconciliationsWidget — same swap**

Open `frontend/src/components/compliance/RecentReconciliationsWidget.tsx`. Find the `isLoading` branch. Replace with the same `<Spinner /> Loading…` block as Step 12.4. Add the `Spinner` import.

- [ ] **Step 12.7: Run tests + smoke-test**

```bash
cd frontend && npm test && npx tsc --noEmit
```

Expected: all green, no type errors.

Optional dev-server smoke: visit each page, observe consistent spinner styling on first load. Throttle the network in browser devtools to make loading states observable.

- [ ] **Step 12.8: Commit**

```bash
git add frontend/src/pages/ReconReport.tsx frontend/src/pages/ClientDetail.tsx frontend/src/components/clients/ClientsTable.tsx frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx frontend/src/components/compliance/OverdueClientsWidget.tsx frontend/src/components/compliance/RecentReconciliationsWidget.tsx
git commit -m "polish(ui): consistent loading states across pages and widgets"
```

---

## Task 13: README.md (project root runbook)

**Files:**
- Create: `README.md`

- [ ] **Step 13.1: Confirm migration filenames for the README**

```bash
ls migrations/*.sql
```

Make a mental note of the migration count for the deploy section.

- [ ] **Step 13.2: Write `README.md`**

```markdown
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

   Apply every file in `migrations/` in lexical order. Easiest path is to
   paste each file into the SQL Editor on the Supabase dashboard. For
   automation, point `psql` at your project's connection string:
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

Re-running with the same email is idempotent. Pass `--reset` to wipe
the demo tenant and reseed from clean. Pass `--regenerate-fixtures` to
re-derive the two demo XLSX files from source.

## Tests

```bash
# Backend
cd backend && pytest -q

# Frontend
cd frontend && npm test
```

The seeder integration test (`tests/scripts/test_seed_demo.py`) is
skipped unless `SEED_TEST_SUPABASE_URL` and
`SEED_TEST_SUPABASE_SERVICE_ROLE_KEY` are set — point those at a
disposable project, never prod.

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
3. After the first deploy, copy the Render service URL into
   `VITE_API_URL` on Netlify and redeploy the frontend.

`/health` and `/ready` are wired up — Render uses `/health` for its
liveness probe.

## Project structure

```
.
├── backend/        # FastAPI service
│   ├── app/        # Application code (auth, reconciliation, etc.)
│   ├── scripts/    # Operational scripts (seed_demo.py)
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
```

- [ ] **Step 13.3: Sanity-check the rendered Markdown**

Open the file in a Markdown preview (VS Code, GitHub) — confirm the ASCII diagram and tables render without alignment glitches.

- [ ] **Step 13.4: Commit**

```bash
git add README.md
git commit -m "docs: project README with setup, seeding, and deploy runbook"
```

---

## Task 14: render.yaml + netlify.toml

**Files:**
- Create: `render.yaml`
- Create: `netlify.toml`

- [ ] **Step 14.1: Create `render.yaml`**

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
      - key: LOG_LEVEL
        value: INFO
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_ANON_KEY
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: SUPABASE_JWT_SECRET
        sync: false
      - key: FRONTEND_ORIGIN
        sync: false
      - key: STORAGE_BUCKET
        value: documents
```

- [ ] **Step 14.2: Create `netlify.toml`**

```toml
[build]
  base = "frontend"
  publish = "frontend/dist"
  command = "npm run build"

[build.environment]
  NODE_VERSION = "20"

# SPA fallback so React Router deep links resolve to index.html
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

- [ ] **Step 14.3: Validate Netlify build locally**

```bash
cd frontend && npm run build
```

Expected: clean build into `frontend/dist/`. No TypeScript errors.

- [ ] **Step 14.4: Commit**

```bash
git add render.yaml netlify.toml
git commit -m "feat(deploy): render.yaml + netlify.toml deploy config"
```

---

## Task 15: Phase E wrap-up — full test sweep + tag

**Files:** none — verification + tag.

- [ ] **Step 15.1: Run the full backend suite**

```bash
cd backend && pytest -q
```

Expected: 62 passed, 1 skipped (seed integration). No failures.

- [ ] **Step 15.2: Run the full frontend suite + type-check**

```bash
cd frontend && npm test && npx tsc --noEmit
```

Expected: 30 passed, no type errors.

- [ ] **Step 15.3: Run the manual acceptance checklist from the spec**

Per spec section 8:

1. Fresh-clone walkthrough: confirm README's "Local setup" steps work end-to-end (or manually re-read the README and trace each step against the actual repo state).
2. Run the seeder against dev Supabase, log in as demo, confirm 3 clients + upcoming events + 1 recon visible.
3. Visit a non-existent route (`/clients/this-uuid-doesnt-exist-blah`) → NotFound page renders.
4. `curl http://localhost:8000/ready` → 200 with `version` field.
5. Both test suites green.

- [ ] **Step 15.4: Tag the phase**

```bash
git tag -a phase-e-complete -m "$(cat <<'EOF'
Phase E — Polish + Ship complete.

Deliverables:
- backend: /health and /ready return version, CORS supports FRONTEND_ORIGIN env var
- backend: scripts/seed_demo.py — one tenant, 3 clients, 90 days of events,
  1 reconciliation with 8 deliberate mismatches; idempotent + --reset
- frontend: shared <Spinner /> + <PageLoading /> components
- frontend: <ErrorBoundary /> at root and per authed route
- frontend: real <NotFound /> page replaces silent /login redirect
- frontend: consistent loading states across pages and widgets
- repo: README.md runbook, render.yaml, netlify.toml

Tests: 62 backend (1 skipped integration), 30 frontend.

Next: live deploy (user-owned).
EOF
)"
```

- [ ] **Step 15.5: Confirm tag**

```bash
git tag -l "phase-*"
```

Expected:
```
phase-a-complete
phase-b-complete
phase-c-complete
phase-d-complete
phase-e-complete
```

---

## Self-review notes

**Spec coverage (against `docs/superpowers/specs/2026-05-08-phase-e-polish-and-ship-design.md`):**

| Spec section | Plan task(s) |
|---|---|
| §3 deliverable 1 (seeder) | Tasks 3, 4, 5, 6, 7 |
| §3 deliverable 2 (error boundaries) | Tasks 9, 10 |
| §3 deliverable 3 (NotFound) | Task 11 |
| §3 deliverable 4 (loading) | Tasks 8, 12 |
| §3 deliverable 5 (health + audit) | Tasks 1, 2 |
| §3 deliverable 6 (README + deploy config + .env audit) | Tasks 13, 14; backend `.env.example` audit folded into Task 2 |
| §6.2 CORS hygiene | Task 2 |
| §7.1 frontend `.env.example` audit | Skipped — current file already has the three vars the build needs (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`); no new keys to add. |
| §8 acceptance test | Task 15 |

No spec gaps.

**Type/identifier consistency:** `Spinner` and `PageLoading` (Task 8) are referenced consistently in Task 12. `ErrorBoundary` and `RouteBoundary` (Task 9) used identically in Task 10. `seed`, `_reset_demo`, `DEMO_TENANT_NAME` referenced correctly across Tasks 4-7.

**Placeholder scan:** none — every step has the actual code or command to run.
