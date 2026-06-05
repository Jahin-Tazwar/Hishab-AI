"""Database I/O for working papers. Uses the supabase admin client.

All callers are expected to have validated tenant scope already; the
`tenant_id` arg is defense-in-depth on every query.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.database import get_supabase_admin
from app.working_papers.schemas import (
    WorkingPaperEditSource,
    WorkingPaperKind,
    WorkingPaperStatus,
)


def _json_safe(value: Any) -> Any:
    """Recursively coerce Decimal/date/datetime/UUID into JSON-serializable."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


# ── CRUD ─────────────────────────────────────────────────────────────────


async def create_working_paper(
    *,
    tenant_id: UUID,
    client_id: UUID,
    kind: WorkingPaperKind,
    reconciliation_id: Optional[UUID],
    notice_id: Optional[UUID] = None,
    period_start: Optional[date],
    period_end: Optional[date],
    recipe_version: str,
    composed_json: Dict[str, Any],
    composed_by: UUID,
) -> UUID:
    """Insert the head row + revision_no=1 with edit_source='recipe_composed'."""
    sb = get_supabase_admin()
    payload = _json_safe(composed_json)

    def _ins_wp():
        return sb.table("working_papers").insert({
            "tenant_id": str(tenant_id),
            "client_id": str(client_id),
            "kind": kind.value,
            "reconciliation_id": str(reconciliation_id) if reconciliation_id else None,
            "notice_id": str(notice_id) if notice_id else None,
            "period_start": period_start.isoformat() if period_start else None,
            "period_end": period_end.isoformat() if period_end else None,
            "recipe_version": recipe_version,
            "composed_json": payload,
            "notes_html": "",
            "status": WorkingPaperStatus.DRAFT.value,
            "composed_by": str(composed_by),
        }).execute()

    res = await asyncio.to_thread(_ins_wp)
    wp_id = UUID(res.data[0]["id"])

    def _ins_rev():
        return sb.table("working_paper_revisions").insert({
            "tenant_id": str(tenant_id),
            "working_paper_id": str(wp_id),
            "revision_no": 1,
            "composed_json": payload,
            "notes_html": "",
            "edited_by": str(composed_by),
            "edit_source": WorkingPaperEditSource.RECIPE_COMPOSED.value,
        }).execute()

    await asyncio.to_thread(_ins_rev)
    return wp_id


async def get_working_paper(
    wp_id: UUID, *, tenant_id: UUID,
) -> Optional[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("working_papers")
            .select("*")
            .eq("id", str(wp_id))
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data[0] if res.data else None


async def update_working_paper(
    wp_id: UUID,
    *,
    tenant_id: UUID,
    edited_by: UUID,
    edit_source: WorkingPaperEditSource,
    notes_html: Optional[str] = None,
    composed_json: Optional[Dict[str, Any]] = None,
    edit_reason: Optional[str] = None,
) -> None:
    """Patch the head + append a revision in the same logical save."""
    sb = get_supabase_admin()

    head_payload: Dict[str, Any] = {}
    if notes_html is not None:
        head_payload["notes_html"] = notes_html
    if composed_json is not None:
        head_payload["composed_json"] = _json_safe(composed_json)
    if not head_payload:
        return

    def _patch_head():
        return (
            sb.table("working_papers")
            .update(head_payload)
            .eq("id", str(wp_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_patch_head)

    # Need the *current* full state for the revision row, since revisions are
    # snapshots, not patches.
    current = await get_working_paper(wp_id, tenant_id=tenant_id)
    if current is None:
        return

    def _max_rev():
        return (
            sb.table("working_paper_revisions")
            .select("revision_no")
            .eq("working_paper_id", str(wp_id))
            .order("revision_no", desc=True)
            .limit(1)
            .execute()
        )

    mrev = await asyncio.to_thread(_max_rev)
    next_no = (mrev.data[0]["revision_no"] if mrev.data else 0) + 1

    def _ins_rev():
        return sb.table("working_paper_revisions").insert({
            "tenant_id": str(tenant_id),
            "working_paper_id": str(wp_id),
            "revision_no": next_no,
            "composed_json": _json_safe(current["composed_json"]),
            "notes_html": current.get("notes_html") or "",
            "edited_by": str(edited_by),
            "edit_source": edit_source.value,
            "edit_reason": edit_reason,
        }).execute()

    await asyncio.to_thread(_ins_rev)


async def finalize_working_paper(
    wp_id: UUID, *, tenant_id: UUID, finalized_by: UUID,
) -> None:
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("working_papers")
            .update({
                "status": WorkingPaperStatus.FINALIZED.value,
                "finalized_at": datetime.now(timezone.utc).isoformat(),
                "finalized_by": str(finalized_by),
            })
            .eq("id", str(wp_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def reopen_working_paper(wp_id: UUID, *, tenant_id: UUID) -> None:
    sb = get_supabase_admin()

    def _u():
        return (
            sb.table("working_papers")
            .update({
                "status": WorkingPaperStatus.DRAFT.value,
                "finalized_at": None,
                "finalized_by": None,
            })
            .eq("id", str(wp_id))
            .eq("tenant_id", str(tenant_id))
            .execute()
        )

    await asyncio.to_thread(_u)


async def list_working_papers(
    *,
    tenant_id: UUID,
    client_id: Optional[UUID] = None,
    kind: Optional[WorkingPaperKind] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        q = (
            sb.table("working_papers")
            .select("*")
            .eq("tenant_id", str(tenant_id))
        )
        if client_id is not None:
            q = q.eq("client_id", str(client_id))
        if kind is not None:
            q = q.eq("kind", kind.value)
        return q.order("created_at", desc=True).limit(limit).execute()

    res = await asyncio.to_thread(_q)
    return res.data or []


async def list_revisions(
    wp_id: UUID, *, tenant_id: UUID,
) -> List[Dict[str, Any]]:
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("working_paper_revisions")
            .select("id, revision_no, edited_by, edit_source, edit_reason, created_at")
            .eq("working_paper_id", str(wp_id))
            .eq("tenant_id", str(tenant_id))
            .order("revision_no", desc=True)
            .execute()
        )

    res = await asyncio.to_thread(_q)
    return res.data or []
