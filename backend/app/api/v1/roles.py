"""Coordinator role administration.

Only an administrator creates these assignments; coordinators then work inside
the scope granted here. The matrix endpoint answers the operational question
"who coordinates what, and which department has nobody?"
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import DbSession, require_permission
from app.core.errors import (
    BusinessRuleError, ConflictError, NotFoundError, ValidationError,
)
from app.core.rbac import P
from app.models.enums import (
    ASSIGNED_ROLE_CAPABILITIES, AssignedRole, AuditAction, CoordinationDomain,
    NotificationType, Role,
)
from app.models.identity import (
    AcademicYear, Department, Faculty, FacultyRoleAssignment, User, UserRole,
)
from app.schemas.common import Message
from app.schemas.identity import (
    DomainCoverage, RoleAssignmentCreate, RoleAssignmentOut, RoleAssignmentUpdate,
    RoleDefinition, RoleMatrix,
)
from app.services import audit, notifications

router = APIRouter(prefix="/admin/roles", tags=["admin"])

#: Domains that only make sense per department (everything, currently) versus
#: those an institution-wide assignment is reasonable for.
ROLE_LABELS = {
    AssignedRole.COORDINATOR: "Coordinator",
    AssignedRole.MENTOR: "Mentor",
}

DOMAIN_LABELS = {
    CoordinationDomain.CSSI: "CSSI",
    CoordinationDomain.SUMMER_INTERNSHIP: "Summer Internship",
    CoordinationDomain.MINOR: "Minor Specialisation",
    CoordinationDomain.MOOC: "NPTEL / MOOC",
    CoordinationDomain.OPEN_ELECTIVE: "Open Electives",
    CoordinationDomain.CORE_ELECTIVE: "Program Core Electives",
    CoordinationDomain.MENTORSHIP: "Mentor–Mentee",
}


def _out(assignment: FacultyRoleAssignment,
         year_label: str | None = None,
         assigner: str | None = None) -> RoleAssignmentOut:
    faculty = assignment.faculty
    department = assignment.department
    return RoleAssignmentOut(
        id=assignment.id, faculty_id=assignment.faculty_id,
        faculty_name=faculty.user.full_name if faculty else None,
        employee_code=faculty.employee_code if faculty else None,
        faculty_department_code=(faculty.department.code
                                 if faculty and faculty.department else None),
        designation=faculty.designation if faculty else None,
        role=assignment.role,
        role_label=ROLE_LABELS[assignment.role],
        domain=assignment.domain,
        domain_label=DOMAIN_LABELS[assignment.domain],
        department_id=assignment.department_id,
        department_code=department.code if department else None,
        department_name=department.name if department else None,
        is_institution_wide=assignment.department_id is None,
        academic_year_id=assignment.academic_year_id,
        academic_year_label=year_label,
        assigned_by_name=assigner, assigned_at=assignment.assigned_at,
        starts_on=assignment.starts_on, ends_on=assignment.ends_on,
        is_active=assignment.is_active, is_current=assignment.is_current(),
        notes=assignment.notes,
    )


def _load(db, assignment: FacultyRoleAssignment) -> RoleAssignmentOut:
    year = (db.get(AcademicYear, assignment.academic_year_id)
            if assignment.academic_year_id else None)
    assigner = (db.get(User, assignment.assigned_by_user_id)
                if assignment.assigned_by_user_id else None)
    return _out(assignment, year.label if year else None,
                assigner.full_name if assigner else None)


@router.get("/domains")
def domains(_: User = Depends(require_permission(P["FACULTY_MANAGE"]))) -> list[dict]:
    """The coordination vocabulary, for building the assignment form."""
    return [{"value": d.value, "label": DOMAIN_LABELS[d]} for d in CoordinationDomain]


@router.get("/definitions", response_model=list[RoleDefinition])
def role_definitions(
    _: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> list[RoleDefinition]:
    """The roles an administrator may grant, and what each permits in scope.

    Role *definition* and role *assignment* are separate: this endpoint answers
    "what roles exist", the collection below answers "who holds them, where".
    """
    return [
        RoleDefinition(value=role.value, label=ROLE_LABELS[role],
                       description=ASSIGNED_ROLE_CAPABILITIES[role])
        for role in AssignedRole
    ]


@router.get("", response_model=list[RoleAssignmentOut])
def list_assignments(
    db: DbSession,
    role: AssignedRole | None = Query(None),
    domain: CoordinationDomain | None = Query(None),
    department_id: int | None = Query(None),
    faculty_id: int | None = Query(None),
    include_inactive: bool = Query(False),
    _: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> list[RoleAssignmentOut]:
    stmt = select(FacultyRoleAssignment)
    if role:
        stmt = stmt.where(FacultyRoleAssignment.role == role)
    if domain:
        stmt = stmt.where(FacultyRoleAssignment.domain == domain)
    if department_id:
        stmt = stmt.where(FacultyRoleAssignment.department_id == department_id)
    if faculty_id:
        stmt = stmt.where(FacultyRoleAssignment.faculty_id == faculty_id)
    if not include_inactive:
        stmt = stmt.where(FacultyRoleAssignment.is_active.is_(True))
    return [_load(db, a) for a in db.scalars(stmt.order_by(
        FacultyRoleAssignment.role, FacultyRoleAssignment.domain,
        FacultyRoleAssignment.department_id,
    ))]


@router.get("/matrix", response_model=RoleMatrix)
def matrix(
    db: DbSession,
    _: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> RoleMatrix:
    """Who coordinates what, per department — including uncovered cells."""
    departments = list(db.scalars(
        select(Department).where(Department.is_active.is_(True))
        .order_by(Department.code)
    ))
    assignments = list(db.scalars(
        select(FacultyRoleAssignment)
        .where(FacultyRoleAssignment.is_active.is_(True))
    ))

    coverage: list[DomainCoverage] = []
    gaps: list[dict] = []

    for domain in CoordinationDomain:
        for department in departments:
            holders = [
                a for a in assignments
                if a.domain == domain
                and (a.department_id == department.id or a.department_id is None)
            ]
            leads = [a for a in holders if a.role == AssignedRole.COORDINATOR]
            guides = [a for a in holders if a.role == AssignedRole.MENTOR]
            if holders:
                coverage.append(DomainCoverage(
                    domain=domain, domain_label=DOMAIN_LABELS[domain],
                    department_id=department.id,
                    department_code=department.code, department_name=department.name,
                    coordinators=[_load(db, a) for a in leads],
                    mentors=[_load(db, a) for a in guides],
                ))
            # A gap is an *uncoordinated* module: mentors alone do not cover it.
            if not leads:
                gaps.append({
                    "domain": domain.value, "domain_label": DOMAIN_LABELS[domain],
                    "department_id": department.id,
                    "department_code": department.code,
                    "department_name": department.name,
                })

    # Per-faculty roll-up: every faculty member and what they hold.
    faculty_rows = list(db.scalars(select(Faculty).where(Faculty.is_active.is_(True))))
    summary = []
    for faculty in faculty_rows:
        held = [a for a in assignments if a.faculty_id == faculty.id]
        summary.append({
            "faculty_id": faculty.id,
            "name": faculty.user.full_name,
            "employee_code": faculty.employee_code,
            "designation": faculty.designation,
            "department_code": faculty.department.code if faculty.department else None,
            "roles": [r.role.value for r in db.scalars(
                select(UserRole).where(UserRole.user_id == faculty.user_id)
            )],
            # Every grant this person holds, of every role — the union, so one
            # assignment never hides another.
            "coordinations": [
                {
                    "id": a.id,
                    "role": a.role.value,
                    "role_label": ROLE_LABELS[a.role],
                    "domain": a.domain.value,
                    "domain_label": DOMAIN_LABELS[a.domain],
                    "department_code": (a.department.code if a.department
                                        else "All departments"),
                    "is_current": a.is_current(),
                }
                for a in held
            ],
        })
    summary.sort(key=lambda r: (-len(r["coordinations"]), r["name"]))

    return RoleMatrix(
        domains=[d.value for d in CoordinationDomain],
        roles=[RoleDefinition(value=r.value, label=ROLE_LABELS[r],
                              description=ASSIGNED_ROLE_CAPABILITIES[r])
               for r in AssignedRole],
        coverage=coverage, gaps=gaps, faculty_summary=summary,
    )


@router.post("", response_model=RoleAssignmentOut, status_code=201)
def assign(
    payload: RoleAssignmentCreate, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> RoleAssignmentOut:
    faculty = db.get(Faculty, payload.faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")
    if payload.department_id and db.get(Department, payload.department_id) is None:
        raise NotFoundError("Department not found.")

    existing = db.scalar(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.faculty_id == payload.faculty_id,
        FacultyRoleAssignment.role == payload.role,
        FacultyRoleAssignment.domain == payload.domain,
        FacultyRoleAssignment.department_id == payload.department_id,
        FacultyRoleAssignment.academic_year_id == payload.academic_year_id,
    ))
    if existing and existing.is_active:
        raise ConflictError(
            f"That faculty member is already {ROLE_LABELS[payload.role]} for "
            f"{DOMAIN_LABELS[payload.domain]} in this scope."
        )
    if existing:
        existing.is_active = True          # reinstate a revoked assignment
        existing.assigned_by_user_id = user.id
        existing.assigned_at = dt.datetime.now(dt.timezone.utc)
        assignment = existing
    else:
        assignment = FacultyRoleAssignment(
            **payload.model_dump(),
            assigned_by_user_id=user.id,
            assigned_at=dt.datetime.now(dt.timezone.utc),
        )
        db.add(assignment)
    db.flush()

    # Coordinating an internship implies the coarse role so route guards that
    # only look at `Role` still admit them. It grants no scope of its own —
    # `services/scope.assert_coordinates` requires a matching assignment, which
    # is why holding it for Summer Internship does not open CSSI.
    # A Mentor assignment deliberately does NOT grant it.
    if (payload.role is AssignedRole.COORDINATOR
            and payload.domain in (CoordinationDomain.CSSI,
                                   CoordinationDomain.SUMMER_INTERNSHIP)):
        _ensure_role(db, faculty.user_id, Role.INTERNSHIP_COORDINATOR)

    department = db.get(Department, payload.department_id) if payload.department_id else None
    scope_label = department.code if department else "all departments"
    # The faculty member gains navigation and review powers the moment this is
    # saved, so they are told rather than left to discover it.
    notifications.notify(
        db, user_id=faculty.user_id, type=NotificationType.SYSTEM,
        title=f"You are now {DOMAIN_LABELS[payload.domain]} "
              f"{ROLE_LABELS[payload.role].lower()}",
        message=(
            f"Assigned for {scope_label}. You can review submissions and assign "
            "mentors within this scope."
            if payload.role is AssignedRole.COORDINATOR
            else f"Assigned for {scope_label}. Students allocated to you appear "
                 "under your mentee screens."
        ),
        link="/dashboard",
    )
    audit.record(
        db, action=AuditAction.CREATE, entity_type="faculty_role_assignment",
        entity_id=assignment.id, actor=user,
        description=f"Assigned {DOMAIN_LABELS[payload.domain]} "
                    f"{ROLE_LABELS[payload.role].lower()} to "
                    f"{faculty.user.full_name} for {scope_label}",
        meta={"faculty_id": faculty.id, "role": payload.role.value,
              "domain": payload.domain.value,
              "department_id": payload.department_id,
              "starts_on": payload.starts_on.isoformat() if payload.starts_on else None,
              "ends_on": payload.ends_on.isoformat() if payload.ends_on else None},
    )
    db.commit()
    db.refresh(assignment)
    return _load(db, assignment)


def _ensure_role(db, user_id: int, role: Role) -> None:
    if not db.scalar(select(UserRole).where(UserRole.user_id == user_id,
                                            UserRole.role == role)):
        db.add(UserRole(user_id=user_id, role=role))


@router.delete("/{assignment_id}", response_model=Message)
def revoke(
    assignment_id: int, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> Message:
    assignment = db.get(FacultyRoleAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Role assignment not found.")
    assignment.is_active = False
    faculty = assignment.faculty

    # Drop the coarse role once no internship coordination remains.
    # Only a Coordinator grant put the coarse role there, so only losing the
    # last one takes it away. Revoking a Mentor grant must not strip a
    # Coordinator's access — one role never removes another's permissions.
    if (assignment.role is AssignedRole.COORDINATOR
            and assignment.domain in (CoordinationDomain.CSSI,
                                      CoordinationDomain.SUMMER_INTERNSHIP)):
        remaining = db.scalar(select(FacultyRoleAssignment).where(
            FacultyRoleAssignment.faculty_id == assignment.faculty_id,
            FacultyRoleAssignment.id != assignment.id,
            FacultyRoleAssignment.is_active.is_(True),
            FacultyRoleAssignment.role == AssignedRole.COORDINATOR,
            FacultyRoleAssignment.domain.in_([CoordinationDomain.CSSI,
                                              CoordinationDomain.SUMMER_INTERNSHIP]),
        ))
        if not remaining:
            link = db.scalar(select(UserRole).where(
                UserRole.user_id == faculty.user_id,
                UserRole.role == Role.INTERNSHIP_COORDINATOR,
            ))
            if link:
                db.delete(link)

    notifications.notify(
        db, user_id=faculty.user_id, type=NotificationType.SYSTEM,
        title=f"{DOMAIN_LABELS[assignment.domain]} "
              f"{ROLE_LABELS[assignment.role].lower()} role ended",
        message="This coordination role has been revoked. The related screens "
                "are no longer available to you.",
        link="/dashboard",
    )
    audit.record(
        db, action=AuditAction.DELETE, entity_type="faculty_role_assignment",
        entity_id=assignment.id, actor=user,
        description=f"Revoked {DOMAIN_LABELS[assignment.domain]} coordination from "
                    f"{faculty.user.full_name}",
    )
    db.commit()
    return Message(message="Coordination revoked.")


@router.patch("/{assignment_id}", response_model=RoleAssignmentOut)
def edit(
    assignment_id: int, payload: RoleAssignmentUpdate, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> RoleAssignmentOut:
    """Edit an existing assignment — scope, validity window, or active flag.

    Role and domain are deliberately immutable: changing "Mentor for CSSI" into
    "Coordinator for NPTEL" in place would silently rewrite history in the audit
    trail. Revoke and create instead.
    """
    assignment = db.get(FacultyRoleAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Role assignment not found.")

    changes = payload.model_dump(exclude_unset=True)
    if "department_id" in changes and changes["department_id"] is not None:
        if db.get(Department, changes["department_id"]) is None:
            raise NotFoundError("Department not found.")

    starts = changes.get("starts_on", assignment.starts_on)
    ends = changes.get("ends_on", assignment.ends_on)
    if starts and ends and ends < starts:
        raise BusinessRuleError("The end date cannot fall before the start date.")

    # A scope change must not collide with a grant this faculty already holds.
    if "department_id" in changes:
        clash = db.scalar(select(FacultyRoleAssignment).where(
            FacultyRoleAssignment.faculty_id == assignment.faculty_id,
            FacultyRoleAssignment.role == assignment.role,
            FacultyRoleAssignment.domain == assignment.domain,
            FacultyRoleAssignment.department_id == changes["department_id"],
            FacultyRoleAssignment.id != assignment.id,
            FacultyRoleAssignment.is_active.is_(True),
        ))
        if clash:
            raise ConflictError(
                "That faculty member already holds this role for that scope."
            )

    for field, value in changes.items():
        setattr(assignment, field, value)

    # Losing the last active internship coordination also drops the coarse role.
    if (changes.get("is_active") is False
            and assignment.role is AssignedRole.COORDINATOR
            and assignment.domain in (CoordinationDomain.CSSI,
                                      CoordinationDomain.SUMMER_INTERNSHIP)):
        _sync_internship_role(db, assignment)

    audit.record(
        db, action=AuditAction.UPDATE, entity_type="faculty_role_assignment",
        entity_id=assignment.id, actor=user,
        description=f"Edited {ROLE_LABELS[assignment.role].lower()} assignment for "
                    f"{assignment.faculty.user.full_name}",
        meta={"changes": {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                          for k, v in changes.items()}},
    )
    db.commit()
    db.refresh(assignment)
    return _load(db, assignment)


def _sync_internship_role(db, assignment: FacultyRoleAssignment) -> None:
    """Drop `Role.INTERNSHIP_COORDINATOR` once no active coordination remains."""
    faculty = assignment.faculty
    remaining = db.scalar(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.faculty_id == assignment.faculty_id,
        FacultyRoleAssignment.id != assignment.id,
        FacultyRoleAssignment.is_active.is_(True),
        FacultyRoleAssignment.role == AssignedRole.COORDINATOR,
        FacultyRoleAssignment.domain.in_([CoordinationDomain.CSSI,
                                          CoordinationDomain.SUMMER_INTERNSHIP]),
    ))
    if remaining:
        return
    link = db.scalar(select(UserRole).where(
        UserRole.user_id == faculty.user_id,
        UserRole.role == Role.INTERNSHIP_COORDINATOR,
    ))
    if link:
        db.delete(link)
