"""NPTEL / SWAYAM. Visibility is driven by the curriculum, not by role alone."""
from __future__ import annotations

import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.core.deps import CurrentStudent, CurrentUser, DbSession, require_permission
from app.core.errors import (
    BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError, ValidationError,
)
from app.core.rbac import P, has_permission
from app.models.academics import (
    Course, CourseOffering, Curriculum, CurriculumComponent, MoocRegistration, MoocRound,
    MoocRoundCourse, Program,
)
from app.models.enums import (
    AuditAction, ComponentType, CoordinationDomain, FileCategory, MoocOption,
    MoocOutcome, MoocRoundStatus, MoocStatus, NotificationType, Role, VerificationStatus,
)
from app.models.identity import Student, User
from app.schemas.academics import (
    CourseOfferingOut, MoocRegisterRequest, MoocRegistrationOut, MoocUpdateRequest,
    MoocVerifyRequest,
)
from app.schemas.common import Message
from app.schemas.fields import csv_safe
from app.schemas.mooc import (
    MoocChoiceIn, MoocChoiceOut, MoocCloseRequest, MoocCloseResult, MoocCourseIn,
    MoocCourseOut, MoocImportResult, MoocRemindResult, MoocRosterRow, MoocRoundIn,
    MoocRoundOut, MoocRoundUpdate, StudentMoocRoundOut, StudentMoocStanding,
)
from app.services import audit, mooc_rounds, notifications, scope
from app.services.eligibility import (
    components_for_semester, offering_window_open, student_can_access_component,
)
from app.services.files import save_upload
from app.services.serializers import file_url, offering_out

router = APIRouter(prefix="/mooc", tags=["mooc"])


def _reg_course(reg: MoocRegistration) -> Course | None:
    if reg.course is not None:
        return reg.course
    return reg.course_offering.course if reg.course_offering else None


def _out(db, reg: MoocRegistration) -> MoocRegistrationOut:
    course = _reg_course(reg)
    student = db.get(Student, reg.student_id)
    ncc = reg.option == MoocOption.NCC
    return MoocRegistrationOut(
        id=reg.id, student_id=reg.student_id,
        student_name=student.user.full_name if student else None,
        roll_number=student.roll_number if student else None,
        course_offering_id=reg.course_offering_id,
        course_code=("NCC" if ncc else course.code if course else None),
        course_title=("NCC certification" if ncc else course.title if course else None),
        option=reg.option, mooc_round_id=reg.mooc_round_id,
        platform=reg.platform,
        platform_registration_id=reg.platform_registration_id,
        course_url=reg.course_url or (course.provider_url if course else None),
        status=reg.status, exam_date=reg.exam_date, exam_city=reg.exam_city,
        exam_fee_paid=reg.exam_fee_paid, exam_fee_reference=reg.exam_fee_reference,
        certificate_url=file_url(db, reg.certificate_file_id),
        verification_status=reg.verification_status, verified_at=reg.verified_at,
        final_score=float(reg.final_score) if reg.final_score is not None else None,
        grade=reg.grade, remarks=reg.remarks,
    )


def _mooc_component(db, student: Student) -> CurriculumComponent | None:
    return mooc_rounds.mooc_component(db, student)


@router.get("/eligibility")
def my_eligibility(db: DbSession, student: CurrentStudent) -> dict:
    """Whether MOOC/NPTEL applies to this student *at all*, per their curriculum."""
    component = _mooc_component(db, student)
    if component is None:
        return {
            "eligible": False, "component": None,
            "reasons": ["Your curriculum does not include a MOOC/NPTEL requirement."],
        }
    access = student_can_access_component(student, component)
    return {
        "eligible": access.eligible,
        "reasons": access.reasons,
        "component": {
            "id": component.id, "code": component.code, "title": component.title,
            "semester_number": component.semester_number,
            "credits": float(component.credits),
            "scope_label": component.scope_label,
        },
    }


@router.get("/catalogue", response_model=list[CourseOfferingOut])
def catalogue(db: DbSession, student: CurrentStudent) -> list[CourseOfferingOut]:
    component = _mooc_component(db, student)
    if component is None:
        return []
    offerings = db.scalars(
        select(CourseOffering).where(
            CourseOffering.curriculum_component_id == component.id
        )
    )
    return [offering_out(o, is_open=offering_window_open(o)) for o in offerings]


@router.get("/me", response_model=list[MoocRegistrationOut])
def my_registrations(db: DbSession, student: CurrentStudent) -> list[MoocRegistrationOut]:
    rows = db.scalars(
        select(MoocRegistration).where(MoocRegistration.student_id == student.id)
        .order_by(MoocRegistration.created_at.desc())
    )
    return [_out(db, r) for r in rows]


