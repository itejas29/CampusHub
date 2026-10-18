"""Add the Semester VII and VIII project programmes to a database seeded before them.

    python -m app.seed.add_project_programs            # make the changes
    python -m app.seed.add_project_programs --dry-run  # only report

A reseed would also create them, but a reseed rebuilds every table, wiping
whatever coordinators and students have done in the live portal. This adds only
what is missing and touches nothing else:

* the Minor Project, Seminar and Major Project / Industry Internship
  programmes (with their stages, rubrics, tracks and settings), plus the two
  demo records the full seed starts the Minor Project with;
* the Projects and Major Project coordinator roles (Dr. Rakesh Bhatt, demo) and
  the project mentor grants, exactly as `seed/data.py` lists them.

It is safe to run twice: anything already present is left alone. Each addition
is written to the audit log.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import (
    AssignedRole, AuditAction, CoordinationDomain, OrganizationType, Role,
)
from app.models.identity import (
    AcademicYear, Department, Faculty, FacultyRoleAssignment, Semester, Student, UserRole,
)
from app.models.internships import InternshipProgram, Organization
from app.seed import data as D
from app.seed import run as seed
from app.services import audit, scope

PROJECT_DOMAINS = {CoordinationDomain.PROJECT.value, CoordinationDomain.MAJOR_PROJECT.value}


def add(db, *, dry_run: bool) -> list[str]:
    done: list[str] = []
    departments = {d.code: d for d in db.scalars(select(Department))}
    faculty_by_code = {f.employee_code: f for f in db.scalars(select(Faculty))}
    year = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    if year is None or "ICT" not in departments or "ICT-F-103" not in faculty_by_code:
        raise SystemExit("This database is missing the ICT department, the current academic "
                         "year or Dr. Rakesh Bhatt (ICT-F-103); run the full seed instead.")
    semesters = {s.number: s for s in db.scalars(select(Semester).where(
        Semester.academic_year_id == year.id))}

    # ── roles ─────────────────────────────────────────────────────────────
    for code, role, domain, dept in D.ROLE_ASSIGNMENTS:
        if domain not in PROJECT_DOMAINS:
            continue
        faculty = faculty_by_code.get(code)
        if faculty is None or scope.is_hod(db, faculty):
            continue
        exists = db.scalar(select(FacultyRoleAssignment).where(
            FacultyRoleAssignment.faculty_id == faculty.id,
            FacultyRoleAssignment.role == AssignedRole(role),
            FacultyRoleAssignment.domain == CoordinationDomain(domain),
            FacultyRoleAssignment.department_id == departments[dept].id))
        if exists is not None:
            continue
        done.append(f"{role.lower()} grant: {faculty.user.full_name} — {domain}")
        if dry_run:
            continue
        db.add(FacultyRoleAssignment(
            faculty_id=faculty.id, role=AssignedRole(role), domain=CoordinationDomain(domain),
            department_id=departments[dept].id, academic_year_id=year.id, is_active=True,
            assigned_at=dt.datetime.now(dt.timezone.utc),
            notes="Added with the Semester VII/VIII programmes."))
        if role == "COORDINATOR" and not db.scalar(select(UserRole).where(
                UserRole.user_id == faculty.user_id, UserRole.role == Role.INTERNSHIP_COORDINATOR)):
            db.add(UserRole(user_id=faculty.user_id, role=Role.INTERNSHIP_COORDINATOR))
        db.flush()

    # ── programmes ────────────────────────────────────────────────────────
    present = set(db.scalars(select(InternshipProgram.code)))
    created: dict[str, InternshipProgram] = {}
    for spec in seed.PROJECT_PROGRAMS:
        code = spec[0]
        if code in present:
            continue
        done.append(f"programme: {spec[1]} ({code})")
        if not dry_run:
            created[code] = seed.make_project_program(db, spec, year, semesters, departments,
                                                      faculty_by_code)
    if created and not dry_run:
        students = list(db.scalars(select(Student)))
        companies = list(db.scalars(select(Organization).where(
            Organization.type == OrganizationType.COMPANY)))
        seed.seed_project_samples(db, created.get("MP7-2025"), created.get("MP8-2025"),
                                  departments, faculty_by_code, students, companies)

    if done and not dry_run:
        audit.record(db, action=AuditAction.CREATE, entity_type="internship_program",
                     entity_id=None, actor=None,
                     description="Semester VII/VIII programmes and roles added to the live data",
                     meta={"added": done})
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would be added")
    args = parser.parse_args()
    with SessionLocal() as db:
        done = add(db, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    verb = "Would add" if args.dry_run else "Added"
    print(f"{verb} {len(done)} item(s)." if done else "Nothing to add — already up to date.")
    for item in done:
        print("  •", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
