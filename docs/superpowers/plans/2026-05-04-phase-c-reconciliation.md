# Phase C — VAT Reconciliation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the hero MVP feature — a CA uploads a purchase register XLSX + supplier export XLSX, the backend matches them, and the frontend renders a color-coded report showing at-risk Input Tax Credit (ITC) in BDT.

**Architecture:** A single FastAPI endpoint (`POST /api/v1/reconciliations`) parses both XLSX files, runs a deterministic four-tier matching algorithm (EXACT > FUZZY > PARTIAL > NO_MATCH) using pandas, and writes results to Supabase via the service role. Frontend uploads files directly to Supabase Storage using the user's JWT, then triggers the backend endpoint with the resulting `document.id` references. The report screen reads results back from Supabase via TanStack Query and renders a hero ITC card, donut breakdown chart, and color-coded line-item table. An XLSX export endpoint regenerates a downloadable spreadsheet from the persisted line items.

**Tech Stack:**
- Backend: FastAPI 0.115 (async), pandas 2.2 + openpyxl 3.1 (XLSX I/O), supabase-py 2.10 (sync, wrapped in `asyncio.to_thread`), structlog, pydantic 2.9
- Frontend: React 18 + TypeScript, axios (FastAPI calls), `@supabase/supabase-js` (Storage uploads + reads), TanStack Query, react-hook-form + Zod, Recharts (donut chart), shadcn/ui
- Database: Postgres via Supabase (RLS-enforced for Storage + DB)

**Critical architectural decisions (locked):**

1. **Audit trigger user_id capture:** Option 3 from the spike — modify the audit trigger to fall back to `NEW.run_by` / `NEW.uploaded_by` / `NEW.created_by` when `request.jwt.claim.sub` is NULL. This means the recon engine code stays clean (no per-write `set_request_user` ceremony) and audit rows get the right actor automatically. (Spike doc: `migrations/spike_results/audit_trigger_user_id_capture.md`.)
2. **Storage layout:** Single private bucket `recon-files`. Path: `{tenant_id}/{client_id}/{recon_uuid}/{purchase_register|supplier_export|recon_export}.xlsx`. Tenant ID at the top of the path is the RLS pivot.
3. **Frontend → Storage uploads:** Use the user's JWT (RLS-protected). Backend uses service-role to download for processing.
4. **Synchronous processing:** No Celery, no polling. Endpoint returns `{ reconciliation_id }` after the full match completes (target <3s for 1500 rows).
5. **Recon endpoint is idempotent on `(client_id, period_start, period_end)`:** the `vat_reconciliations` UNIQUE constraint guarantees this; backend returns `409 RECONCILIATION_ALREADY_EXISTS` if a completed run exists for the same window.

---

## Required reading before starting

