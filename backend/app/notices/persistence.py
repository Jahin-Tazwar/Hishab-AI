"""Database I/O for the notices module. Uses the supabase admin client.

All callers are expected to have validated tenant scope already; the
`tenant_id` arg is defense-in-depth on every query.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import List, Optional
from uuid import UUID

from app.database import get_supabase_admin


async def find_client_ids_by_bin(
    bin_: str, *, tenant_id: UUID,
) -> List[UUID]:
    """Return client ids under this tenant matching the given BIN.

    The clients table stores BIN under the `bin` column (see migration 0002).
    """
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("clients")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .eq("bin", bin_)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return [UUID(r["id"]) for r in (res.data or [])]


async def find_recon_by_period(
    *, client_id: UUID, tenant_id: UUID,
    period_start: date, period_end: date,
) -> Optional[UUID]:
    """Most recent reconciliation matching the (client, exact period) tuple."""
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("vat_reconciliations")
            .select("id, started_at")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .eq("period_start", period_start.isoformat())
            .eq("period_end", period_end.isoformat())
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return UUID(res.data[0]["id"]) if res.data else None
