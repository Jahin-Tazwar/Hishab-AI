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
        supabase.table("tenants").select("id").eq("firm_name", seed_demo.DEMO_TENANT_FIRM_NAME)
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
        supabase.table("vat_reconciliations")
        .select("id,total_invoices,at_risk_itc_bdt")
        .eq("tenant_id", tenant_id).execute().data
    )
    assert len(recons) == 1
    assert recons[0]["total_invoices"] == 30
    assert Decimal(str(recons[0]["at_risk_itc_bdt"])) > 0

    # Second run — idempotent
    asyncio.run(seed_demo.seed(email, password))
    recons2 = (
        supabase.table("vat_reconciliations").select("id").eq("tenant_id", tenant_id)
        .execute().data
    )
    assert len(recons2) == 1, "second run should not create a duplicate recon"

    # Cleanup
    seed_demo._reset_demo()