@router.post("/register", response_model=MoocRegistrationOut, status_code=201)
def register(payload: MoocRegisterRequest, db: DbSession, student: CurrentStudent,
             user: CurrentUser) -> MoocRegistrationOut:
    component = _mooc_component(db, student)
    if component is None:
        raise BusinessRuleError(
            "Your curriculum does not include a MOOC/NPTEL component."
        )
    access = student_can_access_component(student, component)
    if not access.eligible:
        raise BusinessRuleError(access.reasons[0])
    if mooc_rounds.round_for_student(db, student) is not None:
        raise BusinessRuleError(
            "Your coordinator has opened a round for this: choose your course or NCC there.")

    offering = db.get(CourseOffering, payload.course_offering_id)
    if offering is None or offering.curriculum_component_id != component.id:
        raise NotFoundError("That course is not part of your MOOC requirement.")
    if not offering_window_open(offering):
        raise BusinessRuleError("Registration for this course is not currently open.")
    if db.scalar(select(MoocRegistration).where(
        MoocRegistration.student_id == student.id,
        MoocRegistration.course_offering_id == offering.id,
    )):
        raise BusinessRuleError("You have already registered for this course.")

    registration = MoocRegistration(
        student_id=student.id, course_offering_id=offering.id,
        curriculum_component_id=component.id,
        platform=offering.course.platform or "NPTEL",
        platform_registration_id=payload.platform_registration_id,
        course_url=offering.course.provider_url,
        exam_date=payload.exam_date, exam_city=payload.exam_city,
        status=MoocStatus.REGISTERED,
    )
    db.add(registration)
    offering.seats_filled += 1
    db.flush()
    notifications.notify(
        db, user_id=user.id, type=NotificationType.REGISTRATION_CONFIRMED,
        title="NPTEL registration recorded",
        message=f"You are registered for {offering.course.title}. Upload your "
                "certificate once the course is complete.",
        link="/academics/nptel",
    )
    audit.record(db, action=AuditAction.CREATE, entity_type="mooc_registration",
                 entity_id=registration.id, actor=user,
                 description=f"Registered for MOOC {offering.course.code}")
    db.commit()
    db.refresh(registration)
    return _out(db, registration)


