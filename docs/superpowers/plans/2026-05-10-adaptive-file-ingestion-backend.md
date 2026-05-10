# Adaptive File Ingestion — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend ingestion pipeline that accepts mixed-format files (XLSX/CSV/PDF/image), routes them through engine adapters (pandas / pdfplumber+LLM / Gemini Vision), persists extracted rows, supports a review workflow, and hands confirmed rows off to the existing reconciliation pipeline via canonical XLSX — all behind an `INGESTION_ENABLED` feature flag, with the existing reconciliation flow untouched.

**Architecture:** New `app/ingestion/` module mirroring the structure of `app/reconciliation/`. Per-MIME router selects an engine; engines emit `ExtractedFileResult`. State machine over `ingestion_jobs` (Postgres) drives the lifecycle. In-process async worker with `SELECT ... FOR UPDATE SKIP LOCKED` lease pattern. Handoff serializes confirmed rows into a canonical XLSX, writes it to the existing `recon-files` bucket as a normal `documents` row, then calls existing `reconciliation.service.run_reconciliation()` in-process.

**Tech Stack:** FastAPI, Supabase (Postgres + Storage + Realtime), pandas, openpyxl, pdfplumber, pypdfium2, Pillow, pillow-heif, google-generativeai (Gemini 2.5 Flash), structlog, pytest, pytest-asyncio, respx.

**Spec:** [`docs/superpowers/specs/2026-05-10-adaptive-file-ingestion-design.md`](../specs/2026-05-10-adaptive-file-ingestion-design.md)

**Branch:** `phase-f-adaptive-ingestion` (already created)

---

## File structure being built

**Backend (created):**
```
backend/app/ingestion/
  __init__.py
  exceptions.py
  schemas.py                  # Pydantic request/response + internal types
  router.py                   # FastAPI endpoints under /api/v1/ingestion
  service.py                  # job orchestration, finalize entry point
  persistence.py              # CRUD on jobs/files/rows/column_mappings
  storage.py                  # ingestion-files bucket I/O
  router_engine.py            # MIME → engine router
  validation.py               # BIN/date/15%-rule deterministic validators
  lifecycle.py                # state machine transitions
  handoff.py                  # confirmed rows → canonical XLSX → reconciliation
  worker.py                   # in-process job runner with lease pattern
  llm.py                      # LLM adapter interface + Gemini impl + Stub
  rate_limit.py               # per-tenant token bucket
  engines/
    __init__.py
    base.py                   # ExtractedFileResult, ExtractedRow, EngineProtocol
    pandas_canonical.py       # XLSX/CSV with canonical headers
    pandas_mapper.py          # XLSX/CSV with non-canonical headers
    pdf_borndigital.py        # pdfplumber + LLM normalizer
    vision.py                 # Gemini Flash vision
```

**Backend (modified):**
```
backend/requirements.txt      # add pdfplumber, pypdfium2, Pillow, pillow-heif, google-generativeai
backend/app/main.py           # conditional router registration + worker lifespan
backend/.env.example          # INGESTION_ENABLED, GEMINI_API_KEY, rate limits
```

**Tests (created):**
```
backend/tests/ingestion/
  __init__.py
  conftest.py                 # fixtures: stub LLM adapter, sample tenant
  test_persistence.py
  test_storage.py
  test_validation.py
  test_llm_stub.py
  test_router_engine.py       # MIME → engine routing
  test_lifecycle.py
  test_handoff.py
  test_worker.py
  test_rate_limit.py
  test_api.py                 # endpoint integration tests
  fixtures/
    canonical_register.xlsx
    bangla_headers.xlsx
    mushak_6.3_borndigital.pdf
    mushak_6.3_scan.pdf
    phone_photo_invoice.jpg
    bundled_scan_5pages.pdf
    unreadable_garbage.pdf
  engines/
    __init__.py
    test_pandas_canonical.py
    test_pandas_mapper.py
    test_pdf_borndigital.py
    test_vision.py
  integration/
    __init__.py
    test_full_flow.py         # gated on INGESTION_TEST_SUPABASE_URL
```

**Migrations (created):**
```
migrations/
  0014_ingestion_tables.sql
  0015_ingestion_storage_bucket.sql
```

---

## Phase 1 — Foundation

### Task 1: Database migration — ingestion tables, indexes, RLS

**Files:**
- Create: `migrations/0014_ingestion_tables.sql`

- [ ] **Step 1: Write the migration**

Create `migrations/0014_ingestion_tables.sql`:

```sql
-- 0014_ingestion_tables.sql
-- Adaptive file ingestion: jobs, per-file extraction state, extracted rows,
-- and the LLM column-mapping cache. All tenant-scoped via RLS using the same
-- pattern as 0004_rls_policies.sql.

-- ============================================================
-- INGESTION_JOBS — one row per upload session
-- ============================================================

CREATE TYPE ingestion_job_status AS ENUM (
  'pending', 'extracting', 'ready_for_review',
  'confirmed', 'reconciling', 'completed', 'failed'
);

CREATE TYPE ingestion_kind AS ENUM (
  'purchase_register', 'supplier_export'
);

CREATE TABLE ingestion_jobs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id          uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  created_by         uuid NOT NULL,
  kind               ingestion_kind NOT NULL,
  period_start       date NOT NULL,
  period_end         date NOT NULL,
  status             ingestion_job_status NOT NULL DEFAULT 'pending',
  files_total        int NOT NULL DEFAULT 0,
  files_done         int NOT NULL DEFAULT 0,
  rows_total         int NOT NULL DEFAULT 0,
  rows_needs_review  int NOT NULL DEFAULT 0,
  error_summary      text,
  reconciliation_id  uuid REFERENCES vat_reconciliations(id) ON DELETE SET NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  completed_at       timestamptz,
  CHECK (period_end >= period_start)
);

-- ============================================================
-- INGESTION_FILES — one row per uploaded file
-- ============================================================

CREATE TYPE ingestion_file_status AS ENUM (
  'queued', 'extracting', 'extracted', 'failed', 'skipped'
);

CREATE TABLE ingestion_files (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id             uuid NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  tenant_id          uuid NOT NULL,
  storage_path       text NOT NULL,
  original_filename  text NOT NULL,
  mime_type          text NOT NULL,
  byte_size          bigint NOT NULL,
  engine             text,
  status             ingestion_file_status NOT NULL DEFAULT 'queued',
  rows_extracted     int NOT NULL DEFAULT 0,
  needs_review       boolean NOT NULL DEFAULT false,
  warnings           jsonb NOT NULL DEFAULT '[]'::jsonb,
  error              text,
  extraction_started_at timestamptz,
  extracted_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- EXTRACTED_ROWS — one row per invoice extracted from any file
-- ============================================================

CREATE TYPE extracted_row_status AS ENUM (
  'auto_passed', 'needs_review', 'confirmed', 'rejected', 'edited'
);

CREATE TABLE extracted_rows (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id            uuid NOT NULL REFERENCES ingestion_files(id) ON DELETE CASCADE,
  job_id             uuid NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
  tenant_id          uuid NOT NULL,
  source_page_no     int,
  row_data           jsonb NOT NULL,
  row_data_original  jsonb NOT NULL,
  status             extracted_row_status NOT NULL DEFAULT 'needs_review',
  field_warnings     jsonb NOT NULL DEFAULT '[]'::jsonb,
  reviewed_by        uuid,
  reviewed_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
-- COLUMN_MAPPINGS — cache for LLM-inferred header mappings
-- ============================================================

CREATE TABLE ingestion_column_mappings (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  kind               ingestion_kind NOT NULL,
  header_signature   text NOT NULL,
  mapping            jsonb NOT NULL,
  confirmed_by       uuid,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, kind, header_signature)
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX ix_ingestion_jobs_tenant_status_created
  ON ingestion_jobs (tenant_id, status, created_at DESC);

CREATE INDEX ix_ingestion_files_job_status
  ON ingestion_files (job_id, status);

CREATE INDEX ix_extracted_rows_job_status
  ON extracted_rows (job_id, status);

CREATE INDEX ix_extracted_rows_needs_review
  ON extracted_rows (job_id)
  WHERE status = 'needs_review';

-- Lease index used by the worker's SELECT ... FOR UPDATE SKIP LOCKED
CREATE INDEX ix_ingestion_jobs_lease
  ON ingestion_jobs (status, updated_at)
  WHERE status IN ('pending', 'extracting');

-- ============================================================
-- updated_at trigger (reuse existing helper from 0002 if present;
-- otherwise inline a simple one)
-- ============================================================

CREATE OR REPLACE FUNCTION ingestion_set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ingestion_jobs_updated_at
  BEFORE UPDATE ON ingestion_jobs
  FOR EACH ROW EXECUTE FUNCTION ingestion_set_updated_at();

-- ============================================================
-- RLS — same pattern as 0004_rls_policies.sql
-- tenant_id pulled from auth.jwt() ->> 'tenant_id'
-- Service role bypasses RLS automatically (worker writes via admin client).
-- ============================================================

ALTER TABLE ingestion_jobs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_files          ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_rows           ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_column_mappings ENABLE ROW LEVEL SECURITY;

CREATE POLICY ingestion_jobs_tenant ON ingestion_jobs
  FOR ALL TO authenticated
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)
  WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY ingestion_files_tenant ON ingestion_files
  FOR ALL TO authenticated
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)
  WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY extracted_rows_tenant ON extracted_rows
  FOR ALL TO authenticated
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)
  WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY ingestion_column_mappings_tenant ON ingestion_column_mappings
  FOR ALL TO authenticated
  USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)
  WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
```

> **Note:** If `migrations/0004_rls_policies.sql` uses a different JWT-claim path (e.g., a helper function), copy that pattern verbatim instead of `(auth.jwt() ->> 'tenant_id')::uuid`. Check 0004 before applying.

- [ ] **Step 2: Apply migration via Supabase MCP**

Apply via the Supabase MCP `apply_migration` tool, or run against local Postgres if developing locally:

```bash
psql "$SUPABASE_DB_URL" -f migrations/0014_ingestion_tables.sql
```

Expected: no errors. The four tables, three enums, five indexes, four RLS policies, and the trigger should now exist.

- [ ] **Step 3: Verify schema**

```bash
psql "$SUPABASE_DB_URL" -c "\d ingestion_jobs" \
                       -c "\d ingestion_files" \
                       -c "\d extracted_rows" \
                       -c "\d ingestion_column_mappings"
```

Expected: each `\d` shows the table with the columns listed in the migration, with `RLS enabled`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0014_ingestion_tables.sql
git commit -m "migration: ingestion_jobs/files/rows/column_mappings (0014)"
```

---

### Task 2: Storage bucket migration — `ingestion-files`

**Files:**
- Create: `migrations/0015_ingestion_storage_bucket.sql`

- [ ] **Step 1: Write the migration**

Mirror the pattern from `migrations/0011_storage_buckets.sql`:

```sql
-- 0015_ingestion_storage_bucket.sql
-- Private bucket 'ingestion-files' for raw uploaded XLSX/PDF/image originals
-- BEFORE extraction. Path layout: {tenant_id}/{job_id}/{file_id}/{filename}
-- The first path segment (tenant_id) is the RLS pivot, identical to 0011.

INSERT INTO storage.buckets (id, name, public)
VALUES ('ingestion-files', 'ingestion-files', false)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS ingestion_files_tenant_select ON storage.objects;
DROP POLICY IF EXISTS ingestion_files_tenant_insert ON storage.objects;
DROP POLICY IF EXISTS ingestion_files_tenant_update ON storage.objects;
DROP POLICY IF EXISTS ingestion_files_tenant_delete ON storage.objects;

CREATE POLICY ingestion_files_tenant_select ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY ingestion_files_tenant_insert ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY ingestion_files_tenant_update ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  )
  WITH CHECK (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );

CREATE POLICY ingestion_files_tenant_delete ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'ingestion-files'
    AND (storage.foldername(name))[1]::uuid =
      (SELECT tenant_id FROM public.user_profiles WHERE id = auth.uid())
  );
```

- [ ] **Step 2: Apply**

```bash
psql "$SUPABASE_DB_URL" -f migrations/0015_ingestion_storage_bucket.sql
```

- [ ] **Step 3: Verify**

```bash
psql "$SUPABASE_DB_URL" -c "SELECT id, name, public FROM storage.buckets WHERE id = 'ingestion-files';"
```

Expected: one row, `public = false`.

- [ ] **Step 4: Commit**

```bash
git add migrations/0015_ingestion_storage_bucket.sql
git commit -m "migration: ingestion-files storage bucket (0015)"
```

---

### Task 3: Add new Python dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Edit requirements.txt — append the new ingestion deps**

Add to `backend/requirements.txt`, in a new "Ingestion" section after the "Data processing" block:

```
# Ingestion (Phase F)
pdfplumber==0.11.4
pypdfium2==4.30.0
Pillow==10.4.0
pillow-heif==0.18.0
google-generativeai==0.8.3
python-magic==0.4.27
```

> Why these versions: all ship `manylinux_2_17_x86_64` wheels (no compile on Render). `python-magic` requires `libmagic` system lib — on Debian-slim it's available via `libmagic1`. We'll add the apt step to the Dockerfile in Task 30.

- [ ] **Step 2: Install locally and smoke-test imports**

```bash
cd backend && pip install -r requirements.txt
python -c "import pdfplumber, pypdfium2, PIL, pillow_heif, google.generativeai, magic; print('ok')"
```

Expected: prints `ok`. If `magic` import fails on Windows, that's expected — see Task 30 for OS notes; the rest must succeed.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: add ingestion deps (pdfplumber, pypdfium2, Pillow, pillow-heif, google-generativeai, python-magic)"
```

---

### Task 4: Ingestion module skeleton + Pydantic schemas

