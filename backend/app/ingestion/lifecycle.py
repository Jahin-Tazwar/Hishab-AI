"""Job state machine — pure logic.

The DB-side transition (UPDATE ingestion_jobs SET status = ...) is performed
by `persistence.update_job_status`. This module only validates that the
transition is legal.
"""
from __future__ import annotations

from app.ingestion.exceptions import InvalidStateTransitionError
from app.ingestion.schemas import JobStatus

_ALLOWED: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING:           {JobStatus.EXTRACTING, JobStatus.FAILED},
    JobStatus.EXTRACTING:        {JobStatus.READY_FOR_REVIEW, JobStatus.FAILED},
    JobStatus.READY_FOR_REVIEW:  {JobStatus.CONFIRMED, JobStatus.FAILED},
    JobStatus.CONFIRMED:         {JobStatus.RECONCILING, JobStatus.FAILED},
    JobStatus.RECONCILING:       {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CONFIRMED},
    JobStatus.COMPLETED:         set(),
    JobStatus.FAILED:            set(),
}


def assert_can_transition(frm: JobStatus, to: JobStatus) -> None:
    if to not in _ALLOWED.get(frm, set()):
        raise InvalidStateTransitionError(frm.value, to.value)


def next_status_for_extraction(any_needs_review: bool) -> JobStatus:
    """After all files are extracted, the job moves to ready_for_review.

    Even when nothing needs review, the user is still expected to open the
    job and click Finalize (spec §7).
    """
    return JobStatus.READY_FOR_REVIEW