@router.patch("/{registration_id}", response_model=MoocRegistrationOut)
def update_registration(registration_id: int, payload: MoocUpdateRequest, db: DbSession,
                        student: CurrentStudent, user: CurrentUser) -> MoocRegistrationOut:
    reg = db.get(MoocRegistration, registration_id)
    if reg is None:
        raise NotFoundError("Registration not found.")
    if reg.student_id != student.id:
        raise PermissionDeniedError("You can only update your own registration.")
    if reg.verification_status == VerificationStatus.VERIFIED:
        raise BusinessRuleError("A verified registration can no longer be edited.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(reg, field, value)
    if reg.exam_date and reg.status == MoocStatus.REGISTERED:
        reg.status = MoocStatus.EXAM_SCHEDULED
    audit.record(db, action=AuditAction.UPDATE, entity_type="mooc_registration",
                 entity_id=reg.id, actor=user, description="Updated MOOC registration")
    db.commit()
    db.refresh(reg)
    return _out(db, reg)


@router.post("/{registration_id}/certificate", response_model=MoocRegistrationOut)
async def upload_certificate(registration_id: int, db: DbSession,
                             student: CurrentStudent, user: CurrentUser,
                             file: UploadFile = File(...)) -> MoocRegistrationOut:
    reg = db.get(MoocRegistration, registration_id)
    if reg is None:
        raise NotFoundError("Registration not found.")
    if reg.student_id != student.id:
        raise PermissionDeniedError("You can only upload to your own registration.")
    # Replacing a verified certificate used to reset it to PENDING, reopening
    # a completed registration (and its score) to edits.
    if reg.verification_status == VerificationStatus.VERIFIED:
        raise BusinessRuleError("This certificate has been verified and can no longer be replaced.")
    if reg.mooc_round_id is not None:
        mooc_rounds.assert_can_submit_result(db.get(MoocRound, reg.mooc_round_id), reg)

    stored = await save_upload(db, file, category=FileCategory.CERTIFICATE,
                               uploaded_by=user)
    reg.certificate_file_id = stored.id
    reg.status = MoocStatus.CERTIFICATE_UPLOADED
    reg.verification_status = VerificationStatus.PENDING
    audit.record(db, action=AuditAction.UPLOAD, entity_type="mooc_registration",
                 entity_id=reg.id, actor=user, description="Uploaded MOOC certificate")
    db.commit()
    db.refresh(reg)
    return _out(db, reg)


# ── verification (department admin) ───────────────────────────────────────
@router.get("/admin/registrations", response_model=list[MoocRegistrationOut])
def all_registrations(
    db: DbSession, user: CurrentUser,
    verification_status: VerificationStatus | None = None,
) -> list[MoocRegistrationOut]:
    """Verification queue, narrowed to the departments the caller coordinates."""
    if not has_permission(user.roles, P["MOOC_VERIFY"]) and not any(
        c.domain == CoordinationDomain.MOOC for c in scope.coordinations_for(db, user)
    ):
        raise PermissionDeniedError("You do not coordinate NPTEL verification.")

    stmt = select(MoocRegistration).order_by(MoocRegistration.created_at.desc())
    if verification_status:
        stmt = stmt.where(MoocRegistration.verification_status == verification_status)

    rows = list(db.scalars(stmt))
    # Only institution-wide roles see every department. Department Admin holds
    # `mooc:verify` too, and that used to skip the filter — the ICT office saw
    # every department's NPTEL registrations. Each row is now held to the same
    # test as verifying it.
    if not user.has_role(*scope.UNSCOPED_ROLES):
        rows = [
            r for r in rows
            if scope.coordinates(db, user, CoordinationDomain.MOOC,
                                 scope.student_department_id(db, r.student_id))
        ]
    return [_out(db, r) for r in rows]


@router.post("/admin/{registration_id}/verify", response_model=MoocRegistrationOut)
def verify(
    registration_id: int, payload: MoocVerifyRequest, db: DbSession,
    user: CurrentUser,
) -> MoocRegistrationOut:
    reg = db.get(MoocRegistration, registration_id)
    if reg is None:
        raise NotFoundError("Registration not found.")
    scope.assert_coordinates(
        db, user, CoordinationDomain.MOOC,
        scope.student_department_id(db, reg.student_id),
        permission=P["MOOC_VERIFY"], what="NPTEL",
    )
    if reg.certificate_file_id is None:
        raise BusinessRuleError("No certificate has been uploaded for this registration.")
    if payload.verification_status not in (VerificationStatus.VERIFIED, VerificationStatus.REJECTED):
        raise ValidationError("Verify or reject the certificate.")
    if payload.verification_status == VerificationStatus.REJECTED and not (payload.remarks or "").strip():
        raise ValidationError("Say why the certificate is rejected, so the student can fix it.")

    reg.verification_status = payload.verification_status
    reg.verified_by_user_id = user.id
    reg.verified_at = dt.datetime.now(dt.timezone.utc)
    reg.remarks = payload.remarks
    if payload.grade:
        reg.grade = payload.grade
    if payload.final_score is not None:
        reg.final_score = payload.final_score
    reg.status = (
        MoocStatus.COMPLETED if payload.verification_status == VerificationStatus.VERIFIED
        else MoocStatus.REJECTED
    )

    student = db.get(Student, reg.student_id)
    if student:
        notifications.notify(
            db, user_id=student.user_id, type=NotificationType.EVALUATION_UPDATE,
            title=(f"{'NCC' if reg.option == MoocOption.NCC else 'NPTEL'} certificate "
                   f"{payload.verification_status.value.lower()}"),
            message=payload.remarks or "Your certificate has been reviewed.",
            link="/academics/nptel",
        )
    audit.record(db, action=AuditAction.UPDATE, entity_type="mooc_registration",
                 entity_id=reg.id, actor=user,
                 description=f"Certificate {payload.verification_status.value}",
                 meta={"remarks": payload.remarks})
    db.commit()
    db.refresh(reg)
    return _out(db, reg)


# ── rounds: the coordinator's NPTEL / NCC choice for a semester ───────────
def _course_out(course: Course, chosen: int | None = None) -> MoocCourseOut:
    details = course.provider_details or {}
    return MoocCourseOut(
        course_id=course.id, code=course.code, title=course.title,
        weeks=course.duration_weeks,
        credits=float(course.credits) if course.credits is not None else None,
        url=course.provider_url, discipline=details.get("discipline"),
        instructors=details.get("instructors"), institute=details.get("institute"),
        coordinating_institute=details.get("coordinating_institute"),
        chosen_count=chosen)


def _round_department(db, component: CurriculumComponent) -> int | None:
    curriculum = db.get(Curriculum, component.curriculum_id)
    program = db.get(Program, curriculum.program_id) if curriculum else None
    return program.department_id if program else None


def _manages_round(db, user: User, round_: MoocRound) -> bool:
    return user.has_role(Role.SUPER_ADMIN) or scope.coordinates(
        db, user, CoordinationDomain.MOOC, round_.department_id)


def _assert_manages_round(db, user: User, round_: MoocRound) -> None:
    scope.assert_coordinates(db, user, CoordinationDomain.MOOC, round_.department_id,
                             permission=P["MOOC_VERIFY"], what="NPTEL")


def _assert_views_round(db, user: User, round_: MoocRound) -> None:
    if _manages_round(db, user, round_):
        return
    if round_.department_id is not None and scope.oversees(db, user, round_.department_id):
        return
    raise PermissionDeniedError("This NPTEL round belongs to another department.")


def _get_round(db, round_id: int) -> MoocRound:
    round_ = db.get(MoocRound, round_id)
    if round_ is None:
        raise NotFoundError("NPTEL round not found.")
    return round_


def _round_out(db, round_: MoocRound, user: User | None = None) -> MoocRoundOut:
    now = mooc_rounds.utcnow()
    component = db.get(CurriculumComponent, round_.curriculum_component_id)
    # The coordinator counts everyone the round is for, verified ones included.
    covered = mooc_rounds.covered_students(db, round_, include_cleared=True) \
        if round_.status != MoocRoundStatus.CLOSED else []
    regs = list(db.scalars(select(MoocRegistration).where(
        MoocRegistration.mooc_round_id == round_.id)))
    return MoocRoundOut(
        id=round_.id, title=round_.title, message=round_.message, status=round_.status,
        department_id=round_.department_id,
        curriculum_component_id=round_.curriculum_component_id,
        component_code=component.code if component else None,
        component_title=component.title if component else None,
        component_semester=component.semester_number if component else None,
        eligible_semesters=round_.eligible_semesters or [],
        opens_at=round_.opens_at, closes_at=round_.closes_at,
        platform_deadline=round_.platform_deadline, locked_at=round_.locked_at,
        closed_at=round_.closed_at, is_open=round_.is_open_at(now),
        is_past_deadline=bool(round_.closes_at_utc and now >= round_.closes_at_utc),
        course_count=len(mooc_rounds.approved_courses(db, round_)),
        covered_count=len(covered), carry_over_count=sum(1 for c in covered if c.carry_over),
        chosen_count=len(regs),
        nptel_count=sum(1 for r in regs if r.option == MoocOption.NPTEL),
        ncc_count=sum(1 for r in regs if r.option == MoocOption.NCC),
        certificates_waiting=sum(1 for r in regs if r.certificate_file_id is not None
                                 and r.verification_status == VerificationStatus.PENDING),
        verified_count=sum(1 for r in regs
                           if r.verification_status == VerificationStatus.VERIFIED),
        failed_count=sum(1 for r in regs if r.status == MoocStatus.FAILED),
        can_manage=bool(user and _manages_round(db, user, round_)),
    )


def _coordinator_or_hod(db: DbSession, user: CurrentUser) -> User:
    if (has_permission(user.roles, P["MOOC_VERIFY"]) or scope.hod_department(db, user)
            or any(c.domain == CoordinationDomain.MOOC
                   for c in scope.coordinations_for(db, user))):
        return user
    raise PermissionDeniedError("You do not coordinate NPTEL.")


@router.get("/admin/rounds", response_model=list[MoocRoundOut])
def list_rounds(db: DbSession, user: User = Depends(_coordinator_or_hod)) -> list[MoocRoundOut]:
    rounds = db.scalars(select(MoocRound).order_by(MoocRound.id.desc()))
    out = []
    for round_ in rounds:
        try:
            _assert_views_round(db, user, round_)
        except PermissionDeniedError:
            continue
        out.append(_round_out(db, round_, user))
    return out


@router.get("/admin/slots")
def mooc_slots(db: DbSession, user: User = Depends(_coordinator_or_hod)) -> list[dict]:
    """The curriculum MOOC slots this coordinator can open a round for."""
    rows = db.execute(
        select(CurriculumComponent, Curriculum, Program)
        .join(Curriculum, Curriculum.id == CurriculumComponent.curriculum_id)
        .join(Program, Program.id == Curriculum.program_id)
        .where(CurriculumComponent.component_type == ComponentType.MOOC)
        .order_by(Program.code, CurriculumComponent.semester_number)).all()
    return [
        {"component_id": c.id, "code": c.code, "title": c.title,
         "semester_number": c.semester_number, "program_code": program.code,
         "curriculum_version": curriculum.version, "department_id": program.department_id}
        for c, curriculum, program in rows
        if user.has_role(Role.SUPER_ADMIN)
        or scope.coordinates(db, user, CoordinationDomain.MOOC, program.department_id)
    ]


@router.post("/admin/rounds", response_model=MoocRoundOut, status_code=201)
def create_round(payload: MoocRoundIn, db: DbSession, user: CurrentUser) -> MoocRoundOut:
    component = db.get(CurriculumComponent, payload.curriculum_component_id)
    if component is None or component.component_type != ComponentType.MOOC:
        raise ValidationError("Choose the curriculum's NPTEL / MOOC slot.")
    if payload.opens_at and payload.closes_at and payload.closes_at <= payload.opens_at:
        raise ValidationError("The closing time must be after the opening time.")
    round_ = MoocRound(
        title=payload.title, message=payload.message,
        curriculum_component_id=component.id,
        department_id=_round_department(db, component),
        eligible_semesters=payload.eligible_semesters or [component.semester_number],
        opens_at=payload.opens_at, closes_at=payload.closes_at,
        platform_deadline=payload.platform_deadline, status=MoocRoundStatus.DRAFT)
    _assert_manages_round(db, user, round_)
    db.add(round_)
    db.flush()
    if payload.copy_list_from:
        source = _get_round(db, payload.copy_list_from)
        _assert_views_round(db, user, source)
        mooc_rounds.copy_list(db, round_, source)
    audit.record(db, action=AuditAction.CREATE, entity_type="mooc_round",
                 entity_id=round_.id, actor=user, description=f"NPTEL round '{round_.title}'")
    db.commit()
    return _round_out(db, round_, user)


@router.patch("/admin/rounds/{round_id}", response_model=MoocRoundOut)
def update_round(round_id: int, payload: MoocRoundUpdate, db: DbSession,
                 user: CurrentUser) -> MoocRoundOut:
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    if round_.status == MoocRoundStatus.CLOSED:
        raise BusinessRuleError("This round is closed.")
    changes = payload.model_dump(exclude_unset=True)
    before = round_.closes_at_utc
    for key, value in changes.items():
        if key == "eligible_semesters" and value is not None and not value:
            raise ValidationError("Choose at least one semester.")
        setattr(round_, key, value)
    if round_.opens_at and round_.closes_at and round_.closes_at_utc <= round_.opens_at_utc:
        raise ValidationError("The closing time must be after the opening time.")
    moved = "closes_at" in changes and round_.closes_at_utc != before
    if moved and round_.status == MoocRoundStatus.OPEN:
        if round_.closes_at_utc is None or round_.closes_at_utc <= mooc_rounds.utcnow():
            raise ValidationError("The new deadline must be in the future. To stop "
                                  "choosing now, lock the round.")
        _notify_covered(db, round_, f"{round_.title}: deadline extended",
                        "Choose your NPTEL course or NCC before "
                        f"{round_.closes_at_utc:%d %b %Y, %H:%M} UTC.")
    audit.record(db, action=AuditAction.UPDATE, entity_type="mooc_round",
                 entity_id=round_.id, actor=user, description="Updated NPTEL round",
                 meta=payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return _round_out(db, round_, user)


def _notify_covered(db, round_: MoocRound, title: str, message: str,
                    only: set[int] | None = None) -> int:
    ids = [c.student.user_id for c in mooc_rounds.covered_students(db, round_)
           if only is None or c.student.id in only]
    notifications.notify_many(db, user_ids=ids, type=NotificationType.ELECTIVE_DEADLINE,
                              title=title, message=message, link="/academics/nptel")
    return len(ids)


@router.post("/admin/rounds/{round_id}/status", response_model=MoocRoundOut)
def move_round(round_id: int, target: MoocRoundStatus, db: DbSession,
               user: CurrentUser) -> MoocRoundOut:
    """Open (or reopen) choosing, or lock it. Closing has its own route."""
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    previous = round_.status
    allowed = {MoocRoundStatus.DRAFT: {MoocRoundStatus.OPEN},
               MoocRoundStatus.OPEN: {MoocRoundStatus.LOCKED},
               MoocRoundStatus.LOCKED: {MoocRoundStatus.OPEN}}
    if target not in allowed.get(previous, set()):
        raise BusinessRuleError(
            f"A {previous.value.lower()} round cannot become {target.value.lower()}.")
    notified = 0
    if target == MoocRoundStatus.OPEN:
        if not mooc_rounds.approved_courses(db, round_):
            raise BusinessRuleError("Add the approved course list before opening the round.")
        if round_.closes_at_utc is None or round_.closes_at_utc <= mooc_rounds.utcnow():
            raise BusinessRuleError("Set a deadline in the future before opening the round.")
        round_.status = MoocRoundStatus.OPEN
        round_.locked_at = None
        deadline = f"{round_.closes_at_utc:%d %b %Y, %H:%M} UTC"
        nptel = (f" Register on the NPTEL portal by {round_.platform_deadline:%d %b %Y}."
                 if round_.platform_deadline else "")
        notified = _notify_covered(
            db, round_, f"{round_.title}: choose your NPTEL course or NCC",
            f"Choose one course from the approved list, or NCC, before {deadline}.{nptel}")
    else:
        round_.status = MoocRoundStatus.LOCKED
        round_.locked_at = mooc_rounds.utcnow()
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="mooc_round",
                 entity_id=round_.id, actor=user,
                 description=f"NPTEL round: {previous.value} -> {target.value}",
                 meta={"notified": notified})
    db.commit()
    return _round_out(db, round_, user)


@router.delete("/admin/rounds/{round_id}", response_model=Message)
def delete_round(round_id: int, db: DbSession, user: CurrentUser) -> Message:
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    if round_.status != MoocRoundStatus.DRAFT and db.scalar(
            select(func.count(MoocRegistration.id)).where(
                MoocRegistration.mooc_round_id == round_.id)):
        raise BusinessRuleError(
            "Students have chosen in this round, so it is kept as the semester's record.")
    if round_.status == MoocRoundStatus.CLOSED:
        raise BusinessRuleError("A closed round is the semester's record and is kept.")
    title = round_.title
    db.delete(round_)
    audit.record(db, action=AuditAction.DELETE, entity_type="mooc_round",
                 entity_id=round_id, actor=user, description=f"Deleted NPTEL round '{title}'")
    db.commit()
    return Message(message=f"{title} deleted.")


@router.get("/admin/rounds/{round_id}/courses", response_model=list[MoocCourseOut])
def round_courses(round_id: int, db: DbSession,
                  user: User = Depends(_coordinator_or_hod)) -> list[MoocCourseOut]:
    round_ = _get_round(db, round_id)
    _assert_views_round(db, user, round_)
    counts = dict(db.execute(
        select(MoocRegistration.course_id, func.count(MoocRegistration.id))
        .where(MoocRegistration.mooc_round_id == round_.id,
               MoocRegistration.course_id.is_not(None))
        .group_by(MoocRegistration.course_id)).all())
    return [_course_out(c, int(counts.get(c.id, 0)))
            for c in mooc_rounds.approved_courses(db, round_)]


def _row(payload: MoocCourseIn) -> mooc_rounds.CourseRow:
    return mooc_rounds.CourseRow(**payload.model_dump())


@router.post("/admin/rounds/{round_id}/courses", response_model=MoocCourseOut, status_code=201)
def add_round_course(round_id: int, payload: MoocCourseIn, db: DbSession,
                     user: CurrentUser) -> MoocCourseOut:
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    course, state = mooc_rounds.add_course(db, round_, _row(payload))
    if state == "already listed":
        raise ConflictError(f"{course.code} is already on this round's list.")
    audit.record(db, action=AuditAction.CREATE, entity_type="mooc_round_course",
                 entity_id=round_.id, actor=user, description=f"Listed {course.code}")
    db.commit()
    return _course_out(course, 0)


@router.post("/admin/rounds/{round_id}/courses/import", response_model=MoocImportResult)
async def import_round_courses(round_id: int, db: DbSession, user: CurrentUser,
                               file: UploadFile = File(...)) -> MoocImportResult:
    """Read the department's sheet (.xlsx or .csv) onto the list."""
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    content = await file.read()
    if len(content) > 2_000_000:
        raise ValidationError("That file is too large for a course list.")
    rows = mooc_rounds.parse_sheet(content, file.filename or "")
    result = mooc_rounds.import_courses(db, round_, rows)
    audit.record(db, action=AuditAction.CREATE, entity_type="mooc_round_course",
                 entity_id=round_.id, actor=user,
                 description=f"Imported {len(result.added) + len(result.updated)} course(s)",
                 meta={"file": file.filename, "skipped": len(result.skipped)})
    db.commit()
    return MoocImportResult(added=result.added, updated=result.updated,
                            already_listed=result.already_listed,
                            skipped=[{"course": c, "reason": r} for c, r in result.skipped])


@router.delete("/admin/rounds/{round_id}/courses/{course_id}", response_model=Message)
def remove_round_course(round_id: int, course_id: int, db: DbSession,
                        user: CurrentUser) -> Message:
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    mooc_rounds.remove_course(db, round_, course_id)
    audit.record(db, action=AuditAction.DELETE, entity_type="mooc_round_course",
                 entity_id=round_.id, actor=user, description=f"Unlisted course {course_id}")
    db.commit()
    return Message(message="Removed from the list.")


@router.post("/admin/rounds/{round_id}/courses/copy/{source_id}", response_model=Message)
def copy_round_courses(round_id: int, source_id: int, db: DbSession,
                       user: CurrentUser) -> Message:
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    source = _get_round(db, source_id)
    _assert_views_round(db, user, source)
    added = mooc_rounds.copy_list(db, round_, source)
    db.commit()
    return Message(message=f"{added} course(s) copied from {source.title}.")


def _roster(db, round_: MoocRound) -> list[MoocRosterRow]:
    regs = {r.student_id: r for r in db.scalars(select(MoocRegistration).where(
        MoocRegistration.mooc_round_id == round_.id))}
    # The coordinator counts everyone the round is for, verified ones included.
    covered = mooc_rounds.covered_students(db, round_, include_cleared=True) \
        if round_.status != MoocRoundStatus.CLOSED else []
    people = {c.student.id: c for c in covered}
    for student_id in regs:
        if student_id not in people:
            student = db.get(Student, student_id)
            if student:
                people[student_id] = mooc_rounds.Covered(student, carry_over=False)
    rows = []
    for c in sorted(people.values(), key=lambda c: c.student.roll_number or ""):
        reg = regs.get(c.student.id)
        course = _reg_course(reg) if reg else None
        ncc = reg is not None and reg.option == MoocOption.NCC
        rows.append(MoocRosterRow(
            student_id=c.student.id, student_name=c.student.user.full_name,
            roll_number=c.student.roll_number, semester=c.student.current_semester,
            carry_over=c.carry_over, registration_id=reg.id if reg else None,
            option=reg.option if reg else None,
            course_code="NCC" if ncc else (course.code if course else None),
            course_title="NCC certification" if ncc else (course.title if course else None),
            status=reg.status if reg else None,
            verification_status=reg.verification_status if reg else None,
            certificate_url=file_url(db, reg.certificate_file_id) if reg else None))
    return rows


@router.get("/admin/rounds/{round_id}/students", response_model=list[MoocRosterRow])
def round_students(round_id: int, db: DbSession,
                   user: User = Depends(_coordinator_or_hod)) -> list[MoocRosterRow]:
    round_ = _get_round(db, round_id)
    _assert_views_round(db, user, round_)
    return _roster(db, round_)


@router.post("/admin/rounds/{round_id}/remind", response_model=MoocRemindResult)
def remind_round(round_id: int, db: DbSession, user: CurrentUser) -> MoocRemindResult:
    """Remind only the students who have not chosen yet."""
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    if round_.status != MoocRoundStatus.OPEN:
        raise BusinessRuleError("Only an open round has students left to remind.")
    chosen = set(db.scalars(select(MoocRegistration.student_id).where(
        MoocRegistration.mooc_round_id == round_.id)))
    waiting = {c.student.id for c in mooc_rounds.covered_students(db, round_)} - chosen
    deadline = (f" before {round_.closes_at_utc:%d %b %Y, %H:%M} UTC"
                if round_.closes_at_utc else "")
    notified = _notify_covered(db, round_, f"Reminder: {round_.title}",
                               f"You have not chosen your NPTEL course or NCC yet. "
                               f"Choose from the approved list{deadline}.", only=waiting)
    audit.record(db, action=AuditAction.UPDATE, entity_type="mooc_round",
                 entity_id=round_.id, actor=user, description="Reminded students",
                 meta={"notified": notified})
    db.commit()
    return MoocRemindResult(notified=notified)


@router.get("/admin/rounds/{round_id}/export")
def export_round(round_id: int, db: DbSession,
                 user: User = Depends(_coordinator_or_hod)) -> StreamingResponse:
    round_ = _get_round(db, round_id)
    _assert_views_round(db, user, round_)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Roll number", "Name", "Semester", "Carry-over", "Choice",
                     "Course ID", "Course name", "Status", "Certificate"])
    for row in _roster(db, round_):
        writer.writerow([csv_safe(v) for v in (
            row.roll_number, row.student_name, row.semester,
            "Yes" if row.carry_over else "", row.option.value if row.option else "Not chosen",
            row.course_code or "", row.course_title or "",
            row.status.value if row.status else "",
            row.verification_status.value if row.verification_status and row.registration_id
            else "")])
    name = "".join(ch if ch.isalnum() else "-" for ch in round_.title).strip("-")[:60]
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{name or "nptel"}.csv"'})


