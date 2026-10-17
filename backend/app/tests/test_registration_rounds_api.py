"""Registration rounds, driven through the API by the people who use them.

``test_registration_windows`` pins the round's own rules against the service.
These pin what was missing above it:

* **A coordinator could not run a round at all.** Every round route asked
  `scope.assert_coordinates` without its required arguments, so anyone but the
  super admin got a 500. The first block is the regression for that, and for
  the scope it should have been enforcing: one elective family, one department.
* **The Head of Department reads rounds and drives none.**
* **A round, not the semester, opens registration early.** Choice filling for a
  Semester IV elective runs mid-way through Semester III. Before, the curriculum
  refused that student before the round was even consulted.
* **Students are told** when a round opens or its deadline moves.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.academics import (
    Course, CourseOffering, CurriculumComponent, ElectivePreference,
    ElectiveRegistrationWindow,
)
from app.models.engagement import Notification
from app.models.enums import (
    AssignedRole, CoordinationDomain, OfferingStatus, RegistrationWindowStatus,
    SemesterTerm,
)
from app.models.identity import AcademicYear, FacultyRoleAssignment, Semester
from app.services import registration, scope

WINDOWS = "/api/v1/electives/admin/windows"
NOW = dt.datetime.now(dt.timezone.utc)
NEXT_WEEK = (NOW + dt.timedelta(days=7)).isoformat()
IN_A_MONTH = (NOW + dt.timedelta(days=30)).isoformat()
YESTERDAY = (NOW - dt.timedelta(days=1)).isoformat()

CURRICULUM = [
    (4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL"),
    (5, "PE1", "Program Elective 1", "PROGRAM_CORE_ELECTIVE", "ANY"),
    (6, "OE3", "Open Elective 3", "OPEN_ELECTIVE", "ANY"),
]


@pytest.fixture
def campus(db, world, make_curriculum):
    """ICT's 2024-28 slots with courses on offer, and the four people who
    relate to a round differently."""
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
    db.add(semester)
    db.flush()

    offerings: dict[str, list[CourseOffering]] = {}
    for code, count in [("OE1", 3), ("PE1", 1), ("OE3", 1)]:
        offerings[code] = []
        for n in range(count):
            course = Course(code=f"{code}-C{n}", title=f"{code} course {n}",
                            department_id=world.departments["SLS"].id, credits=3)
            db.add(course)
            db.flush()
            offering = CourseOffering(course_id=course.id, semester_id=semester.id,
                                      curriculum_component_id=components[code].id,
                                      status=OfferingStatus.OPEN)
            db.add(offering)
            offerings[code].append(offering)
    db.flush()

    def coordinator(account, domain, dept):
        db.add(FacultyRoleAssignment(
            faculty_id=account.faculty.id, role=AssignedRole.COORDINATOR,
            domain=domain, department_id=world.departments[dept].id,
            is_active=True, assigned_at=NOW))
        db.flush()
        db.refresh(account.faculty)
        return account

    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)
    world.student_a.student.current_semester = 3
    world.student_b.student.current_semester = 5
    db.flush()
    return type("Campus", (), {
        "components": components, "offerings": offerings,
        "ict": world.departments["ICT"].id, "cse": world.departments["CSE"].id,
        "program": world.programs["B.TECH-ICT"].id,
        "open": coordinator(world.cssi_ict, CoordinationDomain.OPEN_ELECTIVE, "ICT"),
        "core": coordinator(world.mentor_ict, CoordinationDomain.CORE_ELECTIVE, "ICT"),
        "open_cse": coordinator(world.summer_cse, CoordinationDomain.OPEN_ELECTIVE, "CSE"),
        "hod": world.plain,
    })


def payload(campus, **overrides):
    body = {
        "code": "OE1-EARLY", "title": "Open Elective 1 — for Semester IV",
        "component_type": "OPEN_ELECTIVE", "department_id": campus.ict,
        "closes_at": NEXT_WEEK, "eligible_semesters": [3],
        "eligible_program_ids": [campus.program],
    }
    body.update(overrides)
    return body


@pytest.fixture
def draft(api, login, campus):
    """A drafted Open Elective round with its three courses attached."""
    headers = login(campus.open.email)
    created = api.post(WINDOWS, json=payload(campus), headers=headers)
    assert created.status_code == 201, created.text
    round_id = created.json()["id"]
    attached = api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
                        json={"offering_ids": [o.id for o in campus.offerings["OE1"]]})
    assert attached.status_code == 200, attached.text
    return round_id


def move(api, headers, round_id, target):
    return api.post(f"{WINDOWS}/{round_id}/status", params={"target": target},
                    headers=headers)


@pytest.fixture
def live(api, login, campus, draft):
    response = move(api, login(campus.open.email), draft, "OPEN")
    assert response.status_code == 200, response.text
    return draft


def message(response):
    return response.json()["error"]["message"]


def prefs(campus, count=1, slot="OE1"):
    return {
        "curriculum_component_id": campus.components[slot].id,
        "preferences": [
            {"course_offering_id": o.id, "preference_order": i + 1}
            for i, o in enumerate(campus.offerings[slot][:count])
        ],
    }


def submit(api, headers, campus, **kw):
    return api.post("/api/v1/electives/preferences", json=prefs(campus, **kw),
                    headers=headers)


def workspace(api, headers, campus, slot="OE1"):
    response = api.get(
        f"/api/v1/electives/components/{campus.components[slot].id}/workspace",
        headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def notices(db, account):
    return [n.title for n in db.scalars(select(Notification).where(
        Notification.user_id == account.user.id).order_by(Notification.id))]


# ── the coordinator runs their round ───────────────────────────────────────
def test_a_coordinator_can_read_their_round_by_id(api, login, campus, draft):
    """Regression: this was a 500 for everyone but the super admin."""
    response = api.get(f"{WINDOWS}/{draft}", headers=login(campus.open.email))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_manage"] is True
    assert body["slot_semester"] == 4 and body["eligible_semesters"] == [3]
    assert [s["code"] for s in body["slots"]] == ["OE1"]


def test_a_coordinator_drives_the_round_from_draft_to_locked_and_back(
        api, login, campus, draft):
    headers = login(campus.open.email)
    assert move(api, headers, draft, "OPEN").json()["status"] == "OPEN"

    extended = api.patch(f"{WINDOWS}/{draft}", json={"closes_at": IN_A_MONTH},
                         headers=headers)
    assert extended.status_code == 200, extended.text
    assert extended.json()["closes_at"].startswith(IN_A_MONTH[:10])

    assert move(api, headers, draft, "LOCKED").json()["status"] == "LOCKED"
    assert move(api, headers, draft, "OPEN").json()["status"] == "OPEN"


def test_the_list_shows_a_coordinator_only_the_family_they_run(
        api, login, campus, draft):
    assert [w["code"] for w in api.get(
        WINDOWS, headers=login(campus.open.email)).json()] == ["OE1-EARLY"]
    assert api.get(WINDOWS, headers=login(campus.core.email)).json() == []
    assert api.get(WINDOWS, headers=login(campus.open_cse.email)).json() == []


@pytest.mark.parametrize("who", ["core", "open_cse"])
def test_another_modules_or_departments_coordinator_is_refused_not_crashed(
        api, login, campus, draft, who):
    """Coordinating Core Electives for ICT, or Open Electives for CSE, grants
    nothing over ICT's Open Elective round — and says so with a 403."""
    headers = login(getattr(campus, who).email)
    attempts = [
        api.get(f"{WINDOWS}/{draft}", headers=headers),
        api.patch(f"{WINDOWS}/{draft}", json={"closes_at": IN_A_MONTH}, headers=headers),
        api.post(f"{WINDOWS}/{draft}/offerings", json={"offering_ids": []},
                 headers=headers),
        move(api, headers, draft, "OPEN"),
    ]
    assert [r.status_code for r in attempts] == [403, 403, 403, 403]
    assert registration.utcnow() and api.get(
        f"{WINDOWS}/{draft}", headers=login(campus.open.email)).json()["status"] == "DRAFT"


