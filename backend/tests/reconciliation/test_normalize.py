"""Tests for invoice number normalization."""
import pytest

from app.reconciliation.normalize import normalize_invoice_no


@pytest.mark.parametrize("raw,expected", [
    ("INV-0023/2024", "inv23/2024"),
    ("inv 23 / 2024", "inv23/2024"),
    ("  INV-23/2024  ", "inv23/2024"),
    ("INV-23-2024", "inv232024"),
    ("MUSHAK-9.1/00045", "mushak9.1/45"),
    ("00045", "45"),
    ("ABC", "abc"),
    ("", ""),
])
def test_normalize_invoice_no(raw: str, expected: str):
    assert normalize_invoice_no(raw) == expected


def test_normalize_invoice_no_preserves_dot_separators():
    """Decimal points inside identifiers must NOT be stripped."""
    assert normalize_invoice_no("9.1") == "9.1"


def test_normalize_invoice_no_handles_none_via_caller():
    """Function does not handle None — caller's responsibility."""
    with pytest.raises(AttributeError):
        normalize_invoice_no(None)  # type: ignore[arg-type]