@router.post("/admin/rounds/{round_id}/close", response_model=MoocCloseResult)
def close_round(round_id: int, payload: MoocCloseRequest, db: DbSession,
                user: CurrentUser) -> MoocCloseResult:
    """Close the semester: record each student's outcome on the slot."""
    round_ = _get_round(db, round_id)
    _assert_manages_round(db, user, round_)
    result = mooc_rounds.close_round(db, round_, force=payload.force)
    component = db.get(CurriculumComponent, round_.curriculum_component_id)
    name = component.title if component else "Your NPTEL / NCC requirement"
    for ids, title, message in (
        (result.carried_over, f"{name}: carried over to next semester",
         "It was not cleared this semester. Choose an NPTEL course or NCC again in the "
         "next semester's round."),
        (result.backlog, f"{name}: now a backlog",
         "It was not cleared in either semester. Contact the department."),
    ):
        users = [s.user_id for sid in ids if (s := db.get(Student, sid))]
        notifications.notify_many(db, user_ids=users, type=NotificationType.EVALUATION_UPDATE,
                                  title=title, message=message, link="/academics/nptel")
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="mooc_round",
                 entity_id=round_.id, actor=user, description="Closed NPTEL round semester",
                 meta={"cleared": len(result.cleared),
                       "carried_over": len(result.carried_over),
                       "backlog": len(result.backlog), "forced": payload.force})
    db.commit()
    return MoocCloseResult(cleared=len(result.cleared),
                           carried_over=len(result.carried_over),
                           backlog=len(result.backlog),
                           awaiting_verification=result.awaiting_verification)


