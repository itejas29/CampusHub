"""Bulk internship mentor allocation: who can be a mentor, and how many each.

The rules this file protects were all broken at once before:

* **No mentor carries more than the programme allows.** Roll-number allocation
  used to hand every leftover student to the last mentor — 203 students over
  five mentors came out as 10/10/10/10/163.
* **Mentors come from the programme's department, and never the HoD.** The pool
  was every faculty member in the university, so a CSE professor could be given
  ICT's CSSI students, and a run that reached the HoD failed part-way.
* **Mentor loads are the coordinator's to see.** The capacity list answered any
  signed-in account, students included.
* **The cap is programme data**, not a number in the route.
"""
from __future__ import annotations

import pytest

from app.models.enums import InternshipType, Role, StudentStatus
from app.models.identity import Faculty, Student, User, UserRole
from app.models.internships import InternshipEnrollment, InternshipProgram
from app.services import internships as engine
from app.services import scope


@pytest.fixture
def cssi(db, world):
    # Seeded coordinators carry the coarse role as well as the scoped grant;
    # the role opens the route, the grant decides which programme.
    db.add(UserRole(user_id=world.cssi_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    program = InternshipProgram(
        code="CSSI-ICT-T", name="CSSI (ICT)", type=InternshipType.CSSI,
        department_id=world.departments["ICT"].id, config={},
    )
    db.add(program)
    db.flush()
    return program


def _faculty(db, world, name, dept="ICT"):
    user = User(email=f"{name.lower().replace(' ', '.')}@test.example.com",
                hashed_password="x", full_name=name)
    db.add(user)
    db.flush()
    row = Faculty(user_id=user.id, employee_code=f"F-{name}",
                  department_id=world.departments[dept].id,
                  designation="Assistant Professor")
    db.add(row)
    db.flush()
    return row


def _enrol(db, world, program, count):
    rows = []
    for n in range(count):
        user = User(email=f"cssi{n}@test.example.com", hashed_password="x",
                    full_name=f"CSSI Student {n}")
        db.add(user)
        db.flush()
        student = Student(
            user_id=user.id, roll_number=f"24BIT{n:03d}",
            program_id=world.programs["B.TECH-ICT"].id,
            department_id=world.departments["ICT"].id, admission_year=2024,
            current_semester=3, division="A", cpi=8.0, backlog_count=0,
            status=StudentStatus.ACTIVE)
        db.add(student)
        db.flush()
        enrollment = InternshipEnrollment(program_id=program.id, student_id=student.id)
        db.add(enrollment)
        rows.append(enrollment)
    db.flush()
    return rows


def _loads(db, program):
    counts: dict[int, int] = {}
    for e in db.query(InternshipEnrollment).filter_by(program_id=program.id):
        if e.mentor_faculty_id:
            counts[e.mentor_faculty_id] = counts.get(e.mentor_faculty_id, 0) + 1
    return counts


def _assign(api, login, world, program, **body):
    return api.post(f"/api/v1/internships/programs/{program.id}/assign-mentors",
                    headers=login(world.cssi_ict.email), json=body)


# ── the split itself ───────────────────────────────────────────────────────
@pytest.mark.parametrize("total, mentors, capacity, expected", [
    (203, 5, 10, [10, 10, 10, 10, 10]),   # the old code gave the fifth 163
    (50, 2, 10, [10, 10]),
    (21, 3, 10, [7, 7, 7]),
    (11, 5, 10, [6, 5]),                  # uses only as many mentors as needed
    (0, 4, 10, []),
    (9, 0, 10, []),
])
def test_roll_number_blocks_never_exceed_capacity(total, mentors, capacity, expected):
    sizes = engine.split_by_roll(total, mentors, capacity)
    assert sizes == expected
    assert all(s <= capacity for s in sizes)


def test_the_cap_is_read_from_the_programme(cssi):
    assert engine.mentor_capacity(cssi) == engine.DEFAULT_MENTOR_CAPACITY
    cssi.config = {"mentor_capacity": 6}
    assert engine.mentor_capacity(cssi) == 6


# ── through the API ────────────────────────────────────────────────────────
def test_overflow_students_are_left_unassigned_not_piled_on_one_mentor(
        api, db, world, login, cssi):
    a, b = _faculty(db, world, "Alpha Mentor"), _faculty(db, world, "Beta Mentor")
    _enrol(db, world, cssi, 25)

    response = _assign(api, login, world, cssi, allocate_by_roll_no=True,
                       faculty_ids=[a.id, b.id])
    assert response.status_code == 200, response.text
    assert sorted(_loads(db, cssi).values()) == [10, 10]
    assert "5 still need a mentor" in response.json()["message"]


def test_a_programme_cap_is_honoured_by_bulk_allocation(api, db, world, login, cssi):
    cssi.config = {"mentor_capacity": 4}
    db.flush()
    a = _faculty(db, world, "Alpha Mentor")
    _enrol(db, world, cssi, 9)

    _assign(api, login, world, cssi, allocate_by_roll_no=True, faculty_ids=[a.id])
    assert list(_loads(db, cssi).values()) == [4]


def test_faculty_from_another_department_cannot_be_chosen(api, db, world, login, cssi):
    outsider = _faculty(db, world, "Cse Professor", dept="CSE")
    _enrol(db, world, cssi, 3)

    response = _assign(api, login, world, cssi, allocate_by_roll_no=True,
                       faculty_ids=[outsider.id])
    assert response.status_code == 422, response.text
    assert _loads(db, cssi) == {}


def test_rebalance_draws_only_on_the_programmes_department(api, db, world, login, cssi):
    _faculty(db, world, "Cse Professor", dept="CSE")
    _enrol(db, world, cssi, 30)

    response = _assign(api, login, world, cssi, rebalance=True)
    assert response.status_code == 200, response.text
    ict = world.departments["ICT"].id
    for faculty_id in _loads(db, cssi):
        assert db.get(Faculty, faculty_id).department_id == ict


def test_the_hod_is_skipped_rather_than_failing_the_run(api, db, world, login, cssi):
    # The HoD sorts first by name, so the old pool reached them immediately.
    hod = _faculty(db, world, "Aaron Head")
    scope.set_hod(db, world.departments["ICT"], hod)
    _enrol(db, world, cssi, 12)

    response = _assign(api, login, world, cssi, rebalance=True)
    assert response.status_code == 200, response.text
    assert hod.id not in _loads(db, cssi)


def test_a_single_override_respects_the_department(api, db, world, login, cssi):
    outsider = _faculty(db, world, "Cse Professor", dept="CSE")
    [enrollment] = _enrol(db, world, cssi, 1)

    response = api.post(f"/api/v1/internships/enrollments/{enrollment.id}/mentor",
                        headers=login(world.cssi_ict.email),
                        json={"mentor_faculty_id": outsider.id, "reason": "test"})
    assert response.status_code == 409, response.text
    assert enrollment.mentor_faculty_id is None


def test_mentor_loads_are_visible_only_to_the_programmes_coordinator(
        api, db, world, login, cssi):
    url = f"/api/v1/internships/programs/{cssi.id}/mentors-capacity"
    for account in (world.student_a, world.plain, world.summer_ict):
        assert api.get(url, headers=login(account.email)).status_code == 403

    response = api.get(url, headers=login(world.cssi_ict.email))
    assert response.status_code == 200, response.text
    departments = {row["department_code"] for row in response.json()}
    assert departments <= {"ICT"}


def test_the_capacity_list_reports_the_programmes_own_cap(api, db, world, login, cssi):
    cssi.config = {"mentor_capacity": 7}
    db.flush()
    response = api.get(f"/api/v1/internships/programs/{cssi.id}/mentors-capacity",
                       headers=login(world.cssi_ict.email))
    assert {row["max_capacity"] for row in response.json()} == {7}


def test_reassigning_the_same_mentor_records_nothing(db, world, cssi):
    from app.models.system import AuditLog

    mentor = _faculty(db, world, "Alpha Mentor")
    [enrollment] = _enrol(db, world, cssi, 1)
    engine.override_mentor(db, enrollment=enrollment, new_faculty_id=mentor.id, reason="x")
    db.flush()
    before = db.query(AuditLog).count()
    engine.override_mentor(db, enrollment=enrollment, new_faculty_id=mentor.id, reason="x")
    db.flush()
    assert db.query(AuditLog).count() == before


# ── the faculty dashboard's portfolio figures ──────────────────────────────
def test_the_coordinators_dashboard_counts_their_own_programme(
        api, db, world, login, cssi):
    mentor = _faculty(db, world, "Alpha Mentor")
    rows = _enrol(db, world, cssi, 3)
    engine.override_mentor(db, enrollment=rows[0], new_faculty_id=mentor.id, reason="x")
    db.flush()

    response = api.get("/api/v1/dashboard/faculty", headers=login(world.cssi_ict.email))
    assert response.status_code == 200, response.text
    [portfolio] = [p for p in response.json()["portfolios"] if p["domain"] == "CSSI"]
    assert portfolio["program_id"] == cssi.id
    stats = {s["label"]: s["value"] for s in portfolio["stats"]}
    assert stats["Registered"] == 3
    assert stats["Mentors"] == 1
    assert stats["Awaiting mentor"] == 2


def test_another_modules_coordinator_sees_no_cssi_figures(api, db, world, login, cssi):
    _enrol(db, world, cssi, 3)
    response = api.get("/api/v1/dashboard/faculty", headers=login(world.summer_ict.email))
    domains = {p["domain"] for p in response.json()["portfolios"]}
    assert "CSSI" not in domains


# ── confirming the cap ─────────────────────────────────────────────────────
# The default of 10 is the portal's, not a written PDEU rule. Until a
# coordinator records the figure their department uses, every surface must
# say it is unconfirmed rather than present it as policy.
def test_the_default_cap_is_reported_as_unconfirmed(api, db, world, login, cssi):
    rows = api.get(f"/api/v1/internships/programs/{cssi.id}/mentors-capacity",
                   headers=login(world.cssi_ict.email)).json()
    assert rows and {r["capacity_confirmed"] for r in rows} == {False}


def test_the_coordinator_confirms_the_cap_and_it_is_audited(api, db, world, login, cssi):
    from app.models.system import AuditLog

    response = api.patch(f"/api/v1/internships/programs/{cssi.id}",
                         headers=login(world.cssi_ict.email), json={"mentor_capacity": 12})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mentor_capacity"] == 12 and body["mentor_capacity_confirmed"] is True

    rows = api.get(f"/api/v1/internships/programs/{cssi.id}/mentors-capacity",
                   headers=login(world.cssi_ict.email)).json()
    assert {(r["max_capacity"], r["capacity_confirmed"]) for r in rows} == {(12, True)}
    last = (db.query(AuditLog).filter_by(entity_type="internship_program", entity_id=cssi.id)
            .order_by(AuditLog.id.desc()).first())
    assert "mentor cap confirmed at 12 (was 10)" in last.description


def test_another_modules_coordinator_cannot_set_the_cap(api, db, world, login, cssi):
    db.add(UserRole(user_id=world.summer_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    db.flush()
    response = api.patch(f"/api/v1/internships/programs/{cssi.id}",
                         headers=login(world.summer_ict.email), json={"mentor_capacity": 30})
    assert response.status_code == 403
    assert engine.mentor_capacity_confirmed(cssi) is False


@pytest.mark.parametrize("value", [0, -1, 61])
def test_an_implausible_cap_is_refused(api, db, world, login, cssi, value):
    response = api.patch(f"/api/v1/internships/programs/{cssi.id}",
                         headers=login(world.cssi_ict.email), json={"mentor_capacity": value})
    assert response.status_code == 422
