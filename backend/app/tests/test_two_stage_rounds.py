"""Two-stage elective rounds, as the ICT department runs Semester VII.

Guidelines and Procedure for Elective Course Offering, B.Tech ICT Semester 7:
an interest round identifies the most wanted subjects, the coordinator
shortlists, and a final round has each student take the subjects they will
study. A subject runs only with enough students; the department places anyone
whose subject was withdrawn, and anyone who did not submit.

Every number is the coordinator's — how many to tick, the minimum, the section
size — because the department changes them year to year. These tests pin the
flow with deliberately unusual numbers so nothing can quietly assume 4, 3 or 48.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.academics import (
    Course, CourseOffering, CurriculumComponent, ElectiveAllocation,
    ElectiveRegistrationWindow, ElectiveRoundChoice,
)
from app.models.engagement import Notification
from app.models.enums import (
    AssignedRole, CoordinationDomain, OfferingStatus, RegistrationWindowStatus,
    RoundStage, SemesterTerm,
)
from app.models.identity import AcademicYear, FacultyRoleAssignment, Semester, Student
from app.services import registration, scope, two_stage

WINDOWS = "/api/v1/electives/admin/windows"
NOW = dt.datetime.now(dt.timezone.utc)
NEXT_WEEK = (NOW + dt.timedelta(days=7)).isoformat()
IN_TWO_WEEKS = (NOW + dt.timedelta(days=14)).isoformat()
SUBJECTS = ["NLP", "BDA", "CV", "EFC", "ISA", "RTOS", "SSP", "SEPM"]


@pytest.fixture
def sem7(db, world, make_curriculum, make_student):
    """ICT Semester VII: two Program Elective slots sharing one basket of eight
    subjects, a Core Elective coordinator, and a Semester VI cohort of six."""
    curriculum = make_curriculum("B.TECH-ICT", "2024-28", 2024, None, [
        (7, "PE4", "Program Elective 4", "PROGRAM_CORE_ELECTIVE", "ANY"),
        (7, "PE5", "Program Elective 5", "PROGRAM_CORE_ELECTIVE", "ANY"),
        (5, "PE1", "Program Elective 1", "PROGRAM_CORE_ELECTIVE", "ANY"),
    ])
    slots = {c.code: c for c in db.scalars(select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == curriculum.id))}
    year = AcademicYear(label="2026-27", start_date=dt.date(2026, 7, 1),
                        end_date=dt.date(2027, 6, 30), is_current=True)
    db.add(year)
    db.flush()
    semester = Semester(academic_year_id=year.id, number=7, term=SemesterTerm.ODD)
    db.add(semester)
    db.flush()
    courses = {}
    for code in SUBJECTS:
        course = Course(code=f"ICT-{code}", title=f"{code} subject",
                        department_id=world.departments["ICT"].id, credits=3)
        db.add(course)
        db.flush()
        courses[code] = course
    offerings: dict[tuple[str, str], CourseOffering] = {}
    for slot in ("PE4", "PE5"):
        for code, course in courses.items():
            offering = CourseOffering(course_id=course.id, semester_id=semester.id,
                                      curriculum_component_id=slots[slot].id,
                                      status=OfferingStatus.OPEN, min_students_to_run=40)
            db.add(offering)
            offerings[(slot, code)] = offering
    db.flush()

    db.add(FacultyRoleAssignment(
        faculty_id=world.mentor_ict.faculty.id, role=AssignedRole.COORDINATOR,
        domain=CoordinationDomain.CORE_ELECTIVE, department_id=world.departments["ICT"].id,
        is_active=True, assigned_at=NOW))
    db.add(FacultyRoleAssignment(
        faculty_id=world.cssi_ict.faculty.id, role=AssignedRole.COORDINATOR,
        domain=CoordinationDomain.OPEN_ELECTIVE, department_id=world.departments["ICT"].id,
        is_active=True, assigned_at=NOW))
    db.flush()
    db.refresh(world.mentor_ict.faculty)
    db.refresh(world.cssi_ict.faculty)
    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)

    db.query(Student).update({Student.current_semester: 1})
    world.student_a.student.current_semester = 6
    world.student_a.student.program_id = world.programs["B.TECH-ICT"].id
    others = [make_student("B.TECH-ICT", 2023, semester=6) for _ in range(5)]
    db.flush()
    return type("Sem7", (), {
        "slots": slots, "courses": courses, "offerings": offerings,
        "program": world.programs["B.TECH-ICT"].id, "ict": world.departments["ICT"].id,
        "coord": world.mentor_ict, "open_coord": world.cssi_ict, "hod": world.plain,
        "student": world.student_a, "others": others,
        "cohort": [world.student_a.student, *others],
    })


def body(sem7, **overrides):
    payload = {
        "code": "SEM7-PE", "title": "Semester VII Program Electives",
        "component_type": "PROGRAM_CORE_ELECTIVE", "department_id": sem7.ict,
        "closes_at": NEXT_WEEK, "eligible_semesters": [6],
        "eligible_program_ids": [sem7.program], "selection_mode": "TWO_STAGE",
        "interest_pick_count": 5, "min_students_to_run": 2,
    }
    payload.update(overrides)
    return payload


def move(api, headers, rid, target):
    return api.post(f"{WINDOWS}/{rid}/status", params={"target": target}, headers=headers)


def err(response):
    return response.json()["error"]["message"]


@pytest.fixture
def coord(login, sem7):
    return login(sem7.coord.email)


@pytest.fixture
def interest(api, db, sem7, coord):
    """An open two-stage round over all eight subjects in both slots."""
    created = api.post(WINDOWS, json=body(sem7), headers=coord)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    attached = api.post(f"{WINDOWS}/{rid}/offerings", headers=coord,
                        json={"offering_ids": [o.id for o in sem7.offerings.values()]})
    assert attached.status_code == 200, attached.text
    opened = move(api, coord, rid, "OPEN")
    assert opened.status_code == 200, opened.text
    return rid


def ids(sem7, *codes):
    return [sem7.courses[c].id for c in codes]


def tick(db, window_id, student, codes, sem7, stage=RoundStage.INTEREST):
    """Record ticks directly, for students who cannot sign in."""
    window = db.get(ElectiveRegistrationWindow, window_id)
    for old in two_stage.choices(db, window, stage, student.id):
        db.delete(old)
    for cid in ids(sem7, *codes):
        db.add(ElectiveRoundChoice(registration_window_id=window_id, stage=stage,
                                   student_id=student.id, course_id=cid, submitted_at=NOW))
    db.flush()


def choose(api, login, sem7, rid, codes):
    return api.put(f"/api/v1/electives/rounds/{rid}/choices",
                   headers=login(sem7.student.email), json={"course_ids": ids(sem7, *codes)})


# ── setting a round up ─────────────────────────────────────────────────────
def test_a_two_stage_round_starts_in_its_interest_stage(api, sem7, coord, interest):
    round_ = api.get(f"{WINDOWS}/{interest}", headers=coord).json()
    assert round_["selection_mode"] == "TWO_STAGE"
    assert round_["stage"] == "INTEREST"
    assert round_["interest_pick_count"] == 5


def test_opening_needs_the_number_of_subjects_to_tick(api, sem7, coord):
    rid = api.post(WINDOWS, json=body(sem7, interest_pick_count=None),
                   headers=coord).json()["id"]
    api.post(f"{WINDOWS}/{rid}/offerings", headers=coord,
             json={"offering_ids": [o.id for o in sem7.offerings.values()]})
    response = move(api, coord, rid, "OPEN")
    assert response.status_code == 422
    assert "how many subjects" in err(response)


def test_students_cannot_be_asked_to_tick_more_subjects_than_offered(api, sem7, coord):
    rid = api.post(WINDOWS, json=body(sem7, interest_pick_count=9),
                   headers=coord).json()["id"]
    api.post(f"{WINDOWS}/{rid}/offerings", headers=coord,
             json={"offering_ids": [o.id for o in sem7.offerings.values()]})
    response = move(api, coord, rid, "OPEN")
    assert response.status_code == 422
    assert "the round offers 8" in err(response)


def test_the_rounds_minimum_and_section_size_reach_its_courses(api, db, sem7, coord):
    rid = api.post(WINDOWS, json=body(sem7, min_students_to_run=48, section_capacity=60),
                   headers=coord).json()["id"]
    api.post(f"{WINDOWS}/{rid}/offerings", headers=coord,
             json={"offering_ids": [o.id for o in sem7.offerings.values()]})
    for offering in sem7.offerings.values():
        db.refresh(offering)
        assert (offering.min_students_to_run, offering.section_capacity) == (48, 60)
    api.patch(f"{WINDOWS}/{rid}", headers=coord, json={"min_students_to_run": 30})
    db.refresh(sem7.offerings[("PE4", "NLP")])
    assert sem7.offerings[("PE4", "NLP")].min_students_to_run == 30


def test_how_students_choose_is_fixed_once_the_round_opens(api, sem7, coord, interest):
    response = api.patch(f"{WINDOWS}/{interest}", headers=coord,
                         json={"selection_mode": "RANKED"})
    assert response.status_code == 409


# ── the interest round ─────────────────────────────────────────────────────
def test_the_workspace_shows_the_round_and_its_eight_subjects(api, login, sem7, interest):
    ws = api.get(f"/api/v1/electives/components/{sem7.slots['PE4'].id}/workspace",
                 headers=login(sem7.student.email)).json()
    assert ws["round"]["stage"] == "INTEREST"
    assert ws["round"]["pick_count"] == 5
    assert ws["round"]["can_submit"] is True
    assert len(ws["round"]["subjects"]) == 8      # each subject once, not once per slot


def test_a_student_ticks_exactly_the_number_set(api, login, sem7, interest):
    too_few = choose(api, login, sem7, interest, ["NLP", "BDA"])
    assert too_few.status_code == 422 and "exactly 5" in err(too_few)
    ok = choose(api, login, sem7, interest, ["NLP", "BDA", "CV", "EFC", "ISA"])
    assert ok.status_code == 200, ok.text
    assert sorted(ok.json()["my_course_ids"]) == sorted(ids(sem7, "NLP", "BDA", "CV", "EFC", "ISA"))


def test_ticking_again_replaces_the_earlier_ticks(api, login, db, sem7, interest):
    choose(api, login, sem7, interest, ["NLP", "BDA", "CV", "EFC", "ISA"])
    choose(api, login, sem7, interest, ["RTOS", "SSP", "SEPM", "NLP", "BDA"])
    window = db.get(ElectiveRegistrationWindow, interest)
    mine = {c.course_id for c in two_stage.choices(db, window, RoundStage.INTEREST,
                                                   sem7.student.student.id)}
    assert mine == set(ids(sem7, "RTOS", "SSP", "SEPM", "NLP", "BDA"))


def test_the_same_subject_cannot_be_ticked_twice(api, login, sem7, interest):
    response = api.put(f"/api/v1/electives/rounds/{interest}/choices",
                       headers=login(sem7.student.email),
                       json={"course_ids": ids(sem7, "NLP", "NLP", "CV", "EFC", "ISA")})
    assert response.status_code == 422


def test_a_subject_outside_the_round_is_refused(api, login, db, sem7, interest):
    stray = Course(code="ICT-STRAY", title="Not offered", credits=3)
    db.add(stray)
    db.flush()
    response = api.put(f"/api/v1/electives/rounds/{interest}/choices",
                       headers=login(sem7.student.email),
                       json={"course_ids": ids(sem7, "NLP", "BDA", "CV", "EFC") + [stray.id]})
    assert response.status_code == 422


def test_ranking_is_refused_in_a_two_stage_round(api, login, sem7, interest):
    response = api.post("/api/v1/electives/preferences", headers=login(sem7.student.email),
                        json={"curriculum_component_id": sem7.slots["PE4"].id,
                              "preferences": [{"course_offering_id":
                                               sem7.offerings[("PE4", "NLP")].id,
                                               "preference_order": 1}]})
    assert response.status_code == 409
    assert "ticking subjects" in err(response)


def test_a_student_the_round_does_not_cover_cannot_tick(api, login, db, sem7, interest):
    sem7.student.student.current_semester = 4
    db.flush()
    response = choose(api, login, sem7, interest, ["NLP", "BDA", "CV", "EFC", "ISA"])
    assert response.status_code == 409


def test_nobody_can_tick_once_the_interest_round_is_locked(api, login, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    response = choose(api, login, sem7, interest, ["NLP", "BDA", "CV", "EFC", "ISA"])
    assert response.status_code == 409


def test_only_the_coordinator_and_hod_see_the_votes(api, login, db, sem7, coord, interest):
    tick(db, interest, sem7.others[0], ["NLP", "BDA", "CV", "EFC", "ISA"], sem7)
    tick(db, interest, sem7.others[1], ["NLP", "BDA", "CV", "RTOS", "SSP"], sem7)
    tally = api.get(f"{WINDOWS}/{interest}/interest", headers=coord)
    assert tally.status_code == 200, tally.text
    votes = {row["code"]: row["votes"] for row in tally.json()["subjects"]}
    assert votes["ICT-NLP"] == 2 and votes["ICT-RTOS"] == 1 and votes["ICT-SEPM"] == 0
    assert tally.json()["voters"] == 2
    assert tally.json()["subjects"][0]["votes"] == 2           # most first
    assert api.get(f"{WINDOWS}/{interest}/interest",
                   headers=login(sem7.hod.email)).status_code == 200
    assert api.get(f"{WINDOWS}/{interest}/interest",
                   headers=login(sem7.student.email)).status_code == 403


def test_a_student_is_not_shown_vote_counts(api, login, db, sem7, interest):
    tick(db, interest, sem7.others[0], ["NLP", "BDA", "CV", "EFC", "ISA"], sem7)
    ws = api.get(f"/api/v1/electives/components/{sem7.slots['PE4'].id}/workspace",
                 headers=login(sem7.student.email)).text
    assert "votes" not in ws


# ── the shortlist ──────────────────────────────────────────────────────────
def shortlist(api, coord, rid, sem7, codes, picks=2, closes=IN_TWO_WEEKS):
    return api.post(f"{WINDOWS}/{rid}/shortlist", headers=coord, json={
        "course_ids": ids(sem7, *codes), "final_pick_count": picks, "closes_at": closes})


def test_the_interest_round_must_be_locked_before_shortlisting(api, sem7, coord, interest):
    response = shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"])
    assert response.status_code == 409
    assert "Lock the interest round" in err(response)


def test_the_coordinator_keeps_any_number_of_subjects(api, db, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    response = shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"])
    assert response.status_code == 200, response.text
    assert response.json()["stage"] == "FINAL"
    assert response.json()["status"] == "OPEN"
    window = db.get(ElectiveRegistrationWindow, interest)
    assert [c.code for c in two_stage.subjects(db, window)] == ["ICT-BDA", "ICT-CV", "ICT-NLP"]
    # Dropped subjects leave the round in both slots, free for another round.
    assert sem7.offerings[("PE4", "RTOS")].registration_window_id is None
    assert sem7.offerings[("PE5", "RTOS")].registration_window_id is None


def test_dropped_subjects_keep_their_votes_on_record(api, db, sem7, coord, interest):
    tick(db, interest, sem7.others[0], ["NLP", "BDA", "CV", "RTOS", "SSP"], sem7)
    move(api, coord, interest, "LOCKED")
    shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"])
    rows = {r["code"]: r for r in api.get(f"{WINDOWS}/{interest}/interest",
                                          headers=coord).json()["subjects"]}
    assert rows["ICT-RTOS"]["votes"] == 1 and rows["ICT-RTOS"]["in_round"] is False


def test_a_student_takes_no_more_subjects_than_the_round_has_slots(api, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    response = shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"], picks=3)
    assert response.status_code == 422
    assert "2 elective slot(s)" in err(response)


def test_the_final_pick_count_cannot_exceed_the_shortlist(api, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    response = shortlist(api, coord, interest, sem7, ["NLP"], picks=2)
    assert response.status_code == 422


def test_the_final_round_needs_a_future_deadline(api, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    past = (NOW - dt.timedelta(hours=1)).isoformat()
    response = shortlist(api, coord, interest, sem7, ["NLP", "BDA"], closes=past)
    assert response.status_code == 422


def test_every_covered_student_hears_the_final_round_opened(
        api, db, sem7, coord, interest):
    tick(db, interest, sem7.others[0], ["NLP", "BDA", "CV", "EFC", "ISA"], sem7)
    move(api, coord, interest, "LOCKED")
    db.query(Notification).delete()
    db.flush()
    shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"])
    told = {n.user_id for n in db.scalars(select(Notification).where(
        Notification.title.like("%final round is open%")))}
    # Including the five who never voted.
    assert told == {s.user_id for s in sem7.cohort}


def test_the_hod_cannot_shortlist(api, login, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    response = shortlist(api, login(sem7.hod.email), interest, sem7, ["NLP", "BDA"])
    assert response.status_code == 403


# ── the final round ────────────────────────────────────────────────────────
@pytest.fixture
def final(api, db, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    response = shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"])
    assert response.status_code == 200, response.text
    return interest


def test_in_the_final_round_a_student_ticks_the_shortlisted_subjects(
        api, login, sem7, final):
    dropped = choose(api, login, sem7, final, ["NLP", "RTOS"])
    assert dropped.status_code == 422
    ok = choose(api, login, sem7, final, ["NLP", "CV"])
    assert ok.status_code == 200, ok.text
    assert ok.json()["stage"] == "FINAL" and ok.json()["pick_count"] == 2


def test_the_student_sees_their_interest_ticks_during_the_final_round(
        api, login, db, sem7, coord):
    rid = api.post(WINDOWS, json=body(sem7), headers=coord).json()["id"]
    api.post(f"{WINDOWS}/{rid}/offerings", headers=coord,
             json={"offering_ids": [o.id for o in sem7.offerings.values()]})
    move(api, coord, rid, "OPEN")
    choose(api, login, sem7, rid, ["NLP", "BDA", "CV", "EFC", "ISA"])
    move(api, coord, rid, "LOCKED")
    shortlist(api, coord, rid, sem7, ["NLP", "BDA", "CV"])
    ws = api.get(f"/api/v1/electives/components/{sem7.slots['PE4'].id}/workspace",
                 headers=login(sem7.student.email)).json()["round"]
    assert sorted(ws["my_interest_course_ids"]) == sorted(ids(sem7, "NLP", "BDA", "CV", "EFC", "ISA"))
    assert ws["my_course_ids"] == []


# ── finalising ─────────────────────────────────────────────────────────────
def finalise(api, coord, rid, **kw):
    return api.post(f"{WINDOWS}/{rid}/finalise", headers=coord,
                    json={"dry_run": kw.pop("dry_run", False), **kw})


@pytest.fixture
def chosen(db, sem7, final):
    """NLP 4, CV 3, BDA 1 (below the minimum of 2); one student never chose."""
    picks = [["NLP", "CV"], ["NLP", "CV"], ["NLP", "BDA"], ["NLP", "CV"], None, None]
    for student, codes in zip(sem7.cohort, picks):
        if codes:
            tick(db, final, student, codes, sem7, stage=RoundStage.FINAL)
    # The fifth student also chose nothing; the sixth chose nothing.
    return final


def test_finalising_needs_the_final_round_locked(api, sem7, coord, chosen):
    response = finalise(api, coord, chosen)
    assert response.status_code == 409
    preview = finalise(api, coord, chosen, dry_run=True)
    assert preview.status_code == 200, preview.text


def test_a_subject_under_the_minimum_is_withdrawn(api, sem7, coord, chosen):
    preview = finalise(api, coord, chosen, dry_run=True).json()
    runs = {s["code"]: s["runs"] for s in preview["subjects"]}
    assert runs == {"ICT-NLP": True, "ICT-CV": True, "ICT-BDA": False}
    assert any("Withdrawn" in n and "ICT-BDA" in n for n in preview["notes"])


def test_every_student_gets_one_seat_per_slot_in_running_subjects(
        api, db, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    result = finalise(api, coord, chosen)
    assert result.status_code == 200, result.text
    seats = list(db.scalars(select(ElectiveAllocation)))
    assert len(seats) == 12                                   # six students × two slots
    by_student: dict[int, list[ElectiveAllocation]] = {}
    for seat in seats:
        by_student.setdefault(seat.student_id, []).append(seat)
    running = set(ids(sem7, "NLP", "CV"))
    for student_seats in by_student.values():
        assert {s.curriculum_component_id for s in student_seats} == {
            sem7.slots["PE4"].id, sem7.slots["PE5"].id}
        assert {s.course_offering.course_id for s in student_seats} == running


def test_whoever_chose_the_withdrawn_subject_is_placed_and_told_why(
        api, db, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    result = finalise(api, coord, chosen).json()
    assert result["replaced_withdrawn"] == 1
    assert result["placed_no_submission"] == 2
    # Three got both subjects they chose; the fourth lost BDA, counted above.
    assert result["by_choice"] == 3
    assert (result["by_choice"] + result["replaced_withdrawn"]
            + result["placed_no_submission"]) == result["students_placed"] == 6
    third = sem7.cohort[2].id
    remarks = [a.remarks for a in db.scalars(select(ElectiveAllocation).where(
        ElectiveAllocation.student_id == third))]
    assert None in remarks                                        # kept NLP as chosen
    assert any(r and "withdrawn" in r for r in remarks)


def test_the_round_is_allocated_and_nobody_is_told_until_publish(
        api, db, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    db.query(Notification).delete()
    db.flush()
    finalise(api, coord, chosen)
    assert db.get(ElectiveRegistrationWindow, chosen).status == RegistrationWindowStatus.ALLOCATED
    assert db.scalars(select(Notification)).all() == []
    assert move(api, coord, chosen, "PUBLISHED").status_code == 200
    told = {n.user_id: n.message for n in db.scalars(select(Notification))}
    assert set(told) == {s.user_id for s in sem7.cohort}
    assert all("ICT-NLP" in m and "ICT-CV" in m for m in told.values())


def test_the_preview_is_what_finalising_writes(api, db, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    preview = finalise(api, coord, chosen, dry_run=True).json()
    result = finalise(api, coord, chosen).json()
    for key in ("by_choice", "replaced_withdrawn", "placed_no_submission", "unplaced"):
        assert preview[key] == result[key]
    assert result["seats_written"] == 12


def test_the_coordinator_can_lower_the_minimum_for_the_run(api, sem7, coord, chosen):
    preview = finalise(api, coord, chosen, dry_run=True, min_students_to_run=1).json()
    assert all(s["runs"] for s in preview["subjects"])
    assert preview["minimum"] == 1


def test_the_coordinator_can_decide_which_subjects_run(api, sem7, coord, chosen):
    preview = finalise(api, coord, chosen, dry_run=True,
                       run_course_ids=ids(sem7, "NLP", "BDA")).json()
    assert {s["code"] for s in preview["subjects"] if s["runs"]} == {"ICT-NLP", "ICT-BDA"}


def test_with_nothing_running_finalising_is_refused(api, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    response = finalise(api, coord, chosen, min_students_to_run=100)
    assert response.status_code == 409
    assert "No subject reached 100" in err(response)


def test_a_missing_offering_in_a_slot_is_created_when_needed(
        api, db, sem7, coord, chosen):
    # CV is offered only in PE4: anyone given CV for PE5 needs an offering there.
    sem7.offerings[("PE5", "CV")].registration_window_id = None
    db.delete(sem7.offerings[("PE5", "CV")])
    db.flush()
    move(api, coord, chosen, "LOCKED")
    assert finalise(api, coord, chosen).status_code == 200
    seats = list(db.scalars(select(ElectiveAllocation)))
    assert len(seats) == 12
    cv_offerings = {s.course_offering_id for s in seats
                    if s.course_offering.course_id == sem7.courses["CV"].id}
    assert len(cv_offerings) == 1     # placed through the PE4 offering only
    assert all(s.curriculum_component_id == s.course_offering.curriculum_component_id
               for s in seats)


def test_a_two_stage_round_is_not_moved_to_allocated_by_hand(api, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    response = move(api, coord, chosen, "ALLOCATED")
    assert response.status_code == 409
    assert "finalising" in err(response)


def test_a_ranked_allocation_run_is_refused_for_a_two_stage_round(
        api, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    response = api.post("/api/v1/electives/admin/allocate", headers=coord, json={
        "curriculum_component_id": sem7.slots["PE4"].id, "registration_window_id": chosen,
        "strategy": "first_come_first_served", "dry_run": True})
    assert response.status_code == 409


def test_deleting_a_two_stage_round_removes_its_ticks(api, db, sem7, coord, chosen):
    tick(db, chosen, sem7.cohort[5], ["NLP", "BDA", "CV", "EFC", "ISA"], sem7)
    response = api.delete(f"{WINDOWS}/{chosen}", headers=coord)
    assert response.status_code == 200, response.text
    assert db.scalars(select(ElectiveRoundChoice)).all() == []


# ── subjects ───────────────────────────────────────────────────────────────
def test_the_coordinator_adds_a_new_subject_to_a_slot(api, db, sem7, coord):
    response = api.post(f"/api/v1/electives/admin/slots/{sem7.slots['PE4'].id}/subjects",
                        headers=coord, json={"code": "ict-qc", "title": "Quantum Computing",
                                             "credits": 3})
    assert response.status_code == 201, response.text
    assert response.json()["code"] == "ICT-QC"
    course = db.scalar(select(Course).where(Course.code == "ICT-QC"))
    assert course is not None and course.department_id == sem7.ict


def test_an_existing_course_is_offered_rather_than_duplicated(api, db, sem7, coord):
    response = api.post(f"/api/v1/electives/admin/slots/{sem7.slots['PE1'].id}/subjects",
                        headers=coord, json={"code": "ICT-NLP", "title": "ignored"})
    assert response.status_code == 201, response.text
    assert response.json()["course_id"] == sem7.courses["NLP"].id


def test_a_subject_already_in_the_slot_is_refused(api, sem7, coord):
    response = api.post(f"/api/v1/electives/admin/slots/{sem7.slots['PE4'].id}/subjects",
                        headers=coord, json={"code": "ICT-NLP", "title": "again"})
    assert response.status_code == 409


def test_another_familys_coordinator_cannot_add_subjects(api, login, sem7):
    response = api.post(f"/api/v1/electives/admin/slots/{sem7.slots['PE4'].id}/subjects",
                        headers=login(sem7.open_coord.email),
                        json={"code": "ICT-X", "title": "X"})
    assert response.status_code == 403


def test_editing_a_subject_changes_it_everywhere(api, db, sem7, coord):
    offering = sem7.offerings[("PE4", "NLP")]
    response = api.patch(f"/api/v1/electives/admin/subjects/{offering.id}", headers=coord,
                         json={"code": "ICT-NLP2", "title": "Natural Language Processing",
                               "credits": 4})
    assert response.status_code == 200, response.text
    db.refresh(sem7.offerings[("PE5", "NLP")])
    assert sem7.offerings[("PE5", "NLP")].course.title == "Natural Language Processing"
    assert float(sem7.offerings[("PE5", "NLP")].course.credits) == 4


def test_a_subject_code_cannot_clash_with_another_course(api, sem7, coord):
    response = api.patch(f"/api/v1/electives/admin/subjects/{sem7.offerings[('PE4', 'NLP')].id}",
                         headers=coord, json={"code": "ICT-CV"})
    assert response.status_code == 409


def test_a_subject_is_removed_from_its_slot_only(api, db, sem7, coord):
    offering = sem7.offerings[("PE4", "SEPM")]
    response = api.delete(f"/api/v1/electives/admin/subjects/{offering.id}", headers=coord)
    assert response.status_code == 200, response.text
    assert db.get(CourseOffering, offering.id) is None
    assert db.get(Course, sem7.courses["SEPM"].id) is not None
    assert db.get(CourseOffering, sem7.offerings[("PE5", "SEPM")].id) is not None


def test_a_subject_in_a_live_round_cannot_be_removed(api, sem7, coord, interest):
    response = api.delete(f"/api/v1/electives/admin/subjects/"
                          f"{sem7.offerings[('PE4', 'NLP')].id}", headers=coord)
    assert response.status_code == 409


def test_a_subject_cannot_be_changed_once_allocated(api, sem7, coord, chosen):
    move(api, coord, chosen, "LOCKED")
    finalise(api, coord, chosen)
    response = api.patch(f"/api/v1/electives/admin/subjects/"
                         f"{sem7.offerings[('PE4', 'NLP')].id}", headers=coord,
                         json={"title": "late change"})
    assert response.status_code == 409


def test_a_ranked_round_still_works_as_before(api, login, db, sem7, coord):
    rid = api.post(WINDOWS, json=body(sem7, code="PE-RANKED", selection_mode="RANKED",
                                      interest_pick_count=None), headers=coord).json()["id"]
    api.post(f"{WINDOWS}/{rid}/offerings", headers=coord,
             json={"offering_ids": [sem7.offerings[("PE4", c)].id for c in SUBJECTS]})
    assert move(api, coord, rid, "OPEN").status_code == 200
    ws = api.get(f"/api/v1/electives/components/{sem7.slots['PE4'].id}/workspace",
                 headers=login(sem7.student.email)).json()
    assert ws["round"] is None and ws["window_open"] is True


def test_a_slot_without_the_subject_gets_it_offered_at_finalising(
        api, db, sem7, coord, chosen):
    """NLP and CV run, but PE5 offers neither: every student needs one of them
    in PE5, so the subject is offered there, attached to the round."""
    for code in ("NLP", "CV"):
        db.delete(sem7.offerings[("PE5", code)])
    db.flush()
    move(api, coord, chosen, "LOCKED")
    assert finalise(api, coord, chosen).status_code == 200
    created = list(db.scalars(select(CourseOffering).where(
        CourseOffering.curriculum_component_id == sem7.slots["PE5"].id,
        CourseOffering.course_id.in_(ids(sem7, "NLP", "CV")))))
    assert created and all(o.registration_window_id == chosen for o in created)
    pe5 = [a for a in db.scalars(select(ElectiveAllocation))
           if a.curriculum_component_id == sem7.slots["PE5"].id]
    assert len(pe5) == 6


# ── the student's elective list follows the round ──────────────────────────
def card(api, login, sem7, code="PE4"):
    rows = {c["code"]: c for c in api.get(
        "/api/v1/electives/components?component_type=PROGRAM_CORE_ELECTIVE",
        headers=login(sem7.student.email)).json()}
    return rows[code]


def test_the_list_says_the_interest_round_is_open_not_not_started(
        api, login, sem7, interest):
    row = card(api, login, sem7)
    assert row["is_unlocked"] is True
    assert row["status_label"] == "Interest round open"


def test_the_list_says_submitted_once_the_student_ticks(api, login, sem7, interest):
    choose(api, login, sem7, interest, ["NLP", "BDA", "CV", "EFC", "ISA"])
    assert card(api, login, sem7)["status_label"] == "Choice submitted"
    assert card(api, login, sem7, "PE5")["status_label"] == "Choice submitted"


def test_the_list_follows_the_round_into_its_final_stage(api, login, sem7, coord, interest):
    choose(api, login, sem7, interest, ["NLP", "BDA", "CV", "EFC", "ISA"])
    move(api, coord, interest, "LOCKED")
    assert card(api, login, sem7)["status_label"] == "Choice submitted"
    shortlist(api, coord, interest, sem7, ["NLP", "BDA", "CV"])
    # Interest ticks are not a final choice.
    assert card(api, login, sem7)["status_label"] == "Final round open"


def test_a_student_who_did_not_choose_sees_the_round_locked(api, login, sem7, coord, interest):
    move(api, coord, interest, "LOCKED")
    assert card(api, login, sem7)["status_label"] == "Choices locked"


def test_the_list_tells_the_page_both_slots_are_chosen_together(api, login, sem7, interest):
    pe4, pe5 = card(api, login, sem7, "PE4"), card(api, login, sem7, "PE5")
    assert pe4["round_id"] == pe5["round_id"] == interest
    assert pe4["round_two_stage"] is True and pe5["round_two_stage"] is True


def test_a_slot_with_no_round_reports_none(api, login, sem7):
    row = card(api, login, sem7, "PE1")
    assert row["round_id"] is None and row["round_two_stage"] is None
