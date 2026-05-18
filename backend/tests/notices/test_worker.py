"""End-to-end worker test with all dependencies stubbed."""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest

from app.notices.llm import StubNoticeLLMAdapter, set_notice_llm_adapter
from app.notices.schemas import (
    CitationChunk, DraftAppendixRow, DraftParagraph, DraftReply,
    LinkedRecon, NeedsIngestion, NoticeStatus, NoticeType, ParsedNotice,
)


@pytest.mark.asyncio
async def test_worker_processes_notice_end_to_end(monkeypatch):
    """Notice with linked recon → parser → linker → retriever → drafter → drafted."""
    from app.notices import worker

    notice_id = uuid4()
    tenant = uuid4()
    client = uuid4()
    recon = uuid4()
    user = uuid4()

    captured_status: list[str] = []

    parsed = ParsedNotice(
        notice_no="X-1", notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567", period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30), classification_confidence=0.95,
        alleged_shortfall_bdt=Decimal("10000.00"),
    )
    draft_reply = DraftReply(
        body_paragraphs=[DraftParagraph(text="hi [CIT-1]", citation_tags=["CIT-1"])],
        computation_table_rows=[DraftAppendixRow(label="x", value_bdt=Decimal("1.00"))],
        cited_refs=["CIT-1"],
    )
    set_notice_llm_adapter(StubNoticeLLMAdapter(
        parses={"any-key": parsed},
        drafts={"any-key": draft_reply},
        embeddings={"q": [0.0] * 768},
    ))

    monkeypatch.setattr(
        worker, "get_notice", AsyncMock(return_value={
            "id": str(notice_id), "tenant_id": str(tenant), "client_id": str(client),
            "created_by": str(user),
            "storage_path": "x/y/z/notice.pdf", "mime_type": "application/pdf",
            "original_filename": "notice.pdf",
            "status": NoticeStatus.PENDING.value,
        }),
    )
    monkeypatch.setattr(worker, "download_original",
                        AsyncMock(return_value=b"%PDF-fake"))
    monkeypatch.setattr(worker, "parse_notice",
                        lambda *a, **kw: parsed)
    monkeypatch.setattr(worker, "link_notice",
                        AsyncMock(return_value=LinkedRecon(
                            reconciliation_id=recon, client_id=client,
                        )))
    monkeypatch.setattr(worker, "fetch_recon_summary",
                        AsyncMock(return_value={
                            "reconciliation_id": str(recon),
                            "safe_itc_bdt": "40000.00", "at_risk_itc_bdt": "10000.00",
                            "total_vat_claimed_bdt": "50000.00",
                            "matched_exact": 8, "matched_fuzzy": 3,
                            "partial_match": 2, "no_match": 2,
                            "disputed_rows": [],
                        }))
    monkeypatch.setattr(worker, "retrieve",
                        AsyncMock(return_value=[CitationChunk(
                            id=UUID("00000000-0000-0000-0000-0000000000aa"),
                            source="vat_act_2012", source_ref="Section 46",
                            subsection=None, language="bn",
                            title="ITC", body="...",
                        )]))
    monkeypatch.setattr(worker, "draft_phase",
                        AsyncMock(return_value={
                            "body_html": "<p>hi</p>",
                            "appendix_json": {"computation_table_rows": []},
                            "citations": [],
                        }))

    async def _upd(notice_id_, *, tenant_id, **fields):
        if "status" in fields:
            captured_status.append(fields["status"].value
                                   if hasattr(fields["status"], "value")
                                   else fields["status"])
    monkeypatch.setattr(worker, "update_notice", _upd)

    monkeypatch.setattr(worker, "get_draft", AsyncMock(return_value=None))
    monkeypatch.setattr(worker, "create_draft", AsyncMock(return_value=uuid4()))

    await worker.process_notice(notice_id, tenant_id=tenant)

    assert "parsing" in captured_status
    assert "drafting" in captured_status
    assert "drafted" in captured_status


@pytest.mark.asyncio
async def test_worker_stops_at_awaiting_data_when_no_recon(monkeypatch):
    from app.notices import worker

    notice_id = uuid4()
    tenant = uuid4()
    client = uuid4()
    user = uuid4()

    set_notice_llm_adapter(StubNoticeLLMAdapter(
        parses={"k": ParsedNotice(
            notice_type=NoticeType.INPUT_VAT_MISMATCH,
            taxpayer_bin="001234567", period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30), classification_confidence=0.9,
        )},
    ))

    monkeypatch.setattr(worker, "get_notice", AsyncMock(return_value={
        "id": str(notice_id), "tenant_id": str(tenant), "client_id": str(client),
        "created_by": str(user),
        "storage_path": "x", "mime_type": "application/pdf",
        "original_filename": "n.pdf", "status": NoticeStatus.PENDING.value,
    }))
    monkeypatch.setattr(worker, "download_original",
                        AsyncMock(return_value=b"%PDF-fake"))
    monkeypatch.setattr(worker, "parse_notice", lambda *a, **kw:
                        ParsedNotice(
                            notice_type=NoticeType.INPUT_VAT_MISMATCH,
                            taxpayer_bin="001234567",
                            period_start=date(2026, 4, 1),
                            period_end=date(2026, 4, 30),
                            classification_confidence=0.9,
                        ))
    monkeypatch.setattr(worker, "link_notice",
                        AsyncMock(return_value=NeedsIngestion(
                            client_id=client,
                            period_start=date(2026, 4, 1),
                            period_end=date(2026, 4, 30),
                        )))
    captured = []
    async def _upd(notice_id_, *, tenant_id, **fields):
        if "status" in fields:
            captured.append(fields["status"].value
                            if hasattr(fields["status"], "value")
                            else fields["status"])
    monkeypatch.setattr(worker, "update_notice", _upd)

    await worker.process_notice(notice_id, tenant_id=tenant)
    assert "awaiting_data" in captured
    assert "drafted" not in captured
