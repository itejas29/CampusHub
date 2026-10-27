"""A module nobody coordinates falls to the department's Head.

Decided by the project owner on 27 Oct 2026. Removing the last coordinator of a
module used to leave it to nobody but the registrar, so the module stopped:
no one could open a round or allocate a mentor. Now the HoD of that department
acts as its coordinator until someone is appointed.

It is computed, never stored. The HoD still holds no assignment and takes no
mentees; the moment anyone is appointed to the seat, the HoD stops acting, and
there is nothing left to clean up. An acting HoD gets exactly what an appointed
coordinator of that seat would get — the same scope, the same permissions —
and nothing over a module that has a coordinator.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.engagement import Notification
from app.models.enums import AssignedRole, CoordinationDomain, InternshipType
from app.models.identity import FacultyRoleAssignment
from app.models.internships import InternshipProgram
from app.services import scope

ROLES = "/api/v1/admin/roles"
D = CoordinationDomain


@pytest.fixture
def hod(db, world):
    """`world.plain` — an ICT faculty member with no grants — made Head of ICT.

    ICT has a CSSI and a Summer Internship coordinator; every other module in
    ICT has nobody."""
    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)
    db.flush()
    return world.plain


def ict(world):
    return world.departments["ICT"].id


def seat(world, domain, holder, *, dept="ICT", role=AssignedRole.COORDINATOR, **extra):
    row = FacultyRoleAssignment(
        faculty_id=holder.faculty.id, role=role, domain=domain,
        department_id=world.departments[dept].id if dept else None, is_active=True,
        assigned_at=dt.datetime.now(dt.timezone.utc), **extra)
    world.db.add(row)
    world.db.flush()
    return row


def cssi_assignment(db, world):
    return db.scalar(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.faculty_id == world.cssi_ict.faculty.id))


# ── who acts, and where ────────────────────────────────────────────────────
def test_the_hod_coordinates_a_module_nobody_in_the_department_coordinates(db, world, hod):
    assert scope.coordinates(db, hod.user, D.OPEN_ELECTIVE, ict(world))
    assert scope.coordinates(db, hod.user, D.PROJECT, ict(world))


def test_the_hod_does_not_act_where_a_coordinator_is_appointed(db, world, hod):
    assert not scope.coordinates(db, hod.user, D.CSSI, ict(world))
    assert not scope.coordinates(db, hod.user, D.SUMMER_INTERNSHIP, ict(world))


def test_the_hod_acts_only_in_the_department_they_head(db, world, hod):
    assert not scope.coordinates(db, hod.user, D.OPEN_ELECTIVE, world.departments["CSE"].id)


def test_an_institution_wide_coordinator_fills_every_departments_seat(db, world, hod):
    seat(world, D.MOOC, world.summer_cse, dept=None)
    assert not scope.coordinates(db, hod.user, D.MOOC, ict(world))


def test_a_mentor_grant_does_not_fill_a_coordinator_seat(db, world, hod):
    """Mentor and Coordinator are independent grants: a module with mentors and
    no coordinator is still uncoordinated."""
    seat(world, D.OPEN_ELECTIVE, world.mentor_ict, role=AssignedRole.MENTOR)
    assert scope.coordinates(db, hod.user, D.OPEN_ELECTIVE, ict(world))


def test_an_assignment_that_has_ended_leaves_the_seat_to_the_hod(db, world, hod):
    cssi_assignment(db, world).ends_on = dt.date.today() - dt.timedelta(days=1)
    db.flush()
    assert scope.coordinates(db, hod.user, D.CSSI, ict(world))


def test_nobody_but_the_hod_picks_up_an_empty_seat(db, world, hod):
    for other in (world.mentor_ict, world.summer_ict, world.summer_cse):
        assert not scope.coordinates(db, other.user, D.OPEN_ELECTIVE, ict(world))


def test_a_department_with_no_head_leaves_the_seat_to_the_registrar(db, world):
    """CSE has no HoD in these fixtures: its empty seats stay empty."""
    assert not scope.coordinates(db, world.summer_cse.user, D.CSSI,
                                 world.departments["CSE"].id)
    assert scope.coordinates(db, world.admin, D.CSSI, world.departments["CSE"].id)


# ── the seat changes hands ─────────────────────────────────────────────────
def test_removing_the_last_coordinator_hands_the_module_to_the_hod(
        api, db, world, login, hod):
    response = api.delete(f"{ROLES}/{cssi_assignment(db, world).id}",
                          headers=login(world.admin.email))
    assert response.status_code == 200, response.text
    assert scope.coordinates(db, hod.user, D.CSSI, ict(world))


def test_the_hod_is_told_when_a_module_falls_to_them(api, db, world, login, hod):
    api.delete(f"{ROLES}/{cssi_assignment(db, world).id}", headers=login(world.admin.email))
    told = list(db.scalars(select(Notification).where(Notification.user_id == hod.user.id)))
    assert any("CSSI" in n.title and "acting" in n.title.lower() for n in told), \
        [n.title for n in told]


def test_the_hod_is_not_told_while_another_coordinator_still_holds_the_seat(
        api, db, world, login, hod):
    seat(world, D.CSSI, world.mentor_ict)          # a second CSSI coordinator
    api.delete(f"{ROLES}/{cssi_assignment(db, world).id}", headers=login(world.admin.email))
    assert not scope.coordinates(db, hod.user, D.CSSI, ict(world))
    told = db.scalars(select(Notification.title).where(Notification.user_id == hod.user.id))
    assert not any("acting" in t.lower() for t in told)


def test_switching_an_assignment_off_also_hands_the_seat_over(api, db, world, login, hod):
    response = api.patch(f"{ROLES}/{cssi_assignment(db, world).id}",
                         json={"is_active": False}, headers=login(world.admin.email))
    assert response.status_code == 200, response.text
    assert scope.coordinates(db, hod.user, D.CSSI, ict(world))
    told = db.scalars(select(Notification.title).where(Notification.user_id == hod.user.id))
    assert any("CSSI" in t for t in told)


def test_appointing_a_coordinator_ends_the_hods_acting(api, db, world, login, hod):
    assert scope.coordinates(db, hod.user, D.OPEN_ELECTIVE, ict(world))
    response = api.post(ROLES, json={
        "faculty_id": world.mentor_ict.faculty.id, "role": "COORDINATOR",
        "domain": "OPEN_ELECTIVE", "department_id": ict(world),
    }, headers=login(hod.email))
    assert response.status_code == 201, response.text
    assert not scope.coordinates(db, hod.user, D.OPEN_ELECTIVE, ict(world))


def test_the_hod_still_holds_no_assignment_and_cannot_be_given_one(
        api, db, world, login, hod):
    """Acting is not appointing: the old rule against appointing the HoD stands."""
    assert not db.scalars(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.faculty_id == hod.faculty.id)).all()
    response = api.post(ROLES, json={
        "faculty_id": hod.faculty.id, "role": "COORDINATOR",
        "domain": "OPEN_ELECTIVE", "department_id": ict(world),
    }, headers=login(world.admin.email))
    assert response.status_code == 409


# ── what the HoD's screens are told ────────────────────────────────────────
def me(api, login, account):
    response = api.get("/api/v1/auth/me", headers=login(account.email))
    assert response.status_code == 200, response.text
    return response.json()


def test_who_am_i_lists_the_seats_the_hod_is_covering(api, world, login, hod):
    seats = {(c["domain"], c.get("acting")) for c in me(api, login, hod)["faculty"]["coordinations"]}
    assert ("OPEN_ELECTIVE", True) in seats
    assert not any(domain == "CSSI" for domain, _ in seats)


def test_an_internship_seat_brings_the_internship_coordinators_permissions(
        api, world, login, hod):
    # PROJECT and MAJOR_PROJECT have nobody in ICT, so the HoD covers them.
    assert "internships:manage" in me(api, login, hod)["permissions"]


def test_no_internship_seat_means_no_internship_permissions(api, world, login, hod):
    for domain in (D.PROJECT, D.MAJOR_PROJECT):
        seat(world, domain, world.mentor_ict)
    assert "internships:manage" not in me(api, login, hod)["permissions"]


@pytest.fixture
def ict_cssi(db, world):
    program = InternshipProgram(code="CSSI-HOD", name="CSSI", type=InternshipType.CSSI,
                                department_id=ict(world))
    db.add(program)
    db.flush()
    return program


def test_the_acting_hod_can_run_a_module_whose_coordinator_was_removed(
        api, db, world, login, hod, ict_cssi):
    path = f"/api/v1/internships/programs/{ict_cssi.id}"
    assert api.patch(path, json={"description": "x"},
                     headers=login(hod.email)).status_code == 403
    api.delete(f"{ROLES}/{cssi_assignment(db, world).id}", headers=login(world.admin.email))
    response = api.patch(path, json={"description": "Run by the HoD until appointed"},
                         headers=login(hod.email))
    assert response.status_code == 200, response.text


def test_the_acting_hod_cannot_run_a_module_that_has_a_coordinator(
        api, world, login, hod, ict_cssi):
    """Covering PROJECT gives `internships:manage`, but CSSI has a coordinator."""
    response = api.patch(f"/api/v1/internships/programs/{ict_cssi.id}",
                         json={"description": "x"}, headers=login(hod.email))
    assert response.status_code == 403


def test_the_role_board_names_who_is_covering_each_empty_seat(api, world, login, hod):
    response = api.get(f"{ROLES}/matrix", headers=login(hod.email))
    assert response.status_code == 200, response.text
    gaps = {g["domain"]: g for g in response.json()["gaps"]}
    assert gaps["OPEN_ELECTIVE"]["acting_hod"] == hod.user.full_name
    assert "CSSI" not in gaps


def test_the_hod_dashboard_marks_the_modules_the_hod_is_covering(api, world, login, hod):
    response = api.get("/api/v1/dashboard/hod", headers=login(hod.email))
    assert response.status_code == 200, response.text
    modules = {m["domain"]: m for m in response.json()["modules"]}
    assert modules["OPEN_ELECTIVE"]["covered_by_hod"] is True
    assert modules["CSSI"]["covered_by_hod"] is False
