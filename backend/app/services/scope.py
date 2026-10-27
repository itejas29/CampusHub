"""Scope resolution: *what slice* of the institution a user may act on.

`app/core/rbac.py` answers "what kind of thing may this user do". This module
answers "over which department / module". The two are checked together:
a Summer Internship coordinator for ICT holds `internships:manage`, but only
for Summer Internship programmes belonging to ICT.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    INTERNSHIP_DOMAIN_FOR_TYPE, INTERNSHIP_DOMAINS, AssignedRole, CoordinationDomain, Role,
)
from app.models.identity import (
    Department, Faculty, FacultyRoleAssignment, User, UserRole, assignments_for,
    scope_matches,
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
    #: Not an appointment: the HoD covering a seat nobody holds (`acting_seats`).
    acting: bool = False

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
    held = [
        Coordination(
            role=a.role,
            domain=a.domain,
            department_id=a.department_id,
            department_code=a.department.code if a.department else None,
            department_name=a.department.name if a.department else None,
        )
        for a in assignments_for(faculty.role_assignments, role)
    ]
    if role in (None, AssignedRole.COORDINATOR):
        department = hod_department(db, user) if user.has_role(Role.HOD) else None
        held += [
            Coordination(role=AssignedRole.COORDINATOR, domain=domain,
                         department_id=department.id, department_code=department.code,
                         department_name=department.name, acting=True)
            for domain in acting_seats(db, user)
        ]
    return held


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

    if faculty.coordinates(domain, department_id):
        return True
    # An empty seat falls to the department's Head (`acting_seats`).
    return domain in acting_seats(db, user, department_id)


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


def domain_for_program(program: InternshipProgram) -> CoordinationDomain | None:
    """The domain that governs an internship-engine programme, if any.

    Read from INTERNSHIP_DOMAIN_FOR_TYPE. An unmapped type used to fall back to
    Summer Internship, so a new programme type would quietly have been run by
    the Summer coordinator. Unmapped now means no coordinator role governs it,
    and only an institution-wide role can manage it.
    """
    return INTERNSHIP_DOMAIN_FOR_TYPE.get(program.type.value)


def can_manage_program(db: Session, user: User, program: InternshipProgram) -> bool:
    """Coordinator rights over one internship programme.

    Scoped by both the programme's *type* (CSSI vs Summer) and its department,
    so the ICT summer coordinator cannot touch Mechanical's programme or ICT's
    CSSI programme.
    """
    domain = domain_for_program(program)
    if domain is None:
        return user.has_role(*UNSCOPED_ROLES)
    return coordinates(db, user, domain, program.department_id)


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


# ── Head of Department ─────────────────────────────────────────────────────
# One rule set, in one place:
#   * the HoD of a department is `departments.hod_faculty_id`; `Role.HOD` is
#     only the coarse flag that carries the permissions, kept in step by
#     `set_hod` and never consulted for *which* department;
#   * the HoD appoints and removes that department's coordinators and mentors;
#   * the HoD reads every module in the department, and changes only those
#     nobody is appointed to coordinate — acting until someone is (`acting_seats`);
#   * the HoD holds no scoped role and has no mentees of any kind.
def hod_department(db: Session, user: User) -> Department | None:
    """The department this user heads, if any."""
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty is None:
        return None
    return db.scalar(select(Department).where(Department.hod_faculty_id == faculty.id))


def seat_is_vacant(db: Session, domain: CoordinationDomain, department_id: int) -> bool:
    """No current Coordinator assignment covers `domain` in this department.

    An institution-wide coordinator covers every department; a Mentor grant
    covers none (Mentor and Coordinator are independent).
    """
    rows = db.scalars(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.role == AssignedRole.COORDINATOR,
        FacultyRoleAssignment.domain == domain,
        FacultyRoleAssignment.is_active.is_(True),
        (FacultyRoleAssignment.department_id == department_id)
        | FacultyRoleAssignment.department_id.is_(None),
    ))
    return not any(a.is_current() for a in rows)


def acting_seats(db: Session, user: User,
                 department_id: int | None = None) -> list[CoordinationDomain]:
    """The modules this user coordinates *as Head of Department*, because their
    department has nobody appointed to them.

    Decided by the project owner (27 Oct 2026): a seat left empty fell to nobody
    but the registrar and the module stopped. Computed on every check, never
    stored, so appointing anyone ends it and nothing is left behind.
    `department_id`, when given, must be the HoD's own department.
    """
    # The coarse role is kept in step with the department pointer by `set_hod`,
    # so nobody else pays a query for this.
    if not user.has_role(Role.HOD):
        return []
    department = hod_department(db, user)
    if department is None or (department_id is not None and department_id != department.id):
        return []
    held = {a.domain for a in db.scalars(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.role == AssignedRole.COORDINATOR,
        FacultyRoleAssignment.is_active.is_(True),
        (FacultyRoleAssignment.department_id == department.id)
        | FacultyRoleAssignment.department_id.is_(None),
    )) if a.is_current()}
    return [domain for domain in CoordinationDomain if domain not in held]


def acting_permissions(db: Session, user: User) -> set[str]:
    """What covering a seat adds to the HoD's permissions — exactly what being
    appointed to it would add. Appointing an internship coordinator gives them
    `Role.INTERNSHIP_COORDINATOR` (`api/v1/roles.assign`); no other domain adds
    a role. Scope still narrows every action to the seats being covered."""
    from app.core.rbac import ROLE_PERMISSIONS

    if any(domain in INTERNSHIP_DOMAINS for domain in acting_seats(db, user)):
        return set(ROLE_PERMISSIONS[Role.INTERNSHIP_COORDINATOR])
    return set()


def effective_permissions(db: Session, user: User) -> set[str]:
    """The user's permissions, including any that covering a seat brings."""
    from app.core.rbac import permissions_for

    return permissions_for(user.roles) | acting_permissions(db, user)