# ── the student's side of a round ─────────────────────────────────────────
def _choice_out(db, reg: MoocRegistration) -> MoocChoiceOut:
    course = _reg_course(reg)
    return MoocChoiceOut(
        registration_id=reg.id, option=reg.option,
        course=_course_out(course) if course and reg.option == MoocOption.NPTEL else None,
        status=reg.status, verification_status=reg.verification_status,
        certificate_url=file_url(db, reg.certificate_file_id), remarks=reg.remarks,
        updated_at=reg.updated_at)


def _student_round(db, round_: MoocRound, covered: mooc_rounds.Covered,
                   student: Student) -> StudentMoocRoundOut:
    now = mooc_rounds.utcnow()
    reg = db.scalar(select(MoocRegistration).where(
        MoocRegistration.mooc_round_id == round_.id,
        MoocRegistration.student_id == student.id))
    can_choose = round_.is_open_at(now) and not (reg and reg.certificate_file_id)
    if can_choose:
        reason = None
    elif round_.status == MoocRoundStatus.OPEN and round_.opens_at_utc \
            and now < round_.opens_at_utc:
        reason = f"Choosing opens on {round_.opens_at_utc:%d %b %Y, %H:%M} UTC."
    elif reg and reg.certificate_file_id:
        reason = "Your certificate is submitted, so your choice is final."
    else:
        reason = "Choosing has closed."
    can_result = (reg is not None and reg.verification_status != VerificationStatus.VERIFIED
                  and round_.status in (MoocRoundStatus.OPEN, MoocRoundStatus.LOCKED))
    return StudentMoocRoundOut(
        id=round_.id, title=round_.title, message=round_.message, status=round_.status,
        opens_at=round_.opens_at, closes_at=round_.closes_at,
        platform_deadline=round_.platform_deadline, can_choose=bool(can_choose),
        reason=reason, carry_over=covered.carry_over,
        courses=[_course_out(c) for c in mooc_rounds.approved_courses(db, round_)],
        choice=_choice_out(db, reg) if reg else None, can_submit_result=can_result)


