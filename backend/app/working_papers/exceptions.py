"""Domain exceptions for working papers. Mirrors notices/exceptions.py."""
from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import HishabError


class WorkingPaperError(HishabError):
    default_code: str = "WORKING_PAPER_ERROR"
    default_status: int = 400

    def __init__(
        self,
        message: str = "Working paper error",
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(self.default_code, message, self.default_status, details)


class WorkingPaperNotFoundError(WorkingPaperError):
    default_code = "WORKING_PAPER_NOT_FOUND"
    default_status = 404


class RecipeNotFoundError(WorkingPaperError):
    default_code = "RECIPE_NOT_FOUND"
    default_status = 400


class WorkingPaperInvalidStateError(WorkingPaperError):
    default_code = "WORKING_PAPER_INVALID_STATE"
    default_status = 409


class RecipeComposeError(WorkingPaperError):
    default_code = "RECIPE_COMPOSE_ERROR"
    default_status = 400


class WorkingPaperReviewError(WorkingPaperError):
    """Finalizing requires a reviewer different from the preparer (segregation
    of duties). Raised when the same user tries to compose and sign off."""
    default_code = "WORKING_PAPER_REVIEW_REQUIRED"
    default_status = 409