- Spec: `docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md` (sections 6.5, 7, 8)
- Spike result: `migrations/spike_results/audit_trigger_user_id_capture.md`
- Existing audit trigger: `migrations/0005_audit_trigger.sql`
- Existing tenant tables: `migrations/0002_tenant_tables.sql` (the `vat_reconciliations` and `recon_line_items` schemas you'll be writing into)
- Existing dependencies module: `backend/app/dependencies.py` (auth + tenant lookup)
- Existing onboarding RPC pattern: `migrations/0009_onboard_create_tenant_rpc.sql` (atomic SECURITY DEFINER pattern reused for the line-items insert)

## File map

### New backend files

```
migrations/
  0010_audit_trigger_fallback.sql      # Audit trigger reads row.run_by/uploaded_by/created_by
  0011_storage_buckets.sql             # 'recon-files' bucket + RLS

backend/app/reconciliation/
  __init__.py                          # Exports
  schemas.py                           # ReconciliationCreate, LineItemDTO, AggregatesDTO, etc.
  normalize.py                         # normalize_invoice_no(s) -> str
  parser.py                            # parse_purchase_register(bytes) / parse_supplier_export(bytes)
  matcher.py                           # match_register(pr, sf) -> list[MatchResult]
  aggregates.py                        # aggregate(matches) -> AggregatesDTO
  storage.py                           # download_xlsx(path) -> bytes
  persistence.py                       # insert_vat_reconciliation, bulk_insert_line_items
  exporter.py                          # export_to_xlsx(recon_id) -> bytes
  service.py                           # run_reconciliation(req, tenant_id, user_id) — orchestrator
  router.py                            # FastAPI APIRouter

backend/app/main.py                    # MODIFY: include reconciliation.router

backend/app/core/exceptions.py         # MODIFY: add INVALID_XLSX_FORMAT, RECONCILIATION_ALREADY_EXISTS,
                                       #   STORAGE_DOWNLOAD_FAILED, DOCUMENT_TENANT_MISMATCH

backend/tests/reconciliation/
  __init__.py
  conftest.py                          # Fixtures: minimal valid XLSX bytes for both formats
  test_normalize.py                    # 6+ cases for invoice no normalization
  test_parser.py                       # Happy path + missing-column errors
  test_matcher.py                      # All four match tiers + per-row priority
  test_aggregates.py                   # Sums + edge cases
  test_persistence.py                  # Bulk insert path
  test_service.py                      # End-to-end orchestration with mocked storage
  test_router.py                       # Endpoint contract + auth
  fixtures/
    purchase_register_valid.xlsx       # Generated by conftest helper, 5 rows
    supplier_export_valid.xlsx
```

### New frontend files

```
frontend/public/templates/
  purchase_register_template.xlsx      # Sample with just headers + 1 example row
  supplier_export_template.xlsx

frontend/src/types/
  reconciliation.ts                    # Zod schemas + types

frontend/src/lib/
  api.ts                               # Axios instance pointing at VITE_API_URL with auth interceptor
  storage.ts                           # uploadReconFile(file, paths) -> { storage_path, document_id }

frontend/src/hooks/
  useReconciliations.ts                # useReconList(clientId), useRecon(reconId), useRunReconciliation(),
                                       #   useReconLineItems(reconId), useUpdateLineItemOverride()

frontend/src/components/recon/
  FileDropzone.tsx                     # File input with drag+drop, validation
  PeriodPicker.tsx                     # Two month inputs producing first-of-month / end-of-month dates
  ReconHeroCard.tsx                    # Big BDT at-risk number + match-tier counts
  ReconBreakdownChart.tsx              # Recharts donut
  ReconLineItemsTable.tsx              # Table with color-coded match status
  MatchStatusBadge.tsx                 # exact=green, fuzzy=yellow, partial=orange, no_match=red
  LineItemDrawer.tsx                   # shadcn Sheet with line item details + override controls
  CAOverrideSelect.tsx                 # Dropdown: approved / disputed / ignore / null

frontend/src/pages/
  ReconNew.tsx                         # /clients/:id/recon/new
  ReconReport.tsx                      # /clients/:id/recon/:reconId

frontend/src/router.tsx                # MODIFY: add 2 new routes
frontend/src/pages/ClientDetail.tsx    # MODIFY: add Reconciliations tab
```

---

## Section 1 — Foundation (migrations + error codes)

### Task C1: Audit trigger fallback to row actor columns

**Why:** The Phase A spike confirmed `set_request_user` doesn't survive the per-REST-call transaction boundary. With the recon backend using service role, `audit_log.user_id` would be NULL. Option 3 fixes this transparently: the trigger reads the actor from the row itself when the JWT claim is missing.

**Files:**
- Create: `migrations/0010_audit_trigger_fallback.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0010_audit_trigger_fallback.sql
-- Audit trigger: when request.jwt.claim.sub is NULL (e.g. backend writes via service-role),
-- fall back to the row's own actor column (run_by / uploaded_by / created_by).
-- This means audit_log.user_id is correct without backend ceremony.
-- Spike: migrations/spike_results/audit_trigger_user_id_capture.md (Option 3).

CREATE OR REPLACE FUNCTION audit_log_trigger() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id  uuid;
  v_claim    text;
  v_row      jsonb;
BEGIN
  -- 1. Try the JWT claim first (frontend-originated writes)
  v_claim := current_setting('request.jwt.claim.sub', true);
  IF v_claim IS NOT NULL AND v_claim <> '' THEN
    BEGIN
      v_user_id := v_claim::uuid;
    EXCEPTION WHEN OTHERS THEN
      v_user_id := NULL;
    END;
  END IF;

  -- 2. Fall back to the row's own actor column (backend-originated writes).
  --    Each tenant-scoped table names the actor differently:
  --      clients.created_by | documents.uploaded_by
  --      vat_reconciliations.run_by | recon_line_items: inherit from parent recon (NULL ok)
  IF v_user_id IS NULL THEN
    v_row := CASE TG_OP WHEN 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
    BEGIN
      v_user_id := COALESCE(
        (v_row->>'run_by')::uuid,
        (v_row->>'uploaded_by')::uuid,
        (v_row->>'created_by')::uuid
      );
    EXCEPTION WHEN OTHERS THEN
      v_user_id := NULL;
    END;
  END IF;

  IF (TG_OP = 'INSERT') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (NEW.tenant_id, v_user_id, 'insert', TG_TABLE_NAME, NEW.id, NULL, to_jsonb(NEW));
    RETURN NEW;
  ELSIF (TG_OP = 'UPDATE') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (NEW.tenant_id, v_user_id, 'update', TG_TABLE_NAME, NEW.id, to_jsonb(OLD), to_jsonb(NEW));
    RETURN NEW;
  ELSIF (TG_OP = 'DELETE') THEN
    INSERT INTO audit_log (tenant_id, user_id, action, table_name, row_id, before, after)
    VALUES (OLD.tenant_id, v_user_id, 'delete', TG_TABLE_NAME, OLD.id, to_jsonb(OLD), NULL);
    RETURN OLD;
  END IF;
  RETURN NULL;
END;
$$;

COMMENT ON FUNCTION audit_log_trigger() IS
  'Audit trigger v2: prefers JWT claim, falls back to NEW.run_by/uploaded_by/created_by '
  'so backend writes via service-role still produce non-NULL audit_log.user_id.';
```

- [ ] **Step 2: Apply the migration via Supabase MCP**

Use the Supabase MCP `apply_migration` tool with `name="0010_audit_trigger_fallback"` and the SQL above as `query`. Verify success with the JSON `{"success": true}` response.

- [ ] **Step 3: Verify with a quick spike SQL**

Run via the MCP `execute_sql` tool:

```sql
-- Insert a test client without setting JWT claim, with a known created_by uuid.
-- Then read the most recent audit_log row and assert user_id == created_by.
DO $$
DECLARE
  v_tenant uuid;
  v_user   uuid := '99999999-9999-9999-9999-999999999999';
  v_client uuid;
  v_audit_user uuid;
BEGIN
  -- Use any existing tenant or create a throwaway
  SELECT id INTO v_tenant FROM tenants LIMIT 1;
  IF v_tenant IS NULL THEN
    INSERT INTO tenants (firm_name, email) VALUES ('SPIKE', 'spike@local') RETURNING id INTO v_tenant;
  END IF;

  -- Reset request.jwt.claim.sub so we test the fallback path
  PERFORM set_config('request.jwt.claim.sub', '', true);

  INSERT INTO clients (tenant_id, name, entity_type, created_by)
  VALUES (v_tenant, 'spike-client', 'company', v_user)
  RETURNING id INTO v_client;

  SELECT user_id INTO v_audit_user FROM audit_log
   WHERE table_name = 'clients' AND row_id = v_client;

  RAISE NOTICE 'audit user_id=% expected=%', v_audit_user, v_user;
  IF v_audit_user IS DISTINCT FROM v_user THEN
    RAISE EXCEPTION 'fallback FAILED: got % expected %', v_audit_user, v_user;
  END IF;

  -- cleanup
  DELETE FROM audit_log WHERE row_id = v_client;
  DELETE FROM clients WHERE id = v_client;
END $$;
```

Expected: query returns successfully (no exception raised). The DO block prints a NOTICE confirming the user_id matches.

- [ ] **Step 4: Commit**

```bash
git add migrations/0010_audit_trigger_fallback.sql
git commit -m "feat(db): audit trigger falls back to row actor when JWT claim missing"
```

---

### Task C2: Storage bucket + RLS for recon files

**Why:** The frontend uploads XLSX files using the user's JWT, the backend reads them using service-role. Need a private bucket with RLS policies that only let a tenant's users see their own tenant's files.

**Files:**
- Create: `migrations/0011_storage_buckets.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0011_storage_buckets.sql
-- Private bucket 'recon-files' for purchase register / supplier export / recon export XLSX.
-- Path layout: {tenant_id}/{client_id}/{recon_uuid}/{filename}.xlsx
-- The first path segment (tenant_id) is the RLS pivot.

INSERT INTO storage.buckets (id, name, public)
VALUES ('recon-files', 'recon-files', false)
ON CONFLICT (id) DO NOTHING;

-- Helper: pull tenant_id from the storage object path's first segment
-- storage.foldername returns text[] of path segments before the filename.

DROP POLICY IF EXISTS recon_files_tenant_select ON storage.objects;
DROP POLICY IF EXISTS recon_files_tenant_insert ON storage.objects;
DROP POLICY IF EXISTS recon_files_tenant_update ON storage.objects;
DROP POLICY IF EXISTS recon_files_tenant_delete ON storage.objects;

CREATE POLICY recon_files_tenant_select ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY recon_files_tenant_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY recon_files_tenant_update ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  )
  WITH CHECK (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY recon_files_tenant_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'recon-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

-- Service role bypasses RLS automatically; backend doesn't need a policy.
```

- [ ] **Step 2: Apply via Supabase MCP**

Apply with `name="0011_storage_buckets"`. Verify success.

- [ ] **Step 3: Verify the bucket exists**

```sql
SELECT id, name, public FROM storage.buckets WHERE id = 'recon-files';
```

Expected: one row with `public = false`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0011_storage_buckets.sql
git commit -m "feat(storage): private recon-files bucket with tenant-scoped RLS"
```

---

### Task C3: New error codes for the recon flow

**Files:**
- Modify: `backend/app/core/exceptions.py`
- Test: `backend/tests/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_exceptions.py` (create if it doesn't exist):

```python
"""Tests for HishabError subclasses."""
from app.core.exceptions import (
    InvalidXlsxFormatError,
    ReconciliationAlreadyExistsError,
    StorageDownloadFailedError,
    DocumentTenantMismatchError,
)


def test_invalid_xlsx_lists_missing_columns():
    err = InvalidXlsxFormatError(
        file_label="purchase register",
        missing_columns=["Invoice No", "Supplier BIN"],
    )
    assert err.code == "INVALID_XLSX_FORMAT"
    assert err.status_code == 400
    assert "purchase register" in err.message
    assert "Invoice No" in err.message
    assert "Supplier BIN" in err.message
    assert err.details == {
        "file_label": "purchase register",
        "missing_columns": ["Invoice No", "Supplier BIN"],
    }


def test_reconciliation_already_exists_carries_id():
    err = ReconciliationAlreadyExistsError(reconciliation_id="abc-123")
    assert err.code == "RECONCILIATION_ALREADY_EXISTS"
    assert err.status_code == 409
    assert err.details == {"reconciliation_id": "abc-123"}


def test_storage_download_failed():
    err = StorageDownloadFailedError(path="t/c/r/file.xlsx", reason="404 not found")
    assert err.code == "STORAGE_DOWNLOAD_FAILED"
    assert err.status_code == 502
    assert "t/c/r/file.xlsx" in err.message


def test_document_tenant_mismatch():
    err = DocumentTenantMismatchError(document_id="doc-1")
    assert err.code == "DOCUMENT_TENANT_MISMATCH"
    assert err.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_exceptions.py -v
```

Expected: ImportError — none of the new classes exist yet.

- [ ] **Step 3: Add the new classes to `app/core/exceptions.py`**

Append (do not replace existing classes):

```python
# ── Reconciliation Errors (Phase C) ──────────────────────────────────────


class InvalidXlsxFormatError(HishabError):
    def __init__(self, file_label: str, missing_columns: list[str]) -> None:
        cols = ", ".join(missing_columns)
        super().__init__(
            "INVALID_XLSX_FORMAT",
            f"{file_label} is missing required columns: {cols}",
            status_code=400,
            details={"file_label": file_label, "missing_columns": missing_columns},
        )


class ReconciliationAlreadyExistsError(HishabError):
    def __init__(self, reconciliation_id: str) -> None:
        super().__init__(
            "RECONCILIATION_ALREADY_EXISTS",
            "A reconciliation already exists for this client and period.",
            status_code=409,
            details={"reconciliation_id": reconciliation_id},
        )


class StorageDownloadFailedError(HishabError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            "STORAGE_DOWNLOAD_FAILED",
            f"Could not download {path}: {reason}",
            status_code=502,
            details={"path": path, "reason": reason},
        )


class DocumentTenantMismatchError(HishabError):
    def __init__(self, document_id: str) -> None:
        super().__init__(
            "DOCUMENT_TENANT_MISMATCH",
            "Document does not belong to the authenticated tenant.",
            status_code=403,
            details={"document_id": document_id},
        )
```

- [ ] **Step 4: Run the test, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_exceptions.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/exceptions.py backend/tests/test_exceptions.py
git commit -m "feat(errors): add reconciliation-flow error classes"
```

---

## Section 2 — Pure functions (TDD core of the engine)

### Task C4: Reconciliation module skeleton + Pydantic schemas

**Files:**
- Create: `backend/app/reconciliation/__init__.py`
- Create: `backend/app/reconciliation/schemas.py`
- Create: `backend/tests/reconciliation/__init__.py`
- Test: `backend/tests/reconciliation/test_schemas.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/reconciliation/test_schemas.py`:

```python
"""Tests for reconciliation Pydantic schemas."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.reconciliation.schemas import (
    ReconciliationCreateRequest,
    PurchaseRow,
    SupplierRow,
    MatchStatus,
)


def test_create_request_round_trips():
    payload = {
        "client_id": str(uuid4()),
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "purchase_register_doc_id": str(uuid4()),
        "supplier_data_doc_id": str(uuid4()),
    }
    req = ReconciliationCreateRequest.model_validate(payload)
    assert req.period_start == date(2024, 1, 1)
    assert req.period_end == date(2024, 1, 31)


def test_create_request_rejects_inverted_period():
    with pytest.raises(ValidationError):
        ReconciliationCreateRequest(
            client_id=uuid4(),
            period_start=date(2024, 2, 1),
            period_end=date(2024, 1, 1),
            purchase_register_doc_id=uuid4(),
            supplier_data_doc_id=uuid4(),
        )


def test_purchase_row_normalizes_amounts_to_decimal():
    row = PurchaseRow(
        invoice_no="INV-001",
        supplier_bin="123456789",
        supplier_name="Acme Ltd",
        invoice_date=date(2024, 1, 15),
        taxable_amount_bdt=1000.50,
        vat_amount_bdt=150.075,
    )
    assert isinstance(row.taxable_amount_bdt, Decimal)
    assert row.vat_amount_bdt == Decimal("150.08")  # rounded to 2dp


def test_supplier_row_minimal():
    row = SupplierRow(
        invoice_no="INV-001",
        invoice_date=date(2024, 1, 15),
        taxable_amount_bdt=Decimal("1000.50"),
        vat_amount_bdt=Decimal("150.08"),
        buyer_bin="987654321",
    )
    assert row.invoice_no == "INV-001"


def test_match_status_values():
    assert MatchStatus.EXACT.value == "exact"
    assert MatchStatus.FUZZY.value == "fuzzy"
    assert MatchStatus.PARTIAL.value == "partial"
    assert MatchStatus.NO_MATCH.value == "no_match"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_schemas.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Create the package init files**

`backend/app/reconciliation/__init__.py`:

```python
"""HishabAI VAT reconciliation engine."""
```

`backend/tests/reconciliation/__init__.py`: empty file.

- [ ] **Step 4: Implement the schemas**

`backend/app/reconciliation/schemas.py`:

```python
"""Pydantic models for the reconciliation flow."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    """Round to 2 decimal places using banker-safe HALF_UP."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class MatchStatus(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    PARTIAL = "partial"
    NO_MATCH = "no_match"


class CAOverride(str, Enum):
    APPROVED = "approved"
    DISPUTED = "disputed"
    IGNORE = "ignore"


# ── Inbound API ──────────────────────────────────────────────────────────


class ReconciliationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    period_start: date
    period_end: date
    purchase_register_doc_id: UUID
    supplier_data_doc_id: UUID

    @model_validator(mode="after")
    def _period_ordered(self) -> "ReconciliationCreateRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ReconciliationCreateResponse(BaseModel):
    reconciliation_id: UUID


# ── Parser DTOs ──────────────────────────────────────────────────────────


class PurchaseRow(BaseModel):
    """One row from the purchase register XLSX."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_no: str
    supplier_bin: Optional[str] = None
    supplier_name: Optional[str] = None
    invoice_date: date
    taxable_amount_bdt: Decimal
    vat_amount_bdt: Decimal

    @field_validator("taxable_amount_bdt", "vat_amount_bdt", mode="before")
    @classmethod
    def _round(cls, v: object) -> Decimal:
        return _to_2dp(v)  # type: ignore[arg-type]


class SupplierRow(BaseModel):
    """One row from the supplier-filed export XLSX."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_no: str
    invoice_date: date
    taxable_amount_bdt: Decimal
    vat_amount_bdt: Decimal
    buyer_bin: Optional[str] = None

    @field_validator("taxable_amount_bdt", "vat_amount_bdt", mode="before")
    @classmethod
    def _round(cls, v: object) -> Decimal:
        return _to_2dp(v)  # type: ignore[arg-type]


# ── Matcher output DTOs ──────────────────────────────────────────────────


class DiscrepancyFlags(BaseModel):
    date_off_by_days: Optional[int] = None
    amount_diff_bdt: Optional[Decimal] = None
    amount_diff_pct: Optional[float] = None
    reason: Optional[str] = None


class MatchResult(BaseModel):
    """Result of matching one purchase row against the supplier pool."""
    pr_row: PurchaseRow
    sf_row: Optional[SupplierRow] = None
    status: MatchStatus
    score: Decimal
    flags: DiscrepancyFlags = Field(default_factory=DiscrepancyFlags)


class AggregatesDTO(BaseModel):
    total_invoices: int
    matched_exact: int
    matched_fuzzy: int
    partial_match: int
    no_match: int
    total_vat_claimed_bdt: Decimal
    safe_itc_bdt: Decimal
    at_risk_itc_bdt: Decimal
```

- [ ] **Step 5: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_schemas.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/reconciliation/__init__.py backend/app/reconciliation/schemas.py \
        backend/tests/reconciliation/__init__.py backend/tests/reconciliation/test_schemas.py
git commit -m "feat(recon): add Pydantic schemas for the reconciliation flow"
```

---

### Task C5: Invoice number normalization

**Why:** Real invoices vary in formatting ("INV-0023/2024", "inv 23 / 2024"). To compare them reliably, normalize to a canonical form before comparison.

**Files:**
- Create: `backend/app/reconciliation/normalize.py`
- Test: `backend/tests/reconciliation/test_normalize.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for invoice number normalization."""
import pytest

from app.reconciliation.normalize import normalize_invoice_no


@pytest.mark.parametrize("raw,expected", [
    ("INV-0023/2024", "inv23/2024"),
    ("inv 23 / 2024", "inv23/2024"),
    ("  INV-23/2024  ", "inv23/2024"),
    ("INV-23-2024", "inv232024"),
    ("MUSHAK-9.1/00045", "mushak9.1/45"),
    ("00045", "45"),
    ("ABC", "abc"),
    ("", ""),
])
def test_normalize_invoice_no(raw: str, expected: str):
    assert normalize_invoice_no(raw) == expected


def test_normalize_invoice_no_preserves_dot_separators():
    """Decimal points inside identifiers must NOT be stripped."""
    assert normalize_invoice_no("9.1") == "9.1"


def test_normalize_invoice_no_handles_none_via_caller():
    """Function does not handle None — caller's responsibility."""
    with pytest.raises(AttributeError):
        normalize_invoice_no(None)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_normalize.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/reconciliation/normalize.py`:

```python
"""Invoice number normalization for matching."""
from __future__ import annotations

import re

# Match runs of digits so we can strip leading zeros per numeric segment
_DIGITS_RE = re.compile(r"\d+")
# Non-alphanumeric, non-slash, non-dot characters to drop
_STRIP_RE = re.compile(r"[^a-z0-9/.]")


def normalize_invoice_no(value: str) -> str:
    """Canonical form for invoice number comparison.

    Steps:
      1. Lowercase
      2. Strip surrounding whitespace
      3. Remove characters that aren't letters, digits, '/', or '.'
         (kills hyphens, spaces, parens, etc.)
      4. Strip leading zeros from each numeric segment

    Decimal '.' is preserved so identifiers like 'mushak-9.1/...' stay intact.

    >>> normalize_invoice_no("INV-0023/2024")
    'inv23/2024'
    """
    s = value.lower().strip()
    s = _STRIP_RE.sub("", s)
    return _DIGITS_RE.sub(lambda m: str(int(m.group(0))), s)
```

- [ ] **Step 4: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_normalize.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconciliation/normalize.py backend/tests/reconciliation/test_normalize.py
git commit -m "feat(recon): add invoice number normalization with edge-case tests"
```

---

### Task C6: XLSX parsers + test fixtures

**Files:**
- Create: `backend/app/reconciliation/parser.py`
- Create: `backend/tests/reconciliation/conftest.py`
- Test: `backend/tests/reconciliation/test_parser.py`

- [ ] **Step 1: Write the conftest helper that builds in-memory XLSX**

`backend/tests/reconciliation/conftest.py`:

```python
"""Shared fixtures for reconciliation tests."""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import openpyxl
import pytest


def _make_xlsx(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def valid_purchase_register_bytes() -> bytes:
    headers = [
        "Invoice No", "Supplier BIN", "Supplier Name",
        "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
    ]
    rows = [
        ["INV-0023/2024", "123456789", "Acme Ltd", date(2024, 1, 15), 1000.00, 150.00],
        ["INV-0024/2024", "123456789", "Acme Ltd", date(2024, 1, 20),  500.00,  75.00],
        ["INV-0001",      "987654321", "Beta Co",  date(2024, 1, 10), 2500.50, 375.08],
    ]
    return _make_xlsx(headers, rows)


@pytest.fixture
def valid_supplier_export_bytes() -> bytes:
    headers = [
        "Invoice No", "Invoice Date",
        "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN",
    ]
    rows = [
        # Exact match for purchase row 1
        ["INV-0023/2024", date(2024, 1, 15), 1000.00, 150.00, "111222333"],
        # Fuzzy match for purchase row 3 (date off by 1 day, amount within 0.5%)
        ["INV-0001",      date(2024, 1, 11), 2500.00, 375.00, "111222333"],
        # Unrelated row (buyer is someone else's BIN)
        ["INV-9999",      date(2024, 1, 5),    50.00,   7.50, "555666777"],
    ]
    return _make_xlsx(headers, rows)


@pytest.fixture
def purchase_register_missing_column_bytes() -> bytes:
    # Drop "Supplier BIN"
    headers = [
        "Invoice No", "Supplier Name",
        "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
    ]
    return _make_xlsx(headers, [["INV-1", "X", date(2024, 1, 1), 100, 15]])


@pytest.fixture
def empty_xlsx_bytes() -> bytes:
    return _make_xlsx(["irrelevant"], [])
```

- [ ] **Step 2: Write the failing parser tests**

`backend/tests/reconciliation/test_parser.py`:

```python
"""Tests for XLSX parsers."""
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import InvalidXlsxFormatError
from app.reconciliation.parser import (
    parse_purchase_register,
    parse_supplier_export,
)
from app.reconciliation.schemas import PurchaseRow, SupplierRow


def test_parse_purchase_register_happy_path(valid_purchase_register_bytes: bytes):
    rows = parse_purchase_register(valid_purchase_register_bytes)

    assert len(rows) == 3
    assert isinstance(rows[0], PurchaseRow)
    assert rows[0].invoice_no == "INV-0023/2024"
    assert rows[0].supplier_bin == "123456789"
    assert rows[0].invoice_date == date(2024, 1, 15)
    assert rows[0].taxable_amount_bdt == Decimal("1000.00")
    assert rows[0].vat_amount_bdt == Decimal("150.00")


def test_parse_purchase_register_is_case_insensitive(valid_purchase_register_bytes: bytes):
    """The parser must accept 'invoice no' as well as 'Invoice No'."""
    # Build a variant with lowercased headers; reuse openpyxl in-line.
    import io, openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([
        "invoice no", "supplier bin", "supplier name",
        "invoice date", "taxable amount (bdt)", "vat amount (bdt)",
    ])
    ws.append(["INV-1", "123456789", "X", date(2024, 1, 1), 100, 15])
    buf = io.BytesIO()
    wb.save(buf)

    rows = parse_purchase_register(buf.getvalue())
    assert len(rows) == 1
    assert rows[0].invoice_no == "INV-1"


def test_parse_purchase_register_missing_column_raises(
    purchase_register_missing_column_bytes: bytes,
):
    with pytest.raises(InvalidXlsxFormatError) as ei:
        parse_purchase_register(purchase_register_missing_column_bytes)
    assert "Supplier BIN" in ei.value.message
    assert ei.value.details["file_label"] == "purchase register"


def test_parse_purchase_register_empty_returns_empty_list(empty_xlsx_bytes: bytes):
    """An empty file (only header row exists but no required headers) raises."""
    with pytest.raises(InvalidXlsxFormatError):
        parse_purchase_register(empty_xlsx_bytes)


def test_parse_supplier_export_happy_path(valid_supplier_export_bytes: bytes):
    rows = parse_supplier_export(valid_supplier_export_bytes)
    assert len(rows) == 3
    assert isinstance(rows[0], SupplierRow)
    assert rows[0].invoice_no == "INV-0023/2024"
    assert rows[0].buyer_bin == "111222333"
```

- [ ] **Step 3: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_parser.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement the parser**

`backend/app/reconciliation/parser.py`:

```python
"""XLSX parsers for the purchase register and supplier export formats."""
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

import pandas as pd

from app.core.exceptions import InvalidXlsxFormatError

from .schemas import PurchaseRow, SupplierRow


# Required columns are matched case-insensitively after stripping whitespace.
_PURCHASE_COLUMNS = {
    "invoice no":            "invoice_no",
    "supplier bin":          "supplier_bin",
    "supplier name":         "supplier_name",
    "invoice date":          "invoice_date",
    "taxable amount (bdt)":  "taxable_amount_bdt",
    "vat amount (bdt)":      "vat_amount_bdt",
}

_SUPPLIER_COLUMNS = {
    "invoice no":            "invoice_no",
    "invoice date":          "invoice_date",
    "taxable amount (bdt)":  "taxable_amount_bdt",
    "vat amount (bdt)":      "vat_amount_bdt",
    "buyer bin":             "buyer_bin",
}


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _check_columns(df: pd.DataFrame, required: dict[str, str], label: str) -> None:
    missing = [original.title() if original != "vat amount (bdt)" else "VAT Amount (BDT)"
               for original in required if original not in df.columns]
    # Re-derive original casings for the error message
    pretty = {
        "invoice no": "Invoice No",
        "supplier bin": "Supplier BIN",
        "supplier name": "Supplier Name",
        "invoice date": "Invoice Date",
        "taxable amount (bdt)": "Taxable Amount (BDT)",
        "vat amount (bdt)": "VAT Amount (BDT)",
        "buyer bin": "Buyer BIN",
    }
    missing = [pretty[k] for k in required if k not in df.columns]
    if missing:
        raise InvalidXlsxFormatError(file_label=label, missing_columns=missing)


def _coerce_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Accept YYYY-MM-DD or DD/MM/YYYY
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Could not parse date: {value!r}")


def _coerce_str(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).strip() or None


def parse_purchase_register(file_bytes: bytes) -> list[PurchaseRow]:
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    df = _normalize_headers(df)
    _check_columns(df, _PURCHASE_COLUMNS, label="purchase register")

    out: list[PurchaseRow] = []
    for _, row in df.iterrows():
        out.append(PurchaseRow(
            invoice_no=str(row["invoice no"]).strip(),
            supplier_bin=_coerce_str(row["supplier bin"]),
            supplier_name=_coerce_str(row["supplier name"]),
            invoice_date=_coerce_date(row["invoice date"]),
            taxable_amount_bdt=row["taxable amount (bdt)"],
            vat_amount_bdt=row["vat amount (bdt)"],
        ))
    return out


def parse_supplier_export(file_bytes: bytes) -> list[SupplierRow]:
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    df = _normalize_headers(df)
    _check_columns(df, _SUPPLIER_COLUMNS, label="supplier export")

    out: list[SupplierRow] = []
    for _, row in df.iterrows():
        out.append(SupplierRow(
            invoice_no=str(row["invoice no"]).strip(),
            invoice_date=_coerce_date(row["invoice date"]),
            taxable_amount_bdt=row["taxable amount (bdt)"],
            vat_amount_bdt=row["vat amount (bdt)"],
            buyer_bin=_coerce_str(row["buyer bin"]),
        ))
    return out
```

- [ ] **Step 5: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_parser.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/reconciliation/parser.py backend/tests/reconciliation/conftest.py \
        backend/tests/reconciliation/test_parser.py
git commit -m "feat(recon): XLSX parsers for purchase register and supplier export"
```

---

### Task C7: Matching engine — per-row decision

**Why:** Core of the hero feature. Pure function: given one purchase row and the full supplier pool, return a `MatchResult` with status / score / flags.

**Files:**
- Create: `backend/app/reconciliation/matcher.py`
- Test: `backend/tests/reconciliation/test_matcher.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/reconciliation/test_matcher.py`:

```python
"""Tests for the matching engine."""
from datetime import date
from decimal import Decimal

from app.reconciliation.matcher import match_register, match_one
from app.reconciliation.schemas import (
    MatchStatus, PurchaseRow, SupplierRow,
)


def _pr(invoice_no: str = "INV-1", bin_: str | None = "111111111",
        d: date = date(2024, 1, 15), tax: float = 1000, vat: float = 150) -> PurchaseRow:
    return PurchaseRow(
        invoice_no=invoice_no, supplier_bin=bin_, supplier_name="X",
        invoice_date=d, taxable_amount_bdt=tax, vat_amount_bdt=vat,
    )


def _sf(invoice_no: str = "INV-1", buyer_bin: str | None = "999999999",
        d: date = date(2024, 1, 15), tax: float = 1000, vat: float = 150) -> SupplierRow:
    return SupplierRow(
        invoice_no=invoice_no, invoice_date=d,
        taxable_amount_bdt=tax, vat_amount_bdt=vat, buyer_bin=buyer_bin,
    )


# ── EXACT ───────────────────────────────────────────────────────────────


def test_exact_match_when_all_fields_align():
    pr = _pr("INV-0023", "111111111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-23", "x", date(2024, 1, 15), 1000, 150)]  # invoice_no normalized matches
    by_bin = {"111111111": pool}

    result = match_one(pr, by_bin)
    assert result.status == MatchStatus.EXACT
    assert result.score == Decimal("1.00")


def test_exact_normalizes_invoice_no():
    pr = _pr("INV-0023/2024")
    pool = [_sf("inv 23 / 2024")]
    by_bin = {pr.supplier_bin: pool}
    assert match_one(pr, by_bin).status == MatchStatus.EXACT


# ── FUZZY ───────────────────────────────────────────────────────────────


def test_fuzzy_when_date_off_by_3_days_and_amount_within_half_pct():
    pr = _pr("INV-1", "111", date(2024, 1, 15), 1000.00, 150.00)
    pool = [_sf("INV-1", "x", date(2024, 1, 18), 1003.00, 150.45)]  # within 0.5%
    by_bin = {"111": pool}

    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.FUZZY
    assert res.score == Decimal("0.80")
    assert res.flags.date_off_by_days == 3
    assert res.flags.amount_diff_pct is not None
    assert res.flags.amount_diff_pct < 0.005


def test_fuzzy_falls_through_when_date_off_by_4_days():
    pr = _pr("INV-1", "111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-1", "x", date(2024, 1, 19), 1000, 150)]
    by_bin = {"111": pool}
    assert match_one(pr, by_bin).status == MatchStatus.PARTIAL


def test_fuzzy_falls_through_when_amount_off_by_1pct():
    pr = _pr("INV-1", "111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-1", "x", date(2024, 1, 15), 1010, 151.5)]  # 1% off
    by_bin = {"111": pool}
    assert match_one(pr, by_bin).status == MatchStatus.PARTIAL


# ── PARTIAL ──────────────────────────────────────────────────────────────


def test_partial_when_bin_present_but_invoice_not_found():
    pr = _pr("INV-A", "111", date(2024, 1, 15), 1000, 150)
    pool = [_sf("INV-OTHER", "x", date(2024, 1, 15), 1000, 150)]
    by_bin = {"111": pool}

    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.PARTIAL
    assert res.score == Decimal("0.40")
    assert res.flags.reason == "no_invoice_no_match"


# ── NO_MATCH ─────────────────────────────────────────────────────────────


def test_no_match_when_bin_not_in_supplier_pool():
    pr = _pr("INV-A", "111", date(2024, 1, 15), 1000, 150)
    by_bin = {"222": []}

    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.NO_MATCH
    assert res.score == Decimal("0.00")
    assert res.flags.reason == "supplier_bin_not_filed"


def test_no_match_when_pr_has_null_bin():
    pr = _pr("INV-A", None, date(2024, 1, 15), 1000, 150)
    by_bin: dict[str, list[SupplierRow]] = {}
    res = match_one(pr, by_bin)
    assert res.status == MatchStatus.NO_MATCH


# ── Whole register ───────────────────────────────────────────────────────


def test_match_register_returns_one_result_per_purchase_row(
    valid_purchase_register_bytes: bytes,
    valid_supplier_export_bytes: bytes,
):
    """Smoke test: 3 purchase rows in / 3 results out."""
    from app.reconciliation.parser import parse_purchase_register, parse_supplier_export
    pr_rows = parse_purchase_register(valid_purchase_register_bytes)
    sf_rows = parse_supplier_export(valid_supplier_export_bytes)
    results = match_register(pr_rows, sf_rows)
    assert len(results) == 3

    statuses = [r.status for r in results]
    # Row 1 (INV-0023/2024 vs INV-0023/2024 same date/amount) → EXACT
    # Row 2 (INV-0024/2024 BIN exists in PR but not as buyer in supplier rows for that bin) → NO_MATCH (bin not filed)
    # Row 3 (INV-0001 fuzzy match: date off by 1, amount within 0.5%) → FUZZY
    assert MatchStatus.EXACT in statuses
    assert MatchStatus.FUZZY in statuses
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_matcher.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement the matcher**

`backend/app/reconciliation/matcher.py`:

```python
"""VAT reconciliation matching engine.

Per-row decision priority (first match wins):
    EXACT  > FUZZY > PARTIAL > NO_MATCH

EXACT:    same BIN, same normalized invoice_no, same date, same amounts (<0.01 BDT diff)
FUZZY:    same BIN, same normalized invoice_no, date within 3 days, amount within 0.5%
PARTIAL:  same BIN exists in supplier pool, but no invoice_no match
NO_MATCH: BIN not present in supplier pool at all
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable

from .normalize import normalize_invoice_no
from .schemas import (
    DiscrepancyFlags, MatchResult, MatchStatus,
    PurchaseRow, SupplierRow,
)

EXACT_AMOUNT_TOL = Decimal("0.01")        # BDT
FUZZY_DATE_TOL_DAYS = 3
FUZZY_AMOUNT_TOL_PCT = 0.005              # 0.5%


def _index_supplier_pool(rows: Iterable[SupplierRow]) -> dict[str, list[SupplierRow]]:
    """Group supplier rows by buyer_bin so we can do constant-time lookup."""
    out: dict[str, list[SupplierRow]] = defaultdict(list)
    for r in rows:
        if r.buyer_bin:
            out[r.buyer_bin].append(r)
    return dict(out)


def _amount_diff_pct(pr_amount: Decimal, sf_amount: Decimal) -> float:
    """Returns the absolute relative diff. Uses sf_amount as denominator."""
    if sf_amount == 0:
        return float("inf")
    return float(abs(pr_amount - sf_amount) / sf_amount)


def _try_exact(pr: PurchaseRow, sf: SupplierRow) -> bool:
    if pr.invoice_date != sf.invoice_date:
        return False
    if abs(pr.taxable_amount_bdt - sf.taxable_amount_bdt) >= EXACT_AMOUNT_TOL:
        return False
    if abs(pr.vat_amount_bdt - sf.vat_amount_bdt) >= EXACT_AMOUNT_TOL:
        return False
    return True


def _try_fuzzy(pr: PurchaseRow, sf: SupplierRow) -> bool:
    if abs((pr.invoice_date - sf.invoice_date).days) > FUZZY_DATE_TOL_DAYS:
        return False
    pct = _amount_diff_pct(pr.taxable_amount_bdt, sf.taxable_amount_bdt)
    if pct > FUZZY_AMOUNT_TOL_PCT:
        return False
    return True


def match_one(pr: PurchaseRow, by_bin: dict[str, list[SupplierRow]]) -> MatchResult:
    """Match one purchase row against the indexed supplier pool."""
    if not pr.supplier_bin or pr.supplier_bin not in by_bin:
        return MatchResult(
            pr_row=pr, sf_row=None,
            status=MatchStatus.NO_MATCH, score=Decimal("0.00"),
            flags=DiscrepancyFlags(reason="supplier_bin_not_filed"),
        )

    pool = by_bin[pr.supplier_bin]
    pr_norm = normalize_invoice_no(pr.invoice_no)

    invoice_candidates = [s for s in pool if normalize_invoice_no(s.invoice_no) == pr_norm]

    # EXACT
    for sf in invoice_candidates:
        if _try_exact(pr, sf):
            return MatchResult(
                pr_row=pr, sf_row=sf,
                status=MatchStatus.EXACT, score=Decimal("1.00"),
            )

    # FUZZY
    for sf in invoice_candidates:
        if _try_fuzzy(pr, sf):
            days_off = abs((pr.invoice_date - sf.invoice_date).days)
            amount_diff = pr.taxable_amount_bdt - sf.taxable_amount_bdt
            return MatchResult(
                pr_row=pr, sf_row=sf,
                status=MatchStatus.FUZZY, score=Decimal("0.80"),
                flags=DiscrepancyFlags(
                    date_off_by_days=days_off,
                    amount_diff_bdt=amount_diff,
                    amount_diff_pct=_amount_diff_pct(
                        pr.taxable_amount_bdt, sf.taxable_amount_bdt),
                ),
            )

    # PARTIAL — bin matched but invoice did not
    return MatchResult(
        pr_row=pr, sf_row=None,
        status=MatchStatus.PARTIAL, score=Decimal("0.40"),
        flags=DiscrepancyFlags(reason="no_invoice_no_match"),
    )


def match_register(
    pr_rows: list[PurchaseRow],
    sf_rows: list[SupplierRow],
) -> list[MatchResult]:
    """Match every purchase row against the supplier pool."""
    by_bin = _index_supplier_pool(sf_rows)
    return [match_one(pr, by_bin) for pr in pr_rows]
```

- [ ] **Step 4: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_matcher.py -v
```

Expected: 9 passed. If `test_match_register_returns_one_result_per_purchase_row` fails on count assertions, adjust the conftest fixture so the BIN columns line up — the supplier export's `Buyer BIN` should match the purchase register's `Supplier BIN` for each match scenario. Both fixtures must be edited together so a row that matches uses the same BIN value on both sides.

> **Test fixture sanity check:** in the conftest, the purchase register row 1 has `supplier_bin = "123456789"` and the supplier export row 1 has `buyer_bin = "111222333"`. **These won't match.** Update the supplier export fixture to use `"123456789"` for row 1 (exact match) and `"987654321"` for row 2 (fuzzy match), and re-run.

If you needed to fix the fixture, re-run pytest and confirm 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconciliation/matcher.py backend/tests/reconciliation/test_matcher.py \
        backend/tests/reconciliation/conftest.py
git commit -m "feat(recon): four-tier matching engine (EXACT > FUZZY > PARTIAL > NO_MATCH)"
```

---

### Task C8: Aggregate computation

**Files:**
- Create: `backend/app/reconciliation/aggregates.py`
- Test: `backend/tests/reconciliation/test_aggregates.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for aggregate computation across match results."""
from datetime import date
from decimal import Decimal

from app.reconciliation.aggregates import aggregate
from app.reconciliation.schemas import (
    AggregatesDTO, DiscrepancyFlags, MatchResult, MatchStatus,
    PurchaseRow,
)


def _row(status: MatchStatus, vat: float = 100.0) -> MatchResult:
    return MatchResult(
        pr_row=PurchaseRow(
            invoice_no="X", supplier_bin="111", supplier_name=None,
            invoice_date=date(2024, 1, 1),
            taxable_amount_bdt=Decimal("0.00"),
            vat_amount_bdt=Decimal(str(vat)),
        ),
        sf_row=None,
        status=status,
        score=Decimal("0.00"),
        flags=DiscrepancyFlags(),
    )


def test_aggregate_counts_each_status():
    matches = [
        _row(MatchStatus.EXACT,    100),
        _row(MatchStatus.EXACT,    200),
        _row(MatchStatus.FUZZY,    150),
        _row(MatchStatus.PARTIAL,   50),
        _row(MatchStatus.NO_MATCH,  25),
    ]
    agg = aggregate(matches)
    assert isinstance(agg, AggregatesDTO)
    assert agg.total_invoices == 5
    assert agg.matched_exact == 2
    assert agg.matched_fuzzy == 1
    assert agg.partial_match == 1
    assert agg.no_match == 1


def test_aggregate_safe_itc_is_exact_plus_fuzzy_vat():
    matches = [
        _row(MatchStatus.EXACT, 100),
        _row(MatchStatus.FUZZY, 150),
        _row(MatchStatus.PARTIAL, 50),
        _row(MatchStatus.NO_MATCH, 25),
    ]
    agg = aggregate(matches)
    assert agg.safe_itc_bdt == Decimal("250.00")
    assert agg.at_risk_itc_bdt == Decimal("75.00")
    assert agg.total_vat_claimed_bdt == Decimal("325.00")


def test_aggregate_empty():
    agg = aggregate([])
    assert agg.total_invoices == 0
    assert agg.safe_itc_bdt == Decimal("0.00")
    assert agg.at_risk_itc_bdt == Decimal("0.00")
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_aggregates.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/reconciliation/aggregates.py`:

```python
"""Aggregate match results into headline numbers for the recon report."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .schemas import AggregatesDTO, MatchResult, MatchStatus

_SAFE = {MatchStatus.EXACT, MatchStatus.FUZZY}


def aggregate(matches: Iterable[MatchResult]) -> AggregatesDTO:
    matches = list(matches)
    total = len(matches)
    counts = {s: 0 for s in MatchStatus}
    safe = Decimal("0.00")
    at_risk = Decimal("0.00")

    for m in matches:
        counts[m.status] += 1
        if m.status in _SAFE:
            safe += m.pr_row.vat_amount_bdt
        else:
            at_risk += m.pr_row.vat_amount_bdt

    return AggregatesDTO(
        total_invoices=total,
        matched_exact=counts[MatchStatus.EXACT],
        matched_fuzzy=counts[MatchStatus.FUZZY],
        partial_match=counts[MatchStatus.PARTIAL],
        no_match=counts[MatchStatus.NO_MATCH],
        total_vat_claimed_bdt=safe + at_risk,
        safe_itc_bdt=safe,
        at_risk_itc_bdt=at_risk,
    )
```

- [ ] **Step 4: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_aggregates.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconciliation/aggregates.py backend/tests/reconciliation/test_aggregates.py
git commit -m "feat(recon): aggregate function for headline ITC numbers"
```

---

## Section 3 — Storage and persistence

### Task C9: Storage download helper

**Why:** The backend needs to fetch the XLSX bytes from Supabase Storage using the service-role key (RLS doesn't apply to service-role).

**Files:**
- Create: `backend/app/reconciliation/storage.py`
- Test: `backend/tests/reconciliation/test_storage.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the storage download helper."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import StorageDownloadFailedError
from app.reconciliation.storage import download_xlsx


@pytest.mark.asyncio
async def test_download_xlsx_returns_bytes(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.storage.from_.return_value.download.return_value = b"fake-xlsx-bytes"

    monkeypatch.setattr(
        "app.reconciliation.storage.get_supabase_admin",
        lambda: fake_supabase,
    )

    result = await download_xlsx("recon-files", "tenant/client/recon/file.xlsx")
    assert result == b"fake-xlsx-bytes"
    fake_supabase.storage.from_.assert_called_once_with("recon-files")
    fake_supabase.storage.from_.return_value.download.assert_called_once_with(
        "tenant/client/recon/file.xlsx"
    )


@pytest.mark.asyncio
async def test_download_xlsx_raises_on_error(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.storage.from_.return_value.download.side_effect = Exception("404 not found")

    monkeypatch.setattr(
        "app.reconciliation.storage.get_supabase_admin",
        lambda: fake_supabase,
    )

    with pytest.raises(StorageDownloadFailedError) as ei:
        await download_xlsx("recon-files", "missing/file.xlsx")
    assert "missing/file.xlsx" in ei.value.message
    assert "404 not found" in ei.value.details["reason"]
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_storage.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`backend/app/reconciliation/storage.py`:

```python
"""Supabase Storage helpers for reconciliation file downloads."""
from __future__ import annotations

import asyncio

from app.core.exceptions import StorageDownloadFailedError
from app.database import get_supabase_admin


async def download_xlsx(bucket: str, path: str) -> bytes:
    """Download a file from Supabase Storage as bytes (service-role)."""
    supabase = get_supabase_admin()

    def _call() -> bytes:
        return supabase.storage.from_(bucket).download(path)

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001 — re-raise typed
        raise StorageDownloadFailedError(path=path, reason=str(exc)) from exc
```

- [ ] **Step 4: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_storage.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconciliation/storage.py backend/tests/reconciliation/test_storage.py
git commit -m "feat(recon): Storage download helper using service-role"
```

---

### Task C10: Persistence — vat_reconciliations + bulk insert line items

**Why:** Once the matcher has produced results, the service needs to persist a header row (`vat_reconciliations`) and a batch of line items. Use a single SECURITY DEFINER RPC for atomicity (similar to the onboarding RPC pattern from `0009`).

**Files:**
- Create: `migrations/0012_persist_reconciliation_rpc.sql`
- Create: `backend/app/reconciliation/persistence.py`
- Test: `backend/tests/reconciliation/test_persistence.py`

- [ ] **Step 1: Write the migration**

```sql
-- 0012_persist_reconciliation_rpc.sql
-- Atomic write of one vat_reconciliations row + N recon_line_items rows.
-- SECURITY DEFINER so the backend (service-role) can call it without bypassing the audit
-- trigger semantics — actor user_id flows through `run_by` per migration 0010.

CREATE OR REPLACE FUNCTION public.persist_reconciliation(
  p_tenant_id              uuid,
  p_client_id              uuid,
  p_period_start           date,
  p_period_end             date,
  p_run_by                 uuid,
  p_pr_doc_id              uuid,
  p_sf_doc_id              uuid,
  p_total_invoices         integer,
  p_matched_exact          integer,
  p_matched_fuzzy          integer,
  p_partial_match          integer,
  p_no_match               integer,
  p_total_vat_claimed_bdt  numeric,
  p_safe_itc_bdt           numeric,
  p_at_risk_itc_bdt        numeric,
  p_line_items             jsonb           -- array of objects matching recon_line_items columns
)
RETURNS uuid                                -- the new reconciliation id
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_recon_id uuid;
BEGIN
  IF p_tenant_id IS NULL OR p_client_id IS NULL OR p_run_by IS NULL THEN
    RAISE EXCEPTION 'tenant_id, client_id, run_by are required' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.vat_reconciliations (
    tenant_id, client_id, period_start, period_end,
    status, total_invoices,
    matched_exact, matched_fuzzy, partial_match, no_match,
    total_vat_claimed_bdt, safe_itc_bdt, at_risk_itc_bdt,
    purchase_register_doc_id, supplier_data_doc_id,
    run_by, started_at, completed_at
  )
  VALUES (
    p_tenant_id, p_client_id, p_period_start, p_period_end,
    'completed', p_total_invoices,
    p_matched_exact, p_matched_fuzzy, p_partial_match, p_no_match,
    p_total_vat_claimed_bdt, p_safe_itc_bdt, p_at_risk_itc_bdt,
    p_pr_doc_id, p_sf_doc_id,
    p_run_by, now(), now()
  )
  RETURNING id INTO v_recon_id;

  -- Bulk insert line items from JSONB
  INSERT INTO public.recon_line_items (
    tenant_id, reconciliation_id,
    pr_invoice_no, pr_supplier_bin, pr_supplier_name, pr_invoice_date,
    pr_taxable_amount_bdt, pr_vat_amount_bdt,
    sf_invoice_no, sf_invoice_date, sf_taxable_amount_bdt, sf_vat_amount_bdt,
    match_status, match_score, discrepancy_flags
  )
  SELECT
    p_tenant_id, v_recon_id,
    item->>'pr_invoice_no',
    item->>'pr_supplier_bin',
    item->>'pr_supplier_name',
    (item->>'pr_invoice_date')::date,
    (item->>'pr_taxable_amount_bdt')::numeric,
    (item->>'pr_vat_amount_bdt')::numeric,
    item->>'sf_invoice_no',
    NULLIF(item->>'sf_invoice_date','')::date,
    NULLIF(item->>'sf_taxable_amount_bdt','')::numeric,
    NULLIF(item->>'sf_vat_amount_bdt','')::numeric,
    item->>'match_status',
    (item->>'match_score')::numeric,
    item->'discrepancy_flags'
  FROM jsonb_array_elements(p_line_items) AS item;

  RETURN v_recon_id;
END;
$$;

REVOKE ALL ON FUNCTION public.persist_reconciliation(
  uuid,uuid,date,date,uuid,uuid,uuid,integer,integer,integer,integer,integer,
  numeric,numeric,numeric,jsonb
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.persist_reconciliation(
  uuid,uuid,date,date,uuid,uuid,uuid,integer,integer,integer,integer,integer,
  numeric,numeric,numeric,jsonb
) TO service_role;
```

- [ ] **Step 2: Apply migration via Supabase MCP**

Apply with `name="0012_persist_reconciliation_rpc"`. Verify success.

- [ ] **Step 3: Write the failing persistence test**

`backend/tests/reconciliation/test_persistence.py`:

```python
"""Tests for the persistence layer."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.reconciliation.persistence import persist_reconciliation
from app.reconciliation.schemas import (
    AggregatesDTO, DiscrepancyFlags, MatchResult, MatchStatus, PurchaseRow,
)


def _match() -> MatchResult:
    return MatchResult(
        pr_row=PurchaseRow(
            invoice_no="INV-1", supplier_bin="111", supplier_name="X",
            invoice_date=date(2024, 1, 1),
            taxable_amount_bdt=Decimal("100"),
            vat_amount_bdt=Decimal("15"),
        ),
        sf_row=None,
        status=MatchStatus.NO_MATCH,
        score=Decimal("0.00"),
        flags=DiscrepancyFlags(reason="supplier_bin_not_filed"),
    )


@pytest.mark.asyncio
async def test_persist_reconciliation_calls_rpc(monkeypatch):
    new_id = uuid4()
    fake = MagicMock()
    fake.rpc.return_value.execute.return_value.data = str(new_id)

    monkeypatch.setattr(
        "app.reconciliation.persistence.get_supabase_admin",
        lambda: fake,
    )

    result = await persist_reconciliation(
        tenant_id=uuid4(),
        client_id=uuid4(),
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        run_by=uuid4(),
        pr_doc_id=uuid4(),
        sf_doc_id=uuid4(),
        aggregates=AggregatesDTO(
            total_invoices=1, matched_exact=0, matched_fuzzy=0,
            partial_match=0, no_match=1,
            total_vat_claimed_bdt=Decimal("15"),
            safe_itc_bdt=Decimal("0"),
            at_risk_itc_bdt=Decimal("15"),
        ),
        matches=[_match()],
    )

    assert str(result) == str(new_id)
    assert fake.rpc.call_args.args[0] == "persist_reconciliation"
    payload = fake.rpc.call_args.args[1]
    assert payload["p_total_invoices"] == 1
    assert payload["p_no_match"] == 1
    assert isinstance(payload["p_line_items"], list)
    assert payload["p_line_items"][0]["pr_invoice_no"] == "INV-1"
    assert payload["p_line_items"][0]["match_status"] == "no_match"
```

- [ ] **Step 4: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_persistence.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 5: Implement**

`backend/app/reconciliation/persistence.py`:

```python
"""Persist a completed reconciliation via the persist_reconciliation RPC."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Iterable
from uuid import UUID

from app.database import get_supabase_admin

from .schemas import AggregatesDTO, MatchResult


def _serialize_match(m: MatchResult) -> dict:
    pr = m.pr_row
    sf = m.sf_row
    return {
        "pr_invoice_no":         pr.invoice_no,
        "pr_supplier_bin":       pr.supplier_bin,
        "pr_supplier_name":      pr.supplier_name,
        "pr_invoice_date":       pr.invoice_date.isoformat(),
        "pr_taxable_amount_bdt": str(pr.taxable_amount_bdt),
        "pr_vat_amount_bdt":     str(pr.vat_amount_bdt),
        "sf_invoice_no":         sf.invoice_no if sf else None,
        "sf_invoice_date":       sf.invoice_date.isoformat() if sf else "",
        "sf_taxable_amount_bdt": str(sf.taxable_amount_bdt) if sf else "",
        "sf_vat_amount_bdt":     str(sf.vat_amount_bdt) if sf else "",
        "match_status":          m.status.value,
        "match_score":           str(m.score),
        "discrepancy_flags":     m.flags.model_dump(mode="json"),
    }


async def persist_reconciliation(
    *,
    tenant_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    run_by: UUID,
    pr_doc_id: UUID,
    sf_doc_id: UUID,
    aggregates: AggregatesDTO,
    matches: Iterable[MatchResult],
) -> UUID:
    """Calls the persist_reconciliation RPC. Returns the new reconciliation id."""
    supabase = get_supabase_admin()

    payload = {
        "p_tenant_id": str(tenant_id),
        "p_client_id": str(client_id),
        "p_period_start": period_start.isoformat(),
        "p_period_end": period_end.isoformat(),
        "p_run_by": str(run_by),
        "p_pr_doc_id": str(pr_doc_id),
        "p_sf_doc_id": str(sf_doc_id),
        "p_total_invoices": aggregates.total_invoices,
        "p_matched_exact": aggregates.matched_exact,
        "p_matched_fuzzy": aggregates.matched_fuzzy,
        "p_partial_match": aggregates.partial_match,
        "p_no_match": aggregates.no_match,
        "p_total_vat_claimed_bdt": str(aggregates.total_vat_claimed_bdt),
        "p_safe_itc_bdt": str(aggregates.safe_itc_bdt),
        "p_at_risk_itc_bdt": str(aggregates.at_risk_itc_bdt),
        "p_line_items": [_serialize_match(m) for m in matches],
    }

    def _call() -> str:
        return supabase.rpc("persist_reconciliation", payload).execute().data

    new_id = await asyncio.to_thread(_call)
    return UUID(str(new_id))
```

- [ ] **Step 6: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_persistence.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add migrations/0012_persist_reconciliation_rpc.sql \
        backend/app/reconciliation/persistence.py \
        backend/tests/reconciliation/test_persistence.py
git commit -m "feat(recon): persist_reconciliation RPC + Python wrapper"
```

---

## Section 4 — Service orchestration

### Task C11: Document tenant validation helper

**Why:** Defense in depth. The endpoint receives `purchase_register_doc_id` and `supplier_data_doc_id` from the (authenticated) frontend, but we still verify both rows belong to the calling user's tenant *and* the requested client before downloading anything.

**Files:**
- Create: `backend/app/reconciliation/access.py`
- Test: `backend/tests/reconciliation/test_access.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for cross-document tenant validation."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import DocumentNotFoundError, DocumentTenantMismatchError
from app.reconciliation.access import fetch_and_validate_documents


@pytest.mark.asyncio
async def test_returns_storage_paths_when_documents_belong_to_tenant_and_client(monkeypatch):
    tenant_id = uuid4()
    client_id = uuid4()
    pr_doc_id = uuid4()
    sf_doc_id = uuid4()

    fake = MagicMock()
    # supabase.table('documents').select(...).in_('id', [...]).execute().data = [...]
    fake.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": str(pr_doc_id), "tenant_id": str(tenant_id),
         "client_id": str(client_id), "storage_path": "recon-files/t/c/r/pr.xlsx",
         "doc_type": "purchase_register"},
        {"id": str(sf_doc_id), "tenant_id": str(tenant_id),
         "client_id": str(client_id), "storage_path": "recon-files/t/c/r/sf.xlsx",
         "doc_type": "supplier_export"},
    ]
    monkeypatch.setattr("app.reconciliation.access.get_supabase_admin", lambda: fake)

    paths = await fetch_and_validate_documents(
        pr_doc_id=pr_doc_id, sf_doc_id=sf_doc_id,
        tenant_id=tenant_id, client_id=client_id,
    )
    assert paths.pr_path == "recon-files/t/c/r/pr.xlsx"
    assert paths.sf_path == "recon-files/t/c/r/sf.xlsx"


@pytest.mark.asyncio
async def test_raises_when_doc_belongs_to_different_tenant(monkeypatch):
    tenant_id = uuid4()
    client_id = uuid4()
    other_tenant = uuid4()
    pr_doc_id = uuid4()
    sf_doc_id = uuid4()

    fake = MagicMock()
    fake.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": str(pr_doc_id), "tenant_id": str(other_tenant),
         "client_id": str(client_id), "storage_path": "x", "doc_type": "purchase_register"},
        {"id": str(sf_doc_id), "tenant_id": str(tenant_id),
         "client_id": str(client_id), "storage_path": "y", "doc_type": "supplier_export"},
    ]
    monkeypatch.setattr("app.reconciliation.access.get_supabase_admin", lambda: fake)

    with pytest.raises(DocumentTenantMismatchError):
        await fetch_and_validate_documents(
            pr_doc_id=pr_doc_id, sf_doc_id=sf_doc_id,
            tenant_id=tenant_id, client_id=client_id,
        )


@pytest.mark.asyncio
async def test_raises_when_doc_not_found(monkeypatch):
    tenant_id = uuid4()
    client_id = uuid4()
    pr_doc_id = uuid4()
    sf_doc_id = uuid4()

    fake = MagicMock()
    fake.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        # Only one of the two docs comes back
        {"id": str(pr_doc_id), "tenant_id": str(tenant_id),
         "client_id": str(client_id), "storage_path": "x", "doc_type": "purchase_register"},
    ]
    monkeypatch.setattr("app.reconciliation.access.get_supabase_admin", lambda: fake)

    with pytest.raises(DocumentNotFoundError):
        await fetch_and_validate_documents(
            pr_doc_id=pr_doc_id, sf_doc_id=sf_doc_id,
            tenant_id=tenant_id, client_id=client_id,
        )
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_access.py -v
```

- [ ] **Step 3: Implement**

`backend/app/reconciliation/access.py`:

```python
"""Defense-in-depth document access checks for the reconciliation flow."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from app.core.exceptions import DocumentNotFoundError, DocumentTenantMismatchError
from app.database import get_supabase_admin


@dataclass(frozen=True)
class DocumentPaths:
    pr_path: str
    sf_path: str


async def fetch_and_validate_documents(
    *,
    pr_doc_id: UUID,
    sf_doc_id: UUID,
    tenant_id: UUID,
    client_id: UUID,
) -> DocumentPaths:
    """Confirm both docs exist, belong to the tenant, and reference the same client."""
    supabase = get_supabase_admin()

    def _query():
        return (
            supabase.table("documents")
            .select("id,tenant_id,client_id,storage_path,doc_type")
            .in_("id", [str(pr_doc_id), str(sf_doc_id)])
            .execute()
        )

    result = await asyncio.to_thread(_query)
    rows = result.data or []
    by_id = {row["id"]: row for row in rows}

    pr = by_id.get(str(pr_doc_id))
    sf = by_id.get(str(sf_doc_id))

    if pr is None:
        raise DocumentNotFoundError(doc_id=str(pr_doc_id))
    if sf is None:
        raise DocumentNotFoundError(doc_id=str(sf_doc_id))

    for row in (pr, sf):
        if row["tenant_id"] != str(tenant_id):
            raise DocumentTenantMismatchError(document_id=row["id"])
        if row["client_id"] != str(client_id):
            raise DocumentTenantMismatchError(document_id=row["id"])

    return DocumentPaths(pr_path=pr["storage_path"], sf_path=sf["storage_path"])
```

- [ ] **Step 4: Run, verify pass**

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconciliation/access.py backend/tests/reconciliation/test_access.py
git commit -m "feat(recon): defense-in-depth document tenant/client validation"
```

---

### Task C12: Reconciliation service (orchestrator)

**Files:**
- Create: `backend/app/reconciliation/service.py`
- Test: `backend/tests/reconciliation/test_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""End-to-end orchestration test with mocked storage + persistence."""
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.reconciliation.service import run_reconciliation
from app.reconciliation.schemas import ReconciliationCreateRequest


@pytest.mark.asyncio
async def test_run_reconciliation_full_pipeline(
    monkeypatch,
    valid_purchase_register_bytes: bytes,
    valid_supplier_export_bytes: bytes,
):
    tenant_id = uuid4()
    user_id = uuid4()
    client_id = uuid4()
    pr_doc_id = uuid4()
    sf_doc_id = uuid4()
    new_recon_id = uuid4()

    # Mock document validation → returns paths
    async def _fake_validate(**kwargs):
        from app.reconciliation.access import DocumentPaths
        return DocumentPaths(pr_path="t/c/r/pr.xlsx", sf_path="t/c/r/sf.xlsx")
    monkeypatch.setattr(
        "app.reconciliation.service.fetch_and_validate_documents",
        _fake_validate,
    )

    # Mock storage downloads → return our fixture bytes
    async def _fake_download(bucket: str, path: str) -> bytes:
        return (valid_purchase_register_bytes if "pr" in path
                else valid_supplier_export_bytes)
    monkeypatch.setattr(
        "app.reconciliation.service.download_xlsx",
        _fake_download,
    )

    # Mock persistence → return new id
    captured = {}
    async def _fake_persist(**kwargs):
        captured.update(kwargs)
        return new_recon_id
    monkeypatch.setattr(
        "app.reconciliation.service.persist_reconciliation",
        _fake_persist,
    )

    req = ReconciliationCreateRequest(
        client_id=client_id,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        purchase_register_doc_id=pr_doc_id,
        supplier_data_doc_id=sf_doc_id,
    )

    result = await run_reconciliation(req, tenant_id=tenant_id, user_id=user_id)
    assert result == new_recon_id
    assert captured["aggregates"].total_invoices == 3
    # 3 line items captured
    assert len(list(captured["matches"])) == 3
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_service.py -v
```

- [ ] **Step 3: Implement**

`backend/app/reconciliation/service.py`:

```python
"""Reconciliation orchestrator: validate → download → parse → match → persist."""
from __future__ import annotations

import structlog
from uuid import UUID

from .access import fetch_and_validate_documents
from .aggregates import aggregate
from .matcher import match_register
from .parser import parse_purchase_register, parse_supplier_export
from .persistence import persist_reconciliation
from .schemas import ReconciliationCreateRequest
from .storage import download_xlsx

logger = structlog.get_logger()
BUCKET = "recon-files"


async def run_reconciliation(
    req: ReconciliationCreateRequest,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> UUID:
    log = logger.bind(
        tenant_id=str(tenant_id),
        client_id=str(req.client_id),
        user_id=str(user_id),
    )

    # 1. Defense in depth — both docs belong to caller's tenant and client
    paths = await fetch_and_validate_documents(
        pr_doc_id=req.purchase_register_doc_id,
        sf_doc_id=req.supplier_data_doc_id,
        tenant_id=tenant_id,
        client_id=req.client_id,
    )
    log.info("recon.docs_validated")

    # 2. Download both files (parallel via asyncio.gather)
    import asyncio
    pr_bytes, sf_bytes = await asyncio.gather(
        download_xlsx(BUCKET, paths.pr_path),
        download_xlsx(BUCKET, paths.sf_path),
    )
    log.info("recon.storage_downloaded",
             pr_bytes=len(pr_bytes), sf_bytes=len(sf_bytes))

    # 3. Parse + match (CPU-bound; offload via to_thread to avoid blocking the loop)
    def _process():
        pr_rows = parse_purchase_register(pr_bytes)
        sf_rows = parse_supplier_export(sf_bytes)
        matches = match_register(pr_rows, sf_rows)
        agg = aggregate(matches)
        return matches, agg

    matches, agg = await asyncio.to_thread(_process)
    log.info(
        "recon.matched",
        total=agg.total_invoices,
        exact=agg.matched_exact, fuzzy=agg.matched_fuzzy,
        partial=agg.partial_match, no_match=agg.no_match,
        safe_itc_bdt=str(agg.safe_itc_bdt),
        at_risk_itc_bdt=str(agg.at_risk_itc_bdt),
    )

    # 4. Persist
    recon_id = await persist_reconciliation(
        tenant_id=tenant_id,
        client_id=req.client_id,
        period_start=req.period_start,
        period_end=req.period_end,
        run_by=user_id,
        pr_doc_id=req.purchase_register_doc_id,
        sf_doc_id=req.supplier_data_doc_id,
        aggregates=agg,
        matches=matches,
    )
    log.info("recon.persisted", reconciliation_id=str(recon_id))
    return recon_id
```

- [ ] **Step 4: Run, verify pass**

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/reconciliation/service.py backend/tests/reconciliation/test_service.py
git commit -m "feat(recon): orchestrator service that runs the full pipeline"
```

---

## Section 5 — API endpoint and export

### Task C13: POST /api/v1/reconciliations endpoint

**Files:**
- Create: `backend/app/reconciliation/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/reconciliation/test_router.py`

- [ ] **Step 1: Write the failing test**

```python
"""Endpoint contract tests for POST /api/v1/reconciliations."""
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.reconciliation.router as router_module
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _bypass_auth(monkeypatch, tenant_id, user_id):
    async def _fake_user_id():
        return user_id
    async def _fake_tenant_id():
        return tenant_id

    from app import dependencies as deps
    app.dependency_overrides[deps.get_current_user_id] = _fake_user_id
    app.dependency_overrides[deps.get_current_tenant_id] = _fake_tenant_id


def test_post_reconciliation_returns_id(monkeypatch, client):
    tenant_id = uuid4()
    user_id = uuid4()
    new_id = uuid4()

    _bypass_auth(monkeypatch, tenant_id, user_id)

    async def _fake_run(req, *, tenant_id, user_id):
        return new_id
    monkeypatch.setattr(router_module, "run_reconciliation", _fake_run)

    body = {
        "client_id": str(uuid4()),
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "purchase_register_doc_id": str(uuid4()),
        "supplier_data_doc_id": str(uuid4()),
    }
    res = client.post("/api/v1/reconciliations", json=body,
                      headers={"Authorization": "Bearer fake"})
    assert res.status_code == 201, res.text
    assert res.json()["reconciliation_id"] == str(new_id)

    app.dependency_overrides.clear()


def test_post_reconciliation_400_on_inverted_period(client):
    body = {
        "client_id": str(uuid4()),
        "period_start": "2024-02-01",
        "period_end": "2024-01-01",
        "purchase_register_doc_id": str(uuid4()),
        "supplier_data_doc_id": str(uuid4()),
    }
    # No auth override needed — the request body fails validation before deps run
    res = client.post("/api/v1/reconciliations", json=body,
                      headers={"Authorization": "Bearer fake"})
    assert res.status_code == 422
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_router.py -v
```

- [ ] **Step 3: Implement the router**

`backend/app/reconciliation/router.py`:

```python
"""Reconciliation API endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies import get_current_tenant_id, get_current_user_id

from .schemas import ReconciliationCreateRequest, ReconciliationCreateResponse
from .service import run_reconciliation

router = APIRouter(prefix="/api/v1/reconciliations", tags=["reconciliation"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ReconciliationCreateResponse,
)
async def create_reconciliation(
    body: ReconciliationCreateRequest,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> ReconciliationCreateResponse:
    """Run a synchronous VAT reconciliation. Returns the new reconciliation id."""
    new_id = await run_reconciliation(body, tenant_id=tenant_id, user_id=user_id)
    return ReconciliationCreateResponse(reconciliation_id=new_id)
```

- [ ] **Step 4: Wire it into the app**

Modify `backend/app/main.py` — find the line that calls `app.add_middleware(CORSMiddleware, ...)` and add (anywhere after `app = FastAPI(...)`):

```python
    from app.reconciliation.router import router as reconciliation_router
    app.include_router(reconciliation_router)
```

Place it directly after the `# ── Health Checks ─────────────` block but before `return app`.

- [ ] **Step 5: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_router.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/reconciliation/router.py backend/app/main.py \
        backend/tests/reconciliation/test_router.py
git commit -m "feat(api): POST /api/v1/reconciliations endpoint wired into app"
```

---

### Task C14: XLSX export endpoint

**Why:** "Export to XLSX" button on the report screen needs a backend endpoint that regenerates a spreadsheet from the persisted line items.

**Files:**
- Create: `backend/app/reconciliation/exporter.py`
- Modify: `backend/app/reconciliation/router.py`
- Test: `backend/tests/reconciliation/test_exporter.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/reconciliation/test_exporter.py`:

```python
"""Tests for the XLSX exporter."""
import io
from unittest.mock import MagicMock
from uuid import uuid4

import openpyxl
import pytest

from app.core.exceptions import HishabError
from app.reconciliation.exporter import export_recon_to_xlsx


@pytest.mark.asyncio
async def test_export_returns_xlsx_with_expected_sheets(monkeypatch):
    tenant_id = uuid4()
    recon_id = uuid4()

    fake = MagicMock()

    def _table(name):
        m = MagicMock()
        if name == "vat_reconciliations":
            m.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "id": str(recon_id), "tenant_id": str(tenant_id),
                "client_id": str(uuid4()),
                "period_start": "2024-01-01", "period_end": "2024-01-31",
                "total_invoices": 3, "matched_exact": 1, "matched_fuzzy": 1,
                "partial_match": 0, "no_match": 1,
                "total_vat_claimed_bdt": "325.00", "safe_itc_bdt": "250.00",
                "at_risk_itc_bdt": "75.00",
            }
        elif name == "recon_line_items":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"pr_invoice_no": "INV-1", "pr_supplier_bin": "111",
                 "pr_supplier_name": "X", "pr_invoice_date": "2024-01-15",
                 "pr_taxable_amount_bdt": "1000.00", "pr_vat_amount_bdt": "150.00",
                 "sf_invoice_no": "INV-1", "sf_invoice_date": "2024-01-15",
                 "sf_taxable_amount_bdt": "1000.00", "sf_vat_amount_bdt": "150.00",
                 "match_status": "exact", "match_score": "1.00",
                 "discrepancy_flags": {}, "ca_override": None, "ca_notes": None},
            ]
        return m

    fake.table.side_effect = _table
    monkeypatch.setattr("app.reconciliation.exporter.get_supabase_admin", lambda: fake)

    raw = await export_recon_to_xlsx(reconciliation_id=recon_id, tenant_id=tenant_id)
    assert isinstance(raw, bytes)
    assert raw[:2] == b"PK"  # ZIP magic — every XLSX is a zip

    wb = openpyxl.load_workbook(io.BytesIO(raw))
    assert "Summary" in wb.sheetnames
    assert "Line Items" in wb.sheetnames

    summary = wb["Summary"]
    assert summary["A1"].value == "VAT Reconciliation Report"


@pytest.mark.asyncio
async def test_export_404_when_recon_not_found(monkeypatch):
    fake = MagicMock()
    fake.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    monkeypatch.setattr("app.reconciliation.exporter.get_supabase_admin", lambda: fake)

    with pytest.raises(HishabError) as ei:
        await export_recon_to_xlsx(reconciliation_id=uuid4(), tenant_id=uuid4())
    assert ei.value.code == "RECONCILIATION_NOT_FOUND"
```

- [ ] **Step 2: Add the missing error class**

In `backend/app/core/exceptions.py`, append:

```python
class ReconciliationNotFoundError(HishabError):
    def __init__(self, reconciliation_id: str = "") -> None:
        msg = f"Reconciliation {reconciliation_id} not found" if reconciliation_id else "Reconciliation not found"
        super().__init__("RECONCILIATION_NOT_FOUND", msg, status_code=404)
```

- [ ] **Step 3: Run test to verify fail**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/test_exporter.py -v
```

- [ ] **Step 4: Implement the exporter**

`backend/app/reconciliation/exporter.py`:

```python
"""XLSX export of a completed reconciliation."""
from __future__ import annotations

import asyncio
import io
from uuid import UUID

import openpyxl
from openpyxl.styles import Font, PatternFill

from app.core.exceptions import ReconciliationNotFoundError
from app.database import get_supabase_admin

_FILL_BY_STATUS = {
    "exact":    PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
    "fuzzy":    PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
    "partial":  PatternFill(start_color="FFC78F", end_color="FFC78F", fill_type="solid"),
    "no_match": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
}


async def export_recon_to_xlsx(
    *, reconciliation_id: UUID, tenant_id: UUID,
) -> bytes:
    supabase = get_supabase_admin()

    def _fetch():
        recon = supabase.table("vat_reconciliations").select("*") \
            .eq("id", str(reconciliation_id)) \
            .eq("tenant_id", str(tenant_id)) \
            .single().execute().data
        items = supabase.table("recon_line_items").select("*") \
            .eq("reconciliation_id", str(reconciliation_id)) \
            .eq("tenant_id", str(tenant_id)) \
            .execute().data or []
        return recon, items

    recon, items = await asyncio.to_thread(_fetch)
    if recon is None:
        raise ReconciliationNotFoundError(reconciliation_id=str(reconciliation_id))

    wb = openpyxl.Workbook()

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "VAT Reconciliation Report"
    ws["A1"].font = Font(bold=True, size=14)
    rows = [
        ("Period",                 f"{recon['period_start']} → {recon['period_end']}"),
        ("Total invoices",         recon["total_invoices"]),
        ("Exact matches",          recon["matched_exact"]),
        ("Fuzzy matches",          recon["matched_fuzzy"]),
        ("Partial matches",        recon["partial_match"]),
        ("No matches",             recon["no_match"]),
        ("Safe ITC (BDT)",         recon["safe_itc_bdt"]),
        ("At-risk ITC (BDT)",      recon["at_risk_itc_bdt"]),
        ("Total VAT claimed (BDT)", recon["total_vat_claimed_bdt"]),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws.cell(row=i, column=2, value=v)

    # Line items sheet
    ws2 = wb.create_sheet("Line Items")
    headers = [
        "PR Invoice No", "PR Supplier BIN", "PR Supplier Name", "PR Invoice Date",
        "PR Taxable (BDT)", "PR VAT (BDT)",
        "SF Invoice No", "SF Invoice Date", "SF Taxable (BDT)", "SF VAT (BDT)",
        "Match Status", "Match Score", "CA Override", "CA Notes",
    ]
    ws2.append(headers)
    for cell in ws2[1]:
        cell.font = Font(bold=True)

    for item in items:
        ws2.append([
            item["pr_invoice_no"], item["pr_supplier_bin"], item["pr_supplier_name"],
            item["pr_invoice_date"],
            item["pr_taxable_amount_bdt"], item["pr_vat_amount_bdt"],
            item["sf_invoice_no"], item["sf_invoice_date"],
            item["sf_taxable_amount_bdt"], item["sf_vat_amount_bdt"],
            item["match_status"], item["match_score"],
            item.get("ca_override"), item.get("ca_notes"),
        ])
        # Color the row by match status
        fill = _FILL_BY_STATUS.get(item["match_status"])
        if fill:
            for cell in ws2[ws2.max_row]:
                cell.fill = fill

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: Add the export endpoint to the router**

Append to `backend/app/reconciliation/router.py`:

```python
from fastapi.responses import StreamingResponse

from .exporter import export_recon_to_xlsx


@router.get("/{reconciliation_id}/export")
async def export_reconciliation(
    reconciliation_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> StreamingResponse:
    raw = await export_recon_to_xlsx(
        reconciliation_id=reconciliation_id, tenant_id=tenant_id,
    )
    headers = {
        "Content-Disposition":
            f'attachment; filename="recon-{reconciliation_id}.xlsx"',
    }
    return StreamingResponse(
        iter([raw]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
```

- [ ] **Step 6: Run, verify pass**

```bash
.venv/Scripts/python.exe -m pytest tests/reconciliation/ -v
```

Expected: all tests in the reconciliation directory pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/reconciliation/exporter.py backend/app/reconciliation/router.py \
        backend/app/core/exceptions.py backend/tests/reconciliation/test_exporter.py
git commit -m "feat(api): GET /api/v1/reconciliations/{id}/export returns colored XLSX"
```

---

## Section 6 — Frontend foundations

### Task C15: Axios API client + auth interceptor

**Files:**
- Create: `frontend/src/lib/api.ts`
- Test: skip — pure wiring, validated via integration in Task C20.

- [ ] **Step 1: Create the file**

`frontend/src/lib/api.ts`:

```typescript
import axios from "axios"

import { env } from "./env"
import { supabase } from "./supabase"

export const api = axios.create({
  baseURL: env.VITE_API_URL,
  timeout: 30_000,  // recon takes up to ~3s for 1500 rows; 30s is generous headroom
})

// Attach the user's Supabase JWT to every request
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Surface backend HishabError shape to callers
export interface HishabApiError {
  code: string
  message: string
  details?: Record<string, unknown>
}

export function isHishabApiError(value: unknown): value is HishabApiError {
  return (
    typeof value === "object" && value !== null &&
    "code" in value && "message" in value
  )
}

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const payload = err?.response?.data?.error
    if (isHishabApiError(payload)) {
      // Reject with the structured error shape so React Query can read .message / .code
      return Promise.reject(payload)
    }
    return Promise.reject(err)
  },
)
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): axios client with Supabase JWT auth + error shape"
```

---

### Task C16: Reconciliation types + Zod schemas

**Files:**
- Create: `frontend/src/types/reconciliation.ts`
- Test: `frontend/src/types/__tests__/reconciliation.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, expect, it } from "vitest"

import {
  reconCreateSchema,
  matchStatusEnum,
  caOverrideEnum,
} from "@/types/reconciliation"

describe("reconCreateSchema", () => {
  const valid = {
    clientId: "11111111-1111-1111-1111-111111111111",
    periodStart: "2024-01-01",
    periodEnd: "2024-01-31",
    purchaseRegisterDocId: "22222222-2222-2222-2222-222222222222",
    supplierDataDocId: "33333333-3333-3333-3333-333333333333",
  }

  it("accepts a valid payload", () => {
    expect(reconCreateSchema.parse(valid)).toEqual(valid)
  })

  it("rejects inverted periods", () => {
    const r = reconCreateSchema.safeParse({
      ...valid, periodStart: "2024-02-01", periodEnd: "2024-01-01",
    })
    expect(r.success).toBe(false)
  })

  it("rejects non-uuid client id", () => {
    const r = reconCreateSchema.safeParse({ ...valid, clientId: "not-a-uuid" })
    expect(r.success).toBe(false)
  })
})

describe("enums", () => {
  it("exposes the four match statuses", () => {
    expect(matchStatusEnum.options).toEqual(["exact", "fuzzy", "partial", "no_match"])
  })
  it("exposes the three override values", () => {
    expect(caOverrideEnum.options).toEqual(["approved", "disputed", "ignore"])
  })
})
```

- [ ] **Step 2: Run, verify fail**

```bash
cd frontend
npm run test -- --run src/types/__tests__/reconciliation.test.ts
```

- [ ] **Step 3: Implement**

`frontend/src/types/reconciliation.ts`:

```typescript
import { z } from "zod"

export const matchStatusEnum = z.enum(["exact", "fuzzy", "partial", "no_match"])
export type MatchStatus = z.infer<typeof matchStatusEnum>

export const caOverrideEnum = z.enum(["approved", "disputed", "ignore"])
export type CAOverride = z.infer<typeof caOverrideEnum>

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD")

export const reconCreateSchema = z.object({
  clientId: z.string().uuid(),
  periodStart: isoDate,
  periodEnd: isoDate,
  purchaseRegisterDocId: z.string().uuid(),
  supplierDataDocId: z.string().uuid(),
}).refine(
  (v) => v.periodStart <= v.periodEnd,
  { message: "periodEnd must be on or after periodStart", path: ["periodEnd"] },
)

export type ReconCreateInput = z.infer<typeof reconCreateSchema>

export interface VatReconciliation {
  id: string
  tenant_id: string
  client_id: string
  period_start: string
  period_end: string
  status: "running" | "completed" | "error"
  total_invoices: number
  matched_exact: number
  matched_fuzzy: number
  partial_match: number
  no_match: number
  total_vat_claimed_bdt: string
  safe_itc_bdt: string
  at_risk_itc_bdt: string
  purchase_register_doc_id: string
  supplier_data_doc_id: string
  run_by: string
  started_at: string
  completed_at: string | null
}

export interface ReconLineItem {
  id: string
  reconciliation_id: string
  pr_invoice_no: string | null
  pr_supplier_bin: string | null
  pr_supplier_name: string | null
  pr_invoice_date: string | null
  pr_taxable_amount_bdt: string | null
  pr_vat_amount_bdt: string | null
  sf_invoice_no: string | null
  sf_invoice_date: string | null
  sf_taxable_amount_bdt: string | null
  sf_vat_amount_bdt: string | null
  match_status: MatchStatus
  match_score: string
  discrepancy_flags: Record<string, unknown> | null
  ca_override: CAOverride | null
  ca_notes: string | null
  created_at: string
}
```

- [ ] **Step 4: Run, verify pass**

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/reconciliation.ts \
        frontend/src/types/__tests__/reconciliation.test.ts
git commit -m "feat(frontend): reconciliation types + Zod schemas"
```

---

### Task C17: Storage upload helper

**Files:**
- Create: `frontend/src/lib/storage.ts`
- Test: skipped — wraps Supabase SDK; will be exercised manually in Task C20.

- [ ] **Step 1: Implement**

`frontend/src/lib/storage.ts`:

```typescript
import { supabase } from "./supabase"

export type DocType = "purchase_register" | "supplier_export" | "recon_export" | "other"

export interface UploadOptions {
  tenantId: string
  clientId: string
  reconUuid: string
  docType: DocType
  file: File
  uploadedBy: string
}

export interface UploadResult {
  storage_path: string
  document_id: string
}

const BUCKET = "recon-files"

/**
 * Uploads a file to Supabase Storage and inserts a corresponding `documents` row.
 * Returns the storage path and the new document id.
 *
 * Path layout: `{tenantId}/{clientId}/{reconUuid}/{docType}.xlsx`
 * RLS on the bucket only allows users in the same tenant (path[0]) to access it.
 */
export async function uploadReconFile(opts: UploadOptions): Promise<UploadResult> {
  const ext = opts.file.name.split(".").pop() ?? "xlsx"
  const filename = `${opts.docType}.${ext}`
  const path = `${opts.tenantId}/${opts.clientId}/${opts.reconUuid}/${filename}`

  const { error: upErr } = await supabase.storage
    .from(BUCKET)
    .upload(path, opts.file, { upsert: true, contentType: opts.file.type })
  if (upErr) throw new Error(`Upload failed: ${upErr.message}`)

  const { data: docRow, error: docErr } = await supabase
    .from("documents")
    .insert({
      tenant_id: opts.tenantId,
      client_id: opts.clientId,
      original_filename: opts.file.name,
      storage_path: path,
      file_size_bytes: opts.file.size,
      mime_type: opts.file.type,
      doc_type: opts.docType,
      uploaded_by: opts.uploadedBy,
    })
    .select("id")
    .single()

  if (docErr || !docRow) {
    // Best-effort: delete the storage object if the DB insert failed
    await supabase.storage.from(BUCKET).remove([path])
    throw new Error(`Document row insert failed: ${docErr?.message ?? "unknown"}`)
  }

  return { storage_path: path, document_id: docRow.id }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/storage.ts
git commit -m "feat(frontend): Supabase Storage upload helper for recon files"
```

---

### Task C18: useReconciliations hooks

**Files:**
- Create: `frontend/src/hooks/useReconciliations.ts`

- [ ] **Step 1: Implement**

`frontend/src/hooks/useReconciliations.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { supabase } from "@/lib/supabase"
import type {
  CAOverride,
  ReconCreateInput,
  ReconLineItem,
  VatReconciliation,
} from "@/types/reconciliation"

export const reconKeys = {
  all: ["reconciliations"] as const,
  byClient: (clientId: string) => ["reconciliations", "byClient", clientId] as const,
  one: (reconId: string) => ["reconciliations", "one", reconId] as const,
  lineItems: (reconId: string) => ["reconciliations", "lineItems", reconId] as const,
}

export function useReconList(clientId: string | undefined) {
  return useQuery({
    enabled: Boolean(clientId),
    queryKey: clientId ? reconKeys.byClient(clientId) : reconKeys.all,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("vat_reconciliations")
        .select("*")
        .eq("client_id", clientId!)
        .order("started_at", { ascending: false })
      if (error) throw error
      return (data ?? []) as VatReconciliation[]
    },
  })
}

export function useRecon(reconId: string | undefined) {
  return useQuery({
    enabled: Boolean(reconId),
    queryKey: reconId ? reconKeys.one(reconId) : reconKeys.all,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("vat_reconciliations")
        .select("*")
        .eq("id", reconId!)
        .single()
      if (error) throw error
      return data as VatReconciliation
    },
  })
}

export function useReconLineItems(reconId: string | undefined) {
  return useQuery({
    enabled: Boolean(reconId),
    queryKey: reconId ? reconKeys.lineItems(reconId) : reconKeys.all,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("recon_line_items")
        .select("*")
        .eq("reconciliation_id", reconId!)
        .order("created_at", { ascending: true })
      if (error) throw error
      return (data ?? []) as ReconLineItem[]
    },
  })
}

export function useRunReconciliation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: ReconCreateInput): Promise<{ reconciliation_id: string }> => {
      const res = await api.post("/api/v1/reconciliations", {
        client_id: input.clientId,
        period_start: input.periodStart,
        period_end: input.periodEnd,
        purchase_register_doc_id: input.purchaseRegisterDocId,
        supplier_data_doc_id: input.supplierDataDocId,
      })
      return res.data
    },
    onSuccess: (_data, input) => {
      qc.invalidateQueries({ queryKey: reconKeys.byClient(input.clientId) })
    },
  })
}

export function useUpdateLineItemOverride() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (args: {
      lineItemId: string
      reconciliationId: string
      override: CAOverride | null
      notes?: string | null
    }) => {
      const { error } = await supabase
        .from("recon_line_items")
        .update({ ca_override: args.override, ca_notes: args.notes ?? null })
        .eq("id", args.lineItemId)
      if (error) throw error
    },
    onSuccess: (_d, args) => {
      qc.invalidateQueries({ queryKey: reconKeys.lineItems(args.reconciliationId) })
    },
  })
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useReconciliations.ts
git commit -m "feat(frontend): TanStack Query hooks for recon list/get/run/override"
```

---

## Section 7 — Recon Upload UI

### Task C19: FileDropzone + PeriodPicker components

**Files:**
- Create: `frontend/src/components/recon/FileDropzone.tsx`
- Create: `frontend/src/components/recon/PeriodPicker.tsx`

- [ ] **Step 1: Implement FileDropzone**

`frontend/src/components/recon/FileDropzone.tsx`:

```typescript
import { useRef, useState } from "react"

import { Button } from "@/components/ui/button"

interface Props {
  label: string
  onFileSelected: (file: File) => void
  acceptedExt?: string[]   // e.g. [".xlsx", ".xls"]
  selected?: File | null
}

export function FileDropzone({
  label, onFileSelected, acceptedExt = [".xlsx"], selected,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const accept = acceptedExt.join(",")

  function handleFiles(files: FileList | null) {
    const f = files?.[0]
    if (!f) return
    const ok = acceptedExt.some((e) => f.name.toLowerCase().endsWith(e))
    if (!ok) return
    onFileSelected(f)
  }

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
        dragOver ? "border-slate-900 bg-slate-50" : "border-slate-300"
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        handleFiles(e.dataTransfer.files)
      }}
    >
      <p className="text-sm font-medium text-slate-700">{label}</p>
      <p className="text-xs text-slate-500 mt-1">
        {selected ? selected.name : `Drop ${acceptedExt.join(" or ")}, or click below`}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-3"
        onClick={() => inputRef.current?.click()}
      >
        {selected ? "Replace file" : "Choose file"}
      </Button>
    </div>
  )
}
```

- [ ] **Step 2: Implement PeriodPicker**

`frontend/src/components/recon/PeriodPicker.tsx`:

```typescript
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface Props {
  periodStart: string
  periodEnd: string
  onChange: (start: string, end: string) => void
}

/**
 * Picks first-of-month / end-of-month for a given period.
 * The CA picks the first month for `periodStart` and the last month for `periodEnd`;
 * we automatically resolve to YYYY-MM-01 / YYYY-MM-(last day).
 */
export function PeriodPicker({ periodStart, periodEnd, onChange }: Props) {
  function lastDay(yyyymm: string): string {
    if (!/^\d{4}-\d{2}$/.test(yyyymm)) return ""
    const [y, m] = yyyymm.split("-").map(Number)
    const d = new Date(y, m, 0).getDate()
    return `${yyyymm}-${String(d).padStart(2, "0")}`
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="space-y-1">
        <Label htmlFor="period-start">Period start (month)</Label>
        <Input
          id="period-start"
          type="month"
          value={periodStart.slice(0, 7)}
          onChange={(e) => {
            const start = e.target.value ? `${e.target.value}-01` : ""
            onChange(start, periodEnd)
          }}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="period-end">Period end (month)</Label>
        <Input
          id="period-end"
          type="month"
          value={periodEnd.slice(0, 7)}
          onChange={(e) => {
            const end = e.target.value ? lastDay(e.target.value) : ""
            onChange(periodStart, end)
          }}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recon/FileDropzone.tsx \
        frontend/src/components/recon/PeriodPicker.tsx
git commit -m "feat(frontend): FileDropzone and PeriodPicker recon components"
```

---

### Task C20: ReconNew page + sample template downloads

**Files:**
- Create: `frontend/public/templates/purchase_register_template.xlsx` (generated; see step 1)
- Create: `frontend/public/templates/supplier_export_template.xlsx`
- Create: `frontend/src/pages/ReconNew.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Generate the sample templates**

Run from the project root:

```bash
.venv/Scripts/python.exe - <<'EOF'
import io, openpyxl, os
from datetime import date

os.makedirs("frontend/public/templates", exist_ok=True)

def write(headers, sample, path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for s in sample:
        ws.append(s)
    wb.save(path)

write(
  headers=["Invoice No","Supplier BIN","Supplier Name","Invoice Date","Taxable Amount (BDT)","VAT Amount (BDT)"],
  sample=[["INV-0001","123456789","Acme Ltd",date(2024,1,15),1000.00,150.00]],
  path="frontend/public/templates/purchase_register_template.xlsx",
)

write(
  headers=["Invoice No","Invoice Date","Taxable Amount (BDT)","VAT Amount (BDT)","Buyer BIN"],
  sample=[["INV-0001",date(2024,1,15),1000.00,150.00,"987654321"]],
  path="frontend/public/templates/supplier_export_template.xlsx",
)
print("templates written")
EOF
```

(Use `cd backend` then `.venv/Scripts/python.exe -` if running from backend dir; otherwise activate the venv.)

- [ ] **Step 2: Implement the ReconNew page**

`frontend/src/pages/ReconNew.tsx`:

```typescript
import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { FileDropzone } from "@/components/recon/FileDropzone"
import { PeriodPicker } from "@/components/recon/PeriodPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useUserProfile } from "@/hooks/useUserProfile"
import { useRunReconciliation } from "@/hooks/useReconciliations"
import { uploadReconFile } from "@/lib/storage"
import { useAuthStore } from "@/store/auth"

export function ReconNew() {
  const { id: clientId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const { data: profile } = useUserProfile()
  const runRecon = useRunReconciliation()

  const [pr, setPr] = useState<File | null>(null)
  const [sf, setSf] = useState<File | null>(null)
  const [periodStart, setPeriodStart] = useState("")
  const [periodEnd, setPeriodEnd] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit() {
    if (!clientId || !user || !profile?.tenant_id) return
    if (!pr || !sf) {
      toast.error("Please upload both XLSX files.")
      return
    }
    if (!periodStart || !periodEnd) {
      toast.error("Pick the period.")
      return
    }

    setSubmitting(true)
    const reconUuid = crypto.randomUUID()

    try {
      const [prUp, sfUp] = await Promise.all([
        uploadReconFile({
          tenantId: profile.tenant_id, clientId, reconUuid,
          docType: "purchase_register", file: pr, uploadedBy: user.id,
        }),
        uploadReconFile({
          tenantId: profile.tenant_id, clientId, reconUuid,
          docType: "supplier_export", file: sf, uploadedBy: user.id,
        }),
      ])

      const result = await runRecon.mutateAsync({
        clientId,
        periodStart,
        periodEnd,
        purchaseRegisterDocId: prUp.document_id,
        supplierDataDocId: sfUp.document_id,
      })

      toast.success("Reconciliation complete.")
      navigate(`/clients/${clientId}/recon/${result.reconciliation_id}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message :
                  typeof err === "object" && err && "message" in err
                    ? String((err as { message: unknown }).message) : "Unknown error"
      toast.error(`Reconciliation failed: ${msg}`)
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">New reconciliation</h1>
        <p className="text-slate-600 mt-1">
          Upload the client's purchase register and the supplier-filed export.
          We'll match them and surface ITC at risk.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>1. Files</CardTitle>
          <CardDescription>
            Both files must be XLSX with the expected columns.{" "}
            <a className="underline" href="/templates/purchase_register_template.xlsx" download>
              Purchase register template
            </a>
            {" · "}
            <a className="underline" href="/templates/supplier_export_template.xlsx" download>
              Supplier export template
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <FileDropzone
            label="Purchase register (from client books)"
            selected={pr} onFileSelected={setPr}
          />
          <FileDropzone
            label="Supplier export (filed with NBR)"
            selected={sf} onFileSelected={setSf}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Period</CardTitle>
        </CardHeader>
        <CardContent>
          <PeriodPicker
            periodStart={periodStart}
            periodEnd={periodEnd}
            onChange={(s, e) => { setPeriodStart(s); setPeriodEnd(e) }}
          />
        </CardContent>
      </Card>

      <div className="flex gap-2">
        <Button
          variant="outline"
          onClick={() => navigate(`/clients/${clientId}`)}
          disabled={submitting}
        >
          Cancel
        </Button>
        <Button
          onClick={onSubmit}
          disabled={submitting || !pr || !sf || !periodStart || !periodEnd}
        >
          {submitting ? "Running…" : "Run reconciliation"}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add the route**

In `frontend/src/router.tsx`, add **before** the wildcard `{ path: "*", ... }` route:

```typescript
import { ReconNew } from "@/pages/ReconNew"
// ...
  {
    path: "/clients/:id/recon/new",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><ReconNew /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
```

- [ ] **Step 4: Add a "New reconciliation" button on ClientDetail**

In `frontend/src/pages/ClientDetail.tsx`, modify the "Coming in later phases" block — replace it with a button that navigates to the new recon page:

```typescript
      <div className="border-t pt-6 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Reconciliations</h2>
          <p className="text-sm text-slate-600 mt-1">
            Match purchase register against supplier-filed VAT data.
          </p>
        </div>
        <Link to={`/clients/${client.id}/recon/new`}>
          <Button>+ New reconciliation</Button>
        </Link>
      </div>
```

(Remove the "Documents (Phase C), Compliance Calendar (Phase D)" line — Documents is now part of recon, Calendar comes in Phase D.)

- [ ] **Step 5: Sanity-check by running the dev server**

```bash
cd frontend
npm run dev
```

Navigate to `/clients/{id}/recon/new`. Confirm the page renders with two dropzones, period picker, sample template links work (XLSX downloads). Don't run a recon yet — full integration test happens in Section 8.

Stop the dev server.

- [ ] **Step 6: Commit**

```bash
git add frontend/public/templates/ frontend/src/pages/ReconNew.tsx \
        frontend/src/pages/ClientDetail.tsx frontend/src/router.tsx
git commit -m "feat(frontend): /clients/:id/recon/new upload page + sample templates"
```

---

## Section 8 — Recon Report UI (the hero screen)

### Task C21: BDT formatting helper

**Why:** The hero card shows "৳47,000" prominently. Bangladesh uses South Asian numbering (lakh = 1,00,000). Implement once, use everywhere.

**Files:**
- Create: `frontend/src/lib/format.ts`
- Test: `frontend/src/lib/__tests__/format.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, expect, it } from "vitest"

import { formatBDT } from "@/lib/format"

describe("formatBDT", () => {
  it.each([
    [0,        "৳0.00"],
    [1,        "৳1.00"],
    [1000,     "৳1,000.00"],
    [100000,   "৳1,00,000.00"],     // 1 lakh
    [10000000, "৳1,00,00,000.00"],  // 1 crore
    [1234567.89, "৳12,34,567.89"],
  ])("formats %s as %s", (input, expected) => {
    expect(formatBDT(input)).toBe(expected)
  })

  it("accepts string decimal input", () => {
    expect(formatBDT("100000.50")).toBe("৳1,00,000.50")
  })

  it("renders negative with the minus before the sign", () => {
    expect(formatBDT(-1000)).toBe("-৳1,000.00")
  })
})
```

- [ ] **Step 2: Run, verify fail**

```bash
cd frontend
npm run test -- --run src/lib/__tests__/format.test.ts
```

- [ ] **Step 3: Implement**

`frontend/src/lib/format.ts`:

```typescript
/** Format a number/string as Bangladesh BDT with South Asian (lakh/crore) grouping. */
export function formatBDT(value: number | string): string {
  const n = typeof value === "string" ? Number(value) : value
  if (!Number.isFinite(n)) return "৳0.00"

  const sign = n < 0 ? "-" : ""
  const abs = Math.abs(n)
  const [intPart, decPart = "00"] = abs.toFixed(2).split(".")

  // South Asian grouping: last 3 digits, then groups of 2.
  let formatted: string
  if (intPart.length <= 3) {
    formatted = intPart
  } else {
    const last3 = intPart.slice(-3)
    const rest = intPart.slice(0, -3)
    const restGrouped = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")
    formatted = `${restGrouped},${last3}`
  }

  return `${sign}৳${formatted}.${decPart}`
}
```

- [ ] **Step 4: Run, verify pass**

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/format.ts frontend/src/lib/__tests__/format.test.ts
git commit -m "feat(frontend): formatBDT with South Asian grouping (lakh/crore)"
```

---

### Task C22: MatchStatusBadge component

**Files:**
- Create: `frontend/src/components/recon/MatchStatusBadge.tsx`

- [ ] **Step 1: Implement**

```typescript
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { MatchStatus } from "@/types/reconciliation"

const styles: Record<MatchStatus, { label: string; className: string }> = {
  exact:    { label: "Exact",    className: "bg-emerald-100 text-emerald-800 hover:bg-emerald-100" },
  fuzzy:    { label: "Fuzzy",    className: "bg-amber-100 text-amber-800 hover:bg-amber-100" },
  partial:  { label: "Partial",  className: "bg-orange-100 text-orange-800 hover:bg-orange-100" },
  no_match: { label: "No match", className: "bg-rose-100 text-rose-800 hover:bg-rose-100" },
}

export function MatchStatusBadge({ status }: { status: MatchStatus }) {
  const s = styles[status]
  return <Badge variant="outline" className={cn("border-0", s.className)}>{s.label}</Badge>
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/recon/MatchStatusBadge.tsx
git commit -m "feat(frontend): MatchStatusBadge with color-coded match status"
```

---

### Task C23: ReconHeroCard

**Files:**
- Create: `frontend/src/components/recon/ReconHeroCard.tsx`

- [ ] **Step 1: Implement**

```typescript
import { Card, CardContent } from "@/components/ui/card"
import { formatBDT } from "@/lib/format"
import type { VatReconciliation } from "@/types/reconciliation"

export function ReconHeroCard({ recon }: { recon: VatReconciliation }) {
  return (
    <Card className="bg-gradient-to-br from-rose-50 to-amber-50 border-rose-200">
      <CardContent className="py-8">
        <div className="grid grid-cols-2 gap-8">
          <div>
            <p className="text-sm font-medium text-slate-600 uppercase tracking-wide">
              Input tax credit at risk
            </p>
            <p className="text-5xl font-bold text-rose-700 mt-2 tracking-tight">
              {formatBDT(recon.at_risk_itc_bdt)}
            </p>
            <p className="text-sm text-slate-600 mt-2">
              of {formatBDT(recon.total_vat_claimed_bdt)} total VAT claimed
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Counter label="Exact"     value={recon.matched_exact}  color="emerald" />
            <Counter label="Fuzzy"     value={recon.matched_fuzzy}  color="amber" />
            <Counter label="Partial"   value={recon.partial_match}  color="orange" />
            <Counter label="No match"  value={recon.no_match}       color="rose" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function Counter({ label, value, color }: {
  label: string; value: number; color: "emerald" | "amber" | "orange" | "rose"
}) {
  const bg = {
    emerald: "bg-emerald-100 text-emerald-800",
    amber: "bg-amber-100 text-amber-800",
    orange: "bg-orange-100 text-orange-800",
    rose: "bg-rose-100 text-rose-800",
  }[color]
  return (
    <div className={`rounded-md px-3 py-2 ${bg}`}>
      <p className="text-xs uppercase">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/recon/ReconHeroCard.tsx
git commit -m "feat(frontend): ReconHeroCard with at-risk ITC headline"
```

---

### Task C24: ReconBreakdownChart (donut)

**Files:**
- Create: `frontend/src/components/recon/ReconBreakdownChart.tsx`

- [ ] **Step 1: Confirm Recharts is installed** (per spec section 5.2 it should be)

```bash
cd frontend
npm ls recharts 2>&1
```

If missing:

```bash
npm install recharts@^2.13.0
```

- [ ] **Step 2: Implement**

`frontend/src/components/recon/ReconBreakdownChart.tsx`:

```typescript
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"

import type { VatReconciliation } from "@/types/reconciliation"

const COLORS = {
  exact: "#10b981",     // emerald-500
  fuzzy: "#f59e0b",     // amber-500
  partial: "#f97316",   // orange-500
  no_match: "#e11d48",  // rose-600
}

export function ReconBreakdownChart({ recon }: { recon: VatReconciliation }) {
  const data = [
    { name: "Exact",    value: recon.matched_exact, fill: COLORS.exact },
    { name: "Fuzzy",    value: recon.matched_fuzzy, fill: COLORS.fuzzy },
    { name: "Partial",  value: recon.partial_match, fill: COLORS.partial },
    { name: "No match", value: recon.no_match,      fill: COLORS.no_match },
  ].filter((d) => d.value > 0)

  if (data.length === 0) {
    return <p className="text-sm text-slate-500">No invoices to display.</p>
  }

  return (
    <div style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            cx="50%" cy="50%"
            innerRadius={60} outerRadius={90}
            paddingAngle={2}
            dataKey="value"
          >
            {data.map((entry) => <Cell key={entry.name} fill={entry.fill} />)}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recon/ReconBreakdownChart.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): donut chart breakdown of match results"
```

---

### Task C25: ReconLineItemsTable

**Files:**
- Create: `frontend/src/components/recon/ReconLineItemsTable.tsx`

- [ ] **Step 1: Implement**

```typescript
import { useState } from "react"

import { LineItemDrawer } from "@/components/recon/LineItemDrawer"
import { MatchStatusBadge } from "@/components/recon/MatchStatusBadge"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/format"
import type { ReconLineItem } from "@/types/reconciliation"

interface Props {
  items: ReconLineItem[]
  reconciliationId: string
}

export function ReconLineItemsTable({ items, reconciliationId }: Props) {
  const [openItem, setOpenItem] = useState<ReconLineItem | null>(null)

  if (items.length === 0) {
    return <p className="text-sm text-slate-500">No line items.</p>
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Status</TableHead>
            <TableHead>Invoice No</TableHead>
            <TableHead>Supplier</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="text-right">Taxable (BDT)</TableHead>
            <TableHead className="text-right">VAT (BDT)</TableHead>
            <TableHead>CA</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow
              key={item.id}
              className="cursor-pointer hover:bg-slate-50"
              onClick={() => setOpenItem(item)}
            >
              <TableCell><MatchStatusBadge status={item.match_status} /></TableCell>
              <TableCell className="font-mono text-xs">{item.pr_invoice_no ?? "—"}</TableCell>
              <TableCell>
                <div className="text-sm">{item.pr_supplier_name ?? "—"}</div>
                <div className="text-xs text-slate-500 font-mono">{item.pr_supplier_bin ?? ""}</div>
              </TableCell>
              <TableCell className="text-sm">{item.pr_invoice_date ?? "—"}</TableCell>
              <TableCell className="text-right font-mono text-sm">
                {formatBDT(item.pr_taxable_amount_bdt ?? "0")}
              </TableCell>
              <TableCell className="text-right font-mono text-sm">
                {formatBDT(item.pr_vat_amount_bdt ?? "0")}
              </TableCell>
              <TableCell className="text-sm capitalize text-slate-600">
                {item.ca_override ?? "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <LineItemDrawer
        item={openItem}
        reconciliationId={reconciliationId}
        onClose={() => setOpenItem(null)}
      />
    </>
  )
}
```

- [ ] **Step 2: Commit** (drawer is added in next task; the import will fail until then — keep this commit small)

Don't commit yet — the import `LineItemDrawer` doesn't exist. Continue to next task and commit both together.

---

### Task C26: LineItemDrawer + CAOverrideSelect

**Files:**
- Create: `frontend/src/components/recon/CAOverrideSelect.tsx`
- Create: `frontend/src/components/recon/LineItemDrawer.tsx`
- Verify shadcn Sheet is available; install if missing (Task 0 below).

- [ ] **Step 0: Add shadcn Sheet component**

Check: does `frontend/src/components/ui/sheet.tsx` exist?

```bash
ls frontend/src/components/ui/sheet.tsx 2>&1 || echo "MISSING"
```

If missing, install via shadcn CLI:

```bash
cd frontend
npx shadcn@latest add sheet
```

Verify the file appears at `frontend/src/components/ui/sheet.tsx`.

If the generated file uses `@base-ui/react/dialog` instead of `@radix-ui/react-dialog`, replace it manually with the radix-based version (matching the pattern from `dialog.tsx` in this repo). The Phase B fix log notes this happened with `dialog.tsx` already.

- [ ] **Step 1: Implement CAOverrideSelect**

`frontend/src/components/recon/CAOverrideSelect.tsx`:

```typescript
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useUpdateLineItemOverride } from "@/hooks/useReconciliations"
import type { CAOverride, ReconLineItem } from "@/types/reconciliation"

const NONE = "__none__"

export function CAOverrideSelect({ item }: { item: ReconLineItem }) {
  const update = useUpdateLineItemOverride()

  return (
    <Select
      value={item.ca_override ?? NONE}
      onValueChange={(v) => {
        update.mutate({
          lineItemId: item.id,
          reconciliationId: item.reconciliation_id,
          override: v === NONE ? null : (v as CAOverride),
        })
      }}
    >
      <SelectTrigger className="w-44">
        <SelectValue placeholder="No override" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>No override</SelectItem>
        <SelectItem value="approved">Approved (CA accepts)</SelectItem>
        <SelectItem value="disputed">Disputed</SelectItem>
        <SelectItem value="ignore">Ignore</SelectItem>
      </SelectContent>
    </Select>
  )
}
```

- [ ] **Step 2: Implement LineItemDrawer**

`frontend/src/components/recon/LineItemDrawer.tsx`:

```typescript
import { CAOverrideSelect } from "@/components/recon/CAOverrideSelect"
import { MatchStatusBadge } from "@/components/recon/MatchStatusBadge"
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet"
import { formatBDT } from "@/lib/format"
import type { ReconLineItem } from "@/types/reconciliation"

interface Props {
  item: ReconLineItem | null
  reconciliationId: string
  onClose: () => void
}

export function LineItemDrawer({ item, onClose }: Props) {
  return (
    <Sheet open={Boolean(item)} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="sm:max-w-xl overflow-y-auto">
        {item && (
          <>
            <SheetHeader>
              <SheetTitle>Line item</SheetTitle>
              <SheetDescription>
                <MatchStatusBadge status={item.match_status} />
              </SheetDescription>
            </SheetHeader>

            <div className="grid grid-cols-2 gap-6 mt-6">
              <Section title="Purchase register">
                <Field label="Invoice No"  value={item.pr_invoice_no} mono />
                <Field label="Supplier BIN" value={item.pr_supplier_bin} mono />
                <Field label="Supplier"    value={item.pr_supplier_name} />
                <Field label="Date"        value={item.pr_invoice_date} />
                <Field label="Taxable"     value={item.pr_taxable_amount_bdt && formatBDT(item.pr_taxable_amount_bdt)} mono />
                <Field label="VAT"         value={item.pr_vat_amount_bdt && formatBDT(item.pr_vat_amount_bdt)} mono />
              </Section>
              <Section title="Supplier export">
                <Field label="Invoice No"  value={item.sf_invoice_no} mono />
                <Field label="Date"        value={item.sf_invoice_date} />
                <Field label="Taxable"     value={item.sf_taxable_amount_bdt && formatBDT(item.sf_taxable_amount_bdt)} mono />
                <Field label="VAT"         value={item.sf_vat_amount_bdt && formatBDT(item.sf_vat_amount_bdt)} mono />
              </Section>
            </div>

            {item.discrepancy_flags && Object.keys(item.discrepancy_flags).length > 0 && (
              <div className="mt-6 rounded-md bg-slate-50 p-3 text-sm">
                <p className="font-semibold text-slate-700">Discrepancy</p>
                <pre className="text-xs text-slate-600 mt-1 whitespace-pre-wrap">
                  {JSON.stringify(item.discrepancy_flags, null, 2)}
                </pre>
              </div>
            )}

            <div className="mt-6">
              <p className="text-sm font-semibold text-slate-700 mb-2">CA decision</p>
              <CAOverrideSelect item={item} />
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase font-semibold text-slate-500 mb-2">{title}</p>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function Field({ label, value, mono }:
  { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className={mono ? "font-mono text-right" : "text-right"}>{value ?? "—"}</span>
    </div>
  )
}
```

- [ ] **Step 3: Commit (table + drawer + override together so the build passes)**

```bash
git add frontend/src/components/ui/sheet.tsx \
        frontend/src/components/recon/ReconLineItemsTable.tsx \
        frontend/src/components/recon/LineItemDrawer.tsx \
        frontend/src/components/recon/CAOverrideSelect.tsx
git commit -m "feat(frontend): line items table + drilldown drawer + CA override select"
```

---

### Task C27: ReconReport page

**Files:**
- Create: `frontend/src/pages/ReconReport.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Implement**

`frontend/src/pages/ReconReport.tsx`:

```typescript
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { ReconBreakdownChart } from "@/components/recon/ReconBreakdownChart"
import { ReconHeroCard } from "@/components/recon/ReconHeroCard"
import { ReconLineItemsTable } from "@/components/recon/ReconLineItemsTable"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useRecon, useReconLineItems } from "@/hooks/useReconciliations"
import { api } from "@/lib/api"

export function ReconReport() {
  const { id: clientId, reconId } = useParams<{ id: string; reconId: string }>()
  const { data: recon, isLoading } = useRecon(reconId)
  const { data: items = [], isLoading: itemsLoading } = useReconLineItems(reconId)

  async function downloadXlsx() {
    if (!reconId) return
    try {
      const res = await api.get(`/api/v1/reconciliations/${reconId}/export`, {
        responseType: "blob",
      })
      const url = URL.createObjectURL(res.data)
      const a = document.createElement("a")
      a.href = url
      a.download = `recon-${reconId}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error("Could not export. Please try again.")
    }
  }

  if (isLoading) return <p className="text-slate-500 p-8">Loading…</p>
  if (!recon) return (
    <div className="space-y-4 p-8">
      <p>Reconciliation not found.</p>
      <Link to={`/clients/${clientId}`} className="underline">Back to client</Link>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to={`/clients/${clientId}`} className="text-sm text-slate-500 hover:underline">
            ← Client
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">Reconciliation</h1>
          <p className="text-slate-600 mt-1 text-sm">
            Period: {recon.period_start} → {recon.period_end}
          </p>
        </div>
        <Button onClick={downloadXlsx}>Export to XLSX</Button>
      </div>

      <ReconHeroCard recon={recon} />

      <div className="grid grid-cols-3 gap-4">
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle>Match breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <ReconBreakdownChart recon={recon} />
          </CardContent>
        </Card>
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>Line items</CardTitle>
          </CardHeader>
          <CardContent>
            {itemsLoading ? (
              <p className="text-slate-500 text-sm">Loading line items…</p>
            ) : (
              <ReconLineItemsTable items={items} reconciliationId={reconId!} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire route**

In `frontend/src/router.tsx`, before the `*` wildcard:

```typescript
import { ReconReport } from "@/pages/ReconReport"
// ...
  {
    path: "/clients/:id/recon/:reconId",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><ReconReport /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ReconReport.tsx frontend/src/router.tsx
git commit -m "feat(frontend): /clients/:id/recon/:reconId hero report screen"
```

---

### Task C28: Recon list section on ClientDetail

**Files:**
- Modify: `frontend/src/pages/ClientDetail.tsx`

- [ ] **Step 1: Add a recon list panel**

Inside `ClientDetail.tsx`, replace the current "Reconciliations" placeholder block (added in Task C20) with:

```typescript
import { useReconList } from "@/hooks/useReconciliations"
import { MatchStatusBadge } from "@/components/recon/MatchStatusBadge"
import { formatBDT } from "@/lib/format"

// Inside the component, after the existing Cards:
{/* Recon list */}
<RecentRecons clientId={client.id} />
```

Then add a sub-component at the bottom of the file:

```typescript
function RecentRecons({ clientId }: { clientId: string }) {
  const { data: recons = [], isLoading } = useReconList(clientId)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Reconciliations</CardTitle>
          <Link to={`/clients/${clientId}/recon/new`}>
            <Button size="sm">+ New reconciliation</Button>
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : recons.length === 0 ? (
          <p className="text-sm text-slate-500">
            No reconciliations yet. Run your first one.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {recons.map((r) => (
              <li key={r.id} className="py-3 flex items-center justify-between">
                <div>
                  <Link to={`/clients/${clientId}/recon/${r.id}`} className="text-sm font-medium hover:underline">
                    {r.period_start} → {r.period_end}
                  </Link>
                  <p className="text-xs text-slate-500">
                    {r.total_invoices} invoices · {r.matched_exact} exact · {r.no_match} no-match
                  </p>
                </div>
                <p className="text-sm font-semibold text-rose-700">
                  {formatBDT(r.at_risk_itc_bdt)} at risk
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
```

Remove the prior "+ New reconciliation" block from Task C20 (now superseded by the card header here).

- [ ] **Step 2: Verify the build still compiles**

```bash
cd frontend
npm run build
```

Expected: build success. Fix any TypeScript errors before committing.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClientDetail.tsx
git commit -m "feat(frontend): client recon list with at-risk ITC summary"
```

---

## Section 9 — End-to-end verification

### Task C29: Full pipeline manual test via Playwright

**Why:** Phase B's manual verification was deferred and resurfaced as the Onboard hotfix. This time, verify the recon pipeline end-to-end *before* declaring Phase C complete.

**Files:**
- None (manual test, results recorded in commit message of next task)

- [ ] **Step 1: Start both servers**

```bash
# Terminal A
cd backend
.venv/Scripts/python.exe -m app.main

# Terminal B
cd frontend
npm run dev
```

- [ ] **Step 2: Generate intentionally-mismatched test fixtures**

```bash
.venv/Scripts/python.exe - <<'EOF'
import openpyxl, os
from datetime import date
os.makedirs("/tmp/recon-test", exist_ok=True)

# Purchase register: 5 rows
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Invoice No","Supplier BIN","Supplier Name","Invoice Date","Taxable Amount (BDT)","VAT Amount (BDT)"])
ws.append(["INV-0001","123456789","Acme Ltd",date(2024,1,15),10000,1500])      # exact
ws.append(["INV-0002","123456789","Acme Ltd",date(2024,1,18),5000,750])         # fuzzy (date+amount within tol)
ws.append(["INV-0003","987654321","Beta Co", date(2024,1,20),20000,3000])       # partial (BIN matches, invoice no doesn't)
ws.append(["INV-0004","555666777","Gamma BD",date(2024,1,25),15000,2250])       # no_match (BIN absent)
ws.append(["INV-0005","123456789","Acme Ltd",date(2024,1,28),3000,450])         # exact
wb.save("/tmp/recon-test/purchase_register.xlsx")

# Supplier export
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Invoice No","Invoice Date","Taxable Amount (BDT)","VAT Amount (BDT)","Buyer BIN"])
ws.append(["INV-0001",date(2024,1,15),10000,1500,"123456789"])    # exact match for row 1
ws.append(["INV-0002",date(2024,1,17),5020,753,"123456789"])      # fuzzy: 1 day off, 0.4% amount diff
ws.append(["INV-9999",date(2024,1,5),  500, 75,"987654321"])      # different invoice no for partial test
ws.append(["INV-0005",date(2024,1,28),3000,450,"123456789"])      # exact match for row 5
wb.save("/tmp/recon-test/supplier_export.xlsx")
print("fixtures written")
EOF
```

- [ ] **Step 3: Use Playwright to drive the flow**

Manual sequence (run in Playwright):
1. Navigate to `http://localhost:5173/login`
2. Log in with the existing test user (or create one via the SQL pgcrypto pattern from the Onboard hotfix verification)
3. Navigate to `/clients` and pick any client (or add one)
4. Click "+ New reconciliation"
5. Drop the two test XLSX files (use `browser_evaluate` to set `<input type="file">` value, or use Playwright's file upload helper)
6. Pick period 2024-01 → 2024-01
7. Click "Run reconciliation"
8. Wait for redirect to `/clients/:id/recon/:reconId`

**Expected on the report page:**
- Hero shows at-risk ITC = `formatBDT(2250 + 3000)` = `৳5,250.00` (no_match VAT + partial VAT — wait, partial counts as at-risk too)

  Recompute: **safe** = exact (1500 + 450) + fuzzy (750) = 2700. **at_risk** = partial (3000) + no_match (2250) = 5250. **total** = 7950.

- Hero number = `৳5,250.00`
- Counters: 2 exact, 1 fuzzy, 1 partial, 1 no_match
- Donut chart shows the four slices
- Line items table shows all 5 rows with correct color-coded badges
- Click a row → drawer opens with PR + SF columns side-by-side
- For the fuzzy row, drawer shows discrepancy_flags with `date_off_by_days = 1`
- Change CA override on a row to "Approved" → toast confirms, persists on reload

**Expected XLSX export:**
- Click "Export to XLSX" → file downloads named `recon-{uuid}.xlsx`
- Open it: Summary sheet has the headline numbers; Line Items sheet has all 5 rows color-coded by match status

If any expectation fails, halt the plan and debug before continuing.

- [ ] **Step 4: Stop the servers**

Stop both background processes via TaskStop / Ctrl+C.

- [ ] **Step 5: Cleanup test data**

Use Supabase MCP `execute_sql` to delete the test reconciliation, line items, and any documents created during the test:

```sql
-- Find recently-created recons (within the last 1 hour)
DELETE FROM recon_line_items
 WHERE reconciliation_id IN (
   SELECT id FROM vat_reconciliations WHERE started_at > now() - interval '1 hour'
 );
DELETE FROM vat_reconciliations WHERE started_at > now() - interval '1 hour';
DELETE FROM documents WHERE created_at > now() - interval '1 hour' AND doc_type IN ('purchase_register','supplier_export');
DELETE FROM audit_log
 WHERE table_name IN ('vat_reconciliations','recon_line_items','documents')
   AND created_at > now() - interval '1 hour';
```

(Storage objects in the `recon-files` bucket should also be deleted — list them via the Supabase Studio UI or skip if non-essential for ongoing dev.)

---

### Task C30: Tag Phase C complete

**Files:** none (git tag only).

- [ ] **Step 1: Verify all tests pass**

```bash
# Backend
cd backend
.venv/Scripts/python.exe -m pytest -v

# Frontend
cd ../frontend
npm run test -- --run
npm run build
```

All must pass / succeed. Fix any failures before tagging.

- [ ] **Step 2: Tag**

```bash
git tag phase-c-complete
git log --oneline phase-b-complete..phase-c-complete
```

The log should show every commit added during Phase C in order.

- [ ] **Step 3: Summary message**

Post a Phase C summary to the user listing:
- Number of commits in this phase
- All migrations applied (0010, 0011, 0012)
- Backend test count
- Frontend test count
- Any deferred items / known gaps (e.g., XLSX duplicate-period 409 handling not yet wired in the FE)
- Manual verification confirmation (the recon pipeline ran end-to-end and produced the expected at-risk number)

---

## Self-review checklist (run after writing this plan, before execution)

1. **Spec section 7 (recon flow) coverage:**
   - 7.1 sequence steps 1-8 → C19 (upload), C20 (run + redirect), C25/C26/C27 (report read)
   - 7.2 matcher tiers → C7 (every tier with explicit tests)
   - 7.3 column contract → C6 (case-insensitive header check + missing column error)
2. **Spec section 6.5 audit trigger:** C1 implements Option 3. ✅
3. **Spec section 5.2 frontend dependencies:** Recharts added in C24 install step. ✅
4. **Spec section 9 UI screens:** `/clients/:id/recon/new` (C20), `/clients/:id/recon/:id` (C27), recon list on ClientDetail (C28). ✅
5. **Spec section 12 success criteria 1-8:** all addressed by the C20+C27+C28 trio plus the export endpoint C14.
6. **Risk #2 (BD deadline correctness):** out of scope for Phase C — was Phase B/D.
7. **Risk #4 (Cloud Run cold starts):** deferred to Phase E (deploy).
8. **Type consistency:** `MatchStatus` values match across Python (`exact`/`fuzzy`/`partial`/`no_match`), TypeScript Zod enum, and the badge style map. ✅ The `CAOverride` Python enum and TypeScript zod enum both use `approved`/`disputed`/`ignore`. ✅
9. **No placeholders / TBDs:** scanned. None present.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-04-phase-c-reconciliation.md`.** Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
