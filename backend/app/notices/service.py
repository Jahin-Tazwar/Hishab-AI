"""High-level service operations called by the FastAPI router."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional
from uuid import UUID

import structlog
from fastapi import UploadFile

from app.notices import persistence as p
from app.notices import storage as st
from app.notices.exceptions import (
    DraftNotFoundError, NoticeInvalidStateError, NoticeNotFoundError,
    NoticeUnsupportedTypeError,
)
from app.notices.rendering import (
    PdfRendererUnavailableError, render_docx, render_pdf,
)
from app.notices.schemas import (
    NoticeDraftEditSource, NoticeDraftStatus, NoticeStatus,
)
from app.notices.worker import process_notice

log = structlog.get_logger()


_MAX_BYTES = 25 * 1024 * 1024
_ACCEPTED_MIMES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png",
    "image/heic", "image/heif", "image/webp", "image/tiff",
}


async def create_notice(
    *, tenant_id: UUID, user_id: UUID, client_id: UUID, file: UploadFile,
) -> UUID:
    content = await file.read()
    size = len(content)
    if size > _MAX_BYTES:
        raise NoticeUnsupportedTypeError(
            filename=file.filename or "<unnamed>",
            mime=f"file too large ({size} bytes > {_MAX_BYTES})",
        )
    mime = (file.content_type or "").strip().lower() or "application/octet-stream"
    if mime not in _ACCEPTED_MIMES:
        raise NoticeUnsupportedTypeError(
            filename=file.filename or "<unnamed>", mime=mime,
        )

    notice_id = await p.create_notice(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        storage_path="placeholder",
        original_filename=file.filename or f"notice-{notice_id_placeholder()}",
        mime_type=mime, byte_size=size,
    )
    path = await st.upload_original(
        tenant_id=tenant_id, client_id=client_id, notice_id=notice_id,
        filename=file.filename or f"notice-{notice_id}", content=content,
        mime_type=mime,
    )
    await p.update_notice(notice_id, tenant_id=tenant_id, storage_path=path)

    asyncio.create_task(process_notice(notice_id, tenant_id=tenant_id))
    return notice_id


def notice_id_placeholder() -> str:
    """Filename placeholder used before we know the real notice_id."""
    from uuid import uuid4
    return str(uuid4())


async def _fetch_tenant_meta(tenant_id: UUID) -> dict:
    """Letterhead fields from the tenants row. Falls back to neutral defaults.

    V1 reads `firm_name` and `address` only; both are optional on the
    existing tenants schema so we tolerate missing columns/rows.
    """
    from app.database import get_supabase_admin
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("tenants")
            .select("*")
            .eq("id", str(tenant_id))
            .single()
            .execute()
        )

    try:
        res = await asyncio.to_thread(_q)
        row = res.data or {}
    except Exception:
        row = {}
    return {
        "firm_name": row.get("name") or row.get("firm_name") or "Chartered Accountants",
        "address": row.get("address") or "",
    }


async def relink_notice(
    *, notice_id: UUID, tenant_id: UUID,
    client_id: UUID, period_start: date, period_end: date,
    reconciliation_id: Optional[UUID] = None,
) -> None:
    notice = await p.get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        raise NoticeNotFoundError(f"Notice {notice_id} not found")

    fields = dict(
        client_id=client_id,
        period_start=period_start,
        period_end=period_end,
    )
    if reconciliation_id is not None:
        fields["linked_reconciliation_id"] = reconciliation_id
        fields["status"] = NoticeStatus.READY_TO_DRAFT
    await p.update_notice(notice_id, tenant_id=tenant_id, **fields)
    asyncio.create_task(process_notice(notice_id, tenant_id=tenant_id))


async def generate_draft(*, notice_id: UUID, tenant_id: UUID) -> None:
    notice = await p.get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        raise NoticeNotFoundError(f"Notice {notice_id} not found")
    if notice["status"] not in (NoticeStatus.READY_TO_DRAFT.value,
                                NoticeStatus.DRAFTED.value):
        raise NoticeInvalidStateError(
            f"Cannot draft from status={notice['status']}; need ready_to_draft or drafted",
        )
    # Drop existing draft so process_notice will re-create one
    if notice["status"] == NoticeStatus.DRAFTED.value:
        existing = await p.get_draft(notice_id, tenant_id=tenant_id)
        if existing:
            # We don't physically delete — we just blow status back to ready_to_draft
            # so the worker re-runs; the existing draft + its revisions stay as history
            await p.update_notice(notice_id, tenant_id=tenant_id,
                                  status=NoticeStatus.READY_TO_DRAFT)
    asyncio.create_task(process_notice(notice_id, tenant_id=tenant_id))


async def save_draft_revision(
    *, notice_id: UUID, tenant_id: UUID, user_id: UUID,
    body_html: str, appendix_json: dict,
) -> None:
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    if draft["status"] == NoticeDraftStatus.FINALIZED.value:
        raise NoticeInvalidStateError("Draft is finalized; reopen first")
    await p.update_draft(
        UUID(draft["id"]), tenant_id=tenant_id,
        body_html=body_html, appendix_json=appendix_json,
        edited_by=user_id, edit_source=NoticeDraftEditSource.USER_EDIT,
    )


async def finalize_draft(
    *, notice_id: UUID, tenant_id: UUID, user_id: UUID,
) -> UUID:
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    if draft["status"] == NoticeDraftStatus.FINALIZED.value:
        return UUID(draft["id"])  # idempotent
    await p.finalize_draft(
        UUID(draft["id"]), tenant_id=tenant_id, finalized_by=user_id,
    )
    await p.update_notice(notice_id, tenant_id=tenant_id,
                          status=NoticeStatus.FINALIZED)
    return UUID(draft["id"])


async def reopen_draft_for_edit(
    *, notice_id: UUID, tenant_id: UUID, user_id: UUID, reason: str,
) -> None:
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")
    await p.reopen_draft(UUID(draft["id"]), tenant_id=tenant_id)
    await p.update_notice(notice_id, tenant_id=tenant_id,
                          status=NoticeStatus.DRAFTED)
    # Log the reopen as an edit-source row so we have the reason recorded
    await p.update_draft(
        UUID(draft["id"]), tenant_id=tenant_id,
        body_html=draft["body_html"], appendix_json=draft["appendix_json"],
        edited_by=user_id, edit_source=NoticeDraftEditSource.USER_EDIT,
        edit_reason=f"Reopened: {reason}",
    )


async def export_draft(
    *, notice_id: UUID, tenant_id: UUID, format: str,
) -> tuple[bytes, str, str]:
    """Returns (bytes, content_type, filename)."""
    if format not in ("docx", "pdf"):
        raise NoticeInvalidStateError(f"Unsupported export format: {format}")
    notice = await p.get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        raise NoticeNotFoundError(f"Notice {notice_id} not found")
    draft = await p.get_draft(notice_id, tenant_id=tenant_id)
    if draft is None:
        raise DraftNotFoundError(f"No draft for notice {notice_id}")

    tenant_meta = await _fetch_tenant_meta(tenant_id)
    docx_bytes = render_docx(draft=draft, notice=notice, tenant=tenant_meta)
    if format == "docx":
        return (docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                f"notice-{notice_id}.docx")
    try:
        pdf_bytes = render_pdf(docx_bytes)
    except PdfRendererUnavailableError as e:
        # Surface a 503 via a custom error
        err = NoticeInvalidStateError(str(e))
        err.default_status = 503
        err.status_code = 503
        raise err
    return (pdf_bytes, "application/pdf", f"notice-{notice_id}.pdf")
