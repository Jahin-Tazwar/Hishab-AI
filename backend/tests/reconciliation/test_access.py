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
