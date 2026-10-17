"""Locking a programme's mentor allocation, and changing it once locked.

How the ICT department asked for it to work (not from a written rule):

* The coordinator **locks** the allocation once every registered student has a
  mentor. The mentors carrying students at that moment become the allocation.
* While it is locked, nothing can re-run or reset it: the roll-number run, the
  auto-distribute and Reset all are refused. The allocation changes only one
  deliberate step at a time — **add** a mentor, **remove** one (their students
  move to another mentor in the allocation, or wait for one), **replace** one
  with another (their whole block moves), or move one student. Every step is
  audited, and the students and mentors it touches are notified.
* Only the coordinator who may run the allocation can lock, change or unlock
  it; unlocking is audited too.

State lives in ``program.config["mentor_allocation"]``:
``{"locked_at": iso, "locked_by_user_id": int, "faculty_ids": [int, ...]}``.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.enums import AuditAction
from app.models.identity import Faculty, User
from app.models.internships import InternshipEnrollment, InternshipProgram
from app.services import audit
from app.services import internships as engine

KEY = "mentor_allocation"


def _state(program: InternshipProgram) -> dict:
    return dict((program.config or {}).get(KEY) or {})


def _save(program: InternshipProgram, state: dict | None) -> None:
    config = dict(program.config or {})
    if state is None:
        config.pop(KEY, None)
    else:
        config[KEY] = state
    program.config = config      # reassigned so the JSON column is marked dirty


def is_locked(program: InternshipProgram) -> bool:
    return bool(_state(program).get("locked_at"))


def locked_at(program: InternshipProgram) -> dt.datetime | None:
    value = _state(program).get("locked_at")
    return dt.datetime.fromisoformat(value) if value else None


def allocated_ids(program: InternshipProgram) -> list[int]:
    """The mentors in a locked allocation; empty when it is not locked."""
    return list(_state(program).get("faculty_ids") or []) if is_locked(program) else []


def assert_not_locked(program: InternshipProgram) -> None:
    if is_locked(program):
        raise BusinessRuleError(
            "The mentor allocation is locked. Change it one mentor at a time, or "
            "unlock it to run the allocation again.")


def assert_allowed_target(program: InternshipProgram, faculty_id: int | None) -> None:
    """While locked, a student can be moved only to a mentor in the allocation."""
    if faculty_id is not None and is_locked(program) and faculty_id not in allocated_ids(program):
        raise BusinessRuleError(
            "That mentor is not in the locked allocation. Add them to it first.")


def _loads(db: Session, program: InternshipProgram) -> dict[int, int]:
    return dict(db.execute(
        select(InternshipEnrollment.mentor_faculty_id, func.count(InternshipEnrollment.id))
        .where(InternshipEnrollment.program_id == program.id,
               InternshipEnrollment.mentor_faculty_id.is_not(None))
        .group_by(InternshipEnrollment.mentor_faculty_id)
    ).all())


def _students_of(db: Session, program: InternshipProgram, faculty_id: int):
    return list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.program_id == program.id,
        InternshipEnrollment.mentor_faculty_id == faculty_id)))


def _faculty(db: Session, faculty_id: int) -> Faculty:
    faculty = db.get(Faculty, faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")
    return faculty


def _record(db, program, actor, description, meta) -> None:
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program",
                 entity_id=program.id, actor=actor, description=description,
                 meta={"mentor_allocation": meta})


def _require_locked(program: InternshipProgram) -> None:
    if not is_locked(program):
        raise BusinessRuleError("Lock the allocation first.")


# ── lock / unlock ─────────────────────────────────────────────────────────
def lock(db: Session, program: InternshipProgram, *, actor: User) -> None:
    assert_not_locked(program)
    loads = _loads(db, program)
    total = db.scalar(select(func.count(InternshipEnrollment.id))
                      .where(InternshipEnrollment.program_id == program.id)) or 0
    if total == 0:
        raise BusinessRuleError("No students are registered, so there is nothing to lock.")
    waiting = total - sum(loads.values())
    if waiting:
        raise BusinessRuleError(
            f"{waiting} student{'s' if waiting != 1 else ''} still "
            f"need{'' if waiting != 1 else 's'} a mentor. Allocate everyone before locking.")
    ids = sorted(loads, key=lambda fid: _faculty(db, fid).user.full_name)
    _save(program, {"locked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "locked_by_user_id": actor.id, "faculty_ids": ids})
    _record(db, program, actor, f"Mentor allocation locked: {len(ids)} mentors, {total} students",
            {"action": "LOCK", "faculty_ids": ids})


def unlock(db: Session, program: InternshipProgram, *, actor: User) -> None:
    _require_locked(program)
    ids = allocated_ids(program)
    _save(program, None)
    _record(db, program, actor, "Mentor allocation unlocked",
            {"action": "UNLOCK", "faculty_ids": ids})


# ── changes while locked ──────────────────────────────────────────────────
def add_mentor(db: Session, program: InternshipProgram, faculty_id: int, *, actor: User) -> None:
    _require_locked(program)
    faculty = _faculty(db, faculty_id)
    engine.assert_eligible_mentor(db, program, faculty)
    ids = allocated_ids(program)
    if faculty_id in ids:
        raise ValidationError(f"{faculty.user.full_name} is already in the allocation.")
    _save(program, {**_state(program), "faculty_ids": ids + [faculty_id]})
    _record(db, program, actor, f"Mentor added to the allocation: {faculty.user.full_name}",
            {"action": "ADD", "faculty_id": faculty_id})


def remove_mentor(db: Session, program: InternshipProgram, faculty_id: int, *,
                  move_to: int | None, actor: User) -> int:
    """Take a mentor out; their students go to `move_to`, or wait for a mentor."""
    _require_locked(program)
    ids = allocated_ids(program)
    if faculty_id not in ids:
        raise ValidationError("That mentor is not in the allocation.")
    leaving = _faculty(db, faculty_id)
    students = _students_of(db, program, faculty_id)
    if move_to is not None:
        if move_to == faculty_id or move_to not in ids:
            raise ValidationError("Move the students to another mentor in the allocation.")
        target = _faculty(db, move_to)
        capacity = engine.mentor_capacity(program)
        load = _loads(db, program).get(move_to, 0)
        if load + len(students) > capacity:
            raise BusinessRuleError(
                f"{target.user.full_name} has {load} students; taking {len(students)} more "
                f"would pass this programme's {capacity} per mentor.")
    reason = (f"Mentor {leaving.user.full_name} removed from the allocation"
              + (f"; students moved to {target.user.full_name}" if move_to else ""))
    for enrollment in students:
        engine.override_mentor(db, enrollment=enrollment, new_faculty_id=move_to,
                               reason=reason, actor=actor, enforce_capacity=False)
    _save(program, {**_state(program), "faculty_ids": [i for i in ids if i != faculty_id]})
    _record(db, program, actor, reason,
            {"action": "REMOVE", "faculty_id": faculty_id, "moved_to": move_to,
             "students": len(students)})
    return len(students)


def replace_mentor(db: Session, program: InternshipProgram, faculty_id: int,
                   new_faculty_id: int, *, actor: User) -> int:
    """Hand a mentor's whole block to someone not yet in the allocation."""
    _require_locked(program)
    ids = allocated_ids(program)
    if faculty_id not in ids:
        raise ValidationError("That mentor is not in the allocation.")
    if new_faculty_id in ids:
        raise ValidationError(
            "That mentor is already in the allocation — remove this one and move "
            "the students to them instead.")
    old, new = _faculty(db, faculty_id), _faculty(db, new_faculty_id)
    engine.assert_eligible_mentor(db, program, new)
    students = _students_of(db, program, faculty_id)
    reason = f"Mentor changed from {old.user.full_name} to {new.user.full_name}"
    for enrollment in students:
        engine.override_mentor(db, enrollment=enrollment, new_faculty_id=new_faculty_id,
                               reason=reason, actor=actor, enforce_capacity=False)
    _save(program, {**_state(program),
                    "faculty_ids": [new_faculty_id if i == faculty_id else i for i in ids]})
    _record(db, program, actor, reason,
            {"action": "REPLACE", "faculty_id": faculty_id, "new_faculty_id": new_faculty_id,
             "students": len(students)})
    return len(students)
