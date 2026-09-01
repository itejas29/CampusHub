"""Scoped coordination: a role is (domain × department), not a global flag."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.models.enums import CoordinationDomain, Role


def _assignment(domain, department_id, active=True,
                role=None, starts_on=None, ends_on=None):
    from app.models.enums import AssignedRole
    from app.models.identity import FacultyRoleAssignment

    row = SimpleNamespace(
        domain=domain, department_id=department_id, is_active=active,
        role=role or AssignedRole.COORDINATOR,
        starts_on=starts_on, ends_on=ends_on,
    )
    # Reuse the model's own validity rule rather than restating it here.
    row.is_current = lambda on=None: FacultyRoleAssignment.is_current(row, on)
    return row


def _mentor(domain, department_id, **kw):
    from app.models.enums import AssignedRole

    return _assignment(domain, department_id, role=AssignedRole.MENTOR, **kw)


class _Faculty:
    """Exercises the pure scope rule without a session or ORM instrumentation.

    `Faculty.coordinates` delegates to `scope_matches`, so this covers the same
    logic the model uses.
    """

    def __init__(self, department_id, assignments):
        self.department_id = department_id
        self.role_assignments = assignments

    def coordinates(self, domain, department_id=None):
        from app.models.enums import AssignedRole
        from app.models.identity import scope_matches

        return scope_matches(self.role_assignments, domain, department_id,
                             role=AssignedRole.COORDINATOR)

    def mentors(self, domain, department_id=None):
        from app.models.enums import AssignedRole
        from app.models.identity import scope_matches

        return scope_matches(self.role_assignments, domain, department_id,
                             role=AssignedRole.MENTOR)


def _faculty(department_id, assignments):
    return _Faculty(department_id, assignments)


ICT, CSE = 1, 2


def test_coordination_is_scoped_to_its_department():
    """The ICT summer coordinator has no rights over CSE's programme."""
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.SUMMER_INTERNSHIP, ICT),
    ])
    assert faculty.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, ICT)
    assert not faculty.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, CSE)


def test_coordination_is_scoped_to_its_domain():
    """A Summer Internship coordinator is not a CSSI coordinator."""
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.SUMMER_INTERNSHIP, ICT),
    ])
    assert not faculty.coordinates(CoordinationDomain.CSSI, ICT)


def test_two_faculty_can_hold_the_same_domain_for_different_departments():
    ict_lead = _faculty(ICT, [_assignment(CoordinationDomain.SUMMER_INTERNSHIP, ICT)])
    cse_lead = _faculty(CSE, [_assignment(CoordinationDomain.SUMMER_INTERNSHIP, CSE)])
    assert ict_lead.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, ICT)
    assert not ict_lead.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, CSE)
    assert cse_lead.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, CSE)
    assert not cse_lead.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, ICT)


def test_one_faculty_can_hold_several_coordinations():
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.SUMMER_INTERNSHIP, ICT),
        _assignment(CoordinationDomain.MOOC, ICT),
    ])
    assert faculty.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, ICT)
    assert faculty.coordinates(CoordinationDomain.MOOC, ICT)
    assert not faculty.coordinates(CoordinationDomain.MINOR, ICT)


def test_department_less_assignment_is_institution_wide():
    faculty = _faculty(ICT, [_assignment(CoordinationDomain.MOOC, None)])
    for department in (ICT, CSE, 99):
        assert faculty.coordinates(CoordinationDomain.MOOC, department)


def test_revoked_assignment_grants_nothing():
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.CSSI, ICT, active=False),
    ])
    assert not faculty.coordinates(CoordinationDomain.CSSI, ICT)


def test_faculty_with_no_assignment_coordinates_nothing():
    faculty = _faculty(ICT, [])
    for domain in CoordinationDomain:
        assert not faculty.coordinates(domain, ICT)


@pytest.mark.parametrize("program_type,expected", [
    ("CSSI", CoordinationDomain.CSSI),
    ("SUMMER", CoordinationDomain.SUMMER_INTERNSHIP),
])
def test_internship_programme_maps_to_its_governing_domain(program_type, expected):
    from app.services.scope import domain_for_program

    program = SimpleNamespace(type=SimpleNamespace(value=program_type))
    assert domain_for_program(program) is expected


