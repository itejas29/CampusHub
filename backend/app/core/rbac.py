"""Role → permission matrix, enforced server-side.

The frontend uses the *same* permission strings (served by ``/auth/me``) to
decide what to render, but every protected route also calls
``require_permission`` so hiding a button is never the only control.
"""
from __future__ import annotations

from app.models.enums import Role

# ── permission vocabulary ─────────────────────────────────────────────────
# Format: "<domain>:<action>". ``*`` on SUPER_ADMIN grants everything.
P = {
    "ACADEMIC_READ": "academics:read",
    "ACADEMIC_MANAGE": "academics:manage",
    "ELECTIVE_APPLY": "electives:apply",
    "ELECTIVE_MANAGE": "electives:manage",
    "ELECTIVE_ALLOCATE": "electives:allocate",
    "MOOC_APPLY": "mooc:apply",
    "MOOC_VERIFY": "mooc:verify",
    "MINOR_APPLY": "minors:apply",
    "MINOR_MANAGE": "minors:manage",
    "INTERNSHIP_ENROLL": "internships:enroll",
    "INTERNSHIP_SUBMIT": "internships:submit",
    "INTERNSHIP_MENTOR": "internships:mentor",
    "INTERNSHIP_EVALUATE": "internships:evaluate",
    "INTERNSHIP_MANAGE": "internships:manage",
    "CLUB_READ": "clubs:read",
    "CLUB_MANAGE": "clubs:manage",
    "EVENT_REGISTER": "events:register",
    "EVENT_MANAGE": "events:manage",
    "MENTORSHIP_STUDENT": "mentorship:student",
    "MENTORSHIP_FACULTY": "mentorship:faculty",
    "MENTORSHIP_MANAGE": "mentorship:manage",
    "ANNOUNCEMENT_PUBLISH": "announcements:publish",
    "STUDENT_READ": "students:read",
    "STUDENT_MANAGE": "students:manage",
    "FACULTY_READ": "faculty:read",
    "FACULTY_MANAGE": "faculty:manage",
    "DEPARTMENT_MANAGE": "departments:manage",
    "REPORT_VIEW": "reports:view",
    "AUDIT_VIEW": "audit:view",
    "SYSTEM_ADMIN": "system:admin",
}

_STUDENT = {
    P["ACADEMIC_READ"], P["ELECTIVE_APPLY"], P["MOOC_APPLY"], P["MINOR_APPLY"],
    P["INTERNSHIP_ENROLL"], P["INTERNSHIP_SUBMIT"], P["CLUB_READ"],
    P["EVENT_REGISTER"], P["MENTORSHIP_STUDENT"], P["FACULTY_READ"],
}

# A plain faculty member works from their own dashboard (mentees, review queue,
# evaluations). `reports:view` is institution-wide aggregate reporting and is
# deliberately NOT granted here — it also gates the admin dashboard, whose
# recent-activity panel is drawn from the audit log faculty cannot read.
_FACULTY = {
    P["ACADEMIC_READ"], P["STUDENT_READ"], P["FACULTY_READ"], P["CLUB_READ"],
    P["EVENT_REGISTER"], P["INTERNSHIP_MENTOR"], P["INTERNSHIP_EVALUATE"],
    P["MENTORSHIP_FACULTY"], P["ANNOUNCEMENT_PUBLISH"],
}

_DEPARTMENT_ADMIN = _FACULTY | {
    P["REPORT_VIEW"], P["AUDIT_VIEW"],
    P["ACADEMIC_MANAGE"], P["ELECTIVE_MANAGE"], P["ELECTIVE_ALLOCATE"],
    P["MOOC_VERIFY"], P["MINOR_MANAGE"], P["STUDENT_MANAGE"], P["FACULTY_MANAGE"],
    P["MENTORSHIP_MANAGE"], P["EVENT_MANAGE"], P["INTERNSHIP_MANAGE"],
}

_INTERNSHIP_COORDINATOR = {
    P["ACADEMIC_READ"], P["STUDENT_READ"], P["FACULTY_READ"], P["CLUB_READ"],
    P["INTERNSHIP_MANAGE"], P["INTERNSHIP_MENTOR"], P["INTERNSHIP_EVALUATE"],
    P["ANNOUNCEMENT_PUBLISH"], P["REPORT_VIEW"], P["MENTORSHIP_MANAGE"],
}

_CLUB_ADMIN = {
    P["CLUB_READ"], P["CLUB_MANAGE"], P["EVENT_MANAGE"], P["EVENT_REGISTER"],
    P["ANNOUNCEMENT_PUBLISH"], P["STUDENT_READ"], P["REPORT_VIEW"],
}

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.STUDENT: _STUDENT,
    Role.FACULTY: _FACULTY,
    Role.DEPARTMENT_ADMIN: _DEPARTMENT_ADMIN,
    Role.INTERNSHIP_COORDINATOR: _INTERNSHIP_COORDINATOR,
    Role.CLUB_ADMIN: _CLUB_ADMIN,
    Role.SUPER_ADMIN: {"*"},
}

# Roles that can see the administration section of the app.
ADMIN_ROLES = (
    Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN, Role.INTERNSHIP_COORDINATOR, Role.CLUB_ADMIN,
)


def permissions_for(roles: list[Role] | set[Role]) -> set[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, set())
    if "*" in granted:
        return {"*"} | {p for p in P.values()}
    return granted


def has_permission(roles: list[Role] | set[Role], permission: str) -> bool:
    granted = permissions_for(roles)
    return "*" in granted or permission in granted
