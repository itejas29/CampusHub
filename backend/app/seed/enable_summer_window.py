"""Run ICT's Summer Internship registration in a coordinator-opened window.

    python -m app.seed.enable_summer_window            # make the change
    python -m app.seed.enable_summer_window --dry-run  # only report

Brings a database seeded before this change up to what the seed now makes:

* the ICT Summer Internship lists a REGISTRATION window in its configuration,
  so registration opens when the coordinator opens it for the Semester VI
  cohort (as CSSI's does) — no window is opened here;
* the demo student Meera Joshi (22BIT004) is left unregistered, so the demo can
  show a student registering once the window is open. Her seeded Summer
  Internship record — demo data only, never a real student's — is removed.

Nothing else is touched. Safe to run twice.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.enums import AuditAction, InternshipType
from app.models.identity import Department, Student, User
from app.models.internships import (
    EnrollmentStageProgress, EvaluationScore, InternshipDocument, InternshipEnrollment,
    InternshipEvaluation, InternshipProgram, InternshipProject, InternshipReport,
)
from app.seed import data as D
from app.services import audit

DEMO_DOMAIN = "@campushub.example.com"


def apply(db, *, dry_run: bool) -> list[str]:
    done: list[str] = []
    ict = db.scalar(select(Department).where(Department.code == "ICT"))
    if ict is None:
        return done
    programs = list(db.scalars(select(InternshipProgram).where(
        InternshipProgram.department_id == ict.id, InternshipProgram.type == InternshipType.SUMMER)))
    for program in programs:
        config = dict(program.config or {})
        if "REGISTRATION" in (config.get("windows") or []):
            continue
        done.append(f"{program.code}: registration now runs in a coordinator-opened window")
        if not dry_run:
            config["windows"] = [*(config.get("windows") or []), "REGISTRATION"]
            program.config = config

    for roll in sorted(D.LEFT_TO_REGISTER_SUMMER):
        student = db.scalar(select(Student).where(Student.roll_number == roll))
        if student is None:
            continue
        email = db.get(User, student.user_id).email
        if not email.endswith(DEMO_DOMAIN) or "@students." in email:
            continue                      # never a real student's record
        for program in programs:
            enrollment = db.scalar(select(InternshipEnrollment).where(
                InternshipEnrollment.program_id == program.id,
                InternshipEnrollment.student_id == student.id))
            if enrollment is None:
                continue
            done.append(f"{program.code}: removed demo enrolment of {roll} so they can register live")
            if dry_run:
                continue
            evaluation_ids = select(InternshipEvaluation.id).where(
                InternshipEvaluation.enrollment_id == enrollment.id)
            db.execute(delete(EvaluationScore).where(EvaluationScore.evaluation_id.in_(evaluation_ids)))
            for model in (InternshipEvaluation, InternshipReport, InternshipDocument,
                          InternshipProject, EnrollmentStageProgress):
                db.execute(delete(model).where(model.enrollment_id == enrollment.id))
            db.execute(delete(InternshipEnrollment).where(InternshipEnrollment.id == enrollment.id))

    if done and not dry_run:
        audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program", entity_id=None,
                     actor=None, description="Summer Internship registration moved to a window",
                     meta={"changes": done})
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would change")
    args = parser.parse_args()
    with SessionLocal() as db:
        done = apply(db, dry_run=args.dry_run)
        db.rollback() if args.dry_run else db.commit()
    verb = "Would make" if args.dry_run else "Made"
    print(f"{verb} {len(done)} change(s)." if done else "Nothing to change — already up to date.")
    for item in done:
        print("  •", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
