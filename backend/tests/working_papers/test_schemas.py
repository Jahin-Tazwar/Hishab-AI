"""Pydantic validation for working_papers schemas."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.working_papers.schemas import (
    AtRiskItcSchedulePayload,
    AtRiskLine,
    AtRiskSummary,
    AtRiskSupplierGroup,
    WorkingPaperKind,
    WorkingPaperPayload,
    WorkingPaperStatus,
)


def _line(**overrides) -> AtRiskLine:
    base = dict(
        line_id=uuid4(),
        supplier_name="ACME Ltd",
        supplier_bin="123456789",
        invoice_no="INV-1",
        invoice_date=date(2026, 4, 5),
        taxable_amount_bdt=Decimal("1000.00"),
        vat_amount_bdt=Decimal("150.00"),
        match_status="no_match",
        match_score=None,
        ca_override=None,
        ca_notes=None,
        recommended_action="chase_supplier",
    )
    base.update(overrides)
    return AtRiskLine(**base)


def _payload(**overrides) -> AtRiskItcSchedulePayload:
    base = dict(
        recipe_version="v1",
        client_id=uuid4(),
        client_name="Demo Client Ltd",
        client_bin="987654321",
        reconciliation_id=uuid4(),
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        summary=AtRiskSummary(
            total_vat_claimed_bdt=Decimal("50000.00"),
            safe_itc_bdt=Decimal("40000.00"),
            at_risk_itc_bdt=Decimal("10000.00"),
            total_lines=10,
            at_risk_line_count=3,
            supplier_count_at_risk=2,
        ),
        supplier_groups=[
            AtRiskSupplierGroup(
                supplier_name="ACME Ltd",
                supplier_bin="123456789",
                lines=[_line()],
                total_vat_at_risk_bdt=Decimal("150.00"),
                line_count=1,
            ),
        ],
    )
    base.update(overrides)
    return AtRiskItcSchedulePayload(**base)


def test_payload_round_trip_via_json():
    payload = _payload()
    blob = payload.model_dump(mode="json")
    # Money fields must serialize as strings
    assert blob["summary"]["at_risk_itc_bdt"] == "10000.00"
    assert blob["supplier_groups"][0]["total_vat_at_risk_bdt"] == "150.00"
    assert blob["supplier_groups"][0]["lines"][0]["vat_amount_bdt"] == "150.00"
    # Round-trip back through validation
    AtRiskItcSchedulePayload.model_validate(blob)


def test_payload_kind_discriminator_routes_correctly():
    adapter: TypeAdapter = TypeAdapter(WorkingPaperPayload)
    blob = _payload().model_dump(mode="json")
    validated = adapter.validate_python(blob)
    assert isinstance(validated, AtRiskItcSchedulePayload)
    assert validated.kind == "at_risk_itc_schedule"


def test_payload_kind_discriminator_rejects_unknown_kind():
    adapter: TypeAdapter = TypeAdapter(WorkingPaperPayload)
    blob = _payload().model_dump(mode="json")
    blob["kind"] = "totally_made_up"
    with pytest.raises(ValidationError):
        adapter.validate_python(blob)


def test_recommended_action_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        _line(recommended_action="invent_an_action")


def test_match_status_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        _line(match_status="weird")


def test_ca_override_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        _line(ca_override="maybe")


def test_at_risk_line_round_trip():
    line = _line(
        ca_override="approved",
        recommended_action="approved_by_ca",
        match_score=Decimal("0.95"),
    )
    blob = line.model_dump(mode="json")
    assert blob["ca_override"] == "approved"
    assert blob["recommended_action"] == "approved_by_ca"
    assert blob["match_score"] == "0.95"
    AtRiskLine.model_validate(blob)


def test_enum_values_match_postgres():
    # WorkingPaperKind values must equal the Postgres enum values from 0022.
    assert WorkingPaperKind.AT_RISK_ITC_SCHEDULE.value == "at_risk_itc_schedule"
    assert WorkingPaperStatus.DRAFT.value == "draft"
    assert WorkingPaperStatus.FINALIZED.value == "finalized"
