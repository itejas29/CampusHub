from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.errors import NotFoundError
from app.core.rbac import P
from app.models.academics import Course, CourseOffering
from app.models.enums import AuditAction, MoocPlatform
from app.models.identity import Faculty, User
from app.schemas.academics import (
    CourseOfferingCreate, CourseOfferingOut, CourseOfferingUpdate, CourseOut,
    CourseCreate, CourseUpdate,
)
from app.schemas.common import Message, Page
from app.services import audit
from app.services.serializers import course_out, offering_out

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=Page[CourseOut])
def list_courses(
    db: DbSession, _: CurrentUser,
    q: str | None = Query(None, description="Search code or title"),
    department_id: int | None = None,
    specialization_area: str | None = None,
    platform: MoocPlatform | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
) -> Page[CourseOut]:
    stmt = select(Course)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Course.code.ilike(pattern), Course.title.ilike(pattern)))
    if department_id:
        stmt = stmt.where(Course.department_id == department_id)
    if specialization_area:
        stmt = stmt.where(Course.specialization_area == specialization_area)
    if platform:
        stmt = stmt.where(Course.platform == platform)
    if is_active is not None:
        stmt = stmt.where(Course.is_active.is_(is_active))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Course.code).offset((page - 1) * page_size).limit(page_size)
    )
    return Page[CourseOut](items=[course_out(c) for c in rows], total=total,
                           page=page, page_size=page_size)


@router.get("/specializations", response_model=list[str])
def specializations(db: DbSession, _: CurrentUser) -> list[str]:
    rows = db.scalars(
        select(Course.specialization_area)
        .where(Course.specialization_area.is_not(None))
        .distinct().order_by(Course.specialization_area)
    )
    return list(rows)


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: DbSession, _: CurrentUser) -> CourseOut:
    course = db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    return course_out(course)


@router.post("", response_model=CourseOut, status_code=201)
def create_course(
    payload: CourseCreate, db: DbSession,
    user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
) -> CourseOut:
    course = Course(**payload.model_dump())
    db.add(course)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="course",
                 entity_id=course.id, actor=user,
                 description=f"Created course {course.code}")
    db.commit()
    db.refresh(course)
    return course_out(course)


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(
    course_id: int, payload: CourseUpdate, db: DbSession,
    user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
) -> CourseOut:
    course = db.get(Course, course_id)
    if course is None:
        raise NotFoundError("Course not found.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(course, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="course",
                 entity_id=course.id, actor=user,
                 description=f"Updated course {course.code}", meta={"changes": list(changes)})
    db.commit()
    db.refresh(course)
    return course_out(course)


# ── offerings ─────────────────────────────────────────────────────────────
offerings_router = APIRouter(prefix="/course-offerings", tags=["courses"])


@offerings_router.get("", response_model=list[CourseOfferingOut])
def list_offerings(
    db: DbSession, _: CurrentUser,
    curriculum_component_id: int | None = None,
    semester_id: int | None = None,
    status: str | None = None,
) -> list[CourseOfferingOut]:
    stmt = select(CourseOffering)
    if curriculum_component_id:
        stmt = stmt.where(
            CourseOffering.curriculum_component_id == curriculum_component_id
        )
    if semester_id:
        stmt = stmt.where(CourseOffering.semester_id == semester_id)
    if status:
        stmt = stmt.where(CourseOffering.status == status)
    return [offering_out(o) for o in db.scalars(stmt.order_by(CourseOffering.id))]


@offerings_router.post("", response_model=CourseOfferingOut, status_code=201)
def create_offering(
    payload: CourseOfferingCreate, db: DbSession,
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> CourseOfferingOut:
    offering = CourseOffering(**payload.model_dump())
    db.add(offering)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="course_offering",
                 entity_id=offering.id, actor=user, description="Created course offering")
    db.commit()
    db.refresh(offering)
    return offering_out(offering)


@offerings_router.patch("/{offering_id}", response_model=CourseOfferingOut)
def update_offering(
    offering_id: int, payload: CourseOfferingUpdate, db: DbSession,
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> CourseOfferingOut:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFoundError("Course offering not found.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(offering, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="course_offering",
                 entity_id=offering.id, actor=user,
                 description="Updated course offering", meta={"changes": list(changes)})
    db.commit()
    db.refresh(offering)
    return offering_out(offering)


@offerings_router.delete("/{offering_id}", response_model=Message)
def delete_offering(
    offering_id: int, db: DbSession,
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> Message:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFoundError("Course offering not found.")
    db.delete(offering)
    audit.record(db, action=AuditAction.DELETE, entity_type="course_offering",
                 entity_id=offering_id, actor=user, description="Deleted course offering")
    db.commit()
    return Message(message="Course offering removed.")
