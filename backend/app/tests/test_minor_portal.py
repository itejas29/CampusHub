"""A minor, once a student holds a seat: courses by semester, results, fees.

* Applications are made in Semester III; a later student who never applied
  does not see the minor, a student who applied keeps it.
* The enrolled student sees each semester's courses, their result in each,
  and the semester's fee — no fee until the coordinator announces one.
* Only the minor's coordinator records results and payments; a passed course
  counts its credits.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models.academics import Course
from app.models.enums import (
    AssignedRole, CoordinationDomain, MinorEnrollmentStatus, Role,
)
from app.models.identity import FacultyRoleAssignment, UserRole
from app.models.minors import MinorCourse, MinorEnrollment, MinorProgram
from app.services import minors as minor_service

from app.tests.test_internship_windows import _student  # noqa: F401

NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def minor(db, world):
    """A CSE minor with one course in Semester III and one in Semester IV,
    coordinated by world.summer_cse for CSE."""
    program = MinorProgram(code="MIN-T", name="Minor in Testing",
                           department_id=world.departments["CSE"].id, capacity=10,
                           eligible_from_semester=3, min_cpi=7.0, max_backlogs=0,
                           application_opens_at=NOW - dt.timedelta(days=1),
                           application_closes_at=NOW + dt.timedelta(days=10),
                           rules={"ranking": {"criteria": [{"field": "cpi", "direction": "desc"}]}})
    db.add(program)
    db.flush()
    for i, (code, sem, credits) in enumerate([("MT-1", 3, 3), ("MT-2", 4, 4)], 1):
        course = Course(code=code, title=f"Course {code}", department_id=world.departments["CSE"].id,
                        credits=credits)
        db.add(course)
        db.flush()
        db.add(MinorCourse(minor_program_id=program.id, course_id=course.id, sequence=i,
                           semester_offset=sem - 2))
    db.add(FacultyRoleAssignment(faculty_id=world.summer_cse.faculty.id, role=AssignedRole.COORDINATOR,
                                 domain=CoordinationDomain.MINOR,
                                 department_id=world.departments["CSE"].id, is_active=True))
    db.flush()
    db.refresh(program)
    return program


@pytest.fixture
def seat(db, world, minor):
    """An ICT student, now in Semester IV, who took the seat in Semester III."""
    student = _student(db, world, "23BIT400", semester=4)
    enrollment = MinorEnrollment(student_id=student.id, minor_program_id=minor.id,
                                 status=MinorEnrollmentStatus.ACTIVE, started_semester=3)
    db.add(enrollment)
    db.flush()
    return student, enrollment


def test_a_later_student_who_never_applied_cannot_apply_or_see_it(api, db, world, login, minor):
    student = _student(db, world, "23BIT401", semester=4)
    headers = login(student.user.email)
    assert api.get("/api/v1/minors/workspace", headers=headers).json()["programs"] == []
    response = api.post("/api/v1/minors/apply", headers=headers, json={"preferences": [minor.id]})
    assert response.status_code in (400, 409, 422)
    me = api.get("/api/v1/auth/me", headers=headers).json()
    assert "minors" not in me["student"]["visible_sections"]


def test_a_semester_three_student_applies(api, db, world, login, minor):
    student = _student(db, world, "24BIT402", semester=3)
    response = api.post("/api/v1/minors/apply", headers=login(student.user.email),
                        json={"preferences": [minor.id]})
    assert response.status_code == 201, response.text


def test_the_enrolled_student_sees_a_semester_plan(api, db, world, login, minor, seat):
    student, _enrollment = seat
    body = api.get("/api/v1/minors/workspace", headers=login(student.user.email)).json()
    plan = {p["semester"]: p for p in body["enrollment"]["plan"]}
    assert plan[3]["when"] == "past" and plan[4]["when"] == "current"
    assert [c["code"] for c in plan[4]["courses"]] == ["MT-2"]
    assert plan[3]["fee"] is None     # nothing announced, nothing shown


def test_the_coordinator_records_a_result_and_the_credits_follow(api, db, world, login, minor, seat):
    student, enrollment = seat
    first = next(c for c in minor.courses if c.course.code == "MT-1")
    url = f"/api/v1/minors/{minor.id}/courses/{first.id}/results"
    refused = api.put(url, headers=login(world.summer_ict.email),
                      json={"results": [{"enrollment_id": enrollment.id, "marks": 70, "status": "PASSED"}]})
    assert refused.status_code == 403
    no_mark = api.put(url, headers=login(world.summer_cse.email),
                      json={"results": [{"enrollment_id": enrollment.id, "status": "PASSED"}]})
    assert no_mark.status_code == 422
    ok = api.put(url, headers=login(world.summer_cse.email),
                 json={"results": [{"enrollment_id": enrollment.id, "marks": 78, "grade": "b+", "status": "PASSED"}]})
    assert ok.status_code == 200, ok.text
    db.refresh(enrollment)
    assert float(enrollment.credits_completed) == 3
    plan = {p["semester"]: p for p in api.get("/api/v1/minors/workspace",
                                              headers=login(student.user.email)).json()["enrollment"]["plan"]}
    assert plan[3]["courses"][0]["result"] == {"marks": 78.0, "grade": "B+", "status": "PASSED"}


def test_fees_are_set_by_the_coordinator_and_payments_recorded(api, db, world, login, minor, seat):
    student, enrollment = seat
    coordinator = login(world.summer_cse.email)
    assert api.put(f"/api/v1/minors/{minor.id}/fees", headers=coordinator,
                   json={"fees": [{"semester": 7, "amount": 1}]}).status_code == 422
    assert api.put(f"/api/v1/minors/{minor.id}/fees", headers=coordinator,
                   json={"fees": [{"semester": 3, "amount": 9000}, {"semester": 4, "amount": 9000}]}).status_code == 200
    assert api.put(f"/api/v1/minors/enrollments/{enrollment.id}/fees/3", headers=login(student.user.email),
                   json={"amount": 9000}).status_code == 403
    assert api.put(f"/api/v1/minors/enrollments/{enrollment.id}/fees/3", headers=coordinator,
                   json={"amount": 9000, "reference": "R-1"}).status_code == 200
    plan = {p["semester"]: p for p in api.get("/api/v1/minors/workspace",
                                              headers=login(student.user.email)).json()["enrollment"]["plan"]}
    assert plan[3]["payment"]["reference"] == "R-1" and plan[4]["payment"] is None
    assert plan[4]["fee"]["amount"] == 9000


def test_application_semesters_default_to_the_first_eligible_one(minor):
    assert minor_service.application_semesters(minor) == [3]
    minor.rules = {**minor.rules, "application_semesters": [3, 5]}
    assert minor_service.application_semesters(minor) == [3, 5]


# ── syllabus ──────────────────────────────────────────────────────────────
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
SYLLABUS = {"units": [{"title": "Unit 1: Foundations", "topics": ["Sets", "  ", "Logic"], "hours": 6}],
            "outcomes": ["Reason formally"], "references": ["A textbook"]}


def test_a_syllabus_appears_only_once_published(api, db, world, login, minor, seat):
    student, _enrollment = seat
    course = next(c for c in minor.courses if c.course.code == "MT-2")
    plan = lambda: {p["semester"]: p for p in api.get(
        "/api/v1/minors/workspace", headers=login(student.user.email)).json()["enrollment"]["plan"]}
    assert plan()[4]["courses"][0]["syllabus"] is None
    url = f"/api/v1/minors/{minor.id}/courses/{course.id}/syllabus"
    assert api.put(url, headers=login(world.summer_ict.email), json=SYLLABUS).status_code == 403
    assert api.put(url, headers=login(student.user.email), json=SYLLABUS).status_code == 403
    response = api.put(url, headers=login(world.summer_cse.email), json=SYLLABUS)
    assert response.status_code == 200, response.text
    published = plan()[4]["courses"][0]["syllabus"]
    assert published["units"][0]["topics"] == ["Sets", "Logic"] and published["updated_at"]


def test_a_published_syllabus_pdf_is_readable_by_students(api, db, world, login, minor, seat):
    student, _enrollment = seat
    course = next(c for c in minor.courses if c.course.code == "MT-2")
    url = f"/api/v1/minors/{minor.id}/courses/{course.id}/syllabus/file"
    response = api.post(url, headers=login(world.summer_cse.email),
                        files={"file": ("s.pdf", PDF, "application/pdf")})
    assert response.status_code == 200, response.text
    file_url = response.json()["syllabus"]["file_url"]
    assert api.get(file_url, headers=login(student.user.email)).status_code == 200
    assert api.get(file_url, headers=login(world.student_b.email)).status_code == 200
    assert api.get(file_url).status_code == 401
