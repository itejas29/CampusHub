"""A minor student's semester-by-semester view, and the coordinator's records.

Once a student holds a minor seat, their minor stops being an application and
becomes a programme: a different set of courses each semester (Annexure II
gives the semester each course is preferably offered in), their result in
each, the credits they have earned, and the fee for each semester.

* **Courses** come from the minor's `MinorCourse` rows; the semester of a
  course is `eligible_from_semester + semester_offset - 1`.
* **Results** are recorded by the minor's coordinator. Marks and grade are
  stored as given — no grading scale is assumed. A PASSED course counts its
  credits towards `credits_completed`.
* **Fees** are a schedule on the minor, `rules["fees"]`
  (`[{"semester", "amount", "due_on", "note"}]`), set by its coordinator, and
  each student's payment recorded by the department with its receipt number.
  No amount is assumed: a semester without one is "not announced".

Every change is audited.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.enums import AuditAction, MinorCourseResultStatus, MinorEnrollmentStatus
from app.models.identity import Student, User
from app.models.minors import (
    MinorCourse, MinorCourseResult, MinorEnrollment, MinorFeePayment, MinorProgram,
)
from app.services import audit


def course_semester(program: MinorProgram, course: MinorCourse) -> int:
    return program.eligible_from_semester + max(course.semester_offset, 1) - 1


def fee_schedule(program: MinorProgram) -> dict[int, dict]:
    return {int(f["semester"]): f for f in (program.rules or {}).get("fees") or []}


def _results(db: Session, enrollment: MinorEnrollment) -> dict[int, MinorCourseResult]:
    return {r.minor_course_id: r for r in db.scalars(select(MinorCourseResult).where(
        MinorCourseResult.enrollment_id == enrollment.id))}


def _payments(db: Session, enrollment: MinorEnrollment) -> dict[int, MinorFeePayment]:
    return {p.semester: p for p in db.scalars(select(MinorFeePayment).where(
        MinorFeePayment.enrollment_id == enrollment.id))}


def plan(db: Session, enrollment: MinorEnrollment, current_semester: int) -> list[dict]:
    """Every semester of the minor: its courses, results, and fee."""
    program = enrollment.minor_program
    results, payments, fees = _results(db, enrollment), _payments(db, enrollment), fee_schedule(program)
    by_semester: dict[int, list[dict]] = {}
    for course in sorted(program.courses, key=lambda c: c.sequence):
        sem = course_semester(program, course)
        result = results.get(course.id)
        by_semester.setdefault(sem, []).append({
            "minor_course_id": course.id, "code": course.course.code,
            "title": course.course.title, "credits": float(course.course.credits),
            "result": None if result is None else {
                "marks": float(result.marks) if result.marks is not None else None,
                "grade": result.grade, "status": result.status.value,
            },
        })
    out = []
    for sem in sorted(set(by_semester) | set(fees)):
        fee = fees.get(sem)
        paid = payments.get(sem)
        out.append({
            "semester": sem,
            "when": "current" if sem == current_semester else "past" if sem < current_semester else "upcoming",
            "courses": by_semester.get(sem, []),
            "fee": None if fee is None else {
                "amount": float(fee["amount"]), "due_on": fee.get("due_on"), "note": fee.get("note"),
            },
            "payment": None if paid is None else {
                "amount": float(paid.amount_paid), "reference": paid.reference,
                "paid_on": paid.paid_on.isoformat() if paid.paid_on else None,
            },
        })
    return out


# ── coordinator: results ──────────────────────────────────────────────────
def _course(program: MinorProgram, minor_course_id: int) -> MinorCourse:
    course = next((c for c in program.courses if c.id == minor_course_id), None)
    if course is None:
        raise NotFoundError("That course is not part of this minor.")
    return course


def enrolled(db: Session, program: MinorProgram) -> list[MinorEnrollment]:
    rows = db.scalars(select(MinorEnrollment).where(
        MinorEnrollment.minor_program_id == program.id,
        MinorEnrollment.status != MinorEnrollmentStatus.DISCONTINUED))
    return sorted(rows, key=lambda e: db.get(Student, e.student_id).roll_number)


def gradebook(db: Session, program: MinorProgram, minor_course_id: int) -> list[dict]:
    course = _course(program, minor_course_id)
    rows = []
    for enrollment in enrolled(db, program):
        student = db.get(Student, enrollment.student_id)
        result = _results(db, enrollment).get(course.id)
        rows.append({
            "enrollment_id": enrollment.id, "student_name": student.user.full_name,
            "roll_number": student.roll_number, "department": student.department.code if student.department else None,
            "semester": student.current_semester,
            "marks": float(result.marks) if result and result.marks is not None else None,
            "grade": result.grade if result else None,
            "status": result.status.value if result else None,
        })
    return rows


def _recount(db: Session, enrollment: MinorEnrollment) -> None:
    program = enrollment.minor_program
    credits = {c.id: Decimal(str(c.course.credits)) for c in program.courses}
    passed = [r.minor_course_id for r in _results(db, enrollment).values()
              if r.status == MinorCourseResultStatus.PASSED]
    enrollment.credits_completed = float(sum((credits.get(cid, 0) for cid in passed), Decimal(0)))
    enrollment.completed_course_ids = passed


def record_results(db: Session, program: MinorProgram, minor_course_id: int, rows: list[dict], *,
                   actor: User) -> int:
    course = _course(program, minor_course_id)
    members = {e.id: e for e in enrolled(db, program)}
    changed = 0
    for row in rows:
        enrollment = members.get(row.get("enrollment_id"))
        if enrollment is None:
            raise ValidationError("A row names a student who is not enrolled in this minor.")
        marks, grade = row.get("marks"), (row.get("grade") or "").strip().upper() or None
        status = MinorCourseResultStatus(row.get("status") or MinorCourseResultStatus.IN_PROGRESS)
        if marks is not None and not 0 <= float(marks) <= 100:
            raise ValidationError("Marks are out of 100.")
        if grade is not None and len(grade) > 4:
            raise ValidationError("A grade is at most four characters.")
        if status != MinorCourseResultStatus.IN_PROGRESS and marks is None and grade is None:
            raise ValidationError("Give marks or a grade before passing or failing a student.")
        result = _results(db, enrollment).get(course.id)
        if result is None:
            result = MinorCourseResult(enrollment_id=enrollment.id, minor_course_id=course.id)
            db.add(result)
        result.marks, result.grade, result.status = marks, grade, status
        result.recorded_by_user_id = actor.id
        result.recorded_at = dt.datetime.now(dt.timezone.utc)
        db.flush()
        _recount(db, enrollment)
        changed += 1
    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_program", entity_id=program.id,
                 actor=actor, description=f"{program.code}: results recorded for "
                                          f"{course.course.code} ({changed} students)",
                 meta={"minor_course_id": course.id, "rows": changed})
    db.flush()
    return changed


# ── coordinator: fees ─────────────────────────────────────────────────────
def set_fee_schedule(db: Session, program: MinorProgram, items: list[dict], *, actor: User) -> list[dict]:
    semesters = {course_semester(program, c) for c in program.courses}
    clean, seen = [], set()
    for item in items:
        sem = int(item.get("semester"))
        if semesters and sem not in semesters:
            raise ValidationError(f"{program.name} has no courses in semester {sem}.")
        if sem in seen:
            raise ValidationError(f"Semester {sem} is listed twice.")
        seen.add(sem)
        amount = float(item.get("amount"))
        if amount < 0:
            raise ValidationError("A fee cannot be negative.")
        due = item.get("due_on")
        if due:
            dt.date.fromisoformat(str(due))
        clean.append({"semester": sem, "amount": amount, "due_on": str(due) if due else None,
                      "note": (item.get("note") or "").strip() or None})
    program.rules = {**(program.rules or {}), "fees": sorted(clean, key=lambda f: f["semester"])}
    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_program", entity_id=program.id,
                 actor=actor, description=f"{program.code}: fee schedule set",
                 meta={"fees": clean})
    db.flush()
    return clean


def record_payment(db: Session, enrollment: MinorEnrollment, semester: int, *, amount: float,
                   reference: str | None, paid_on: dt.date | None, actor: User) -> MinorFeePayment:
    if semester not in fee_schedule(enrollment.minor_program):
        raise ValidationError(f"No fee is set for semester {semester} yet.")
    if amount <= 0:
        raise ValidationError("Record the amount paid.")
    payment = _payments(db, enrollment).get(semester)
    if payment is None:
        payment = MinorFeePayment(enrollment_id=enrollment.id, semester=semester, amount_paid=amount)
        db.add(payment)
    payment.amount_paid, payment.reference, payment.paid_on = amount, (reference or "").strip() or None, paid_on
    payment.recorded_by_user_id = actor.id
    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_enrollment", entity_id=enrollment.id,
                 actor=actor, description=f"Minor fee for semester {semester} recorded as paid",
                 meta={"amount": amount, "reference": payment.reference})
    db.flush()
    return payment


def clear_payment(db: Session, enrollment: MinorEnrollment, semester: int, *, actor: User) -> None:
    payment = _payments(db, enrollment).get(semester)
    if payment is None:
        raise NotFoundError("No payment is recorded for that semester.")
    db.delete(payment)
    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_enrollment", entity_id=enrollment.id,
                 actor=actor, description=f"Minor fee payment for semester {semester} removed")
    db.flush()


def fee_status(db: Session, program: MinorProgram) -> list[dict]:
    fees = fee_schedule(program)
    rows = []
    for enrollment in enrolled(db, program):
        student = db.get(Student, enrollment.student_id)
        paid = _payments(db, enrollment)
        rows.append({
            "enrollment_id": enrollment.id, "student_name": student.user.full_name,
            "roll_number": student.roll_number,
            "semesters": [{"semester": sem, "amount": float(f["amount"]),
                           "paid": sem in paid,
                           "reference": paid[sem].reference if sem in paid else None}
                          for sem, f in sorted(fees.items())],
        })
    return rows