def test_a_coordinator_cannot_create_a_round_for_another_department(
        api, login, campus):
    response = api.post(WINDOWS, json=payload(campus, code="X"),
                        headers=login(campus.open_cse.email))
    assert response.status_code == 403


def test_a_coordinator_cannot_create_a_round_for_a_family_they_do_not_run(
        api, login, campus):
    response = api.post(
        WINDOWS, headers=login(campus.open.email),
        json=payload(campus, code="PE1-X", component_type="PROGRAM_CORE_ELECTIVE"))
    assert response.status_code == 403


def test_the_core_elective_coordinator_runs_core_rounds_the_same_way(
        api, login, campus):
    headers = login(campus.core.email)
    created = api.post(WINDOWS, headers=headers, json=payload(
        campus, code="PE1-EARLY", title="Program Elective 1",
        component_type="PROGRAM_CORE_ELECTIVE", eligible_semesters=[4]))
    assert created.status_code == 201, created.text
    round_id = created.json()["id"]
    api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
             json={"offering_ids": [o.id for o in campus.offerings["PE1"]]})
    assert move(api, headers, round_id, "OPEN").json()["status"] == "OPEN"


# ── the Head of Department reads, and does not drive ───────────────────────
def test_the_hod_sees_every_round_of_their_department_read_only(
        api, login, campus, draft):
    headers = login(campus.hod.email)
    listed = api.get(WINDOWS, headers=headers)
    assert listed.status_code == 200
    assert [(w["code"], w["can_manage"]) for w in listed.json()] == [("OE1-EARLY", False)]
    assert api.get(f"{WINDOWS}/{draft}", headers=headers).json()["can_manage"] is False


