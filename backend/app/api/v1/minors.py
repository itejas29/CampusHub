from __future__ import annotations

import dataclasses
import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import CurrentStudent, CurrentUser, DbSession, require_permission
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.rbac import P, has_permission
from app.models.enums import (
    AuditAction, CoordinationDomain, MinorApplicationStatus, MinorEnrollmentStatus,
    NotificationType,
)
from app.models.identity import Faculty, Student, User
from app.models.minors import (
    MinorApplication, MinorCourse, MinorEnrollment, MinorProgram,
)
from app.schemas.common import Message
from app.schemas.minors import (
    MinorAllocationPreview, MinorAllocationResult, MinorApplicationOut,
    MinorApplyRequest, MinorCourseOut, MinorDecisionRequest, MinorEnrollmentOut,
    MinorProgramCreate, MinorProgramOut, MinorProgramUpdate, RankedApplicantOut,
    RankingCriterion, RankingPolicyUpdate, MinorWorkspace,
)
from app.services import audit, minors as minor_service, notifications, scope
from app.services.eligibility import check_minor_eligibility

router = APIRouter(prefix="/minors", tags=["minors"])


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _course_out(mc: MinorCourse, completed_ids: set[int] | None = None) -> MinorCourseOut:
    return MinorCourseOut(
        id=mc.id, course_id=mc.course_id,
        course_code=mc.course.code if mc.course else None,
        course_title=mc.course.title if mc.course else None,
        credits=float(mc.course.credits) if mc.course else None,
        sequence=mc.sequence, semester_offset=mc.semester_offset,
        is_mandatory=mc.is_mandatory,
        is_completed=bool(completed_ids and mc.course_id in completed_ids),
    )


def _program_out(db, program: MinorProgram, student: Student | None = None,
                 my_status: MinorApplicationStatus | None = None) -> MinorProgramOut:
    coordinator = (
        db.get(Faculty, program.coordinator_faculty_id)
        if program.coordinator_faculty_id else None
    )
    eligible = notes = None
    if student:
        result = check_minor_eligibility(student, program)
        eligible, notes = result.eligible, result.reasons
    # `pro_rata` is deliberately not surfaced: it is recorded as
    # REQUIRES_FACULTY_CONFIRMATION and unconfirmed policy must not be shown to
    # students as though it were settled.
    rules = program.rules or {}
    return MinorProgramOut(
        id=program.id, code=program.code, name=program.name,
        description=program.description, department_id=program.department_id,
        department_name=program.department.name if program.department else None,
        total_credits=float(program.total_credits), capacity=program.capacity,
        seats_filled=program.seats_filled, seats_available=program.seats_available,
        eligible_from_semester=program.eligible_from_semester,
        min_cpi=float(program.min_cpi) if program.min_cpi is not None else None,
        max_backlogs=program.max_backlogs,
        allocation_strategy=program.allocation_strategy,
        application_opens_at=program.application_opens_at,
        application_closes_at=program.application_closes_at,
        coordinator_name=coordinator.user.full_name if coordinator else None,
        is_active=program.is_active,
        courses=[_course_out(c) for c in program.courses],
        continuation_rule=rules.get("continuation_rule"),
        rule_source=rules.get("source"),
        rule_source_url=rules.get("source_url"),
        offered_semesters=[int(s) for s in rules.get("offered_semesters") or []],
        window_open=minor_service.application_window_open(program),
        is_eligible=eligible, eligibility_notes=notes or [],
        my_application_status=my_status,
    )


def _application_out(db, app: MinorApplication) -> MinorApplicationOut:
    student = db.get(Student, app.student_id)
    program = app.minor_program
    return MinorApplicationOut(
        id=app.id, student_id=app.student_id,
        student_name=student.user.full_name if student else None,
        roll_number=student.roll_number if student else None,
        minor_program_id=app.minor_program_id,
        minor_name=program.name if program else None,
        minor_department=program.department.name if program and program.department else None,
        preference_order=app.preference_order, status=app.status,
        cpi_at_application=(float(app.cpi_at_application)
                            if app.cpi_at_application is not None else None),
        backlogs_at_application=app.backlogs_at_application,
        semester_at_application=app.semester_at_application,
        motivation=app.motivation,
        allocation_score=(float(app.allocation_score)
                          if app.allocation_score is not None else None),
        submitted_at=app.submitted_at, decided_at=app.decided_at, remarks=app.remarks,
    )


