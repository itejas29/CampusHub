"""NPTEL / NCC rounds — the Semester V Open Elective, as the ICT department runs it.

From the coordinator's emails to the 2024 batch and the department's answers:
an approved list of 12-week NPTEL courses (3 credits each), one course or NCC
per student with no limit per course, a certificate at the end — or a report
that the student did not pass — and two semesters to clear it before it is a
backlog. The portal does not track NPTEL portal registration.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile

import pytest
from sqlalchemy import select

from app.models.academics import (
    Course, CurriculumComponent, MoocRegistration, MoocRound, MoocRoundOutcome,
)
from app.models.engagement import Notification
from app.models.enums import (
    AssignedRole, CoordinationDomain, MoocOutcome, MoocStatus, VerificationStatus,
)
from app.models.identity import FacultyRoleAssignment, Student
from app.services import mooc_rounds, scope

ROUNDS = "/api/v1/mooc/admin/rounds"
NOW = dt.datetime.now(dt.timezone.utc)
NEXT_WEEK = (NOW + dt.timedelta(days=7)).isoformat()
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

#: Four rows as the department's sheet has them, one of them not 12 weeks.
SHEET = [
    ["S. No.", "Course ID", "Discipline", "Course Name", "SME Name", "Institute",
     "Coordinating Institute", "Duration", "NPTEL URL"],
    ["1", "noc26-ee159", "Electronics and Communication Engineering",
     "5G Wireless Standard Design", "Prof. Rohit Budhiraja", "IIT Kanpur", "IIT Kanpur",
     "12 Weeks", "https://nptel.ac.in/courses/117104484"],
    ["2", "noc26-cs171", "Computer Science and Engineering",
     "Introduction to Large Language Models (LLMs)",
     "Prof. Tanmoy Chakraborty, Prof. Soumen Chakraborti", "IIT Delhi IIT Bombay",
     "IIT Delhi", "12 Weeks", "https://nptel.ac.in/courses/106102576"],
    ["3", "noc26-cs157", "Computer Science and Engineering", "Ethical Hacking",
     "Prof. Indranil Sengupta", "IIT Kharagpur", "IIT Kharagpur", "12 Weeks",
     "https://nptel.ac.in/courses/106105217"],
    ["4", "noc26-cs999", "Computer Science and Engineering", "A Short Course",
     "Prof. X", "IIT Y", "IIT Y", "8 Weeks", "https://nptel.ac.in/courses/1"],
]


def xlsx(rows: list[list[str]]) -> bytes:
    """A minimal workbook, the way Excel stores one: shared strings + sheet1."""
    strings: list[str] = []
    def ref(text):
        if text not in strings:
            strings.append(text)
        return strings.index(text)
    cols = "ABCDEFGHIJ"
    sheet_rows = []
    for r, row in enumerate(rows, start=1):
        cells = "".join(f'<c r="{cols[c]}{r}" t="s"><v>{ref(v)}</v></c>'
                        for c, v in enumerate(row))
        sheet_rows.append(f'<row r="{r}">{cells}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    shared = "".join(f"<si><t>{s.replace('&', '&amp;')}</t></si>" for s in strings)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{shared}</sst>")
        z.writestr("xl/worksheets/sheet1.xml",
                   f"<worksheet {ns}><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>")
    return buf.getvalue()


@pytest.fixture
def ict(db, world, make_curriculum, make_student):
    """ICT's 2024-28 MOOC slot in Semester V, its NPTEL coordinator, and a
    Semester V cohort (two who can sign in, three who cannot)."""
    curriculum = make_curriculum("B.TECH-ICT", "2024-28", 2024, None, [
        (5, "OE2-MOOC", "Open Elective 2 (NPTEL / SWAYAM / MOOC)", "MOOC", "ANY"),
    ])
    slot = db.scalar(select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == curriculum.id))
    for account, dept in ((world.cssi_ict, "ICT"), (world.summer_cse, "CSE")):
        db.add(FacultyRoleAssignment(
            faculty_id=account.faculty.id, role=AssignedRole.COORDINATOR,
            domain=CoordinationDomain.MOOC, department_id=world.departments[dept].id,
            is_active=True, assigned_at=NOW))
    db.flush()
    db.refresh(world.cssi_ict.faculty)
    db.refresh(world.summer_cse.faculty)
    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)
    db.query(Student).update({Student.current_semester: 1})
    world.student_a.student.current_semester = 5
    world.student_b.student.current_semester = 5
    others = [make_student("B.TECH-ICT", 2024, semester=5) for _ in range(3)]
    sem4 = make_student("B.TECH-ICT", 2025, semester=4)
    db.flush()
    return type("Ict", (), {
        "slot": slot, "coord": world.cssi_ict, "other_dept": world.summer_cse,
        "hod": world.plain, "a": world.student_a, "b": world.student_b,
        "others": others, "sem4": sem4,
        "cohort": [world.student_a.student, world.student_b.student, *others],
    })


@pytest.fixture
def coord(login, ict):
    return login(ict.coord.email)


def make_round(api, headers, ict, **extra):
    body = {"title": "NPTEL / NCC — Semester V (2026-27)",
            "message": "Choose one NPTEL course from the list, or NCC.",
            "curriculum_component_id": ict.slot.id, "eligible_semesters": [5],
            "closes_at": NEXT_WEEK, "platform_deadline": "2026-07-27"}
    body.update(extra)
    response = api.post(ROUNDS, headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def import_sheet(api, headers, rid, rows=SHEET, name="list.xlsx", content=None):
    return api.post(f"{ROUNDS}/{rid}/courses/import", headers=headers,
                    files={"file": (name, content or xlsx(rows),
                                    "application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet")})


@pytest.fixture
def live(api, coord, ict):
    rid = make_round(api, coord, ict)
    assert import_sheet(api, coord, rid).status_code == 200
    opened = api.post(f"{ROUNDS}/{rid}/status", params={"target": "OPEN"}, headers=coord)
    assert opened.status_code == 200, opened.text
    return rid


def courses(db, rid):
    return {c.code: c for c in mooc_rounds.approved_courses(db, db.get(MoocRound, rid))}


def mine(api, login, who):
    return api.get("/api/v1/mooc/rounds/mine", headers=login(who.email)).json()


def choose(api, login, who, rid, option="NPTEL", course_id=None):
    return api.post(f"/api/v1/mooc/rounds/{rid}/choice", headers=login(who.email),
                    json={"option": option, "course_id": course_id})


def err(response):
    return response.json()["error"]["message"]


# ── the approved list ──────────────────────────────────────────────────────
def test_the_departments_sheet_is_read_and_only_12_week_courses_listed(
        api, db, coord, ict):
    rid = make_round(api, coord, ict)
    response = import_sheet(api, coord, rid)
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["added"]) == ["noc26-cs157", "noc26-cs171", "noc26-ee159"]
    assert body["skipped"][0]["course"] == "noc26-cs999"
    assert "12-week" in body["skipped"][0]["reason"]
    llm = courses(db, rid)["noc26-cs171"]
    assert llm.title == "Introduction to Large Language Models (LLMs)"
    assert float(llm.credits) == 3 and llm.duration_weeks == 12
    assert llm.provider_details["instructors"].startswith("Prof. Tanmoy Chakraborty")
    assert llm.provider_details["coordinating_institute"] == "IIT Delhi"
    assert llm.provider_url == "https://nptel.ac.in/courses/106102576"


def test_a_csv_of_the_list_is_read_too(api, db, coord, ict):
    rid = make_round(api, coord, ict)
    buf = io.StringIO()
    csv.writer(buf).writerows(SHEET[:2])
    response = import_sheet(api, coord, rid, name="list.csv",
                            content=buf.getvalue().encode())
    assert response.status_code == 200, response.text
    assert response.json()["added"] == ["noc26-ee159"]


def test_a_sheet_without_course_columns_is_refused(api, coord, ict):
    rid = make_round(api, coord, ict)
    response = import_sheet(api, coord, rid, rows=[["Name", "Marks"], ["x", "1"]])
    assert response.status_code == 422
    assert "Course ID" in err(response)


def test_importing_again_updates_rather_than_duplicates(api, db, coord, ict):
    rid = make_round(api, coord, ict)
    import_sheet(api, coord, rid)
    again = import_sheet(api, coord, rid).json()
    assert sorted(again["already_listed"]) == ["noc26-cs157", "noc26-cs171", "noc26-ee159"]
    assert db.query(Course).filter(Course.code == "noc26-cs171").count() == 1


def test_a_course_is_added_by_hand_and_must_be_12_weeks(api, coord, ict):
    rid = make_round(api, coord, ict)
    url = f"{ROUNDS}/{rid}/courses"
    short = api.post(url, headers=coord, json={"code": "noc26-x1", "title": "X", "weeks": 4})
    assert short.status_code == 422
    ok = api.post(url, headers=coord, json={"code": "noc26-x1", "title": "X", "weeks": 12})
    assert ok.status_code == 201 and ok.json()["credits"] == 3
    again = api.post(url, headers=coord, json={"code": "noc26-x1", "title": "X", "weeks": 12})
    assert again.status_code == 409


def test_the_next_semesters_round_can_copy_the_list(api, db, coord, ict, live):
    rid = make_round(api, coord, ict, title="Semester VI round", copy_list_from=live)
    assert set(courses(db, rid)) == set(courses(db, live))


# ── who may run it ─────────────────────────────────────────────────────────
def test_another_departments_coordinator_cannot_create_or_open(api, login, ict, live):
    other = login(ict.other_dept.email)
    assert api.post(ROUNDS, headers=other, json={
        "title": "x", "curriculum_component_id": ict.slot.id}).status_code == 403
    assert api.post(f"{ROUNDS}/{live}/status", params={"target": "LOCKED"},
                    headers=other).status_code == 403


def test_the_hod_sees_the_round_but_changes_nothing(api, login, ict, live):
    hod = login(ict.hod.email)
    assert [r["id"] for r in api.get(ROUNDS, headers=hod).json()] == [live]
    assert api.get(f"{ROUNDS}/{live}/students", headers=hod).status_code == 200
    assert api.post(f"{ROUNDS}/{live}/status", params={"target": "LOCKED"},
                    headers=hod).status_code == 403


def test_opening_needs_a_list_and_a_future_deadline(api, coord, ict):
    rid = make_round(api, coord, ict)
    response = api.post(f"{ROUNDS}/{rid}/status", params={"target": "OPEN"}, headers=coord)
    assert response.status_code == 409 and "course list" in err(response)


def test_opening_tells_the_semester_v_cohort_only(api, db, ict, live):
    told = {n.user_id for n in db.scalars(select(Notification).where(
        Notification.title.like("%choose your NPTEL course or NCC%")))}
    assert told == {s.user_id for s in ict.cohort}
    assert ict.sem4.user_id not in told


# ── the student chooses ────────────────────────────────────────────────────
def test_the_student_sees_the_round_and_the_list(api, login, ict, live):
    view = mine(api, login, ict.a)
    assert view["round"]["can_choose"] is True
    assert len(view["round"]["courses"]) == 3
    assert view["round"]["platform_deadline"] == "2026-07-27"
    assert view["standing"] is None


def test_a_student_picks_a_listed_course(api, db, login, ict, live):
    llm = courses(db, live)["noc26-cs171"]
    response = choose(api, login, ict.a, live, course_id=llm.id)
    assert response.status_code == 200, response.text
    assert response.json()["choice"]["course"]["code"] == "noc26-cs171"


def test_a_course_off_the_list_is_refused(api, db, login, ict, live):
    stray = Course(code="noc26-zz1", title="Not approved", credits=3)
    db.add(stray)
    db.flush()
    response = choose(api, login, ict.a, live, course_id=stray.id)
    assert response.status_code == 422 and "approved list" in err(response)


def test_ncc_needs_no_course(api, login, ict, live):
    ok = choose(api, login, ict.a, live, option="NCC")
    assert ok.status_code == 200 and ok.json()["choice"]["option"] == "NCC"
    assert ok.json()["choice"]["course"] is None
    bad = choose(api, login, ict.b, live, option="NCC", course_id=1)
    assert bad.status_code == 422


def test_the_choice_can_change_until_the_deadline(api, db, login, ict, live):
    llm = courses(db, live)["noc26-cs171"]
    choose(api, login, ict.a, live, option="NCC")
    changed = choose(api, login, ict.a, live, course_id=llm.id)
    assert changed.json()["choice"]["option"] == "NPTEL"
    assert db.query(MoocRegistration).filter(
        MoocRegistration.student_id == ict.a.student.id).count() == 1


def test_there_is_no_limit_per_course(api, db, login, ict, live):
    llm = courses(db, live)["noc26-cs171"]
    window = db.get(MoocRound, live)
    for student in ict.cohort:
        mooc_rounds.choose(db, window, student, option=mooc_rounds.MoocOption.NPTEL,
                           course_id=llm.id)
    db.flush()
    assert db.query(MoocRegistration).filter(
        MoocRegistration.course_id == llm.id).count() == 5


def test_choosing_stops_when_the_round_is_locked(api, coord, login, ict, live):
    api.post(f"{ROUNDS}/{live}/status", params={"target": "LOCKED"}, headers=coord)
    assert choose(api, login, ict.a, live, option="NCC").status_code == 409


def test_a_student_the_round_is_not_for_cannot_choose(api, db, login, ict, live):
    ict.a.student.current_semester = 3
    db.flush()
    assert choose(api, login, ict.a, live, option="NCC").status_code == 409


def test_the_old_free_registration_gives_way_to_the_round(api, db, login, ict, live):
    from app.models.academics import CourseOffering
    from app.models.identity import Semester
    response = api.post("/api/v1/mooc/register", headers=login(ict.a.email),
                        json={"course_offering_id": 999999})
    assert response.status_code == 409
    assert "round" in err(response)


# ── results ────────────────────────────────────────────────────────────────
def upload(api, login, who, reg_id):
    return api.post(f"/api/v1/mooc/{reg_id}/certificate", headers=login(who.email),
                    files={"file": ("certificate.pdf", PDF, "application/pdf")})


def chosen_reg(db, who, rid):
    return db.scalar(select(MoocRegistration).where(
        MoocRegistration.mooc_round_id == rid,
        MoocRegistration.student_id == who.student.id))


def test_an_ncc_certificate_is_submitted_and_verified(api, db, login, coord, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    reg = chosen_reg(db, ict.a, live)
    assert upload(api, login, ict.a, reg.id).status_code == 200
    queue = api.get("/api/v1/mooc/admin/registrations", headers=coord).json()
    assert any(r["id"] == reg.id and r["course_code"] == "NCC" for r in queue)
    verified = api.post(f"/api/v1/mooc/admin/{reg.id}/verify", headers=coord,
                        json={"verification_status": "VERIFIED"})
    assert verified.status_code == 200, verified.text
    assert mine(api, login, ict.a)["standing"] == "CLEARED"


def test_a_student_reports_they_did_not_pass(api, db, login, ict, live):
    choose(api, login, ict.a, live, course_id=courses(db, live)["noc26-cs157"].id)
    reg = chosen_reg(db, ict.a, live)
    response = api.post(f"/api/v1/mooc/{reg.id}/failed", headers=login(ict.a.email))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "FAILED"


def test_a_certificate_fixes_the_choice(api, db, login, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    upload(api, login, ict.a, chosen_reg(db, ict.a, live).id)
    response = choose(api, login, ict.a, live, course_id=courses(db, live)["noc26-cs157"].id)
    assert response.status_code == 409


# ── closing the semester, carry-over, backlog ──────────────────────────────
def lock(api, coord, rid):
    assert api.post(f"{ROUNDS}/{rid}/status", params={"target": "LOCKED"},
                    headers=coord).status_code == 200


def close(api, coord, rid, force=False):
    return api.post(f"{ROUNDS}/{rid}/close", headers=coord, json={"force": force})


def test_closing_needs_the_round_locked(api, coord, live):
    assert close(api, coord, live).status_code == 409


def test_a_certificate_waiting_for_verification_holds_the_close(
        api, db, login, coord, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    upload(api, login, ict.a, chosen_reg(db, ict.a, live).id)
    lock(api, coord, live)
    held = close(api, coord, live)
    assert held.status_code == 409 and "waiting for verification" in err(held)
    assert close(api, coord, live, force=True).status_code == 200


def test_closing_records_cleared_and_carried_over(api, db, login, coord, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    reg = chosen_reg(db, ict.a, live)
    upload(api, login, ict.a, reg.id)
    api.post(f"/api/v1/mooc/admin/{reg.id}/verify", headers=coord,
             json={"verification_status": "VERIFIED"})
    choose(api, login, ict.b, live, course_id=courses(db, live)["noc26-cs157"].id)
    api.post(f"/api/v1/mooc/{chosen_reg(db, ict.b, live).id}/failed",
             headers=login(ict.b.email))
    lock(api, coord, live)
    result = close(api, coord, live)
    assert result.status_code == 200, result.text
    assert result.json() == {"cleared": 1, "carried_over": 4, "backlog": 0,
                             "awaiting_verification": 0}
    outcomes = {o.student_id: o.outcome for o in db.scalars(select(MoocRoundOutcome))}
    assert outcomes[ict.a.student.id] == MoocOutcome.CLEARED
    assert outcomes[ict.b.student.id] == MoocOutcome.CARRIED_OVER
    told = {n.user_id for n in db.scalars(select(Notification).where(
        Notification.title.like("%carried over%")))}
    assert ict.b.user.id in told and ict.a.user.id not in told


@pytest.fixture
def carried(api, db, login, coord, ict, live):
    """Semester V closed with everyone carried over; the cohort is now in VI."""
    lock(api, coord, live)
    assert close(api, coord, live).status_code == 200
    for student in ict.cohort:
        student.current_semester = 6
    db.flush()
    return live


def test_a_carried_over_student_is_in_the_next_semesters_round(
        api, db, login, coord, ict, carried):
    nxt = make_round(api, coord, ict, title="Semester VI round", copy_list_from=carried)
    api.post(f"{ROUNDS}/{nxt}/status", params={"target": "OPEN"}, headers=coord)
    view = mine(api, login, ict.a)
    assert view["standing"] == "CARRIED_OVER"
    assert view["round"]["id"] == nxt and view["round"]["carry_over"] is True
    roster = {r["student_id"]: r for r in api.get(f"{ROUNDS}/{nxt}/students",
                                                  headers=coord).json()}
    assert roster[ict.a.student.id]["carry_over"] is True


def test_carrying_over_a_student_may_switch_to_ncc(api, db, login, coord, ict, carried):
    nxt = make_round(api, coord, ict, title="Semester VI round", copy_list_from=carried)
    api.post(f"{ROUNDS}/{nxt}/status", params={"target": "OPEN"}, headers=coord)
    assert choose(api, login, ict.a, nxt, option="NCC").status_code == 200


def test_not_cleared_in_the_second_semester_is_a_backlog(
        api, db, login, coord, ict, carried):
    nxt = make_round(api, coord, ict, title="Semester VI round", copy_list_from=carried)
    api.post(f"{ROUNDS}/{nxt}/status", params={"target": "OPEN"}, headers=coord)
    lock(api, coord, nxt)
    result = close(api, coord, nxt).json()
    assert result["backlog"] == 5 and result["carried_over"] == 0
    assert mine(api, login, ict.a)["standing"] == "BACKLOG"
    # A third round never picks them up again.
    third = make_round(api, coord, ict, title="Later", eligible_semesters=[6])
    assert mooc_rounds.covered_students(db, db.get(MoocRound, third)) == []


def test_a_cleared_student_is_not_asked_again(api, db, login, coord, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    reg = chosen_reg(db, ict.a, live)
    upload(api, login, ict.a, reg.id)
    api.post(f"/api/v1/mooc/admin/{reg.id}/verify", headers=coord,
             json={"verification_status": "VERIFIED"})
    lock(api, coord, live)
    close(api, coord, live)
    ict.a.student.current_semester = 6
    db.flush()
    nxt = make_round(api, coord, ict, eligible_semesters=[6])
    ids = {c.student.id for c in mooc_rounds.covered_students(db, db.get(MoocRound, nxt))}
    assert ict.a.student.id not in ids


# ── the coordinator's tools ────────────────────────────────────────────────
def test_a_reminder_goes_only_to_those_who_have_not_chosen(
        api, db, login, coord, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    db.query(Notification).delete()
    db.flush()
    response = api.post(f"{ROUNDS}/{live}/remind", headers=coord)
    assert response.json()["notified"] == 4
    told = {n.user_id for n in db.scalars(select(Notification))}
    assert ict.a.user.id not in told and ict.b.user.id in told


def test_the_export_lists_every_student_and_their_choice(api, db, login, coord, ict, live):
    choose(api, login, ict.a, live, option="NCC")
    response = api.get(f"{ROUNDS}/{live}/export", headers=coord)
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][:5] == ["Roll number", "Name", "Semester", "Carry-over", "Choice"]
    assert len(rows) == 1 + 5
    assert any(r[0] == ict.a.student.roll_number and r[4] == "NCC" for r in rows)


def test_a_course_someone_chose_stays_on_the_list(api, db, login, coord, ict, live):
    course = courses(db, live)["noc26-cs157"]
    choose(api, login, ict.a, live, course_id=course.id)
    response = api.delete(f"{ROUNDS}/{live}/courses/{course.id}", headers=coord)
    assert response.status_code == 409


def test_extending_the_deadline_tells_the_students(api, db, coord, ict, live):
    db.query(Notification).delete()
    db.flush()
    later = (NOW + dt.timedelta(days=12)).isoformat()
    assert api.patch(f"{ROUNDS}/{live}", headers=coord,
                     json={"closes_at": later}).status_code == 200
    assert len(db.scalars(select(Notification).where(
        Notification.title.like("%deadline extended%"))).all()) == 5


def test_the_dashboard_asks_the_student_to_choose(api, login, ict, live):
    items = api.get("/api/v1/dashboard/student", headers=login(ict.a.email)).json()
    titles = " | ".join(i["title"] for i in items["action_items"])
    assert "choose an NPTEL course or NCC" in titles


def test_the_dashboard_reminds_a_carried_over_student(api, db, login, coord, ict, carried):
    nxt = make_round(api, coord, ict, title="Semester VI round", copy_list_from=carried)
    api.post(f"{ROUNDS}/{nxt}/status", params={"target": "OPEN"}, headers=coord)
    items = api.get("/api/v1/dashboard/student", headers=login(ict.a.email)).json()
    assert any("carried over" in i["title"] for i in items["action_items"])