def notify_if_seat_falls_to_hod(db: Session, domain: CoordinationDomain,
                                department_id: int | None, *, label: str) -> None:
    """Tell a department's HoD that a module is now theirs to cover.

    Called after a Coordinator assignment ends. An institution-wide assignment
    ending can empty the seat in every department."""
    from app.services import notifications
    from app.models.enums import NotificationType

    stmt = select(Department).where(Department.is_active.is_(True),
                                    Department.hod_faculty_id.is_not(None))
    if department_id is not None:
        stmt = stmt.where(Department.id == department_id)
    for department in db.scalars(stmt):
        if not seat_is_vacant(db, domain, department.id):
            continue
        head = db.get(Faculty, department.hod_faculty_id)
        notifications.notify(
            db, user_id=head.user_id, type=NotificationType.SYSTEM,
            title=f"You are now acting {label} coordinator for {department.code}",
            message=(f"{department.code} has no {label} coordinator. As Head of "
                     "Department you cover the module until someone is appointed; "
                     "appointing a coordinator hands it over."),
            link="/dashboard",
        )


def is_hod(db: Session, faculty: Faculty) -> bool:
    return db.scalar(
        select(Department.id).where(Department.hod_faculty_id == faculty.id)
    ) is not None


def oversees(db: Session, user: User, department_id: int | None) -> bool:
    """May `user` *read* everything in this department?

    Reading is not managing: every write path still asks `coordinates()`, which
    an HoD satisfies only for a seat nobody holds (`acting_seats`) — so
    oversight alone cannot be used to open or lock a round.
    """
    if user.has_role(*UNSCOPED_ROLES):
        return True
    department = hod_department(db, user)
    return department is not None and department.id == department_id


def assert_can_assign_roles(db: Session, user: User, *, department_id: int | None,
                            faculty: Faculty) -> None:
    """Only a department's own HoD appoints into it.

    Both sides must be theirs: the scope being granted *and* the person being
    appointed. Otherwise the ICT HoD could hand ICT's electives to a Mechanical
    faculty member, or — worse — hand out an institution-wide grant.
    """
    from app.core.errors import PermissionDeniedError

    if user.has_role(*UNSCOPED_ROLES):
        return
    department = hod_department(db, user)
    if department is None:
        raise PermissionDeniedError(
            "Only the Head of Department assigns coordinators and mentors."
        )
    if department_id is None:
        raise PermissionDeniedError(
            "An institution-wide assignment can only be made by the registrar's "
            "office, not by a Head of Department."
        )
    if department_id != department.id:
        raise PermissionDeniedError(
            f"You head {department.code}; you cannot assign roles in another "
            "department."
        )
    if faculty.department_id != department.id:
        raise PermissionDeniedError(
            f"{faculty.user.full_name} is not a member of {department.code}. "
            "A Head of Department appoints from their own department's faculty."
        )


