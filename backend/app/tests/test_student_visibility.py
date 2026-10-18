"""What a student is allowed to *see*, as distinct from what they may submit.

``test_program_phase`` already pins the phase each semester produces. These
tests pin the consequence: a programme in a phase the student has not reached
must not appear in their listing at all, and must not be fetchable by id.

The distinction matters because hiding a card in the UI while the API still
serves the stages, criteria, dates and coordinator is not visibility control.
A student who opens the network tab, or any script holding their token, sees
everything the endpoint returned.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.services.internships import student_can_see_program
from app.services.minors import application_window_open, student_can_see_minor

NOW = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)


def cssi():
    """Floated in Semester II, carried out in III, closed from IV."""
    return SimpleNamespace(
        name="Community and Social Service Internship",
        target_semester=3, announce_from_semester=2, visible_to_semester=3,
    )


def summer():
    """Announced and opened in Semester VI, with no closing semester."""
    return SimpleNamespace(
        name="Summer Internship",
        target_semester=6, announce_from_semester=6, visible_to_semester=None,
    )


# ── internships: a future programme is not the student's business yet ─────
@pytest.mark.parametrize("semester,visible", [
    (1, False),   # hidden — CSSI has not been floated
    (2, True),    # announced — find an NGO over the break
    (3, True),    # active
    (4, False),   # concluded, and this student never took it
    (7, False),
])
def test_cssi_is_listed_only_while_it_concerns_the_student(semester, visible):
    assert student_can_see_program(
        cssi(), semester, has_enrollment=False) is visible


@pytest.mark.parametrize("semester", [1, 2, 3, 4, 5])
def test_summer_internship_is_not_shown_before_semester_six(semester):
    assert student_can_see_program(
        summer(), semester, has_enrollment=False) is False


@pytest.mark.parametrize("semester", [6, 7, 8])
def test_summer_internship_appears_from_semester_six(semester):
    assert student_can_see_program(
        summer(), semester, has_enrollment=False) is True


@pytest.mark.parametrize("semester", [1, 2, 3, 4, 5, 6, 7, 8])
def test_a_students_own_record_is_never_hidden_from_them(semester):
    """Enrolment outlives the window.

    A Semester IV student's CSSI record has to stay readable — it is their
    academic history. The editing lock is a separate concern, guarded by
    assert_submissions_open().
    """
    assert student_can_see_program(cssi(), semester, has_enrollment=True) is True
    assert student_can_see_program(summer(), semester, has_enrollment=True) is True


def test_a_student_with_no_semester_recorded_sees_nothing_speculative():
    assert student_can_see_program(cssi(), None, has_enrollment=False) is False


# ── minors: the registration round decides visibility ─────────────────────
def minor(opens=None, closes=None, from_semester=3, rules=None):
    return SimpleNamespace(
        eligible_from_semester=from_semester, rules=rules or {},
        application_opens_at=opens, application_closes_at=closes,
    )


def student(semester):
    return SimpleNamespace(current_semester=semester)


def test_window_with_no_dates_configured_counts_as_open():
    """Neither bound set means "no limit", which is how the seeded rounds run."""
    assert application_window_open(minor(), NOW) is True


def test_window_is_shut_before_it_opens_and_after_it_closes():
    m = minor(opens=NOW + dt.timedelta(days=1), closes=NOW + dt.timedelta(days=10))
    assert application_window_open(m, NOW) is False
    m = minor(opens=NOW - dt.timedelta(days=10), closes=NOW - dt.timedelta(days=1))
    assert application_window_open(m, NOW) is False


@pytest.mark.parametrize("semester", [1, 2])
def test_minor_is_not_shown_before_the_semester_it_opens_from(semester):
    m = minor(opens=NOW - dt.timedelta(days=5), closes=NOW + dt.timedelta(days=5))
    assert student_can_see_minor(
        m, student(semester), has_application=False, now=NOW) is False


def test_eligible_student_sees_the_minor_while_the_round_runs():
    m = minor(opens=NOW - dt.timedelta(days=5), closes=NOW + dt.timedelta(days=5))
    assert student_can_see_minor(
        m, student(3), has_application=False, now=NOW) is True


def test_minor_disappears_for_a_student_who_did_not_register():
    m = minor(opens=NOW - dt.timedelta(days=30), closes=NOW - dt.timedelta(days=1))
    assert student_can_see_minor(
        m, student(3), has_application=False, now=NOW) is False


@pytest.mark.parametrize("semester", [4, 6])
def test_a_later_student_who_never_applied_does_not_see_an_open_round(semester):
    """Applications are made in Semester III; the minor is not offered later."""
    m = minor(opens=NOW - dt.timedelta(days=5), closes=NOW + dt.timedelta(days=5))
    assert student_can_see_minor(
        m, student(semester), has_application=False, now=NOW) is False


def test_a_minor_can_take_applications_in_other_semesters_when_configured():
    m = minor(opens=NOW - dt.timedelta(days=5), closes=NOW + dt.timedelta(days=5),
              rules={"application_semesters": [3, 5]})
    assert student_can_see_minor(m, student(5), has_application=False, now=NOW) is True


def test_minor_stays_visible_to_the_student_who_registered():
    """A seat that vanishes when the round shuts would be worse than useless."""
    m = minor(opens=NOW - dt.timedelta(days=30), closes=NOW - dt.timedelta(days=1))
    assert student_can_see_minor(
        m, student(6), has_application=True, now=NOW) is True


def test_cpi_and_backlogs_do_not_decide_visibility():
    """Eligibility is shown, not enforced by hiding.

    A student short on CPI still needs to see the programme and the reason they
    do not qualify; hiding it would leave them unable to find out why. The CPI
    and backlog gates live in check_minor_eligibility(), which blocks the
    application itself.
    """
    m = minor(opens=NOW - dt.timedelta(days=5), closes=NOW + dt.timedelta(days=5))
    # The rule takes no CPI or backlog input at all — this is the guarantee.
    assert student_can_see_minor(
        m, student(3), has_application=False, now=NOW) is True