@router.get("/rounds/mine", response_model=StudentMoocStanding)
def my_round(db: DbSession, student: CurrentStudent) -> StudentMoocStanding:
    component = _mooc_component(db, student)
    found = mooc_rounds.round_for_student(db, student)
    if found is not None:
        round_, covered = found
        component = db.get(CurriculumComponent, round_.curriculum_component_id)
    return StudentMoocStanding(
        component_id=component.id if component else None,
        component_code=component.code if component else None,
        component_title=component.title if component else None,
        component_semester=component.semester_number if component else None,
        standing=(mooc_rounds.standing(db, student, component.id) if component else None),
        round=_student_round(db, found[0], found[1], student) if found else None)


@router.post("/rounds/{round_id}/choice", response_model=StudentMoocRoundOut)
def choose_in_round(round_id: int, payload: MoocChoiceIn, db: DbSession,
                    student: CurrentStudent, user: CurrentUser) -> StudentMoocRoundOut:
    round_ = _get_round(db, round_id)
    if round_.status == MoocRoundStatus.DRAFT:
        raise NotFoundError("NPTEL round not found.")
    reg = mooc_rounds.choose(db, round_, student, option=payload.option,
                             course_id=payload.course_id)
    chosen = ("NCC" if payload.option == MoocOption.NCC
              else (reg.course.title if reg.course else "your course"))
    notifications.notify(
        db, user_id=user.id, type=NotificationType.REGISTRATION_CONFIRMED,
        title=f"{round_.title}: choice recorded",
        message=(f"You chose {chosen}. "
                 + ("Register for it on the NPTEL portal yourself"
                    + (f" by {round_.platform_deadline:%d %b %Y}" if round_.platform_deadline
                       else "")
                    + ". " if payload.option == MoocOption.NPTEL else "")
                 + "Submit the certificate here when you complete it."),
        link="/academics/nptel")
    audit.record(db, action=AuditAction.CREATE, entity_type="mooc_registration",
                 entity_id=reg.id, actor=user,
                 description=f"Chose {chosen} in NPTEL round {round_.id}")
    db.commit()
    covered = mooc_rounds.covers(db, round_, student) or mooc_rounds.Covered(student, False)
    return _student_round(db, round_, covered, student)


@router.post("/{registration_id}/failed", response_model=MoocRegistrationOut)
def report_failed(registration_id: int, db: DbSession, student: CurrentStudent,
                  user: CurrentUser) -> MoocRegistrationOut:
    """The student did not pass (and so has no certificate)."""
    reg = db.get(MoocRegistration, registration_id)
    if reg is None:
        raise NotFoundError("Registration not found.")
    if reg.student_id != student.id:
        raise PermissionDeniedError("You can only update your own registration.")
    round_ = db.get(MoocRound, reg.mooc_round_id) if reg.mooc_round_id else None
    mooc_rounds.report_failed(db, round_, reg)
    audit.record(db, action=AuditAction.UPDATE, entity_type="mooc_registration",
                 entity_id=reg.id, actor=user, description="Reported not passing")
    db.commit()
    db.refresh(reg)
    return _out(db, reg)
