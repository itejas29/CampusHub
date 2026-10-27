"""A student's faculty mentor (the Mentor–Mentee module).

**One active mentor per student, in any academic year** — the department's
rule, confirmed by the project owner on 24 Oct 2026 (QA-15). Assigning a new
mentor retires the old assignment; it stays in the table, inactive, as history.

The database enforces it too: a partial unique index on `student_id` where
`is_active` (migration 0019). The old `(student_id, academic_year_id)` unique
constraint never could — NULL years never collide, and a new academic year
left last year's assignment active beside the new one.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.locking import locked
from app.models.engagement import MentorAssignment
from app.models.identity import AcademicYear, Faculty, Student


@dataclass(slots=True)
class Assigned:
    assignment: MentorAssignment
    #: The mentor the student had before, if any (for the audit trail).
    previous_faculty_id: int | None
    #: Older active assignments this call retired.
    retired: list[MentorAssignment]


def current_year_id(db: Session) -> int | None:
    return db.scalar(select(AcademicYear.id).where(AcademicYear.is_current.is_(True)))


def assign(db: Session, student: Student, faculty: Faculty, *, actor_user_id: int | None,
           now: dt.datetime | None = None) -> Assigned:
    """Make `faculty` the student's one active mentor."""
    now = now or dt.datetime.now(dt.timezone.utc)
    # Two assignments for one student at the same instant would both see "no
    # active mentor" and both insert. Locking the student row makes the second
    # wait for the first and then see it (the index would refuse it anyway).
    locked(db, Student, student.id)
    year_id = current_year_id(db)
    rows = list(db.scalars(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id)))
    active = [r for r in rows if r.is_active]
    previous = max(active, key=lambda r: (r.assigned_at or dt.datetime.min.replace(
        tzinfo=dt.timezone.utc), r.id), default=None)
    # This year's row is reused if there is one: (student, year) stays unique.
    target = next((r for r in rows if r.academic_year_id == year_id), None)

    retired = [r for r in active if r is not target]
    for row in retired:
        row.is_active = False
    db.flush()          # retire first, so the one-active index never sees two

    if target is None:
        target = MentorAssignment(student_id=student.id, academic_year_id=year_id)
        db.add(target)
    target.faculty_id = faculty.id
    target.is_active = True
    target.assigned_by_user_id = actor_user_id
    target.assigned_at = now
    db.flush()
    return Assigned(assignment=target,
                    previous_faculty_id=previous.faculty_id if previous else None,
                    retired=retired)


def duplicate_active(db: Session) -> dict[int, list[MentorAssignment]]:
    """Students holding more than one active assignment (should be none)."""
    by_student: dict[int, list[MentorAssignment]] = {}
    for row in db.scalars(select(MentorAssignment).where(MentorAssignment.is_active.is_(True))
                          .order_by(MentorAssignment.student_id, MentorAssignment.id)):
        by_student.setdefault(row.student_id, []).append(row)
    return {sid: rows for sid, rows in by_student.items() if len(rows) > 1}
