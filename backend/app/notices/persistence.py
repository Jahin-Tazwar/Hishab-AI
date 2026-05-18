"""Database I/O for the notices module. Uses the supabase admin client.

All callers are expected to have validated tenant scope already; the
`tenant_id` arg is defense-in-depth on every query.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import get_supabase_admin
from app.notices.schemas import (
    NoticeDraftEditSource,
    NoticeDraftStatus,
    NoticeStatus,
)


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


# ── Citation corpus ANN ───────────────────────────────────────────────────


async def retrieve_citation_chunks(
    *, embedding: list[float], topic_tags: list[str], k: int,
) -> list[dict]:
    """ANN over citation_corpus_chunks, pre-filtered by topic_tags overlap.

    Returns at most 2*k DB rows (both languages × k groups). Caller dedupes
    by (source, source_ref, subsection) if needed.
    """
    from app.notices.schemas import CitationChunk

    sb = get_supabase_admin()
    def _rpc():
        return sb.rpc(
            "match_citation_chunks",
            {
                "query_embedding": embedding,
                "match_topic_tags": topic_tags,
                "match_k": k,
            },
        ).execute()

    res = await asyncio.to_thread(_rpc)
    rows = res.data or []
    return [
        CitationChunk(
            id=r["id"], source=r["source"], source_ref=r["source_ref"],
            subsection=r.get("subsection"), language=r["language"],
            title=r["title"], body=r["body"],
        )
        for r in rows
    ]


# ── Notice CRUD ──────────────────────────────────────────────────────────


async def create_notice(
    *,
    tenant_id: UUID,
    client_id: UUID,
    created_by: UUID,
    storage_path: str,
    original_filename: str,
    mime_type: str,
    byte_size: int,
) -> UUID:
    sb = get_supabase_admin()

    def _ins():
        return sb.table("notices").insert({
            "tenant_id": str(tenant_id),
            "client_id": str(client_id),
            "created_by": str(created_by),
            "storage_path": storage_path,
            "original_filename": original_filename,
            "mime_type": mime_type,
            "byte_size": byte_size,
            "status": NoticeStatus.PENDING.value,
        }).execute()

    res = await asyncio.to_thread(_ins)
    return UUID(res.data[0]["id"])


async def get_notice(notice_id: UUID, *, tenant_id: UUID) -> Optional[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notices")
            .select("*")
            .eq("id", str(notice_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def list_notices(
    *, tenant_id: UUID, client_id: UUID, limit: int = 100,
) -> List[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notices")
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("client_id", str(client_id))
            .order("notice_date", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


async def update_notice(
    notice_id: UUID, *, tenant_id: UUID, **fields: Any,
) -> None:
    """Update arbitrary fields on a notice. Enum values are .value-unwrapped."""
    payload: Dict[str, Any] = {}
    for k, v in fields.items():
        if v is None:
            continue
        if hasattr(v, "value"):
            payload[k] = v.value
        elif isinstance(v, Decimal):
            payload[k] = str(v)
        elif isinstance(v, (date, datetime)):
            payload[k] = v.isoformat()
        elif isinstance(v, UUID):
            payload[k] = str(v)
        else:
            payload[k] = v
    if not payload:
        return
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("notices")
            .update(payload)
            .eq("id", str(notice_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Draft CRUD (with append-only revisions) ──────────────────────────────


async def create_draft(
    *,
    notice_id: UUID,
    tenant_id: UUID,
    body_html: str,
    appendix_json: Dict[str, Any],
    citations: List[Dict[str, Any]],
    model_version: str,
    edited_by: UUID,
    edit_source: NoticeDraftEditSource,
) -> UUID:
    """Create the head draft row + revision #1 atomically (two inserts)."""
    sb = get_supabase_admin()

    def _ins_draft():
        return sb.table("notice_drafts").insert({
            "tenant_id": str(tenant_id),
            "notice_id": str(notice_id),
            "language": "bn",
            "body_html": body_html,
            "appendix_json": appendix_json,
            "citations": citations,
            "model_version": model_version,
            "status": NoticeDraftStatus.DRAFT.value,
        }).execute()

    res = await asyncio.to_thread(_ins_draft)
    draft_id = UUID(res.data[0]["id"])

    def _ins_rev():
        return sb.table("notice_draft_revisions").insert({
            "tenant_id": str(tenant_id),
            "draft_id": str(draft_id),
            "revision_no": 1,
            "body_html": body_html,
            "appendix_json": appendix_json,
            "edited_by": str(edited_by),
            "edit_source": edit_source.value,
        }).execute()

    await asyncio.to_thread(_ins_rev)
    return draft_id


