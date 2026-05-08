"""
HishabAI Backend — Custom Exception Classes

Standard error codes used across all API responses.
"""

from typing import Any, Optional


class HishabError(Exception):
    """Base exception for all HishabAI errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


# ── Auth Errors ───────────────────────────────────────────────────────────

class UnauthorizedError(HishabError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("UNAUTHORIZED", message, 401)


class ForbiddenError(HishabError):
    def __init__(self, message: str = "Access denied") -> None:
        super().__init__("FORBIDDEN", message, 403)


# ── Resource Errors ───────────────────────────────────────────────────────

class TenantNotFoundError(HishabError):
    def __init__(self) -> None:
        super().__init__("TENANT_NOT_FOUND", "Tenant not found", 404)


class ClientNotFoundError(HishabError):
    def __init__(self, client_id: str = "") -> None:
        msg = f"Client {client_id} not found" if client_id else "Client not found"
        super().__init__("CLIENT_NOT_FOUND", msg, 404)


class DocumentNotFoundError(HishabError):
    def __init__(self, doc_id: str = "") -> None:
        msg = f"Document {doc_id} not found" if doc_id else "Document not found"
        super().__init__("DOCUMENT_NOT_FOUND", msg, 404)


class NoticeNotFoundError(HishabError):
    def __init__(self, notice_id: str = "") -> None:
        msg = f"Notice {notice_id} not found" if notice_id else "Notice not found"
        super().__init__("NOTICE_NOT_FOUND", msg, 404)


# ── Validation Errors ────────────────────────────────────────────────────

class InvalidBINError(HishabError):
    def __init__(self, value: str = "") -> None:
        super().__init__(
            "INVALID_BIN_FORMAT",
            f"BIN must be exactly 9 digits. Got: '{value}'",
        )


class InvalidTINError(HishabError):
    def __init__(self, value: str = "") -> None:
        super().__init__(
            "INVALID_TIN_FORMAT",
            f"TIN must be exactly 12 digits. Got: '{value}'",
        )


# ── Processing Errors ────────────────────────────────────────────────────

class DocumentProcessingError(HishabError):
    def __init__(self) -> None:
        super().__init__(
            "DOCUMENT_STILL_PROCESSING",
            "Document is still being processed. Try again later.",
            409,
        )


class OCRFailedError(HishabError):
    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "OCR_EXTRACTION_FAILED",
            f"OCR extraction failed: {reason}" if reason else "OCR extraction failed",
            500,
        )


class ReconciliationRunningError(HishabError):
    def __init__(self) -> None:
        super().__init__(
            "RECONCILIATION_ALREADY_RUNNING",
            "A reconciliation is already running for this client and period.",
            409,
        )


class AIDraftFailedError(HishabError):
    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "AI_DRAFT_GENERATION_FAILED",
            f"AI draft generation failed: {reason}" if reason else "AI draft generation failed",
            500,
        )


class PlanLimitExceededError(HishabError):
    def __init__(self, limit_type: str = "") -> None:
        super().__init__(
            "PLAN_LIMIT_EXCEEDED",
            f"Plan limit exceeded: {limit_type}" if limit_type else "Plan limit exceeded",
            429,
        )


# ── Reconciliation Errors (Phase C) ──────────────────────────────────────


class InvalidXlsxFormatError(HishabError):
    def __init__(self, file_label: str, missing_columns: list[str]) -> None:
        cols = ", ".join(missing_columns)
        super().__init__(
            "INVALID_XLSX_FORMAT",
            f"{file_label} is missing required columns: {cols}",
            status_code=400,
            details={"file_label": file_label, "missing_columns": missing_columns},
        )


class ReconciliationAlreadyExistsError(HishabError):
    def __init__(self, reconciliation_id: str) -> None:
        super().__init__(
            "RECONCILIATION_ALREADY_EXISTS",
            "A reconciliation already exists for this client and period.",
            status_code=409,
            details={"reconciliation_id": reconciliation_id},
        )


class StorageDownloadFailedError(HishabError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            "STORAGE_DOWNLOAD_FAILED",
            f"Could not download {path}: {reason}",
            status_code=502,
            details={"path": path, "reason": reason},
        )


class DocumentTenantMismatchError(HishabError):
    def __init__(self, document_id: str) -> None:
        super().__init__(
            "DOCUMENT_TENANT_MISMATCH",
            "Document does not belong to the authenticated tenant.",
            status_code=403,
            details={"document_id": document_id},
        )


class ReconciliationNotFoundError(HishabError):
    def __init__(self, reconciliation_id: str = "") -> None:
        msg = (
            f"Reconciliation {reconciliation_id} not found"
            if reconciliation_id else "Reconciliation not found"
        )
        super().__init__("RECONCILIATION_NOT_FOUND", msg, status_code=404)
