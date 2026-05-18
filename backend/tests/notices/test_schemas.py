"""Pydantic schema invariants."""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.notices.schemas import (
    CitationChunk, DraftAppendixRow, DraftParagraph, DraftReply,
    LinkedRecon, NeedsIngestion, NeedsManualLink,
    NoticeStatus, NoticeType, ParsedNotice, ReconSummary,
)


def test_parsed_notice_requires_classification_confidence():
    with pytest.raises(ValidationError):
        ParsedNotice(notice_type=NoticeType.INPUT_VAT_MISMATCH)


def test_parsed_notice_normalizes_bin_to_digits():
    n = ParsedNotice(
        notice_type=NoticeType.INPUT_VAT_MISMATCH,
        taxpayer_bin="001-234-567",
        classification_confidence=0.9,
    )
    assert n.taxpayer_bin == "001234567"


def test_parsed_notice_period_end_must_be_ge_start():
    with pytest.raises(ValidationError):
        ParsedNotice(
            notice_type=NoticeType.INPUT_VAT_MISMATCH,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 4, 1),
            classification_confidence=0.9,
        )


def test_draft_reply_serializes_decimals_as_strings():
    r = DraftReply(
        body_paragraphs=[DraftParagraph(text="hello [CIT-1]", citation_tags=["CIT-1"])],
        computation_table_rows=[
            DraftAppendixRow(label="Claimed", value_bdt=Decimal("50000.00"), note=None),
        ],
        cited_refs=["CIT-1"],
    )
    j = r.model_dump(mode="json")
    assert j["computation_table_rows"][0]["value_bdt"] == "50000.00"


def test_linker_result_discriminators_serialize_with_kind():
    lr = LinkedRecon(reconciliation_id="00000000-0000-0000-0000-000000000001",
                    client_id="00000000-0000-0000-0000-000000000002")
    assert lr.model_dump()["kind"] == "linked_recon"

    ni = NeedsIngestion(client_id="00000000-0000-0000-0000-000000000002",
                        period_start=date(2026, 4, 1),
                        period_end=date(2026, 4, 30))
    assert ni.model_dump()["kind"] == "needs_ingestion"

    nml = NeedsManualLink(candidate_clients=[])
    assert nml.model_dump()["kind"] == "needs_manual_link"


def test_notice_status_enum_values_match_db():
    expected = {"pending","parsing","parsed","awaiting_data","ready_to_draft",
                "drafting","drafted","finalized","failed"}
    assert {s.value for s in NoticeStatus} == expected


def test_recon_summary_money_fields_serialize_as_strings():
    s = ReconSummary(
        reconciliation_id="00000000-0000-0000-0000-000000000001",
        safe_itc_bdt=Decimal("40000.00"),
        at_risk_itc_bdt=Decimal("10000.00"),
        total_vat_claimed_bdt=Decimal("50000.00"),
        matched_exact=8, matched_fuzzy=3, partial_match=2, no_match=2,
        disputed_rows=[],
    )
    j = s.model_dump(mode="json")
    assert j["safe_itc_bdt"] == "40000.00"