def test_the_hod_cannot_change_a_round(api, login, campus, draft):
    headers = login(campus.hod.email)
    attempts = [
        api.post(WINDOWS, json=payload(campus, code="HOD-ROUND"), headers=headers),
        api.patch(f"{WINDOWS}/{draft}", json={"closes_at": IN_A_MONTH}, headers=headers),
        api.post(f"{WINDOWS}/{draft}/offerings", json={"offering_ids": []},
                 headers=headers),
        move(api, headers, draft, "OPEN"),
    ]
    assert [r.status_code for r in attempts] == [403, 403, 403, 403]


def test_the_hod_does_not_see_another_departments_rounds(api, login, campus, db):
    db.add(ElectiveRegistrationWindow(
        code="CSE-OE", title="CSE round", component_type="OPEN_ELECTIVE",
        department_id=campus.cse, status=RegistrationWindowStatus.DRAFT))
    db.flush()
    other = db.scalar(select(ElectiveRegistrationWindow).where(
        ElectiveRegistrationWindow.code == "CSE-OE"))

    headers = login(campus.hod.email)
    assert api.get(WINDOWS, headers=headers).json() == []
    assert api.get(f"{WINDOWS}/{other.id}", headers=headers).status_code == 403


def test_plain_faculty_cannot_see_rounds_at_all(api, login, world, campus, draft):
    headers = login(world.summer_ict.email)
    assert api.get(WINDOWS, headers=headers).status_code == 403
    assert api.get(f"{WINDOWS}/{draft}", headers=headers).status_code == 403


# ── a round that could not mean anything is refused ───────────────────────
def test_a_round_cannot_be_aimed_two_semesters_ahead(api, login, campus):
    """Semester II students cannot be asked to choose a Semester IV elective."""
    headers = login(campus.open.email)
    round_id = api.post(WINDOWS, headers=headers, json=payload(
        campus, eligible_semesters=[2])).json()["id"]
    response = api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
                        json={"offering_ids": [o.id for o in campus.offerings["OE1"]]})
    assert response.status_code == 422
    assert "Semester 3" in message(response) and "Semester 4" in message(response)


