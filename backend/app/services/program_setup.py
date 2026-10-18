"""A coordinator edits a programme's stages and rubric, and confirms them.

Stages and rubrics are data on the one internship engine. The Semester VII and
VIII projects were seeded with a starting point the department still has to
confirm, and until now only a database edit could change it. The rules here
keep an edit from corrupting records already under way:

* **Stages** — add, rename, reorder, change what each needs, or remove. A new
  stage reaches every student's record at once. A stage cannot be removed once
  a student has submitted work against it (or a document is attached to it); a
  stage's code never changes, because tracks and records refer to it.
* **Rubric** — editable until the first marks are recorded against it, then
  frozen, so every student of the programme is marked on the same scale.
* **Confirmation** — each item the department had to confirm (`stages`,
  `rubric`, `credits`, …) is confirmed separately, by the coordinator, on the
  record. Editing does not confirm anything by itself.

Every change is audited.
"""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationError
from app.models.enums import AuditAction, DocumentType, EvaluatorRole, StageStatus
from app.models.identity import User
from app.models.internships import (
    EnrollmentStageProgress, EvaluationCriteria, InternshipDocument, InternshipEnrollment,
    InternshipEvaluation, InternshipProgram, InternshipStage,
)
from app.services import audit
from app.services import internships as engine

OWNERS = ("STUDENT", "COORDINATOR", "FACULTY")
#: Stage progress that means a student has already acted on the stage.
_STARTED = (StageStatus.SUBMITTED, StageStatus.APPROVED, StageStatus.REJECTED)


def _code(text: str) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")[:50]
    if not code:
        raise ValidationError("Every stage needs a name.")
    return code


# ── stages ────────────────────────────────────────────────────────────────
def replace_stages(db: Session, program: InternshipProgram, items: list[dict], *,
                   actor: User) -> list[InternshipStage]:
    """Make the programme's stages exactly `items`, in that order.

    An item with an `id` updates that stage; one without creates a stage; a
    current stage left out is removed (when nothing has been done against it).
    """
    if not items:
        raise ValidationError("A programme needs at least one stage.")
    current = {s.id: s for s in db.scalars(select(InternshipStage).where(
        InternshipStage.program_id == program.id))}
    kept_ids = {i["id"] for i in items if i.get("id")}
    unknown = kept_ids - set(current)
    if unknown:
        raise ValidationError("A stage in the list belongs to another programme.")

    removed = [s for sid, s in current.items() if sid not in kept_ids]
    for stage in removed:
        started = db.scalar(select(func.count(EnrollmentStageProgress.id)).where(
            EnrollmentStageProgress.stage_id == stage.id,
            EnrollmentStageProgress.status.in_(_STARTED))) or 0
        documents = db.scalar(select(func.count(InternshipDocument.id)).where(
            InternshipDocument.stage_id == stage.id)) or 0
        if started or documents:
            raise BusinessRuleError(
                f"“{stage.name}” cannot be removed: {started or documents} student"
                f"{'s have' if (started or documents) != 1 else ' has'} already "
                "submitted work for it. Rename it or make it optional instead.")

    codes: set[str] = set()
    result: list[InternshipStage] = []
    # Park every kept stage on a free sequence first, so reordering never trips
    # over itself.
    for offset, stage in enumerate(current.values(), start=1000):
        stage.sequence = offset
    for stage in removed:
        for progress in db.scalars(select(EnrollmentStageProgress).where(
                EnrollmentStageProgress.stage_id == stage.id)):
            db.delete(progress)
        db.delete(stage)
    db.flush()

    for sequence, item in enumerate(items, start=1):
        name = (item.get("name") or "").strip()
        if not name:
            raise ValidationError("Every stage needs a name.")
        owner = item.get("owner_role") or "STUDENT"
        if owner not in OWNERS:
            raise ValidationError(f"A stage is done by the student, the coordinator or faculty, not {owner}.")
        doc_type = item.get("document_type")
        requires_document = bool(item.get("requires_document"))
        if requires_document and not doc_type:
            raise ValidationError(f"“{name}” needs a document: say which kind.")
        stage = current.get(item.get("id")) if item.get("id") else None
        if stage is None:
            code = _code(item.get("code") or name)
            stage = InternshipStage(program_id=program.id, code=code)
            db.add(stage)
        if stage.code in codes:
            raise ValidationError(f"Two stages are both called {stage.code}.")
        codes.add(stage.code)
        stage.name = name[:150]
        stage.description = (item.get("description") or "").strip() or None
        stage.sequence = sequence
        stage.is_mandatory = bool(item.get("is_mandatory", True))
        stage.requires_document = requires_document
        stage.document_type = DocumentType(doc_type) if requires_document else None
        stage.owner_role = owner
        result.append(stage)
    db.flush()

    # New stages reach every record; the current step is recomputed.
    for enrollment in db.scalars(select(InternshipEnrollment).where(
            InternshipEnrollment.program_id == program.id)):
        engine.initialise_stage_progress(db, enrollment=enrollment, program=program)
        db.refresh(enrollment)
        engine._advance_current_stage(db, enrollment)

    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program",
                 entity_id=program.id, actor=actor,
                 description=f"Stages of {program.code} edited",
                 meta={"stages": [s.code for s in result],
                       "removed": [s.code for s in removed]})
    db.flush()
    return result


