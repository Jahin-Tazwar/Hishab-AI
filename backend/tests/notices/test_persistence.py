"""Live-DB persistence tests. Gated on INGESTION_TEST_TENANT_ID."""
import os
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_TENANT_ID"),
    reason="Live persistence tests require INGESTION_TEST_TENANT_ID",
)


@pytest.fixture
def tenant_id() -> UUID:
    return UUID(os.environ["INGESTION_TEST_TENANT_ID"])


@pytest.fixture
def client_id() -> UUID:
    return UUID(os.environ["INGESTION_TEST_CLIENT_ID"])


@pytest.fixture
def user_id() -> UUID:
    return UUID(os.environ["INGESTION_TEST_USER_ID"])


@pytest.mark.asyncio
async def test_create_get_update_notice_roundtrip(tenant_id, client_id, user_id):
    from app.notices import persistence as p
    from app.notices.schemas import NoticeStatus

    notice_id = await p.create_notice(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        storage_path="placeholder", original_filename="x.pdf",
        mime_type="application/pdf", byte_size=1024,
    )
    n = await p.get_notice(notice_id, tenant_id=tenant_id)
    assert n["status"] == NoticeStatus.PENDING.value

    await p.update_notice(
        notice_id, tenant_id=tenant_id,
        status=NoticeStatus.PARSED,
        notice_no="NBR/X/1", notice_date=date(2026, 5, 1),
        taxpayer_bin="001234567",
        period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        alleged_shortfall_bdt=Decimal("10000.00"),
    )
    n2 = await p.get_notice(notice_id, tenant_id=tenant_id)
    assert n2["status"] == NoticeStatus.PARSED.value
    assert n2["notice_no"] == "NBR/X/1"


@pytest.mark.asyncio
async def test_create_and_update_draft_creates_revisions(
    tenant_id, client_id, user_id,
):
    from app.notices import persistence as p
    from app.notices.schemas import NoticeDraftEditSource, NoticeStatus

    notice_id = await p.create_notice(
        tenant_id=tenant_id, client_id=client_id, created_by=user_id,
        storage_path="placeholder", original_filename="y.pdf",
        mime_type="application/pdf", byte_size=10,
    )
    draft_id = await p.create_draft(
        notice_id=notice_id, tenant_id=tenant_id,
        body_html="<p>v1</p>", appendix_json={"rows": []},
        citations=[], model_version="t",
        edited_by=user_id, edit_source=NoticeDraftEditSource.LLM_GENERATED,
    )
    revs1 = await p.list_revisions(draft_id, tenant_id=tenant_id)
    assert len(revs1) == 1

    await p.update_draft(
        draft_id, tenant_id=tenant_id,
        body_html="<p>v2</p>", appendix_json={"rows": [{"label": "x"}]},
        edited_by=user_id, edit_source=NoticeDraftEditSource.USER_EDIT,
    )
    revs2 = await p.list_revisions(draft_id, tenant_id=tenant_id)
    assert len(revs2) == 2
    assert revs2[0]["revision_no"] == 2