@pytest.mark.parametrize("semesters", [[3], [4], [3, 4]])
def test_a_round_may_be_for_the_semester_before_the_slot_or_the_slot_itself(
        api, login, campus, semesters):
    headers = login(campus.open.email)
    round_id = api.post(WINDOWS, headers=headers, json=payload(
        campus, eligible_semesters=semesters)).json()["id"]
    response = api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
                        json={"offering_ids": [o.id for o in campus.offerings["OE1"]]})
    assert response.status_code == 200, response.text


def test_the_student_semester_cannot_be_changed_to_one_the_slot_does_not_allow(
        api, login, campus, draft):
    response = api.patch(f"{WINDOWS}/{draft}", json={"eligible_semesters": [1]},
                         headers=login(campus.open.email))
    assert response.status_code == 422


def test_a_round_covers_one_elective_family(api, login, campus, draft):
    response = api.post(
        f"{WINDOWS}/{draft}/offerings", headers=login(campus.open.email),
        json={"offering_ids": [campus.offerings["PE1"][0].id]})
    assert response.status_code == 422
    assert "one elective family" in message(response)


def test_a_round_covers_the_slots_of_one_semester(api, login, campus, draft):
    mixed = [campus.offerings["OE1"][0].id, campus.offerings["OE3"][0].id]
    response = api.post(f"{WINDOWS}/{draft}/offerings", json={"offering_ids": mixed},
                        headers=login(campus.open.email))
    assert response.status_code == 422
    assert "one semester" in message(response)


def test_a_course_cannot_be_pulled_out_of_another_round(api, login, campus, live):
    """Attaching used to reassign silently, emptying a round students were
    already choosing in."""
    headers = login(campus.open.email)
    second = api.post(WINDOWS, json=payload(campus, code="OE1-SECOND"),
                      headers=headers).json()["id"]
    response = api.post(f"{WINDOWS}/{second}/offerings", headers=headers,
                        json={"offering_ids": [campus.offerings["OE1"][0].id]})
    assert response.status_code == 409
    assert "one round at a time" in message(response)
    assert api.get(f"{WINDOWS}/{live}", headers=headers).json()["offering_count"] == 3


def test_the_coordinator_is_offered_only_the_slots_of_their_own_family_and_department(
        api, login, campus, draft):
    slots = api.get("/api/v1/electives/admin/slots",
                    headers=login(campus.open.email)).json()
    assert {(s["code"], s["component_type"]) for s in slots} == {
        ("OE1", "OPEN_ELECTIVE"), ("OE3", "OPEN_ELECTIVE")}
    oe1 = next(s for s in slots if s["code"] == "OE1")
    assert len(oe1["offerings"]) == 3
    assert all(o["registration_window_id"] == draft for o in oe1["offerings"])

    core = api.get("/api/v1/electives/admin/slots",
                   headers=login(campus.core.email)).json()
    assert [s["code"] for s in core] == ["PE1"]
    assert api.get("/api/v1/electives/admin/slots",
                   headers=login(campus.open_cse.email)).json() == []
    assert api.get("/api/v1/electives/admin/slots",
                   headers=login(campus.hod.email)).status_code == 403


def test_a_round_with_no_courses_cannot_open(api, login, campus):
    headers = login(campus.open.email)
    round_id = api.post(WINDOWS, json=payload(campus), headers=headers).json()["id"]
    response = move(api, headers, round_id, "OPEN")
    assert response.status_code == 409
    assert "at least one course" in message(response)


def test_a_round_whose_deadline_has_passed_cannot_open(api, login, campus, draft, db):
    window = db.get(ElectiveRegistrationWindow, draft)
    window.closes_at = NOW - dt.timedelta(days=1)
    db.flush()
    response = move(api, login(campus.open.email), draft, "OPEN")
    assert response.status_code == 409
    assert "already passed" in message(response)


