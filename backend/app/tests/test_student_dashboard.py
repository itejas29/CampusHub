"""The student dashboard, end to end, one semester at a time.

``test_semester_requirements`` pins the rule for a single slot. These drive the
real endpoint, because the failure students actually saw was at this level: a
dashboard that answered every student with the same semester. Here one student
is moved through the semesters of one curriculum and the response has to follow.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.academics import (
    Course, CourseOffering, CurriculumComponent, ElectiveAllocation, ElectivePreference,
    MoocRegistration,
)
from app.models.enums import AllocationStatus, MoocStatus, PreferenceStatus, SemesterTerm
from app.models.identity import AcademicYear, Semester

#: The shape of the ICT 2024-28 handbook, cut down to what the rule depends on:
#: no elective slot until Semester IV, and the NPTEL slot beside PE1 in V.
CURRICULUM = [
    (1, "S1-01", "Mathematics – 1", "CORE", "ANY"),
    (1, "S1-02", "Physics", "CORE", "ANY"),
    (2, "S2-01", "Mathematics – 2", "CORE", "ANY"),
    (4, "S4-01", "Database Management Systems", "CORE", "ANY"),
    (4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL"),
    (5, "OE2-MOOC", "Open Elective 2 (NPTEL/SWAYAM/MOOC)", "MOOC", "EXTERNAL_PLATFORM"),
    (5, "PE1", "Program Elective 1", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT"),
]


@pytest.fixture
def campus(db, world, make_curriculum):
    """`world.student_a` on a published ICT curriculum, plus one course on offer."""
    curriculum = make_curriculum("B.TECH-ICT", "2024-28", 2024, None, CURRICULUM)
    components = {
        c.code: c for c in db.scalars(select(CurriculumComponent).where(
            CurriculumComponent.curriculum_id == curriculum.id))
    }
    year = AcademicYear(label="2025-26", start_date=dt.date(2025, 7, 1),
                        end_date=dt.date(2026, 6, 30), is_current=True)
    db.add(year)
    db.flush()
    semester = Semester(academic_year_id=year.id, number=4, term=SemesterTerm.EVEN)
    course = Course(code="SLS-201", title="Psychology of Everyday Life",
                    department_id=world.departments["SLS"].id, credits=3)
    db.add_all([semester, course])
    db.flush()

    def offering(code):
        row = CourseOffering(course_id=course.id, semester_id=semester.id,
                             curriculum_component_id=components[code].id)
        db.add(row)
        db.flush()
        return row

    return type("Campus", (), {"components": components, "offering": staticmethod(offering)})


@pytest.fixture
def dashboard(api, world, login, db, campus):
    """The dashboard as `student_a` sees it once they are in `semester`."""
    def fetch(semester):
        world.student_a.student.current_semester = semester
        db.flush()
        response = api.get("/api/v1/dashboard/student",
                           headers=login(world.student_a.email))
        assert response.status_code == 200, response.text
        return response.json()

    return fetch


def stat(body, key):
    return next(s for s in body["stats"] if s["key"] == key)


def statuses(body):
    return {c["code"]: c["status"] for c in body["curriculum_semester"]["components"]}


# ── a semester with no elective slot ───────────────────────────────────────
@pytest.mark.parametrize("semester,codes", [(1, {"S1-01", "S1-02"}), (2, {"S2-01"})])
def test_a_first_year_sees_only_their_own_core_courses(dashboard, semester, codes):
    body = dashboard(semester)
    assert statuses(body) == {code: "Core" for code in codes}
    assert body["curriculum_semester"]["semester_number"] == semester


@pytest.mark.parametrize("semester", [1, 2])
def test_a_first_year_has_no_elective_work_and_nowhere_to_be_sent(dashboard, semester):
    body = dashboard(semester)
    pending = stat(body, "pending_electives")
    assert pending["value"] == 0
    # No slot exists, so a link to an elective screen would be a guess.
    assert pending["link"] is None
    assert body["action_items"] == []
    assert body["progress"] == []


def test_later_semesters_electives_do_not_leak_into_an_earlier_one(dashboard):
    types = {c["component_type"] for c in dashboard(1)["curriculum_semester"]["components"]}
    assert types == {"CORE"}


def test_a_semester_the_curriculum_leaves_empty_shows_no_semester_at_all(dashboard):
    """Semester III has no rows in this cut-down curriculum. The dashboard says
    so; it does not fall back to some other semester's slots."""
    body = dashboard(3)
    assert body["curriculum_semester"] is None
    assert stat(body, "pending_electives")["value"] == 0


# ── semester IV: the first elective ────────────────────────────────────────
def test_the_open_elective_appears_in_semester_four_and_waits_on_the_student(
        dashboard, campus):
    body = dashboard(4)
    assert statuses(body) == {"S4-01": "Core", "OE1": "Action needed"}
    pending = stat(body, "pending_electives")
    assert pending["value"] == 1
    assert pending["link"] == f"/academics/open-electives/{campus.components['OE1'].id}"
    assert [item["link"] for item in body["action_items"]] == [pending["link"]]


