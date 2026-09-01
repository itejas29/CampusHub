"""Elective registration rounds — the backend decides, not the browser.

The failure these tests exist to prevent is a student getting a write through
after the deadline: a stale tab, a clock skewed by a day, or a hand-written
request. Every one of those reaches the same server-side check, so the tests
drive that check directly rather than going through a rendered countdown.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.core.errors import BusinessRuleError
from app.models.academics import (
    Course, CourseOffering, CurriculumComponent, ElectivePreference,
    ElectiveRegistrationWindow,
)
from app.models.enums import (
    ComponentType, PreferenceStatus, RegistrationWindowStatus, SourceScope,
    StudentRegistrationState,
)
from app.services import registration

NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.timezone.utc)
YESTERDAY = NOW - dt.timedelta(days=1)
TOMORROW = NOW + dt.timedelta(days=1)
NEXT_WEEK = NOW + dt.timedelta(days=7)


@pytest.fixture
def round_world(db, academic_world, make_curriculum, make_student):
    """One Open Elective component, one course on offer, one round covering it."""
    curriculum = make_curriculum(
        "B.TECH-ICT", "2024-28", 2024, None,
        [(4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL")],
    )
    component = db.scalar(
        CurriculumComponent.__table__.select().where(
            CurriculumComponent.curriculum_id == curriculum.id).with_only_columns(
            CurriculumComponent.id)
    )
    component = db.get(CurriculumComponent, component)

    from app.models.identity import AcademicYear, Semester
    from app.models.enums import SemesterTerm

    year = AcademicYear(label="2025-26", start_date=dt.date(2025, 7, 1),
                        end_date=dt.date(2026, 6, 30), is_current=True)
    db.add(year)
    db.flush()
    semester = Semester(academic_year_id=year.id, number=4, term=SemesterTerm.EVEN)
    db.add(semester)
    db.flush()

    course = Course(code="SLS-201", title="Psychology of Everyday Life",
                    department_id=academic_world.departments["SLS"].id, credits=3)
    db.add(course)
    db.flush()

    def make_window(**kw):
        window = ElectiveRegistrationWindow(
            code=kw.pop("code", "OE1-2026"), title="Open Elective 1 — Semester IV",
            component_type=ComponentType.OPEN_ELECTIVE, **kw,
        )
        db.add(window)
        db.flush()
        offering = CourseOffering(
            course_id=course.id, semester_id=semester.id,
            curriculum_component_id=component.id, registration_window_id=window.id,
            min_students_to_run=40, section_capacity=75, allow_multiple_sections=True,
        )
        db.add(offering)
        db.flush()
        return window, offering

    student = make_student("B.TECH-ICT", 2024, semester=4, division="A")
    return type("World", (), {
        "db": db, "component": component, "student": student,
        "make_window": staticmethod(make_window), "course": course,
        "semester": semester, "programs": academic_world.programs,
    })


def state(world, **kw):
    return registration.status_for(world.db, world.component, world.student,
                                   now=kw.pop("now", NOW))


# ── the deadline is enforced on the server ─────────────────────────────────
def test_a_draft_round_is_not_open(round_world):
    round_world.make_window(status=RegistrationWindowStatus.DRAFT,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK)
    result = state(round_world)
    assert result.state is StudentRegistrationState.NOT_OPEN
    assert not result.can_submit


def test_an_open_round_inside_its_window_accepts_writes(round_world):
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK)
    result = state(round_world)
    assert result.state is StudentRegistrationState.OPEN
    assert result.can_submit


def test_a_round_before_its_opening_time_is_refused(round_world):
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=TOMORROW, closes_at=NEXT_WEEK)
    result = state(round_world)
    assert result.state is StudentRegistrationState.NOT_OPEN
    assert not result.can_submit
    assert "opens on" in result.reason


def test_the_deadline_wins_even_if_the_coordinator_has_not_locked(round_world):
    """The exact case a browser countdown cannot be trusted with: the round is
    still flagged OPEN, but the clock has passed the closing time."""
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=YESTERDAY - dt.timedelta(days=5),
                            closes_at=YESTERDAY)
    result = state(round_world)
    assert result.state is StudentRegistrationState.LOCKED
    assert not result.can_submit
    assert "deadline passed" in result.reason

    with pytest.raises(BusinessRuleError, match="deadline"):
        registration.assert_can_submit(round_world.db, round_world.component,
                                       round_world.student, now=NOW)


def test_a_locked_round_refuses_writes(round_world):
    round_world.make_window(status=RegistrationWindowStatus.LOCKED,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK)
    with pytest.raises(BusinessRuleError):
        registration.assert_can_submit(round_world.db, round_world.component,
                                       round_world.student, now=NOW)


def test_submitting_preferences_moves_the_state_to_submitted(round_world):
    _window, offering = round_world.make_window(
        status=RegistrationWindowStatus.OPEN, opens_at=YESTERDAY, closes_at=NEXT_WEEK)
    assert state(round_world).state is StudentRegistrationState.OPEN

    round_world.db.add(ElectivePreference(
        student_id=round_world.student.id,
        curriculum_component_id=round_world.component.id,
        course_offering_id=offering.id, preference_order=1,
        status=PreferenceStatus.SUBMITTED))
    round_world.db.flush()

    result = state(round_world)
    assert result.state is StudentRegistrationState.SUBMITTED
    assert result.preference_count == 1
    assert result.can_submit          # still editable before the deadline


def test_results_are_hidden_until_the_round_is_published(round_world):
    from app.models.academics import ElectiveAllocation
    from app.models.enums import AllocationStatus

    window, offering = round_world.make_window(
        status=RegistrationWindowStatus.ALLOCATED, opens_at=YESTERDAY,
        closes_at=YESTERDAY)
    round_world.db.add(ElectiveAllocation(
        student_id=round_world.student.id,
        curriculum_component_id=round_world.component.id,
        course_offering_id=offering.id, status=AllocationStatus.ALLOCATED))
    round_world.db.flush()

    # Allocation has run, but the coordinator has not released it.
    assert state(round_world).state is StudentRegistrationState.LOCKED

    window.status = RegistrationWindowStatus.PUBLISHED
    round_world.db.flush()
    assert state(round_world).state is StudentRegistrationState.ALLOCATED


def test_a_published_round_with_no_seat_reads_as_closed(round_world):
    round_world.make_window(status=RegistrationWindowStatus.PUBLISHED,
                            opens_at=YESTERDAY, closes_at=YESTERDAY)
    result = state(round_world)
    assert result.state is StudentRegistrationState.CLOSED
    assert not result.can_submit


# ── eligibility narrows a round without any hard-coding ────────────────────
def test_a_round_can_be_narrowed_to_particular_semesters(round_world):
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK,
                            eligible_semesters=[6])
    # The student is in Semester IV, so this round does not cover them at all.
    assert state(round_world).window is None


def test_a_round_can_be_narrowed_to_particular_programmes(round_world):
    other = round_world.programs["B.TECH-MECH"].id
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK,
                            eligible_program_ids=[other])
    assert state(round_world).window is None


def test_a_round_can_be_narrowed_to_particular_divisions(round_world):
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK,
                            eligible_divisions=["C", "D"])
    assert state(round_world).window is None


def test_an_unnarrowed_round_covers_everyone_it_reaches(round_world):
    round_world.make_window(status=RegistrationWindowStatus.OPEN,
                            opens_at=YESTERDAY, closes_at=NEXT_WEEK,
                            eligible_semesters=[4],
                            eligible_program_ids=[round_world.programs["B.TECH-ICT"].id],
                            eligible_divisions=["A", "B"])
    assert state(round_world).can_submit


# ── the round's own lifecycle ──────────────────────────────────────────────
@pytest.mark.parametrize("start,target", [
    (RegistrationWindowStatus.DRAFT, RegistrationWindowStatus.OPEN),
    (RegistrationWindowStatus.OPEN, RegistrationWindowStatus.LOCKED),
    (RegistrationWindowStatus.LOCKED, RegistrationWindowStatus.ALLOCATED),
    (RegistrationWindowStatus.ALLOCATED, RegistrationWindowStatus.PUBLISHED),
    (RegistrationWindowStatus.PUBLISHED, RegistrationWindowStatus.CLOSED),
])
def test_the_lifecycle_moves_forward(start, target):
    window = ElectiveRegistrationWindow(
        code="X", title="X", component_type=ComponentType.OPEN_ELECTIVE, status=start)
    registration.transition(window, target)
    assert window.status is target


@pytest.mark.parametrize("start,target", [
    # Publishing without ever allocating would show students an empty result.
    (RegistrationWindowStatus.OPEN, RegistrationWindowStatus.PUBLISHED),
    (RegistrationWindowStatus.DRAFT, RegistrationWindowStatus.ALLOCATED),
    # A closed round is finished.
    (RegistrationWindowStatus.CLOSED, RegistrationWindowStatus.OPEN),
])
def test_the_lifecycle_refuses_skips_and_reversals(start, target):
    window = ElectiveRegistrationWindow(
        code="X", title="X", component_type=ComponentType.OPEN_ELECTIVE, status=start)
    with pytest.raises(BusinessRuleError, match="cannot become"):
        registration.transition(window, target)


def test_locking_and_publishing_are_timestamped():
    window = ElectiveRegistrationWindow(
        code="X", title="X", component_type=ComponentType.OPEN_ELECTIVE,
        status=RegistrationWindowStatus.OPEN)
    registration.transition(window, RegistrationWindowStatus.LOCKED)
    assert window.locked_at is not None
    registration.transition(window, RegistrationWindowStatus.ALLOCATED)
    assert window.allocated_at is not None
    registration.transition(window, RegistrationWindowStatus.PUBLISHED)
    assert window.published_at is not None


def test_a_component_with_no_round_falls_back_to_offering_dates(round_world):
    """Offerings created before rounds existed keep working unchanged."""
    result = state(round_world)
    assert result.window is None
    assert result.state is StudentRegistrationState.NOT_OPEN


def test_a_future_semesters_component_is_never_open_however_the_dates_read(
    round_world
):
    """The regression this catches: an offering left open by a coordinator told
    a Semester IV student that their Semester VII elective was available.

    The curriculum decides when a component unlocks; the dates only decide when
    registration runs *within* that.
    """
    from app.models.academics import CourseOffering
    from app.models.enums import OfferingStatus

    round_world.component.semester_number = 7      # student is in Semester IV
    offering = CourseOffering(
        course_id=round_world.course.id, semester_id=round_world.semester.id,
        curriculum_component_id=round_world.component.id,
        status=OfferingStatus.OPEN,                # wide open, no round attached
        registration_opens_at=YESTERDAY, registration_closes_at=NEXT_WEEK,
    )
    round_world.db.add(offering)
    round_world.db.flush()

    result = state(round_world)
    assert result.state is StudentRegistrationState.NOT_OPEN
    assert not result.can_submit
    assert "opens in semester 7" in result.reason


def test_counting_covered_students_does_not_load_them(round_world):
    """The admin list renders a row per round; hydrating every covered student
    to call len() on them turned a summary table into hundreds of objects."""
    window, _offering = round_world.make_window(
        status=RegistrationWindowStatus.OPEN, opens_at=YESTERDAY,
        closes_at=NEXT_WEEK,
        eligible_program_ids=[round_world.programs["B.TECH-ICT"].id],
        eligible_semesters=[4])
    assert registration.count_students_in_window(round_world.db, window) == 1