def _enrollment_out(enrollment: MinorEnrollment) -> MinorEnrollmentOut:
    program = enrollment.minor_program
    total = float(program.total_credits) if program else 0
    done = float(enrollment.credits_completed)
    completed_ids = set(enrollment.completed_course_ids or [])
    return MinorEnrollmentOut(
        id=enrollment.id, minor_program_id=enrollment.minor_program_id,
        minor_name=program.name if program else None,
        minor_department=program.department.name if program and program.department else None,
        status=enrollment.status, started_semester=enrollment.started_semester,
        credits_completed=done, total_credits=total,
        progress_percent=round(done * 100 / total) if total else 0,
        courses=[_course_out(c, completed_ids) for c in (program.courses if program else [])],
    )


# ── student ───────────────────────────────────────────────────────────────
@router.get("/workspace", response_model=MinorWorkspace)
def workspace(db: DbSession, student: CurrentStudent) -> MinorWorkspace:
    all_programs = list(db.scalars(
        select(MinorProgram).where(MinorProgram.is_active.is_(True))
        .order_by(MinorProgram.name)
    ))
    programs = all_programs
    my_apps = list(db.scalars(
        select(MinorApplication).where(MinorApplication.student_id == student.id)
        .order_by(MinorApplication.preference_order)
    ))
    status_by_program = {a.minor_program_id: a.status for a in my_apps}
    enrollment = db.scalar(
        select(MinorEnrollment).where(MinorEnrollment.student_id == student.id)
    )

    # A minor a student has applied to, or holds a seat in, stays theirs to see
    # for good; everything else is gated on semester and the registration round.
    engaged_ids = {a.minor_program_id for a in my_apps}
    if enrollment:
        engaged_ids.add(enrollment.minor_program_id)
    programs = [
        p for p in programs
        if minor_service.student_can_see_minor(
            p, student, has_application=p.id in engaged_ids)
    ]

    # Overall eligibility: is the student past the earliest allowed semester?
    earliest = min((p.eligible_from_semester for p in all_programs), default=3)
    overall_notes: list[str] = []
    if student.current_semester < earliest:
        overall_notes.append(
            f"Minor registration opens from semester {earliest}. "
            f"You are currently in semester {student.current_semester}."
        )
    elif not programs:
        overall_notes.append(
            "Minor registration is not open at the moment. Programmes appear "
            "here while a registration round is running; if you hold a minor "
            "seat it stays listed."
        )
    return MinorWorkspace(
        is_eligible=not overall_notes,
        eligibility_notes=overall_notes,
        programs=[_program_out(db, p, student, status_by_program.get(p.id))
                  for p in programs],
        applications=[_application_out(db, a) for a in my_apps],
        enrollment=_enrollment_out(enrollment) if enrollment else None,
    )


