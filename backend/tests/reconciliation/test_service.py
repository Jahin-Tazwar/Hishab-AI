"""End-to-end orchestration test with mocked storage + persistence."""
from datetime import date
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
