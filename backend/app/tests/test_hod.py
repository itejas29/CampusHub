"""The Head of Department: what the post grants, and what it rules out.

Three rules, each of which is easy to break by accident:

* **Only a department's own HoD appoints into it.** Coordinator assignment used
  to hang off `faculty:manage`, with no department check, so any internship
  coordinator could appoint anyone anywhere. It is now the HoD's alone — and
  both sides have to be theirs: the scope granted and the person appointed.
* **The HoD holds no scoped role.** If they could appoint themselves, "sees
  everything, changes nothing" would last one click.
* **The HoD has no mentees** — academic or internship — and cannot be handed
  any by a route that forgets to ask.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.errors import BusinessRuleError
from app.core.rbac import P, permissions_for
from app.models.engagement import MentorAssignment
from app.models.enums import AssignedRole, CoordinationDomain, Role
from app.models.identity import FacultyRoleAssignment, UserRole
from app.services import internships as engine
from app.services import scope

NOW = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)
ROLES = "/api/v1/admin/roles"


@pytest.fixture
def hod(db, world):
    """`world.plain` — an ICT faculty member with no grants — made Head of ICT."""
    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)
    db.flush()
    return world.plain


def grant(world, account, *, domain="OPEN_ELECTIVE", dept="ICT", role="COORDINATOR"):
    return {
        "faculty_id": account.faculty.id, "role": role, "domain": domain,
        "department_id": world.departments[dept].id if dept else None,
    }


def roles_of(db, account):
    return set(db.scalars(select(UserRole.role).where(
        UserRole.user_id == account.user.id)))


# ── becoming the HoD ───────────────────────────────────────────────────────
def test_appointing_an_hod_sets_the_pointer_the_role_and_the_mentor_flag(db, world, hod):
    assert world.departments["ICT"].hod_faculty_id == hod.faculty.id
    assert Role.HOD in roles_of(db, hod)
    assert hod.faculty.is_mentor is False
    assert scope.hod_department(db, hod.user).code == "ICT"


def test_the_hod_role_carries_the_power_to_appoint_and_nothing_to_manage():
    granted = permissions_for([Role.HOD])
    assert P["ROLE_ASSIGN"] in granted
    assert not {p for p in granted if p.endswith(":manage")}
    assert P["INTERNSHIP_MENTOR"] not in granted
    assert P["MENTORSHIP_FACULTY"] not in granted


@pytest.mark.parametrize("role", [
    Role.FACULTY, Role.DEPARTMENT_ADMIN, Role.INTERNSHIP_COORDINATOR, Role.CLUB_ADMIN,
])
def test_no_other_staff_role_may_appoint(role):
    """Regression: `faculty:manage` used to be enough, and internship
    coordinators hold it."""
    assert P["ROLE_ASSIGN"] not in permissions_for([role])


def test_a_faculty_member_from_another_department_cannot_head_this_one(db, world):
    with pytest.raises(BusinessRuleError, match="not a member of ICT"):
        scope.set_hod(db, world.departments["ICT"], world.summer_cse.faculty)


def test_a_mentor_must_hand_over_before_becoming_hod(db, world):
    """`mentor_ict` holds a Mentor grant. The post is refused, not silently
    given to someone who still has mentoring work."""
    with pytest.raises(BusinessRuleError, match="Reassign these first"):
        scope.set_hod(db, world.departments["ICT"], world.mentor_ict.faculty)
    assert world.departments["ICT"].hod_faculty_id is None


def test_a_faculty_member_with_mentees_cannot_become_hod(db, world):
    db.add(MentorAssignment(student_id=world.student_a.student.id,
                            faculty_id=world.plain.faculty.id,
                            assigned_at=NOW, is_active=True))
    db.flush()
    with pytest.raises(BusinessRuleError, match="1 academic mentee"):
        scope.set_hod(db, world.departments["ICT"], world.plain.faculty)


def test_replacing_the_hod_takes_the_role_from_the_previous_one(db, world, hod):
    db.query(FacultyRoleAssignment).filter_by(
        faculty_id=world.summer_ict.faculty.id).update({"is_active": False})
    db.flush()
    db.refresh(world.summer_ict.faculty)

    scope.set_hod(db, world.departments["ICT"], world.summer_ict.faculty)
    db.flush()

    assert Role.HOD not in roles_of(db, hod)
    assert Role.HOD in roles_of(db, world.summer_ict)
    assert scope.hod_department(db, hod.user) is None


def test_clearing_the_post_removes_the_role(db, world, hod):
    scope.set_hod(db, world.departments["ICT"], None)
    db.flush()
    assert world.departments["ICT"].hod_faculty_id is None
    assert Role.HOD not in roles_of(db, hod)


# ── appointing coordinators ────────────────────────────────────────────────
def test_the_hod_appoints_a_coordinator_in_their_own_department(
        api, world, login, db, hod):
    response = api.post(ROLES, json=grant(world, world.cssi_ict),
                        headers=login(hod.email))
    assert response.status_code == 201, response.text
    assert response.json()["domain"] == "OPEN_ELECTIVE"
    db.refresh(world.cssi_ict.faculty)
    assert world.cssi_ict.faculty.coordinates(
        CoordinationDomain.OPEN_ELECTIVE, world.departments["ICT"].id)


def test_the_hod_removes_a_coordinator_in_their_own_department(
        api, world, login, db, hod):
    headers = login(hod.email)
    created = api.post(ROLES, json=grant(world, world.cssi_ict), headers=headers).json()

    response = api.delete(f"{ROLES}/{created['id']}", headers=headers)
    assert response.status_code == 200, response.text
    db.refresh(world.cssi_ict.faculty)
    assert not world.cssi_ict.faculty.coordinates(
        CoordinationDomain.OPEN_ELECTIVE, world.departments["ICT"].id)


def test_the_hod_cannot_appoint_into_another_department(api, world, login, hod):
    response = api.post(ROLES, json=grant(world, world.summer_cse, dept="CSE"),
                        headers=login(hod.email))
    assert response.status_code == 403
    assert "another department" in response.json()["error"]["message"]


def test_the_hod_cannot_appoint_another_departments_faculty_into_their_own(
        api, world, login, hod):
    """The scope is theirs, the person is not."""
    response = api.post(ROLES, json=grant(world, world.summer_cse, dept="ICT"),
                        headers=login(hod.email))
    assert response.status_code == 403
    assert "not a member of ICT" in response.json()["error"]["message"]


def test_the_hod_cannot_make_an_institution_wide_assignment(api, world, login, hod):
    response = api.post(ROLES, json=grant(world, world.cssi_ict, dept=None),
                        headers=login(hod.email))
    assert response.status_code == 403


def test_the_hod_cannot_revoke_another_departments_coordinator(
        api, world, login, db, hod):
    theirs = db.scalar(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.faculty_id == world.summer_cse.faculty.id))
    response = api.delete(f"{ROLES}/{theirs.id}", headers=login(hod.email))
    assert response.status_code == 403
    db.refresh(theirs)
    assert theirs.is_active is True


def test_the_hod_cannot_move_a_grant_into_another_department(
        api, world, login, db, hod):
    headers = login(hod.email)
    created = api.post(ROLES, json=grant(world, world.cssi_ict), headers=headers).json()
    response = api.patch(f"{ROLES}/{created['id']}", headers=headers,
                         json={"department_id": world.departments["CSE"].id})
    assert response.status_code == 403


@pytest.fixture
def others(db, world):
    """The accounts that could appoint before, and must not be able to now."""
    db.add(UserRole(user_id=world.summer_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    db.add(UserRole(user_id=world.cssi_ict.user.id, role=Role.DEPARTMENT_ADMIN))
    db.flush()
    return {"internship coordinator": world.summer_ict,
            "department admin": world.cssi_ict,
            "plain faculty": world.mentor_ict}


@pytest.mark.parametrize("who", ["internship coordinator", "department admin",
                                 "plain faculty"])
def test_nobody_but_the_hod_can_appoint_or_even_list(api, world, login, others, who):
    headers = login(others[who].email)
    assert api.post(ROLES, json=grant(world, world.plain), headers=headers).status_code == 403
    assert api.get(ROLES, headers=headers).status_code == 403
    assert api.get(f"{ROLES}/matrix", headers=headers).status_code == 403


def test_the_registrar_can_still_appoint_anywhere(api, world, login):
    response = api.post(ROLES, json=grant(world, world.summer_cse, dept="CSE",
                                          domain="OPEN_ELECTIVE"),
                        headers=login(world.admin.email))
    assert response.status_code == 201, response.text


# ── the HoD holds no scoped role ───────────────────────────────────────────
@pytest.mark.parametrize("role", ["COORDINATOR", "MENTOR"])
def test_the_hod_cannot_appoint_themselves(api, world, login, hod, role):
    response = api.post(ROLES, json=grant(world, hod, role=role),
                        headers=login(hod.email))
    assert response.status_code == 409
    assert "does not hold one of these roles" in response.json()["error"]["message"]


def test_not_even_the_registrar_can_give_the_hod_a_module(api, world, login, hod):
    response = api.post(ROLES, json=grant(world, hod), headers=login(world.admin.email))
    assert response.status_code == 409


# ── the HoD has no mentees ─────────────────────────────────────────────────
def test_the_hod_cannot_be_made_a_students_mentor(api, world, login, hod):
    response = api.post(
        "/api/v1/mentorship/assignments", headers=login(world.admin.email),
        params={"student_id": world.student_a.student.id, "faculty_id": hod.faculty.id})
    assert response.status_code == 409
    assert "does not take mentees" in response.json()["error"]["message"]


def test_the_hod_cannot_be_made_an_internship_mentor(db, world, hod):
    """Every internship mentor change — single, bulk, auto-allocation — goes
    through this one service function, so this is the only place to hold it."""
    enrollment = SimpleNamespace(id=1, program_id=1, mentor_faculty_id=None, status=None)
    with pytest.raises(BusinessRuleError, match="does not take mentees"):
        engine.override_mentor(db, enrollment=enrollment,
                               new_faculty_id=hod.faculty.id, reason="test")
    assert enrollment.mentor_faculty_id is None


def test_the_mentor_flag_cannot_be_switched_back_on_for_the_hod(
        api, world, login, hod):
    response = api.patch(f"/api/v1/faculty/{hod.faculty.id}",
                         headers=login(world.admin.email), json={"is_mentor": True})
    assert response.status_code == 409
    assert hod.faculty.is_mentor is False


def test_an_ordinary_faculty_member_can_still_be_a_mentor(api, world, login, hod):
    response = api.post(
        "/api/v1/mentorship/assignments", headers=login(world.admin.email),
        params={"student_id": world.student_a.student.id,
                "faculty_id": world.mentor_ict.faculty.id})
    assert response.status_code == 200, response.text


# ── what the HoD sees ──────────────────────────────────────────────────────
def test_the_hod_sees_only_their_own_departments_assignments(api, world, login, hod):
    headers = login(hod.email)
    listed = api.get(ROLES, headers=headers).json()
    assert listed and {row["department_code"] for row in listed} == {"ICT"}

    matrix = api.get(f"{ROLES}/matrix", headers=headers).json()
    assert {row["department_code"] for row in matrix["coverage"]} == {"ICT"}
    assert {row["department_code"] for row in matrix["gaps"]} == {"ICT"}
    assert {row["department_code"] for row in matrix["faculty_summary"]} == {"ICT"}


def test_the_matrix_marks_the_hod_so_they_are_not_offered_as_an_appointee(
        api, world, login, hod):
    summary = api.get(f"{ROLES}/matrix", headers=login(hod.email)).json()["faculty_summary"]
    flagged = {row["name"] for row in summary if row["is_hod"]}
    assert flagged == {hod.user.full_name}


def test_who_am_i_names_the_department_the_hod_heads(api, world, login, hod):
    me = api.get("/api/v1/auth/me", headers=login(hod.email)).json()
    assert me["faculty"]["hod_department_code"] == "ICT"
    assert "HOD" in me["roles"] and "roles:assign" in me["permissions"]

    other = api.get("/api/v1/auth/me", headers=login(world.mentor_ict.email)).json()
    assert other["faculty"]["hod_department_id"] is None


def test_the_hod_dashboard_shows_every_module_and_which_have_nobody(
        api, world, login, hod):
    response = api.get("/api/v1/dashboard/hod", headers=login(hod.email))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["department"]["code"] == "ICT"
    modules = {m["domain"]: m for m in body["modules"]}
    assert set(modules) == {d.value for d in CoordinationDomain}
    # Seeded by the fixture: ICT has a Summer and a CSSI coordinator and a CSSI
    # mentor. A mentor alone does not cover a module.
    assert modules["SUMMER_INTERNSHIP"]["is_covered"] is True
    assert modules["CSSI"]["is_covered"] is True and modules["CSSI"]["mentor_count"] == 1
    assert modules["OPEN_ELECTIVE"]["is_covered"] is False
    uncovered = next(s for s in body["stats"] if s["key"] == "uncovered")
    # Every module but the two the fixture covers.
    assert uncovered["value"] == len(CoordinationDomain) - 2


def test_the_hod_dashboard_is_only_for_an_hod(api, world, login, hod):
    response = api.get("/api/v1/dashboard/hod", headers=login(world.mentor_ict.email))
    assert response.status_code == 403


def test_the_departments_list_names_its_head(api, world, login, hod):
    rows = api.get("/api/v1/departments", headers=login(world.mentor_ict.email)).json()
    by_code = {row["code"]: row for row in rows}
    assert by_code["ICT"]["hod_name"] == hod.user.full_name
    assert by_code["CSE"]["hod_name"] is None


def test_only_the_registrar_appoints_an_hod(api, world, login, hod):
    url = f"/api/v1/departments/{world.departments['CSE'].id}/hod"
    payload = {"faculty_id": world.summer_cse.faculty.id}
    assert api.put(url, json=payload, headers=login(hod.email)).status_code == 403

    # summer_cse still coordinates a module, so the post is refused until that
    # is handed over — through the API as well as the service.
    refused = api.put(url, json=payload, headers=login(world.admin.email))
    assert refused.status_code == 409
