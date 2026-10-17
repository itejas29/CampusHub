"""Deleting a registration round.

A coordinator who opened a round by mistake — or a demo that has used up its
courses on earlier rounds — had no way back: a course belongs to one round at
a time, and nothing released it. A round can now be deleted **until allocation
has run** (Draft, Open, Locked). Its courses return to no round, the choices
filled in it are removed, and students who had been told it was open are told
it is withdrawn. From Allocated on, students hold seats from it, so it stays.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.academics import (
    CourseOffering, ElectiveAllocation, ElectivePreference, ElectiveRegistrationWindow,
)
from app.models.system import AuditLog

from app.tests.test_registration_rounds_api import (  # noqa: F401  (fixtures)
    WINDOWS, campus, draft, live, message, move, notices, payload, submit,
)


def delete(api, headers, round_id):
    return api.delete(f"{WINDOWS}/{round_id}", headers=headers)


def round_courses(db, round_id):
    return list(db.scalars(select(CourseOffering).where(
        CourseOffering.registration_window_id == round_id)))


def test_a_coordinator_can_delete_a_draft_and_its_courses_are_freed(
        api, login, db, campus, draft):
    response = delete(api, login(campus.open.email), draft)
    assert response.status_code == 200, response.text
    assert db.get(ElectiveRegistrationWindow, draft) is None
    assert all(o.registration_window_id is None for o in campus.offerings["OE1"])
    assert "3 course(s) are free" in response.json()["message"]


def test_deleting_a_draft_tells_no_student(api, login, db, world, campus, draft):
    delete(api, login(campus.open.email), draft)
    assert not any("withdrawn" in t for t in notices(db, world.student_a))


def test_an_open_round_can_be_deleted_and_its_filled_choices_go_with_it(
        api, login, db, world, campus, live):
    student = login(world.student_a.email)
    assert submit(api, student, campus, count=2).status_code == 200
    response = delete(api, login(campus.open.email), live)
    assert response.status_code == 200, response.text
    # One student's list of two ranked choices.
    assert "the choices of 1 student(s) were removed" in response.json()["message"]
    assert db.scalars(select(ElectivePreference).where(
        ElectivePreference.student_id == world.student_a.student.id)).all() == []


def test_students_who_were_told_it_opened_are_told_it_was_withdrawn(
        api, login, db, world, campus, live):
    delete(api, login(campus.open.email), live)
    assert "Open Elective 1 — for Semester IV: round withdrawn" in notices(
        db, world.student_a)
    # Semester V was never in the round, and hears nothing.
    assert not any("withdrawn" in t for t in notices(db, world.student_b))


def test_a_locked_round_can_still_be_deleted(api, login, db, campus, live):
    headers = login(campus.open.email)
    assert move(api, headers, live, "LOCKED").status_code == 200
    assert delete(api, headers, live).status_code == 200
    assert db.get(ElectiveRegistrationWindow, live) is None


def test_once_allocated_a_round_cannot_be_deleted(api, login, db, campus, live):
    headers = login(campus.open.email)
    move(api, headers, live, "LOCKED")
    assert move(api, headers, live, "ALLOCATED").status_code == 200
    response = delete(api, headers, live)
    assert response.status_code == 409
    assert "until allocation has run" in message(response)
    assert db.get(ElectiveRegistrationWindow, live) is not None


def test_a_published_round_cannot_be_deleted(api, login, db, campus, live):
    headers = login(campus.open.email)
    for target in ("LOCKED", "ALLOCATED", "PUBLISHED"):
        assert move(api, headers, live, target).status_code == 200
    assert delete(api, headers, live).status_code == 409
    assert len(round_courses(db, live)) == 3


def test_a_locked_round_whose_allocation_already_ran_is_kept(
        api, login, db, world, campus, live):
    """The run commits seats before the round is moved to Allocated; deleting
    in between would strand those seats."""
    submit(api, login(world.student_a.email), campus)
    headers = login(campus.open.email)
    move(api, headers, live, "LOCKED")
    ran = api.post("/api/v1/electives/admin/allocate", headers=headers, json={
        "curriculum_component_id": campus.components["OE1"].id,
        "registration_window_id": live, "strategy": "preference_order",
        "dry_run": False})
    assert ran.status_code == 200, ran.text
    response = delete(api, headers, live)
    assert response.status_code == 409
    assert "Allocation has already run" in message(response)
    assert db.scalars(select(ElectiveAllocation)).all() != []


def test_the_freed_courses_can_be_put_in_a_new_round(api, login, db, campus, live):
    headers = login(campus.open.email)
    delete(api, headers, live)
    created = api.post(WINDOWS, headers=headers, json=payload(campus, code="OE1-AGAIN"))
    assert created.status_code == 201, created.text
    attached = api.post(f"{WINDOWS}/{created.json()['id']}/offerings", headers=headers,
                        json={"offering_ids": [o.id for o in campus.offerings["OE1"]]})
    assert attached.status_code == 200, attached.text


def test_a_deleted_early_round_no_longer_lets_the_earlier_cohort_in(
        api, login, world, campus, live):
    student = login(world.student_a.email)
    assert submit(api, student, campus).status_code == 200
    delete(api, login(campus.open.email), live)
    # Semester III again sees a Semester IV slot it cannot reach yet.
    assert submit(api, student, campus).status_code in (403, 409, 422)


def test_the_hod_reads_rounds_but_cannot_delete_one(api, login, db, campus, draft):
    assert delete(api, login(campus.hod.email), draft).status_code == 403
    assert db.get(ElectiveRegistrationWindow, draft) is not None


def test_another_family_or_department_cannot_delete_the_round(
        api, login, db, campus, draft):
    for who in (campus.core, campus.open_cse):
        assert delete(api, login(who.email), draft).status_code == 403
    assert db.get(ElectiveRegistrationWindow, draft) is not None


def test_a_student_cannot_delete_a_round(api, login, db, world, campus, draft):
    assert delete(api, login(world.student_a.email), draft).status_code == 403


def test_deleting_a_round_that_does_not_exist_is_a_404(api, login, campus):
    assert delete(api, login(campus.open.email), 999_999).status_code == 404


def test_the_deletion_is_audited(api, login, db, campus, live):
    delete(api, login(campus.open.email), live)
    entry = db.scalar(select(AuditLog).where(
        AuditLog.entity_type == "registration_window", AuditLog.entity_id == live,
        AuditLog.action == "DELETE"))
    assert entry is not None
    assert entry.meta["courses_released"] == 3
    assert "OE1-EARLY (OPEN)" in entry.description


def test_deleting_one_round_leaves_another_rounds_courses_alone(
        api, login, db, campus, draft):
    headers = login(campus.core.email)
    other = api.post(WINDOWS, headers=headers, json=payload(
        campus, code="PE1-KEEP", component_type="PROGRAM_CORE_ELECTIVE",
        eligible_semesters=[4]))
    assert other.status_code == 201, other.text
    api.post(f"{WINDOWS}/{other.json()['id']}/offerings", headers=headers,
             json={"offering_ids": [o.id for o in campus.offerings["PE1"]]})
    delete(api, login(campus.open.email), draft)
    assert len(round_courses(db, other.json()["id"])) == 1


def test_the_coordinators_list_no_longer_shows_a_deleted_round(
        api, login, campus, draft):
    headers = login(campus.open.email)
    delete(api, headers, draft)
    assert api.get(WINDOWS, headers=headers).json() == []