def test_a_round_with_no_programme_cannot_open(api, login, campus):
    headers = login(campus.open.email)
    round_id = api.post(WINDOWS, headers=headers, json=payload(
        campus, eligible_program_ids=[])).json()["id"]
    api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
             json={"offering_ids": [o.id for o in campus.offerings["OE1"]]})
    assert move(api, headers, round_id, "OPEN").status_code == 409


def test_a_live_rounds_deadline_cannot_be_moved_into_the_past(
        api, login, campus, live):
    """Stopping choice filling is the Lock button, with its own audit entry."""
    response = api.patch(f"{WINDOWS}/{live}", json={"closes_at": YESTERDAY},
                         headers=login(campus.open.email))
    assert response.status_code == 422
    assert "lock the round" in message(response)


# ── a round opens registration a semester early ───────────────────────────
def test_without_a_round_a_semester_three_student_cannot_reach_the_slot(
        api, login, world, campus):
    headers = login(world.student_a.email)
    assert workspace(api, headers, campus)["eligible"] is False
    refused = submit(api, headers, campus)
    assert refused.status_code == 409
    assert "opens in semester 4" in message(refused)


def test_a_draft_round_opens_nothing(api, login, world, campus, draft):
    headers = login(world.student_a.email)
    assert workspace(api, headers, campus)["eligible"] is False
    assert submit(api, headers, campus).status_code == 409


def test_an_open_round_lets_the_semester_before_fill_their_choices(
        api, login, world, campus, live, db):
    headers = login(world.student_a.email)
    before = workspace(api, headers, campus)
    assert before["eligible"] is True and before["window_open"] is True
    assert before["registration_state"] == "OPEN"
    assert before["window_title"] == "Open Elective 1 — for Semester IV"
    assert len(before["offerings"]) == 3

    saved = submit(api, headers, campus, count=2)
    assert saved.status_code == 200, saved.text
    assert workspace(api, headers, campus)["registration_state"] == "SUBMITTED"
    assert db.scalar(select(ElectivePreference.id).where(
        ElectivePreference.student_id == world.student_a.student.id)) is not None


def test_a_student_two_semesters_away_is_never_let_in(api, login, world, campus, live, db):
    world.student_a.student.current_semester = 2
    db.flush()
    headers = login(world.student_a.email)
    assert workspace(api, headers, campus)["eligible"] is False
    assert submit(api, headers, campus).status_code == 409


def test_a_student_the_round_is_not_aimed_at_is_not_let_in(api, login, world, campus, db):
    """Same semester, but the round is for another programme."""
    headers = login(campus.open.email)
    round_id = api.post(WINDOWS, headers=headers, json=payload(
        campus, eligible_program_ids=[world.programs["B.TECH-CE"].id])).json()["id"]
    api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
             json={"offering_ids": [o.id for o in campus.offerings["OE1"]]})
    assert move(api, headers, round_id, "OPEN").status_code == 200

    assert submit(api, login(world.student_a.email), campus).status_code == 409


def test_locking_the_round_stops_early_choice_filling(api, login, world, campus, live):
    assert move(api, login(campus.open.email), live, "LOCKED").status_code == 200

    headers = login(world.student_a.email)
    state = workspace(api, headers, campus)
    assert state["window_open"] is False and state["registration_state"] == "LOCKED"
    assert submit(api, headers, campus).status_code == 409


def test_the_deadline_stops_early_choice_filling_even_if_nobody_locks(
        api, login, world, campus, live, db):
    window = db.get(ElectiveRegistrationWindow, live)
    window.closes_at = NOW - dt.timedelta(minutes=5)
    db.flush()

    refused = submit(api, login(world.student_a.email), campus)
    assert refused.status_code == 409
    assert "deadline passed" in message(refused)


def test_a_round_cannot_open_a_slot_from_someone_elses_curriculum(
        db, world, campus, live, make_curriculum):
    """The early path is for the student's own governing curriculum only."""
    other = make_curriculum("B.TECH-CE", "2024-28", 2024, None,
                            [(4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "ANY")])
    foreign = db.scalar(select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == other.id))
    campus.offerings["OE1"][0].curriculum_component_id = foreign.id
    db.flush()

    student = world.student_a.student
    assert registration.access_for(db, student, campus.components["OE1"]).eligible
    assert not registration.access_for(db, student, foreign).eligible