@router.post("/apply", response_model=list[MinorApplicationOut], status_code=201)
def apply(payload: MinorApplyRequest, db: DbSession, student: CurrentStudent,
          user: CurrentUser) -> list[MinorApplicationOut]:
    if db.scalar(select(MinorEnrollment).where(
        MinorEnrollment.student_id == student.id,
        MinorEnrollment.status == MinorEnrollmentStatus.ACTIVE,
    )):
        raise BusinessRuleError("You are already enrolled in a minor programme.")
    if len(set(payload.preferences)) != len(payload.preferences):
        raise BusinessRuleError("The same minor cannot be listed twice.")

    programs = []
    for program_id in payload.preferences:
        program = db.get(MinorProgram, program_id)
        if program is None:
            raise NotFoundError(f"Minor programme {program_id} does not exist.")
        result = check_minor_eligibility(student, program)
        if not result.eligible:
            raise BusinessRuleError(f"{program.name}: {result.reasons[0]}")
        programs.append(program)

    # A withdrawn application is replaced too: left in place it collided with
    # the new one on (student, minor, year) and re-applying failed with a
    # database error. A decided one (allocated, waitlisted, rejected) stays,
    # and applying to that minor again is refused with the reason.
    decided = {a.minor_program_id: a for a in db.scalars(select(MinorApplication).where(
        MinorApplication.student_id == student.id,
        MinorApplication.status.not_in([MinorApplicationStatus.SUBMITTED,
                                        MinorApplicationStatus.DRAFT,
                                        MinorApplicationStatus.WITHDRAWN]),
    ))}
    for program in programs:
        earlier = decided.get(program.id)
        if earlier is not None and earlier.academic_year_id == program.academic_year_id:
            raise BusinessRuleError(
                f"{program.name}: your application this year was already "
                f"{earlier.status.value.lower()}.")
    for old in db.scalars(select(MinorApplication).where(
        MinorApplication.student_id == student.id,
        MinorApplication.status.in_(
            [MinorApplicationStatus.SUBMITTED, MinorApplicationStatus.DRAFT,
             MinorApplicationStatus.WITHDRAWN]
        ),
    )):
        db.delete(old)
    db.flush()

    now = utcnow()
    created = []
    for order, program in enumerate(programs, start=1):
        application = MinorApplication(
            student_id=student.id, minor_program_id=program.id,
            academic_year_id=program.academic_year_id, preference_order=order,
            status=MinorApplicationStatus.SUBMITTED,
            cpi_at_application=student.cpi,
            backlogs_at_application=student.backlog_count,
            semester_at_application=student.current_semester,
            motivation=payload.motivation, submitted_at=now,
        )
        db.add(application)
        created.append(application)

    notifications.notify(
        db, user_id=user.id, type=NotificationType.MINOR_APPLICATION,
        title="Minor application submitted",
        message=f"{len(created)} preference(s) recorded. Allocation results will be "
                "published by the department.",
        link="/academics/minors",
    )
    audit.record(db, action=AuditAction.CREATE, entity_type="minor_application",
                 entity_id=student.id, actor=user,
                 description=f"Applied to {len(created)} minor programme(s)",
                 meta={"program_ids": payload.preferences})
    db.commit()
    for application in created:
        db.refresh(application)
    return [_application_out(db, a) for a in created]


@router.delete("/applications", response_model=Message)
def withdraw(db: DbSession, student: CurrentStudent, user: CurrentUser) -> Message:
    rows = list(db.scalars(select(MinorApplication).where(
        MinorApplication.student_id == student.id,
        MinorApplication.status == MinorApplicationStatus.SUBMITTED,
    )))
    if not rows:
        raise BusinessRuleError("There is no pending application to withdraw.")
    for row in rows:
        row.status = MinorApplicationStatus.WITHDRAWN
    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_application",
                 entity_id=student.id, actor=user, description="Withdrew minor application")
    db.commit()
    return Message(message="Your minor application has been withdrawn.")


# ── admin ─────────────────────────────────────────────────────────────────
@router.get("", response_model=list[MinorProgramOut])
def list_programs(db: DbSession, _: CurrentUser,
                  department_id: int | None = None) -> list[MinorProgramOut]:
    stmt = select(MinorProgram).order_by(MinorProgram.name)
    if department_id:
        stmt = stmt.where(MinorProgram.department_id == department_id)
    return [_program_out(db, p) for p in db.scalars(stmt)]


@router.post("", response_model=MinorProgramOut, status_code=201)
def create_program(
    payload: MinorProgramCreate, db: DbSession,
    user: User = Depends(require_permission(P["MINOR_MANAGE"])),
) -> MinorProgramOut:
    program = MinorProgram(**payload.model_dump())
    db.add(program)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="minor_program",
                 entity_id=program.id, actor=user,
                 description=f"Created minor {program.code}")
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


@router.patch("/{program_id}", response_model=MinorProgramOut)
def update_program(
    program_id: int, payload: MinorProgramUpdate, db: DbSession,
    user: User = Depends(require_permission(P["MINOR_MANAGE"])),
) -> MinorProgramOut:
    program = db.get(MinorProgram, program_id)
    if program is None:
        raise NotFoundError("Minor programme not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(program, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_program",
                 entity_id=program.id, actor=user, description="Updated minor programme")
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


