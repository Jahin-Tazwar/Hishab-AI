"""Linker pure-logic tests with mocked DB lookups."""
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.notices.linker import link_notice
from app.notices.schemas import (
    LinkedRecon, NeedsIngestion, NeedsManualLink, NoticeType, ParsedNotice,
)


CLIENT_A = UUID("00000000-0000-0000-0000-00000000000a")
RECON_R = UUID("00000000-0000-0000-0000-0000000000aa")
TENANT = UUID("00000000-0000-0000-0000-000000000099")


def _parsed(**over) -> ParsedNotice:
    base = dict(
        notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001234567",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        classification_confidence=0.95,
    )
    base.update(over)
    return ParsedNotice(**base)


@pytest.mark.asyncio
async def test_linker_returns_linked_recon_on_match(monkeypatch):
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return [CLIENT_A]
    async def fake_find_recon(client_id, *, tenant_id, period_start, period_end):
        return RECON_R
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    monkeypatch.setattr("app.notices.linker.find_recon_by_period",
                        fake_find_recon)

    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, LinkedRecon)
    assert out.reconciliation_id == RECON_R
    assert out.client_id == CLIENT_A


@pytest.mark.asyncio
async def test_linker_returns_needs_ingestion_when_no_recon(monkeypatch):
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return [CLIENT_A]
    async def fake_find_recon(client_id, *, tenant_id, period_start, period_end):
        return None
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    monkeypatch.setattr("app.notices.linker.find_recon_by_period",
                        fake_find_recon)

    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, NeedsIngestion)
    assert out.client_id == CLIENT_A
    assert out.period_start == date(2026, 4, 1)


@pytest.mark.asyncio
async def test_linker_returns_manual_link_when_no_client_match(monkeypatch):
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return []
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, NeedsManualLink)
    assert out.candidate_clients == []


@pytest.mark.asyncio
async def test_linker_returns_manual_link_when_multiple_clients(monkeypatch):
    CLIENT_B = UUID("00000000-0000-0000-0000-00000000000b")
    async def fake_find_client_ids_by_bin(bin_, *, tenant_id):
        return [CLIENT_A, CLIENT_B]
    monkeypatch.setattr("app.notices.linker.find_client_ids_by_bin",
                        fake_find_client_ids_by_bin)
    out = await link_notice(_parsed(), tenant_id=TENANT)
    assert isinstance(out, NeedsManualLink)
    assert set(out.candidate_clients) == {CLIENT_A, CLIENT_B}


@pytest.mark.asyncio
async def test_linker_returns_manual_link_when_no_bin():
    out = await link_notice(_parsed(taxpayer_bin=None), tenant_id=TENANT)
    assert isinstance(out, NeedsManualLink)
