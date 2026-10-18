"""Credit seeded CSSI milestone approvals to each student's own mentor.

    python -m app.seed.fix_cssi_reviewers            # make the change
    python -m app.seed.fix_cssi_reviewers --dry-run  # only report

The seed used to record one person (ICT-F-101, Dr. Anand Mehta) as the reviewer
of every approved CSSI milestone, so the faculty score credited them with ~900
reviews. This moves each such approval to the enrollment's mentor, as the seed
now does. Only rows reviewed by ICT-F-101 on an enrollment mentored by someone
else are touched; anything reviewed through the app keeps its reviewer. Safe to
run twice.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import AuditAction, StageStatus
from app.models.identity import Faculty
from app.models.internships import EnrollmentStageProgress, InternshipEnrollment, InternshipProgram
from app.services import audit


def fix(db, *, dry_run: bool) -> int:
    seeded_reviewer = db.scalar(select(Faculty).where(Faculty.employee_code == "ICT-F-101"))
    cssi_ids = list(db.scalars(select(InternshipProgram.id).where(InternshipProgram.code.like("CSSI%"))))
    if seeded_reviewer is None or not cssi_ids:
        return 0
    rows = db.execute(
        select(EnrollmentStageProgress, InternshipEnrollment)
        .join(InternshipEnrollment, InternshipEnrollment.id == EnrollmentStageProgress.enrollment_id)
        .where(InternshipEnrollment.program_id.in_(cssi_ids),
               EnrollmentStageProgress.status == StageStatus.APPROVED,
               EnrollmentStageProgress.reviewed_by_user_id == seeded_reviewer.user_id,
               InternshipEnrollment.mentor_faculty_id.is_not(None),
               InternshipEnrollment.mentor_faculty_id != seeded_reviewer.id)
    ).all()
    mentors = {f.id: f.user_id for f in db.scalars(select(Faculty))}
    for progress, enrollment in rows:
        if not dry_run:
            progress.reviewed_by_user_id = mentors[enrollment.mentor_faculty_id]
    if rows and not dry_run:
        audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program", entity_id=None,
                     actor=None, description="Seeded CSSI approvals credited to each student's mentor",
                     meta={"rows": len(rows)})
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would change")
    args = parser.parse_args()
    with SessionLocal() as db:
        count = fix(db, dry_run=args.dry_run)
        db.rollback() if args.dry_run else db.commit()
    print(f"{'Would move' if args.dry_run else 'Moved'} {count} approval(s) to the student's mentor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
