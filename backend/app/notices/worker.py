"""In-process async worker for notice processing.

Two entry points:
  * `process_notice(notice_id, tenant_id)` — single-shot orchestration of
    all four phases for one notice. Idempotent; reads current status and
    resumes from the right phase.
  * `poll_pending_notices(sleep_s)` — long-running loop; picks up notices
    that were created on a different instance or whose lease expired.

Lease pattern mirrors app/ingestion/worker.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog

from app.database import get_supabase_admin
from app.notices.drafter import draft as draft_phase
from app.notices.linker import link_notice
from app.notices.llm import get_notice_llm_adapter
from app.notices.parser import parse_notice
from app.notices.persistence import (
    create_draft, fetch_recon_summary, get_draft, get_notice, update_notice,
)
from app.notices.retriever import retrieve
from app.notices.schemas import (
    LinkedRecon, NeedsIngestion, NeedsManualLink,
    NoticeDraftEditSource, NoticeStatus, ParsedNotice, ReconSummary,
)
from app.notices.storage import download_original

log = structlog.get_logger()

_LEASE_TIMEOUT = timedelta(minutes=10)
_MODEL_VERSION = "gemini-2.5-flash | prompt v1"


async def process_notice(notice_id: UUID, *, tenant_id: UUID) -> None:
    """Run all four phases for one notice. Safe to call repeatedly."""
    notice = await get_notice(notice_id, tenant_id=tenant_id)
    if notice is None:
        log.warning("notices.worker.not_found", notice_id=str(notice_id))
        return

    adapter = get_notice_llm_adapter()
    status = notice["status"]

    try:
        if status in (NoticeStatus.PENDING.value, NoticeStatus.PARSING.value,
                      NoticeStatus.FAILED.value):
            await update_notice(notice_id, tenant_id=tenant_id,
                                status=NoticeStatus.PARSING, parse_error=None)
            content = await download_original(notice["storage_path"])
            # parse_notice is sync (Gemini Vision call blocks for several
            # seconds). Run it in a worker thread so other API requests stay
            # responsive while a notice parses.
            parsed: ParsedNotice = await asyncio.to_thread(
                parse_notice,
                content, mime=notice["mime_type"], adapter=adapter,
                filename=notice["original_filename"],
            )
            await update_notice(
                notice_id, tenant_id=tenant_id,
                status=NoticeStatus.PARSED,
                notice_no=parsed.notice_no,
                notice_date=parsed.notice_date,
                notice_type=parsed.notice_type,
                taxpayer_bin=parsed.taxpayer_bin,
                taxpayer_tin=parsed.taxpayer_tin,
                period_start=parsed.period_start,
                period_end=parsed.period_end,
                alleged_itc_claimed_bdt=parsed.alleged_itc_claimed_bdt,
                alleged_itc_allowed_bdt=parsed.alleged_itc_allowed_bdt,
                alleged_shortfall_bdt=parsed.alleged_shortfall_bdt,
            )
            if (parsed.notice_type.value != "input_vat_mismatch"
                    or parsed.classification_confidence < 0.7):
                await update_notice(
                    notice_id, tenant_id=tenant_id, status=NoticeStatus.FAILED,
                    parse_error="Notice category not supported in V1 "
                                "(only input VAT mismatch is supported).",
                )
                return
            notice = await get_notice(notice_id, tenant_id=tenant_id)
            status = notice["status"]
        else:
            parsed = _parsed_from_notice_row(notice)

        link = await link_notice(parsed, tenant_id=tenant_id)
        if isinstance(link, NeedsIngestion):
            await update_notice(notice_id, tenant_id=tenant_id,
                                status=NoticeStatus.AWAITING_DATA)
            return
        if isinstance(link, NeedsManualLink):
            await update_notice(notice_id, tenant_id=tenant_id,
                                status=NoticeStatus.PARSED)
            return
        assert isinstance(link, LinkedRecon)
        await update_notice(
            notice_id, tenant_id=tenant_id,
            status=NoticeStatus.READY_TO_DRAFT,
            linked_reconciliation_id=link.reconciliation_id,
        )

        existing_draft = await get_draft(notice_id, tenant_id=tenant_id)
        if existing_draft is not None:
            return

        await update_notice(notice_id, tenant_id=tenant_id,
                            status=NoticeStatus.DRAFTING)
        summary_dict = await fetch_recon_summary(
            link.reconciliation_id, tenant_id=tenant_id,
        )
        summary = ReconSummary(**summary_dict)
        chunks = await retrieve(parsed, summary, adapter=adapter)
        finalized = await draft_phase(parsed, summary, chunks, adapter=adapter)

        await create_draft(
            notice_id=notice_id, tenant_id=tenant_id,
            body_html=finalized["body_html"],
            appendix_json=finalized["appendix_json"],
            citations=finalized["citations"],
            model_version=_MODEL_VERSION,
            edited_by=UUID(notice["created_by"]),
            edit_source=NoticeDraftEditSource.LLM_GENERATED,
        )
        await update_notice(notice_id, tenant_id=tenant_id,
                            status=NoticeStatus.DRAFTED)
    except Exception as e:
        log.exception("notices.worker.failed",
                      notice_id=str(notice_id), error=str(e))
        await update_notice(
            notice_id, tenant_id=tenant_id,
            status=NoticeStatus.FAILED, parse_error=str(e)[:500],
        )


def _parsed_from_notice_row(n: dict) -> ParsedNotice:
    """Re-hydrate a ParsedNotice from a persisted notice row."""
    from datetime import date
    from decimal import Decimal
    def _date(v): return date.fromisoformat(v) if v else None
    def _dec(v): return Decimal(str(v)) if v is not None else None
    return ParsedNotice(
        notice_no=n.get("notice_no"),
        notice_date=_date(n.get("notice_date")),
        notice_type=n["notice_type"] or "input_vat_mismatch",
        taxpayer_bin=n.get("taxpayer_bin"),
        taxpayer_tin=n.get("taxpayer_tin"),
        period_start=_date(n.get("period_start")),
        period_end=_date(n.get("period_end")),
        alleged_itc_claimed_bdt=_dec(n.get("alleged_itc_claimed_bdt")),
        alleged_itc_allowed_bdt=_dec(n.get("alleged_itc_allowed_bdt")),
        alleged_shortfall_bdt=_dec(n.get("alleged_shortfall_bdt")),
        classification_confidence=1.0,
    )


async def poll_pending_notices(*, sleep_s: float = 5.0) -> None:
    """Long-running loop that re-claims stuck notices."""
    sb = get_supabase_admin()
    log.info("notices.worker.loop_started")
    while True:
        try:
            cutoff = (datetime.now(timezone.utc) - _LEASE_TIMEOUT).isoformat()

            def _q():
                return (
                    sb.table("notices")
                    .select("id, tenant_id, status, updated_at")
                    .in_("status", [NoticeStatus.PENDING.value,
                                    NoticeStatus.PARSING.value,
                                    NoticeStatus.DRAFTING.value])
                    .order("created_at")
                    .limit(20)
                    .execute()
                )

            res = await asyncio.to_thread(_q)
            for row in res.data or []:
                if (row["status"] in (NoticeStatus.PARSING.value,
                                      NoticeStatus.DRAFTING.value)
                        and row["updated_at"] > cutoff):
                    continue
                asyncio.create_task(
                    process_notice(UUID(row["id"]), tenant_id=UUID(row["tenant_id"]))
                )
        except Exception as e:
            log.exception("notices.worker.poll_error", error=str(e))
        await asyncio.sleep(sleep_s)