# ── the student's own screens follow the round ────────────────────────────
def sections(api, headers):
    return set(api.get("/api/v1/auth/me", headers=headers).json()["student"]["visible_sections"])


def dashboard(api, headers):
    body = api.get("/api/v1/dashboard/student", headers=headers).json()
    pending = next(s for s in body["stats"] if s["key"] == "pending_electives")
    return pending, [i for i in body["action_items"] if i["kind"] == "elective"]


def test_the_menu_offers_open_electives_only_once_a_round_reaches_the_student(
        api, login, world, campus, draft):
    headers = login(world.student_a.email)
    assert "open_electives" not in sections(api, headers)      # draft is private

    move(api, login(campus.open.email), draft, "OPEN")
    assert "open_electives" in sections(api, headers)
    assert "core_electives" not in sections(api, headers)

    move(api, login(campus.open.email), draft, "LOCKED")
    assert "open_electives" in sections(api, headers)          # still theirs to read


def test_the_dashboard_asks_the_student_to_choose_and_stops_once_they_have(
        api, login, world, campus, live):
    headers = login(world.student_a.email)
    pending, items = dashboard(api, headers)
    assert pending["value"] == 1
    assert pending["link"] == f"/academics/open-electives/{campus.components['OE1'].id}"
    assert [i["title"] for i in items] == [
        "Open Elective 1 — choice filling open for Semester 4"]
    assert items[0]["due_at"] is not None

    submit(api, headers, campus)
    pending, items = dashboard(api, headers)
    assert pending["value"] == 0 and items == []


def test_the_dashboard_says_nothing_about_a_round_for_someone_else(
        api, login, world, campus, live):
    pending, items = dashboard(api, login(world.student_b.email))   # Semester V
    assert items == [] or all("Open Elective 1" not in i["title"] for i in items)


def test_the_slot_reads_as_unlocked_in_the_students_elective_list(
        api, login, world, campus, live):
    headers = login(world.student_a.email)
    rows = {c["code"]: c for c in api.get(
        "/api/v1/electives/components", headers=headers).json()}
    # The card follows the round: it used to say "Not started" while the
    # dashboard and the notification said choice filling had opened.
    assert rows["OE1"]["is_unlocked"] is True
    assert rows["OE1"]["status_label"] == "Choice filling open"
    assert rows["OE3"]["is_unlocked"] is False and rows["OE3"]["status_label"] == "Upcoming"


# ── students are told ─────────────────────────────────────────────────────
def test_opening_a_round_tells_exactly_the_students_it_covers(
        api, login, world, campus, draft, db):
    assert notices(db, world.student_a) == []          # a draft tells nobody
    move(api, login(campus.open.email), draft, "OPEN")

    assert notices(db, world.student_a) == [
        "Open Elective 1 — for Semester IV: choice filling is open"]
    assert notices(db, world.student_b) == []          # Semester V, not covered


def test_moving_a_live_rounds_deadline_tells_the_students(
        api, login, world, campus, live, db):
    api.patch(f"{WINDOWS}/{live}", json={"closes_at": IN_A_MONTH},
              headers=login(campus.open.email))
    assert notices(db, world.student_a)[-1] == (
        "Open Elective 1 — for Semester IV: deadline changed")


def test_editing_a_draft_or_an_unrelated_field_tells_nobody(
        api, login, world, campus, draft, live, db):
    before = len(notices(db, world.student_a))
    api.patch(f"{WINDOWS}/{live}", json={"notes": "Timetable meeting on Friday."},
              headers=login(campus.open.email))
    assert len(notices(db, world.student_a)) == before


