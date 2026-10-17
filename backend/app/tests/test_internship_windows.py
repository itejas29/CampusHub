"""The CSSI cycle, run by the coordinator's windows.

1. The HoD appoints a CSSI coordinator (covered in test_hod).
2. The coordinator opens **registration** with a message, an opening date and a
   deadline. The Semester II cohort is notified and, while it is open, records
   the NGO and its supervisor's name and number. It locks at the deadline.
3. Mentors can be allocated only once registration has been started.
4. In Semester III the coordinator opens **presentations** with the poster
   deadline and presentation day. Every student is told their mentor; every
   mentor is told their students.
5. Posters go to the mentor until the poster deadline; marks are entered until
   the window closes, then lock. The coordinator can extend either.

None of it is CSSI-specific code: the programme lists its windows in config.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models.engagement import Notification
from app.models.enums import InternshipType, InternshipWindowKind as Kind, Role, StudentStatus
from app.models.identity import Student, User, UserRole
from app.models.internships import InternshipEnrollment, InternshipProgram, InternshipWindow
from app.services import internship_windows as windows

NOW = dt.datetime.now(dt.timezone.utc)


def at(days: float) -> str:
    return (NOW + dt.timedelta(days=days)).isoformat()


@pytest.fixture
def cssi(db, world):
    db.add(UserRole(user_id=world.cssi_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    program = InternshipProgram(
        code="CSSI-W", name="Community and Social Service Internship",
        type=InternshipType.CSSI, department_id=world.departments["ICT"].id,
        target_semester=3, announce_from_semester=2, visible_to_semester=3,
        requires_industry_mentor=True,
        config={"windows": ["REGISTRATION", "PRESENTATION"]},
    )
    db.add(program)
    db.flush()
    return program


def _student(db, world, roll, semester=2, dept="ICT"):
    from app.core.security import hash_password

    user = User(email=f"{roll.lower()}@test.example.com",
                hashed_password=hash_password(world.password), full_name=f"Student {roll}")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role=Role.STUDENT))
    student = Student(
        user_id=user.id, roll_number=roll,
        program_id=world.programs["B.TECH-ICT" if dept == "ICT" else "B.TECH-CE"].id,
        department_id=world.departments[dept].id, admission_year=2025,
        current_semester=semester, division="A", cpi=8.0, backlog_count=0,
        status=StudentStatus.ACTIVE)
    db.add(student)
    db.flush()
    return student


REGISTRATION = {
    "kind": "REGISTRATION", "title": "CSSI 2026 registration",
    "message": "CSSI is a compulsory community internship. Find an approved NGO "
               "and register it here with your supervisor's details.",
    "opens_at": at(-0.01), "closes_at": at(10), "cohort_semester": 2,
}


def _open_registration(api, login, world, cssi, **overrides):
    return api.post(f"/api/v1/internships/programs/{cssi.id}/windows",
                    headers=login(world.cssi_ict.email), json={**REGISTRATION, **overrides})


def _enrol(api, login, student, cssi, **body):
    payload = {"new_organization": {"name": f"NGO for {student.roll_number}", "type": "NGO",
                                    "city": "Gandhinagar"},
               "industry_mentor_name": "Asha Patel", "industry_mentor_phone": "9800000000",
               **body}
    return api.post(f"/api/v1/internships/programs/{cssi.id}/enroll",
                    headers=login(student.user.email), json=payload)


def _close(db, cssi, kind):
    window = windows.get(db, cssi.id, kind)
    window.closes_at = NOW - dt.timedelta(minutes=1)
    db.flush()
    return window


# ── registration ───────────────────────────────────────────────────────────
def test_without_a_window_a_semester_two_student_cannot_register(api, db, world, login, cssi):
    student = _student(db, world, "25BIT001")
    response = _enrol(api, login, student, cssi)
    assert response.status_code == 409
    assert "not opened yet" in response.json()["error"]["message"]


def test_opening_registration_notifies_exactly_the_cohort(api, db, world, login, cssi):
    cohort = [_student(db, world, f"25BIT00{i}") for i in range(1, 4)]
    later = _student(db, world, "24BIT050", semester=4)
    other_dept = _student(db, world, "25BCE001", dept="CSE")

    response = _open_registration(api, login, world, cssi)
    assert response.status_code == 201, response.text
    assert response.json()["state"] == "OPEN"

    told = {n.user_id for n in db.query(Notification).filter_by(type="INTERNSHIP_WINDOW")}
    assert {s.user_id for s in cohort} <= told
    assert later.user_id not in told and other_dept.user_id not in told
    note = db.query(Notification).filter_by(user_id=cohort[0].user_id).first()
    assert "compulsory community internship" in note.message and "Deadline:" in note.message


def test_a_semester_two_student_registers_the_ngo_and_its_supervisor(api, db, world, login, cssi):
    student = _student(db, world, "25BIT001")
    _open_registration(api, login, world, cssi)
    response = _enrol(api, login, student, cssi)
    assert response.status_code == 201, response.text
    enrollment = db.query(InternshipEnrollment).filter_by(student_id=student.id).one()
    assert (enrollment.industry_mentor_name, enrollment.industry_mentor_phone) == (
        "Asha Patel", "9800000000")


def test_the_supervisors_name_and_number_are_required(api, db, world, login, cssi):
    student = _student(db, world, "25BIT001")
    _open_registration(api, login, world, cssi)
    response = _enrol(api, login, student, cssi, industry_mentor_phone="")
    assert response.status_code == 422


def test_the_window_admits_only_its_cohort(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    response = _enrol(api, login, _student(db, world, "24BIT050", semester=4), cssi)
    assert response.status_code == 409
    assert "Semester 2 students" in response.json()["error"]["message"]


def test_registration_locks_at_the_deadline_and_reopens_when_extended(api, db, world, login, cssi):
    student = _student(db, world, "25BIT001")
    _open_registration(api, login, world, cssi)
    _enrol(api, login, student, cssi)
    enrollment = db.query(InternshipEnrollment).filter_by(student_id=student.id).one()
    window = _close(db, cssi, Kind.REGISTRATION)

    edit = lambda: api.patch(f"/api/v1/internships/enrollments/{enrollment.id}",  # noqa: E731
                             headers=login(student.user.email),
                             json={"industry_mentor_phone": "9811111111"})
    late = _student(db, world, "25BIT002")
    assert _enrol(api, login, late, cssi).status_code == 409
    response = edit()
    assert response.status_code == 409 and "closed on" in response.json()["error"]["message"]

    extended = api.patch(f"/api/v1/internships/windows/{window.id}",
                         headers=login(world.cssi_ict.email), json={"closes_at": at(3)})
    assert extended.status_code == 200, extended.text
    assert extended.json()["state"] == "OPEN"
    assert edit().status_code == 200
    assert _enrol(api, login, late, cssi).status_code == 201
    assert db.query(Notification).filter(
        Notification.user_id == late.user_id,
        Notification.title.contains("reopened")).count() == 1


def test_only_this_programmes_coordinator_opens_its_windows(api, db, world, login, cssi):
    db.add(UserRole(user_id=world.summer_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    db.flush()
    response = api.post(f"/api/v1/internships/programs/{cssi.id}/windows",
                        headers=login(world.summer_ict.email), json=REGISTRATION)
    assert response.status_code == 403
    student = _student(db, world, "25BIT001")
    response = api.post(f"/api/v1/internships/programs/{cssi.id}/windows",
                        headers=login(student.user.email), json=REGISTRATION)
    assert response.status_code == 403


@pytest.mark.parametrize("change, message", [
    ({"opens_at": at(-3), "closes_at": at(-1)}, "past"),
    ({"opens_at": at(5), "closes_at": at(4)}, "after the opening"),
    ({"cohort_semester": 5}, "Semester 2 or 3"),
])
def test_implausible_registration_windows_are_refused(api, db, world, login, cssi, change, message):
    response = _open_registration(api, login, world, cssi, **change)
    assert response.status_code == 422
    assert message in response.json()["error"]["message"]


# ── mentor allocation waits for the cycle to start ─────────────────────────
def test_mentors_cannot_be_allocated_before_registration_starts(api, db, world, login, cssi):
    url = f"/api/v1/internships/programs/{cssi.id}/assign-mentors"
    body = {"allocate_by_roll_no": True}
    response = api.post(url, headers=login(world.cssi_ict.email), json=body)
    assert response.status_code == 409
    assert "Open the registration window" in response.json()["error"]["message"]

    _open_registration(api, login, world, cssi)
    _enrol(api, login, _student(db, world, "25BIT001"), cssi)
    assert api.post(url, headers=login(world.cssi_ict.email), json=body).status_code == 200


# ── presentations, posters and marks ──────────────────────────────────────
PRESENTATION = {
    "kind": "PRESENTATION", "title": "CSSI posters and presentations",
    "message": "Submit your poster to your mentor and present on the day.",
    "opens_at": at(-0.01), "submission_due_at": at(5), "closes_at": at(12),
    "presentation_from": (NOW + dt.timedelta(days=7)).date().isoformat(),
}


@pytest.fixture
def registered(api, db, world, login, cssi):
    """Two students registered, registration closed, both with the ICT mentor."""
    students = [_student(db, world, f"25BIT00{i}") for i in (1, 2)]
    _open_registration(api, login, world, cssi)
    for s in students:
        assert _enrol(api, login, s, cssi).status_code == 201
    _close(db, cssi, Kind.REGISTRATION)
    return students


def _assign_all(db, world, cssi):
    for e in db.query(InternshipEnrollment).filter_by(program_id=cssi.id):
        e.mentor_faculty_id = world.mentor_ict.faculty.id
    db.flush()


def _open_presentations(api, login, world, cssi, **overrides):
    return api.post(f"/api/v1/internships/programs/{cssi.id}/windows",
                    headers=login(world.cssi_ict.email), json={**PRESENTATION, **overrides})


def test_presentations_wait_until_every_student_has_a_mentor(api, db, world, login, cssi, registered):
    response = _open_presentations(api, login, world, cssi)
    assert response.status_code == 409
    assert "no faculty mentor" in response.json()["error"]["message"]


def test_presentations_wait_for_registration_to_close(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    response = _open_presentations(api, login, world, cssi)
    assert response.status_code == 409
    assert "still open" in response.json()["error"]["message"]


def test_opening_presentations_tells_each_student_their_mentor(api, db, world, login, cssi, registered):
    _assign_all(db, world, cssi)
    response = _open_presentations(api, login, world, cssi)
    assert response.status_code == 201, response.text

    note = (db.query(Notification).filter(Notification.user_id == registered[0].user_id,
                                          Notification.title.contains("your mentor"))
            .one())
    assert "Mentor ICT" in note.title
    assert "Poster to your mentor by" in note.message and "Mentors assigned:" in note.message
    assert "25BIT001–25BIT002" in note.message
    mentor_note = db.query(Notification).filter(
        Notification.user_id == world.mentor_ict.user.id,
        Notification.title.contains("2 students present to you")).one()
    assert "Marks lock" in mentor_note.message


def test_posters_close_at_the_poster_deadline(api, db, world, login, cssi, registered):
    _assign_all(db, world, cssi)
    _open_presentations(api, login, world, cssi)
    windows.assert_can_submit_poster(db, cssi, now=NOW + dt.timedelta(days=1))
    with pytest.raises(Exception, match="Posters were due"):
        windows.assert_can_submit_poster(db, cssi, now=NOW + dt.timedelta(days=6))


def test_marks_open_with_presentations_and_lock_at_the_deadline(api, db, world, login, cssi, registered):
    _assign_all(db, world, cssi)
    enrollment = db.query(InternshipEnrollment).filter_by(student_id=registered[0].id).one()
    mark = lambda: api.post(f"/api/v1/internships/enrollments/{enrollment.id}/evaluation",  # noqa: E731
                            headers=login(world.mentor_ict.email), json={"scores": []})

    response = mark()
    assert response.status_code == 409 and "not started" in response.json()["error"]["message"]

    _open_presentations(api, login, world, cssi)
    assert mark().status_code == 200

    window = _close(db, cssi, Kind.PRESENTATION)
    response = mark()
    assert response.status_code == 409 and "Marks are locked" in response.json()["error"]["message"]

    api.patch(f"/api/v1/internships/windows/{window.id}",
              headers=login(world.cssi_ict.email), json={"closes_at": at(14)})
    assert mark().status_code == 200


def test_the_mentor_list_is_published_with_the_presentation_window(api, db, world, login, cssi, registered):
    _assign_all(db, world, cssi)
    url = f"/api/v1/internships/programs/{cssi.id}/mentor-roster"
    student = login(registered[0].user.email)
    assert api.get(url, headers=student).status_code == 403

    _open_presentations(api, login, world, cssi)
    [group] = api.get(url, headers=student).json()
    assert group["name"] == "Mentor ICT" and group["roll_range"] == "25BIT001–25BIT002"
    outsider = _student(db, world, "25BIT009")
    assert api.get(url, headers=login(outsider.user.email)).status_code == 403


def test_a_programme_without_windows_keeps_the_semester_rules(db, world):
    plain = InternshipProgram(code="SI-PLAIN", name="Summer", type=InternshipType.SUMMER,
                              config={})
    assert windows.kinds_for(plain) == []
    windows.assert_can_allocate_mentors(db, plain)
    windows.assert_marks_open(db, plain)
    windows.assert_can_submit_poster(db, plain)