def test_an_allocation_settles_the_open_elective(dashboard, campus, world, db):
    db.add(ElectiveAllocation(
        student_id=world.student_a.student.id,
        curriculum_component_id=campus.components["OE1"].id,
        course_offering_id=campus.offering("OE1").id,
        status=AllocationStatus.ALLOCATED))
    db.flush()

    body = dashboard(4)
    assert statuses(body)["OE1"] == "Allocated"
    assert stat(body, "pending_electives")["value"] == 0
    assert body["action_items"] == []


def rank(db, world, campus, status):
    db.add(ElectivePreference(
        student_id=world.student_a.student.id,
        curriculum_component_id=campus.components["OE1"].id,
        course_offering_id=campus.offering("OE1").id, preference_order=1,
        status=status))
    db.flush()


def test_submitted_preferences_stop_the_dashboard_asking_again(
        dashboard, campus, world, db):
    rank(db, world, campus, PreferenceStatus.SUBMITTED)

    body = dashboard(4)
    assert statuses(body)["OE1"] == "Preferences submitted"
    assert stat(body, "pending_electives")["value"] == 0
    assert body["action_items"] == []


def test_a_draft_preference_is_not_a_submission(dashboard, campus, world, db):
    rank(db, world, campus, PreferenceStatus.DRAFT)

    body = dashboard(4)
    assert statuses(body)["OE1"] == "Action needed"
    assert stat(body, "pending_electives")["value"] == 1


# ── semester V: the NPTEL slot ─────────────────────────────────────────────
def test_semester_five_asks_for_an_nptel_course_and_a_program_elective(
        dashboard, campus):
    body = dashboard(5)
    assert statuses(body) == {"OE2-MOOC": "Action needed", "PE1": "Action needed"}
    assert stat(body, "pending_electives")["value"] == 2
    links = {item["title"].split(" — ")[0]: item["link"] for item in body["action_items"]}
    # The NPTEL slot is registered on its own screen, not through preferences.
    assert links["Open Elective 2 (NPTEL/SWAYAM/MOOC)"] == "/academics/nptel"
    assert links["Program Elective 1"] == (
        f"/academics/core-electives/{campus.components['PE1'].id}")


def register_mooc(db, world, campus, status):
    row = MoocRegistration(
        student_id=world.student_a.student.id,
        course_offering_id=campus.offering("OE2-MOOC").id,
        curriculum_component_id=campus.components["OE2-MOOC"].id,
        status=status)
    db.add(row)
    db.flush()
    return row


@pytest.mark.parametrize("status", [MoocStatus.REGISTERED, MoocStatus.VERIFIED])
def test_an_nptel_registration_settles_the_slot(dashboard, campus, world, db, status):
    """Regression: the slot was judged by an elective allocation it can never
    receive, so it stayed "Action needed" after the certificate was verified."""
    register_mooc(db, world, campus, status)

    body = dashboard(5)
    assert statuses(body) == {"OE2-MOOC": status.value, "PE1": "Action needed"}
    assert stat(body, "pending_electives")["value"] == 1
    assert [item["title"] for item in body["action_items"]] == [
        "Program Elective 1 — submit preferences"]


def test_a_rejected_nptel_registration_puts_the_slot_back_on_the_list(
        dashboard, campus, world, db):
    register_mooc(db, world, campus, MoocStatus.REJECTED)

    body = dashboard(5)
    assert statuses(body)["OE2-MOOC"] == "REJECTED"
    assert stat(body, "pending_electives")["value"] == 2
    assert any("register again" in item["title"] for item in body["action_items"])


def test_another_students_registration_settles_nothing_for_this_one(
        dashboard, campus, world, db):
    db.add(MoocRegistration(
        student_id=world.student_b.student.id,
        course_offering_id=campus.offering("OE2-MOOC").id,
        curriculum_component_id=campus.components["OE2-MOOC"].id,
        status=MoocStatus.VERIFIED))
    db.flush()

    assert statuses(dashboard(5))["OE2-MOOC"] == "Action needed"


# ── who may ask ────────────────────────────────────────────────────────────
def test_the_student_dashboard_refuses_non_students(api, world, login, campus):
    response = api.get("/api/v1/dashboard/student", headers=login(world.plain.email))
    assert response.status_code == 403


# ── the sidebar is told the same thing ─────────────────────────────────────
@pytest.mark.parametrize("semester,sections", [
    (1, set()), (2, set()), (3, set()),
    (4, {"open_electives"}),
    (5, {"open_electives", "core_electives", "nptel"}),
])
def test_the_menu_offers_elective_screens_only_once_the_curriculum_reaches_them(
        api, world, login, db, campus, semester, sections):
    world.student_a.student.current_semester = semester
    db.flush()

    me = api.get("/api/v1/auth/me", headers=login(world.student_a.email))
    assert me.status_code == 200, me.text
    offered = set(me.json()["student"]["visible_sections"])
    assert offered & {"open_electives", "core_electives", "nptel"} == sections
