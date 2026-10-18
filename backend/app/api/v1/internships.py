"""One router for every internship programme.

CSSI and Summer Internship are the same endpoints with different
``InternshipProgram`` rows behind them.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import func, or_, select

from app.core.deps import (
    CurrentUser, DbSession, get_optional_faculty, require_permission, request_context,
)
from app.core.errors import (
    BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError, ValidationError,
)
from app.core.rbac import P
from app.models.enums import (
    SATISFYING_STATUSES,
    AuditAction, DocumentType, EnrollmentStatus, EvaluationStatus, EvaluatorRole,
    FileCategory, NotificationType, ProgramPhase, ProgramStatus, Role,
    SubmissionStatus,
)
from app.models.identity import Faculty, Student, User
from app.models.system import StoredFile
from app.models.internships import (
    ProjectTeam,
    EnrollmentStageProgress, EvaluationCriteria, EvaluationScore, InternshipDocument,
    InternshipEnrollment, InternshipEvaluation, InternshipGroup, InternshipProgram,
    InternshipProject, InternshipReport, InternshipStage, Organization,
)
from app.schemas.fields import csv_safe
from app.schemas.common import Message
from app.schemas.internships import (
    DocumentGroupOut, DocumentReviewRequest, ExpectedDocumentOut, ProgressOut,
    DocumentOut, EnrollRequest, EnrollmentDetail, EnrollmentSummary, EnrollmentUpdate,
    PresentationQueueRow, PresentationSchedule,
    EvaluationCriteriaOut, EvaluationOut, EvaluationScoreOut, EvaluationSubmit,
    GroupCreate, GroupOut, InternshipProgramCreate, InternshipProgramOut,
    InternshipProgramUpdate, MentorOverrideRequest, OrganizationCreate, OrganizationOut,
    ProjectDetailOut, ProjectDetailUpdate, ReportOut, ReportReview, ReportSubmit,
    StageActionRequest, StageOut, StageProgressOut, StageReviewRequest,
    MentorCapacityOut, BatchMentorAssignRequest, BatchMentorAssignResponse,
    InternshipWindowOpen, InternshipWindowOut, InternshipWindowUpdate, MentorRosterGroup,
    MentorRosterStudent, ProgramWindowsOut, AllocationMentorAdd, AllocationMentorReplace,
    ConfirmItem, CriteriaReplace, StagesReplace, TeamCreate, TeamMemberAdd, GuidePreferences,
)
from app.services import (
    audit, documents as docs, internships as engine, notifications, scope,
)
from app.services import internship_windows as program_windows
from app.services import mentor_allocation, program_setup, project_teams
from app.models.enums import InternshipWindowKind
from app.models.internships import InternshipWindow
from app.services.files import save_upload, signed_url

router = APIRouter(prefix="/internships", tags=["internships"])


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── access control helpers ────────────────────────────────────────────────
def _can_manage(user: CurrentUser, db=None,
                program: InternshipProgram | None = None) -> bool:
    """Coordinator rights.

    With a programme, the check is scoped: the caller must coordinate that
    programme's domain (CSSI vs Summer Internship) for that programme's
    department. Without one it answers the weaker "coordinates anything at all",
    used only to decide whether to show a management surface.
    """
    if user.has_role(Role.SUPER_ADMIN):
        return True
    if db is None:
        return user.has_role(Role.DEPARTMENT_ADMIN, Role.INTERNSHIP_COORDINATOR)
    if program is not None:
        return scope.can_manage_program(db, user, program)
    return bool(scope.managed_program_ids(db, user))


def _assert_can_view(db, enrollment: InternshipEnrollment, user: CurrentUser,
                     faculty: Faculty | None) -> None:
    """A student sees only their own record; faculty see their mentees; a
    coordinator sees the programmes they actually coordinate."""
    if _can_manage(user, db, enrollment.program):
        return
    student = db.get(Student, enrollment.student_id)
    if student and student.user_id == user.id:
        return
    if faculty and enrollment.mentor_faculty_id == faculty.id:
        return
    if faculty and enrollment.group and enrollment.group.faculty_id == faculty.id:
        return
    raise PermissionDeniedError("You do not have access to this internship record.")


def _assert_can_manage_program(db, user: CurrentUser,
                               program: InternshipProgram) -> None:
    if not _can_manage(user, db, program):
        raise PermissionDeniedError(
            f"You do not coordinate {program.name} for this department."
        )


def _assert_is_owner(db, enrollment: InternshipEnrollment, user: CurrentUser) -> Student:
    student = db.get(Student, enrollment.student_id)
    if student is None or student.user_id != user.id:
        raise PermissionDeniedError("Only the enrolled student can do this.")
    return student


def _assert_can_submit(db, enrollment: InternshipEnrollment, user: CurrentUser) -> Student:
    """Owner check plus the programme's semester window.

    A programme that has only been *announced* is readable but not writable —
    CSSI is floated in Semester II and does not accept submissions until
    Semester III begins.
    """
    student = _assert_is_owner(db, enrollment, user)
    engine.assert_submissions_open(enrollment.program, student.current_semester)
    return student


def _assert_can_review(db, enrollment: InternshipEnrollment, user: CurrentUser,
                       faculty: Faculty | None) -> None:
    if _can_manage(user, db, enrollment.program):
        return
    if engine.can_review(enrollment, faculty):
        return
    raise PermissionDeniedError("Only the student's mentor or a coordinator may review this.")


# ── serialisers ───────────────────────────────────────────────────────────
def _program_out(db, program: InternshipProgram,
                 student: Student | None = None) -> InternshipProgramOut:
    coordinator = (db.get(Faculty, program.coordinator_faculty_id)
                   if program.coordinator_faculty_id else None)
    enrolled = db.scalar(select(func.count(InternshipEnrollment.id))
                         .where(InternshipEnrollment.program_id == program.id)) or 0
    completed = db.scalar(
        select(func.count(InternshipEnrollment.id)).where(
            InternshipEnrollment.program_id == program.id,
            InternshipEnrollment.status == EnrollmentStatus.COMPLETED,
        )
    ) or 0

    my_enrollment = can_enroll = None
    blocked = None
    phase = ProgramPhase.ACTIVE
    if student:
        phase = engine.program_phase(program, student.current_semester)
        row = db.scalar(select(InternshipEnrollment).where(
            InternshipEnrollment.program_id == program.id,
            InternshipEnrollment.student_id == student.id,
        ))
        my_enrollment = row.id if row else None
        if row:
            can_enroll, blocked = False, "You are already enrolled."
        elif not engine.governs_batch(program, student.admission_year):
            can_enroll, blocked = False, f"This programme is {engine.batch_note(program)}."
        elif InternshipWindowKind.REGISTRATION in program_windows.kinds_for(program):
            # A window-run programme: the coordinator's registration window is
            # the authority, not the semester alone.
            try:
                program_windows.assert_can_register(db, program, student,
                                                    already_enrolled=False)
                can_enroll = True
            except BusinessRuleError as exc:
                can_enroll, blocked = False, exc.message
        elif phase is not ProgramPhase.ACTIVE and not engine.registers_early(
                program, student.current_semester):
            # Announced but not yet open, or already past — see program_phase().
            can_enroll = False
            blocked = engine.phase_note(program, phase, student.current_semester)
        elif program.status != ProgramStatus.REGISTRATION_OPEN:
            can_enroll, blocked = False, "Registration is not open for this programme."
        else:
            can_enroll = True

    domain = scope.domain_for_program(program)
    return InternshipProgramOut(
        coordination_domain=domain.value if domain else None,
        tracks=[{"key": t.get("key"), "label": t.get("label"), "description": t.get("description"),
                 "stages": t.get("stages"), **engine.registration_requirements(program, t)}
                for t in engine.program_tracks(program)],
        batch_note=engine.batch_note(program) or None,
        needs_confirmation=list((program.config or {}).get("requires_faculty_confirmation") or []),
        mentor_capacity=engine.mentor_capacity(program),
        window_kinds=[k.value for k in program_windows.kinds_for(program)],
        mentor_capacity_confirmed=engine.mentor_capacity_confirmed(program),
        mentor_allocation_locked_at=mentor_allocation.locked_at(program),
        mentor_allocation_ids=mentor_allocation.allocated_ids(program),
        id=program.id, code=program.code, name=program.name, type=program.type,
        description=program.description, department_id=program.department_id,
        target_semester=program.target_semester,
        announce_from_semester=program.announce_from_semester,
        visible_to_semester=program.visible_to_semester,
        phase=phase,
        phase_note=engine.phase_note(program, phase,
                                     student.current_semester if student else None),
        credits=float(program.credits),
        requires_group=program.requires_group,
        default_group_size=program.default_group_size,
        requires_organization=program.requires_organization,
        allowed_organization_types=program.allowed_organization_types or [],
        report_frequency=program.report_frequency,
        expected_report_count=program.expected_report_count,
        requires_industry_mentor=program.requires_industry_mentor,
        registration_opens_at=program.registration_opens_at,
        registration_closes_at=program.registration_closes_at,
        start_date=program.start_date, end_date=program.end_date,
        status=program.status,
        coordinator_name=coordinator.user.full_name if coordinator else None,
        stages=[StageOut.model_validate(s) for s in program.stages],
        criteria=[EvaluationCriteriaOut.model_validate(c) for c in program.criteria],
        enrolled_count=int(enrolled), completed_count=int(completed),
        group_count=len(program.groups),
        my_enrollment_id=my_enrollment, can_enroll=bool(can_enroll),
        enroll_blocked_reason=blocked,
    )


def _summary(db, enrollment: InternshipEnrollment,
             evaluation_status: EvaluationStatus | None = None) -> EnrollmentSummary:
    student = enrollment.student
    stage = (db.get(InternshipStage, enrollment.current_stage_id)
             if enrollment.current_stage_id else None)
    return EnrollmentSummary(
        id=enrollment.id, program_id=enrollment.program_id,
        program_code=enrollment.program.code if enrollment.program else None,
        program_type=(enrollment.program.type.value if enrollment.program else None),
        program_name=enrollment.program.name if enrollment.program else None,
        track=enrollment.track,
        track_label=next((t.get("label") for t in engine.program_tracks(enrollment.program)
                          if t.get("key") == enrollment.track), None) if enrollment.track else None,
        team=project_teams.team_out(db, enrollment),
        guide_preferences=project_teams.preference_names(db, enrollment),
        student_id=enrollment.student_id,
        student_name=student.user.full_name if student else None,
        roll_number=student.roll_number if student else None,
        department_code=(student.department.code
                         if student and student.department else None),
        division=student.division if student else None,
        semester=student.current_semester if student else None,
        avatar_url=student.user.avatar_url if student else None,
        group_id=enrollment.group_id,
        group_name=enrollment.group.name if enrollment.group else None,
        mentor_faculty_id=enrollment.mentor_faculty_id,
        mentor_name=enrollment.mentor.user.full_name if enrollment.mentor else None,
        organization_id=enrollment.organization_id,
        organization_name=(enrollment.organization.name
                           if enrollment.organization else None),
        status=enrollment.status,
        current_stage=stage.name if stage else None,
        progress_percent=docs.progress(db, enrollment)["percent"],
        evaluation_status=evaluation_status,
        final_marks=(float(enrollment.final_marks)
                     if enrollment.final_marks is not None else None),
        final_grade=enrollment.final_grade,
    )


def _criteria_out(criterion: EvaluationCriteria) -> EvaluationCriteriaOut:
    out = EvaluationCriteriaOut.model_validate(criterion)
    # The industry component comes from outside the institution; the UI marks
    # it and the API refuses student-entered marks for it.
    out.is_external = criterion.evaluator_role == EvaluatorRole.INDUSTRY_MENTOR
    return out


def _document_out(db, doc: InternshipDocument) -> DocumentOut:
    file = doc.file
    return DocumentOut(
        id=doc.id, document_type=doc.document_type, title=doc.title,
        file_id=doc.file_id, file_name=file.original_name if file else None,
        file_url=signed_url(file), content_type=file.content_type if file else None,
        size_bytes=file.size_bytes if file else None, status=doc.status,
        stage_id=doc.stage_id, remarks=doc.remarks, created_at=doc.created_at,
    )


def _report_out(db, report: InternshipReport) -> ReportOut:
    return ReportOut(
        id=report.id, report_type=report.report_type,
        sequence_number=report.sequence_number, title=report.title,
        period_start=report.period_start, period_end=report.period_end,
        summary=report.summary, tasks_completed=report.tasks_completed,
        challenges=report.challenges, next_plan=report.next_plan,
        hours_spent=(float(report.hours_spent)
                     if report.hours_spent is not None else None),
        file_url=signed_url(db.get(StoredFile, report.file_id))
        if report.file_id else None,
        status=report.status, submitted_at=report.submitted_at,
        reviewed_at=report.reviewed_at, feedback=report.feedback,
    )


def _evaluation_out(db, evaluation: InternshipEvaluation) -> EvaluationOut:
    user = (db.get(User, evaluation.evaluator_user_id)
            if evaluation.evaluator_user_id else None)
    return EvaluationOut(
        id=evaluation.id, enrollment_id=evaluation.enrollment_id,
        evaluator_user_id=evaluation.evaluator_user_id,
        evaluator_name=user.full_name if user else None,
        evaluator_role=evaluation.evaluator_role,
        evaluation_round=evaluation.evaluation_round, status=evaluation.status,
        is_absent=evaluation.is_absent,
        total_marks=(float(evaluation.total_marks)
                     if evaluation.total_marks is not None else None),
        max_marks=(float(evaluation.max_marks)
                   if evaluation.max_marks is not None else None),
        grade=evaluation.grade, comments=evaluation.comments,
        submitted_at=evaluation.submitted_at,
        scores=[
            EvaluationScoreOut(
                id=s.id, criteria_id=s.criteria_id,
                criteria_name=s.criteria.name if s.criteria else None,
                max_marks=float(s.criteria.max_marks) if s.criteria else None,
                marks=float(s.marks) if s.marks is not None else None,
                is_absent=s.is_absent, comments=s.comments,
            )
            for s in evaluation.scores
        ],
    )


def _detail(db, enrollment: InternshipEnrollment) -> EnrollmentDetail:
    student = enrollment.student
    documents = list(db.scalars(
        select(InternshipDocument)
        .where(InternshipDocument.enrollment_id == enrollment.id)
        .order_by(InternshipDocument.created_at.desc())
    ))
    reports = list(db.scalars(
        select(InternshipReport)
        .where(InternshipReport.enrollment_id == enrollment.id)
        .order_by(InternshipReport.report_type, InternshipReport.sequence_number)
    ))
    evaluations = list(db.scalars(
        select(InternshipEvaluation)
        .where(InternshipEvaluation.enrollment_id == enrollment.id)
    ))
    timeline = engine.stage_timeline(db, enrollment)
    mentor = enrollment.mentor
    base = _summary(db, enrollment,
                    evaluations[0].status if evaluations else None)

    return EnrollmentDetail(
        **base.model_dump(),
        team_limits=project_teams.team_limits(enrollment.program, enrollment),
        preference_limit=project_teams.preference_count(enrollment.program, enrollment),
        email=student.user.email if student else None,
        phone=student.user.phone if student else None,
        guardian_name=student.guardian_name if student else None,
        guardian_phone=student.guardian_phone if student else None,
        report_frequency=(
            enrollment.program.report_frequency.value
            if enrollment.program and enrollment.program.report_frequency
            else "WEEKLY"
        ),
        start_date=enrollment.start_date, end_date=enrollment.end_date,
        presentation_at=enrollment.presentation_at,
        presentation_venue=enrollment.presentation_venue,
        presentation_panel=enrollment.presentation_panel,
        location=enrollment.location,
        stipend=float(enrollment.stipend) if enrollment.stipend is not None else None,
        industry_mentor_name=enrollment.industry_mentor_name,
        industry_mentor_email=enrollment.industry_mentor_email,
        industry_mentor_phone=enrollment.industry_mentor_phone,
        industry_mentor_designation=enrollment.industry_mentor_designation,
        industry_mentor_feedback=enrollment.industry_mentor_feedback,
        coordinator_remarks=enrollment.coordinator_remarks,
        organization=(OrganizationOut.model_validate(enrollment.organization)
                      if enrollment.organization else None),
        project=(ProjectDetailOut.model_validate(enrollment.project)
                 if enrollment.project else None),
        stages=[
            StageProgressOut(
                stage=StageOut.model_validate(v.stage), status=v.status,
                submitted_at=v.progress.submitted_at if v.progress else None,
                reviewed_at=v.progress.reviewed_at if v.progress else None,
                remarks=v.progress.remarks if v.progress else None,
                is_current=v.stage.id == enrollment.current_stage_id,
            )
            for v in timeline
        ],
        documents=[_document_out(db, d) for d in documents],
        reports=[_report_out(db, r) for r in reports],
        evaluations=[_evaluation_out(db, e) for e in evaluations],
        criteria=[_criteria_out(c)
                  for c in engine.rubric_for(db, enrollment.program_id)],
        mentor=(
            {
                "id": mentor.id, "name": mentor.user.full_name,
                "designation": mentor.designation,
                "department": mentor.department.name if mentor.department else None,
                "cabin": mentor.cabin,
                "email": mentor.public_email or mentor.user.email,
                "phone": mentor.public_phone,
                "specialization": mentor.specialization,
                "avatar_url": mentor.user.avatar_url,
            } if mentor else None
        ),
        report_schedule=[
            {**item, "period_start": item["period_start"].isoformat(),
             "period_end": item["period_end"].isoformat()}
            for item in engine.expected_report_schedule(enrollment.program)
        ],
        document_groups=[
            DocumentGroupOut(
                title=group.title, submitted=group.submitted,
                satisfied=group.satisfied, total=group.total,
                items=[
                    ExpectedDocumentOut(
                        **{k: getattr(item, k) for k in (
                            "key", "label", "kind", "status", "is_mandatory",
                            "document_type", "stage_id", "stage_code",
                            "week_number", "document_id", "report_id", "file_id",
                            "file_name", "file_url", "size_bytes", "content_type",
                            "submitted_at", "reviewed_at", "reviewed_by",
                            "review_comment", "revision", "period_start",
                            "period_end",
                        )},
                        is_submitted=item.is_submitted,
                        is_satisfied=item.is_satisfied,
                        awaits_review=item.awaits_review,
                    )
                    for item in group.items
                ],
            )
            for group in docs.expected_documents(db, enrollment)
        ],
        progress=ProgressOut(**docs.progress(db, enrollment)),
    )


# ── programmes ────────────────────────────────────────────────────────────
def _student_visible_programs(db, student: Student,
                              programs: list[InternshipProgram]
                              ) -> list[InternshipProgram]:
    """Narrow a programme list to what this student is entitled to see.

    Two independent filters, both server-side. The semester window decides
    *when* a programme exists for a student; the department decides *whether* it
    is theirs at all. Without the second, an ICT student was being served the
    Chemical, Civil, CSE, ECE, Mechanical and Petroleum variants of every
    programme.
    """
    enrolled_ids = set(db.scalars(
        select(InternshipEnrollment.program_id)
        .where(InternshipEnrollment.student_id == student.id)
    ))
    return [
        p for p in programs
        if (p.department_id is None or p.department_id == student.department_id
            or p.id in enrolled_ids)
        and (p.id in enrolled_ids or engine.governs_batch(p, student.admission_year))
        and engine.student_can_see_program(
            p, student.current_semester, has_enrollment=p.id in enrolled_ids)
    ]


@router.get("/programs", response_model=list[InternshipProgramOut])
def list_programs(db: DbSession, user: CurrentUser,
                  type: str | None = Query(None)) -> list[InternshipProgramOut]:
    stmt = select(InternshipProgram).order_by(InternshipProgram.code)
    if type:
        stmt = stmt.where(InternshipProgram.type == type)
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    programs = list(db.scalars(stmt))
    if student:
        programs = _student_visible_programs(db, student, programs)
    out = []
    for p in programs:
        row = _program_out(db, p, student)
        # Lets each screen list only what this person runs, instead of every
        # programme in the institution with actions that would then be refused.
        row.can_manage = not student and _can_manage(user, db, p)
        out.append(row)
    return out


@router.get("/programs/{program_id}", response_model=InternshipProgramOut)
def get_program(program_id: int, db: DbSession, user: CurrentUser) -> InternshipProgramOut:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Internship programme not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    # Fetching by id must obey the same rule as the listing, or the filter is
    # only a suggestion: the id is guessable and the payload is the whole
    # programme. Reported as "not found" rather than "forbidden" so the response
    # does not confirm that a programme the student cannot see exists.
    if student and not _student_visible_programs(db, student, [program]):
        raise NotFoundError("Internship programme not found.")
    return _program_out(db, program, student)


@router.get("/programs/{program_id}/export")
def export_program_enrollments_csv(
    program_id: int, db: DbSession, user: CurrentUser,
) -> Response:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Internship programme not found.")
    _assert_can_manage_program(db, user, program)

    enrollments = db.scalars(
        select(InternshipEnrollment)
        .where(InternshipEnrollment.program_id == program_id)
        .order_by(InternshipEnrollment.student_id)
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Roll Number", "Student Name", "Division", "Department",
        "Company / Organization", "Industry Mentor", "Faculty Mentor",
        "Current Stage", "Progress %", "Evaluation Status",
        "Total Marks", "Final Grade", "Status",
    ])
    # The export read four attributes the model does not have (mentor_faculty,
    # current_stage, progress_percent, evaluation_status), so it always failed.
    stage_names = dict(db.execute(select(InternshipStage.id, InternshipStage.name)
                                  .where(InternshipStage.program_id == program_id)).all())
    for e in enrollments:
        student = e.student
        student_user = student.user if student else None
        dept = student.department.name if student and student.department else ""
        mentor = e.mentor.user.full_name if e.mentor and e.mentor.user else ""
        org = e.organization.name if e.organization else ""
        stage = stage_names.get(e.current_stage_id, "") if e.current_stage_id else ""
        evaluations = list(db.scalars(select(InternshipEvaluation.status).where(
            InternshipEvaluation.enrollment_id == e.id)))
        evaluation = ("FINALISED" if EvaluationStatus.FINALISED in evaluations
                      else "SUBMITTED" if EvaluationStatus.SUBMITTED in evaluations
                      else "DRAFT" if evaluations else "")
        # Typed text (names, organisations) must not run as a spreadsheet formula.
        writer.writerow([csv_safe(cell) for cell in [
            student.roll_number if student else "",
            student_user.full_name if student_user else "",
            student.division if student else "",
            dept,
            org,
            e.industry_mentor_name or "",
            mentor,
            stage,
            engine.completion_percent(db, e),
            evaluation,
            float(e.final_marks) if e.final_marks is not None else "",
            e.final_grade or "",
            e.status.value,
        ]])

    csv_data = output.getvalue()
    code_slug = program.code.replace(" ", "_")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="internship_{code_slug}_grades.csv"'},
    )


@router.post("/programs", response_model=InternshipProgramOut, status_code=201)
def create_program(
    payload: InternshipProgramCreate, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = InternshipProgram(**payload.model_dump())
    db.add(program)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="internship_program",
                 entity_id=program.id, actor=user,
                 description=f"Created internship programme {program.code}")
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


@router.patch("/programs/{program_id}", response_model=InternshipProgramOut)
def update_program(
    program_id: int, payload: InternshipProgramUpdate, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Internship programme not found.")
    _assert_can_manage_program(db, user, program)
    changes = payload.model_dump(exclude_unset=True)
    capacity = changes.pop("mentor_capacity", None)
    for field, value in changes.items():
        setattr(program, field, value)
    description = "Updated programme settings"
    if capacity is not None:
        before = engine.mentor_capacity(program)
        # Reassigned, not mutated, so the JSON column is seen as changed.
        program.config = {**(program.config or {}), "mentor_capacity": capacity}
        description += f"; mentor cap confirmed at {capacity} (was {before})"
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program",
                 entity_id=program.id, actor=user, description=description)
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


# ── groups ────────────────────────────────────────────────────────────────
@router.get("/programs/{program_id}/groups", response_model=list[GroupOut])
def list_groups(program_id: int, db: DbSession, _: CurrentUser) -> list[GroupOut]:
    counts = dict(db.execute(
        select(InternshipEnrollment.group_id, func.count(InternshipEnrollment.id))
        .where(InternshipEnrollment.program_id == program_id)
        .group_by(InternshipEnrollment.group_id)
    ).all())
    groups = db.scalars(
        select(InternshipGroup).where(InternshipGroup.program_id == program_id)
        .order_by(InternshipGroup.name)
    )
    return [
        GroupOut(
            id=g.id, program_id=g.program_id, name=g.name, faculty_id=g.faculty_id,
            faculty_name=g.faculty.user.full_name if g.faculty else None,
            faculty_designation=g.faculty.designation if g.faculty else None,
            faculty_cabin=g.faculty.cabin if g.faculty else None,
            faculty_email=(g.faculty.public_email or g.faculty.user.email)
            if g.faculty else None,
            capacity=g.capacity, member_count=counts.get(g.id, 0),
            meeting_schedule=g.meeting_schedule,
        )
        for g in groups
    ]


@router.post("/programs/{program_id}/groups", response_model=GroupOut, status_code=201)
def create_group(
    program_id: int, payload: GroupCreate, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> GroupOut:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Internship programme not found.")
    _assert_can_manage_program(db, user, program)
    if payload.faculty_id:
        lead = db.get(Faculty, payload.faculty_id)
        if lead is not None:
            scope.assert_can_mentor(db, lead)
    group = InternshipGroup(program_id=program_id, **payload.model_dump())
    db.add(group)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="internship_group",
                 entity_id=group.id, actor=user, description=f"Created group {group.name}")
    db.commit()
    db.refresh(group)
    return GroupOut(
        id=group.id, program_id=program_id, name=group.name, faculty_id=group.faculty_id,
        faculty_name=group.faculty.user.full_name if group.faculty else None,
        faculty_designation=group.faculty.designation if group.faculty else None,
        faculty_cabin=group.faculty.cabin if group.faculty else None,
        faculty_email=(group.faculty.public_email or group.faculty.user.email)
        if group.faculty else None,
        capacity=group.capacity, member_count=0,
        meeting_schedule=group.meeting_schedule,
    )


# ── enrolment ─────────────────────────────────────────────────────────────
@router.get("/enrollments", response_model=list[EnrollmentSummary])
def list_enrollments(
    db: DbSession, user: CurrentUser, faculty=Depends(get_optional_faculty),
    program_id: int | None = Query(None), group_id: int | None = Query(None),
    status: EnrollmentStatus | None = Query(None),
    mine: bool = Query(False, description="Faculty: only my assigned students"),
    q: str | None = Query(None),
) -> list[EnrollmentSummary]:
    stmt = select(InternshipEnrollment)
    if program_id:
        stmt = stmt.where(InternshipEnrollment.program_id == program_id)
    if group_id:
        stmt = stmt.where(InternshipEnrollment.group_id == group_id)
    if status:
        stmt = stmt.where(InternshipEnrollment.status == status)

    managed = scope.managed_program_ids(db, user)
    if managed is not None and not managed:
        # Coordinates nothing — fall back to the mentor view.
        if faculty is None:
            raise PermissionDeniedError("Only faculty and coordinators can list students.")
        stmt = stmt.where(InternshipEnrollment.mentor_faculty_id == faculty.id)
    elif mine and faculty is not None:
        stmt = stmt.where(InternshipEnrollment.mentor_faculty_id == faculty.id)
    elif managed is not None:
        # A coordinator sees every student in the programmes they coordinate,
        # plus anyone they personally mentor elsewhere.
        conditions = [InternshipEnrollment.program_id.in_(managed)]
        if faculty is not None:
            conditions.append(InternshipEnrollment.mentor_faculty_id == faculty.id)
        stmt = stmt.where(or_(*conditions))

    rows = list(db.scalars(stmt.order_by(InternshipEnrollment.id)))
    if q:
        needle = q.strip().lower()
        rows = [
            r for r in rows
            if needle in (r.student.user.full_name or "").lower()
            or needle in (r.student.roll_number or "").lower()
        ]
    return [_summary(db, r) for r in rows]


@router.get("/enrollments/me", response_model=list[EnrollmentSummary])
def my_enrollments(db: DbSession, user: CurrentUser) -> list[EnrollmentSummary]:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        return []
    rows = db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.student_id == student.id
    ))
    return [_summary(db, r) for r in rows]


@router.get("/enrollments/{enrollment_id}", response_model=EnrollmentDetail)
def get_enrollment(enrollment_id: int, db: DbSession, user: CurrentUser,
                   faculty=Depends(get_optional_faculty)) -> EnrollmentDetail:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_view(db, enrollment, user, faculty)
    return _detail(db, enrollment)


@router.post("/programs/{program_id}/enroll", response_model=EnrollmentDetail,
             status_code=201)
def enroll(program_id: int, payload: EnrollRequest, db: DbSession,
           user: CurrentUser) -> EnrollmentDetail:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Internship programme not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise PermissionDeniedError("Only students can enrol in an internship.")
    if db.scalar(select(InternshipEnrollment.id).where(
            InternshipEnrollment.program_id == program.id,
            InternshipEnrollment.student_id == student.id)) is not None:
        # A second POST used to overwrite the first registration, add another
        # organisation row and resend "Enrolled". Corrections go through the
        # record (PATCH) while the window is open.
        raise ConflictError("You are already registered. Correct your details from your record.")
    track = engine.track_for(program, payload.track)
    engine.assert_registration_organisation(
        db, program, organization_id=payload.organization_id,
        new_type=payload.new_organization.type if payload.new_organization else None,
        track=track)
    if not engine.governs_batch(program, student.admission_year):
        raise BusinessRuleError(f"{program.name} is {engine.batch_note(program)}.")
    if InternshipWindowKind.REGISTRATION in program_windows.kinds_for(program):
        # The coordinator's registration window decides — it is what lets a
        # Semester II student register for a Semester III programme.
        program_windows.assert_can_register(db, program, student, already_enrolled=False)
    else:
        if program.status != ProgramStatus.REGISTRATION_OPEN:
            raise BusinessRuleError("Registration is not open for this programme.")
        engine.assert_can_register_now(program, student.current_semester)
    # Checked for every programme. It used to sit inside the window branch, so
    # the Summer Internship took registrations with no industry supervisor.
    if engine.registration_requirements(program, track)["requires_supervisor"] and not (
            (payload.industry_mentor_name or "").strip()
            and (payload.industry_mentor_phone or "").strip()):
        raise ValidationError(
            "Give the name and phone number of your supervisor at the organisation.")

    enrollment = engine.enroll_student(db, program=program, student=student, actor=user,
                                       track=track["key"] if track else None)
    for field in ("industry_mentor_name", "industry_mentor_phone", "industry_mentor_email"):
        value = getattr(payload, field)
        if value:
            setattr(enrollment, field, value.strip() if isinstance(value, str) else value)

    if payload.new_organization:
        org = Organization(**payload.new_organization.model_dump(),
                           added_by_user_id=user.id)
        db.add(org)
        db.flush()
        enrollment.organization_id = org.id
    elif payload.organization_id:
        enrollment.organization_id = payload.organization_id

    notifications.notify(
        db, user_id=user.id, type=NotificationType.REGISTRATION_CONFIRMED,
        title=f"Enrolled in {program.name}",
        message="Complete each stage in order; your faculty mentor reviews every "
                "submission.",
        link=f"/internships/{program.id}",
    )
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment)


@router.patch("/enrollments/{enrollment_id}", response_model=EnrollmentDetail)
def update_enrollment(enrollment_id: int, payload: EnrollmentUpdate, db: DbSession,
                      user: CurrentUser,
                      faculty=Depends(get_optional_faculty)) -> EnrollmentDetail:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    if not _can_manage(user, db, enrollment.program):
        # Students edit only while the window is open. Ownership alone let a
        # Semester IV student keep editing a CSSI record that had concluded.
        if InternshipWindowKind.REGISTRATION in program_windows.kinds_for(enrollment.program):
            student = _assert_is_owner(db, enrollment, user)
            program_windows.assert_can_register(db, enrollment.program, student,
                                                already_enrolled=True)
        else:
            # Registration details stay editable for an early registrant.
            student = _assert_is_owner(db, enrollment, user)
            engine.assert_can_register_now(enrollment.program, student.current_semester)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(enrollment, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_enrollment",
                 entity_id=enrollment.id, actor=user, description="Updated internship details")
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment)


@router.put("/enrollments/{enrollment_id}/project", response_model=ProjectDetailOut)
def upsert_project(enrollment_id: int, payload: ProjectDetailUpdate, db: DbSession,
                   user: CurrentUser) -> ProjectDetailOut:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_submit(db, enrollment, user)

    project = enrollment.project
    if project is None:
        project = InternshipProject(enrollment_id=enrollment.id)
        db.add(project)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(project, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_project",
                 entity_id=enrollment.id, actor=user, description="Updated project details")
    db.commit()
    db.refresh(project)
    return ProjectDetailOut.model_validate(project)


# ── stages ────────────────────────────────────────────────────────────────
@router.post("/enrollments/{enrollment_id}/stages/submit",
             response_model=list[StageProgressOut])
def submit_stage(enrollment_id: int, payload: StageActionRequest, db: DbSession,
                 user: CurrentUser) -> list[StageProgressOut]:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_submit(db, enrollment, user)
    stage = db.get(InternshipStage, payload.stage_id)
    if stage is not None and stage.document_type == DocumentType.POSTER:
        program_windows.assert_can_submit_poster(db, enrollment.program)
    engine.submit_stage(db, enrollment=enrollment, stage_id=payload.stage_id,
                        actor=user, data=payload.data)
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment).stages


@router.post("/enrollments/{enrollment_id}/stages/review",
             response_model=list[StageProgressOut])
def review_stage(enrollment_id: int, payload: StageReviewRequest, db: DbSession,
                 user: CurrentUser,
                 faculty=Depends(get_optional_faculty)) -> list[StageProgressOut]:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_review(db, enrollment, user, faculty)
    engine.review_stage(db, enrollment=enrollment, stage_id=payload.stage_id,
                        approve=payload.approve, remarks=payload.remarks, actor=user)
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment).stages


# ── documents ─────────────────────────────────────────────────────────────
@router.post("/enrollments/{enrollment_id}/documents", response_model=DocumentOut,
             status_code=201)
async def upload_document(
    enrollment_id: int, db: DbSession, user: CurrentUser,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(DocumentType.OTHER),
    title: str | None = Form(None, max_length=200),
    stage_id: int | None = Form(None),
    week_number: int | None = Form(None),
) -> DocumentOut:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_submit(db, enrollment, user)
    if document_type == DocumentType.POSTER:
        program_windows.assert_can_submit_poster(db, enrollment.program)

    category = {
        DocumentType.CERTIFICATE: FileCategory.CERTIFICATE,
        DocumentType.REPORT: FileCategory.REPORT,
        DocumentType.OFFER_LETTER: FileCategory.OFFER_LETTER,
        DocumentType.POSTER: FileCategory.POSTER,
        DocumentType.PHOTO: FileCategory.PHOTO,
    }.get(document_type, FileCategory.OTHER)

    # Replacing a rejected submission updates the existing row so its history
    # (revision count, previous review comment) is preserved.
    existing = None
    if stage_id is not None:
        existing = db.scalar(
            select(InternshipDocument).where(
                InternshipDocument.enrollment_id == enrollment.id,
                InternshipDocument.stage_id == stage_id,
            ).order_by(InternshipDocument.created_at.desc()).limit(1)
        )
    if existing is not None:
        docs.assert_can_resubmit(existing)

    stored = await save_upload(db, file, category=category, uploaded_by=user)
    if existing is not None:
        existing.file_id = stored.id
        existing.title = title or file.filename
        existing.document_type = document_type
        existing.status = SubmissionStatus.SUBMITTED
        existing.submitted_at = utcnow()
        existing.revision += 1
        # Keep the previous comment visible until the reviewer decides again.
        existing.reviewed_at = None
        existing.reviewed_by_user_id = None
        doc = existing
    else:
        doc = InternshipDocument(
            enrollment_id=enrollment.id, stage_id=stage_id,
            document_type=document_type, title=title or file.filename,
            file_id=stored.id, uploaded_by_user_id=user.id,
            status=SubmissionStatus.SUBMITTED, submitted_at=utcnow(),
            week_number=week_number,
        )
        db.add(doc)
    # Flush so column defaults (revision) are populated before they are read.
    db.flush()

    # Tell the reviewer there is something waiting.
    if enrollment.mentor_faculty_id:
        mentor = db.get(Faculty, enrollment.mentor_faculty_id)
        if mentor:
            notifications.notify(
                db, user_id=mentor.user_id,
                type=NotificationType.INTERNSHIP_SUBMISSION,
                title="Document submitted for review",
                message=f"{enrollment.student.user.full_name}: "
                        f"{doc.title or document_type.value}"
                        + (f" (revision {doc.revision})" if doc.revision > 1 else ""),
                link=f"/internships/students/{enrollment.id}",
            )
    audit.record(db, action=AuditAction.UPLOAD, entity_type="internship_document",
                 entity_id=enrollment.id, actor=user,
                 description=f"{'Resubmitted' if existing else 'Uploaded'} "
                             f"{document_type.value}",
                 meta={"revision": doc.revision})
    db.commit()
    db.refresh(doc)
    return _document_out(db, doc)


@router.get("/enrollments/{enrollment_id}/documents/expected",
            response_model=list[DocumentGroupOut])
def expected_documents(enrollment_id: int, db: DbSession, user: CurrentUser,
                       faculty=Depends(get_optional_faculty)
                       ) -> list[DocumentGroupOut]:
    """Every document the programme expects, with the real state merged in.

    Items that have never been uploaded come back as NOT_SUBMITTED rather than
    being omitted, so a missing mandatory document stays visible.
    """
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_view(db, enrollment, user, faculty)
    return _detail(db, enrollment).document_groups


@router.post("/documents/{document_id}/review", response_model=DocumentOut)
def review_document(
    document_id: int, payload: DocumentReviewRequest, db: DbSession,
    user: CurrentUser, faculty=Depends(get_optional_faculty),
) -> DocumentOut:
    """Reviewer decision: start_review · verify · reject.

    Rejection requires a comment so the student knows what to fix, and the
    student may then resubmit.
    """
    document = db.get(InternshipDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    enrollment = db.get(InternshipEnrollment, document.enrollment_id)
    _assert_can_review(db, enrollment, user, faculty)

    docs.review_document(db, document=document, decision=payload.decision,
                         comment=payload.comment, actor=user)
    db.commit()
    db.refresh(document)
    return _document_out(db, document)


@router.get("/enrollments/{enrollment_id}/progress", response_model=ProgressOut)
def enrollment_progress(enrollment_id: int, db: DbSession, user: CurrentUser,
                        faculty=Depends(get_optional_faculty)) -> ProgressOut:
    """Progress computed from stage state AND the documents each stage needs."""
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_view(db, enrollment, user, faculty)
    return ProgressOut(**docs.progress(db, enrollment))


@router.delete("/documents/{document_id}", response_model=Message)
def delete_document(document_id: int, db: DbSession, user: CurrentUser) -> Message:
    doc = db.get(InternshipDocument, document_id)
    if doc is None:
        raise NotFoundError("Document not found.")
    enrollment = db.get(InternshipEnrollment, doc.enrollment_id)
    manager = _can_manage(user, db, enrollment.program)
    if not manager:
        _assert_can_submit(db, enrollment, user)
    # Reviewed documents become VERIFIED, not APPROVED — checking only APPROVED
    # let a student delete a document their mentor had already verified.
    if doc.status in (SubmissionStatus.APPROVED, SubmissionStatus.VERIFIED):
        raise BusinessRuleError("A verified document cannot be removed.")
    if doc.status == SubmissionStatus.UNDER_REVIEW and not manager:
        raise BusinessRuleError("Your mentor is reviewing this document, so it cannot be removed now.")
    db.delete(doc)
    audit.record(db, action=AuditAction.DELETE, entity_type="internship_document",
                 entity_id=document_id, actor=user, description="Removed document")
    db.commit()
    return Message(message="Document removed.")


# ── reports ───────────────────────────────────────────────────────────────
@router.post("/enrollments/{enrollment_id}/reports", response_model=ReportOut,
             status_code=201)
def submit_report(enrollment_id: int, payload: ReportSubmit, db: DbSession,
                  user: CurrentUser) -> ReportOut:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_submit(db, enrollment, user)
    engine.assert_report_in_schedule(enrollment.program, payload.report_type,
                                     payload.sequence_number)

    existing = db.scalar(select(InternshipReport).where(
        InternshipReport.enrollment_id == enrollment.id,
        InternshipReport.report_type == payload.report_type,
        InternshipReport.sequence_number == payload.sequence_number,
    ))
    if existing and existing.status in (SubmissionStatus.APPROVED, SubmissionStatus.VERIFIED):
        raise BusinessRuleError("This report has already been approved.")

    report = existing or InternshipReport(
        enrollment_id=enrollment.id, report_type=payload.report_type,
        sequence_number=payload.sequence_number,
    )
    for field, value in payload.model_dump(exclude={"report_type", "sequence_number"}).items():
        setattr(report, field, value)
    report.status = SubmissionStatus.SUBMITTED
    report.submitted_at = utcnow()
    if existing is None:
        db.add(report)

    if enrollment.mentor_faculty_id:
        mentor = db.get(Faculty, enrollment.mentor_faculty_id)
        if mentor:
            notifications.notify(
                db, user_id=mentor.user_id,
                type=NotificationType.INTERNSHIP_SUBMISSION,
                title="Internship report submitted",
                message=f"{enrollment.student.user.full_name} submitted "
                        f"{payload.report_type.value.lower()} report "
                        f"#{payload.sequence_number}.",
                link=f"/internships/students/{enrollment.id}",
            )
    audit.record(db, action=AuditAction.CREATE, entity_type="internship_report",
                 entity_id=enrollment.id, actor=user,
                 description=f"Submitted {payload.report_type.value} report "
                             f"#{payload.sequence_number}")
    db.commit()
    db.refresh(report)
    return _report_out(db, report)


@router.post("/reports/{report_id}/review", response_model=ReportOut)
def review_report(report_id: int, payload: ReportReview, db: DbSession,
                  user: CurrentUser,
                  faculty=Depends(get_optional_faculty)) -> ReportOut:
    report = db.get(InternshipReport, report_id)
    if report is None:
        raise NotFoundError("Report not found.")
    enrollment = db.get(InternshipEnrollment, report.enrollment_id)
    _assert_can_review(db, enrollment, user, faculty)
    engine.assert_report_review(report, payload.status, payload.feedback)

    report.status = payload.status
    report.feedback = payload.feedback
    report.reviewed_by_user_id = user.id
    report.reviewed_at = utcnow()

    notifications.notify(
        db, user_id=enrollment.student.user_id,
        type=NotificationType.INTERNSHIP_STAGE,
        title=f"Report {payload.status.value.replace('_', ' ').lower()}",
        message=payload.feedback or "Your mentor reviewed a report.",
        link=f"/internships/{enrollment.program_id}",
    )
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="internship_report",
                 entity_id=report.id, actor=user,
                 description=f"Report marked {payload.status.value}")
    db.commit()
    db.refresh(report)
    return _report_out(db, report)


# ── evaluation ────────────────────────────────────────────────────────────
@router.get("/programs/{program_id}/criteria", response_model=list[EvaluationCriteriaOut])
def rubric(program_id: int, db: DbSession, _: CurrentUser) -> list[EvaluationCriteriaOut]:
    return [_criteria_out(c) for c in engine.rubric_for(db, program_id)]


@router.post("/enrollments/{enrollment_id}/evaluation", response_model=EvaluationOut)
def submit_evaluation(
    enrollment_id: int, payload: EvaluationSubmit, db: DbSession, user: CurrentUser,
    request_ctx=Depends(request_context), faculty=Depends(get_optional_faculty),
) -> EvaluationOut:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_review(db, enrollment, user, faculty)
    # Marks lock when the coordinator's presentation window closes.
    program_windows.assert_marks_open(db, enrollment.program)

    criteria = engine.rubric_for(db, enrollment.program_id)
    valid_ids = {c.id for c in criteria}

    # A student must never be able to record marks — least of all the industry
    # mentor component, which originates outside the institution.
    if db.scalar(select(Student).where(Student.user_id == user.id)) is not None:
        raise PermissionDeniedError(
            "Students cannot record evaluation marks."
        )

    for score in payload.scores:
        if score.criteria_id not in valid_ids:
            raise ValidationError("An unknown evaluation criterion was submitted.")
        criterion = next(c for c in criteria if c.id == score.criteria_id)
        if score.marks is None:
            continue
        if score.marks < 0:
            raise ValidationError(f"{criterion.name}: marks cannot be negative.")
        if score.marks > float(criterion.max_marks):
            raise ValidationError(
                f"{criterion.name}: maximum is {criterion.max_marks} marks."
            )

    # Checked before anything is written. Finalising needs the student's work approved and verified first.
    if payload.finalise and not payload.is_absent:
        pending = engine.finalise_blockers(db, enrollment)
        if pending:
            raise BusinessRuleError(
                "Marks can be finalised once this work is approved and verified: "
                + ", ".join(pending) + ". Save them as a draft until then.")
    evaluation = db.scalar(select(InternshipEvaluation).where(
        InternshipEvaluation.enrollment_id == enrollment.id,
        InternshipEvaluation.evaluator_user_id == user.id,
        InternshipEvaluation.evaluation_round == 1,
    ))
    if evaluation is None:
        evaluation = InternshipEvaluation(
            enrollment_id=enrollment.id, evaluator_user_id=user.id,
            evaluator_role=(EvaluatorRole.FACULTY_MENTOR if faculty
                            else EvaluatorRole.COORDINATOR),
            evaluation_round=1,
        )
        db.add(evaluation)
        db.flush()
    elif evaluation.status == EvaluationStatus.FINALISED:
        raise BusinessRuleError("This evaluation has been finalised and is locked.")

    by_criteria = {s.criteria_id: s for s in evaluation.scores}
    for item in payload.scores:
        row = by_criteria.get(item.criteria_id)
        if row is None:
            row = EvaluationScore(evaluation_id=evaluation.id,
                                  criteria_id=item.criteria_id)
            db.add(row)
        row.marks = item.marks
        row.is_absent = item.is_absent
        row.comments = item.comments

    total, maximum = engine.compute_totals(
        criteria, {s.criteria_id: s.marks for s in payload.scores},
        is_absent=payload.is_absent,
    )
    # Finalising requires a complete rubric; a partial evaluation stays a draft.
    if payload.finalise and not payload.is_absent:
        scored = {s.criteria_id for s in payload.scores if s.marks is not None}
        missing = [c.name for c in criteria if c.id not in scored]
        if missing:
            raise BusinessRuleError(
                "Every component must be marked before finalising. Missing: "
                + ", ".join(missing)
            )
        if total > maximum:
            raise ValidationError(
                f"Total {total} exceeds the rubric maximum of {maximum}."
            )
    evaluation.is_absent = payload.is_absent
    evaluation.total_marks = total
    evaluation.max_marks = maximum
    evaluation.comments = payload.comments
    evaluation.grade = payload.grade
    evaluation.status = (EvaluationStatus.SUBMITTED if not payload.finalise
                         else EvaluationStatus.FINALISED)
    evaluation.submitted_at = utcnow()

    if payload.finalise:
        engine.finalise_enrollment(db, enrollment=enrollment, evaluation=evaluation,
                                   actor=user)
    audit.record(
        db, action=AuditAction.EVALUATION_SUBMIT, entity_type="internship_evaluation",
        entity_id=evaluation.id, actor=user,
        description=f"Evaluation {'finalised' if payload.finalise else 'saved'} "
                    f"({total}/{maximum})",
        meta={"is_absent": payload.is_absent}, **request_ctx,
    )
    db.commit()
    db.refresh(evaluation)
    return _evaluation_out(db, evaluation)


# ── coordinator overrides ─────────────────────────────────────────────────
@router.post("/enrollments/{enrollment_id}/mentor", response_model=EnrollmentSummary)
def override_mentor(
    enrollment_id: int, payload: MentorOverrideRequest, db: DbSession,
    request_ctx=Depends(request_context),
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> EnrollmentSummary:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_manage_program(db, user, enrollment.program)
    program_windows.assert_can_allocate_mentors(db, enrollment.program)
    mentor_allocation.assert_allowed_target(enrollment.program, payload.mentor_faculty_id)
    if payload.group_id is not None:
        group = db.get(InternshipGroup, payload.group_id)
        if group is None or group.program_id != enrollment.program_id:
            raise ValidationError("That group belongs to a different programme.")
        enrollment.group_id = group.id
    # A team shares one guide: assigning one member assigns them all.
    team = (db.get(ProjectTeam, enrollment.team_id) if enrollment.team_id else None)
    for member in (project_teams.members(db, team) if team else [enrollment]):
        engine.override_mentor(db, enrollment=member,
                               new_faculty_id=payload.mentor_faculty_id,
                               reason=payload.reason, actor=user)
    db.commit()
    db.refresh(enrollment)
    return _summary(db, enrollment)


@router.get("/programs/{program_id}/mentors-capacity", response_model=list[MentorCapacityOut])
def get_mentors_capacity(
    program_id: int, db: DbSession,
    user: CurrentUser,
) -> list[MentorCapacityOut]:
    """Each eligible mentor's load in this programme — for its coordinator only.

    Lists the programme's own department (minus the HoD), plus anyone already
    carrying students here, so an existing assignment never disappears from the
    screen that manages it.
    """
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")
    _assert_can_manage_program(db, user, program)

    capacity = engine.mentor_capacity(program)
    confirmed = engine.mentor_capacity_confirmed(program)
    assigned_counts = dict(
        db.execute(
            select(InternshipEnrollment.mentor_faculty_id, func.count(InternshipEnrollment.id))
            .where(InternshipEnrollment.program_id == program_id,
                   InternshipEnrollment.mentor_faculty_id.is_not(None))
            .group_by(InternshipEnrollment.mentor_faculty_id)
        ).all()
    )
    pool = engine.eligible_mentors(db, program)
    pool_ids = {f.id for f in pool}
    already = [f for f in (db.get(Faculty, fid) for fid in assigned_counts)
               if f is not None and f.id not in pool_ids]

    allocated = set(mentor_allocation.allocated_ids(program))
    out = []
    for f in sorted(pool + already, key=lambda f: f.user.full_name):
        count = assigned_counts.get(f.id, 0)
        out.append(MentorCapacityOut(
            faculty_id=f.id,
            name=f.user.full_name,
            employee_code=f.employee_code,
            department_code=f.department.code if f.department else None,
            designation=f.designation,
            avatar_url=f.user.avatar_url,
            assigned_count=count,
            max_capacity=capacity,
            capacity_confirmed=confirmed,
            remaining_capacity=max(0, capacity - count),
            is_full=count >= capacity,
            in_allocation=f.id in allocated,
        ))
    return out


@router.post("/programs/{program_id}/assign-mentors", response_model=BatchMentorAssignResponse)
def batch_assign_mentors(
    program_id: int, payload: BatchMentorAssignRequest, db: DbSession,
    request_ctx=Depends(request_context),
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> BatchMentorAssignResponse:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")
    _assert_can_manage_program(db, user, program)
    if not payload.clear_all:
        program_windows.assert_can_allocate_mentors(db, program)
    # A locked allocation changes one deliberate step at a time, never by a run.
    if payload.assignments and not (payload.clear_all or payload.allocate_by_roll_no
                                    or payload.rebalance or payload.auto_distribute
                                    or payload.by_preference):
        for item in payload.assignments:
            mentor_allocation.assert_allowed_target(program, item.mentor_faculty_id)
    else:
        mentor_allocation.assert_not_locked(program)

    capacity = engine.mentor_capacity(program)
    pool = engine.eligible_mentors(db, program)
    if payload.faculty_ids:
        by_id = {f.id: f for f in pool}
        outside = [fid for fid in payload.faculty_ids if fid not in by_id]
        if outside:
            raise ValidationError(
                "Some selected faculty cannot mentor this programme — they are "
                "outside its department or head a department."
            )
        # Keep the pool's name order whatever order the ids arrived in.
        wanted = set(payload.faculty_ids)
        pool = [f for f in pool if f.id in wanted]

    def _assign(enrollment, faculty_id, reason):
        engine.override_mentor(db, enrollment=enrollment, new_faculty_id=faculty_id,
                               reason=reason, actor=user, enforce_capacity=False)

    if payload.clear_all:
        cleared = 0
        for enrollment in db.scalars(select(InternshipEnrollment)
                                     .where(InternshipEnrollment.program_id == program_id)):
            if enrollment.mentor_faculty_id is not None:
                _assign(enrollment, None,
                        payload.reason or "Coordinator cleared all mentor assignments")
                cleared += 1
        db.commit()
        return BatchMentorAssignResponse(
            assigned_count=0,
            message=f"Cleared the mentor for {cleared} students.",
        )

    if payload.by_preference:
        result = project_teams.allocate_by_preference(db, program, actor=user)
        db.commit()
        return BatchMentorAssignResponse(
            assigned_count=result["placed"],
            message=(f"Allocated {result['placed']} students to a preferred guide."
                     + (f" {result['left']} could not be placed — their guides are full or "
                        "they ranked none; assign them below." if result["left"] else "")))

    if payload.allocate_by_roll_no or payload.rebalance:
        # Roll-number blocks: consecutive roll numbers share a mentor, which is
        # how the department reads a mentor list. Rebalance is the same run
        # over the whole eligible pool.
        enrollments = list(db.scalars(
            select(InternshipEnrollment)
            .join(Student, InternshipEnrollment.student_id == Student.id)
            .where(InternshipEnrollment.program_id == program_id)
            .order_by(Student.roll_number.asc())
        ))
        if not enrollments:
            return BatchMentorAssignResponse(assigned_count=0,
                                             message="No students enrolled in this programme.")
        if not pool:
            raise ValidationError("No eligible faculty mentors for this programme.")

        sizes = engine.split_by_roll(len(enrollments), len(pool), capacity)
        cursor, blocks = 0, []
        for faculty, size in zip(pool, sizes):
            block = enrollments[cursor:cursor + size]
            cursor += size
            for enrollment in block:
                _assign(enrollment, faculty.id,
                        f"Roll-number allocation: {faculty.user.full_name}")
            blocks.append(f"{faculty.user.full_name} ({block[0].student.roll_number}–"
                          f"{block[-1].student.roll_number})")
        for enrollment in enrollments[cursor:]:
            _assign(enrollment, None, "Unassigned: selected mentors are at capacity")
        db.commit()

        left = len(enrollments) - cursor
        message = (f"Allocated {cursor} students across {len(sizes)} mentors "
                   f"(at most {capacity} each).")
        if left:
            message += f" {left} still need a mentor — select more faculty."
        return BatchMentorAssignResponse(assigned_count=cursor, message=message)

    if payload.auto_distribute:
        unassigned = list(db.scalars(
            select(InternshipEnrollment)
            .where(InternshipEnrollment.program_id == program_id,
                   InternshipEnrollment.mentor_faculty_id.is_(None))
            .order_by(InternshipEnrollment.id)
        ))
        counts = dict(db.execute(
            select(InternshipEnrollment.mentor_faculty_id, func.count(InternshipEnrollment.id))
            .where(InternshipEnrollment.program_id == program_id,
                   InternshipEnrollment.mentor_faculty_id.is_not(None))
            .group_by(InternshipEnrollment.mentor_faculty_id)
        ).all())
        assigned = 0
        for enrollment in unassigned:
            open_ = [f for f in pool if counts.get(f.id, 0) < capacity]
            if not open_:
                break
            chosen = min(open_, key=lambda f: counts.get(f.id, 0))
            _assign(enrollment, chosen.id, payload.reason)
            counts[chosen.id] = counts.get(chosen.id, 0) + 1
            assigned += 1
        db.commit()
        left = len(unassigned) - assigned
        message = f"Allocated {assigned} students (at most {capacity} per mentor)."
        if left:
            message += f" {left} still need a mentor."
        return BatchMentorAssignResponse(assigned_count=assigned, message=message)

    if payload.assignments:
        changed = 0
        for item in payload.assignments:
            enrollment = db.get(InternshipEnrollment, item.enrollment_id)
            if enrollment and enrollment.program_id == program_id:
                engine.override_mentor(
                    db, enrollment=enrollment, new_faculty_id=item.mentor_faculty_id,
                    reason=payload.reason, actor=user, enforce_capacity=True,
                )
                changed += 1
        db.commit()
        return BatchMentorAssignResponse(assigned_count=changed,
                                         message=f"Updated {changed} mentor assignments.")

    return BatchMentorAssignResponse(assigned_count=0, message="No changes performed.")


# ── project teams and guide preferences ───────────────────────────────────
def _own_enrollment(db, user, enrollment_id: int) -> InternshipEnrollment:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    student = _assert_is_owner(db, enrollment, user)
    engine.assert_can_register_now(enrollment.program, student.current_semester)
    return enrollment


def _team_and_mine(db, user, team_id: int) -> tuple[ProjectTeam, InternshipEnrollment]:
    team = db.get(ProjectTeam, team_id)
    if team is None:
        raise NotFoundError("Team not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    mine = student and db.scalar(select(InternshipEnrollment).where(
        InternshipEnrollment.program_id == team.program_id,
        InternshipEnrollment.student_id == student.id))
    if not mine:
        raise PermissionDeniedError("Only the team's own students can change it.")
    engine.assert_can_register_now(mine.program, student.current_semester)
    return team, mine


@router.post("/enrollments/{enrollment_id}/team", response_model=EnrollmentDetail)
def create_team(enrollment_id: int, payload: TeamCreate, db: DbSession,
                user: CurrentUser) -> EnrollmentDetail:
    enrollment = _own_enrollment(db, user, enrollment_id)
    project_teams.create_team(db, enrollment, payload.name, actor=user)
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment)


@router.post("/teams/{team_id}/members", response_model=EnrollmentDetail)
def add_team_member(team_id: int, payload: TeamMemberAdd, db: DbSession,
                    user: CurrentUser) -> EnrollmentDetail:
    team, mine = _team_and_mine(db, user, team_id)
    joined = project_teams.add_member(db, team, mine, payload.roll_number, actor=user)
    notifications.notify(
        db, user_id=joined.student.user_id, type=NotificationType.INTERNSHIP_STAGE,
        title=f"Added to the team “{team.name}”",
        message=f"{mine.student.user.full_name} added you to their {mine.program.name} team.",
        link=f"/internships/record/{joined.id}")
    db.commit()
    db.refresh(mine)
    return _detail(db, mine)


@router.delete("/teams/{team_id}/members/{enrollment_id}", response_model=EnrollmentDetail)
def remove_team_member(team_id: int, enrollment_id: int, db: DbSession,
                       user: CurrentUser) -> EnrollmentDetail:
    team, mine = _team_and_mine(db, user, team_id)
    leaving = db.get(InternshipEnrollment, enrollment_id)
    if leaving is None:
        raise NotFoundError("Internship record not found.")
    project_teams.remove_member(db, team, mine, leaving, actor=user)
    db.commit()
    db.refresh(mine)
    return _detail(db, mine)


@router.put("/enrollments/{enrollment_id}/guide-preferences", response_model=EnrollmentDetail)
def set_guide_preferences(enrollment_id: int, payload: GuidePreferences, db: DbSession,
                          user: CurrentUser) -> EnrollmentDetail:
    enrollment = _own_enrollment(db, user, enrollment_id)
    project_teams.set_preferences(db, enrollment, payload.faculty_ids, actor=user)
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment)


@router.get("/programs/{program_id}/guides", response_model=list[dict])
def list_guides(program_id: int, db: DbSession, user: CurrentUser) -> list[dict]:
    """Who may guide this programme's students — for ranking preferences."""
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Programme not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    registered = student and db.scalar(select(InternshipEnrollment.id).where(
        InternshipEnrollment.program_id == program.id,
        InternshipEnrollment.student_id == student.id))
    if not registered and not _can_manage(user, db, program):
        raise PermissionDeniedError("Register for the programme to see its guides.")
    return [{"faculty_id": f.id, "name": f.user.full_name, "designation": f.designation,
             "specialization": f.specialization}
            for f in engine.eligible_mentors(db, program)]


