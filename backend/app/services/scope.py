"""Scope resolution: *what slice* of the institution a user may act on.

`app/core/rbac.py` answers "what kind of thing may this user do". This module
answers "over which department / module". The two are checked together:
a Summer Internship coordinator for ICT holds `internships:manage`, but only
for Summer Internship programmes belonging to ICT.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    INTERNSHIP_DOMAIN_FOR_TYPE, AssignedRole, CoordinationDomain, Role,
)
from app.models.identity import (
    Faculty, FacultyRoleAssignment, User, assignments_for, scope_matches,
)
from app.models.internships import InternshipEnrollment, InternshipGroup, InternshipProgram

#: Roles that are institution-wide by definition and bypass scope checks.
UNSCOPED_ROLES = (Role.SUPER_ADMIN,)


@dataclass(slots=True)
class Coordination:
    role: AssignedRole
    domain: CoordinationDomain
    department_id: int | None
    department_code: str | None
    department_name: str | None

    @property
    def is_institution_wide(self) -> bool:
        return self.department_id is None


def coordinations_for(db: Session, user: User,
                      role: AssignedRole | None = None) -> list[Coordination]:
    """Every current scoped assignment this user holds, resolved for the API/UI.

    Pass `role` to narrow to Coordinator or Mentor grants; omit it to get the
    union, which is what the profile and the admin matrix show.
    """
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty is None:
        return []
    return [
        Coordination(
            role=a.role,
            domain=a.domain,
            department_id=a.department_id,
            department_code=a.department.code if a.department else None,
            department_name=a.department.name if a.department else None,
        )
        for a in assignments_for(faculty.role_assignments, role)
    ]


def coordinates(db: Session, user: User, domain: CoordinationDomain,
                department_id: int | None = None) -> bool:
    """Does `user` coordinate `domain` over `department_id`?

    SUPER_ADMIN always does. DEPARTMENT_ADMIN does within their own department.
    """
    if user.has_role(*UNSCOPED_ROLES):
        return True

    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty is None:
        return False

    # A department administrator coordinates everything inside their department.
    if user.has_role(Role.DEPARTMENT_ADMIN):
        if department_id is None or faculty.department_id == department_id:
            return True

    return faculty.coordinates(domain, department_id)


class MinorScopeRule(str):
    """How a Minor coordinator's department scope is interpreted.

    Two readings are defensible and the university has not confirmed which
    applies, so neither is hard-coded:

    ``OFFERING``  the coordinator runs the minors their department *offers* —
                  its seats, its ranking policy, its allocation rounds.
    ``APPLICANT`` the coordinator handles minor applications *from students of*
                  their department, whichever department offers the minor.
    ``EITHER``    a match on either side is enough.

    Until the policy is confirmed the default is ``EITHER``, which grants access
    when either reading would — deliberately the permissive end, because the
    alternative is silently locking a real coordinator out of work that is
    plausibly theirs. Set `MINOR_COORDINATOR_SCOPE` once the rule is known.
    """

    OFFERING = "OFFERING"
    APPLICANT = "APPLICANT"
    EITHER = "EITHER"


def minor_scope_rule() -> str:
    """The configured interpretation. Never inferred from the data."""
    from app.core.config import settings

    return getattr(settings, "MINOR_COORDINATOR_SCOPE", MinorScopeRule.EITHER)


def can_manage_minor(db: Session, user: User, program,
                     applicant_department_id: int | None = None) -> bool:
    """Coordinator rights over one minor programme.

    `applicant_department_id` is the department of the student whose application
    is being acted on, and is only consulted under the APPLICANT reading. Pass it
    whenever the action concerns a specific applicant; omit it for programme-wide
    actions such as configuring seats.
    """
    rule = minor_scope_rule()
    offering_side = coordinates(db, user, CoordinationDomain.MINOR,
                                program.department_id)
    if rule == MinorScopeRule.OFFERING:
        return offering_side

    applicant_side = (
        applicant_department_id is not None
        and coordinates(db, user, CoordinationDomain.MINOR, applicant_department_id)
    )
    if rule == MinorScopeRule.APPLICANT:
        return applicant_side
    return offering_side or applicant_side


def assert_manages_minor(db: Session, user: User, program,
                         applicant_department_id: int | None = None) -> None:
    from app.core.errors import PermissionDeniedError

    if can_manage_minor(db, user, program, applicant_department_id):
        return
    raise PermissionDeniedError(
        "You do not coordinate minor specialisation for this scope."
    )


def domain_for_program(program: InternshipProgram) -> CoordinationDomain:
    """Map an internship programme onto the domain that governs it."""
    return {
        "CSSI": CoordinationDomain.CSSI,
        "SUMMER": CoordinationDomain.SUMMER_INTERNSHIP,
    }.get(program.type.value, CoordinationDomain.SUMMER_INTERNSHIP)


def can_manage_program(db: Session, user: User, program: InternshipProgram) -> bool:
    """Coordinator rights over one internship programme.

    Scoped by both the programme's *type* (CSSI vs Summer) and its department,
    so the ICT summer coordinator cannot touch Mechanical's programme or ICT's
    CSSI programme.
    """
    return coordinates(db, user, domain_for_program(program), program.department_id)


def managed_program_ids(db: Session, user: User) -> list[int] | None:
    """Programme ids this user may administer, or None meaning 'all'."""
    if user.has_role(*UNSCOPED_ROLES):
        return None
    programs = list(db.scalars(select(InternshipProgram)))
    return [p.id for p in programs if can_manage_program(db, user, p)]


def mentored_program_types(db: Session, user: User) -> list[str]:
    """Internship types this faculty actually mentors students for.

    Drives navigation: a faculty member who was never made a mentor should not
    see a "CSSI Students" or "SI Students" screen at all.
    """
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty is None:
        return []

    # Direct mentor on an enrolment, or faculty-in-charge of a group.
    direct = db.scalars(
        select(InternshipProgram.type)
        .join(InternshipEnrollment,
              InternshipEnrollment.program_id == InternshipProgram.id)
        .where(InternshipEnrollment.mentor_faculty_id == faculty.id)
        .distinct()
    )
    via_group = db.scalars(
        select(InternshipProgram.type)
        .join(InternshipGroup, InternshipGroup.program_id == InternshipProgram.id)
        .where(InternshipGroup.faculty_id == faculty.id)
        .distinct()
    )
    types = {t.value for t in direct} | {t.value for t in via_group}

    # An explicit Mentor assignment counts even before any student is allocated,
    # so a newly appointed mentor sees the screen straight away. Coordinator
    # assignments deliberately do NOT count — coordinating a module never makes
    # someone a mentor.
    for assignment in assignments_for(faculty.role_assignments, AssignedRole.MENTOR):
        for program_type, domain in INTERNSHIP_DOMAIN_FOR_TYPE.items():
            if assignment.domain == domain:
                types.add(program_type)
    return sorted(types)


def mentors(db: Session, user: User, domain: CoordinationDomain,
            department_id: int | None = None) -> bool:
    """Does this user hold a Mentor assignment over that scope?

    Separate from `coordinates()` on purpose: the two roles are independent
    grants, and neither implies the other.
    """
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty is None:
        return False
    return scope_matches(faculty.role_assignments, domain, department_id,
                         role=AssignedRole.MENTOR)


def active_assignments(db: Session, user: User) -> list:
    """Every current scoped assignment this user holds, across all roles.

    Permissions are the *union* of these — one assignment never removes what
    another grants.
    """
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    return assignments_for(faculty.role_assignments) if faculty else []


def assert_coordinates(db: Session, user: User, domain: CoordinationDomain,
                       department_id: int | None, *, permission: str,
                       what: str) -> None:
    """Require a Coordinator assignment covering `domain` × `department_id`.

    This is how a plain-FACULTY NPTEL coordinator for ICT can approve ICT
    certificates without being handed institution-wide `mooc:verify` — and,
    equally, why holding that coarse permission does not let them touch CSSI.
    """
    from app.core.errors import PermissionDeniedError
    from app.core.rbac import has_permission

    # A coarse permission alone is NOT enough. `Role.INTERNSHIP_COORDINATOR`
    # carries institution-wide `internships:manage`, so short-circuiting on it
    # would let the ICT *Summer* coordinator manage ICT's CSSI — the exact
    # cross-module leak scoped assignments exist to prevent. Only genuinely
    # institution-wide roles bypass, and DEPARTMENT_ADMIN is handled inside
    # `coordinates()` for its own department.
    if user.has_role(*UNSCOPED_ROLES) and has_permission(user.roles, permission):
        return
    if coordinates(db, user, domain, department_id):
        return
    raise PermissionDeniedError(
        f"You are not the {what} coordinator for this department."
    )


def student_department_id(db: Session, student_id: int) -> int | None:
    from app.models.identity import Student

    student = db.get(Student, student_id)
    return student.department_id if student else None
