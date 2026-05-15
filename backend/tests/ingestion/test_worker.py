"""Worker tests — exercise the per-file extraction pipeline against stubs."""
from datetime import date
from uuid import uuid4

import pytest

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.ingestion.worker import process_one_file


class _FakeEngine:
    name = "pandas"

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

    async def fake_update_file(*args, **kw):
        persisted.setdefault("file_updates", []).append(kw)

    async def fake_increment(*args, **kw):
        persisted["incremented"] = True

    async def fake_recompute(*args, **kw):
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
