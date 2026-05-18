"""Domain exceptions for the notices module.

Mirrors app/ingestion/exceptions.py. Every exception sets a stable code
that the frontend can switch on without parsing prose.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import HishabError


class NoticeError(HishabError):
    default_code: str = "NOTICE_ERROR"
    default_status: int = 400

    def __init__(
        self,
        message: str = "Notice error",
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(self.default_code, message, self.default_status, details)


class NoticeNotFoundError(NoticeError):
    default_code = "NOTICE_NOT_FOUND"
    default_status = 404


class NoticeUnsupportedTypeError(NoticeError):
    default_code = "NOTICE_UNSUPPORTED_TYPE"
    default_status = 415

    def __init__(self, *, filename: str, mime: str) -> None:
        super().__init__(
            f"Unsupported notice file: {filename} ({mime})",
            details={"filename": filename, "mime": mime},
        )


class NoticeParseError(NoticeError):
    default_code = "NOTICE_PARSE_ERROR"
    default_status = 400


class NoticeInvalidStateError(NoticeError):
    default_code = "NOTICE_INVALID_STATE"
    default_status = 409


class DraftNotFoundError(NoticeError):
    default_code = "DRAFT_NOT_FOUND"
    default_status = 404