@router.get("/applications", response_model=list[MinorApplicationOut])
def list_applications(
    db: DbSession, user: CurrentUser, program_id: int | None = Query(None),
    status: MinorApplicationStatus | None = Query(None),
) -> list[MinorApplicationOut]:
    if not has_permission(user.roles, P["MINOR_MANAGE"]) and not any(
        c.domain == CoordinationDomain.MINOR for c in scope.coordinations_for(db, user)
    ):
        raise PermissionDeniedError("You do not coordinate minor specialisations.")
    stmt = select(MinorApplication).order_by(
        MinorApplication.preference_order, MinorApplication.submitted_at
    )
    if program_id:
        stmt = stmt.where(MinorApplication.minor_program_id == program_id)
    if status:
        stmt = stmt.where(MinorApplication.status == status)
    # Each application is shown only to someone who may act on it. The list
    # used to answer any minor coordinator with every department's applicants —
    # and their CPI.
    rows = [a for a in db.scalars(stmt)
            if user.has_role(*scope.UNSCOPED_ROLES)
            or scope.can_manage_minor(db, user, a.minor_program,
                                      scope.student_department_id(db, a.student_id))]
    return [_application_out(db, a) for a in rows]


@router.post("/applications/{application_id}/decide", response_model=MinorApplicationOut)
def decide(
    application_id: int, payload: MinorDecisionRequest, db: DbSession,
    user: CurrentUser,
) -> MinorApplicationOut:
    """Record a decision. The *ranking* rule is deliberately not automated —
    see services/allocation for where a faculty-supplied formula will plug in."""
    application = db.get(MinorApplication, application_id)
    if application is None:
        raise NotFoundError("Application not found.")

    program = application.minor_program
    # This action concerns one applicant, so both readings can be evaluated:
    # the department offering the minor, and the department the student is in.
    scope.assert_manages_minor(
        db, user, program,
        scope.student_department_id(db, application.student_id),
    )
    if payload.status == MinorApplicationStatus.ALLOCATED:
        if program.seats_available <= 0:
            raise BusinessRuleError("No seats remain in this minor programme.")
        existing = db.scalar(select(MinorEnrollment).where(
            MinorEnrollment.student_id == application.student_id,
            MinorEnrollment.status == MinorEnrollmentStatus.ACTIVE,
        ))
        if existing:
            raise BusinessRuleError("This student is already enrolled in a minor.")

        db.add(MinorEnrollment(
            student_id=application.student_id, minor_program_id=program.id,
            application_id=application.id, status=MinorEnrollmentStatus.ACTIVE,
            started_semester=application.semester_at_application,
        ))
        program.seats_filled += 1
        # Competing preferences from the same student are closed out.
        for sibling in db.scalars(select(MinorApplication).where(
            MinorApplication.student_id == application.student_id,
            MinorApplication.id != application.id,
            MinorApplication.status == MinorApplicationStatus.SUBMITTED,
        )):
            sibling.status = MinorApplicationStatus.REJECTED
            sibling.decided_at = utcnow()
            sibling.remarks = "Closed — another preference was allocated."

    application.status = payload.status
    application.remarks = payload.remarks
    application.reviewed_by_user_id = user.id
    application.decided_at = utcnow()

    student = db.get(Student, application.student_id)
    if student:
        notifications.notify(
            db, user_id=student.user_id, type=NotificationType.MINOR_APPLICATION,
            title=f"Minor application {payload.status.value.lower()}",
            message=f"{program.name}: {payload.remarks or payload.status.value.title()}",
            link="/academics/minors",
        )
    audit.record(
        db, action=AuditAction.ALLOCATION_OVERRIDE, entity_type="minor_application",
        entity_id=application.id, actor=user,
        description=f"Minor application marked {payload.status.value}",
        meta={"program": program.code, "remarks": payload.remarks},
    )
    db.commit()
    db.refresh(application)
    return _application_out(db, application)


# ── allocation rounds ─────────────────────────────────────────────────────
def _ranked_out(entry: minor_service.RankedApplicant) -> RankedApplicantOut:
    return RankedApplicantOut(**dataclasses.asdict(entry))


def _criteria_out(program: MinorProgram) -> list[RankingCriterion]:
    return [
        RankingCriterion(
            field=c["field"], direction=c["direction"],
            label=minor_service.RANKABLE_FIELDS[c["field"]],
        )
        for c in minor_service.ranking_policy(program)
    ]