def test_reopening_a_locked_round_tells_the_students_again(
        api, login, world, campus, live, db):
    headers = login(campus.open.email)
    move(api, headers, live, "LOCKED")
    move(api, headers, live, "OPEN")
    assert notices(db, world.student_a)[-1].endswith("choice filling has reopened")


# ── the allocation screens answer to the same scope ───────────────────────
# These routes used to ask only for the coarse `electives:manage` permission:
# an appointed coordinator was refused on their own slot, while a department
# administrator could read and allocate another department's students.
ADMIN = "/api/v1/electives/admin"


def allocation_reads(api, headers, component_id):
    return [
        api.get(f"{ADMIN}/preferences", params={"component_id": component_id},
                headers=headers).status_code,
        api.get(f"{ADMIN}/allocations", params={"component_id": component_id},
                headers=headers).status_code,
        api.get(f"{ADMIN}/viability", params={"component_id": component_id},
                headers=headers).status_code,
    ]


def test_a_coordinator_can_work_on_the_slots_of_their_own_family(api, login, campus):
    slot = campus.components["OE1"].id
    assert allocation_reads(api, login(campus.open.email), slot) == [200, 200, 200]
    assert api.get("/api/v1/electives/strategies",
                   headers=login(campus.open.email)).status_code == 200


@pytest.mark.parametrize("who,slot", [
    ("core", "OE1"),        # same department, other family
    ("open", "PE1"),        # same department, other family, the other way round
    ("open_cse", "OE1"),    # same family, other department
])
def test_allocation_screens_refuse_another_family_or_department(
        api, login, campus, who, slot):
    headers = login(getattr(campus, who).email)
    component_id = campus.components[slot].id
    assert allocation_reads(api, headers, component_id) == [403, 403, 403]

    run = api.post(f"{ADMIN}/allocate", headers=headers, json={
        "curriculum_component_id": component_id, "strategy": "preference_order",
        "dry_run": True})
    assert run.status_code == 403
    sections = api.get(f"{ADMIN}/offerings/{campus.offerings[slot][0].id}/sections",
                       headers=headers)
    assert sections.status_code == 403


def test_a_department_admin_is_held_to_their_own_department(
        api, login, world, campus, db, make_curriculum):
    """Holding `electives:manage` is not a pass over every department."""
    from app.models.enums import Role
    from app.models.identity import UserRole

    db.add(UserRole(user_id=world.summer_ict.user.id, role=Role.DEPARTMENT_ADMIN))
    other = make_curriculum("B.TECH-CE", "2024-28", 2024, None,
                            [(4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "ANY")])
    db.flush()
    cse_slot = db.scalar(select(CurriculumComponent.id).where(
        CurriculumComponent.curriculum_id == other.id))

    headers = login(world.summer_ict.email)
    assert allocation_reads(api, headers, campus.components["OE1"].id) == [200, 200, 200]
    assert allocation_reads(api, headers, cse_slot) == [403, 403, 403]


def test_the_hod_and_plain_faculty_cannot_reach_the_allocation_screens(
        api, login, world, campus):
    slot = campus.components["OE1"].id
    assert allocation_reads(api, login(campus.hod.email), slot) == [403, 403, 403]
    assert allocation_reads(api, login(world.summer_ict.email), slot) == [403, 403, 403]


def test_an_unknown_slot_is_not_found_rather_than_empty(api, login, campus):
    assert allocation_reads(api, login(campus.open.email), 999_999) == [404, 404, 404]


# ── Core Electives: the same flow, their own coordinator ─────────────────
@pytest.fixture
def core_round(api, login, campus):
    """Program Elective 1 (Semester V) opened to Semester IV students."""
    headers = login(campus.core.email)
    round_id = api.post(WINDOWS, headers=headers, json=payload(
        campus, code="PE1-EARLY", title="Program Elective 1 — for Semester V",
        component_type="PROGRAM_CORE_ELECTIVE", eligible_semesters=[4])).json()["id"]
    api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
             json={"offering_ids": [o.id for o in campus.offerings["PE1"]]})
    assert move(api, headers, round_id, "OPEN").status_code == 200
    return round_id


