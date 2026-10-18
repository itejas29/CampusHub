"""Expected-vs-actual document tracking.

The point of this module: a student profile must show every document the
programme *requires*, not only the rows that happen to exist. A missing Week 3
report has to stay visible as NOT_SUBMITTED rather than vanishing, and it must
hold its stage open.

Requirements come from configuration, never from hard-coded lists:

* stage documents  — `internship_stages` rows with `requires_document = True`
* periodic reports — `expected_report_schedule()`, itself derived from the
  programme's `report_frequency` and `expected_report_count`
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.models.enums import (
    AuditAction, DocumentType, NotificationType, PENDING_REVIEW_STATUSES,
    SATISFYING_STATUSES, StageStatus, SubmissionStatus,
)
from app.models.identity import Student, User
from app.models.internships import (
    InternshipDocument, InternshipEnrollment, InternshipReport, InternshipStage,
)
from app.core.config import settings
from app.services import audit, notifications
from app.services.internships import expected_report_schedule


def protected_url(file_id: int | None) -> str | None:
    """Authorised view/download route for a stored file.

    Deliberately NOT the raw storage path: `/media/...` is an unauthenticated
    static mount in development and would be a public S3 object in production.
    Every read goes through `/files/{id}/download`, which checks access.
    """
    if not file_id:
        return None
    return f"{settings.API_V1_PREFIX}/files/{file_id}/download"

#: Reviewer decisions and the status each produces.
REVIEW_TRANSITIONS = {
    "start_review": SubmissionStatus.UNDER_REVIEW,
    "verify": SubmissionStatus.VERIFIED,
    "reject": SubmissionStatus.REJECTED,
}

#: A student may replace a submission only while it is in one of these states.
RESUBMITTABLE = frozenset({
    SubmissionStatus.REJECTED, SubmissionStatus.REVISION_REQUESTED,
    SubmissionStatus.DRAFT, SubmissionStatus.SUBMITTED,
})


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass(slots=True)
class ExpectedDocument:
    """One required artefact, whether or not it has been submitted."""

    key: str                          # stable id, e.g. "stage:CERTIFICATE" / "week:3"
    label: str
    kind: str                         # "stage" | "report"
    status: SubmissionStatus
    is_mandatory: bool = True
    document_type: str | None = None
    stage_id: int | None = None
    stage_code: str | None = None
    week_number: int | None = None
    #: Populated only when a real file exists — never a fabricated link.
    document_id: int | None = None
    report_id: int | None = None
    file_id: int | None = None
    file_name: str | None = None
    file_url: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    submitted_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None
    reviewed_by: str | None = None
    review_comment: str | None = None
    revision: int = 1
    period_start: dt.date | None = None
    period_end: dt.date | None = None

    @property
    def is_submitted(self) -> bool:
        return self.status is not SubmissionStatus.NOT_SUBMITTED

    @property
    def is_satisfied(self) -> bool:
        return self.status in SATISFYING_STATUSES

    @property
    def awaits_review(self) -> bool:
        return self.status in PENDING_REVIEW_STATUSES


@dataclass(slots=True)
class DocumentGroup:
    title: str
    items: list[ExpectedDocument] = field(default_factory=list)

    @property
    def submitted(self) -> int:
        return sum(1 for i in self.items if i.is_submitted)

    @property
    def satisfied(self) -> int:
        return sum(1 for i in self.items if i.is_satisfied)

    @property
    def total(self) -> int:
        return len(self.items)


def _reviewer_name(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user.full_name if user else None


def expected_documents(db: Session,
                       enrollment: InternshipEnrollment) -> list[DocumentGroup]:
    """The full expected set for this enrolment, actual state merged in.

    Groups are ordered the way a reviewer reads them: periodic reports first
    (because they are the bulk of the evidence), then stage documents.
    """
    program = enrollment.program

    documents = list(db.scalars(
        select(InternshipDocument)
        .where(InternshipDocument.enrollment_id == enrollment.id)
        .order_by(InternshipDocument.created_at)
    ))
    reports = list(db.scalars(
        select(InternshipReport)
        .where(InternshipReport.enrollment_id == enrollment.id)
    ))

    groups: list[DocumentGroup] = []

    # ── periodic reports (Summer Internship weeks) ────────────────────────
    schedule = expected_report_schedule(program)
    if schedule:
        by_week = {r.sequence_number: r for r in reports
                   if r.report_type.value != "FINAL"}
        period, title = {"DAILY": ("Day", "Daily Reports"), "WEEKLY": ("Week", "Weekly Reports"),
                         "FORTNIGHTLY": ("Fortnight", "Fortnightly Reports"),
                         "MONTHLY": ("Month", "Monthly Reports")
                         }.get(program.report_frequency.value, ("Report", "Reports"))
        group = DocumentGroup(title=title)
        for slot in schedule:
            week = slot["sequence_number"]
            report = by_week.get(week)
            group.items.append(ExpectedDocument(
                key=f"week:{week}",
                label=f"{period} {week} Report",
                kind="report",
                week_number=week,
                period_start=slot["period_start"],
                period_end=slot["period_end"],
                status=(report.status if report
                        else SubmissionStatus.NOT_SUBMITTED),
                report_id=report.id if report else None,
                file_id=report.file_id if report else None,
                file_url=protected_url(report.file_id) if report else None,
                submitted_at=report.submitted_at if report else None,
                reviewed_at=report.reviewed_at if report else None,
                reviewed_by=(_reviewer_name(db, report.reviewed_by_user_id)
                             if report else None),
                review_comment=report.feedback if report else None,
                revision=report.revision if report else 1,
            ))
        groups.append(group)

    # ── stage documents (certificate, poster, presentation, …) ────────────
    stages = list(db.scalars(
        select(InternshipStage)
        .where(InternshipStage.program_id == program.id)
        .order_by(InternshipStage.sequence)
    ))
    doc_by_stage: dict[int, InternshipDocument] = {}
    for document in documents:
        if document.stage_id is not None:
            # Latest submission per stage wins.
            doc_by_stage[document.stage_id] = document

    skipped = {p.stage_id for p in enrollment.stage_progress
               if p.status == StageStatus.SKIPPED}
    required = DocumentGroup(title="Required Documents")
    for stage in stages:
        if not stage.requires_document or stage.id in skipped:
            continue
        document = doc_by_stage.get(stage.id)
        required.items.append(ExpectedDocument(
            key=f"stage:{stage.code}",
            label=stage.name,
            kind="stage",
            is_mandatory=stage.is_mandatory,
            document_type=(stage.document_type.value if stage.document_type
                           else None),
            stage_id=stage.id,
            stage_code=stage.code,
            status=(document.status if document
                    else SubmissionStatus.NOT_SUBMITTED),
            document_id=document.id if document else None,
            file_id=document.file_id if document else None,
            file_name=(document.file.original_name
                       if document and document.file else None),
            file_url=protected_url(document.file_id) if document else None,
            size_bytes=(document.file.size_bytes
                        if document and document.file else None),
            content_type=(document.file.content_type
                          if document and document.file else None),
            submitted_at=(document.submitted_at or document.created_at
                          if document else None),
            reviewed_at=document.reviewed_at if document else None,
            reviewed_by=(_reviewer_name(db, document.reviewed_by_user_id)
                         if document else None),
            review_comment=document.review_comment if document else None,
            revision=document.revision if document else 1,
        ))
    if required.items:
        groups.append(required)

    # ── the final report, when the programme expects one ──────────────────
    final = next((r for r in reports if r.report_type.value == "FINAL"), None)
    has_final_stage = any(
        s.document_type == DocumentType.REPORT for s in stages if s.requires_document
    )
    if final is not None or (schedule and not has_final_stage):
        groups.append(DocumentGroup(title="Final Report", items=[ExpectedDocument(
            key="report:final",
            label="Final Report",
            kind="report",
            status=(final.status if final else SubmissionStatus.NOT_SUBMITTED),
            report_id=final.id if final else None,
            file_url=protected_url(final.file_id) if final else None,
            submitted_at=final.submitted_at if final else None,
            reviewed_at=final.reviewed_at if final else None,
            reviewed_by=(_reviewer_name(db, final.reviewed_by_user_id)
                         if final else None),
            review_comment=final.feedback if final else None,
            revision=final.revision if final else 1,
        )]))

    # ── anything uploaded outside a configured stage ──────────────────────
    extras = [d for d in documents if d.stage_id is None]
    if extras:
        group = DocumentGroup(title="Other Submissions")
        for document in extras:
            group.items.append(ExpectedDocument(
                key=f"doc:{document.id}",
                label=document.title or document.document_type.value.title(),
                kind="stage",
                is_mandatory=False,
                document_type=document.document_type.value,
                status=document.status,
                document_id=document.id,
                file_id=document.file_id,
                file_name=document.file.original_name if document.file else None,
                file_url=protected_url(document.file_id),
                size_bytes=document.file.size_bytes if document.file else None,
                content_type=document.file.content_type if document.file else None,
                submitted_at=document.submitted_at or document.created_at,
                reviewed_at=document.reviewed_at,
                reviewed_by=_reviewer_name(db, document.reviewed_by_user_id),
                review_comment=document.review_comment,
                revision=document.revision,
            ))
        groups.append(group)

    return groups


# ── stage completion, driven by documents ─────────────────────────────────
def stage_requirements_met(db: Session, enrollment: InternshipEnrollment,
                           stage: InternshipStage) -> tuple[bool, str | None]:
    """Can this stage be considered complete?

    A stage that requires a document needs a *verified* one. A stage that
    represents the reporting period needs every expected report satisfied, so a
    missing Week 3 keeps it open.
    """
    if stage.requires_document:
        document = db.scalar(
            select(InternshipDocument).where(
                InternshipDocument.enrollment_id == enrollment.id,
                InternshipDocument.stage_id == stage.id,
            ).order_by(InternshipDocument.created_at.desc()).limit(1)
        )
        if document is None:
            return False, f"{stage.name}: document not submitted."
        if document.status not in SATISFYING_STATUSES:
            return False, (f"{stage.name}: document is "
                           f"{document.status.value.replace('_', ' ').lower()}.")
        return True, None

    # The "in progress" stage of a reporting programme is gated on the reports.
    schedule = expected_report_schedule(enrollment.program)
    if schedule and stage.code in {"IN_PROGRESS", "INTERNSHIP"}:
        reports = {
            r.sequence_number: r for r in db.scalars(
                select(InternshipReport).where(
                    InternshipReport.enrollment_id == enrollment.id,
                    InternshipReport.report_type != "FINAL",
                )
            )
        }
        missing = [
            slot["sequence_number"] for slot in schedule
            if slot["sequence_number"] not in reports
            or reports[slot["sequence_number"]].status not in SATISFYING_STATUSES
        ]
        if missing:
            weeks = ", ".join(str(w) for w in missing[:4])
            more = "…" if len(missing) > 4 else ""
            return False, (f"{stage.name}: week {weeks}{more} outstanding "
                           f"({len(missing)} of {len(schedule)}).")
    return True, None


def progress(db: Session, enrollment: InternshipEnrollment) -> dict:
    """Document-driven progress.

    Counts stages that are genuinely complete — approved *and*, where the stage
    requires evidence, backed by a verified submission. Never an arbitrary
    percentage.
    """
    from app.services.internships import stage_timeline

    timeline = stage_timeline(db, enrollment)
    if not timeline:
        return {"completed": 0, "total": 0, "percent": 0, "blockers": []}

    completed = 0
    blockers: list[str] = []
    for view in timeline:
        if view.status == StageStatus.SKIPPED:
            # Not part of this student's track: nothing to evidence.
            completed += 1
            continue
        approved = view.status == StageStatus.APPROVED
        met, reason = stage_requirements_met(db, enrollment, view.stage)
        if approved and met:
            completed += 1
        elif reason and view.stage.is_mandatory:
            blockers.append(reason)

    total = len(timeline)
    return {
        "completed": completed,
        "total": total,
        "percent": round(completed * 100 / total) if total else 0,
        "blockers": blockers,
    }


# ── review workflow ───────────────────────────────────────────────────────
def review_document(db: Session, *, document: InternshipDocument, decision: str,
                    comment: str | None, actor: User) -> InternshipDocument:
    """Move a submission through UNDER_REVIEW → VERIFIED / REJECTED."""
    if decision not in REVIEW_TRANSITIONS:
        raise BusinessRuleError(
            f"Unknown review decision '{decision}'. "
            f"Expected one of: {', '.join(REVIEW_TRANSITIONS)}."
        )
    if decision == "reject" and not (comment or "").strip():
        raise BusinessRuleError(
            "A rejection must include a reason so the student knows what to fix."
        )

    document.status = REVIEW_TRANSITIONS[decision]
    document.reviewed_by_user_id = actor.id
    document.reviewed_at = utcnow()
    document.review_comment = comment

    enrollment = db.get(InternshipEnrollment, document.enrollment_id)
    student = db.get(Student, enrollment.student_id) if enrollment else None
    if student and decision in ("verify", "reject"):
        notifications.notify(
            db, user_id=student.user_id,
            type=NotificationType.INTERNSHIP_SUBMISSION,
            title=("Document verified" if decision == "verify"
                   else "Document rejected — resubmission needed"),
            message=(document.title or document.document_type.value.title())
                    + (f": {comment}" if comment else ""),
            link=f"/internships/record/{document.enrollment_id}",
        )
    audit.record(
        db, action=AuditAction.STATUS_CHANGE, entity_type="internship_document",
        entity_id=document.id, actor=actor,
        description=f"Document marked {document.status.value}",
        meta={"decision": decision, "comment": comment},
    )
    return document


def assert_can_resubmit(document: InternshipDocument) -> None:
    if document.status not in RESUBMITTABLE:
        raise BusinessRuleError(
            f"This submission is {document.status.value.replace('_', ' ').lower()} "
            "and can no longer be replaced."
        )


# ── file-level authorisation ──────────────────────────────────────────────
def assert_can_read_file(db: Session, file_id: int, user: User) -> None:
    """Authorise reading one stored file.

    A blanket "any staff member" rule is too wide: a club administrator has no
    business opening a student's internship certificate. When a file belongs to
    an internship submission the check reuses the internship scoping rules —
    own record, assigned mentees, or the programmes the caller coordinates.
    Files not attached to an internship fall back to the uploader plus academic
    staff (syllabus PDFs, avatars).
    """
    from app.models.enums import Role
    from app.models.system import StoredFile
    from app.services import scope

    stored = db.get(StoredFile, file_id)
    if stored is None:
        raise NotFoundError("File not found.")
    if user.has_role(Role.SUPER_ADMIN):
        return
    if stored.uploaded_by_user_id == user.id:
        return

    # Is this file part of an internship submission?
    enrollment_id = db.scalar(
        select(InternshipDocument.enrollment_id).where(
            InternshipDocument.file_id == file_id
        )
    ) or db.scalar(
        select(InternshipReport.enrollment_id).where(
            InternshipReport.file_id == file_id
        )
    )

    if enrollment_id is not None:
        enrollment = db.get(InternshipEnrollment, enrollment_id)
        if enrollment is None:
            raise PermissionDeniedError("You do not have access to this file.")
        if scope.can_manage_program(db, user, enrollment.program):
            return
        from app.models.identity import Faculty

        faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
        if faculty is not None and (
            enrollment.mentor_faculty_id == faculty.id
            or (enrollment.group and enrollment.group.faculty_id == faculty.id)
        ):
            return
        student = db.get(Student, enrollment.student_id)
        if student is not None and student.user_id == user.id:
            return
        raise PermissionDeniedError(
            "You do not have access to this student's documents."
        )

    # Not an internship artefact — academic staff may read it.
    if user.has_role(Role.DEPARTMENT_ADMIN, Role.FACULTY,
                     Role.INTERNSHIP_COORDINATOR):
        return
    raise PermissionDeniedError("You do not have access to this file.")
