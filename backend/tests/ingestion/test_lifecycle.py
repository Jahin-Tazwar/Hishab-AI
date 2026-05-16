"""Pure-logic tests for the state machine — no DB needed."""
import pytest

from app.ingestion.exceptions import InvalidStateTransitionError
from app.ingestion.lifecycle import assert_can_transition, next_status_for_extraction
from app.ingestion.schemas import JobStatus


def test_pending_to_extracting_ok():
    assert_can_transition(JobStatus.PENDING, JobStatus.EXTRACTING)


def test_extracting_to_ready_for_review_ok():
    assert_can_transition(JobStatus.EXTRACTING, JobStatus.READY_FOR_REVIEW)


def test_completed_to_anything_blocked():
    with pytest.raises(InvalidStateTransitionError):
        assert_can_transition(JobStatus.COMPLETED, JobStatus.PENDING)


def test_failed_is_terminal():
    with pytest.raises(InvalidStateTransitionError):
        assert_can_transition(JobStatus.FAILED, JobStatus.RECONCILING)


def test_extraction_done_with_review_needed_goes_ready_for_review():
    assert next_status_for_extraction(any_needs_review=True) == JobStatus.READY_FOR_REVIEW


def test_extraction_done_no_review_needed_still_goes_ready_for_review():
    # User must always click finalize, even when nothing needs review.
    # (Spec §7: review screen visit + finalize click are explicit.)
    assert next_status_for_extraction(any_needs_review=False) == JobStatus.READY_FOR_REVIEW


def test_confirmed_to_completed_allowed_for_linked_pr_completion():
    # When an SF finalize succeeds, the linked PR job is moved from
    # confirmed to completed without ever passing through reconciling.
    assert_can_transition(JobStatus.CONFIRMED, JobStatus.COMPLETED)
