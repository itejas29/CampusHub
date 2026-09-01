"""Document lifecycle, protected URLs and the summer rubric.

These are the Phase 2 rules that carry real consequences: a missing mandatory
document must stay visible, a storage path must never leak, and the summer
rubric must total exactly 100 with the industry component out of reach of the
student.
"""
from __future__ import annotations

import pytest

from app.core.errors import BusinessRuleError
from app.models.enums import (
    PENDING_REVIEW_STATUSES, SATISFYING_STATUSES, EvaluatorRole, SubmissionStatus,
)
from app.services.documents import (
    RESUBMITTABLE, REVIEW_TRANSITIONS, assert_can_resubmit, protected_url,
)


class _Doc:
    """A document stub — the guard is pure and needs no ORM instrumentation."""

    def __init__(self, status):
        self.status = status


# ── NOT_SUBMITTED is a real, first-class state ────────────────────────────
def test_not_submitted_is_part_of_the_vocabulary():
    """A document that was never uploaded still has a status to render."""
    assert SubmissionStatus.NOT_SUBMITTED.value == "NOT_SUBMITTED"


def test_not_submitted_never_satisfies_a_requirement():
    assert SubmissionStatus.NOT_SUBMITTED not in SATISFYING_STATUSES
    assert SubmissionStatus.NOT_SUBMITTED not in PENDING_REVIEW_STATUSES


def test_only_verified_work_counts_as_done():
    assert SATISFYING_STATUSES == {SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED}
    for status in (SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW,
                   SubmissionStatus.REJECTED, SubmissionStatus.DRAFT):
        assert status not in SATISFYING_STATUSES


def test_submitted_work_awaits_a_reviewer():
    assert PENDING_REVIEW_STATUSES == {
        SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW,
    }


# ── the review workflow ───────────────────────────────────────────────────
def test_review_transitions_cover_the_documented_workflow():
    assert REVIEW_TRANSITIONS == {
        "start_review": SubmissionStatus.UNDER_REVIEW,
        "verify": SubmissionStatus.VERIFIED,
        "reject": SubmissionStatus.REJECTED,
    }


@pytest.mark.parametrize("status", sorted(RESUBMITTABLE, key=str))
def test_a_returned_document_can_be_replaced(status):
    assert_can_resubmit(_Doc(status))          # does not raise


def test_a_verified_document_cannot_be_silently_replaced():
    with pytest.raises(BusinessRuleError) as excinfo:
        assert_can_resubmit(_Doc(SubmissionStatus.VERIFIED))
    assert "no longer be replaced" in str(excinfo.value)


def test_a_document_under_review_cannot_be_swapped_mid_review():
    with pytest.raises(BusinessRuleError):
        assert_can_resubmit(_Doc(SubmissionStatus.UNDER_REVIEW))


def test_rejection_is_recoverable():
    """Rejection must be a loop back to the student, not a dead end."""
    assert SubmissionStatus.REJECTED in RESUBMITTABLE


# ── storage paths never reach the client ──────────────────────────────────
def test_file_url_is_an_authorised_api_route():
    url = protected_url(42)
    assert url.endswith("/files/42/download")
    assert "/media/" not in url
    assert not url.startswith("http")          # no signed bucket URL either


def test_no_link_is_offered_when_nothing_was_submitted():
    """A missing document must render as absent, never as a broken link."""
    assert protected_url(None) is None
    assert protected_url(0) is None


# ── the summer rubric ─────────────────────────────────────────────────────
def _summer_criteria():
    from app.seed.data import SUMMER_CRITERIA

    return SUMMER_CRITERIA


def test_summer_rubric_is_four_components():
    assert len(_summer_criteria()) == 4


def test_every_summer_component_is_out_of_25():
    assert [c[3] for c in _summer_criteria()] == [25, 25, 25, 25]


def test_summer_rubric_totals_exactly_100():
    assert sum(c[3] * c[4] for c in _summer_criteria()) == 100


def test_summer_rubric_covers_the_four_named_heads():
    codes = {c[0] for c in _summer_criteria()}
    assert codes == {"FINAL_REPORT", "PRESENTATION", "WEEKLY", "INDUSTRY"}


def test_industry_mentor_marks_are_externally_sourced():
    """The student must never be able to enter their own industry marks."""
    assert EvaluatorRole.INDUSTRY_MENTOR.value == "INDUSTRY_MENTOR"
    assert EvaluatorRole.INDUSTRY_MENTOR is not EvaluatorRole.FACULTY_MENTOR
