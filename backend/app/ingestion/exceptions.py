"""Domain exceptions for ingestion."""
from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import HishabError


class IngestionError(HishabError):
    """Base for ingestion-domain errors. Subclasses override the class
    attributes ``default_code`` / ``default_status`` and call
    ``super().__init__(message, details=...)``.
    """

    default_code: str = "INGESTION_ERROR"
    default_status: int = 400

    def __init__(
        self,
        message: str = "Ingestion error",
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(self.default_code, message, self.default_status, details)


class UnsupportedFileTypeError(IngestionError):
    default_code = "INGESTION_UNSUPPORTED_TYPE"

    def __init__(self, filename: str, mime: str) -> None:
        super().__init__(
            f"File '{filename}' has unsupported type '{mime}'",
            details={"filename": filename, "mime": mime},
        )


class FileTooLargeError(IngestionError):
    default_code = "INGESTION_FILE_TOO_LARGE"

    def __init__(self, filename: str, size: int, max_size: int) -> None:
        super().__init__(
            f"File '{filename}' is {size} bytes; max {max_size}",
            details={"filename": filename, "size": size, "max_size": max_size},
        )


class JobNotFoundError(IngestionError):
    default_code = "INGESTION_JOB_NOT_FOUND"
    default_status = 404


class InvalidStateTransitionError(IngestionError):
    default_code = "INGESTION_INVALID_TRANSITION"

    def __init__(self, frm: str, to: str) -> None:
        super().__init__(
            f"Cannot transition from '{frm}' to '{to}'",
            details={"from": frm, "to": to},
        )


class ExtractionFailedError(IngestionError):
    default_code = "INGESTION_EXTRACTION_FAILED"
    default_status = 500


class HandoffError(IngestionError):
    default_code = "INGESTION_HANDOFF_FAILED"
    default_status = 500