def test_a_core_elective_round_lets_the_semester_before_choose(
        api, login, world, campus, core_round, db):
    world.student_a.student.current_semester = 4
    db.flush()
    headers = login(world.student_a.email)

    state = workspace(api, headers, campus, slot="PE1")
    assert state["eligible"] is True and state["registration_state"] == "OPEN"
    assert submit(api, headers, campus, slot="PE1").status_code == 200

    pending, items = dashboard(api, headers)
    assert all("Program Elective 1" not in i["title"] for i in items)   # submitted


def test_a_core_round_sends_the_student_to_the_core_elective_screen(
        api, login, world, campus, core_round, db):
    world.student_a.student.current_semester = 4
    db.flush()
    headers = login(world.student_a.email)

    _pending, items = dashboard(api, headers)
    link = next(i["link"] for i in items if "Program Elective 1" in i["title"])
    assert link == f"/academics/core-electives/{campus.components['PE1'].id}"
    assert "core_electives" in sections(api, headers)


def test_a_core_round_opens_nothing_in_the_open_elective_family(
        api, login, world, campus, core_round, db):
    """One round, one family: the Semester IV student's *Open* Elective is
    theirs anyway (it sits in Semester IV), but Open Elective 3 stays shut."""
    world.student_a.student.current_semester = 4
    db.flush()
    headers = login(world.student_a.email)
    assert workspace(api, headers, campus, slot="OE3")["eligible"] is False


def test_the_open_elective_coordinator_cannot_touch_the_core_round(
        api, login, campus, core_round):
    headers = login(campus.open.email)
    assert api.get(f"{WINDOWS}/{core_round}", headers=headers).status_code == 403
    assert move(api, headers, core_round, "LOCKED").status_code == 403


# ── two cohorts, one slot ─────────────────────────────────────────────────
def test_each_cohort_chooses_only_from_its_own_rounds_courses(
        api, login, world, campus, db):
    """Semester IV is choosing in its own round while Semester III chooses
    ahead for next year. A course belongs to one round, and a student sees — and
    may rank — only the courses of the round that covers them."""
    headers = login(campus.open.email)
    ours, theirs = campus.offerings["OE1"][:2], campus.offerings["OE1"][2:]

    def open_round(code, semester, offerings):
        round_id = api.post(WINDOWS, headers=headers, json=payload(
            campus, code=code, eligible_semesters=[semester])).json()["id"]
        api.post(f"{WINDOWS}/{round_id}/offerings", headers=headers,
                 json={"offering_ids": [o.id for o in offerings]})
        assert move(api, headers, round_id, "OPEN").status_code == 200

    open_round("OE1-AHEAD", 3, ours)       # student_a, Semester III
    open_round("OE1-NOW", 4, theirs)       # student_b, moved to Semester IV
    world.student_b.student.current_semester = 4
    db.flush()

    ahead = workspace(api, login(world.student_a.email), campus)
    now = workspace(api, login(world.student_b.email), campus)
    assert {o["id"] for o in ahead["offerings"]} == {o.id for o in ours}
    assert {o["id"] for o in now["offerings"]} == {o.id for o in theirs}

    # Ranking a course from the other cohort's round is refused.
    stolen = {"curriculum_component_id": campus.components["OE1"].id,
              "preferences": [{"course_offering_id": theirs[0].id, "preference_order": 1}]}
    refused = api.post("/api/v1/electives/preferences", json=stolen,
                       headers=login(world.student_a.email))
    assert refused.status_code == 422


def test_a_student_no_round_covers_does_not_see_another_cohorts_courses(
        api, login, world, campus, live, db):
    """`live` is aimed at Semester III. A Semester IV student has the slot by
    right of the curriculum, but those courses are the other cohort's."""
    world.student_b.student.current_semester = 4
    db.flush()
    state = workspace(api, login(world.student_b.email), campus)
    assert state["eligible"] is True
    assert state["offerings"] == []
