"""Tests for the empty-job worker skip + the POST /jobs/{id}/files endpoint.

These complement test_create_job_linking.py and exercise the bug-fix path:
  * `process_job` is a no-op when the job has 0 files (defends against the
    poller racing the wizard's session-start step).
  * `add_job_files` rejects jobs that are not PENDING.
  * `add_job_files` happy-path persists files and schedules the worker.

The worker-skip test is pure-logic (mocked persistence); the add-files tests
mostly mock persistence too, with a live-DB integration test guarded by the
`INGESTION_TEST_SUPABASE_URL` env var, mirroring the existing convention in
this test directory.
"""
from __future__ import annotations

import asyncio
import os
from datetime import date
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.ingestion import service as svc
from app.ingestion import worker as w
from app.ingestion.exceptions import IngestionError, JobNotFoundError
from app.ingestion.schemas import JobKind, JobStatus


# ── Worker: skip empty job ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_job_skips_empty_files_total(monkeypatch):
    """An empty PENDING job (start_session pre-created it) must not be
    auto-advanced by the worker. Regression test for Bug 1."""
    job_id = uuid4()
    tenant_id = uuid4()
    status_updates: list[JobStatus] = []

    async def fake_get_job(jid, *, tenant_id):
        assert jid == job_id
        return {
            "id": str(jid), "tenant_id": str(tenant_id),
            "kind": "purchase_register",
            "period_start": "2026-01-01", "period_end": "2026-01-31",
            "status": JobStatus.PENDING.value,
            "files_total": 0,
        }

    async def fake_update_job_status(jid, status, *, tenant_id, **kw):
        status_updates.append(status)

    monkeypatch.setattr(w.p, "get_job", fake_get_job)
    monkeypatch.setattr(w.p, "update_job_status", fake_update_job_status)

    await w.process_job(job_id, tenant_id=tenant_id)

    assert status_updates == [], (
        f"Expected no status transitions for empty job; got {status_updates}"
    )


@pytest.mark.asyncio
async def test_process_job_with_files_still_advances(monkeypatch):
    """Sanity check: non-empty jobs still proceed through extraction."""
    job_id = uuid4()
    tenant_id = uuid4()
    status_updates: list[JobStatus] = []

    async def fake_get_job(jid, *, tenant_id):
        return {
            "id": str(jid), "tenant_id": str(tenant_id),
            "kind": "purchase_register",
            "period_start": "2026-01-01", "period_end": "2026-01-31",
            "status": JobStatus.PENDING.value,
            "files_total": 1,
            "rows_needs_review": 0,
        }

    async def fake_update_job_status(jid, status, *, tenant_id, **kw):
        status_updates.append(status)

    async def fake_list_files(jid, *, tenant_id):
        return []  # no QUEUED files, but files_total > 0 so we still proceed

    async def fake_recompute(jid, *, tenant_id):
        pass

    monkeypatch.setattr(w.p, "get_job", fake_get_job)
    monkeypatch.setattr(w.p, "update_job_status", fake_update_job_status)
    monkeypatch.setattr(w.p, "list_files", fake_list_files)
    monkeypatch.setattr(w.p, "recompute_row_counts", fake_recompute)

    await w.process_job(job_id, tenant_id=tenant_id)

    # Should transition: PENDING -> EXTRACTING -> READY_FOR_REVIEW
    assert JobStatus.EXTRACTING in status_updates
    assert JobStatus.READY_FOR_REVIEW in status_updates


# ── add_job_files: validation ──────────────────────────────────────────


def _fake_upload(name: str, content: bytes, mime: str) -> UploadFile:
    """Build an UploadFile suitable for passing into the service layer."""
    return UploadFile(
        filename=name,
        file=BytesIO(content),
        headers=Headers({"content-type": mime}),
    )


@pytest.mark.asyncio
async def test_add_job_files_rejects_missing_job(monkeypatch):
    async def fake_get_job(jid, *, tenant_id):
        return None

    monkeypatch.setattr(svc.p, "get_job", fake_get_job)
    with pytest.raises(JobNotFoundError):
        await svc.add_job_files(
            job_id=uuid4(), tenant_id=uuid4(),
            files=[_fake_upload("x.xlsx", b"x", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
        )


@pytest.mark.asyncio
async def test_add_job_files_rejects_non_pending_job(monkeypatch):
    async def fake_get_job(jid, *, tenant_id):
        return {
            "id": str(jid), "kind": "purchase_register",
            "status": JobStatus.READY_FOR_REVIEW.value,
        }

    monkeypatch.setattr(svc.p, "get_job", fake_get_job)
    with pytest.raises(IngestionError) as exc_info:
        await svc.add_job_files(
            job_id=uuid4(), tenant_id=uuid4(),
            files=[_fake_upload("x.xlsx", b"x", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
        )
    assert exc_info.value.code == "INGESTION_INVALID_STATE_FOR_UPLOAD"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_add_job_files_rejects_empty_file_list(monkeypatch):
    # Even before we hit the get_job check, an empty file list is invalid.
    with pytest.raises(Exception) as exc_info:
        await svc.add_job_files(
            job_id=uuid4(), tenant_id=uuid4(), files=[],
        )
    # Either UnsupportedFileTypeError or IngestionError subclass thereof.
    assert "no files" in str(exc_info.value).lower() or "unsupported" in str(exc_info.value).lower()


# ── Live-DB integration: actually add files and trigger worker ──────────


_LIVE = os.environ.get("INGESTION_TEST_SUPABASE_URL")
pytestmark_live = pytest.mark.skipif(
    not _LIVE,
    reason="Set INGESTION_TEST_SUPABASE_URL to enable live-DB ingestion tests.",
)


@pytestmark_live
@pytest.mark.asyncio
async def test_add_job_files_appends_and_schedules_worker(monkeypatch):
    """Full integration: create empty job, add a file, verify file row exists
    and worker was scheduled (without actually running the engine)."""
    from app.ingestion import persistence as p

    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    client_id = UUID("00000000-0000-0000-0000-000000000002")
    user_id = UUID("00000000-0000-0000-0000-000000000003")

    job_id = await p.create_job(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        kind=JobKind.PURCHASE_REGISTER,
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
    )

    scheduled: list[UUID] = []

    def fake_create_task(coro):
        # Capture which job was scheduled; cancel the coroutine so we don't
        # actually run the engine.
        scheduled.append(job_id)
        coro.close()
        return asyncio.Future()

    monkeypatch.setattr(svc.asyncio, "create_task", fake_create_task)

    # Tiny but well-formed xlsx wouldn't pass engine selection in unit tests;
    # but engine selection only inspects mime + the first 4096 bytes, and we
    # accept whatever it returns. For this integration test, we stub it out.
    monkeypatch.setattr(svc, "select_engine_name", lambda **kw: "pandas")
    # And stub storage upload so we don't hit Supabase Storage.
    async def fake_upload(**kw):
        return f"fake/{kw['file_id']}.xlsx"
    monkeypatch.setattr(svc.st, "upload_original", fake_upload)

    res = await svc.add_job_files(
        job_id=job_id, tenant_id=tenant_id,
        files=[_fake_upload(
            "test.xlsx", b"\x50\x4b\x03\x04dummy",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )],
    )

    assert res.job_id == job_id
    assert len(res.files) == 1 and res.files[0].accepted
    assert scheduled == [job_id]

    refreshed = await p.get_job(job_id, tenant_id=tenant_id)
    assert refreshed["files_total"] == 1