def _assert_manages(db, user: User, program: MinorProgram,
                    applicant_department_id: int | None = None) -> None:
    """Programme-wide actions: seats, ranking policy, allocation rounds.

    Which department scope counts is a configured policy, not an assumption —
    see `services/scope.MinorScopeRule`.
    """
    scope.assert_manages_minor(db, user, program, applicant_department_id)


@router.get("/ranking-fields", response_model=dict)
def ranking_fields(_: CurrentUser) -> dict:
    """The fields a minor may rank on. The institute picks which to use."""
    return {
        "fields": [
            {"field": field, "label": label,
             "default_direction": minor_service.DEFAULT_DIRECTIONS[field]}
            for field, label in minor_service.RANKABLE_FIELDS.items()
        ],
    }


@router.put("/{program_id}/ranking-policy", response_model=MinorProgramOut)
def set_ranking_policy(
    program_id: int, payload: RankingPolicyUpdate, db: DbSession, user: CurrentUser,
) -> MinorProgramOut:
    """Declare how this minor ranks applicants.

    CampusHub ships no default formula — the coordinator states the policy, and
    it is recorded in the audit trail so a published round can be explained.
    """
    program = db.get(MinorProgram, program_id)
    if program is None:
        raise NotFoundError("Minor programme not found.")
    _assert_manages(db, user, program)

    criteria = [{"field": c.field, "direction": c.direction} for c in payload.criteria]
    rules = dict(program.rules or {})
    rules["ranking"] = {"criteria": criteria}
    program.rules = rules
    minor_service.ranking_policy(program)          # validate before persisting

    audit.record(db, action=AuditAction.UPDATE, entity_type="minor_program",
                 entity_id=program.id, actor=user,
                 description=f"Ranking policy set for {program.code}",
                 meta={"criteria": criteria})
    db.commit()
    db.refresh(program)
    return _program_out(db, program)


@router.get("/{program_id}/allocation/preview", response_model=MinorAllocationPreview)
def preview_allocation(
    program_id: int, db: DbSession, user: CurrentUser,
) -> MinorAllocationPreview:
    """Dry run — nothing is written. Lets a coordinator see the cut-off first."""
    program = db.get(MinorProgram, program_id)
    if program is None:
        raise NotFoundError("Minor programme not found.")
    _assert_manages(db, user, program)

    ranked = minor_service.rank(db, program)
    return MinorAllocationPreview(
        program_id=program.id, program_name=program.name,
        capacity=program.capacity, seats_filled=program.seats_filled,
        seats_available=program.seats_available,
        applicants=len(ranked),
        would_allocate=sum(1 for r in ranked if r.within_capacity),
        criteria=_criteria_out(program),
        ranking=[_ranked_out(r) for r in ranked],
    )


@router.post("/{program_id}/allocation/run", response_model=MinorAllocationResult)
def run_allocation(
    program_id: int, db: DbSession, user: CurrentUser,
) -> MinorAllocationResult:
    """Commit the round: seats granted in rank order, the rest waitlisted."""
    program = db.get(MinorProgram, program_id)
    if program is None:
        raise NotFoundError("Minor programme not found.")
    _assert_manages(db, user, program)

    ranked, granted = minor_service.allocate(db, program)
    for entry in ranked:
        student = db.get(Student, entry.student_id)
        if student is None:
            continue
        allocated = entry.within_capacity
        notifications.notify(
            db, user_id=student.user_id, type=NotificationType.MINOR_APPLICATION,
            title="Minor allocated" if allocated else "Minor waitlisted",
            message=(
                f"You have a seat in {program.name}."
                if allocated
                else f"{program.name}: waitlisted at rank {entry.rank} of "
                     f"{len(ranked)} for {program.capacity} seats."
            ),
            link="/academics/minors",
        )
    audit.record(
        db, action=AuditAction.ALLOCATION_RUN, entity_type="minor_program",
        entity_id=program.id, actor=user,
        description=f"Minor allocation round for {program.code}: {granted} allocated",
        meta={"applicants": len(ranked), "allocated": granted,
              "criteria": minor_service.ranking_policy(program)},
    )
    db.commit()
    db.refresh(program)
    return MinorAllocationResult(
        program_id=program.id, allocated=granted,
        waitlisted=len(ranked) - granted, seats_filled=program.seats_filled,
        ranking=[_ranked_out(r) for r in ranked],
    )