def mentoring_load(db: Session, faculty: Faculty) -> list[str]:
    """Everything that currently makes this faculty member a mentor or a
    coordinator — what has to be handed over before they can become HoD."""
    from app.models.engagement import MentorAssignment

    load: list[str] = []
    mentees = db.scalar(select(func.count(MentorAssignment.id)).where(
        MentorAssignment.faculty_id == faculty.id,
        MentorAssignment.is_active.is_(True),
    )) or 0
    if mentees:
        load.append(f"{mentees} academic mentee(s)")
    interns = db.scalar(select(func.count(InternshipEnrollment.id)).where(
        InternshipEnrollment.mentor_faculty_id == faculty.id
    )) or 0
    if interns:
        load.append(f"{interns} internship student(s)")
    groups = db.scalar(select(func.count(InternshipGroup.id)).where(
        InternshipGroup.faculty_id == faculty.id
    )) or 0
    if groups:
        load.append(f"{groups} internship group(s)")
    grants = assignments_for(faculty.role_assignments)
    if grants:
        load.append(f"{len(grants)} coordinator or mentor assignment(s)")
    return load


def assert_can_mentor(db: Session, faculty: Faculty) -> None:
    """A Head of Department takes no mentees — academic or internship."""
    from app.core.errors import BusinessRuleError

    if is_hod(db, faculty):
        raise BusinessRuleError(
            f"{faculty.user.full_name} is the Head of Department and does not "
            "take mentees. Choose another faculty member."
        )


def assert_can_hold_scoped_role(db: Session, faculty: Faculty) -> None:
    """The HoD appoints coordinators; they are never one themselves.

    If they could be, "sees everything, changes nothing" would last exactly as
    long as it took them to appoint themselves.
    """
    from app.core.errors import BusinessRuleError

    if is_hod(db, faculty):
        raise BusinessRuleError(
            f"{faculty.user.full_name} is the Head of Department. The HoD "
            "appoints coordinators and mentors and does not hold one of these "
            "roles."
        )


def set_hod(db: Session, department: Department, faculty: Faculty | None) -> None:
    """Appoint (or clear) a department's head, keeping three facts in step: the
    department's pointer, the coarse role, and the mentor flag."""
    from app.core.errors import BusinessRuleError

    previous = (db.get(Faculty, department.hod_faculty_id)
                if department.hod_faculty_id else None)
    if faculty is not None:
        if faculty.department_id != department.id:
            raise BusinessRuleError(
                f"{faculty.user.full_name} is not a member of {department.code}."
            )
        if not faculty.is_active:
            raise BusinessRuleError("An inactive faculty member cannot be made HoD.")
        other = db.scalar(select(Department).where(
            Department.hod_faculty_id == faculty.id, Department.id != department.id))
        if other is not None:
            raise BusinessRuleError(
                f"{faculty.user.full_name} already heads {other.code}."
            )
        if previous is None or previous.id != faculty.id:
            load = mentoring_load(db, faculty)
            if load:
                raise BusinessRuleError(
                    f"{faculty.user.full_name} still has " + ", ".join(load)
                    + ". Reassign these first: a Head of Department holds no "
                      "mentees and no coordinator or mentor role."
                )

    department.hod_faculty_id = faculty.id if faculty else None
    db.flush()

    if previous is not None and (faculty is None or previous.id != faculty.id):
        link = db.scalar(select(UserRole).where(
            UserRole.user_id == previous.user_id, UserRole.role == Role.HOD))
        if link is not None and not is_hod(db, previous):
            db.delete(link)
    if faculty is not None:
        faculty.is_mentor = False
        if not db.scalar(select(UserRole).where(
                UserRole.user_id == faculty.user_id, UserRole.role == Role.HOD)):
            db.add(UserRole(user_id=faculty.user_id, role=Role.HOD))
    db.flush()
