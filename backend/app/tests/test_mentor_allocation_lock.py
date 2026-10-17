"""A locked mentor allocation changes one deliberate step at a time.

* Locking needs every student to have a mentor, and records who the mentors are.
* While locked, no run, auto-distribute or Reset all can touch it, and a student
  can be moved only to a mentor in the allocation.
* Add, remove (moving the students) and replace work while locked, respect the
  programme's cap, and are audited.
* Only the programme's coordinator can lock, change or unlock it.
"""
from __future__ import annotations

from app.models.system import AuditLog
from app.services import mentor_allocation
from app.tests.test_mentor_allocation import _assign, _enrol, _faculty, _loads, cssi  # noqa: F401


def _url(program, tail=""):
    return f"/api/v1/internships/programs/{program.id}/mentor-allocation{tail}"


def _allocated(api, db, world, login, cssi, students=15):
    a, b = _faculty(db, world, "Alpha Mentor"), _faculty(db, world, "Beta Mentor")
    rows = _enrol(db, world, cssi, students)
    assert _assign(api, login, world, cssi, allocate_by_roll_no=True,
                   faculty_ids=[a.id, b.id]).status_code == 200
    return a, b, rows


def _lock(api, login, world, cssi):
    return api.post(_url(cssi, "/lock"), headers=login(world.cssi_ict.email))


def test_locking_records_the_mentors_carrying_students(api, db, world, login, cssi):
    a, b, _ = _allocated(api, db, world, login, cssi)
    response = _lock(api, login, world, cssi)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mentor_allocation_locked_at"] is not None
    assert set(body["mentor_allocation_ids"]) == {a.id, b.id}
    assert db.query(AuditLog).filter(AuditLog.description.like("Mentor allocation locked%")).count() == 1


def test_an_allocation_with_students_waiting_cannot_be_locked(api, db, world, login, cssi):
    a = _faculty(db, world, "Alpha Mentor")
    _enrol(db, world, cssi, 12)
    _assign(api, login, world, cssi, allocate_by_roll_no=True, faculty_ids=[a.id])   # 10 of 12
    response = _lock(api, login, world, cssi)
    assert response.status_code in (400, 409, 422)
    assert "2 students still need a mentor" in response.text


def test_no_run_or_reset_touches_a_locked_allocation(api, db, world, login, cssi):
    a, b, _ = _allocated(api, db, world, login, cssi)
    _lock(api, login, world, cssi)
    before = _loads(db, cssi)
    for body in ({"allocate_by_roll_no": True}, {"auto_distribute": True},
                 {"rebalance": True}, {"clear_all": True}):
        response = _assign(api, login, world, cssi, **body)
        assert response.status_code in (400, 409, 422), body
    assert _loads(db, cssi) == before


def test_a_student_moves_only_to_a_mentor_in_the_allocation(api, db, world, login, cssi):
    a, b, rows = _allocated(api, db, world, login, cssi)
    outsider = _faculty(db, world, "Gamma Mentor")
    _lock(api, login, world, cssi)
    headers = login(world.cssi_ict.email)
    url = f"/api/v1/internships/enrollments/{rows[0].id}/mentor"
    assert api.post(url, headers=headers, json={"mentor_faculty_id": outsider.id}).status_code in (400, 409, 422)
    assert api.post(url, headers=headers, json={"mentor_faculty_id": b.id}).status_code == 200


def test_an_added_mentor_can_then_take_students(api, db, world, login, cssi):
    a, b, rows = _allocated(api, db, world, login, cssi)
    c = _faculty(db, world, "Gamma Mentor")
    _lock(api, login, world, cssi)
    headers = login(world.cssi_ict.email)
    assert api.post(_url(cssi, "/mentors"), headers=headers, json={"faculty_id": c.id}).status_code == 200
    db.refresh(cssi)
    assert c.id in mentor_allocation.allocated_ids(cssi)
    url = f"/api/v1/internships/enrollments/{rows[0].id}/mentor"
    assert api.post(url, headers=headers, json={"mentor_faculty_id": c.id}).status_code == 200


def test_removing_a_mentor_moves_their_students_within_the_cap(api, db, world, login, cssi):
    a, b, _ = _allocated(api, db, world, login, cssi, students=12)   # 6 + 6
    _lock(api, login, world, cssi)
    headers = login(world.cssi_ict.email)
    # 6 + 6 would pass the cap of 10.
    refused = api.delete(_url(cssi, f"/mentors/{a.id}?move_to={b.id}"), headers=headers)
    assert refused.status_code in (400, 409, 422)
    assert _loads(db, cssi) == {a.id: 6, b.id: 6}
    # Without a target, the students wait for a mentor.
    assert api.delete(_url(cssi, f"/mentors/{a.id}"), headers=headers).status_code == 200
    db.refresh(cssi)
    assert _loads(db, cssi) == {b.id: 6}
    assert mentor_allocation.allocated_ids(cssi) == [b.id]


def test_replacing_a_mentor_hands_over_the_whole_block(api, db, world, login, cssi):
    a, b, _ = _allocated(api, db, world, login, cssi)
    c = _faculty(db, world, "Gamma Mentor")
    _lock(api, login, world, cssi)
    before = _loads(db, cssi)
    response = api.put(_url(cssi, f"/mentors/{a.id}"), headers=login(world.cssi_ict.email),
                       json={"new_faculty_id": c.id})
    assert response.status_code == 200, response.text
    assert _loads(db, cssi) == {c.id: before[a.id], b.id: before[b.id]}
    db.refresh(cssi)
    assert set(mentor_allocation.allocated_ids(cssi)) == {b.id, c.id}


def test_after_unlocking_the_allocation_can_run_again(api, db, world, login, cssi):
    _allocated(api, db, world, login, cssi)
    _lock(api, login, world, cssi)
    assert api.post(_url(cssi, "/unlock"), headers=login(world.cssi_ict.email)).status_code == 200
    assert _assign(api, login, world, cssi, allocate_by_roll_no=True).status_code == 200


def test_another_modules_coordinator_cannot_lock_or_change_it(api, db, world, login, cssi):
    a, _b, _ = _allocated(api, db, world, login, cssi)
    other = login(world.summer_cse.email)
    assert api.post(_url(cssi, "/lock"), headers=other).status_code == 403
    _lock(api, login, world, cssi)
    assert api.delete(_url(cssi, f"/mentors/{a.id}"), headers=other).status_code == 403
    assert api.post(_url(cssi, "/unlock"), headers=other).status_code == 403
