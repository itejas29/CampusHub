"""Report students with more than one active faculty mentor. Read-only.

    python -m app.seed.report_mentor_duplicates

Run it against a database before migration 0019 reaches it, to see exactly
which assignments the migration will retire (it keeps each student's most
recent active one). Changes nothing.
"""
from __future__ import annotations

import sys

from app.db.session import SessionLocal
from app.services.mentoring import duplicate_active


def main() -> int:
    with SessionLocal() as db:
        duplicates = duplicate_active(db)
        if not duplicates:
            print("No student has more than one active mentor.")
            return 0
        print(f"{len(duplicates)} student(s) with more than one active mentor:")
        for student_id, rows in duplicates.items():
            newest = max(rows, key=lambda r: (r.assigned_at is not None,
                                              str(r.assigned_at or ""), r.id))
            roll = rows[0].student.roll_number if rows[0].student else student_id
            for row in rows:
                keep = "keep  " if row is newest else "retire"
                print(f"  {roll}: {keep} assignment {row.id} — "
                      f"{row.faculty.user.full_name if row.faculty else row.faculty_id}, "
                      f"year {row.academic_year_id}, assigned {row.assigned_at}")
        db.rollback()
    return 0


if __name__ == "__main__":
    sys.exit(main())
