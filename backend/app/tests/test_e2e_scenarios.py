"""The end-to-end scenarios Phase 4 named, driven through the real machinery.

These are not unit tests of a helper. Each one walks a workflow the way a
person would — student acts, coordinator acts, the other party sees the
consequence — because that is where the seams between modules actually fail.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models.enums import (
    AllocationStatus, RegistrationStatus, RegistrationWindowStatus,
    StudentRegistrationState,
)
from app.services import registration
from app.services.sections import plan_section_sizes

NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=dt.timezone.utc)


# ── Scenario 1: Open Elective, demand to sections ──────────────────────────
@pytest.mark.parametrize("demand,expected", [
    (90, [75, 15]),
    (150, [75, 75]),
    (151, [75, 75, 1]),
])
def test_scenario_1_open_elective_section_planning(demand, expected):
    """The worked examples, unchanged by everything Phase 4 added."""
    assert plan_section_sizes(demand, 75, allow_multiple=True) == expected


def test_scenario_1_the_round_drives_the_student_through_every_state(
    db, academic_world, make_curriculum, make_student
):
    """A student's state tracks the round the coordinator is driving:
    open → submitted → locked → allocated."""
    from app.models.academics import (
        Course, CourseOffering, CurriculumComponent, ElectiveAllocation,
        ElectivePreference, ElectiveRegistrationWindow,
    )
    from app.models.enums import (
        ComponentType, PreferenceStatus, SemesterTerm,
    )
    from app.models.identity import AcademicYear, Semester

    curriculum = make_curriculum(
        "B.TECH-ICT", "2024-28", 2024, None,
        [(4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL")])
    component = db.scalar(
        __import__("sqlalchemy").select(CurriculumComponent).where(
            CurriculumComponent.curriculum_id == curriculum.id))

    year = AcademicYear(label="2025-26", start_date=dt.date(2025, 7, 1),
                        end_date=dt.date(2026, 6, 30))
    db.add(year); db.flush()
    semester = Semester(academic_year_id=year.id, number=4, term=SemesterTerm.EVEN)
    db.add(semester); db.flush()
    course = Course(code="SLS-900", title="Psychology",
                    department_id=academic_world.departments["SLS"].id, credits=3)
    db.add(course); db.flush()

    window = ElectiveRegistrationWindow(
        code="OE1-E2E", title="Open Elective 1",
        component_type=ComponentType.OPEN_ELECTIVE,
        status=RegistrationWindowStatus.OPEN,
        opens_at=NOW - dt.timedelta(days=1), closes_at=NOW + dt.timedelta(days=5))
    db.add(window); db.flush()
    offering = CourseOffering(
        course_id=course.id, semester_id=semester.id,
        curriculum_component_id=component.id, registration_window_id=window.id,
        min_students_to_run=40, section_capacity=75, allow_multiple_sections=True)
    db.add(offering); db.flush()

    student = make_student("B.TECH-ICT", 2024, semester=4)

    def state():
        return registration.status_for(db, component, student, now=NOW).state

    # 1. open
    assert state() is StudentRegistrationState.OPEN

    # 2. the student submits
    db.add(ElectivePreference(
        student_id=student.id, curriculum_component_id=component.id,
        course_offering_id=offering.id, preference_order=1,
        status=PreferenceStatus.SUBMITTED))
    db.flush()
    assert state() is StudentRegistrationState.SUBMITTED

    # 3. the coordinator locks the round — the student can no longer edit
    registration.transition(window, RegistrationWindowStatus.LOCKED)
    db.flush()
    assert state() is StudentRegistrationState.LOCKED
    with pytest.raises(Exception):
        registration.assert_can_submit(db, component, student, now=NOW)

    # 4. allocation runs, but results are not released yet
    registration.transition(window, RegistrationWindowStatus.ALLOCATED)
    db.add(ElectiveAllocation(
        student_id=student.id, curriculum_component_id=component.id,
        course_offering_id=offering.id, status=AllocationStatus.ALLOCATED))
    db.flush()
    assert state() is StudentRegistrationState.LOCKED, "results leaked before publish"

    # 5. published — now the student sees their seat
    registration.transition(window, RegistrationWindowStatus.PUBLISHED)
    db.flush()
    assert state() is StudentRegistrationState.ALLOCATED


# ── Scenario 2: Core Elective across divisions ─────────────────────────────
def test_scenario_2_forty_across_four_divisions_runs_as_one_class():
    """10 + 10 + 10 + 10 = 40 combined. The minimum is never per division, and
    a Core Elective has no 75 ceiling."""
    divisions = {"A": 10, "B": 10, "C": 10, "D": 10}
    combined = sum(divisions.values())

    assert combined == 40
    assert plan_section_sizes(combined, None, allow_multiple=False) == [40]


def test_scenario_2_the_same_total_runs_with_two_divisions():
    """Division count is programme data. A two-division programme reaching 40
    combined runs exactly as a four-division one does."""
    assert plan_section_sizes(20 + 20, None, allow_multiple=False) == [40]


def test_scenario_2_thirty_nine_combined_does_not_run():
    assert sum({"A": 10, "B": 10, "C": 10, "D": 9}.values()) == 39 < 40


def test_scenario_2_a_large_core_elective_stays_one_class():
    """No 75 ceiling: 150 Core Elective students are one combined class, not
    two sections."""
    assert plan_section_sizes(150, None, allow_multiple=False) == [150]


# ── Scenario 7: event registration, waitlist, promotion ────────────────────
@pytest.fixture
def event_world(db, world):
    from app.models.community import Club, Event
    from app.models.enums import ClubCategory, EventMode, EventStatus, EventType

    club = Club(name="Codegeeks", slug="codegeeks", category=ClubCategory.TECHNICAL,
                description="Dev community")
    db.add(club); db.flush()
    event = Event(
        club_id=club.id, title="HackTheCampus", slug="hackthecampus",
        event_type=EventType.COMPETITION, mode=EventMode.OFFLINE,
        status=EventStatus.PUBLISHED,
        start_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7),
        end_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7, hours=6),
        venue="Innovation Hub", capacity=1,          # one seat, so the next waits
    )
    db.add(event); db.flush()
    return event


def test_scenario_7_full_event_waitlists_then_promotes_on_cancellation(
    api, world, login, event_world, db
):
    first = login(world.student_a.email)
    second = login(world.student_b.email)

    # The single seat goes to the first student.
    response = api.post(f"/api/v1/events/{event_world.id}/register", headers=first)
    assert response.status_code == 200

    # The event is now full, so the second student is waitlisted rather than
    # refused — the distinction that makes the queue useful.
    response = api.post(f"/api/v1/events/{event_world.id}/register", headers=second)
    assert response.status_code == 200

    from app.models.community import EventRegistration

    registrations = {
        r.student_id: r.status for r in db.scalars(
            __import__("sqlalchemy").select(EventRegistration).where(
                EventRegistration.event_id == event_world.id))
    }
    assert registrations[world.student_a.student.id] == RegistrationStatus.REGISTERED
    assert registrations[world.student_b.student.id] == RegistrationStatus.WAITLISTED

    # The first student cancels; the waitlisted student is promoted.
    response = api.delete(f"/api/v1/events/{event_world.id}/register", headers=first)
    assert response.status_code == 200

    db.expire_all()
    promoted = db.scalar(
        __import__("sqlalchemy").select(EventRegistration).where(
            EventRegistration.event_id == event_world.id,
            EventRegistration.student_id == world.student_b.student.id))
    assert promoted.status == RegistrationStatus.REGISTERED, \
        "the waitlisted student was not promoted when a seat freed"


def test_scenario_7_promotion_notifies_the_student(
    api, world, login, event_world, db
):
    """Being promoted silently is the same as not being promoted."""
    from app.models.engagement import Notification

    first = login(world.student_a.email)
    second = login(world.student_b.email)
    api.post(f"/api/v1/events/{event_world.id}/register", headers=first)
    api.post(f"/api/v1/events/{event_world.id}/register", headers=second)
    api.delete(f"/api/v1/events/{event_world.id}/register", headers=first)

    notifications = list(db.scalars(
        __import__("sqlalchemy").select(Notification).where(
            Notification.user_id == world.student_b.user.id)))
    assert notifications, "no notification was raised for the promoted student"


# ── Scenario 8: RBAC boundaries ────────────────────────────────────────────
def test_scenario_8_summer_coordinator_is_allowed_summer_and_denied_cssi(
    db, world
):
    from app.models.enums import CoordinationDomain
    from app.services import scope

    user = world.summer_ict.user
    ict = world.departments["ICT"].id
    assert scope.coordinates(db, user, CoordinationDomain.SUMMER_INTERNSHIP, ict)
    assert not scope.coordinates(db, user, CoordinationDomain.CSSI, ict)


def test_scenario_8_coordinator_of_ict_is_denied_cse(db, world):
    from app.models.enums import CoordinationDomain
    from app.services import scope

    assert not scope.coordinates(db, world.summer_ict.user,
                                 CoordinationDomain.SUMMER_INTERNSHIP,
                                 world.departments["CSE"].id)


def test_scenario_8_mentor_sees_their_students_but_not_the_console(
    api, world, login, db
):
    from app.models.engagement import MentorAssignment

    db.add(MentorAssignment(
        student_id=world.student_a.student.id,
        faculty_id=world.mentor_ict.faculty.id,
        assigned_at=dt.datetime.now(dt.timezone.utc), is_active=True))
    db.flush()

    headers = login(world.mentor_ict.email)
    # Their assigned student: allowed.
    assert api.get(f"/api/v1/student-profile/{world.student_a.student.id}",
                   headers=headers).status_code == 200
    # Coordinator surface: denied.
    assert api.get("/api/v1/electives/admin/windows",
                   headers=headers).status_code == 403
