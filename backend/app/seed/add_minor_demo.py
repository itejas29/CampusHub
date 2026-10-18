"""Bring a database seeded before the minor portal up to the demo the seed makes now.

    python -m app.seed.add_minor_demo            # make the changes
    python -m app.seed.add_minor_demo --dry-run  # only report

Adds, without touching anything else:

* any named demo student (the login page's shortcuts) missing from a database
  seeded before they were added — Ananya Menon and Kavya Patel on the live
  site — created exactly as the seed creates them;
* a minor seat for Ananya Menon (Data Science) and for one generated CSE
  student in ICT's IoT minor, each registered in Semester III — if they have
  no seat yet;
* sample results for demo students who hold a seat but have none, with their
  start moved to Semester III (applications are made then).

Real students are never touched: no seat, no result. Safe to run twice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import AuditAction, MinorApplicationStatus, MinorEnrollmentStatus
from app.models.identity import Student, User
from app.models.minors import MinorApplication, MinorCourseResult, MinorEnrollment, MinorProgram
from app.seed import run as seed
from app.services import audit


def _is_demo(student: Student) -> bool:
    email = student.user.email
    return email.endswith("@campushub.example.com") and "@students." not in email


def add(db, *, dry_run: bool) -> list[str]:
    done: list[str] = []
    rng = random.Random(7)
    # ── named demo students the database predates ─────────────────────────
    from slugify import slugify

    from app.models.enums import Role
    from app.models.academics import Program
    from app.models.identity import Department

    ict = db.scalar(select(Department).where(Department.code == "ICT"))
    btech = db.scalar(select(Program).where(Program.code == "B.TECH-ICT"))
    for name, roll, sem, division, cpi, backlogs, admission in seed.D.NAMED_STUDENTS:
        if db.scalar(select(Student.id).where(Student.roll_number == roll)):
            continue
        email = f"{slugify(name, separator='.')}.{roll[-3:]}@campushub.example.com"
        if db.scalar(select(User.id).where(User.email == email)):
            continue
        done.append(f"demo student: {name} ({roll}, Semester {sem})")
        if dry_run or ict is None or btech is None:
            continue
        user = seed.make_user(db, name=name, email=email, roles=[Role.STUDENT])
        db.add(Student(user_id=user.id, roll_number=roll, enrollment_number=f"PDEU{admission}{roll[-3:]}",
                       program_id=btech.id, department_id=ict.id, admission_year=admission,
                       current_semester=sem, division=division, batch=f"{admission}-{admission + 4}",
                       cpi=cpi, backlog_count=backlogs))
        db.flush()

    minors = {m.code: m for m in db.scalars(select(MinorProgram))}
    admin = db.scalar(select(User).where(User.email == "admin@campushub.example.com"))

    def seat(student: Student | None, minor: MinorProgram | None, why: str) -> None:
        if student is None or minor is None or not _is_demo(student):
            return
        if minor.department_id == student.department_id:
            return
        if db.scalar(select(MinorEnrollment).where(MinorEnrollment.student_id == student.id)):
            return
        done.append(f"seat: {student.user.full_name} ({student.roll_number}) in {minor.name} — {why}")
        if dry_run:
            return
        application = db.scalar(select(MinorApplication).where(
            MinorApplication.student_id == student.id, MinorApplication.minor_program_id == minor.id))
        if application is None:
            application = MinorApplication(student_id=student.id, minor_program_id=minor.id,
                                           academic_year_id=minor.academic_year_id, preference_order=1)
            db.add(application)
        application.status = MinorApplicationStatus.ALLOCATED
        application.semester_at_application = 3
        application.cpi_at_application = student.cpi
        application.backlogs_at_application = student.backlog_count
        application.submitted_at = application.submitted_at or dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=150)
        application.decided_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=140)
        application.reviewed_by_user_id = admin.id if admin else None
        db.flush()
        minor.seats_filled += 1
        enrollment = MinorEnrollment(student_id=student.id, minor_program_id=minor.id,
                                     application_id=application.id,
                                     status=MinorEnrollmentStatus.ACTIVE, started_semester=3)
        db.add(enrollment)
        db.flush()
        seed.seed_minor_results(db, enrollment, student, rng)

    ananya = db.scalar(select(Student).where(Student.roll_number == "23BIT911"))
    seat(ananya, minors.get("MIN-CDS"), "demo sign-in")
    iot = minors.get("MIN-IOT")
    if iot is not None:
        cse = db.scalar(select(Student).where(
            Student.department_id != iot.department_id, Student.current_semester == 4,
            Student.cpi >= 7.5, Student.backlog_count == 0).order_by(Student.roll_number))
        seat(cse, iot, "so the IoT coordinator has a student to grade")

    # Seats seeded before the portal: no results, and started "now".
    for enrollment in db.scalars(select(MinorEnrollment)):
        student = db.get(Student, enrollment.student_id)
        if not _is_demo(student):
            continue
        has_results = db.scalar(select(MinorCourseResult.id).where(
            MinorCourseResult.enrollment_id == enrollment.id))
        if has_results:
            continue
        done.append(f"results: {student.user.full_name} ({student.roll_number}) in "
                    f"{enrollment.minor_program.name}")
        if dry_run:
            continue
        enrollment.started_semester = 3
        seed.seed_minor_results(db, enrollment, student, rng)

    if done and not dry_run:
        audit.record(db, action=AuditAction.CREATE, entity_type="minor_program", entity_id=None,
                     actor=None, description="Minor portal demo seats and results added",
                     meta={"added": done})
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would be added")
    args = parser.parse_args()
    with SessionLocal() as db:
        done = add(db, dry_run=args.dry_run)
        db.rollback() if args.dry_run else db.commit()
    verb = "Would add" if args.dry_run else "Added"
    print(f"{verb} {len(done)} item(s)." if done else "Nothing to add — already up to date.")
    for item in done:
        print("  •", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
