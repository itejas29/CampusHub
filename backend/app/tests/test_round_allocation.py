"""Allocating a registration round: one round at a time, first come first served.

Two things were wrong, and these tests pin both:

* **A run reached students outside the round.** Allocation ran over the whole
  curriculum slot. When the Semester IV cohort and the Semester III cohort
  (choosing ahead) both had a round on Open Elective 1, one run seated both
  cohorts and told every one of them their "allocation was published" — before
  the coordinator had published anything.
* **There was no first-come, first-served rule**, and a student who never
  submitted was simply left out. Now the earliest submission is seated first,
  and anyone the round covered who did not submit is placed at random in the
  seats that remain.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.academics import ElectiveAllocation, ElectivePreference
from app.models.engagement import Announcement, Notification
from app.models.enums import (
    AllocationStatus, AudienceType, PreferenceStatus, RegistrationWindowStatus, Role,
)
from app.models.identity import Student
from app.services.allocation import Candidate, SeatPool, get_strategy

from app.tests.test_registration_rounds_api import (  # noqa: F401  (fixtures)
    NEXT_WEEK, WINDOWS, campus, move, payload,
)

ALLOCATE = "/api/v1/electives/admin/allocate"
T0 = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.timezone.utc)
FCFS = "first_come_first_served"


def at(minutes: int) -> dt.datetime:
    return T0 + dt.timedelta(minutes=minutes)


# ── the rule itself ────────────────────────────────────────────────────────
def run_rule(candidates, seats, **config):
    pools = {pid: SeatPool(course_offering_id=pid, capacity=cap)
             for pid, cap in seats.items()}
    return get_strategy(FCFS).allocate(candidates, pools,
                                       config={"seed": "t", **config})


def seats_of(outcome):
    return {a.student_id: a.course_offering_id for a in outcome.awards}


def test_the_earlier_submission_takes_the_last_seat_whatever_was_ranked():
    # Course 10 has one seat. Student 2 submitted first and ranked it second;
    # student 1 submitted later and ranked it first. First come wins.
    outcome = run_rule([
        Candidate(1, 10, 1, at(5)), Candidate(1, 20, 2, at(5)),
        Candidate(2, 20, 1, at(1)), Candidate(2, 10, 2, at(1)),
    ], {10: 1, 20: 1})
    assert seats_of(outcome) == {2: 20, 1: 10}

    outcome = run_rule([
        Candidate(1, 10, 1, at(5)), Candidate(1, 20, 2, at(5)),
        Candidate(2, 10, 1, at(1)), Candidate(2, 20, 2, at(1)),
    ], {10: 1, 20: 1})
    assert seats_of(outcome) == {2: 10, 1: 20}
    assert {a.student_id: a.preference_order_granted for a in outcome.awards} == {2: 1, 1: 2}


def test_each_student_gets_their_highest_choice_that_still_has_a_seat():
    outcome = run_rule([Candidate(s, c, rank, at(s))
                        for s in (1, 2, 3)
                        for rank, c in enumerate((10, 20, 30), start=1)],
                       {10: 1, 20: 1, 30: 1})
    assert seats_of(outcome) == {1: 10, 2: 20, 3: 30}
    assert not outcome.unallocated_student_ids


def test_with_no_seat_limit_everyone_gets_their_first_choice():
    outcome = run_rule([Candidate(s, 10, 1, at(s)) for s in range(1, 51)],
                       {10: 10_000, 20: 10_000})
    assert set(seats_of(outcome).values()) == {10}


def test_a_student_who_did_not_submit_is_placed_at_random_in_a_seat_left():
    outcome = run_rule([Candidate(1, 10, 1, at(1))], {10: 1, 20: 1, 30: 1},
                       non_submitter_ids=[7, 8])
    seated = seats_of(outcome)
    assert seated[1] == 10
    assert {seated[7], seated[8]} == {20, 30}       # the only seats left
    random_awards = [a for a in outcome.awards if a.student_id in (7, 8)]
    assert all(a.preference_order_granted is None for a in random_awards)
    assert all("No preferences submitted" in a.reason for a in random_awards)


def test_submitters_are_always_served_before_anyone_is_placed_at_random():
    # Non-submitter 1 has the lowest id; a careless loop would seat them first.
    outcome = run_rule([Candidate(9, 10, 1, at(1))], {10: 1, 20: 1},
                       non_submitter_ids=[1])
    assert seats_of(outcome) == {9: 10, 1: 20}


def test_the_random_draw_is_repeatable_so_the_preview_matches_the_run():
    kwargs = dict(non_submitter_ids=list(range(100, 140)))
    first = seats_of(run_rule([], {10: 20, 20: 20, 30: 20}, **kwargs))
    again = seats_of(run_rule([], {10: 20, 20: 20, 30: 20}, **kwargs))
    assert first == again
    assert len(set(first.values())) > 1             # actually spread, not all in one


def test_random_placement_never_overfills_a_course():
    outcome = run_rule([], {10: 3, 20: 2}, non_submitter_ids=list(range(1, 6)))
    filled = list(seats_of(outcome).values())
    assert filled.count(10) == 3 and filled.count(20) == 2


def test_a_submitter_whose_choices_all_filled_is_placed_in_a_free_course():
    outcome = run_rule([Candidate(1, 10, 1, at(1)), Candidate(2, 10, 1, at(2))],
                       {10: 1, 20: 5})
    assert seats_of(outcome) == {1: 10, 2: 20}
    assert "Every course you chose was full" in outcome.awards[1].reason


def test_when_every_seat_is_gone_the_rest_are_reported_not_dropped():
    outcome = run_rule([Candidate(1, 10, 1, at(1)), Candidate(2, 10, 1, at(2))],
                       {10: 1}, non_submitter_ids=[3])
    assert seats_of(outcome) == {1: 10}
    assert outcome.unallocated_student_ids == [2, 3]
    assert any("could not be seated" in n for n in outcome.notes)


def test_a_student_listed_as_non_submitter_and_submitter_is_seated_once():
    outcome = run_rule([Candidate(1, 10, 1, at(1))], {10: 5, 20: 5},
                       non_submitter_ids=[1])
    assert [a.student_id for a in outcome.awards] == [1]


# ── one round at a time, through the API ───────────────────────────────────
@pytest.fixture
def two_cohorts(api, login, db, campus, make_student):
    """Open Elective 1 with two rounds at once: Semester III choosing ahead
    (two courses) and Semester IV choosing now (the third course)."""
    headers = login(campus.open.email)
    oe1 = campus.offerings["OE1"]

    def make_round(code, semester, offerings):
        created = api.post(WINDOWS, headers=headers, json=payload(
            campus, code=code, eligible_semesters=[semester]))
        assert created.status_code == 201, created.text
        rid = created.json()["id"]
        attached = api.post(f"{WINDOWS}/{rid}/offerings", headers=headers,
                            json={"offering_ids": [o.id for o in offerings]})
        assert attached.status_code == 200, attached.text
        assert move(api, headers, rid, "OPEN").status_code == 200
        return rid

    # Nobody else in Semester III or IV, so the cohorts are exactly these.
    db.query(Student).update({Student.current_semester: 1})
    db.flush()
    early = make_round("OE1-SEM3", 3, oe1[:2])
    now = make_round("OE1-SEM4", 4, oe1[2:])
    sem3 = [make_student("B.TECH-ICT", 2024, semester=3) for _ in range(4)]
    sem4 = [make_student("B.TECH-ICT", 2023, semester=4) for _ in range(3)]
    db.flush()

    def prefer(student, offerings, minutes):
        for rank, o in enumerate(offerings, start=1):
            db.add(ElectivePreference(
                student_id=student.id,
                curriculum_component_id=campus.components["OE1"].id,
                course_offering_id=o.id, preference_order=rank,
                status=PreferenceStatus.SUBMITTED, submitted_at=at(minutes)))

    # Semester III: two submit (the later one first ranks the same course),
    # two do not. Semester IV: every one submits.
    prefer(sem3[0], [oe1[0], oe1[1]], 1)
    prefer(sem3[1], [oe1[0], oe1[1]], 2)
    for i, s in enumerate(sem4):
        prefer(s, [oe1[2]], 10 + i)
    db.flush()
    db.query(Notification).delete()
    db.flush()
    return type("Cohorts", (), {"early": early, "now": now, "sem3": sem3,
                                "sem4": sem4, "headers": headers})


def allocate(api, campus, cohorts, round_id=None, **body):
    return api.post(ALLOCATE, headers=cohorts.headers, json={
        "curriculum_component_id": campus.components["OE1"].id,
        "registration_window_id": round_id, "strategy": FCFS,
        "dry_run": False, **body})


def allocations(db, campus):
    return {a.student_id: a for a in db.scalars(select(ElectiveAllocation).where(
        ElectiveAllocation.curriculum_component_id == campus.components["OE1"].id))}


def test_a_run_seats_only_the_students_of_its_own_round(
        api, db, campus, two_cohorts):
    c = two_cohorts
    assert move(api, c.headers, c.early, "LOCKED").status_code == 200
    response = allocate(api, campus, c, c.early, seats_per_course=2)
    assert response.status_code == 200, response.text

    seated = allocations(db, campus)
    assert set(seated) == {s.id for s in c.sem3}                 # all four, none of Sem IV
    early_courses = {o.id for o in campus.offerings["OE1"][:2]}
    assert {a.course_offering_id for a in seated.values()} <= early_courses
    assert seated[c.sem3[0].id].course_offering_id == campus.offerings["OE1"][0].id
    assert seated[c.sem3[1].id].course_offering_id == campus.offerings["OE1"][0].id
    for late in c.sem3[2:]:
        assert seated[late.id].preference_order_granted is None
        assert seated[late.id].status == AllocationStatus.ALLOCATED
    # The other round's students and course are untouched.
    assert campus.offerings["OE1"][2].seats_filled == 0


def test_running_a_round_tells_nobody_until_the_results_are_published(
        api, db, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    assert allocate(api, campus, c, c.early, seats_per_course=2).status_code == 200
    assert db.scalars(select(Notification)).all() == []

    assert move(api, c.headers, c.early, "ALLOCATED").status_code == 200
    assert move(api, c.headers, c.early, "PUBLISHED").status_code == 200
    told = {n.user_id for n in db.scalars(select(Notification))}
    assert told == {s.user_id for s in c.sem3}
    assert not told & {s.user_id for s in c.sem4}


def test_the_first_submitter_wins_the_full_course_through_the_api(
        api, db, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    assert allocate(api, campus, c, c.early, seats_per_course=1,
                    ).status_code == 200
    seated = allocations(db, campus)
    first, second = campus.offerings["OE1"][:2]
    assert seated[c.sem3[0].id].course_offering_id == first.id
    assert seated[c.sem3[1].id].course_offering_id == second.id
    # Two seats for four students: the two who did not submit are reported.
    assert c.sem3[2].id not in seated and c.sem3[3].id not in seated


def test_with_two_rounds_on_the_slot_the_round_must_be_named(
        api, campus, two_cohorts):
    c = two_cohorts
    response = allocate(api, campus, c, None, dry_run=True)
    assert response.status_code in (409, 422), response.text
    assert "2 registration rounds" in response.json()["error"]["message"]


def test_a_round_still_open_can_be_previewed_but_not_allocated(
        api, db, campus, two_cohorts):
    c = two_cohorts
    preview = allocate(api, campus, c, c.early, dry_run=True, seats_per_course=2)
    assert preview.status_code == 200, preview.text
    assert preview.json()["allocated"] == 4
    refused = allocate(api, campus, c, c.early)
    assert refused.status_code in (409, 422)
    assert "Lock the round" in refused.json()["error"]["message"]
    assert allocations(db, campus) == {}


def test_the_preview_is_exactly_what_the_run_does(api, db, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    preview = allocate(api, campus, c, c.early, dry_run=True, seats_per_course=2).json()
    allocate(api, campus, c, c.early, seats_per_course=2)
    planned = {r["student_id"]: r["course_offering_id"] for r in preview["preview"]}
    actual = {sid: a.course_offering_id for sid, a in allocations(db, campus).items()}
    assert planned == actual


def test_a_client_cannot_choose_who_counts_as_a_non_submitter(
        api, db, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    outsider = c.sem4[0].id
    allocate(api, campus, c, c.early, seats_per_course=5,
             config={"non_submitter_ids": [outsider]})
    assert outsider not in allocations(db, campus)


def test_the_coordinator_of_another_family_cannot_allocate_the_round(
        api, login, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    response = api.post(ALLOCATE, headers=login(campus.core.email), json={
        "curriculum_component_id": campus.components["OE1"].id,
        "registration_window_id": c.early, "strategy": FCFS, "dry_run": True})
    assert response.status_code == 403


def test_a_round_from_another_slot_is_refused(api, campus, two_cohorts, db):
    c = two_cohorts
    response = api.post(ALLOCATE, headers=c.headers, json={
        "curriculum_component_id": campus.components["OE3"].id,
        "registration_window_id": c.early, "strategy": FCFS, "dry_run": True})
    assert response.status_code == 422
    assert "has no courses in" in response.json()["error"]["message"]


def test_a_second_run_does_not_reseat_anyone_already_allocated(
        api, db, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    allocate(api, campus, c, c.early, seats_per_course=2)
    before = {sid: a.course_offering_id for sid, a in allocations(db, campus).items()}
    allocate(api, campus, c, c.early, seats_per_course=2)
    after = {sid: a.course_offering_id for sid, a in allocations(db, campus).items()}
    assert before == after


def test_the_round_screen_offers_first_come_first_served(api, campus, two_cohorts):
    keys = {s["key"]: s["is_available"] for s in api.get(
        "/api/v1/electives/strategies", headers=two_cohorts.headers).json()}
    assert keys[FCFS] is True


def test_the_two_cohorts_round_states_are_independent(api, db, campus, two_cohorts):
    c = two_cohorts
    move(api, c.headers, c.early, "LOCKED")
    allocate(api, campus, c, c.early, seats_per_course=2)
    move(api, c.headers, c.early, "ALLOCATED")
    from app.models.academics import ElectiveRegistrationWindow
    assert db.get(ElectiveRegistrationWindow, c.now).status == RegistrationWindowStatus.OPEN


# ── announcements addressed to a role ──────────────────────────────────────
def test_an_announcement_to_one_role_notifies_only_that_role(api, login, db, world):
    db.query(Notification).delete()
    db.flush()
    response = api.post("/api/v1/announcements", headers=login(world.admin.email), json={
        "title": "Coordinators: allocation guidelines", "body": "Read before you run.",
        "audience_type": AudienceType.ROLE.value,
        "audience_ref_value": Role.FACULTY.value, "is_published": True})
    assert response.status_code == 201, response.text
    told = {n.user_id for n in db.scalars(select(Notification).where(
        Notification.title == "Coordinators: allocation guidelines"))}
    assert told
    assert world.student_a.user.id not in told
    assert world.student_b.user.id not in told
    assert all(db.get(type(world.admin), uid).has_role(Role.FACULTY)
               for uid in told)
    assert db.scalar(select(Announcement).where(
        Announcement.title == "Coordinators: allocation guidelines")) is not None
