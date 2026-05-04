"""Reconciliation orchestrator: validate → download → parse → match → persist."""
from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from .access import fetch_and_validate_documents
from .aggregates import aggregate
from .matcher import match_register
from .parser import parse_purchase_register, parse_supplier_export
from .persistence import persist_reconciliation
from .schemas import ReconciliationCreateRequest
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
