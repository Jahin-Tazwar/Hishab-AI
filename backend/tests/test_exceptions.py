"""Tests for HishabError subclasses."""
from app.core.exceptions import (
    InvalidXlsxFormatError,
    ReconciliationAlreadyExistsError,
    StorageDownloadFailedError,
    DocumentTenantMismatchError,
)


def test_invalid_xlsx_lists_missing_columns():
    err = InvalidXlsxFormatError(
        file_label="purchase register",
        missing_columns=["Invoice No", "Supplier BIN"],
    )
    assert err.code == "INVALID_XLSX_FORMAT"
    assert err.status_code == 400
    assert "purchase register" in err.message
    assert "Invoice No" in err.message
    assert "Supplier BIN" in err.message
    assert err.details == {
        "file_label": "purchase register",
        "missing_columns": ["Invoice No", "Supplier BIN"],
    }


def test_reconciliation_already_exists_carries_id():
    err = ReconciliationAlreadyExistsError(reconciliation_id="abc-123")
    assert err.code == "RECONCILIATION_ALREADY_EXISTS"
    assert err.status_code == 409
    assert err.details == {"reconciliation_id": "abc-123"}


def test_storage_download_failed():
    err = StorageDownloadFailedError(path="t/c/r/file.xlsx", reason="404 not found")
    assert err.code == "STORAGE_DOWNLOAD_FAILED"
    assert err.status_code == 502
    assert "t/c/r/file.xlsx" in err.message


def test_document_tenant_mismatch():
    err = DocumentTenantMismatchError(document_id="doc-1")
    assert err.code == "DOCUMENT_TENANT_MISMATCH"
    assert err.status_code == 403