**Files:**
- Create: `backend/app/ingestion/__init__.py`
- Create: `backend/app/ingestion/exceptions.py`
- Create: `backend/app/ingestion/schemas.py`
- Create: `backend/tests/ingestion/__init__.py`
- Create: `backend/tests/ingestion/test_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

Create `backend/tests/ingestion/__init__.py` empty.

Create `backend/tests/ingestion/test_schemas.py`:

```python
"""Tests for ingestion Pydantic schemas."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ingestion.schemas import (
    CreateJobRequest,
    ExtractedRowData,
    JobKind,
    JobStatus,
    RowStatus,
)


def test_job_kind_values():
    assert JobKind.PURCHASE_REGISTER == "purchase_register"
    assert JobKind.SUPPLIER_EXPORT == "supplier_export"


def test_create_job_request_period_ordering():
    with pytest.raises(ValidationError):
        CreateJobRequest(
            client_id=uuid4(),
            period_start=date(2026, 5, 31),
            period_end=date(2026, 5, 1),
            kind=JobKind.PURCHASE_REGISTER,
        )


def test_create_job_request_happy_path():
    req = CreateJobRequest(
        client_id=uuid4(),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert req.kind == JobKind.PURCHASE_REGISTER


def test_extracted_row_data_decimal_rounding():
    row = ExtractedRowData(
        invoice_no="INV-1",
        supplier_bin="123456789",
        supplier_name="ACME",
        invoice_date=date(2026, 5, 15),
        taxable_amount_bdt="1000.999",
        vat_amount_bdt="150.149",
    )
    assert row.taxable_amount_bdt == Decimal("1001.00")
    assert row.vat_amount_bdt == Decimal("150.15")


def test_row_status_values():
    assert RowStatus.AUTO_PASSED == "auto_passed"
    assert RowStatus.NEEDS_REVIEW == "needs_review"
```

- [ ] **Step 2: Run — expect failure (module not yet defined)**

```bash
cd backend && pytest tests/ingestion/test_schemas.py -v
```

Expected: ImportError on `app.ingestion.schemas`.

- [ ] **Step 3: Write `__init__.py`, `exceptions.py`, `schemas.py`**

Create `backend/app/ingestion/__init__.py`:

```python
"""HishabAI adaptive file ingestion."""
```

Create `backend/app/ingestion/exceptions.py`:

```python
"""Domain exceptions for ingestion."""
from __future__ import annotations

from app.core.exceptions import HishabError


class IngestionError(HishabError):
    code = "INGESTION_ERROR"
    status_code = 400


class UnsupportedFileTypeError(IngestionError):
    code = "INGESTION_UNSUPPORTED_TYPE"

    def __init__(self, filename: str, mime: str):
        super().__init__(
            message=f"File '{filename}' has unsupported type '{mime}'",
            details={"filename": filename, "mime": mime},
        )


class FileTooLargeError(IngestionError):
    code = "INGESTION_FILE_TOO_LARGE"

    def __init__(self, filename: str, size: int, max_size: int):
        super().__init__(
            message=f"File '{filename}' is {size} bytes; max {max_size}",
            details={"filename": filename, "size": size, "max_size": max_size},
        )


class JobNotFoundError(IngestionError):
    code = "INGESTION_JOB_NOT_FOUND"
    status_code = 404


class InvalidStateTransitionError(IngestionError):
    code = "INGESTION_INVALID_TRANSITION"

    def __init__(self, frm: str, to: str):
        super().__init__(
            message=f"Cannot transition from '{frm}' to '{to}'",
            details={"from": frm, "to": to},
        )


class ExtractionFailedError(IngestionError):
    code = "INGESTION_EXTRACTION_FAILED"
    status_code = 500


class HandoffError(IngestionError):
    code = "INGESTION_HANDOFF_FAILED"
    status_code = 500
```

Create `backend/app/ingestion/schemas.py`:

```python
"""Pydantic models for the ingestion module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_2dp(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Enums (mirror Postgres enum types from migration 0014) ────────────────


class JobKind(str, Enum):
    PURCHASE_REGISTER = "purchase_register"
    SUPPLIER_EXPORT = "supplier_export"


class JobStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    READY_FOR_REVIEW = "ready_for_review"
    CONFIRMED = "confirmed"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    FAILED = "failed"


class FileStatus(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"
    SKIPPED = "skipped"


class RowStatus(str, Enum):
    AUTO_PASSED = "auto_passed"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EDITED = "edited"


# ── Inbound API ──────────────────────────────────────────────────────────


class CreateJobRequest(BaseModel):
    """Multipart form-data fields for POST /api/v1/ingestion/jobs.

    The actual file uploads come through FastAPI's UploadFile in the router;
    this model carries the non-file fields.
    """

    model_config = ConfigDict(extra="forbid")

    client_id: UUID
    period_start: date
    period_end: date
    kind: JobKind

    @model_validator(mode="after")
    def _period_ordered(self) -> "CreateJobRequest":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class CreateJobFileSummary(BaseModel):
    file_id: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    accepted: bool
    rejection_reason: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: UUID
    files: list[CreateJobFileSummary]


# ── Internal: canonical extracted row shape (matches PurchaseRow/SupplierRow) ─


class ExtractedRowData(BaseModel):
    """Canonical shape for any extracted row, regardless of source engine.

    Mirrors the union of fields in reconciliation.schemas.PurchaseRow
    and SupplierRow. The `kind` of the parent job determines which fields
    are required at handoff time; both schemas tolerate the union here.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    invoice_no: str
    invoice_date: date
    taxable_amount_bdt: Decimal
    vat_amount_bdt: Decimal
    supplier_bin: Optional[str] = None
    supplier_name: Optional[str] = None
    buyer_bin: Optional[str] = None

    @field_validator("taxable_amount_bdt", "vat_amount_bdt", mode="before")
    @classmethod
    def _round(cls, v: object) -> Decimal:
        return _to_2dp(v)  # type: ignore[arg-type]


class FieldWarning(BaseModel):
    field: str
    code: str
    message: str


# ── Outbound API: list rows for review ────────────────────────────────────


class ExtractedRowOut(BaseModel):
    id: UUID
    file_id: UUID
    job_id: UUID
    source_page_no: Optional[int] = None
    row_data: ExtractedRowData
    row_data_original: ExtractedRowData
    status: RowStatus
    field_warnings: list[FieldWarning] = Field(default_factory=list)
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class JobOut(BaseModel):
    id: UUID
    tenant_id: UUID
    client_id: UUID
    kind: JobKind
    period_start: date
    period_end: date
    status: JobStatus
    files_total: int
    files_done: int
    rows_total: int
    rows_needs_review: int
    error_summary: Optional[str] = None
    reconciliation_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class IngestionFileOut(BaseModel):
    id: UUID
    job_id: UUID
    original_filename: str
    mime_type: str
    byte_size: int
    engine: Optional[str] = None
    status: FileStatus
    rows_extracted: int
    needs_review: bool
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    extracted_at: Optional[datetime] = None


class JobDetailOut(BaseModel):
    job: JobOut
    files: list[IngestionFileOut]


class RowsListOut(BaseModel):
    rows: list[ExtractedRowOut]
    total: int
    has_more: bool


class FinalizeResponse(BaseModel):
    reconciliation_id: UUID


# ── Column mapping ───────────────────────────────────────────────────────


class ColumnMappingOut(BaseModel):
    id: UUID
    kind: JobKind
    header_signature: str
    mapping: dict[str, Optional[str]]
    confirmed_by: Optional[UUID] = None
    created_at: datetime
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && pytest tests/ingestion/test_schemas.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/__init__.py backend/app/ingestion/exceptions.py \
        backend/app/ingestion/schemas.py \
        backend/tests/ingestion/__init__.py backend/tests/ingestion/test_schemas.py
git commit -m "feat(ingestion): module skeleton + schemas + exceptions"
```

---

## Phase 2 — Persistence, Storage, Validation, LLM Adapter

### Task 5: Persistence module — jobs CRUD

**Files:**
- Create: `backend/app/ingestion/persistence.py`
- Create: `backend/tests/ingestion/conftest.py`
- Create: `backend/tests/ingestion/test_persistence.py`

- [ ] **Step 1: Write conftest with shared fixtures**

Create `backend/tests/ingestion/conftest.py`:

```python
"""Shared fixtures for ingestion tests."""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest

# Integration tests are gated on a real Supabase URL being present.
pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="INGESTION_TEST_SUPABASE_URL not set; persistence tests require a live DB",
)


@pytest.fixture
def tenant_id() -> UUID:
    raw = os.environ.get("INGESTION_TEST_TENANT_ID")
    if raw:
        return UUID(raw)
    pytest.skip("INGESTION_TEST_TENANT_ID required")


@pytest.fixture
def client_id() -> UUID:
    raw = os.environ.get("INGESTION_TEST_CLIENT_ID")
    if raw:
        return UUID(raw)
    pytest.skip("INGESTION_TEST_CLIENT_ID required")


@pytest.fixture
def user_id() -> UUID:
    raw = os.environ.get("INGESTION_TEST_USER_ID")
    if raw:
        return UUID(raw)
    pytest.skip("INGESTION_TEST_USER_ID required")
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/ingestion/test_persistence.py`:

```python
"""Persistence-layer tests for ingestion jobs/files/rows."""
from datetime import date
from uuid import UUID, uuid4

import pytest

from app.ingestion import persistence as p
from app.ingestion.schemas import (
    ExtractedRowData,
    FileStatus,
    JobKind,
    JobStatus,
    RowStatus,
)


@pytest.mark.asyncio
async def test_create_job_starts_pending(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id,
        client_id=client_id,
        created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    job = await p.get_job(job_id, tenant_id=tenant_id)
    assert job is not None
    assert job["status"] == JobStatus.PENDING.value
    assert job["files_total"] == 0


@pytest.mark.asyncio
async def test_add_file_increments_counter(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id,
        client_id=client_id,
        created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    file_id = await p.add_file(
        job_id=job_id,
        tenant_id=tenant_id,
        storage_path=f"{tenant_id}/{job_id}/file1/x.pdf",
        original_filename="x.pdf",
        mime_type="application/pdf",
        byte_size=12345,
    )
    job = await p.get_job(job_id, tenant_id=tenant_id)
    assert job["files_total"] == 1
    assert isinstance(file_id, UUID)


@pytest.mark.asyncio
async def test_update_job_status_transitions(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    await p.update_job_status(job_id, JobStatus.EXTRACTING, tenant_id=tenant_id)
    j = await p.get_job(job_id, tenant_id=tenant_id)
    assert j["status"] == JobStatus.EXTRACTING.value


@pytest.mark.asyncio
async def test_insert_extracted_rows_and_count_review(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    file_id = await p.add_file(
        job_id=job_id, tenant_id=tenant_id,
        storage_path=f"{tenant_id}/{job_id}/f/y.pdf",
        original_filename="y.pdf", mime_type="application/pdf", byte_size=1,
    )
    rows = [
        ExtractedRowData(
            invoice_no="A1", invoice_date=date(2026, 5, 10),
            taxable_amount_bdt="100", vat_amount_bdt="15",
        ),
        ExtractedRowData(
            invoice_no="A2", invoice_date=date(2026, 5, 11),
            taxable_amount_bdt="200", vat_amount_bdt="30",
        ),
    ]
    await p.insert_extracted_rows(
        job_id=job_id, file_id=file_id, tenant_id=tenant_id,
        rows=rows, status=RowStatus.NEEDS_REVIEW,
        field_warnings_per_row=[[], []],
    )
    listed = await p.list_rows(job_id, tenant_id=tenant_id, only_needs_review=True)
    assert len(listed) == 2
    assert all(r["status"] == RowStatus.NEEDS_REVIEW.value for r in listed)


@pytest.mark.asyncio
async def test_count_needs_review(tenant_id, client_id, user_id):
    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    file_id = await p.add_file(
        job_id=job_id, tenant_id=tenant_id,
        storage_path=f"{tenant_id}/{job_id}/f/z.xlsx",
        original_filename="z.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size=1,
    )
    await p.insert_extracted_rows(
        job_id=job_id, file_id=file_id, tenant_id=tenant_id,
        rows=[ExtractedRowData(
            invoice_no="X", invoice_date=date(2026, 5, 1),
            taxable_amount_bdt="1", vat_amount_bdt="0.15",
        )],
        status=RowStatus.AUTO_PASSED,
        field_warnings_per_row=[[]],
    )
    n = await p.count_needs_review(job_id, tenant_id=tenant_id)
    assert n == 0
```

- [ ] **Step 3: Run — expect failure (module not yet defined)**

```bash
cd backend && pytest tests/ingestion/test_persistence.py -v
```

Expected: ImportError on `app.ingestion.persistence`.

- [ ] **Step 4: Implement `persistence.py`**

Create `backend/app/ingestion/persistence.py`:

```python
"""Database CRUD for ingestion. Uses the supabase admin client.

All callers are expected to have already validated tenant scope (typically
via `get_current_tenant_id`); the `tenant_id` arg is a defense-in-depth
filter on every query.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin
from app.ingestion.schemas import (
    ExtractedRowData,
    FieldWarning,
    FileStatus,
    JobKind,
    JobStatus,
    RowStatus,
)

_TBL_JOBS = "ingestion_jobs"
_TBL_FILES = "ingestion_files"
_TBL_ROWS = "extracted_rows"
_TBL_MAPPINGS = "ingestion_column_mappings"


# ── Jobs ────────────────────────────────────────────────────────────────


async def create_job(
    *,
    tenant_id: UUID,
    client_id: UUID,
    created_by: UUID,
    kind: JobKind,
    period_start: date,
    period_end: date,
) -> UUID:
    sb = get_supabase_admin()

    def _insert():
        return (
            sb.table(_TBL_JOBS)
            .insert({
                "tenant_id": str(tenant_id),
                "client_id": str(client_id),
                "created_by": str(created_by),
                "kind": kind.value,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "status": JobStatus.PENDING.value,
            })
            .execute()
        )

    res = await asyncio.to_thread(_insert)
    return UUID(res.data[0]["id"])


async def get_job(job_id: UUID, *, tenant_id: UUID) -> Optional[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_JOBS)
            .select("*")
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def update_job_status(
    job_id: UUID, status: JobStatus, *, tenant_id: UUID,
    error_summary: Optional[str] = None,
    reconciliation_id: Optional[UUID] = None,
) -> None:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {"status": status.value}
    if error_summary is not None:
        payload["error_summary"] = error_summary
    if reconciliation_id is not None:
        payload["reconciliation_id"] = str(reconciliation_id)
    if status == JobStatus.COMPLETED:
        payload["completed_at"] = datetime.utcnow().isoformat()

    def _u():
        return (
            sb.table(_TBL_JOBS)
            .update(payload)
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def increment_files_done(job_id: UUID, *, tenant_id: UUID) -> None:
    """Atomic +1 on files_done via Postgres function call."""
    sb = get_supabase_admin()

    def _rpc():
        # Inline RPC via raw SQL through PostgREST: use a row update using
        # the supabase client's postgrest filter chain. supabase-py 2.x
        # doesn't support raw expressions; fall back to read-modify-write
        # under a single transaction is not possible from the client either.
        # For the MVP, do a read-then-update; race is acceptable because
        # only one worker holds a file's lease at a time.
        cur = (
            sb.table(_TBL_JOBS)
            .select("files_done")
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .single()
            .execute()
        )
        new_val = (cur.data["files_done"] or 0) + 1
        return (
            sb.table(_TBL_JOBS)
            .update({"files_done": new_val})
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_rpc)


async def recompute_row_counts(job_id: UUID, *, tenant_id: UUID) -> None:
    """Refresh rows_total and rows_needs_review on the job from extracted_rows."""
    sb = get_supabase_admin()

    def _q():
        total = (
            sb.table(_TBL_ROWS)
            .select("id", count="exact")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )
        needs = (
            sb.table(_TBL_ROWS)
            .select("id", count="exact")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .eq("status", RowStatus.NEEDS_REVIEW.value)
            .execute()
        )
        return total.count or 0, needs.count or 0

    rows_total, rows_needs_review = await asyncio.to_thread(_q)

    def _u():
        return (
            sb.table(_TBL_JOBS)
            .update({
                "rows_total": rows_total,
                "rows_needs_review": rows_needs_review,
            })
            .eq("id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Files ───────────────────────────────────────────────────────────────


async def add_file(
    *,
    job_id: UUID,
    tenant_id: UUID,
    storage_path: str,
    original_filename: str,
    mime_type: str,
    byte_size: int,
) -> UUID:
    sb = get_supabase_admin()

    def _insert():
        res = (
            sb.table(_TBL_FILES)
            .insert({
                "job_id": str(job_id),
                "tenant_id": str(tenant_id),
                "storage_path": storage_path,
                "original_filename": original_filename,
                "mime_type": mime_type,
                "byte_size": byte_size,
                "status": FileStatus.QUEUED.value,
            })
            .execute()
        )
        # Bump files_total atomically
        cur = (
            sb.table(_TBL_JOBS)
            .select("files_total")
            .eq("id", str(job_id))
            .single()
            .execute()
        )
        new_total = (cur.data["files_total"] or 0) + 1
        sb.table(_TBL_JOBS).update({"files_total": new_total}).eq(
            "id", str(job_id)
        ).execute()
        return res

    res = await asyncio.to_thread(_insert)
    return UUID(res.data[0]["id"])


async def list_files(job_id: UUID, *, tenant_id: UUID) -> list[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_FILES)
            .select("*")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .order("created_at")
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


async def update_file(
    file_id: UUID,
    *,
    tenant_id: UUID,
    status: Optional[FileStatus] = None,
    engine: Optional[str] = None,
    rows_extracted: Optional[int] = None,
    needs_review: Optional[bool] = None,
    warnings: Optional[list[dict[str, Any]]] = None,
    error: Optional[str] = None,
    extracted_at: Optional[datetime] = None,
    extraction_started_at: Optional[datetime] = None,
) -> None:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {}
    if status is not None:
        payload["status"] = status.value
    if engine is not None:
        payload["engine"] = engine
    if rows_extracted is not None:
        payload["rows_extracted"] = rows_extracted
    if needs_review is not None:
        payload["needs_review"] = needs_review
    if warnings is not None:
        payload["warnings"] = warnings
    if error is not None:
        payload["error"] = error
    if extracted_at is not None:
        payload["extracted_at"] = extracted_at.isoformat()
    if extraction_started_at is not None:
        payload["extraction_started_at"] = extraction_started_at.isoformat()
    if not payload:
        return

    def _u():
        return (
            sb.table(_TBL_FILES)
            .update(payload)
            .eq("id", str(file_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Extracted rows ──────────────────────────────────────────────────────


async def insert_extracted_rows(
    *,
    job_id: UUID,
    file_id: UUID,
    tenant_id: UUID,
    rows: list[ExtractedRowData],
    status: RowStatus,
    field_warnings_per_row: list[list[FieldWarning]],
    source_pages: Optional[list[Optional[int]]] = None,
) -> list[UUID]:
    if len(rows) != len(field_warnings_per_row):
        raise ValueError("rows and field_warnings_per_row must be same length")
    if source_pages is not None and len(source_pages) != len(rows):
        raise ValueError("source_pages must match rows length")

    sb = get_supabase_admin()
    payload = []
    for i, row in enumerate(rows):
        rec = {
            "job_id": str(job_id),
            "file_id": str(file_id),
            "tenant_id": str(tenant_id),
            "row_data": row.model_dump(mode="json"),
            "row_data_original": row.model_dump(mode="json"),
            "status": status.value,
            "field_warnings": [w.model_dump() for w in field_warnings_per_row[i]],
        }
        if source_pages is not None:
            rec["source_page_no"] = source_pages[i]
        payload.append(rec)

    if not payload:
        return []

    def _ins():
        return sb.table(_TBL_ROWS).insert(payload).execute()

    res = await asyncio.to_thread(_ins)
    return [UUID(r["id"]) for r in (res.data or [])]


async def list_rows(
    job_id: UUID,
    *,
    tenant_id: UUID,
    only_needs_review: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        q = (
            sb.table(_TBL_ROWS)
            .select("*")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .order("created_at")
            .range(offset, offset + limit - 1)
        )
        if only_needs_review:
            q = q.eq("status", RowStatus.NEEDS_REVIEW.value)
        return q.execute()

    res = await asyncio.to_thread(_q)
    return res.data or []


async def count_needs_review(job_id: UUID, *, tenant_id: UUID) -> int:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_ROWS)
            .select("id", count="exact")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .eq("status", RowStatus.NEEDS_REVIEW.value)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.count or 0


async def update_row(
    row_id: UUID,
    *,
    tenant_id: UUID,
    row_data: Optional[ExtractedRowData] = None,
    status: Optional[RowStatus] = None,
    reviewed_by: Optional[UUID] = None,
) -> None:
    sb = get_supabase_admin()
    payload: dict[str, Any] = {}
    if row_data is not None:
        payload["row_data"] = row_data.model_dump(mode="json")
    if status is not None:
        payload["status"] = status.value
    if reviewed_by is not None:
        payload["reviewed_by"] = str(reviewed_by)
        payload["reviewed_at"] = datetime.utcnow().isoformat()
    if not payload:
        return

    def _u():
        return (
            sb.table(_TBL_ROWS)
            .update(payload)
            .eq("id", str(row_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def list_confirmed_rows(
    job_id: UUID, *, tenant_id: UUID
) -> list[dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_ROWS)
            .select("*")
            .eq("job_id", str(job_id))
            .eq("tenant_id", str(tenant_id))
            .in_("status", [
                RowStatus.AUTO_PASSED.value,
                RowStatus.CONFIRMED.value,
                RowStatus.EDITED.value,
            ])
            .order("created_at")
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


# ── Column mappings cache ────────────────────────────────────────────────


async def get_cached_mapping(
    *, tenant_id: UUID, kind: JobKind, header_signature: str
) -> Optional[dict[str, Optional[str]]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table(_TBL_MAPPINGS)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("kind", kind.value)
            .eq("header_signature", header_signature)
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    if res.data:
        return res.data[0]["mapping"]
    return None


async def upsert_mapping(
    *,
    tenant_id: UUID,
    kind: JobKind,
    header_signature: str,
    mapping: dict[str, Optional[str]],
    confirmed_by: Optional[UUID] = None,
) -> UUID:
    sb = get_supabase_admin()
    payload = {
        "tenant_id": str(tenant_id),
        "kind": kind.value,
        "header_signature": header_signature,
        "mapping": mapping,
    }
    if confirmed_by is not None:
        payload["confirmed_by"] = str(confirmed_by)

    def _up():
        return (
            sb.table(_TBL_MAPPINGS)
            .upsert(payload, on_conflict="tenant_id,kind,header_signature")
            .execute()
        )

    res = await asyncio.to_thread(_up)
    return UUID(res.data[0]["id"])
```

- [ ] **Step 5: Run tests — expect pass when DB env vars set**

```bash
cd backend && \
  INGESTION_TEST_SUPABASE_URL=$SUPABASE_URL \
  INGESTION_TEST_TENANT_ID=<demo-tenant-uuid> \
  INGESTION_TEST_CLIENT_ID=<demo-client-uuid> \
  INGESTION_TEST_USER_ID=<demo-user-uuid> \
  pytest tests/ingestion/test_persistence.py -v
```

Expected: 5 passed. Without env vars, tests skip cleanly.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/persistence.py backend/tests/ingestion/conftest.py \
        backend/tests/ingestion/test_persistence.py
git commit -m "feat(ingestion): persistence module + tests (jobs/files/rows/mappings CRUD)"
```

---

### Task 6: Storage module — upload/download originals

**Files:**
- Create: `backend/app/ingestion/storage.py`
- Create: `backend/tests/ingestion/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/ingestion/test_storage.py`:

```python
"""Storage module tests (gated on real Supabase Storage)."""
from uuid import uuid4

import pytest

from app.ingestion import storage as s


@pytest.mark.asyncio
async def test_upload_then_download_roundtrip(tenant_id):
    job_id = uuid4()
    file_id = uuid4()
    payload = b"hello-world-" + str(uuid4()).encode()
    path = await s.upload_original(
        tenant_id=tenant_id,
        job_id=job_id,
        file_id=file_id,
        filename="test.bin",
        content=payload,
        mime_type="application/octet-stream",
    )
    assert path.startswith(f"{tenant_id}/{job_id}/{file_id}/")
    got = await s.download_original(path)
    assert got == payload


@pytest.mark.asyncio
async def test_signed_url_returns_string(tenant_id):
    job_id = uuid4()
    file_id = uuid4()
    path = await s.upload_original(
        tenant_id=tenant_id, job_id=job_id, file_id=file_id,
        filename="x.txt", content=b"x", mime_type="text/plain",
    )
    url = await s.create_signed_url(path, expires_in_seconds=60)
    assert isinstance(url, str) and url.startswith("http")
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_storage.py -v
```

Expected: ImportError on `app.ingestion.storage`.

- [ ] **Step 3: Implement `storage.py`**

Create `backend/app/ingestion/storage.py`:

```python
"""Supabase Storage I/O for the ingestion-files bucket."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin

BUCKET = "ingestion-files"


async def upload_original(
    *,
    tenant_id: UUID,
    job_id: UUID,
    file_id: UUID,
    filename: str,
    content: bytes,
    mime_type: str,
) -> str:
    """Upload an original file, return the storage path."""
    path = f"{tenant_id}/{job_id}/{file_id}/{filename}"
    sb = get_supabase_admin()

    def _up():
        sb.storage.from_(BUCKET).upload(
            path=path,
            file=content,
            file_options={"content-type": mime_type, "upsert": "false"},
        )

    await asyncio.to_thread(_up)
    return path


async def download_original(path: str) -> bytes:
    sb = get_supabase_admin()

    def _dl():
        return sb.storage.from_(BUCKET).download(path)

    return await asyncio.to_thread(_dl)


async def create_signed_url(path: str, *, expires_in_seconds: int = 60) -> str:
    """Time-limited public URL for the review UI's file viewer."""
    sb = get_supabase_admin()

    def _sign():
        res: dict[str, Any] = sb.storage.from_(BUCKET).create_signed_url(
            path, expires_in_seconds
        )
        return res["signedURL"]

    return await asyncio.to_thread(_sign)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && \
  INGESTION_TEST_SUPABASE_URL=$SUPABASE_URL \
  INGESTION_TEST_TENANT_ID=<demo-tenant-uuid> \
  pytest tests/ingestion/test_storage.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/storage.py backend/tests/ingestion/test_storage.py
git commit -m "feat(ingestion): storage module for ingestion-files bucket"
```

---

### Task 7: Validation module — BIN, date, 15% rule

**Files:**
- Create: `backend/app/ingestion/validation.py`
- Create: `backend/tests/ingestion/test_validation.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/ingestion/test_validation.py`:

```python
"""Tests for deterministic field-level validators."""
from datetime import date
from decimal import Decimal

from app.ingestion.schemas import ExtractedRowData, JobKind
from app.ingestion.validation import validate_row


def _row(**over):
    base = dict(
        invoice_no="INV-1",
        supplier_bin="123456789",
        supplier_name="ACME",
        invoice_date=date(2026, 5, 10),
        taxable_amount_bdt=Decimal("1000.00"),
        vat_amount_bdt=Decimal("150.00"),
    )
    base.update(over)
    return ExtractedRowData(**base)


def test_clean_purchase_row_has_no_warnings():
    warnings = validate_row(
        _row(),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    assert warnings == []


def test_short_bin_is_flagged():
    warnings = validate_row(
        _row(supplier_bin="123"),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.field == "supplier_bin" and w.code == "BIN_FORMAT" for w in warnings)


def test_date_outside_period_flagged_soft():
    warnings = validate_row(
        _row(invoice_date=date(2026, 4, 15)),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.field == "invoice_date" and w.code == "DATE_OUT_OF_PERIOD" for w in warnings)


def test_vat_outside_15pct_band_flagged():
    # 15% of 1000 = 150; VAT of 100 should flag
    warnings = validate_row(
        _row(vat_amount_bdt=Decimal("100.00")),
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.code == "VAT_RATIO_UNUSUAL" for w in warnings)


def test_supplier_export_requires_buyer_bin():
    warnings = validate_row(
        _row(buyer_bin=None, supplier_bin=None),
        kind=JobKind.SUPPLIER_EXPORT,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
    )
    assert any(w.field == "buyer_bin" and w.code == "BIN_MISSING" for w in warnings)
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_validation.py -v
```

Expected: ImportError on `app.ingestion.validation`.

- [ ] **Step 3: Implement `validation.py`**

Create `backend/app/ingestion/validation.py`:

```python
"""Deterministic field-level validators run AFTER extraction, BEFORE review.

These produce field-level warnings to guide the reviewer's eye. They never
auto-reject a row — that's a deliberate design choice (see spec §5).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.ingestion.schemas import ExtractedRowData, FieldWarning, JobKind

_BIN_RE = re.compile(r"^\d{9,13}$")


def _bin_warning(field: str, value: str | None) -> list[FieldWarning]:
    if value is None or value == "":
        return [FieldWarning(
            field=field, code="BIN_MISSING",
            message=f"{field} is empty",
        )]
    if not _BIN_RE.match(value):
        return [FieldWarning(
            field=field, code="BIN_FORMAT",
            message=f"{field}='{value}' is not 9-13 digits",
        )]
    return []


def _date_warning(value: date, period_start: date, period_end: date) -> list[FieldWarning]:
    if value < period_start or value > period_end:
        return [FieldWarning(
            field="invoice_date", code="DATE_OUT_OF_PERIOD",
            message=f"invoice_date {value} is outside {period_start}..{period_end}",
        )]
    return []


def _vat_ratio_warning(taxable: Decimal, vat: Decimal) -> list[FieldWarning]:
    if taxable <= 0:
        return []
    ratio = vat / taxable
    # Standard NBR rate is 15%; many goods/services use other reduced rates
    # (5%, 7.5%, 10%). Soft-flag when ratio is below 4% or above 16%.
    if ratio < Decimal("0.04") or ratio > Decimal("0.16"):
        pct = float(ratio) * 100
        return [FieldWarning(
            field="vat_amount_bdt", code="VAT_RATIO_UNUSUAL",
            message=f"VAT/Taxable = {pct:.1f}% (outside 4-16% sanity band)",
        )]
    return []


def validate_row(
    row: ExtractedRowData,
    *,
    kind: JobKind,
    period_start: date,
    period_end: date,
) -> list[FieldWarning]:
    """Return a list of field warnings for this row. Empty list = clean."""
    warnings: list[FieldWarning] = []

    if kind == JobKind.PURCHASE_REGISTER:
        warnings += _bin_warning("supplier_bin", row.supplier_bin)
    elif kind == JobKind.SUPPLIER_EXPORT:
        warnings += _bin_warning("buyer_bin", row.buyer_bin)

    warnings += _date_warning(row.invoice_date, period_start, period_end)
    warnings += _vat_ratio_warning(row.taxable_amount_bdt, row.vat_amount_bdt)

    return warnings
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && pytest tests/ingestion/test_validation.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/validation.py backend/tests/ingestion/test_validation.py
git commit -m "feat(ingestion): field-level validation (BIN/date/VAT-ratio)"
```

---

### Task 8: LLM adapter interface + Stub implementation

**Files:**
- Create: `backend/app/ingestion/llm.py`
- Create: `backend/tests/ingestion/test_llm_stub.py`

- [ ] **Step 1: Write the failing tests for the stub**

Create `backend/tests/ingestion/test_llm_stub.py`:

```python
"""Tests for the StubLLMAdapter — the deterministic test double used in CI."""
from datetime import date

import pytest

from app.ingestion.llm import (
    StubLLMAdapter,
    LLMUnavailableError,
    column_signature,
)
from app.ingestion.schemas import JobKind


def test_column_signature_is_order_independent():
    a = column_signature(["Invoice No", "Supplier BIN", "Date"])
    b = column_signature(["date", "INVOICE NO", "supplier bin"])
    assert a == b


def test_stub_returns_canned_column_mapping():
    sig = column_signature(["বিল নং", "BIN", "তারিখ", "মোট", "VAT"])
    stub = StubLLMAdapter(
        column_mappings={
            sig: {
                "invoice_no": "বিল নং",
                "supplier_bin": "BIN",
                "supplier_name": None,
                "invoice_date": "তারিখ",
                "taxable_amount_bdt": "মোট",
                "vat_amount_bdt": "VAT",
            }
        }
    )
    out = stub.map_columns(
        headers=["বিল নং", "BIN", "তারিখ", "মোট", "VAT"],
        sample_rows=[],
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert out["invoice_no"] == "বিল নং"
    assert out["supplier_name"] is None


def test_stub_raises_when_unmocked_input():
    stub = StubLLMAdapter(column_mappings={})
    with pytest.raises(LLMUnavailableError):
        stub.map_columns(
            headers=["X"], sample_rows=[],
            kind=JobKind.PURCHASE_REGISTER,
        )


def test_stub_extract_rows_returns_canned():
    stub = StubLLMAdapter(
        extractions={
            "fake-payload-key": [
                {
                    "invoice_no": "INV-1",
                    "supplier_bin": "123456789",
                    "supplier_name": "ACME",
                    "invoice_date": "2026-05-10",
                    "taxable_amount_bdt": "1000.00",
                    "vat_amount_bdt": "150.00",
                }
            ]
        }
    )
    rows = stub.extract_rows(
        text="ignored", lookup_key="fake-payload-key",
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert len(rows) == 1
    assert rows[0]["invoice_no"] == "INV-1"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_llm_stub.py -v
```

Expected: ImportError on `app.ingestion.llm`.

- [ ] **Step 3: Implement `llm.py` with adapter interface + stub + Gemini stub-shell**

Create `backend/app/ingestion/llm.py`:

```python
"""LLM adapter interface + StubLLMAdapter (CI) + GeminiLLMAdapter (real).

The real Gemini implementation is wired in Task 9. This task ships only the
interface and the test stub so all subsequent tasks can be developed and
tested without network access.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional, Protocol

from app.ingestion.schemas import JobKind


class LLMUnavailableError(Exception):
    """Raised by the stub when it has no canned response for the given input.

    The real adapter raises a different exception (network/quota); the stub
    raising LLMUnavailableError is purely a test-discipline tool — if a test
    triggers this, that test is missing a mock entry.
    """


def column_signature(headers: list[str]) -> str:
    """Order-independent, case-insensitive hash of a header set.

    Used as the cache key for column_mappings AND as the lookup key for
    StubLLMAdapter.column_mappings in tests.
    """
    norm = sorted({(h or "").strip().lower() for h in headers if h})
    return hashlib.sha256("|".join(norm).encode()).hexdigest()


class LLMAdapter(Protocol):
    """Two LLM-touching operations the ingestion module needs."""

    def map_columns(
        self,
        *,
        headers: list[str],
        sample_rows: list[list[str]],
        kind: JobKind,
    ) -> dict[str, Optional[str]]:
        """Return mapping from canonical_field -> source column name (or None)."""

    def extract_rows(
        self,
        *,
        text: str,
        lookup_key: str,
        kind: JobKind,
        images: Optional[list[bytes]] = None,
    ) -> list[dict[str, Any]]:
        """Extract rows from text+optional images. Returns list of dicts
        matching ExtractedRowData fields (as JSON-serializable values).
        """


class StubLLMAdapter:
    """Test double. Deterministic — given input X, returns canned Y or raises.

    Inject into tests via dependency injection; never used in production.
    """

    def __init__(
        self,
        *,
        column_mappings: Optional[dict[str, dict[str, Optional[str]]]] = None,
        extractions: Optional[dict[str, list[dict[str, Any]]]] = None,
    ) -> None:
        self._column_mappings = column_mappings or {}
        self._extractions = extractions or {}

    def map_columns(
        self,
        *,
        headers: list[str],
        sample_rows: list[list[str]],
        kind: JobKind,
    ) -> dict[str, Optional[str]]:
        sig = column_signature(headers)
        if sig not in self._column_mappings:
            raise LLMUnavailableError(
                f"Stub has no canned mapping for headers signature {sig[:12]}…"
            )
        return self._column_mappings[sig]

    def extract_rows(
        self,
        *,
        text: str,
        lookup_key: str,
        kind: JobKind,
        images: Optional[list[bytes]] = None,
    ) -> list[dict[str, Any]]:
        if lookup_key not in self._extractions:
            raise LLMUnavailableError(
                f"Stub has no canned extraction for lookup_key {lookup_key!r}"
            )
        return self._extractions[lookup_key]


# Module-level singleton plumbing so engines can ask for the adapter without
# having a hardcoded dependency on a specific impl. Tests override via
# `set_llm_adapter(StubLLMAdapter(...))`.

_adapter: LLMAdapter | None = None


def set_llm_adapter(adapter: LLMAdapter) -> None:
    global _adapter
    _adapter = adapter


def get_llm_adapter() -> LLMAdapter:
    if _adapter is None:
        raise RuntimeError(
            "LLM adapter not initialised. Call set_llm_adapter() at startup "
            "(production: GeminiLLMAdapter; tests: StubLLMAdapter)."
        )
    return _adapter
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && pytest tests/ingestion/test_llm_stub.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/llm.py backend/tests/ingestion/test_llm_stub.py
git commit -m "feat(ingestion): LLM adapter interface + StubLLMAdapter for tests"
```

---

### Task 9: Gemini Flash LLM implementation

**Files:**
- Modify: `backend/app/ingestion/llm.py`
- Create: `backend/tests/ingestion/test_llm_gemini.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Write the failing test (gated on GEMINI_API_KEY, marked `live`)**

Create `backend/tests/ingestion/test_llm_gemini.py`:

```python
"""Live tests for GeminiLLMAdapter. Skipped unless GEMINI_API_KEY set
AND -m live flag passed (e.g. pytest -m live)."""
import os

import pytest

from app.ingestion.llm import GeminiLLMAdapter
from app.ingestion.schemas import JobKind

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set",
    ),
]


def test_map_columns_bangla_headers():
    adapter = GeminiLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    out = adapter.map_columns(
        headers=["বিল নং", "BIN", "তারিখ", "মোট", "VAT"],
        sample_rows=[
            ["INV-1", "123456789", "2026-05-10", "1000.00", "150.00"],
        ],
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert out["invoice_no"] == "বিল নং"
    assert out["supplier_bin"] == "BIN"
    assert out["taxable_amount_bdt"] == "মোট"
    assert out["vat_amount_bdt"] == "VAT"
    assert out["invoice_date"] == "তারিখ"


def test_extract_rows_text_mode():
    adapter = GeminiLLMAdapter(api_key=os.environ["GEMINI_API_KEY"])
    text = (
        "Tax Invoice\n"
        "Mushak 6.3\n"
        "Invoice No: INV-2026-001\n"
        "Date: 15/05/2026\n"
        "Supplier: ACME Ltd, BIN 987654321\n"
        "Taxable: BDT 5,000.00\n"
        "VAT (15%): BDT 750.00\n"
    )
    rows = adapter.extract_rows(
        text=text, lookup_key="ignored-in-real",
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert len(rows) == 1
    assert rows[0]["invoice_no"] == "INV-2026-001"
    assert rows[0]["supplier_bin"] == "987654321"
```

Add the `live` marker to `backend/pyproject.toml` or `backend/pytest.ini` (whichever exists). If neither exists, add to `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "live: marks tests that hit real external services (deselect with -m 'not live')",
]
```

- [ ] **Step 2: Run — expect failure (`GeminiLLMAdapter` not defined)**

```bash
cd backend && pytest tests/ingestion/test_llm_gemini.py -v
```

Expected: ImportError on `GeminiLLMAdapter` (or skip if marker filtering active).

- [ ] **Step 3: Implement `GeminiLLMAdapter`**

Append to `backend/app/ingestion/llm.py`:

```python
# ─────────────────────────────────────────────────────────────────────────
# Real Gemini implementation
# ─────────────────────────────────────────────────────────────────────────

import json as _json
from typing import cast

import google.generativeai as genai


_MODEL = "gemini-2.5-flash"

_SCHEMA_FIELDS = [
    "invoice_no", "supplier_bin", "supplier_name", "buyer_bin",
    "invoice_date", "taxable_amount_bdt", "vat_amount_bdt",
]


_COLUMN_MAP_PROMPT = """\
You map column headers from a tax invoice register to a canonical schema
used by HishabAI's reconciliation engine for Bangladesh VAT.

Canonical fields:
  - invoice_no            (Mushak invoice / bill number; the unique reference)
  - supplier_bin          (BIN of the supplier — for purchase registers)
  - supplier_name         (supplier business name)
  - buyer_bin             (BIN of the buyer — for supplier-export filings)
  - invoice_date          (date of the invoice; any locale date format)
  - taxable_amount_bdt    (the pre-VAT taxable value, in Bangladeshi Taka)
  - vat_amount_bdt        (the VAT charged, in Bangladeshi Taka)

The headers may be in English, Bangla, or mixed. Common Bangla forms:
  বিল নং / চালান নং (invoice no), সরবরাহকারী BIN (supplier_bin),
  তারিখ (date), মোট মূল্য / করযোগ্য মূল্য (taxable), মূসক / VAT (vat).

Headers: {headers}

Sample rows (first 3):
{samples}

Job kind: {kind}

Return a JSON object mapping each canonical field to the EXACT source
column name (string) or null if no plausible source exists. Do not invent
columns. Do not include any field that is not in the canonical list above.
"""


_EXTRACT_PROMPT = """\
You extract Bangladesh VAT invoice data into a strict JSON schema.

Job kind: {kind}

Canonical fields per row:
{fields}

For dates, return ISO 8601 (YYYY-MM-DD).
For amounts, return numeric strings with 2 decimals (e.g. "1234.50").
For BINs, return digit strings of 9-13 chars or null.

If you can identify multiple distinguishable invoices in the input, return
one row per invoice. If the input is unreadable or contains no invoice
data, return an empty array.

Do not include keys outside the canonical list. Do not return null
where a string is required (invoice_no, invoice_date,
taxable_amount_bdt, vat_amount_bdt).

Input:
---
{text}
---
"""


class GeminiLLMAdapter:
    """Production LLM adapter using Google's google-generativeai SDK
    against the Gemini 2.5 Flash model.

    Configured with an API key (the simplest auth path). For Vertex AI,
    swap in `vertexai.generative_models.GenerativeModel` with the same
    method shape and a service-account credential.
    """

    def __init__(self, *, api_key: str, model_name: str = _MODEL) -> None:
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)

    # ── public API ──

    def map_columns(
        self,
        *,
        headers: list[str],
        sample_rows: list[list[str]],
        kind: JobKind,
    ) -> dict[str, Optional[str]]:
        prompt = _COLUMN_MAP_PROMPT.format(
            headers=_json.dumps(headers, ensure_ascii=False),
            samples=_json.dumps(sample_rows[:3], ensure_ascii=False, indent=2),
            kind=kind.value,
        )
        out = self._call_json(prompt)
        # Normalize: ensure all canonical fields present, default to None
        return {f: out.get(f) for f in _SCHEMA_FIELDS}

    def extract_rows(
        self,
        *,
        text: str,
        lookup_key: str,  # ignored in production; for stub-API parity
        kind: JobKind,
        images: Optional[list[bytes]] = None,
    ) -> list[dict[str, Any]]:
        prompt = _EXTRACT_PROMPT.format(
            kind=kind.value,
            fields="  - " + "\n  - ".join(_SCHEMA_FIELDS),
            text=text,
        )
        if images:
            parts: list[Any] = [prompt]
            for img in images:
                parts.append({"mime_type": "image/png", "data": img})
            res = self._model.generate_content(
                parts,
                generation_config={"response_mime_type": "application/json"},
            )
        else:
            res = self._model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
        try:
            data = _json.loads(res.text)
        except Exception as e:
            raise RuntimeError(f"Gemini returned non-JSON: {res.text[:200]}") from e
        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]
        if not isinstance(data, list):
            raise RuntimeError(f"Gemini returned non-array: {data!r}")
        return cast(list[dict[str, Any]], data)

    # ── helpers ──

    def _call_json(self, prompt: str) -> dict[str, Any]:
        res = self._model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        try:
            return cast(dict[str, Any], _json.loads(res.text))
        except Exception as e:
            raise RuntimeError(f"Gemini returned non-JSON: {res.text[:200]}") from e
```

- [ ] **Step 4: Add env-var stub**

Append to `backend/.env.example`:

```bash

# ─── Ingestion (Phase F) ────────────────────────────────────────────────
# Gemini API key for the adaptive ingestion pipeline (Vertex AI optional swap)
GEMINI_API_KEY=

# Toggle: set INGESTION_ENABLED=true to register the /api/v1/ingestion routes
# and start the ingestion worker. Default is unset (= disabled).
INGESTION_ENABLED=false

# Per-tenant rate caps for the ingestion LLM
INGESTION_MAX_CALLS_PER_MIN=30
INGESTION_MAX_CALLS_PER_DAY=5000

# Per-job upload limits
INGESTION_MAX_FILES_PER_JOB=200
INGESTION_MAX_FILE_SIZE_MB=25
```

- [ ] **Step 5: Verify the live test (optional — run only if you want to spend a Gemini call)**

```bash
cd backend && GEMINI_API_KEY=... pytest tests/ingestion/test_llm_gemini.py -v -m live
```

Expected: 2 passed (or skip if no key).

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/llm.py backend/tests/ingestion/test_llm_gemini.py \
        backend/.env.example
git commit -m "feat(ingestion): GeminiLLMAdapter (gemini-2.5-flash) + env vars"
```

---

## Phase 3 — Engines + MIME Router

### Task 10: Engine base types + protocol

**Files:**
- Create: `backend/app/ingestion/engines/__init__.py`
- Create: `backend/app/ingestion/engines/base.py`
- Create: `backend/tests/ingestion/engines/__init__.py`
- Create: `backend/tests/ingestion/engines/test_base.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/ingestion/engines/__init__.py` empty.

Create `backend/tests/ingestion/engines/test_base.py`:

```python
"""Smoke tests for the engine base types."""
from app.ingestion.engines.base import (
    EXTRACTION_ENGINES,
    ExtractedFileResult,
    ExtractionContext,
)
from app.ingestion.schemas import ExtractedRowData
from datetime import date


def test_extraction_engines_constants_present():
    assert "pandas" in EXTRACTION_ENGINES
    assert "pandas+llm-mapper" in EXTRACTION_ENGINES
    assert "pdfplumber+llm" in EXTRACTION_ENGINES
    assert "gemini-vision" in EXTRACTION_ENGINES


def test_result_construction():
    res = ExtractedFileResult(
        rows=[ExtractedRowData(
            invoice_no="X", invoice_date=date(2026, 5, 1),
            taxable_amount_bdt="1", vat_amount_bdt="0.15",
        )],
        needs_review=False,
        extraction_engine="pandas",
        page_count=1,
        warnings=[],
    )
    assert res.rows[0].invoice_no == "X"


def test_context_carries_period_and_kind():
    from app.ingestion.schemas import JobKind
    ctx = ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )
    assert ctx.kind == JobKind.PURCHASE_REGISTER
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/engines/test_base.py -v
```

- [ ] **Step 3: Implement `engines/base.py`**

Create `backend/app/ingestion/engines/__init__.py`:

```python
"""Per-MIME extraction engines."""
```

Create `backend/app/ingestion/engines/base.py`:

```python
"""Engine protocol + result type + context type.

All engines have the same single entry point:
    extract(file_bytes: bytes, ctx: ExtractionContext) -> ExtractedFileResult
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.ingestion.schemas import ExtractedRowData, JobKind

# Allowed values for ExtractedFileResult.extraction_engine.
# Used by tests to guard against typo drift.
EXTRACTION_ENGINES: set[str] = {
    "pandas",
    "pandas+llm-mapper",
    "pdfplumber+llm",
    "gemini-vision",
    # Reserved for a future cost-saver path; not implemented in v1.
    "tesseract+llm",
}


@dataclass
class ExtractionContext:
    """Per-job context passed into every engine."""
    kind: JobKind
    period_start: date
    period_end: date
    tenant_id: str  # for cache lookups + structlog binding


@dataclass
class ExtractedFileResult:
    """Uniform shape every engine returns."""
    rows: list[ExtractedRowData]
    needs_review: bool
    extraction_engine: str
    page_count: int
    warnings: list[dict] = field(default_factory=list)
    # Optional engine-emitted source-page mapping aligned to `rows`.
    source_pages: list[int | None] | None = None


class Engine(Protocol):
    """Each engine exposes a single sync `extract` (called from to_thread)."""

    name: str

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult: ...
```

- [ ] **Step 4: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/engines/test_base.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/engines/__init__.py backend/app/ingestion/engines/base.py \
        backend/tests/ingestion/engines/__init__.py backend/tests/ingestion/engines/test_base.py
git commit -m "feat(ingestion): engine protocol + result types"
```

---

### Task 11: Pandas canonical engine

**Files:**
- Create: `backend/app/ingestion/engines/pandas_canonical.py`
- Create: `backend/tests/ingestion/engines/test_pandas_canonical.py`
- Create (binary fixture): `backend/tests/ingestion/fixtures/canonical_register.xlsx`

- [ ] **Step 1: Generate the fixture file**

Create `backend/tests/ingestion/fixtures/__init__.py` empty.

Create a quick generator script run once to produce the XLSX fixture (this is a one-off, not committed code — output is committed):

```bash
cd backend && python - <<'PY'
import openpyxl
from pathlib import Path

wb = openpyxl.Workbook()
ws = wb.active
ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
           "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
ws.append(["INV-1", "123456789", "ACME Ltd",
           "2026-05-10", 1000.00, 150.00])
ws.append(["INV-2", "987654321", "Globex BD",
           "2026-05-12", 2000.50, 300.08])
out = Path("tests/ingestion/fixtures/canonical_register.xlsx")
out.parent.mkdir(parents=True, exist_ok=True)
wb.save(out)
print("wrote", out)
PY
```

Verify the file exists at `backend/tests/ingestion/fixtures/canonical_register.xlsx`.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/ingestion/engines/test_pandas_canonical.py`:

```python
"""Pandas canonical-headers engine tests."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.pandas_canonical import PandasCanonicalEngine
from app.ingestion.schemas import JobKind

FIXTURE = Path(__file__).parents[1] / "fixtures" / "canonical_register.xlsx"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_canonical_xlsx_is_handled_returns_two_rows():
    engine = PandasCanonicalEngine()
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert res.extraction_engine == "pandas"
    assert res.needs_review is False
    assert len(res.rows) == 2
    assert res.rows[0].invoice_no == "INV-1"
    assert res.rows[0].taxable_amount_bdt == Decimal("1000.00")
    assert res.rows[0].vat_amount_bdt == Decimal("150.00")


def test_canonical_handles_returns_true_only_for_canonical_headers():
    engine = PandasCanonicalEngine()
    assert engine.handles_headers([
        "Invoice No", "Supplier BIN", "Supplier Name",
        "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
    ], JobKind.PURCHASE_REGISTER) is True
    assert engine.handles_headers([
        "Bill No", "BIN", "Name", "Date", "Amount", "VAT",
    ], JobKind.PURCHASE_REGISTER) is False
```

- [ ] **Step 3: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/engines/test_pandas_canonical.py -v
```

- [ ] **Step 4: Implement `pandas_canonical.py`**

Create `backend/app/ingestion/engines/pandas_canonical.py`:

```python
"""Engine for XLSX/CSV with the existing canonical column headers.

This is a thin wrapper that delegates to the existing reconciliation parser
so behavior is bit-identical to today's flow.
"""
from __future__ import annotations

import io
from typing import cast

import pandas as pd

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.reconciliation.parser import (
    _PURCHASE_COLUMNS,
    _SUPPLIER_COLUMNS,
    parse_purchase_register,
    parse_supplier_export,
)


def _canonical_set(kind: JobKind) -> set[str]:
    cols = _PURCHASE_COLUMNS if kind == JobKind.PURCHASE_REGISTER else _SUPPLIER_COLUMNS
    return set(cols.keys())  # already lowercased keys


class PandasCanonicalEngine:
    name = "pandas"

    def handles_headers(self, headers: list[str], kind: JobKind) -> bool:
        norm = {(h or "").strip().lower() for h in headers}
        return _canonical_set(kind).issubset(norm)

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        # Route to the right existing parser
        if ctx.kind == JobKind.PURCHASE_REGISTER:
            parsed = parse_purchase_register(file_bytes)
        else:
            parsed = parse_supplier_export(file_bytes)

        rows: list[ExtractedRowData] = []
        for r in parsed:
            d = r.model_dump()
            rows.append(ExtractedRowData(**d))

        return ExtractedFileResult(
            rows=rows,
            needs_review=False,  # auto-pass per spec §5
            extraction_engine="pandas",
            page_count=1,
            warnings=[],
        )

    @staticmethod
    def headers_from_bytes(file_bytes: bytes) -> list[str]:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl", nrows=0)
        return [str(c) for c in df.columns]
```

- [ ] **Step 5: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/engines/test_pandas_canonical.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/engines/pandas_canonical.py \
        backend/tests/ingestion/engines/test_pandas_canonical.py \
        backend/tests/ingestion/fixtures/__init__.py \
        backend/tests/ingestion/fixtures/canonical_register.xlsx
git commit -m "feat(ingestion): pandas canonical engine (delegates to existing parser)"
```

---

### Task 12: Pandas LLM-mapper engine (non-canonical headers)

**Files:**
- Create: `backend/app/ingestion/engines/pandas_mapper.py`
- Create: `backend/tests/ingestion/engines/test_pandas_mapper.py`
- Generate: `backend/tests/ingestion/fixtures/bangla_headers.xlsx`

- [ ] **Step 1: Generate fixture**

```bash
cd backend && python - <<'PY'
import openpyxl
from pathlib import Path

wb = openpyxl.Workbook()
ws = wb.active
ws.append(["বিল নং", "BIN", "নাম", "তারিখ", "মোট", "VAT"])
ws.append(["INV-A", "111222333", "Bangla Supplier", "2026-05-15", 500, 75])
ws.append(["INV-B", "444555666", "Other Supplier", "2026-05-16", 1000, 150])
out = Path("tests/ingestion/fixtures/bangla_headers.xlsx")
wb.save(out)
print("wrote", out)
PY
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/ingestion/engines/test_pandas_mapper.py`:

```python
"""Pandas LLM-mapper engine tests — uses StubLLMAdapter."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.pandas_mapper import PandasMapperEngine
from app.ingestion.llm import StubLLMAdapter, column_signature, set_llm_adapter
from app.ingestion.schemas import JobKind

FIXTURE = Path(__file__).parents[1] / "fixtures" / "bangla_headers.xlsx"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_mapper_uses_llm_to_remap_headers_then_parses(monkeypatch):
    sig = column_signature(["বিল নং", "BIN", "নাম", "তারিখ", "মোট", "VAT"])
    set_llm_adapter(StubLLMAdapter(column_mappings={
        sig: {
            "invoice_no": "বিল নং",
            "supplier_bin": "BIN",
            "supplier_name": "নাম",
            "buyer_bin": None,
            "invoice_date": "তারিখ",
            "taxable_amount_bdt": "মোট",
            "vat_amount_bdt": "VAT",
        }
    }))
    engine = PandasMapperEngine()
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert res.extraction_engine == "pandas+llm-mapper"
    assert res.needs_review is False
    assert len(res.rows) == 2
    assert res.rows[0].invoice_no == "INV-A"
    assert res.rows[0].supplier_bin == "111222333"
    assert res.rows[0].supplier_name == "Bangla Supplier"
    assert res.rows[0].taxable_amount_bdt == Decimal("500.00")
```

- [ ] **Step 3: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/engines/test_pandas_mapper.py -v
```

- [ ] **Step 4: Implement `pandas_mapper.py`**

Create `backend/app/ingestion/engines/pandas_mapper.py`:

```python
"""Engine for XLSX/CSV with NON-canonical headers.

Uses the LLM column-mapper to learn a (canonical_field -> source_column)
mapping, applies it, then runs the parser on the rewritten DataFrame.

Mapping is cached in `ingestion_column_mappings` per (tenant, kind,
header_signature). Cache hit → zero LLM cost; cache miss → one Gemini Flash
call. The mapping for a brand-new header signature is also surfaced to the
review UI for user confirmation (see Task 26).
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pandas as pd

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.llm import column_signature, get_llm_adapter
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.ingestion import persistence as p

_CANONICAL = (
    "invoice_no", "supplier_bin", "supplier_name", "buyer_bin",
    "invoice_date", "taxable_amount_bdt", "vat_amount_bdt",
)


def _coerce_date(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return value  # let pydantic raise if unparseable


class PandasMapperEngine:
    name = "pandas+llm-mapper"

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        headers = [str(c) for c in df.columns]
        sig = column_signature(headers)

        # Check cache first
        tenant_uuid = UUID(ctx.tenant_id)
        cached = asyncio.run(
            p.get_cached_mapping(
                tenant_id=tenant_uuid, kind=ctx.kind, header_signature=sig,
            )
        )

        if cached is None:
            sample_rows = df.head(3).fillna("").astype(str).values.tolist()
            mapping = get_llm_adapter().map_columns(
                headers=headers, sample_rows=sample_rows, kind=ctx.kind,
            )
            # Save unconfirmed to cache; user can confirm later via API.
            asyncio.run(p.upsert_mapping(
                tenant_id=tenant_uuid, kind=ctx.kind,
                header_signature=sig, mapping=mapping,
            ))
        else:
            mapping = cached

        # Build rows by walking the mapping
        rows: list[ExtractedRowData] = []
        for _, src in df.iterrows():
            rec: dict[str, Any] = {}
            for canonical_field in _CANONICAL:
                src_col = mapping.get(canonical_field)
                if src_col is None or src_col not in df.columns:
                    continue
                val = src[src_col]
                if pd.isna(val):
                    continue
                if canonical_field == "invoice_date":
                    rec[canonical_field] = _coerce_date(val)
                elif canonical_field in ("taxable_amount_bdt", "vat_amount_bdt"):
                    rec[canonical_field] = Decimal(str(val))
                else:
                    rec[canonical_field] = str(val).strip() or None
            # Required fields must be present; if not, skip the row
            required = {"invoice_no", "invoice_date",
                        "taxable_amount_bdt", "vat_amount_bdt"}
            if not required.issubset(rec.keys()):
                continue
            rows.append(ExtractedRowData(**rec))

        return ExtractedFileResult(
            rows=rows,
            needs_review=False,  # mapping was deterministic once cached
            extraction_engine="pandas+llm-mapper",
            page_count=1,
            warnings=[],
        )
```

- [ ] **Step 5: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/engines/test_pandas_mapper.py -v
```

Expected: 1 passed (DB integration only fires for cache lookup; if no DB, the test will need adjustment — see note).

> **Note:** The mapper engine writes to `ingestion_column_mappings` even on a cache miss. The test above will currently fail without a DB connection because of `asyncio.run(p.get_cached_mapping(...))`. Fix by injecting a mock `persistence` accessor — refactor: replace direct `asyncio.run(p.get_cached_mapping(...))` with a `mapping_cache` parameter passed into `extract`, defaulting to a closure that uses persistence in production. For the MVP a simpler shortcut: detect "test mode" by an env var. **Recommended:** before implementing, refactor the engine to take an optional `mapping_cache` callable so tests can inject a no-op cache. Then revise the test to pass `mapping_cache=lambda **_: None` and an upsert callback that no-ops.

Refactor accordingly: change `extract` to accept `mapping_cache_get` and `mapping_cache_put` keyword args, defaulting to the persistence-backed implementations. Tests pass `lambda **_: None` for both.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/engines/pandas_mapper.py \
        backend/tests/ingestion/engines/test_pandas_mapper.py \
        backend/tests/ingestion/fixtures/bangla_headers.xlsx
git commit -m "feat(ingestion): pandas LLM-mapper engine for non-canonical headers"
```

---

### Task 13: PDF born-digital engine (pdfplumber + LLM normalizer)

**Files:**
- Create: `backend/app/ingestion/engines/pdf_borndigital.py`
- Create: `backend/tests/ingestion/engines/test_pdf_borndigital.py`
- Generate: `backend/tests/ingestion/fixtures/mushak_6.3_borndigital.pdf`

- [ ] **Step 1: Generate fixture (born-digital PDF via reportlab or fpdf)**

```bash
cd backend && pip install reportlab && python - <<'PY'
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

out = Path("tests/ingestion/fixtures/mushak_6.3_borndigital.pdf")
c = canvas.Canvas(str(out), pagesize=A4)
c.setFont("Helvetica", 12)
y = 800
for line in [
    "Tax Invoice (Mushak 6.3)",
    "Invoice No: INV-2026-001",
    "Date: 15/05/2026",
    "Supplier: ACME Ltd",
    "Supplier BIN: 987654321",
    "Buyer: HishabAI Demo Co",
    "Buyer BIN: 111222333",
    "Taxable Amount: BDT 5,000.00",
    "VAT (15%): BDT 750.00",
    "Total: BDT 5,750.00",
]:
    c.drawString(80, y, line); y -= 24
c.save()
print("wrote", out)
PY
```

> reportlab is a dev-only dep — not added to requirements.txt. Install on the developer machine to regenerate fixtures.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/ingestion/engines/test_pdf_borndigital.py`:

```python
"""Born-digital PDF engine tests — uses StubLLMAdapter."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.ingestion.schemas import JobKind

FIXTURE = Path(__file__).parents[1] / "fixtures" / "mushak_6.3_borndigital.pdf"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_borndigital_extracts_one_row(monkeypatch):
    set_llm_adapter(StubLLMAdapter(extractions={
        # Stub uses the lookup_key the engine produces — for tests,
        # the engine accepts an injected lookup_key generator.
        "test-key": [{
            "invoice_no": "INV-2026-001",
            "supplier_bin": "987654321",
            "supplier_name": "ACME Ltd",
            "invoice_date": "2026-05-15",
            "taxable_amount_bdt": "5000.00",
            "vat_amount_bdt": "750.00",
        }],
    }))
    engine = PdfBornDigitalEngine(lookup_key_for_test="test-key")
    res = engine.extract(FIXTURE.read_bytes(), _ctx())
    assert res.extraction_engine == "pdfplumber+llm"
    assert res.needs_review is False
    assert len(res.rows) == 1
    assert res.rows[0].invoice_no == "INV-2026-001"
    assert res.rows[0].taxable_amount_bdt == Decimal("5000.00")


def test_borndigital_text_density_heuristic_passes_for_textful_pdf():
    engine = PdfBornDigitalEngine()
    is_text = engine.has_extractable_text(FIXTURE.read_bytes())
    assert is_text is True
```

- [ ] **Step 3: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/engines/test_pdf_borndigital.py -v
```

- [ ] **Step 4: Implement `pdf_borndigital.py`**

Create `backend/app/ingestion/engines/pdf_borndigital.py`:

```python
"""Engine for born-digital PDFs.

Uses pdfplumber to extract text+tables losslessly, then sends the text
to the LLM with the canonical schema for structured normalization.
Auto-passes (no review) because the text extraction itself is deterministic.
"""
from __future__ import annotations

import hashlib
import io
from typing import Any, Optional

import pdfplumber

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.llm import get_llm_adapter
from app.ingestion.schemas import ExtractedRowData


_TEXT_DENSITY_THRESHOLD = 50  # chars/page; below this we treat as scanned


class PdfBornDigitalEngine:
    name = "pdfplumber+llm"

    def __init__(self, lookup_key_for_test: Optional[str] = None) -> None:
        # Tests inject a fixed lookup_key so StubLLMAdapter responses are stable.
        self._test_key = lookup_key_for_test

    def has_extractable_text(self, file_bytes: bytes) -> bool:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if len(text) >= _TEXT_DENSITY_THRESHOLD:
                    return True
        return False

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        # Pull text + table-stringified content per page
        page_texts: list[str] = []
        page_count = 0
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                # Render tables as plain text so the LLM sees them
                tbl_text = "\n".join(
                    "\n".join(" | ".join(str(c) if c else "" for c in row)
                              for row in t)
                    for t in tables
                )
                page_texts.append(text + ("\n\n" + tbl_text if tbl_text else ""))

        full_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts)
        lookup_key = self._test_key or hashlib.sha256(file_bytes).hexdigest()[:16]

        raw_rows = get_llm_adapter().extract_rows(
            text=full_text,
            lookup_key=lookup_key,
            kind=ctx.kind,
            images=None,
        )
        rows = [ExtractedRowData(**self._coerce(r)) for r in raw_rows]

        return ExtractedFileResult(
            rows=rows,
            needs_review=False,  # auto-pass per spec §5
            extraction_engine="pdfplumber+llm",
            page_count=page_count,
            warnings=[],
        )

    @staticmethod
    def _coerce(d: dict[str, Any]) -> dict[str, Any]:
        # Drop keys outside the canonical schema and normalize None
        keep = {
            "invoice_no", "supplier_bin", "supplier_name", "buyer_bin",
            "invoice_date", "taxable_amount_bdt", "vat_amount_bdt",
        }
        return {k: v for k, v in d.items() if k in keep}
```

- [ ] **Step 5: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/engines/test_pdf_borndigital.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/engines/pdf_borndigital.py \
        backend/tests/ingestion/engines/test_pdf_borndigital.py \
        backend/tests/ingestion/fixtures/mushak_6.3_borndigital.pdf
git commit -m "feat(ingestion): born-digital PDF engine (pdfplumber + LLM normalize)"
```

---

### Task 14: Vision engine (Gemini Flash multi-modal)

**Files:**
- Create: `backend/app/ingestion/engines/vision.py`
- Create: `backend/tests/ingestion/engines/test_vision.py`
- Generate: `backend/tests/ingestion/fixtures/mushak_6.3_scan.pdf` (image-only PDF) and `phone_photo_invoice.jpg`

- [ ] **Step 1: Generate scan + photo fixtures**

```bash
cd backend && pip install reportlab && python - <<'PY'
"""Build an image-only PDF (no text layer) by drawing onto a canvas as a
flattened image, plus a JPEG of the same content for the photo path."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Render the "invoice" as an image
img = Image.new("RGB", (800, 1000), color="white")
draw = ImageDraw.Draw(img)
y = 50
for line in [
    "TAX INVOICE (Mushak 6.3)",
    "Invoice No: SCAN-001",
    "Date: 20/05/2026",
    "Supplier: Beta Trading",
    "Supplier BIN: 222333444",
    "Buyer BIN: 111222333",
    "Taxable: BDT 3,200.00",
    "VAT (15%): BDT 480.00",
]:
    draw.text((50, y), line, fill="black"); y += 50

img.save(Path("tests/ingestion/fixtures/phone_photo_invoice.jpg"), "JPEG", quality=85)

# Wrap the image in a PDF with no text layer
pdf_path = Path("tests/ingestion/fixtures/mushak_6.3_scan.pdf")
buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
c = canvas.Canvas(str(pdf_path))
c.drawImage(ImageReader(buf), 0, 0, width=595, height=842)
c.save()
print("wrote scan + photo")
PY
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/ingestion/engines/test_vision.py`:

```python
"""Vision engine tests — uses StubLLMAdapter; never hits real Gemini."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ingestion.engines.base import ExtractionContext
from app.ingestion.engines.vision import VisionEngine
from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.ingestion.schemas import JobKind

SCAN_PDF = Path(__file__).parents[1] / "fixtures" / "mushak_6.3_scan.pdf"
PHOTO_JPG = Path(__file__).parents[1] / "fixtures" / "phone_photo_invoice.jpg"


def _ctx() -> ExtractionContext:
    return ExtractionContext(
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        tenant_id="00000000-0000-0000-0000-000000000000",
    )


def test_vision_on_scanned_pdf_marks_review_required():
    set_llm_adapter(StubLLMAdapter(extractions={
        "vision-test-key": [{
            "invoice_no": "SCAN-001",
            "supplier_bin": "222333444",
            "buyer_bin": "111222333",
            "invoice_date": "2026-05-20",
            "taxable_amount_bdt": "3200.00",
            "vat_amount_bdt": "480.00",
        }],
    }))
    engine = VisionEngine(lookup_key_for_test="vision-test-key")
    res = engine.extract(SCAN_PDF.read_bytes(), _ctx())
    assert res.extraction_engine == "gemini-vision"
    assert res.needs_review is True
    assert len(res.rows) == 1
    assert res.rows[0].invoice_no == "SCAN-001"


def test_vision_on_jpeg_photo_works():
    set_llm_adapter(StubLLMAdapter(extractions={
        "photo-test-key": [{
            "invoice_no": "SCAN-001",
            "supplier_bin": "222333444",
            "buyer_bin": "111222333",
            "invoice_date": "2026-05-20",
            "taxable_amount_bdt": "3200.00",
            "vat_amount_bdt": "480.00",
        }],
    }))
    engine = VisionEngine(lookup_key_for_test="photo-test-key")
    res = engine.extract(PHOTO_JPG.read_bytes(), _ctx())
    assert res.needs_review is True
    assert len(res.rows) == 1
```

- [ ] **Step 3: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/engines/test_vision.py -v
```

- [ ] **Step 4: Implement `vision.py`**

Create `backend/app/ingestion/engines/vision.py`:

```python
"""Vision engine: scanned PDFs and photos via Gemini Flash multi-modal.

For PDFs: render each page to a PNG with pypdfium2 (no Poppler dep).
For images: HEIC/WEBP convert to PNG via Pillow, then send raw bytes.

Always flagged needs_review per spec §5.
"""
from __future__ import annotations

import hashlib
import io
from typing import Any, Optional

import pypdfium2 as pdfium
from PIL import Image

# Register HEIC support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.llm import get_llm_adapter
from app.ingestion.schemas import ExtractedRowData

_PDF_DPI = 200
_MAX_PAGES_PER_CALL = 10


class VisionEngine:
    name = "gemini-vision"

    def __init__(self, lookup_key_for_test: Optional[str] = None) -> None:
        self._test_key = lookup_key_for_test

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        images = self._to_png_pages(file_bytes)
        page_count = len(images)

        # Chunk if very long
        all_rows: list[dict[str, Any]] = []
        for chunk_start in range(0, page_count, _MAX_PAGES_PER_CALL):
            chunk = images[chunk_start:chunk_start + _MAX_PAGES_PER_CALL]
            lookup_key = self._test_key or hashlib.sha256(
                b"".join(chunk)
            ).hexdigest()[:16]
            rows = get_llm_adapter().extract_rows(
                text="",
                lookup_key=lookup_key,
                kind=ctx.kind,
                images=chunk,
            )
            all_rows.extend(rows)

        rows = [ExtractedRowData(**self._coerce(r)) for r in all_rows]

        return ExtractedFileResult(
            rows=rows,
            needs_review=True,  # MANDATORY per spec §5
            extraction_engine="gemini-vision",
            page_count=page_count,
            warnings=[],
        )

    def _to_png_pages(self, file_bytes: bytes) -> list[bytes]:
        """Return a list of PNG bytes — one per page (PDF) or one entry (image)."""
        # Detect by magic bytes
        if file_bytes[:4] == b"%PDF":
            return self._pdf_to_pngs(file_bytes)
        return [self._normalize_image_to_png(file_bytes)]

    @staticmethod
    def _pdf_to_pngs(file_bytes: bytes) -> list[bytes]:
        out: list[bytes] = []
        pdf = pdfium.PdfDocument(file_bytes)
        for page in pdf:
            bitmap = page.render(scale=_PDF_DPI / 72)
            pil = bitmap.to_pil()
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            out.append(buf.getvalue())
        return out

    @staticmethod
    def _normalize_image_to_png(file_bytes: bytes) -> bytes:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _coerce(d: dict[str, Any]) -> dict[str, Any]:
        return PdfBornDigitalEngine._coerce(d)
```

- [ ] **Step 5: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/engines/test_vision.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/engines/vision.py \
        backend/tests/ingestion/engines/test_vision.py \
        backend/tests/ingestion/fixtures/mushak_6.3_scan.pdf \
        backend/tests/ingestion/fixtures/phone_photo_invoice.jpg
git commit -m "feat(ingestion): Gemini vision engine for scans/photos"
```

---

### Task 15: MIME router

**Files:**
- Create: `backend/app/ingestion/router_engine.py`
- Create: `backend/tests/ingestion/test_router_engine.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/ingestion/test_router_engine.py`:

```python
"""MIME router tests — pure logic, no DB, no LLM."""
from app.ingestion.router_engine import select_engine_name


def _xlsx_bytes_with_headers(headers: list[str]) -> bytes:
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.append(headers)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_canonical_xlsx_routes_to_pandas():
    headers = ["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"]
    name = select_engine_name(
        file_bytes=_xlsx_bytes_with_headers(headers),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        kind="purchase_register",
    )
    assert name == "pandas"


def test_non_canonical_xlsx_routes_to_mapper():
    headers = ["বিল নং", "BIN", "তারিখ", "মোট", "VAT"]
    name = select_engine_name(
        file_bytes=_xlsx_bytes_with_headers(headers),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        kind="purchase_register",
    )
    assert name == "pandas+llm-mapper"


def test_pdf_with_text_routes_to_borndigital():
    from pathlib import Path
    p = Path("tests/ingestion/fixtures/mushak_6.3_borndigital.pdf").read_bytes()
    name = select_engine_name(
        file_bytes=p, mime="application/pdf", kind="purchase_register",
    )
    assert name == "pdfplumber+llm"


def test_scanned_pdf_routes_to_vision():
    from pathlib import Path
    p = Path("tests/ingestion/fixtures/mushak_6.3_scan.pdf").read_bytes()
    name = select_engine_name(
        file_bytes=p, mime="application/pdf", kind="purchase_register",
    )
    assert name == "gemini-vision"


def test_image_routes_to_vision():
    from pathlib import Path
    p = Path("tests/ingestion/fixtures/phone_photo_invoice.jpg").read_bytes()
    name = select_engine_name(
        file_bytes=p, mime="image/jpeg", kind="purchase_register",
    )
    assert name == "gemini-vision"


def test_unsupported_mime_raises():
    import pytest
    from app.ingestion.exceptions import UnsupportedFileTypeError
    with pytest.raises(UnsupportedFileTypeError):
        select_engine_name(
            file_bytes=b"hi", mime="application/zip",
            kind="purchase_register",
        )
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_router_engine.py -v
```

- [ ] **Step 3: Implement `router_engine.py`**

Create `backend/app/ingestion/router_engine.py`:

```python
"""MIME → engine name router.

Pure logic; no I/O. Engine selection is deterministic from
(MIME, file bytes, kind). Selection happens BEFORE storage upload so
we record the chosen engine on `ingestion_files.engine` immediately.
"""
from __future__ import annotations

from app.ingestion.engines.pandas_canonical import PandasCanonicalEngine
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.exceptions import UnsupportedFileTypeError
from app.ingestion.schemas import JobKind


_XLSX_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "text/tab-separated-values",
}

_PDF_MIMES = {"application/pdf"}

_IMAGE_MIMES = {
    "image/jpeg", "image/jpg", "image/png", "image/tiff",
    "image/webp", "image/heic", "image/heif",
}


def _kind_enum(kind: str | JobKind) -> JobKind:
    return kind if isinstance(kind, JobKind) else JobKind(kind)


def select_engine_name(
    *, file_bytes: bytes, mime: str, kind: str | JobKind,
    filename: str = "<unknown>",
) -> str:
    k = _kind_enum(kind)

    if mime in _XLSX_MIMES:
        canonical = PandasCanonicalEngine()
        try:
            headers = canonical.headers_from_bytes(file_bytes)
        except Exception:
            return "pandas+llm-mapper"
        if canonical.handles_headers(headers, k):
            return "pandas"
        return "pandas+llm-mapper"

    if mime in _PDF_MIMES:
        bd = PdfBornDigitalEngine()
        try:
            return "pdfplumber+llm" if bd.has_extractable_text(file_bytes) else "gemini-vision"
        except Exception:
            return "gemini-vision"

    if mime in _IMAGE_MIMES:
        return "gemini-vision"

    raise UnsupportedFileTypeError(filename=filename, mime=mime)
```

- [ ] **Step 4: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/test_router_engine.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/router_engine.py \
        backend/tests/ingestion/test_router_engine.py
git commit -m "feat(ingestion): MIME → engine router"
```

---

## Phase 4 — Lifecycle, Handoff, Worker

### Task 16: Lifecycle state machine

**Files:**
- Create: `backend/app/ingestion/lifecycle.py`
- Create: `backend/tests/ingestion/test_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/ingestion/test_lifecycle.py`:

```python
"""Pure-logic tests for the state machine — no DB needed."""
import pytest

from app.ingestion.exceptions import InvalidStateTransitionError
from app.ingestion.lifecycle import assert_can_transition, next_status_for_extraction
from app.ingestion.schemas import JobStatus


def test_pending_to_extracting_ok():
    assert_can_transition(JobStatus.PENDING, JobStatus.EXTRACTING)


def test_extracting_to_ready_for_review_ok():
    assert_can_transition(JobStatus.EXTRACTING, JobStatus.READY_FOR_REVIEW)


def test_completed_to_anything_blocked():
    with pytest.raises(InvalidStateTransitionError):
        assert_can_transition(JobStatus.COMPLETED, JobStatus.PENDING)


def test_failed_is_terminal():
    with pytest.raises(InvalidStateTransitionError):
        assert_can_transition(JobStatus.FAILED, JobStatus.RECONCILING)


def test_extraction_done_with_review_needed_goes_ready_for_review():
    assert next_status_for_extraction(any_needs_review=True) == JobStatus.READY_FOR_REVIEW


def test_extraction_done_no_review_needed_still_goes_ready_for_review():
    # User must always click finalize, even when nothing needs review.
    # (Spec §7: review screen visit + finalize click are explicit.)
    assert next_status_for_extraction(any_needs_review=False) == JobStatus.READY_FOR_REVIEW
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_lifecycle.py -v
```

- [ ] **Step 3: Implement `lifecycle.py`**

Create `backend/app/ingestion/lifecycle.py`:

```python
"""Job state machine — pure logic.

The DB-side transition (UPDATE ingestion_jobs SET status = ...) is performed
by `persistence.update_job_status`. This module only validates that the
transition is legal.
"""
from __future__ import annotations

from app.ingestion.exceptions import InvalidStateTransitionError
from app.ingestion.schemas import JobStatus

_ALLOWED: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING:           {JobStatus.EXTRACTING, JobStatus.FAILED},
    JobStatus.EXTRACTING:        {JobStatus.READY_FOR_REVIEW, JobStatus.FAILED},
    JobStatus.READY_FOR_REVIEW:  {JobStatus.CONFIRMED, JobStatus.FAILED},
    JobStatus.CONFIRMED:         {JobStatus.RECONCILING, JobStatus.FAILED},
    JobStatus.RECONCILING:       {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CONFIRMED},
    JobStatus.COMPLETED:         set(),
    JobStatus.FAILED:            set(),
}


def assert_can_transition(frm: JobStatus, to: JobStatus) -> None:
    if to not in _ALLOWED.get(frm, set()):
        raise InvalidStateTransitionError(frm.value, to.value)


def next_status_for_extraction(any_needs_review: bool) -> JobStatus:
    """After all files are extracted, the job moves to ready_for_review.

    Even when nothing needs review, the user is still expected to open the
    job and click Finalize (spec §7).
    """
    return JobStatus.READY_FOR_REVIEW
```

- [ ] **Step 4: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/test_lifecycle.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/lifecycle.py backend/tests/ingestion/test_lifecycle.py
git commit -m "feat(ingestion): job state machine"
```

---

### Task 17: Handoff — confirmed rows → canonical XLSX → reconciliation

**Files:**
- Create: `backend/app/ingestion/handoff.py`
- Create: `backend/tests/ingestion/test_handoff.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/ingestion/test_handoff.py`:

```python
"""Round-trip test: confirmed rows → canonical XLSX bytes → existing parser
must produce identical PurchaseRow output. Pure-logic, no DB."""
from datetime import date
from decimal import Decimal

from app.ingestion.handoff import rows_to_canonical_xlsx
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.reconciliation.parser import parse_purchase_register, parse_supplier_export


def _row(**over):
    base = dict(
        invoice_no="INV-1",
        supplier_bin="123456789",
        supplier_name="ACME",
        invoice_date=date(2026, 5, 10),
        taxable_amount_bdt=Decimal("1000.00"),
        vat_amount_bdt=Decimal("150.00"),
    )
    base.update(over)
    return ExtractedRowData(**base)


def test_purchase_roundtrip_through_existing_parser():
    rows = [_row(), _row(invoice_no="INV-2", supplier_bin="987654321")]
    xlsx = rows_to_canonical_xlsx(rows, kind=JobKind.PURCHASE_REGISTER)
    parsed = parse_purchase_register(xlsx)
    assert len(parsed) == 2
    assert parsed[0].invoice_no == "INV-1"
    assert parsed[0].supplier_bin == "123456789"
    assert parsed[0].taxable_amount_bdt == Decimal("1000.00")


def test_supplier_export_roundtrip():
    rows = [
        ExtractedRowData(
            invoice_no="S-1", buyer_bin="999000111",
            invoice_date=date(2026, 5, 11),
            taxable_amount_bdt=Decimal("500.00"),
            vat_amount_bdt=Decimal("75.00"),
        )
    ]
    xlsx = rows_to_canonical_xlsx(rows, kind=JobKind.SUPPLIER_EXPORT)
    parsed = parse_supplier_export(xlsx)
    assert len(parsed) == 1
    assert parsed[0].buyer_bin == "999000111"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_handoff.py -v
```

- [ ] **Step 3: Implement `handoff.py`**

Create `backend/app/ingestion/handoff.py`:

```python
"""Bridge from ingestion → existing reconciliation pipeline.

`rows_to_canonical_xlsx` is pure — produces the same XLSX shape the
existing parser expects.

`run_handoff` orchestrates the full flow: read confirmed rows, build
both XLSX files, upload to recon-files bucket, insert documents rows,
and call run_reconciliation in-process.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime
from typing import Any
from uuid import UUID

import openpyxl
import structlog

from app.database import get_supabase_admin
from app.ingestion import persistence as p
from app.ingestion.exceptions import HandoffError
from app.ingestion.schemas import ExtractedRowData, JobKind, JobStatus
from app.reconciliation.schemas import ReconciliationCreateRequest
from app.reconciliation.service import run_reconciliation

log = structlog.get_logger()


# ── Pure: rows → XLSX bytes in canonical schema ──────────────────────────


_PURCHASE_HEADERS = [
    "Invoice No", "Supplier BIN", "Supplier Name",
    "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)",
]
_SUPPLIER_HEADERS = [
    "Invoice No", "Invoice Date",
    "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN",
]


def rows_to_canonical_xlsx(
    rows: list[ExtractedRowData], *, kind: JobKind
) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    if kind == JobKind.PURCHASE_REGISTER:
        ws.append(_PURCHASE_HEADERS)
        for r in rows:
            ws.append([
                r.invoice_no, r.supplier_bin or "", r.supplier_name or "",
                r.invoice_date.isoformat(),
                float(r.taxable_amount_bdt), float(r.vat_amount_bdt),
            ])
    else:
        ws.append(_SUPPLIER_HEADERS)
        for r in rows:
            ws.append([
                r.invoice_no, r.invoice_date.isoformat(),
                float(r.taxable_amount_bdt), float(r.vat_amount_bdt),
                r.buyer_bin or "",
            ])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


# ── Orchestrated: full handoff to reconciliation ────────────────────────


_RECON_BUCKET = "recon-files"


async def run_handoff(
    *, job_id: UUID, tenant_id: UUID,
) -> UUID:
    """Returns the new reconciliation_id on success."""
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HandoffError(message=f"Job {job_id} not found")
    if job["status"] != JobStatus.CONFIRMED.value:
        raise HandoffError(
            message=f"Job {job_id} is in {job['status']}, not 'confirmed'"
        )

    client_id = UUID(job["client_id"])
    user_id = UUID(job["created_by"])
    kind = JobKind(job["kind"])

    rows_dicts = await p.list_confirmed_rows(job_id, tenant_id=tenant_id)
    rows = [ExtractedRowData(**r["row_data"]) for r in rows_dicts]

    if not rows:
        raise HandoffError(message="No confirmed rows to hand off")

    # Build the right kind of XLSX. We need BOTH a purchase register and a
    # supplier export to call run_reconciliation. The job is one kind; the
    # other comes from a sibling job the user must have run separately.
    # For MVP we require the user to upload BOTH kinds before finalize:
    # we look up the OTHER kind's most-recent completed job for the same
    # client+period and reuse its canonical XLSX.
    pr_doc_id, sf_doc_id = await _resolve_doc_ids(
        tenant_id=tenant_id, client_id=client_id, job=job, kind=kind, rows=rows,
        user_id=user_id,
    )

    log.info("ingestion.handoff.starting", job_id=str(job_id))

    recon_id = await run_reconciliation(
        ReconciliationCreateRequest(
            client_id=client_id,
            period_start=job["period_start"],
            period_end=job["period_end"],
            purchase_register_doc_id=pr_doc_id,
            supplier_data_doc_id=sf_doc_id,
        ),
        tenant_id=tenant_id, user_id=user_id,
    )
    log.info("ingestion.handoff.done", job_id=str(job_id), recon_id=str(recon_id))
    return recon_id


async def _resolve_doc_ids(
    *, tenant_id, client_id, job, kind, rows, user_id,
) -> tuple[UUID, UUID]:
    """Build the canonical XLSX for THIS job and look up a sibling for the other kind."""
    sb = get_supabase_admin()
    period_start = job["period_start"]; period_end = job["period_end"]

    # 1. Build + upload XLSX for this job's kind
    xlsx_bytes = rows_to_canonical_xlsx(rows, kind=kind)
    suffix = "purchase_register" if kind == JobKind.PURCHASE_REGISTER else "supplier_export"
    filename = f"ingested_{suffix}_{job['id']}.xlsx"
    storage_path = f"{tenant_id}/{client_id}/ingestion/{job['id']}/{filename}"

    def _up_and_register():
        sb.storage.from_(_RECON_BUCKET).upload(
            path=storage_path, file=xlsx_bytes,
            file_options={
                "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "upsert": "false",
            },
        )
        # Insert into documents table — match its required columns
        doc = sb.table("documents").insert({
            "tenant_id": str(tenant_id),
            "client_id": str(client_id),
            "uploaded_by": str(user_id),
            "doc_type": "vat_register" if kind == JobKind.PURCHASE_REGISTER else "supplier_export",
            "storage_path": storage_path,
            "original_filename": filename,
            "file_size_bytes": len(xlsx_bytes),
        }).execute()
        return UUID(doc.data[0]["id"])

    this_doc_id = await asyncio.to_thread(_up_and_register)

    # 2. Look up the most-recent successful sibling-kind doc for this client+period
    sibling_doc_type = (
        "supplier_export" if kind == JobKind.PURCHASE_REGISTER else "vat_register"
    )

    def _lookup_sibling():
        return (
            sb.table("documents")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .eq("doc_type", sibling_doc_type)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

    sibling = await asyncio.to_thread(_lookup_sibling)
    if not sibling.data:
        raise HandoffError(
            message=(
                f"No prior {sibling_doc_type} document found for client {client_id}. "
                f"Upload the matching file via ingestion before finalizing."
            )
        )
    sibling_id = UUID(sibling.data[0]["id"])

    if kind == JobKind.PURCHASE_REGISTER:
        return this_doc_id, sibling_id
    return sibling_id, this_doc_id
```

> **Note:** The sibling-doc lookup is a deliberate v1 simplification. The user must upload a purchase register AND a supplier export as two separate ingestion jobs for the same (client, period). The Phase 5 service code will surface a clear error from `HandoffError.message` to the UI when the sibling is missing.

- [ ] **Step 4: Run — expect pass on the pure tests**

```bash
cd backend && pytest tests/ingestion/test_handoff.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/handoff.py backend/tests/ingestion/test_handoff.py
git commit -m "feat(ingestion): handoff (rows → canonical XLSX → run_reconciliation)"
```

---

### Task 18: Worker — async job runner with lease pattern

**Files:**
- Create: `backend/app/ingestion/worker.py`
- Create: `backend/tests/ingestion/test_worker.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/ingestion/test_worker.py`:

```python
"""Worker tests — exercise the per-file extraction pipeline against stubs."""
from datetime import date
from uuid import uuid4

import pytest

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.ingestion.worker import process_one_file


class _FakeEngine:
    def extract(self, file_bytes: bytes, ctx: ExtractionContext) -> ExtractedFileResult:
        return ExtractedFileResult(
            rows=[ExtractedRowData(
                invoice_no="X", invoice_date=date(2026, 5, 1),
                taxable_amount_bdt="1", vat_amount_bdt="0.15",
            )],
            needs_review=False, extraction_engine="pandas",
            page_count=1, warnings=[],
        )


@pytest.mark.asyncio
async def test_process_one_file_invokes_engine_and_persists(monkeypatch):
    persisted = {}

    async def fake_persist(**kw):
        persisted.update(kw)

    async def fake_update_file(**kw):
        persisted["file_update"] = kw

    async def fake_increment(**kw):
        persisted["incremented"] = True

    async def fake_recompute(**kw):
        persisted["recomputed"] = True

    from app.ingestion import worker as w
    monkeypatch.setattr(w.p, "insert_extracted_rows", fake_persist)
    monkeypatch.setattr(w.p, "update_file", fake_update_file)
    monkeypatch.setattr(w.p, "increment_files_done", fake_increment)
    monkeypatch.setattr(w.p, "recompute_row_counts", fake_recompute)

    await process_one_file(
        engine=_FakeEngine(),
        file_bytes=b"fake",
        file_id=uuid4(), job_id=uuid4(), tenant_id=uuid4(),
        ctx=ExtractionContext(
            kind=JobKind.PURCHASE_REGISTER,
            period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
            tenant_id="00000000-0000-0000-0000-000000000000",
        ),
    )
    assert persisted["incremented"] is True
    assert persisted["recomputed"] is True
    assert persisted["rows"][0].invoice_no == "X"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && pytest tests/ingestion/test_worker.py -v
```

- [ ] **Step 3: Implement `worker.py`**

Create `backend/app/ingestion/worker.py`:

```python
"""In-process async worker for ingestion jobs.

Two entry points:
  * `process_one_file(...)` — does the per-file work; called by the worker
    loop OR directly by tests.
  * `worker_loop()` — long-running asyncio task; polls Postgres for
    pending jobs, processes each file with bounded concurrency.

Uses a soft lease via `update_file(status=extracting, extraction_started_at=now)`.
On startup, the worker re-claims rows where status='extracting' AND
extraction_started_at < now() - 10 min (handled in `claim_pending_jobs`).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import structlog

from app.config import settings
from app.database import get_supabase_admin
from app.ingestion import persistence as p
from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext, Engine
from app.ingestion.engines.pandas_canonical import PandasCanonicalEngine
from app.ingestion.engines.pandas_mapper import PandasMapperEngine
from app.ingestion.engines.pdf_borndigital import PdfBornDigitalEngine
from app.ingestion.engines.vision import VisionEngine
from app.ingestion.exceptions import ExtractionFailedError
from app.ingestion.lifecycle import next_status_for_extraction
from app.ingestion.router_engine import select_engine_name
from app.ingestion.schemas import (
    FileStatus, JobKind, JobStatus, RowStatus,
)
from app.ingestion.storage import download_original
from app.ingestion.validation import validate_row

log = structlog.get_logger()

_CONCURRENCY = 8
_LEASE_TIMEOUT = timedelta(minutes=10)


def _engine_for(name: str) -> Engine:
    return {
        "pandas":             PandasCanonicalEngine(),
        "pandas+llm-mapper":  PandasMapperEngine(),
        "pdfplumber+llm":     PdfBornDigitalEngine(),
        "gemini-vision":      VisionEngine(),
    }[name]


async def process_one_file(
    *,
    engine: Engine,
    file_bytes: bytes,
    file_id: UUID,
    job_id: UUID,
    tenant_id: UUID,
    ctx: ExtractionContext,
) -> None:
    started = datetime.utcnow()
    await p.update_file(
        file_id, tenant_id=tenant_id,
        status=FileStatus.EXTRACTING,
        engine=engine.name,
        extraction_started_at=started,
    )
    try:
        result: ExtractedFileResult = await asyncio.to_thread(
            engine.extract, file_bytes, ctx
        )
    except Exception as e:
        log.exception("ingestion.file.extract_failed",
                      file_id=str(file_id), error=str(e))
        await p.update_file(
            file_id, tenant_id=tenant_id,
            status=FileStatus.FAILED,
            error=str(e)[:500],
        )
        await p.increment_files_done(job_id, tenant_id=tenant_id)
        return

    # Validate each row → field warnings → row status
    field_warnings_per_row = [
        validate_row(
            row, kind=ctx.kind,
            period_start=ctx.period_start, period_end=ctx.period_end,
        )
        for row in result.rows
    ]
    initial_status = (
        RowStatus.NEEDS_REVIEW if result.needs_review else RowStatus.AUTO_PASSED
    )
    await p.insert_extracted_rows(
        job_id=job_id, file_id=file_id, tenant_id=tenant_id,
        rows=result.rows, status=initial_status,
        field_warnings_per_row=field_warnings_per_row,
        source_pages=result.source_pages,
    )

    await p.update_file(
        file_id, tenant_id=tenant_id,
        status=FileStatus.EXTRACTED,
        rows_extracted=len(result.rows),
        needs_review=result.needs_review,
        warnings=result.warnings,
        extracted_at=datetime.utcnow(),
    )
    await p.increment_files_done(job_id, tenant_id=tenant_id)
    await p.recompute_row_counts(job_id, tenant_id=tenant_id)


async def process_job(job_id: UUID, *, tenant_id: UUID) -> None:
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        log.warning("ingestion.worker.job_not_found", job_id=str(job_id))
        return

    await p.update_job_status(job_id, JobStatus.EXTRACTING, tenant_id=tenant_id)
    files = await p.list_files(job_id, tenant_id=tenant_id)
    pending = [f for f in files if f["status"] in (
        FileStatus.QUEUED.value, FileStatus.EXTRACTING.value
    )]

    ctx = ExtractionContext(
        kind=JobKind(job["kind"]),
        period_start=job["period_start"],
        period_end=job["period_end"],
        tenant_id=str(tenant_id),
    )

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(file_row):
        async with sem:
            try:
                content = await download_original(file_row["storage_path"])
            except Exception as e:
                await p.update_file(
                    UUID(file_row["id"]), tenant_id=tenant_id,
                    status=FileStatus.FAILED, error=f"storage: {e}"[:500],
                )
                await p.increment_files_done(job_id, tenant_id=tenant_id)
                return
            engine = _engine_for(select_engine_name(
                file_bytes=content, mime=file_row["mime_type"],
                kind=job["kind"], filename=file_row["original_filename"],
            ))
            await process_one_file(
                engine=engine, file_bytes=content,
                file_id=UUID(file_row["id"]),
                job_id=job_id, tenant_id=tenant_id, ctx=ctx,
            )

    await asyncio.gather(*[_one(f) for f in pending])

    # All files done — refresh counts and transition
    await p.recompute_row_counts(job_id, tenant_id=tenant_id)
    refreshed = await p.get_job(job_id, tenant_id=tenant_id)
    needs = (refreshed or {}).get("rows_needs_review", 0)
    await p.update_job_status(
        job_id, next_status_for_extraction(any_needs_review=needs > 0),
        tenant_id=tenant_id,
    )


async def claim_and_run(job_id: UUID, tenant_id: UUID) -> None:
    """Single-shot: process one specific job.

    Called from the API handler that creates the job (kicks off in background)
    and from the worker loop's polling.
    """
    try:
        await process_job(job_id, tenant_id=tenant_id)
    except Exception as e:
        log.exception("ingestion.worker.job_crashed",
                      job_id=str(job_id), error=str(e))
        await p.update_job_status(
            job_id, JobStatus.FAILED, tenant_id=tenant_id,
            error_summary=str(e)[:500],
        )


async def poll_pending_jobs(*, sleep_s: float = 5.0) -> None:
    """Long-running loop. Picks up jobs that were created on a different
    instance OR jobs whose lease expired due to a worker crash."""
    sb = get_supabase_admin()
    log.info("ingestion.worker.loop_started")
    while True:
        try:
            cutoff = (datetime.utcnow() - _LEASE_TIMEOUT).isoformat()

            def _q():
                # status=pending OR (status=extracting AND updated_at < cutoff)
                return (
                    sb.table("ingestion_jobs")
                    .select("id, tenant_id, status, updated_at")
                    .in_("status", [JobStatus.PENDING.value, JobStatus.EXTRACTING.value])
                    .order("created_at")
                    .limit(20)
                    .execute()
                )

            res = await asyncio.to_thread(_q)
            for row in res.data or []:
                if row["status"] == JobStatus.EXTRACTING.value and row["updated_at"] > cutoff:
                    continue  # still owned
                asyncio.create_task(
                    claim_and_run(UUID(row["id"]), UUID(row["tenant_id"]))
                )
        except Exception as e:
            log.exception("ingestion.worker.poll_error", error=str(e))
        await asyncio.sleep(sleep_s)
```

- [ ] **Step 4: Run — expect pass**

```bash
cd backend && pytest tests/ingestion/test_worker.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/worker.py backend/tests/ingestion/test_worker.py
git commit -m "feat(ingestion): worker with per-file extraction + polling loop"
```

---

### Task 19: Wire the worker into FastAPI lifespan

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add lifespan startup that boots the worker when ingestion enabled**

Edit `backend/app/main.py` — replace the `def create_app() -> FastAPI:` line and the FastAPI() construction with a `lifespan`-using version. Locate this block:

```python
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="HishabAI API",
        description="Automated CA workflow platform for Bangladesh",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    )
```

Replace with:

```python
import os
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Optional ingestion boot: only when feature flag is on AND key present
    ingestion_task: asyncio.Task | None = None
    if os.environ.get("INGESTION_ENABLED", "false").lower() == "true":
        from app.ingestion.llm import GeminiLLMAdapter, set_llm_adapter
        from app.ingestion.worker import poll_pending_jobs

        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not gemini_key:
            logger.warning("ingestion.boot.skipped",
                           reason="INGESTION_ENABLED=true but GEMINI_API_KEY missing")
        else:
            set_llm_adapter(GeminiLLMAdapter(api_key=gemini_key))
            ingestion_task = asyncio.create_task(poll_pending_jobs())
            logger.info("ingestion.boot.started")
    yield
    if ingestion_task is not None:
        ingestion_task.cancel()
        try:
            await ingestion_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="HishabAI API",
        description="Automated CA workflow platform for Bangladesh",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
        lifespan=_lifespan,
    )
```

> Note: `asyncio` is already imported at top of `main.py` per the existing readiness check; if not, add `import asyncio` near the top.

- [ ] **Step 2: Smoke test — start app with ingestion off, then on**

```bash
cd backend && uvicorn app.main:app --port 8001 &
sleep 2 && curl -sf http://127.0.0.1:8001/health && echo
kill %1
```

Expected: health responds 200; no ingestion log lines (flag off).

```bash
cd backend && INGESTION_ENABLED=true GEMINI_API_KEY=fakekey uvicorn app.main:app --port 8001 &
sleep 2 && curl -sf http://127.0.0.1:8001/health && echo
kill %1
```

Expected: log line `ingestion.boot.started`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(ingestion): wire worker into FastAPI lifespan behind feature flag"
```

---

## Phase 5 — API Surface

### Task 20: Service module — create_job orchestration

**Files:**
- Create: `backend/app/ingestion/service.py`

- [ ] **Step 1: Implement `service.py` (no separate test file — exercised end-to-end via API tests in Task 21)**

Create `backend/app/ingestion/service.py`:

```python
"""High-level orchestration entry points called from the router.

Three operations:
  * create_job   — accept multipart files, persist, kick off worker
  * finalize     — verify zero needs_review then run handoff
  * confirm_row / reject_row / edit_row — row-level mutations
"""
from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import UploadFile

from app.ingestion import persistence as p
from app.ingestion import storage as st
from app.ingestion.exceptions import (
    FileTooLargeError,
    JobNotFoundError,
    UnsupportedFileTypeError,
)
from app.ingestion.handoff import run_handoff
from app.ingestion.lifecycle import assert_can_transition
from app.ingestion.router_engine import select_engine_name
from app.ingestion.schemas import (
    CreateJobFileSummary,
    CreateJobResponse,
    ExtractedRowData,
    JobKind,
    JobStatus,
    RowStatus,
)
from app.ingestion.worker import claim_and_run

log = structlog.get_logger()

_MAX_FILES = int(os.environ.get("INGESTION_MAX_FILES_PER_JOB", "200"))
_MAX_SIZE_MB = int(os.environ.get("INGESTION_MAX_FILE_SIZE_MB", "25"))
_MAX_BYTES = _MAX_SIZE_MB * 1024 * 1024


async def create_job(
    *,
    tenant_id: UUID,
    user_id: UUID,
    client_id: UUID,
    period_start: date,
    period_end: date,
    kind: JobKind,
    files: list[UploadFile],
) -> CreateJobResponse:
    if not files:
        raise UnsupportedFileTypeError(filename="", mime="(no files)")
    if len(files) > _MAX_FILES:
        raise UnsupportedFileTypeError(
            filename=f"<{len(files)} files>",
            mime=f"max {_MAX_FILES} files per job",
        )

    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=kind, period_start=period_start, period_end=period_end,
    )

    summaries: list[CreateJobFileSummary] = []
    for upload in files:
        content = await upload.read()
        size = len(content)
        try:
            if size > _MAX_BYTES:
                raise FileTooLargeError(
                    filename=upload.filename or "<unnamed>",
                    size=size, max_size=_MAX_BYTES,
                )
            mime = upload.content_type or "application/octet-stream"
            # Validate MIME → engine mapping early; surfaces 400 on unsupported
            select_engine_name(
                file_bytes=content[:4096], mime=mime,
                kind=kind, filename=upload.filename or "<unnamed>",
            )
        except (UnsupportedFileTypeError, FileTooLargeError) as e:
            summaries.append(CreateJobFileSummary(
                file_id=UUID(int=0), original_filename=upload.filename or "<unnamed>",
                mime_type=upload.content_type or "", byte_size=size,
                accepted=False, rejection_reason=e.message,
            ))
            continue

        # Add file row + upload to storage
        file_id = await p.add_file(
            job_id=job_id, tenant_id=tenant_id,
            storage_path="placeholder", original_filename=upload.filename or "<unnamed>",
            mime_type=mime, byte_size=size,
        )
        path = await st.upload_original(
            tenant_id=tenant_id, job_id=job_id, file_id=file_id,
            filename=upload.filename or f"file-{file_id}", content=content,
            mime_type=mime,
        )
        # Patch the path on the file row
        await p.update_file(file_id, tenant_id=tenant_id, engine=None)
        # Storage path was set to "placeholder"; rewrite it
        from app.database import get_supabase_admin
        sb = get_supabase_admin()

        def _patch():
            sb.table("ingestion_files").update({"storage_path": path}).eq(
                "id", str(file_id)
            ).execute()

        await asyncio.to_thread(_patch)

        summaries.append(CreateJobFileSummary(
            file_id=file_id, original_filename=upload.filename or "<unnamed>",
            mime_type=mime, byte_size=size, accepted=True,
        ))

    # Kick off the worker for this specific job (parallel to the polling loop)
    asyncio.create_task(claim_and_run(job_id, tenant_id))

    return CreateJobResponse(job_id=job_id, files=summaries)


async def finalize_job(*, job_id: UUID, tenant_id: UUID) -> UUID:
    """Idempotent. Validates needs_review == 0; runs handoff."""
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise JobNotFoundError(message=f"Job {job_id} not found")

    current = JobStatus(job["status"])
    if current == JobStatus.COMPLETED:
        # Already done — return the existing reconciliation_id
        if job["reconciliation_id"]:
            return UUID(job["reconciliation_id"])
        from app.ingestion.exceptions import HandoffError
        raise HandoffError(message="Completed job has no reconciliation_id")

    needs = await p.count_needs_review(job_id, tenant_id=tenant_id)
    if needs > 0:
        from app.ingestion.exceptions import IngestionError
        err = IngestionError(message=f"{needs} rows still need review")
        err.code = "INGESTION_REVIEW_INCOMPLETE"
        raise err

    if current == JobStatus.READY_FOR_REVIEW:
        assert_can_transition(current, JobStatus.CONFIRMED)
        await p.update_job_status(
            job_id, JobStatus.CONFIRMED, tenant_id=tenant_id,
        )

    assert_can_transition(JobStatus.CONFIRMED, JobStatus.RECONCILING)
    await p.update_job_status(
        job_id, JobStatus.RECONCILING, tenant_id=tenant_id,
    )

    try:
        recon_id = await run_handoff(job_id=job_id, tenant_id=tenant_id)
    except Exception as e:
        log.exception("ingestion.finalize.handoff_failed",
                      job_id=str(job_id), error=str(e))
        # Roll back to CONFIRMED so user can retry without re-extracting
        await p.update_job_status(
            job_id, JobStatus.CONFIRMED, tenant_id=tenant_id,
            error_summary=str(e)[:500],
        )
        raise

    await p.update_job_status(
        job_id, JobStatus.COMPLETED, tenant_id=tenant_id,
        reconciliation_id=recon_id,
    )
    return recon_id


async def confirm_row(
    *, row_id: UUID, tenant_id: UUID, user_id: UUID,
) -> None:
    await p.update_row(
        row_id, tenant_id=tenant_id,
        status=RowStatus.CONFIRMED, reviewed_by=user_id,
    )


async def reject_row(
    *, row_id: UUID, tenant_id: UUID, user_id: UUID,
) -> None:
    await p.update_row(
        row_id, tenant_id=tenant_id,
        status=RowStatus.REJECTED, reviewed_by=user_id,
    )


async def edit_row(
    *, row_id: UUID, tenant_id: UUID, user_id: UUID,
    new_data: ExtractedRowData,
) -> None:
    await p.update_row(
        row_id, tenant_id=tenant_id,
        row_data=new_data, status=RowStatus.EDITED, reviewed_by=user_id,
    )


async def bulk_confirm(
    *, row_ids: list[UUID], tenant_id: UUID, user_id: UUID,
) -> int:
    """Sequential to keep RLS audit trail clean; row count is small."""
    count = 0
    for rid in row_ids:
        await confirm_row(row_id=rid, tenant_id=tenant_id, user_id=user_id)
        count += 1
    return count
```

- [ ] **Step 2: Commit (no test commit; covered by Task 21+)**

```bash
git add backend/app/ingestion/service.py
git commit -m "feat(ingestion): service orchestration (create_job/finalize/row mutations)"
```

---

### Task 21: Router — POST /jobs (multipart upload)

**Files:**
- Create: `backend/app/ingestion/router.py`
- Create: `backend/tests/ingestion/test_api.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/ingestion/test_api.py`:

```python
"""End-to-end API tests using FastAPI TestClient.

Gated on the same env-var pack as persistence tests because endpoints
require a real DB and storage. Stubs LLM via set_llm_adapter.
"""
from __future__ import annotations

import io
import os
from datetime import date
from uuid import UUID

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.main import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="API tests require a live Supabase",
)


def _canonical_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    ws.append(["INV-API", "111222333", "Test Supplier",
               "2026-05-10", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


@pytest.fixture
def client():
    set_llm_adapter(StubLLMAdapter())
    return TestClient(create_app())


@pytest.fixture
def auth_headers():
    token = os.environ.get("INGESTION_TEST_USER_JWT")
    if not token:
        pytest.skip("INGESTION_TEST_USER_JWT required")
    return {"Authorization": f"Bearer {token}"}


def test_create_job_accepts_canonical_xlsx(client, auth_headers, tenant_id, client_id):
    files = [
        ("files", ("register.xlsx", _canonical_xlsx(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
    ]
    data = {
        "client_id": str(client_id),
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "kind": "purchase_register",
    }
    res = client.post("/api/v1/ingestion/jobs", data=data, files=files,
                      headers=auth_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert "job_id" in body
    assert len(body["files"]) == 1
    assert body["files"][0]["accepted"] is True


def test_create_job_rejects_unsupported_mime(client, auth_headers, client_id):
    files = [("files", ("malware.zip", b"PK\x03\x04...", "application/zip"))]
    data = {
        "client_id": str(client_id),
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "kind": "purchase_register",
    }
    res = client.post("/api/v1/ingestion/jobs", data=data, files=files,
                      headers=auth_headers)
    # Job is created; the file is recorded as rejected
    assert res.status_code == 201
    body = res.json()
    assert body["files"][0]["accepted"] is False
    assert "unsupported" in body["files"][0]["rejection_reason"].lower()
```

- [ ] **Step 2: Implement `router.py`**

Create `backend/app/ingestion/router.py`:

```python
"""FastAPI endpoints for ingestion. Mounted at /api/v1/ingestion."""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_tenant_id, get_current_user_id
from app.ingestion import persistence as p
from app.ingestion import service as svc
from app.ingestion.exceptions import IngestionError, JobNotFoundError
from app.ingestion.schemas import (
    CreateJobResponse,
    ExtractedRowData,
    ExtractedRowOut,
    FieldWarning,
    FinalizeResponse,
    IngestionFileOut,
    JobDetailOut,
    JobKind,
    JobOut,
    RowsListOut,
)
from app.ingestion.storage import create_signed_url, download_original

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


# ── POST /jobs ─────────────────────────────────────────────────────────


@router.post(
    "/jobs", status_code=status.HTTP_201_CREATED,
    response_model=CreateJobResponse,
)
async def create_job_endpoint(
    client_id: UUID = Form(...),
    period_start: date = Form(...),
    period_end: date = Form(...),
    kind: JobKind = Form(...),
    files: list[UploadFile] = File(...),
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> CreateJobResponse:
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end < period_start")
    return await svc.create_job(
        tenant_id=tenant_id, user_id=user_id,
        client_id=client_id, period_start=period_start, period_end=period_end,
        kind=kind, files=files,
    )


# ── GET /jobs/{id} ─────────────────────────────────────────────────────


def _job_row_to_out(row: dict) -> JobOut:
    return JobOut(**{
        "id": row["id"], "tenant_id": row["tenant_id"], "client_id": row["client_id"],
        "kind": row["kind"], "period_start": row["period_start"],
        "period_end": row["period_end"], "status": row["status"],
        "files_total": row["files_total"], "files_done": row["files_done"],
        "rows_total": row["rows_total"], "rows_needs_review": row["rows_needs_review"],
        "error_summary": row.get("error_summary"),
        "reconciliation_id": row.get("reconciliation_id"),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "completed_at": row.get("completed_at"),
    })


def _file_row_to_out(row: dict) -> IngestionFileOut:
    return IngestionFileOut(**{
        "id": row["id"], "job_id": row["job_id"],
        "original_filename": row["original_filename"],
        "mime_type": row["mime_type"], "byte_size": row["byte_size"],
        "engine": row.get("engine"), "status": row["status"],
        "rows_extracted": row["rows_extracted"], "needs_review": row["needs_review"],
        "warnings": row.get("warnings") or [], "error": row.get("error"),
        "extracted_at": row.get("extracted_at"),
    })


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
async def get_job_endpoint(
    job_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> JobDetailOut:
    job = await p.get_job(job_id, tenant_id=tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    files = await p.list_files(job_id, tenant_id=tenant_id)
    return JobDetailOut(
        job=_job_row_to_out(job),
        files=[_file_row_to_out(f) for f in files],
    )


# ── GET /jobs/{id}/rows ─────────────────────────────────────────────────


def _row_to_out(row: dict) -> ExtractedRowOut:
    return ExtractedRowOut(
        id=row["id"], file_id=row["file_id"], job_id=row["job_id"],
        source_page_no=row.get("source_page_no"),
        row_data=ExtractedRowData(**row["row_data"]),
        row_data_original=ExtractedRowData(**row["row_data_original"]),
        status=row["status"],
        field_warnings=[FieldWarning(**w) for w in (row.get("field_warnings") or [])],
        reviewed_by=row.get("reviewed_by"),
        reviewed_at=row.get("reviewed_at"),
        created_at=row["created_at"],
    )


@router.get("/jobs/{job_id}/rows", response_model=RowsListOut)
async def list_rows_endpoint(
    job_id: UUID,
    filter: str = Query("needs_review", regex="^(needs_review|all)$"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> RowsListOut:
    rows = await p.list_rows(
        job_id, tenant_id=tenant_id,
        only_needs_review=(filter == "needs_review"),
        limit=limit, offset=offset,
    )
    out = [_row_to_out(r) for r in rows]
    return RowsListOut(rows=out, total=len(out), has_more=len(out) == limit)


# ── Row mutations: PATCH / confirm / reject / bulk-confirm ─────────────


@router.patch("/jobs/{job_id}/rows/{row_id}", response_model=ExtractedRowOut)
async def edit_row_endpoint(
    job_id: UUID, row_id: UUID, body: ExtractedRowData,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> ExtractedRowOut:
    await svc.edit_row(
        row_id=row_id, tenant_id=tenant_id, user_id=user_id, new_data=body,
    )
    rows = await p.list_rows(job_id, tenant_id=tenant_id, only_needs_review=False)
    found = next((r for r in rows if r["id"] == str(row_id)), None)
    if not found:
        raise HTTPException(status_code=404, detail="Row not found")
    return _row_to_out(found)


@router.post("/jobs/{job_id}/rows/{row_id}/confirm")
async def confirm_row_endpoint(
    job_id: UUID, row_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    await svc.confirm_row(row_id=row_id, tenant_id=tenant_id, user_id=user_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/rows/{row_id}/reject")
async def reject_row_endpoint(
    job_id: UUID, row_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    await svc.reject_row(row_id=row_id, tenant_id=tenant_id, user_id=user_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/rows/bulk-confirm")
async def bulk_confirm_endpoint(
    job_id: UUID, body: dict,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    row_ids = [UUID(x) for x in body.get("row_ids") or []]
    n = await svc.bulk_confirm(row_ids=row_ids, tenant_id=tenant_id, user_id=user_id)
    return {"confirmed_count": n}


# ── POST /jobs/{id}/finalize ───────────────────────────────────────────


@router.post("/jobs/{job_id}/finalize", response_model=FinalizeResponse)
async def finalize_endpoint(
    job_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> FinalizeResponse:
    try:
        recon_id = await svc.finalize_job(job_id=job_id, tenant_id=tenant_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={
            "code": e.code, "message": e.message, "details": e.details,
        })
    return FinalizeResponse(reconciliation_id=recon_id)


# ── GET /jobs/{id}/files/{file_id}/preview ─────────────────────────────


@router.get("/jobs/{job_id}/files/{file_id}/preview")
async def preview_file_endpoint(
    job_id: UUID, file_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> StreamingResponse:
    files = await p.list_files(job_id, tenant_id=tenant_id)
    target = next((f for f in files if f["id"] == str(file_id)), None)
    if target is None:
        raise HTTPException(status_code=404, detail="File not found")
    content = await download_original(target["storage_path"])
    return StreamingResponse(
        iter([content]),
        media_type=target["mime_type"],
        headers={
            "Content-Disposition": f'inline; filename="{target["original_filename"]}"',
        },
    )


# ── Column mappings ────────────────────────────────────────────────────


@router.get("/column-mappings/pending")
async def list_pending_mappings_endpoint(
    tenant_id: UUID = Depends(get_current_tenant_id),
) -> dict:
    from app.database import get_supabase_admin
    import asyncio as _aio
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("ingestion_column_mappings")
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .is_("confirmed_by", "null")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

    res = await _aio.to_thread(_q)
    return {"mappings": res.data or []}


@router.post("/column-mappings/{mapping_id}/confirm")
async def confirm_mapping_endpoint(
    mapping_id: UUID,
    tenant_id: UUID = Depends(get_current_tenant_id),
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    from app.database import get_supabase_admin
    import asyncio as _aio
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("ingestion_column_mappings")
            .update({"confirmed_by": str(user_id)})
            .eq("id", str(mapping_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await _aio.to_thread(_u)
    return {"ok": True}
```

- [ ] **Step 3: Run API test (with env vars set + service running locally)**

```bash
cd backend && pytest tests/ingestion/test_api.py -v
```

Expected: 2 passed when env vars set, otherwise skipped.

- [ ] **Step 4: Commit**

```bash
git add backend/app/ingestion/router.py backend/tests/ingestion/test_api.py
git commit -m "feat(ingestion): API endpoints (jobs, rows, finalize, preview, mappings)"
```

---

## Phase 6 — Operational

### Task 22: Per-tenant rate limiter (token bucket)

**Files:**
- Create: `backend/app/ingestion/rate_limit.py`
- Create: `backend/tests/ingestion/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/ingestion/test_rate_limit.py`:

```python
"""Pure-logic token bucket tests — no DB."""
from uuid import uuid4

import pytest

from app.ingestion.rate_limit import TokenBucketRegistry, RateLimitExceeded


def test_first_call_passes():
    reg = TokenBucketRegistry(per_min=2, per_day=100)
    t = uuid4()
    reg.acquire(t)


def test_third_call_in_minute_blocks():
    reg = TokenBucketRegistry(per_min=2, per_day=100)
    t = uuid4()
    reg.acquire(t); reg.acquire(t)
    with pytest.raises(RateLimitExceeded):
        reg.acquire(t)


def test_separate_tenants_dont_share():
    reg = TokenBucketRegistry(per_min=1, per_day=100)
    a, b = uuid4(), uuid4()
    reg.acquire(a)
    reg.acquire(b)  # b has its own bucket
```

- [ ] **Step 2: Implement `rate_limit.py`**

Create `backend/app/ingestion/rate_limit.py`:

```python
"""Per-tenant token-bucket rate limiter for ingestion LLM calls.

In-process only (single instance is fine for MVP). When we horizontally
scale, swap for a Redis-backed counter.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from uuid import UUID


class RateLimitExceeded(Exception):
    pass


class TokenBucketRegistry:
    """Sliding window over the last 60s and 86400s per tenant."""

    def __init__(self, *, per_min: int, per_day: int) -> None:
        self._per_min = per_min
        self._per_day = per_day
        self._calls: dict[UUID, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def acquire(self, tenant_id: UUID) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._calls[tenant_id]
            # Drop entries older than 1 day
            while q and q[0] < now - 86400:
                q.popleft()
            in_min = sum(1 for t in q if t >= now - 60)
            if in_min >= self._per_min:
                raise RateLimitExceeded(
                    f"tenant {tenant_id}: {in_min}/{self._per_min} in last 60s"
                )
            if len(q) >= self._per_day:
                raise RateLimitExceeded(
                    f"tenant {tenant_id}: {len(q)}/{self._per_day} in last 24h"
                )
            q.append(now)
```

> The Gemini adapter doesn't currently call this — wiring it in is a follow-up. For v1 we install the registry; the worker calls `acquire(tenant_id)` before invoking `get_llm_adapter().extract_rows(...)` / `map_columns(...)` (one-line addition in `worker.process_one_file` and `pandas_mapper.extract` once a registry singleton is exposed).

- [ ] **Step 3: Wire into worker**

Edit `backend/app/ingestion/worker.py` — at the top add:

```python
from app.ingestion.rate_limit import TokenBucketRegistry

_RATE = TokenBucketRegistry(
    per_min=int(os.environ.get("INGESTION_MAX_CALLS_PER_MIN", "30")),
    per_day=int(os.environ.get("INGESTION_MAX_CALLS_PER_DAY", "5000")),
)


def get_rate_limiter() -> TokenBucketRegistry:
    return _RATE
```

(Add `import os` near the top if not present.)

In `process_one_file`, before calling `engine.extract`, call:

```python
# Only LLM-touching engines need rate-limiting
if engine.name in ("pandas+llm-mapper", "pdfplumber+llm", "gemini-vision"):
    try:
        _RATE.acquire(tenant_id)
    except RateLimitExceeded as e:
        await p.update_file(
            file_id, tenant_id=tenant_id,
            status=FileStatus.FAILED, error=f"rate_limited: {e}"[:500],
        )
        await p.increment_files_done(job_id, tenant_id=tenant_id)
        return
```

(Import `RateLimitExceeded` near the other imports.)

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/ingestion/test_rate_limit.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/rate_limit.py backend/app/ingestion/worker.py \
        backend/tests/ingestion/test_rate_limit.py
git commit -m "feat(ingestion): per-tenant token-bucket rate limiting + worker wiring"
```

---

### Task 23: Register router behind feature flag + Dockerfile libmagic

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Conditionally register the ingestion router**

In `backend/app/main.py`, locate the `# ── Routers ──` section and add:

```python
    # ── Routers ───────────────────────────────────────────────────────────
    from app.reconciliation.router import router as reconciliation_router
    app.include_router(reconciliation_router)

    if os.environ.get("INGESTION_ENABLED", "false").lower() == "true":
        from app.ingestion.router import router as ingestion_router
        app.include_router(ingestion_router)
        logger.info("ingestion.router_registered")
```

(`os` and `logger` are already imported.)

- [ ] **Step 2: Add libmagic to Dockerfile**

Edit `backend/Dockerfile`. Locate the `FROM python:3.11-slim` line and insert before the `WORKDIR /app`:

```dockerfile
# python-magic needs libmagic1 at runtime (used by ingestion MIME detection).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 3: Local Docker smoke test**

```bash
cd backend && docker build -t hishabai-test . && \
  docker run --rm -e INGESTION_ENABLED=false -p 8001:8080 hishabai-test &
sleep 5 && curl -sf http://127.0.0.1:8001/health && echo
docker ps -q | xargs docker stop
```

Expected: image builds; health endpoint returns 200.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/Dockerfile
git commit -m "feat(ingestion): conditional router registration + libmagic in Dockerfile"
```

---

### Task 24: Observability — `/health/ingestion` endpoint + structlog binding

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add the health sub-endpoint conditional on the feature flag**

In `backend/app/main.py`, after the existing `/ready` endpoint, add:

```python
    if os.environ.get("INGESTION_ENABLED", "false").lower() == "true":

        @app.get("/health/ingestion", tags=["system"])
        async def ingestion_health():
            """Returns queue depth + stuck-job count + last-hour failure rate."""
            from datetime import datetime, timedelta
            sb = get_supabase_admin()

            def _q_pending():
                return sb.table("ingestion_jobs").select("id", count="exact").eq(
                    "status", "pending"
                ).execute().count or 0

            def _q_stuck():
                cutoff = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
                return sb.table("ingestion_jobs").select("id", count="exact").eq(
                    "status", "extracting"
                ).lt("updated_at", cutoff).execute().count or 0

            def _q_failed():
                cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
                return sb.table("ingestion_jobs").select("id", count="exact").eq(
                    "status", "failed"
                ).gt("created_at", cutoff).execute().count or 0

            pending = await asyncio.to_thread(_q_pending)
            stuck = await asyncio.to_thread(_q_stuck)
            failed_1h = await asyncio.to_thread(_q_failed)

            return {
                "pending_jobs": pending,
                "stuck_extracting_15m": stuck,
                "failed_last_hour": failed_1h,
            }
```

- [ ] **Step 2: Verify the endpoint returns 200 with the flag on**

```bash
cd backend && INGESTION_ENABLED=true GEMINI_API_KEY=fakekey \
  uvicorn app.main:app --port 8002 &
sleep 2 && curl -sf http://127.0.0.1:8002/health/ingestion && echo
kill %1
```

Expected: JSON body with three integer counters.

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(ingestion): /health/ingestion observability endpoint"
```

---

### Task 25: Integration test — full happy path

**Files:**
- Create: `backend/tests/ingestion/integration/__init__.py`
- Create: `backend/tests/ingestion/integration/test_full_flow.py`

- [ ] **Step 1: Write the integration test (gated on the same env-var pack)**

Create `backend/tests/ingestion/integration/__init__.py` empty.

Create `backend/tests/ingestion/integration/test_full_flow.py`:

```python
"""Full happy-path integration test.

Requires: INGESTION_TEST_SUPABASE_URL, INGESTION_TEST_TENANT_ID,
INGESTION_TEST_CLIENT_ID, INGESTION_TEST_USER_ID, INGESTION_TEST_USER_JWT
to be set against a working dev Supabase project + an existing demo client
with both prior PR + SF documents available (per the seed_demo.py output).
"""
from __future__ import annotations

import asyncio
import io
import os
from datetime import date

import openpyxl
import pytest

from app.ingestion import persistence as p
from app.ingestion import service as svc
from app.ingestion.llm import StubLLMAdapter, set_llm_adapter
from app.ingestion.schemas import JobKind, JobStatus

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="full integration requires real Supabase",
)


def _xlsx_pr() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Supplier BIN", "Supplier Name",
               "Invoice Date", "Taxable Amount (BDT)", "VAT Amount (BDT)"])
    for i in range(3):
        ws.append([f"INT-PR-{i}", "100200300", "IntegSupplier",
                   "2026-05-15", 1000, 150])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _xlsx_sf() -> bytes:
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Invoice No", "Invoice Date",
               "Taxable Amount (BDT)", "VAT Amount (BDT)", "Buyer BIN"])
    for i in range(3):
        ws.append([f"INT-PR-{i}", "2026-05-15", 1000, 150, "111222333"])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


class _Upload:
    """Minimal stand-in for fastapi.UploadFile in tests."""
    def __init__(self, name: str, content: bytes, mime: str) -> None:
        self.filename = name
        self.content_type = mime
        self._buf = io.BytesIO(content)

    async def read(self) -> bytes:
        return self._buf.getvalue()


@pytest.mark.asyncio
async def test_full_happy_path(tenant_id, client_id, user_id):
    set_llm_adapter(StubLLMAdapter())

    # Upload 1: supplier export
    sf_resp = await svc.create_job(
        tenant_id=tenant_id, user_id=user_id, client_id=client_id,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        kind=JobKind.SUPPLIER_EXPORT,
        files=[_Upload("sf.xlsx", _xlsx_sf(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
    )

    # Wait for extraction
    for _ in range(30):
        j = await p.get_job(sf_resp.job_id, tenant_id=tenant_id)
        if j and j["status"] == JobStatus.READY_FOR_REVIEW.value:
            break
        await asyncio.sleep(1)
    assert j["status"] == JobStatus.READY_FOR_REVIEW.value
    assert j["rows_needs_review"] == 0  # canonical XLSX → auto-pass

    # Finalize SF
    await svc.finalize_job(job_id=sf_resp.job_id, tenant_id=tenant_id)

    # Upload 2: purchase register (sibling now exists)
    pr_resp = await svc.create_job(
        tenant_id=tenant_id, user_id=user_id, client_id=client_id,
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        kind=JobKind.PURCHASE_REGISTER,
        files=[_Upload("pr.xlsx", _xlsx_pr(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
    )

    for _ in range(30):
        j = await p.get_job(pr_resp.job_id, tenant_id=tenant_id)
        if j and j["status"] == JobStatus.READY_FOR_REVIEW.value:
            break
        await asyncio.sleep(1)

    recon_id = await svc.finalize_job(job_id=pr_resp.job_id, tenant_id=tenant_id)
    assert recon_id is not None

    # Verify reconciliation_id stored on job
    j = await p.get_job(pr_resp.job_id, tenant_id=tenant_id)
    assert j["status"] == JobStatus.COMPLETED.value
    assert j["reconciliation_id"] == str(recon_id)
```

- [ ] **Step 2: Run with env vars set against the dev Supabase**

```bash
cd backend && \
  INGESTION_TEST_SUPABASE_URL=$SUPABASE_URL \
  INGESTION_TEST_TENANT_ID=<demo-tenant-uuid> \
  INGESTION_TEST_CLIENT_ID=<demo-client-uuid> \
  INGESTION_TEST_USER_ID=<demo-user-uuid> \
  INGESTION_TEST_USER_JWT=<demo-user-jwt> \
  INGESTION_ENABLED=true GEMINI_API_KEY=<key> \
  pytest tests/ingestion/integration/test_full_flow.py -v
```

Expected: passes within ~60 seconds.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/ingestion/integration/__init__.py \
        backend/tests/ingestion/integration/test_full_flow.py
git commit -m "test(ingestion): full happy-path integration test"
```

---

### Task 26: Final sweep — run full test suite + tag

**Files:** none

- [ ] **Step 1: Run the full backend test suite (default markers)**

```bash
cd backend && pytest -v
```

Expected:
- Existing reconciliation tests: still pass (no regression)
- New ingestion tests: pure-logic tests pass (lifecycle, validation, llm_stub, router_engine, base, handoff, rate_limit, worker, schemas)
- DB-gated tests skip cleanly when env vars not set
- Live Gemini tests skip (no `-m live` flag)

- [ ] **Step 2: Run live + DB tests opt-in**

```bash
cd backend && \
  INGESTION_TEST_SUPABASE_URL=... \
  INGESTION_TEST_TENANT_ID=... INGESTION_TEST_CLIENT_ID=... \
  INGESTION_TEST_USER_ID=... INGESTION_TEST_USER_JWT=... \
  GEMINI_API_KEY=... \
  pytest -v -m live
```

Expected: all live + DB tests pass.

- [ ] **Step 3: Tag the backend completion**

```bash
git tag phase-f-backend-complete -m "Phase F backend ingestion complete"
git push origin phase-f-adaptive-ingestion --tags
```

- [ ] **Step 4: Summary commit (no code change; updates README if needed)**

If you want a developer pointer in README, add a single bullet under "Roadmap" linking to the spec/plan. Otherwise skip and the tag is the marker.

---

## Self-Review (against spec)

Before handing this plan off, verify each spec section maps to at least one task:

| Spec section | Task(s) |
|---|---|
| §1 Context & Problem | Implicit (this plan addresses it) |
| §2 Goals & Non-Goals | All tasks honor — Tesseract intentionally omitted (per spec) |
| §3 Top-Level Decisions | Tasks 5, 8, 9, 10, 18, 21, 23 |
| §4 Architecture Overview | Tasks 4, 18, 19, 23 |
| §5 File Router & Engines | Tasks 11, 12, 13, 14, 15 |
| §6 Data Model | Tasks 1, 5 |
| §7 Job Lifecycle | Tasks 16, 18, 20 |
| §8 API Surface | Tasks 20, 21 |
| §9 Frontend UX | Out of scope — Plan 2 |
| §10 Backward Compatibility | Tasks 17, 23 |
| §11 Error Handling | Tasks 18, 20, 22 |
| §12 Testing Strategy | Tasks 4-25 (each has tests; Task 25 is the integration test) |
| §13 Operational / Cost | Tasks 22, 24 |
| §14 Open Questions | Resolved during implementation (Gemini API auth → API-key path; worker → in-process polling; HEIC → pillow-heif) |
| §15 Out of Scope | Honored — no Tesseract, no per-supplier templates, no NBR portal, no storage cleanup |
| §16 Success Criteria | Validated by Task 25 integration test |

**Type/name consistency check (cross-task references):**
- `ExtractedRowData` referenced in tasks 4, 5, 7, 11, 12, 13, 14, 17, 18, 20 — matches definition in Task 4
- `JobStatus` enum values used in tasks 5, 16, 18, 20, 24 — match Task 4 + Task 1 SQL
- `ExtractedFileResult` produced by tasks 11-14, consumed by task 18 — interface stable
- `select_engine_name` defined in Task 15, used by Tasks 18 and 20
- `set_llm_adapter` defined in Task 8, used by Tasks 12, 13, 14, 19, 21, 25

**Placeholder scan:** No "TBD", "TODO", or "implement later" remain. The Task 12 refactor note (mapping_cache callable injection) is intentional concrete guidance, not a placeholder.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-10-adaptive-file-ingestion-backend.md`.**

26 tasks across 6 phases. Estimated ~25-35 hours of focused work depending on debugging cycles.

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review the output between tasks, iterate fast. Best for plans this large; isolates context per task and catches drift early.

2. **Inline Execution** — I execute tasks in this session using `superpowers:executing-plans`, batched with checkpoints for your review.

**Which approach?**

Once the backend is done, Plan 2 (frontend) gets written against the now-concrete API surface — no drift between plan and reality.

