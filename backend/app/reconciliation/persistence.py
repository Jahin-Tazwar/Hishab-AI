"""Persist a completed reconciliation via the persist_reconciliation RPC."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Iterable
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
