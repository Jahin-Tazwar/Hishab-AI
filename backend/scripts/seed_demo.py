"""
Seed demo data: one tenant, three clients with mixed entity types,
compliance events for each, and one reconciliation with realistic mismatches.

Usage:
    python -m scripts.seed_demo --email demo@example.test --password DemoPass123!
    python -m scripts.seed_demo --email demo@example.test --reset
    python -m scripts.seed_demo --regenerate-fixtures   # regen XLSX fixtures and exit

Idempotent: re-running with the same email is safe — existing tenant + clients
are reused.

Schema notes (divergences from the original Phase E plan, kept here so future
maintainers don't waste time chasing them):
  - tenants column is `firm_name` not `name`, and `email` is NOT NULL.
  - The user/tenant link table is `user_profiles` (plural) keyed by `id`
    (= auth.users.id), not `user_profile.user_id`.
  - clients uses a single `fiscal_year_end` text column ('06-30'), not the
    split `fiscal_year_end_month/day` from the plan; entity_type allowed
    values are 'company','individual','partnership','ngo','bank'
    (no 'private_limited').
  - documents columns are `original_filename`, `file_size_bytes`, `doc_type`
    (not `file_name`, `size_bytes`, `file_kind`).
  - The reconciliation tables are `vat_reconciliations` and `recon_line_items`.
  - generate_compliance_events RPC signature is
    (p_client_id uuid, p_from_date date, p_to_date date) — no tenant_id arg
    (it derives it from the client row).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import structlog

from app.database import get_supabase_admin

log = structlog.get_logger()

DEMO_TENANT_FIRM_NAME = "Demo CA Firm"
DEMO_TENANT_EMAIL = "demo@hishabai.test"
DEMO_CLIENTS: list[dict] = [
    {
        "name": "Acme Textiles Ltd",
        "name_bn": None,
        # Plan said 'private_limited' but the CHECK constraint only allows
        # 'company','individual','partnership','ngo','bank'. Use 'company'.
        "entity_type": "company",
        "bin": "123456789",
        "tin": "123456789012",
        "is_vat_registered": True,
        "fiscal_year_end": "06-30",
    },
    {
        "name": "Hossain & Co Partnership",
        "name_bn": None,
        "entity_type": "partnership",
        "bin": None,
        "tin": "987654321098",
        "is_vat_registered": False,
        "fiscal_year_end": "06-30",
    },
    {
        "name": "Rahman Trading",
        "name_bn": None,
        "entity_type": "individual",
        "bin": "555666777",
        "tin": "111222333444",
        "is_vat_registered": True,
        "fiscal_year_end": "06-30",
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
    """Create or fetch the demo tenant by firm_name. Returns the tenant UUID."""
    supabase = get_supabase_admin()
    existing = (
        supabase.table("tenants")
        .select("id")
        .eq("firm_name", DEMO_TENANT_FIRM_NAME)
        .limit(1)
        .execute()
    )
    if existing.data:
        tid = UUID(existing.data[0]["id"])
        log.info("seed.tenant_exists", tenant_id=str(tid))
        return tid
    inserted = (
        supabase.table("tenants")
        .insert({"firm_name": DEMO_TENANT_FIRM_NAME, "email": DEMO_TENANT_EMAIL})
        .execute()
    )
    tid = UUID(inserted.data[0]["id"])
    log.info("seed.tenant_created", tenant_id=str(tid))
    return tid


def _ensure_user_profile(user_id: UUID, tenant_id: UUID) -> None:
    """Link the auth user to the demo tenant. No-op if already linked."""
    supabase = get_supabase_admin()
    existing = (
        supabase.table("user_profiles")
        .select("id")
        .eq("id", str(user_id))
        .limit(1)
        .execute()
    )
    if existing.data:
        log.info("seed.user_profile_exists", user_id=str(user_id))
        return
    supabase.table("user_profiles").insert({
        "id": str(user_id),
        "tenant_id": str(tenant_id),
        "full_name": "Demo User",
        "role": "firm_admin",
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


def _generate_events_for_client(client_id: UUID, tenant_id: UUID) -> int:
    """
    Calls the generate_compliance_events RPC for one client over the
    next 90 days. Returns the number of events generated (or 0 if the
    RPC is idempotent and they already exist).

    NOTE: the RPC's actual signature is (p_client_id, p_from_date, p_to_date)
    — the plan's `p_window_start/p_window_end/p_tenant_id` arg names don't
    match. The function reads tenant_id from the clients row internally.
    """
    from datetime import date, timedelta
    supabase = get_supabase_admin()
    today = date.today()
    end = today + timedelta(days=90)
    res = supabase.rpc(
        "generate_compliance_events",
        {
            "p_client_id": str(client_id),
            "p_from_date": today.isoformat(),
            "p_to_date": end.isoformat(),
        },
    ).execute()
    n = res.data if isinstance(res.data, int) else (res.data or 0)
    log.info(
        "seed.events_generated",
        client_id=str(client_id),
        tenant_id=str(tenant_id),
        count=n,
    )
    return int(n)


def _upload_fixture(
    *, tenant_id: UUID, client_id: UUID, user_id: UUID, doc_type: str, fixture_name: str
) -> UUID:
    """
    Upload one fixture XLSX to the recon-files bucket and create a documents row.
    Returns the document UUID.
    doc_type: 'purchase_register' or 'supplier_export'

    NOTE: The plan called this argument `file_kind` and used a `file_kind`
    column on the documents table. The actual schema uses `doc_type` (with a
    CHECK constraint on the same set of values). Same with
    `original_filename` (plan said `file_name`) and `file_size_bytes` (plan
    said `size_bytes`).
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
        .eq("doc_type", doc_type)
        .like("storage_path", "%/demo-seed/%")
        .limit(1)
        .execute()
    )
    if existing.data:
        return UUID(existing.data[0]["id"])

    storage_path = f"{tenant_id}/{client_id}/demo-seed/{fixture_name}"
    with open(fixture_path, "rb") as f:
        bytes_ = f.read()
    # supabase-py's storage upload is sync. upsert handles the case where a
    # previous failed seed left the object behind without a documents row.
    try:
        supabase.storage.from_("recon-files").upload(
            path=storage_path,
            file=bytes_,
            file_options={
                "upsert": "true",
                "content-type":
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Failed to upload fixture to recon-files bucket: {exc!r}. "
            "Confirm the 'recon-files' bucket exists in your Supabase project "
            "(migrations/0011_storage_buckets.sql creates it)."
        ) from exc
    inserted = supabase.table("documents").insert({
        "tenant_id": str(tenant_id),
        "client_id": str(client_id),
        "uploaded_by": str(user_id),
        "original_filename": fixture_name,
        "doc_type": doc_type,
        "storage_path": storage_path,
        "file_size_bytes": len(bytes_),
        "mime_type":
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }).execute()
    doc_id = UUID(inserted.data[0]["id"])
    log.info(
        "seed.fixture_uploaded",
        client_id=str(client_id),
        kind=doc_type,
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
        from calendar import monthrange
        period_start = date(today.year, today.month - 1, 1)
        last_day = monthrange(today.year, today.month - 1)[1]
        period_end = date(today.year, today.month - 1, last_day)

    supabase = get_supabase_admin()
    # NOTE: table is `vat_reconciliations` (plan said `reconciliations`).
    existing = (
        supabase.table("vat_reconciliations")
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
        doc_type="purchase_register", fixture_name="demo_register.xlsx",
    )
    sf_doc_id = _upload_fixture(
        tenant_id=tenant_id, client_id=client_id, user_id=user_id,
        doc_type="supplier_export", fixture_name="demo_supplier.xlsx",
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


async def seed(email: str, password: str | None) -> None:
    user_id = _ensure_auth_user(email, password)
    tenant_id = _ensure_tenant()
    _ensure_user_profile(user_id, tenant_id)
    client_ids = _ensure_clients(tenant_id, user_id)
    for cid in client_ids:
        _generate_events_for_client(cid, tenant_id)
    # Only seed a recon for the first client (Acme Textiles)
    await _seed_reconciliation(
        tenant_id=tenant_id,
        client_id=client_ids[0],
        user_id=user_id,
    )
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
