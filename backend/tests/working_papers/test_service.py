"""Service-layer tests for Phase C controls: segregation-of-duties on
finalize, and staleness detection on read. Persistence + recon lookups are
monkeypatched so no live DB is needed.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.working_papers import service as svc
from app.working_papers.exceptions import WorkingPaperReviewError


TENANT = uuid4()
PREPARER = uuid4()
REVIEWER = uuid4()
WP_ID = uuid4()
RECON_ID = uuid4()


def _wp(**over) -> dict:
    base = {
        "id": str(WP_ID),
        "tenant_id": str(TENANT),
        "client_id": str(uuid4()),
        "kind": "at_risk_itc_schedule",
        "reconciliation_id": str(RECON_ID),
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "recipe_version": "v1",
        "composed_json": {
            "summary": {
                "total_vat_claimed_bdt": "50000.00",
                "safe_itc_bdt": "40000.00",
                "at_risk_itc_bdt": "10000.00",
            },
        },
        "notes_html": "",
        "status": "draft",
        "finalized_at": None,
        "finalized_by": None,
        "composed_by": str(PREPARER),
        "created_at": "2026-06-06T00:00:00Z",
        "updated_at": "2026-06-06T00:00:00Z",
    }
    base.update(over)
    return base


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── F7a: segregation of duties ────────────────────────────────────────────


def test_finalize_rejects_preparer_as_reviewer(monkeypatch):
    async def _get(wp_id, *, tenant_id):
        return _wp()
    monkeypatch.setattr(svc.p, "get_working_paper", _get)

    with pytest.raises(WorkingPaperReviewError):
        _run(svc.finalize_working_paper(
            wp_id=WP_ID, tenant_id=TENANT, user_id=PREPARER,  # same as composer
        ))


def test_finalize_allows_distinct_reviewer(monkeypatch):
    captured = {}

    async def _get(wp_id, *, tenant_id):
        return _wp()

    async def _finalize(wp_id, *, tenant_id, finalized_by):
        captured["finalized_by"] = finalized_by

    monkeypatch.setattr(svc.p, "get_working_paper", _get)
    monkeypatch.setattr(svc.p, "finalize_working_paper", _finalize)

    out = _run(svc.finalize_working_paper(
        wp_id=WP_ID, tenant_id=TENANT, user_id=REVIEWER,
    ))
    assert out == WP_ID
    assert captured["finalized_by"] == REVIEWER


def test_finalize_already_finalized_is_idempotent(monkeypatch):
    async def _get(wp_id, *, tenant_id):
        return _wp(status="finalized", finalized_by=str(REVIEWER))
    monkeypatch.setattr(svc.p, "get_working_paper", _get)
    # Should not raise even though we never set finalize_working_paper.
    out = _run(svc.finalize_working_paper(
        wp_id=WP_ID, tenant_id=TENANT, user_id=PREPARER,
    ))
    assert out == WP_ID


# ── F7b: staleness detection ──────────────────────────────────────────────


def test_get_flags_stale_when_recon_aggregates_changed(monkeypatch):
    async def _get(wp_id, *, tenant_id):
        return _wp()

    async def _recon(tenant_id, recon_id):
        # at_risk shifted 10000 -> 12000 after a CA override on the recon
        return {
            "total_vat_claimed_bdt": "50000.00",
            "safe_itc_bdt": "38000.00",
            "at_risk_itc_bdt": "12000.00",
        }

    monkeypatch.setattr(svc.p, "get_working_paper", _get)
    monkeypatch.setattr(svc, "_fetch_recon_aggregates", _recon)

    wp = _run(svc.get_working_paper(wp_id=WP_ID, tenant_id=TENANT))
    assert wp["is_stale"] is True


def test_get_not_stale_when_aggregates_match(monkeypatch):
    async def _get(wp_id, *, tenant_id):
        return _wp()

    async def _recon(tenant_id, recon_id):
        return {
            "total_vat_claimed_bdt": "50000.00",
            "safe_itc_bdt": "40000.00",
            "at_risk_itc_bdt": "10000.00",
        }

    monkeypatch.setattr(svc.p, "get_working_paper", _get)
    monkeypatch.setattr(svc, "_fetch_recon_aggregates", _recon)

    wp = _run(svc.get_working_paper(wp_id=WP_ID, tenant_id=TENANT))
    assert wp["is_stale"] is False


def test_get_not_stale_when_recon_missing(monkeypatch):
    async def _get(wp_id, *, tenant_id):
        return _wp(reconciliation_id=None)

    monkeypatch.setattr(svc.p, "get_working_paper", _get)
    wp = _run(svc.get_working_paper(wp_id=WP_ID, tenant_id=TENANT))
    assert wp["is_stale"] is False


# ── Audit Defense Pack compose ────────────────────────────────────────────


def test_compose_audit_defense_pack_requires_notice_id(monkeypatch):
    from app.working_papers.schemas import WorkingPaperKind
    from app.working_papers.exceptions import WorkingPaperInvalidStateError

    with pytest.raises(WorkingPaperInvalidStateError):
        _run(svc.compose_working_paper(
            tenant_id=TENANT, user_id=PREPARER,
            kind=WorkingPaperKind.AUDIT_DEFENSE_PACK, notice_id=None,
        ))


def test_compose_audit_defense_pack_persists_notice_id(monkeypatch):
    from app.working_papers.schemas import WorkingPaperKind
    from uuid import uuid4
    captured = {}
    notice_id = uuid4()

    class _Recipe:
        id = "audit_defense_pack"
        version = "v1"
        async def compose(self, *, tenant_id, **inputs):
            captured["inputs"] = inputs
            return {
                "kind": "audit_defense_pack", "recipe_version": "v1",
                "client_id": str(uuid4()), "client_name": "X",
                "notice_id": str(notice_id),
                "notice": {}, "reconciliation_id": None,
                "reconciled_position": None, "override_log": [],
                "drafted_reply": None, "evidence_index": [],
            }

    async def _create(**kw):
        captured["create"] = kw
        return uuid4()

    monkeypatch.setattr(svc, "get_recipe", lambda rid: _Recipe())
    monkeypatch.setattr(svc.p, "create_working_paper", _create)

    _run(svc.compose_working_paper(
        tenant_id=TENANT, user_id=PREPARER,
        kind=WorkingPaperKind.AUDIT_DEFENSE_PACK, notice_id=notice_id,
    ))
    assert captured["inputs"] == {"notice_id": notice_id}
    assert captured["create"]["notice_id"] == notice_id