def test_every_domain_has_a_label_in_the_admin_api():
    """A new domain must not appear in the UI without a human-readable label."""
    from app.api.v1.roles import DOMAIN_LABELS

    for domain in CoordinationDomain:
        assert domain in DOMAIN_LABELS, domain


def test_super_admin_bypasses_scope():
    from app.services.scope import UNSCOPED_ROLES

    assert Role.SUPER_ADMIN in UNSCOPED_ROLES
    assert Role.INTERNSHIP_COORDINATOR not in UNSCOPED_ROLES
    assert Role.DEPARTMENT_ADMIN not in UNSCOPED_ROLES



# ── Coordinator and Mentor are independent grants ─────────────────────────
def test_a_mentor_is_not_a_coordinator():
    """Mentoring CSSI students grants no administrative control over CSSI."""
    faculty = _faculty(ICT, [_mentor(CoordinationDomain.CSSI, ICT)])
    assert faculty.mentors(CoordinationDomain.CSSI, ICT)
    assert not faculty.coordinates(CoordinationDomain.CSSI, ICT)


def test_a_coordinator_is_not_a_mentor():
    """Running the module does not make someone a mentee's mentor."""
    faculty = _faculty(ICT, [_assignment(CoordinationDomain.CSSI, ICT)])
    assert faculty.coordinates(CoordinationDomain.CSSI, ICT)
    assert not faculty.mentors(CoordinationDomain.CSSI, ICT)


def test_one_user_may_hold_both_roles_at_once():
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.MOOC, ICT),
        _mentor(CoordinationDomain.SUMMER_INTERNSHIP, ICT),
    ])
    assert faculty.coordinates(CoordinationDomain.MOOC, ICT)
    assert faculty.mentors(CoordinationDomain.SUMMER_INTERNSHIP, ICT)
    # Neither grant leaks into the other's module.
    assert not faculty.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, ICT)
    assert not faculty.mentors(CoordinationDomain.MOOC, ICT)


def test_one_role_never_removes_another():
    """Revoking the mentor grant leaves the coordination intact."""
    coordination = _assignment(CoordinationDomain.MOOC, ICT)
    mentorship = _mentor(CoordinationDomain.MOOC, ICT)
    faculty = _faculty(ICT, [coordination, mentorship])

    mentorship.is_active = False
    assert not faculty.mentors(CoordinationDomain.MOOC, ICT)
    assert faculty.coordinates(CoordinationDomain.MOOC, ICT)


def test_coordinating_one_module_grants_nothing_over_another():
    """The exact leak scoped assignments exist to prevent."""
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.SUMMER_INTERNSHIP, ICT),
    ])
    assert faculty.coordinates(CoordinationDomain.SUMMER_INTERNSHIP, ICT)
    assert not faculty.coordinates(CoordinationDomain.CSSI, ICT)
    assert not faculty.coordinates(CoordinationDomain.MOOC, ICT)
    assert not faculty.coordinates(CoordinationDomain.MINOR, ICT)


# ── validity windows ──────────────────────────────────────────────────────
def test_an_assignment_grants_nothing_before_it_starts():
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.MINOR, ICT, starts_on=dt.date(2030, 1, 1)),
    ])
    assert not faculty.coordinates(CoordinationDomain.MINOR, ICT)


def test_an_expired_assignment_grants_nothing():
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.MINOR, ICT, ends_on=dt.date(2020, 12, 31)),
    ])
    assert not faculty.coordinates(CoordinationDomain.MINOR, ICT)


def test_an_open_ended_window_is_current():
    faculty = _faculty(ICT, [
        _assignment(CoordinationDomain.MINOR, ICT,
                    starts_on=dt.date(2020, 1, 1), ends_on=None),
    ])
    assert faculty.coordinates(CoordinationDomain.MINOR, ICT)


def test_assignments_for_returns_the_union_across_roles():
    from app.models.enums import AssignedRole
    from app.models.identity import assignments_for

    held = [
        _assignment(CoordinationDomain.MOOC, ICT),
        _mentor(CoordinationDomain.CSSI, ICT),
        _assignment(CoordinationDomain.MINOR, ICT, active=False),
    ]
    assert len(assignments_for(held)) == 2
    assert len(assignments_for(held, AssignedRole.COORDINATOR)) == 1
    assert len(assignments_for(held, AssignedRole.MENTOR)) == 1
