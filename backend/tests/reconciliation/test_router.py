"""Endpoint contract tests for POST /api/v1/reconciliations."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.reconciliation.router as router_module
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _bypass_auth(tenant_id, user_id):
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

    _bypass_auth(tenant_id, user_id)

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


def test_get_export_returns_xlsx_bytes(monkeypatch, client):
    tenant_id = uuid4()
    user_id = uuid4()
    recon_id = uuid4()
    fake_bytes = b"PK\x03\x04 fake-xlsx-bytes"

    _bypass_auth(tenant_id, user_id)

    async def _fake_export(*, reconciliation_id, tenant_id):
        return fake_bytes
    monkeypatch.setattr(router_module, "export_reconciliation", _fake_export)

    try:
        res = client.get(
            f"/api/v1/reconciliations/{recon_id}/export",
            headers={"Authorization": "Bearer fake"},
        )
        assert res.status_code == 200, res.text
        assert res.content == fake_bytes
        assert res.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert f"reconciliation-{recon_id}.xlsx" in res.headers["content-disposition"]
    finally:
        app.dependency_overrides.clear()


def test_post_reconciliation_422_on_inverted_period(client):
    # Bypass auth so Pydantic body validation runs and returns 422
    _bypass_auth(uuid4(), uuid4())
    try:
        body = {
            "client_id": str(uuid4()),
            "period_start": "2024-02-01",
            "period_end": "2024-01-01",
            "purchase_register_doc_id": str(uuid4()),
            "supplier_data_doc_id": str(uuid4()),
        }
        res = client.post("/api/v1/reconciliations", json=body,
                          headers={"Authorization": "Bearer fake"})
        assert res.status_code == 422
    finally:
        app.dependency_overrides.clear()
