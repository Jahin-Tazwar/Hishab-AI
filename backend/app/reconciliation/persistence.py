"""Persist a completed reconciliation via the persist_reconciliation RPC."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Iterable, Optional
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


# ── Override / re-aggregate helpers ─────────────────────────────────────


async def fetch_reconciliation_header(
    reconciliation_id: UUID, *, tenant_id: UUID,
) -> Optional[dict[str, Any]]:
    """Return the vat_reconciliations row scoped to the caller's tenant."""
    supabase = get_supabase_admin()

    def _q() -> Optional[dict[str, Any]]:
        res = (
            supabase.table("vat_reconciliations")
            .select("*")
            .eq("id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    return await asyncio.to_thread(_q)


async def fetch_line_items(
    reconciliation_id: UUID, *, tenant_id: UUID,
) -> list[dict[str, Any]]:
    """Return all line items for a reconciliation, scoped to the caller's tenant."""
    supabase = get_supabase_admin()

    def _q() -> list[dict[str, Any]]:
        res = (
            supabase.table("recon_line_items")
            .select("*")
            .eq("reconciliation_id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )
        return res.data or []

    return await asyncio.to_thread(_q)


async def fetch_line_item(
    line_item_id: UUID, *, reconciliation_id: UUID, tenant_id: UUID,
) -> Optional[dict[str, Any]]:
    """Lookup one line item, scoped to (recon, tenant). Returns None on miss
    so the service can surface a 404."""
    supabase = get_supabase_admin()

    def _q() -> Optional[dict[str, Any]]:
        res = (
            supabase.table("recon_line_items")
            .select("*")
            .eq("id", str(line_item_id))
            .eq("reconciliation_id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    return await asyncio.to_thread(_q)


async def update_line_item_override(
    line_item_id: UUID,
    *,
    reconciliation_id: UUID,
    tenant_id: UUID,
    ca_override: Optional[str],
    ca_notes: Optional[str],
) -> dict[str, Any]:
    """Update a single line item's ca_override + ca_notes, returning the
    refreshed row."""
    supabase = get_supabase_admin()
    payload = {"ca_override": ca_override, "ca_notes": ca_notes}

    def _u() -> dict[str, Any]:
        res = (
            supabase.table("recon_line_items")
            .update(payload)
            .eq("id", str(line_item_id))
            .eq("reconciliation_id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )
        # supabase-py returns the updated rows; assume exactly one matched.
        return res.data[0] if res.data else {}

    return await asyncio.to_thread(_u)


async def update_reconciliation_aggregates(
    reconciliation_id: UUID,
    *,
    tenant_id: UUID,
    aggregates: AggregatesDTO,
) -> None:
    """Refresh the vat_reconciliations row's aggregate columns after an
    override mutation. Counts (matched_exact / fuzzy / partial / no_match)
    are preserved — overrides only shift the VAT bucket sums.
    """
    supabase = get_supabase_admin()
    payload = {
        "total_invoices": aggregates.total_invoices,
        "matched_exact": aggregates.matched_exact,
        "matched_fuzzy": aggregates.matched_fuzzy,
        "partial_match": aggregates.partial_match,
        "no_match": aggregates.no_match,
        "total_vat_claimed_bdt": str(aggregates.total_vat_claimed_bdt),
        "safe_itc_bdt": str(aggregates.safe_itc_bdt),
        "at_risk_itc_bdt": str(aggregates.at_risk_itc_bdt),
    }

    def _u() -> None:
        (
            supabase.table("vat_reconciliations")
            .update(payload)
            .eq("id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)
