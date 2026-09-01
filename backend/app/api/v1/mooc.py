"""NPTEL / SWAYAM. Visibility is driven by the curriculum, not by role alone."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select

from app.core.deps import CurrentStudent, CurrentUser, DbSession, require_permission
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.rbac import P, has_permission
from app.models.academics import CourseOffering, CurriculumComponent, MoocRegistration
from app.models.enums import (
    AuditAction, ComponentType, CoordinationDomain, FileCategory, MoocStatus,
    NotificationType, VerificationStatus,
)
from app.models.identity import Student, User
from app.schemas.academics import (
    CourseOfferingOut, MoocRegisterRequest, MoocRegistrationOut, MoocUpdateRequest,
    MoocVerifyRequest,
)
from app.schemas.common import Message
from app.services import audit, notifications, scope
from app.services.eligibility import (
    components_for_semester, offering_window_open, student_can_access_component,
)
from app.services.files import save_upload
from app.services.serializers import file_url, offering_out

router = APIRouter(prefix="/mooc", tags=["mooc"])


def _out(db, reg: MoocRegistration) -> MoocRegistrationOut:
    offering = reg.course_offering
    student = db.get(Student, reg.student_id)
    return MoocRegistrationOut(
        id=reg.id, student_id=reg.student_id,
        student_name=student.user.full_name if student else None,
        roll_number=student.roll_number if student else None,
        course_offering_id=reg.course_offering_id,
        course_code=offering.course.code if offering else None,
        course_title=offering.course.title if offering else None,
        platform=reg.platform,
        platform_registration_id=reg.platform_registration_id,
        course_url=reg.course_url or (offering.course.provider_url if offering else None),
        status=reg.status, exam_date=reg.exam_date, exam_city=reg.exam_city,
        exam_fee_paid=reg.exam_fee_paid, exam_fee_reference=reg.exam_fee_reference,
        certificate_url=file_url(db, reg.certificate_file_id),
        verification_status=reg.verification_status, verified_at=reg.verified_at,
        final_score=float(reg.final_score) if reg.final_score is not None else None,
        grade=reg.grade, remarks=reg.remarks,
    )


def _mooc_component(db, student: Student) -> CurriculumComponent | None:
    components = [
        c for c in components_for_semester(db, student)
        if c.component_type == ComponentType.MOOC
    ]
    unlocked = [c for c in components if c.semester_number <= student.current_semester]
    return (unlocked or components or [None])[0]


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
    if not has_permission(user.roles, P["MOOC_VERIFY"]):
        allowed = {
            c.department_id
            for c in scope.coordinations_for(db, user)
            if c.domain == CoordinationDomain.MOOC
        }
        if None not in allowed:   # None = institution-wide
            rows = [
                r for r in rows
                if scope.student_department_id(db, r.student_id) in allowed
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
            title=f"NPTEL certificate {payload.verification_status.value.lower()}",
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
