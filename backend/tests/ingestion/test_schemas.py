"""Tests for ingestion Pydantic schemas."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ingestion.schemas import (
    CreateJobRequest,
    ExtractedRowData,
    JobKind,
    JobStatus,
    RowStatus,
)


def test_job_kind_values():
    assert JobKind.PURCHASE_REGISTER == "purchase_register"
    assert JobKind.SUPPLIER_EXPORT == "supplier_export"


def test_create_job_request_period_ordering():
    with pytest.raises(ValidationError):
        CreateJobRequest(
            client_id=uuid4(),
            period_start=date(2026, 5, 31),
            period_end=date(2026, 5, 1),
            kind=JobKind.PURCHASE_REGISTER,
        )


def test_create_job_request_happy_path():
    req = CreateJobRequest(
        client_id=uuid4(),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        kind=JobKind.PURCHASE_REGISTER,
    )
    assert req.kind == JobKind.PURCHASE_REGISTER


def test_extracted_row_data_decimal_rounding():
    row = ExtractedRowData(
        invoice_no="INV-1",
        supplier_bin="123456789",
        supplier_name="ACME",
        invoice_date=date(2026, 5, 15),
        taxable_amount_bdt="1000.999",
        vat_amount_bdt="150.149",
    )
    assert row.taxable_amount_bdt == Decimal("1001.00")
    assert row.vat_amount_bdt == Decimal("150.15")


def test_row_status_values():
    assert RowStatus.AUTO_PASSED == "auto_passed"
    assert RowStatus.NEEDS_REVIEW == "needs_review"