# ── stages and rubric, edited by the coordinator ──────────────────────────
@router.put("/programs/{program_id}/stages", response_model=InternshipProgramOut)
def replace_program_stages(
    program_id: int, payload: StagesReplace, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = _allocation_program(db, user, program_id)
    program_setup.replace_stages(db, program, [s.model_dump() for s in payload.stages], actor=user)
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


@router.put("/programs/{program_id}/criteria", response_model=InternshipProgramOut)
def replace_program_criteria(
    program_id: int, payload: CriteriaReplace, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = _allocation_program(db, user, program_id)
    program_setup.replace_criteria(db, program, [c.model_dump() for c in payload.criteria], actor=user)
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


@router.post("/programs/{program_id}/confirm", response_model=InternshipProgramOut)
def confirm_program_item(
    program_id: int, payload: ConfirmItem, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = _allocation_program(db, user, program_id)
    program_setup.confirm(db, program, payload.item, actor=user)
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


# ── locked mentor allocation ──────────────────────────────────────────────
def _allocation_program(db, user, program_id: int) -> InternshipProgram:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")
    _assert_can_manage_program(db, user, program)
    return program


@router.post("/programs/{program_id}/mentor-allocation/lock", response_model=InternshipProgramOut)
def lock_mentor_allocation(
    program_id: int, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = _allocation_program(db, user, program_id)
    mentor_allocation.lock(db, program, actor=user)
    db.commit()
    return _program_out(db, program)


@router.post("/programs/{program_id}/mentor-allocation/unlock", response_model=InternshipProgramOut)
def unlock_mentor_allocation(
    program_id: int, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipProgramOut:
    program = _allocation_program(db, user, program_id)
    mentor_allocation.unlock(db, program, actor=user)
    db.commit()
    return _program_out(db, program)


@router.post("/programs/{program_id}/mentor-allocation/mentors", response_model=Message)
def add_allocation_mentor(
    program_id: int, payload: AllocationMentorAdd, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> Message:
    program = _allocation_program(db, user, program_id)
    mentor_allocation.add_mentor(db, program, payload.faculty_id, actor=user)
    db.commit()
    return Message(message="Mentor added to the allocation. Move students to them below.")


@router.put("/programs/{program_id}/mentor-allocation/mentors/{faculty_id}", response_model=Message)
def replace_allocation_mentor(
    program_id: int, faculty_id: int, payload: AllocationMentorReplace, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> Message:
    program = _allocation_program(db, user, program_id)
    moved = mentor_allocation.replace_mentor(db, program, faculty_id, payload.new_faculty_id,
                                             actor=user)
    db.commit()
    return Message(message=f"Mentor replaced; {moved} students moved and notified.")


@router.delete("/programs/{program_id}/mentor-allocation/mentors/{faculty_id}", response_model=Message)
def remove_allocation_mentor(
    program_id: int, faculty_id: int, db: DbSession,
    move_to: int | None = None,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> Message:
    program = _allocation_program(db, user, program_id)
    moved = mentor_allocation.remove_mentor(db, program, faculty_id, move_to=move_to, actor=user)
    db.commit()
    return Message(message=(f"Mentor removed; {moved} students moved and notified." if move_to
                            else f"Mentor removed; {moved} students now need a mentor."))


# ── coordinator-run windows ───────────────────────────────────────────────
def _window_out(window: InternshipWindow) -> InternshipWindowOut:
    out = InternshipWindowOut.model_validate(window)
    out.state = window.state_at(program_windows.utcnow())
    return out


@router.get("/programs/{program_id}/windows", response_model=ProgramWindowsOut)
def list_windows(program_id: int, db: DbSession, user: CurrentUser) -> ProgramWindowsOut:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")
    can_manage = _can_manage(user, db, program)
    counts = dict(db.execute(
        select(InternshipEnrollment.mentor_faculty_id.is_(None), func.count())
        .where(InternshipEnrollment.program_id == program.id)
        .group_by(InternshipEnrollment.mentor_faculty_id.is_(None))
    ).all()) if can_manage else {}
    return ProgramWindowsOut(
        kinds=[k.value for k in program_windows.kinds_for(program)],
        windows=[_window_out(w) for w in program_windows.windows(db, program)],
        can_manage=can_manage,
        registered_count=sum(counts.values()),
        unassigned_count=counts.get(True, 0),
    )


@router.post("/programs/{program_id}/windows", response_model=InternshipWindowOut,
             status_code=201)
def open_window(
    program_id: int, payload: InternshipWindowOpen, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipWindowOut:
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")
    _assert_can_manage_program(db, user, program)
    try:
        kind = InternshipWindowKind(payload.kind)
    except ValueError:
        raise ValidationError("Unknown window kind.") from None
    window = program_windows.open_window(
        db, program, kind, title=payload.title, message=payload.message,
        opens_at=payload.opens_at, closes_at=payload.closes_at,
        cohort_semester=payload.cohort_semester,
        submission_due_at=payload.submission_due_at,
        presentation_from=payload.presentation_from,
        presentation_to=payload.presentation_to, actor=user,
    )
    db.commit()
    db.refresh(window)
    return _window_out(window)


def _managed_window(db, user, window_id: int) -> InternshipWindow:
    window = db.get(InternshipWindow, window_id)
    if window is None:
        raise NotFoundError("Window not found.")
    _assert_can_manage_program(db, user, db.get(InternshipProgram, window.program_id))
    return window


@router.patch("/windows/{window_id}", response_model=InternshipWindowOut)
def update_window(
    window_id: int, payload: InternshipWindowUpdate, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipWindowOut:
    window = _managed_window(db, user, window_id)
    program_windows.update_window(db, window, actor=user, **payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(window)
    return _window_out(window)


@router.post("/windows/{window_id}/close", response_model=InternshipWindowOut)
def close_window(
    window_id: int, db: DbSession,
    user: User = Depends(require_permission(P["INTERNSHIP_MANAGE"])),
) -> InternshipWindowOut:
    window = _managed_window(db, user, window_id)
    program_windows.close_window(db, window, actor=user)
    db.commit()
    db.refresh(window)
    return _window_out(window)


@router.get("/programs/{program_id}/mentor-roster", response_model=list[MentorRosterGroup])
def mentor_roster(program_id: int, db: DbSession, user: CurrentUser,
                  faculty=Depends(get_optional_faculty)) -> list[MentorRosterGroup]:
    """The mentor list students are sent when presentations open.

    The coordinator sees it any time; students and mentors of the programme see
    it once the presentation window has been opened — that is when it is
    published to them.
    """
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")
    if not _can_manage(user, db, program):
        if program_windows.get(db, program.id, InternshipWindowKind.PRESENTATION) is None:
            raise PermissionDeniedError("The mentor list has not been published yet.")
        student = db.scalar(select(Student).where(Student.user_id == user.id))
        in_program = (
            (student is not None and db.scalar(select(InternshipEnrollment.id).where(
                InternshipEnrollment.program_id == program.id,
                InternshipEnrollment.student_id == student.id)) is not None)
            or (faculty is not None and db.scalar(select(InternshipEnrollment.id).where(
                InternshipEnrollment.program_id == program.id,
                InternshipEnrollment.mentor_faculty_id == faculty.id).limit(1)) is not None)
        )
        if not in_program:
            raise PermissionDeniedError("Only this programme's students and mentors see its list.")
    return [
        MentorRosterGroup(
            faculty_id=g.faculty_id, name=g.name, designation=g.designation,
            email=g.email, cabin=g.cabin, roll_range=g.roll_range,
            students=[MentorRosterStudent(roll_number=r, name=n) for r, n in g.students],
        )
        for g in program_windows.mentor_roster(db, program)
    ]


# ── organizations ─────────────────────────────────────────────────────────
org_router = APIRouter(prefix="/organizations", tags=["internships"])


@org_router.get("", response_model=list[OrganizationOut])
def list_organizations(db: DbSession, _: CurrentUser, q: str | None = None,
                       type: str | None = None) -> list[OrganizationOut]:
    stmt = select(Organization).order_by(Organization.name)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{q.strip()}%"))
    if type:
        stmt = stmt.where(Organization.type == type)
    return [OrganizationOut.model_validate(o) for o in db.scalars(stmt.limit(200))]


@org_router.post("", response_model=OrganizationOut, status_code=201)
def create_organization(payload: OrganizationCreate, db: DbSession,
                        user: CurrentUser) -> OrganizationOut:
    org = Organization(**payload.model_dump(), added_by_user_id=user.id)
    db.add(org)
    audit.record(db, action=AuditAction.CREATE, entity_type="organization",
                 actor=user, description=f"Added organisation {org.name}")
    db.commit()
    db.refresh(org)
    return OrganizationOut.model_validate(org)


# ── presentation scheduling ───────────────────────────────────────────────
def _certificate_is_verified(db, enrollment: InternshipEnrollment) -> bool:
    """Has the completion certificate been accepted?

    The presentation slot is only allocated once the certificate is verified —
    for CSSI that is the sequence the department follows in Semester III.
    """
    return db.scalar(
        select(InternshipDocument).where(
            InternshipDocument.enrollment_id == enrollment.id,
            InternshipDocument.document_type == DocumentType.CERTIFICATE,
            InternshipDocument.status.in_(list(SATISFYING_STATUSES)),
        ).limit(1)
    ) is not None


@router.post("/enrollments/{enrollment_id}/presentation",
             response_model=EnrollmentDetail)
def schedule_presentation(
    enrollment_id: int, payload: PresentationSchedule, db: DbSession,
    user: CurrentUser, faculty=Depends(get_optional_faculty),
) -> EnrollmentDetail:
    """Allocate this student's presentation slot.

    Coordinator-only, and refused until the certificate is verified — allocating
    a slot to a student who has not completed the internship would put a date in
    front of them that nobody intends to honour.
    """
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    # Coordinator-only, as documented: a mentor could set slots before, which
    # let two mentors book clashing times the coordinator never saw.
    _assert_can_manage_program(db, user, enrollment.program)

    if payload.scheduled_at is not None and not _certificate_is_verified(db, enrollment):
        raise BusinessRuleError(
            "The completion certificate has not been verified yet, so a "
            "presentation slot cannot be allocated."
        )

    enrollment.presentation_at = payload.scheduled_at
    enrollment.presentation_venue = payload.venue
    enrollment.presentation_panel = payload.panel

    student = db.get(Student, enrollment.student_id)
    if student and payload.scheduled_at:
        when = payload.scheduled_at.strftime("%d %b %Y, %H:%M")
        notifications.notify(
            db, user_id=student.user_id, type=NotificationType.INTERNSHIP_STAGE,
            title="Presentation scheduled",
            message=f"{enrollment.program.code}: {when}"
                    + (f" · {payload.venue}" if payload.venue else ""),
            link=f"/internships/record/{enrollment.id}",
        )
    audit.record(
        db, action=AuditAction.UPDATE, entity_type="internship_enrollment",
        entity_id=enrollment.id, actor=user,
        description=("Presentation slot allocated" if payload.scheduled_at
                     else "Presentation slot cleared"),
        meta={"scheduled_at": payload.scheduled_at.isoformat()
                              if payload.scheduled_at else None,
              "venue": payload.venue},
    )
    db.commit()
    db.refresh(enrollment)
    return _detail(db, enrollment)


@router.get("/programs/{program_id}/presentation-queue",
            response_model=list[PresentationQueueRow])
def presentation_queue(
    program_id: int, db: DbSession, user: CurrentUser,
    faculty=Depends(get_optional_faculty),
) -> list[PresentationQueueRow]:
    """Who is ready for a slot, and who already has one.

    Ordered so students still waiting appear first — that is the coordinator's
    actual working list.
    """
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Programme not found.")
    _assert_can_manage_program(db, user, program)

    rows: list[PresentationQueueRow] = []
    for enrollment in db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.program_id == program_id,
    )):
        student = db.get(Student, enrollment.student_id)
        if student is None:
            continue
        ready = _certificate_is_verified(db, enrollment)
        rows.append(PresentationQueueRow(
            enrollment_id=enrollment.id,
            student_name=student.user.full_name if student.user else "—",
            roll_number=student.roll_number,
            division=student.division,
            group_name=enrollment.group.name if enrollment.group else None,
            certificate_verified=ready,
            presentation_at=enrollment.presentation_at,
            presentation_venue=enrollment.presentation_venue,
            presentation_panel=enrollment.presentation_panel,
        ))
    # Ready-but-unscheduled first; then scheduled by date; then not yet ready.
    rows.sort(key=lambda r: (
        0 if (r.certificate_verified and r.presentation_at is None)
        else 1 if r.presentation_at is not None else 2,
        r.presentation_at.timestamp() if r.presentation_at else 0,
        r.roll_number,
    ))
    return rows
