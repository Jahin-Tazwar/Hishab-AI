"""Reconciliation orchestrator: validate → download → parse → match → persist."""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

import structlog

from .access import fetch_and_validate_documents
from .aggregates import aggregate, aggregate_from_db_rows
from .matcher import match_register
from .parser import parse_purchase_register, parse_supplier_export
from .persistence import (
    fetch_line_item,
    fetch_line_items,
    fetch_reconciliation_header,
    persist_reconciliation,
    update_line_item_override,
    update_reconciliation_aggregates,
)
from .schemas import (
    AggregatesDTO,
    CAOverride,
    LineItemOverrideResponse,
    ReconciliationCreateRequest,
)
from .storage import download_xlsx

logger = structlog.get_logger()
BUCKET = "recon-files"


async def run_reconciliation(
    req: ReconciliationCreateRequest,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> UUID:
    log = logger.bind(
        tenant_id=str(tenant_id),
        client_id=str(req.client_id),
        user_id=str(user_id),
    )

    # 1. Defense in depth — both docs belong to caller's tenant and client
    paths = await fetch_and_validate_documents(
        pr_doc_id=req.purchase_register_doc_id,
        sf_doc_id=req.supplier_data_doc_id,
        tenant_id=tenant_id,
        client_id=req.client_id,
    )
    log.info("recon.docs_validated")

    # 2. Download both files in parallel
    pr_bytes, sf_bytes = await asyncio.gather(
        download_xlsx(BUCKET, paths.pr_path),
        download_xlsx(BUCKET, paths.sf_path),
    )
    log.info("recon.storage_downloaded",
             pr_bytes=len(pr_bytes), sf_bytes=len(sf_bytes))

    # 3. Parse + match (CPU-bound; offload via to_thread to avoid blocking the loop)
    def _process():
        pr_rows = parse_purchase_register(pr_bytes)
        sf_rows = parse_supplier_export(sf_bytes)
        matches = match_register(pr_rows, sf_rows)
        agg = aggregate(matches)
        return matches, agg

    matches, agg = await asyncio.to_thread(_process)
    log.info(
        "recon.matched",
        total=agg.total_invoices,
        exact=agg.matched_exact, fuzzy=agg.matched_fuzzy,
        partial=agg.partial_match, no_match=agg.no_match,
        safe_itc_bdt=str(agg.safe_itc_bdt),
        at_risk_itc_bdt=str(agg.at_risk_itc_bdt),
    )

    # 4. Persist
    recon_id = await persist_reconciliation(
        tenant_id=tenant_id,
        client_id=req.client_id,
        period_start=req.period_start,
        period_end=req.period_end,
        run_by=user_id,
        pr_doc_id=req.purchase_register_doc_id,
        sf_doc_id=req.supplier_data_doc_id,
        aggregates=agg,
        matches=matches,
    )
    log.info("recon.persisted", reconciliation_id=str(recon_id))
    return recon_id


class ReconciliationNotFound(Exception):
    """The reconciliation either doesn't exist or doesn't belong to the
    caller's tenant. Maps to 404 at the router boundary."""


class LineItemNotFound(Exception):
    """The line item either doesn't exist or doesn't belong to the recon /
    tenant pair. Maps to 404."""


async def override_line_item(
    *,
    reconciliation_id: UUID,
    line_item_id: UUID,
    tenant_id: UUID,
    ca_override: Optional[CAOverride],
    ca_notes: Optional[str],
) -> LineItemOverrideResponse:
    """Update a single line item's CA decision and recompute the headline
    aggregates atomically.

    Steps:
      1. Confirm the reconciliation belongs to the caller's tenant.
      2. Confirm the line item belongs to that reconciliation.
      3. Update the line item's `ca_override` + `ca_notes`.
      4. Re-fetch all line items (now with the updated row) and recompute
         aggregates honoring override semantics.
      5. Update the vat_reconciliations row's aggregate columns.
      6. Return the new aggregates so the caller can refresh its local
         cache without a second round-trip.

    Match-status counts (matched_exact, matched_fuzzy, partial_match,
    no_match) are NOT touched — they reflect what the engine produced
    and shouldn't shift under user edits.
    """
    log = logger.bind(
        tenant_id=str(tenant_id),
        reconciliation_id=str(reconciliation_id),
        line_item_id=str(line_item_id),
    )

    header = await fetch_reconciliation_header(
        reconciliation_id, tenant_id=tenant_id,
    )
    if header is None:
        raise ReconciliationNotFound(str(reconciliation_id))

    existing = await fetch_line_item(
        line_item_id, reconciliation_id=reconciliation_id, tenant_id=tenant_id,
    )
    if existing is None:
        raise LineItemNotFound(str(line_item_id))

    override_value = ca_override.value if ca_override is not None else None
    await update_line_item_override(
        line_item_id,
        reconciliation_id=reconciliation_id,
        tenant_id=tenant_id,
        ca_override=override_value,
        ca_notes=ca_notes,
    )

    rows = await fetch_line_items(reconciliation_id, tenant_id=tenant_id)
    new_aggregates: AggregatesDTO = aggregate_from_db_rows(rows)
    await update_reconciliation_aggregates(
        reconciliation_id, tenant_id=tenant_id, aggregates=new_aggregates,
    )

    log.info(
        "recon.line_item.override_saved",
        ca_override=override_value,
        safe_itc_bdt=str(new_aggregates.safe_itc_bdt),
        at_risk_itc_bdt=str(new_aggregates.at_risk_itc_bdt),
    )

    return LineItemOverrideResponse(
        line_item_id=line_item_id,
        ca_override=ca_override,
        ca_notes=ca_notes,
        aggregates=new_aggregates,
    )