# ── rubric ────────────────────────────────────────────────────────────────
def rubric_in_use(db: Session, program: InternshipProgram) -> int:
    """How many evaluations have been recorded against this programme."""
    return db.scalar(select(func.count(InternshipEvaluation.id)).join(
        InternshipEnrollment, InternshipEnrollment.id == InternshipEvaluation.enrollment_id
    ).where(InternshipEnrollment.program_id == program.id)) or 0


def replace_criteria(db: Session, program: InternshipProgram, items: list[dict], *,
                     actor: User) -> list[EvaluationCriteria]:
    """Make the rubric exactly `items`, in that order — until marking starts."""
    used = rubric_in_use(db, program)
    if used:
        raise BusinessRuleError(
            f"Marks have already been recorded for {used} student"
            f"{'s' if used != 1 else ''}, so the rubric is fixed for this programme.")
    if not items:
        raise ValidationError("A rubric needs at least one criterion.")
    current = {c.id: c for c in db.scalars(select(EvaluationCriteria).where(
        EvaluationCriteria.program_id == program.id))}
    kept = {i["id"] for i in items if i.get("id")}
    if kept - set(current):
        raise ValidationError("A criterion in the list belongs to another programme.")
    for cid, criterion in current.items():
        if cid not in kept:
            db.delete(criterion)
    db.flush()

    result, codes = [], set()
    for sequence, item in enumerate(items, start=1):
        name = (item.get("name") or "").strip()
        if not name:
            raise ValidationError("Every criterion needs a name.")
        try:
            max_marks = float(item.get("max_marks"))
        except (TypeError, ValueError):
            raise ValidationError(f"“{name}”: give the maximum marks.") from None
        if not 0 < max_marks <= 1000:
            raise ValidationError(f"“{name}”: maximum marks must be between 1 and 1000.")
        criterion = current.get(item.get("id")) if item.get("id") else None
        if criterion is None:
            criterion = EvaluationCriteria(program_id=program.id, code=_code(item.get("code") or name),
                                           evaluator_role=EvaluatorRole.FACULTY_MENTOR)
            db.add(criterion)
        if criterion.code in codes:
            raise ValidationError(f"Two criteria are both called {criterion.code}.")
        codes.add(criterion.code)
        criterion.name = name[:180]
        criterion.description = (item.get("description") or "").strip() or None
        criterion.max_marks = max_marks
        criterion.weight = float(item.get("weight") or 1)
        criterion.sequence = sequence
        result.append(criterion)
    db.flush()
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program",
                 entity_id=program.id, actor=actor,
                 description=f"Rubric of {program.code} edited "
                             f"({sum(float(c.max_marks) for c in result):g} marks)",
                 meta={"criteria": [(c.code, float(c.max_marks)) for c in result]})
    return result


# ── confirming what the department had to confirm ─────────────────────────
def confirm(db: Session, program: InternshipProgram, item: str, *, actor: User) -> list[str]:
    pending = list((program.config or {}).get("requires_faculty_confirmation") or [])
    if item not in pending:
        raise ValidationError(f"“{item}” is not awaiting confirmation for {program.name}.")
    pending.remove(item)
    program.config = {**(program.config or {}), "requires_faculty_confirmation": pending}
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program",
                 entity_id=program.id, actor=actor,
                 description=f"{program.code}: {item} confirmed by the coordinator",
                 meta={"confirmed": item, "still_pending": pending})
    db.flush()
    return pending