async def get_draft(notice_id: UUID, *, tenant_id: UUID) -> Optional[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notice_drafts")
            .select("*")
            .eq("notice_id", str(notice_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def update_draft(
    draft_id: UUID, *,
    tenant_id: UUID,
    body_html: str,
    appendix_json: Dict[str, Any],
    edited_by: UUID,
    edit_source: NoticeDraftEditSource,
    edit_reason: Optional[str] = None,
    citations: Optional[List[Dict[str, Any]]] = None,
    model_version: Optional[str] = None,
) -> None:
    """Patch the head + append a revision in the same logical save."""
    sb = get_supabase_admin()

    head_payload: Dict[str, Any] = {
        "body_html": body_html,
        "appendix_json": appendix_json,
    }
    if citations is not None:
        head_payload["citations"] = citations
    if model_version is not None:
        head_payload["model_version"] = model_version

    def _patch_head():
        return (
            sb.table("notice_drafts")
            .update(head_payload)
            .eq("id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_patch_head)

    def _max_rev():
        return (
            sb.table("notice_draft_revisions")
            .select("revision_no")
            .eq("draft_id", str(draft_id))
            .order("revision_no", desc=True)
            .limit(1)
            .execute()
        )

    mrev = await asyncio.to_thread(_max_rev)
    next_no = (mrev.data[0]["revision_no"] if mrev.data else 0) + 1

    def _ins_rev():
        return sb.table("notice_draft_revisions").insert({
            "tenant_id": str(tenant_id),
            "draft_id": str(draft_id),
            "revision_no": next_no,
            "body_html": body_html,
            "appendix_json": appendix_json,
            "edited_by": str(edited_by),
            "edit_source": edit_source.value,
            "edit_reason": edit_reason,
        }).execute()

    await asyncio.to_thread(_ins_rev)


async def list_revisions(
    draft_id: UUID, *, tenant_id: UUID,
) -> List[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("notice_draft_revisions")
            .select("id, revision_no, edited_by, edit_source, edit_reason, created_at")
            .eq("draft_id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .order("revision_no", desc=True)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []


async def finalize_draft(
    draft_id: UUID, *, tenant_id: UUID, finalized_by: UUID,
) -> None:
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("notice_drafts")
            .update({
                "status": NoticeDraftStatus.FINALIZED.value,
                "finalized_at": datetime.now(timezone.utc).isoformat(),
                "finalized_by": str(finalized_by),
            })
            .eq("id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def reopen_draft(draft_id: UUID, *, tenant_id: UUID) -> None:
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("notice_drafts")
            .update({
                "status": NoticeDraftStatus.DRAFT.value,
                "finalized_at": None,
                "finalized_by": None,
            })
            .eq("id", str(draft_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


# ── Reconciliation summary for the drafter ───────────────────────────────


async def fetch_recon_summary(
    reconciliation_id: UUID, *, tenant_id: UUID,
) -> Dict[str, Any]:
    """Fetch the header aggregates + a representative sample of disputed rows.

    Returns a dict suitable for constructing ReconSummary. Column names are
    verified against migration 0002_tenant_tables.sql (vat_reconciliations
    and recon_line_items).
    """
    sb = get_supabase_admin()

    def _hdr():
        return (
            sb.table("vat_reconciliations")
            .select("*")
            .eq("id", str(reconciliation_id))
            .eq("tenant_id", str(tenant_id))
            .single()
            .execute()
        )

    def _rows():
        return (
            sb.table("recon_line_items")
            .select("pr_supplier_name, pr_supplier_bin, pr_invoice_no, "
                    "pr_vat_amount_bdt, match_status")
            .eq("tenant_id", str(tenant_id))
            .eq("reconciliation_id", str(reconciliation_id))
            .in_("match_status", ["partial", "no_match"])
            .limit(20)
            .execute()
        )

    hdr = (await asyncio.to_thread(_hdr)).data
    rows = (await asyncio.to_thread(_rows)).data or []
    return {
        "reconciliation_id": hdr["id"],
        "safe_itc_bdt": hdr.get("safe_itc_bdt") or "0",
        "at_risk_itc_bdt": hdr.get("at_risk_itc_bdt") or "0",
        "total_vat_claimed_bdt": hdr.get("total_vat_claimed_bdt") or "0",
        "matched_exact": hdr.get("matched_exact") or 0,
        "matched_fuzzy": hdr.get("matched_fuzzy") or 0,
        "partial_match": hdr.get("partial_match") or 0,
        "no_match": hdr.get("no_match") or 0,
        "disputed_rows": [
            {
                "supplier_name": r.get("pr_supplier_name"),
                "supplier_bin":  r.get("pr_supplier_bin"),
                "invoice_no":    r.get("pr_invoice_no"),
                "vat_amount_bdt": r.get("pr_vat_amount_bdt"),
                "match_status":  r.get("match_status"),
            }
            for r in rows
        ],
    }
