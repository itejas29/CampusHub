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
    BusinessRuleError, NotFoundError, PermissionDeniedError, ValidationError,
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
    EnrollmentStageProgress, EvaluationCriteria, EvaluationScore, InternshipDocument,
    InternshipEnrollment, InternshipEvaluation, InternshipGroup, InternshipProgram,
    InternshipProject, InternshipReport, InternshipStage, Organization,
)
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
)
from app.services import (
    audit, documents as docs, internships as engine, notifications, scope,
)
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
    if faculty and (enrollment.mentor_faculty_id == faculty.id
                    or (enrollment.group and enrollment.group.faculty_id == faculty.id)):
        return
    raise PermissionDeniedError("Only the assigned mentor or a coordinator may review this.")


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
        elif phase is not ProgramPhase.ACTIVE:
            # Announced but not yet open, or already past — see program_phase().
            can_enroll = False
            blocked = engine.phase_note(program, phase, student.current_semester)
        elif program.status != ProgramStatus.REGISTRATION_OPEN:
            can_enroll, blocked = False, "Registration is not open for this programme."
        else:
            can_enroll = True

    return InternshipProgramOut(
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
    return [_program_out(db, p, student) for p in programs]


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
    for e in enrollments:
        student = e.student
        student_user = student.user if student else None
        dept = student.department.name if student and student.department else ""
        mentor = (
            e.mentor_faculty.user.full_name
            if e.mentor_faculty and e.mentor_faculty.user
            else ""
        )
        org = e.organization.name if e.organization else ""
        stage = e.current_stage.title if e.current_stage else ""
        writer.writerow([
            student.roll_number if student else "",
            student_user.full_name if student_user else "",
            student.division if student else "",
            dept,
            org,
            e.industry_mentor_name or "",
            mentor,
            stage,
            e.progress_percent,
            e.evaluation_status.value if e.evaluation_status else "",
            float(e.final_marks) if e.final_marks is not None else "",
            e.final_grade or "",
            e.status.value,
        ])

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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(program, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_program",
                 entity_id=program.id, actor=user, description="Updated programme settings")
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
    if program.status != ProgramStatus.REGISTRATION_OPEN:
        raise BusinessRuleError("Registration is not open for this programme.")
    engine.assert_submissions_open(program, student.current_semester)

    enrollment = engine.enroll_student(db, program=program, student=student, actor=user)

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
        _assert_can_submit(db, enrollment, user)
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
    title: str | None = Form(None),
    stage_id: int | None = Form(None),
    week_number: int | None = Form(None),
) -> DocumentOut:
    enrollment = db.get(InternshipEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Internship record not found.")
    _assert_can_submit(db, enrollment, user)

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
    if not _can_manage(user, db, enrollment.program):
        _assert_can_submit(db, enrollment, user)
    if doc.status == SubmissionStatus.APPROVED:
        raise BusinessRuleError("An approved document cannot be removed.")
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

    existing = db.scalar(select(InternshipReport).where(
        InternshipReport.enrollment_id == enrollment.id,
        InternshipReport.report_type == payload.report_type,
        InternshipReport.sequence_number == payload.sequence_number,
    ))
    if existing and existing.status == SubmissionStatus.APPROVED:
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
    if payload.group_id is not None:
        group = db.get(InternshipGroup, payload.group_id)
        if group is None or group.program_id != enrollment.program_id:
            raise ValidationError("That group belongs to a different programme.")
        enrollment.group_id = group.id
    engine.override_mentor(db, enrollment=enrollment,
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
    program = db.get(InternshipProgram, program_id)
    if program is None:
        raise NotFoundError("Program not found.")

    # All faculty, sorted by name
    faculties = list(db.scalars(
        select(Faculty).join(Faculty.user).order_by(User.full_name)
    ))

    # Calculate assigned counts for this program
    assigned_counts = dict(
        db.execute(
            select(
                InternshipEnrollment.mentor_faculty_id,
                func.count(InternshipEnrollment.id)
            )
            .where(
                InternshipEnrollment.program_id == program_id,
                InternshipEnrollment.mentor_faculty_id.is_not(None)
            )
            .group_by(InternshipEnrollment.mentor_faculty_id)
        ).all()
    )

    out = []
    for f in faculties:
        count = assigned_counts.get(f.id, 0)
        out.append(MentorCapacityOut(
            faculty_id=f.id,
            name=f.user.full_name,
            employee_code=f.employee_code,
            department_code=f.department.code if f.department else None,
            designation=f.designation,
            avatar_url=f.user.avatar_url,
            assigned_count=count,
            max_capacity=10,
            remaining_capacity=max(0, 10 - count),
            is_full=count >= 10,
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

    MAX_CAPACITY = 10
    MIN_CAPACITY = 2
    total_assigned = 0

    if payload.clear_all:
        enrollments = list(db.scalars(
            select(InternshipEnrollment)
            .where(InternshipEnrollment.program_id == program_id)
        ))
        cleared_count = 0
        for enrollment in enrollments:
            if enrollment.mentor_faculty_id is not None:
                engine.override_mentor(
                    db, enrollment=enrollment, new_faculty_id=None,
                    reason=payload.reason or "Coordinator cleared all mentor assignments",
                    actor=user, enforce_capacity=False
                )
                cleared_count += 1
        db.commit()
        return BatchMentorAssignResponse(
            assigned_count=0,
            message=f"Cleared mentor assignments for all {cleared_count} students successfully. Mentors are now unassigned."
        )

    elif payload.allocate_by_roll_no:
        # Roll number wise sequential allocation to selected mentors
        enrollments = list(db.scalars(
            select(InternshipEnrollment)
            .join(Student, InternshipEnrollment.student_id == Student.id)
            .where(InternshipEnrollment.program_id == program_id)
            .order_by(Student.roll_number.asc())
        ))

        if not enrollments:
            return BatchMentorAssignResponse(assigned_count=0, message="No students enrolled in this programme.")

        # Determine target faculty list
        if payload.faculty_ids and len(payload.faculty_ids) > 0:
            faculties = list(db.scalars(
                select(Faculty).join(Faculty.user)
                .where(Faculty.id.in_(payload.faculty_ids))
                .order_by(User.full_name)
            ))
        else:
            faculties = list(db.scalars(
                select(Faculty).join(Faculty.user)
                .order_by(Faculty.department_id, User.full_name)
            ))

        if not faculties:
            raise ValidationError("Please select at least one faculty mentor.")

        total_students = len(enrollments)
        needed_mentors = min(len(faculties), (total_students + 9) // MAX_CAPACITY)

        # Compute chunk sizes: each between 2 and 10 students
        chunk_sizes = []
        rem = total_students
        for i in range(needed_mentors):
            if i == needed_mentors - 1:
                chunk_sizes.append(rem)
            elif rem - MAX_CAPACITY >= MIN_CAPACITY:
                chunk_sizes.append(MAX_CAPACITY)
                rem -= MAX_CAPACITY
            elif rem >= 4:
                take = rem // 2
                chunk_sizes.append(take)
                rem -= take
            else:
                chunk_sizes.append(rem)
                rem = 0
                break

        curr_idx = 0
        allocated_mentors_info = []

        for m_idx, count in enumerate(chunk_sizes):
            faculty = faculties[m_idx]
            batch = enrollments[curr_idx : curr_idx + count]
            curr_idx += count

            for enrollment in batch:
                engine.override_mentor(
                    db, enrollment=enrollment, new_faculty_id=faculty.id,
                    reason=f"Roll number allocation: {faculty.user.full_name}",
                    actor=user, enforce_capacity=False
                )
                total_assigned += 1

            first_roll = batch[0].student.roll_number if batch else ""
            last_roll = batch[-1].student.roll_number if batch else ""
            allocated_mentors_info.append(f"{faculty.user.full_name} ({count} students: {first_roll} - {last_roll})")

        # Any remaining students beyond selected mentors capacity become unassigned
        while curr_idx < len(enrollments):
            engine.override_mentor(
                db, enrollment=enrollments[curr_idx], new_faculty_id=None,
                reason="Unassigned: selected mentors reached capacity",
                actor=user, enforce_capacity=False
            )
            curr_idx += 1

        db.commit()
        unassigned_left = len(enrollments) - total_assigned
        return BatchMentorAssignResponse(
            assigned_count=total_assigned,
            message=f"Allocated {total_assigned} students roll-number-wise across {len(chunk_sizes)} mentors ({MIN_CAPACITY} to {MAX_CAPACITY} students per mentor). {unassigned_left} unassigned."
        )

    elif payload.rebalance:
        # Full rebalancing: strictly enforce 10 students max per mentor
        all_enrollments = list(db.scalars(
            select(InternshipEnrollment)
            .where(InternshipEnrollment.program_id == program_id)
            .order_by(InternshipEnrollment.id)
        ))

        faculties = list(db.scalars(
            select(Faculty).join(Faculty.user).order_by(Faculty.department_id, User.full_name)
        ))

        mentor_idx = 0
        mentor_student_counts = {f.id: 0 for f in faculties}

        for enrollment in all_enrollments:
            # Find next faculty with space (< 10)
            while mentor_idx < len(faculties) and mentor_student_counts[faculties[mentor_idx].id] >= MAX_CAPACITY:
                mentor_idx += 1

            if mentor_idx < len(faculties):
                chosen_f = faculties[mentor_idx]
                engine.override_mentor(
                    db, enrollment=enrollment, new_faculty_id=chosen_f.id,
                    reason="Coordinated rebalance: strictly enforced max 10 students per mentor",
                    actor=user, enforce_capacity=False
                )
                mentor_student_counts[chosen_f.id] += 1
                total_assigned += 1
            else:
                # All mentors are full at 10/10! Leave remaining unassigned
                engine.override_mentor(
                    db, enrollment=enrollment, new_faculty_id=None,
                    reason="Unassigned: all faculty mentors reached maximum 10-student capacity",
                    actor=user, enforce_capacity=False
                )

        db.commit()
        unassigned_count = len(all_enrollments) - total_assigned
        return BatchMentorAssignResponse(
            assigned_count=total_assigned,
            message=f"Rebalanced {total_assigned} students across {len(faculties)} faculty mentors (max {MAX_CAPACITY} per mentor). {unassigned_count} students remaining unassigned."
        )

    elif payload.auto_distribute:
        # Fetch unassigned enrollments
        unassigned_enrollments = list(db.scalars(
            select(InternshipEnrollment)
            .where(
                InternshipEnrollment.program_id == program_id,
                InternshipEnrollment.mentor_faculty_id.is_(None)
            )
            .order_by(InternshipEnrollment.id)
        ))

        # Eligible faculty
        f_query = select(Faculty)
        if payload.faculty_ids:
            f_query = f_query.where(Faculty.id.in_(payload.faculty_ids))
        faculties = list(db.scalars(f_query))

        # Current counts
        current_counts = dict(
            db.execute(
                select(
                    InternshipEnrollment.mentor_faculty_id,
                    func.count(InternshipEnrollment.id)
                )
                .where(
                    InternshipEnrollment.program_id == program_id,
                    InternshipEnrollment.mentor_faculty_id.is_not(None)
                )
                .group_by(InternshipEnrollment.mentor_faculty_id)
            ).all()
        )

        for enrollment in unassigned_enrollments:
            # Find faculty with available capacity (< 10) and lowest load
            available_faculty = [
                f for f in faculties
                if current_counts.get(f.id, 0) < MAX_CAPACITY
            ]
            if not available_faculty:
                break
            available_faculty.sort(key=lambda f: current_counts.get(f.id, 0))
            chosen = available_faculty[0]

            engine.override_mentor(
                db, enrollment=enrollment, new_faculty_id=chosen.id,
                reason=payload.reason, actor=user, enforce_capacity=False
            )
            current_counts[chosen.id] = current_counts.get(chosen.id, 0) + 1
            total_assigned += 1

        db.commit()
        return BatchMentorAssignResponse(
            assigned_count=total_assigned,
            message=f"Allocated {total_assigned} students across {len(faculties)} faculty mentors (max {MAX_CAPACITY} students per mentor)."
        )

    elif payload.assignments:
        for item in payload.assignments:
            enrollment = db.get(InternshipEnrollment, item.enrollment_id)
            if enrollment and enrollment.program_id == program_id:
                engine.override_mentor(
                    db, enrollment=enrollment, new_faculty_id=item.mentor_faculty_id,
                    reason=payload.reason, actor=user, enforce_capacity=True
                )
                total_assigned += 1
        db.commit()
        return BatchMentorAssignResponse(
            assigned_count=total_assigned,
            message=f"Updated {total_assigned} mentor assignments."
        )

    return BatchMentorAssignResponse(assigned_count=0, message="No changes performed.")


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
    _assert_can_review(db, enrollment, user, faculty)

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
    scope.assert_coordinates(
        db, user, scope.domain_for_program(program), program.department_id,
        permission=P["INTERNSHIP_MANAGE"], what=program.name,
    )

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
