from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import (
    CurrentUser, DbSession, get_optional_faculty, require_permission,
)
from app.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.core.rbac import P
from app.models.engagement import MentorAssignment, MentorMeeting
from app.models.enums import AuditAction, MeetingStatus, NotificationType, Role
from app.models.identity import AcademicYear, Faculty, Student, User
from app.schemas.common import Message
from app.schemas.engagement import (
    MeetingDecision, MeetingOut, MeetingRequest, MenteeRow, MentorProfile,
)
from app.services import audit, notifications, scope

router = APIRouter(prefix="/mentorship", tags=["mentorship"])


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _mentor_profile(faculty: Faculty) -> MentorProfile:
    return MentorProfile(
        faculty_id=faculty.id, full_name=faculty.user.full_name,
        designation=faculty.designation,
        department_name=faculty.department.name if faculty.department else None,
        department_code=faculty.department.code if faculty.department else None,
        cabin=faculty.cabin, email=faculty.public_email or faculty.user.email,
        phone=faculty.public_phone, specialization=faculty.specialization,
        qualification=faculty.qualification, avatar_url=faculty.user.avatar_url,
        bio=faculty.bio,
    )


def _meeting_out(meeting: MentorMeeting) -> MeetingOut:
    return MeetingOut(
        id=meeting.id, student_id=meeting.student_id,
        student_name=meeting.student.user.full_name if meeting.student else None,
        roll_number=meeting.student.roll_number if meeting.student else None,
        faculty_id=meeting.faculty_id,
        faculty_name=meeting.faculty.user.full_name if meeting.faculty else None,
        title=meeting.title, agenda=meeting.agenda, requested_at=meeting.requested_at,
        proposed_slot=meeting.proposed_slot, scheduled_at=meeting.scheduled_at,
        duration_minutes=meeting.duration_minutes, mode=meeting.mode,
        location=meeting.location, status=meeting.status,
        outcome_notes=meeting.outcome_notes,
    )


@router.get("/my-mentor", response_model=MentorProfile | None)
def my_mentor(db: DbSession, user: CurrentUser) -> MentorProfile | None:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise PermissionDeniedError("Only students have an assigned mentor.")
    assignment = db.scalar(
        select(MentorAssignment).where(MentorAssignment.student_id == student.id,
                                       MentorAssignment.is_active.is_(True))
        .order_by(MentorAssignment.id.desc())
    )
    return _mentor_profile(assignment.faculty) if assignment else None


@router.get("/my-mentees", response_model=list[MenteeRow])
def my_mentees(db: DbSession, user: CurrentUser, faculty=Depends(get_optional_faculty),
               q: str | None = Query(None)) -> list[MenteeRow]:
    if faculty is None:
        raise PermissionDeniedError("Only faculty accounts have mentees.")
    # Each mentee's account, programme and department in three batched
    # queries — loaded one by one this was ~2.4 queries a mentee (4,676 for
    # 1,900 mentees in the 10k-student QA dataset).
    assignments = list(db.scalars(
        select(MentorAssignment).where(MentorAssignment.faculty_id == faculty.id,
                                       MentorAssignment.is_active.is_(True))
        .options(selectinload(MentorAssignment.student).selectinload(Student.user),
                 selectinload(MentorAssignment.student).selectinload(Student.program),
                 selectinload(MentorAssignment.student).selectinload(Student.department))
    ))
    student_ids = [a.student_id for a in assignments]

    open_counts = dict(db.execute(
        select(MentorMeeting.student_id, func.count(MentorMeeting.id))
        .where(MentorMeeting.faculty_id == faculty.id,
               MentorMeeting.status == MeetingStatus.REQUESTED)
        .group_by(MentorMeeting.student_id)
    ).all()) if student_ids else {}

    rows = []
    for assignment in assignments:
        student = assignment.student
        if q and q.strip().lower() not in (
            f"{student.user.full_name} {student.roll_number}".lower()
        ):
            continue
        rows.append(MenteeRow(
            student_id=student.id, full_name=student.user.full_name,
            roll_number=student.roll_number, email=student.user.email,
            phone=student.user.phone,
            department_code=student.department.code if student.department else None,
            program_name=student.program.name if student.program else None,
            semester=student.current_semester, division=student.division,
            cpi=float(student.cpi) if student.cpi is not None else None,
            backlog_count=student.backlog_count,
            avatar_url=student.user.avatar_url,
            open_meetings=open_counts.get(student.id, 0),
        ))
    return sorted(rows, key=lambda r: r.roll_number)


@router.get("/meetings", response_model=list[MeetingOut])
def list_meetings(db: DbSession, user: CurrentUser,
                  faculty=Depends(get_optional_faculty),
                  status: MeetingStatus | None = None) -> list[MeetingOut]:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    conditions = []
    if student:
        conditions.append(MentorMeeting.student_id == student.id)
    if faculty:
        conditions.append(MentorMeeting.faculty_id == faculty.id)
    if not conditions:
        return []
    stmt = select(MentorMeeting).where(or_(*conditions))
    if status:
        stmt = stmt.where(MentorMeeting.status == status)
    return [_meeting_out(m) for m in db.scalars(
        stmt.order_by(MentorMeeting.created_at.desc())
    )]


@router.post("/meetings", response_model=MeetingOut, status_code=201)
def request_meeting(payload: MeetingRequest, db: DbSession,
                    user: CurrentUser) -> MeetingOut:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise PermissionDeniedError("Only students can request a mentor meeting.")

    faculty_id = payload.faculty_id
    if faculty_id is None:
        assignment = db.scalar(
            select(MentorAssignment).where(MentorAssignment.student_id == student.id,
                                           MentorAssignment.is_active.is_(True))
        )
        if assignment is None:
            raise BusinessRuleError("You do not have an assigned mentor yet.")
        faculty_id = assignment.faculty_id

    faculty = db.get(Faculty, faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")

    meeting = MentorMeeting(
        student_id=student.id, faculty_id=faculty_id, requested_by_user_id=user.id,
        title=payload.title, agenda=payload.agenda, requested_at=utcnow(),
        proposed_slot=payload.proposed_slot,
        duration_minutes=payload.duration_minutes, mode=payload.mode,
        status=MeetingStatus.REQUESTED,
        thread_key=f"mentor:{faculty_id}:student:{student.id}",
    )
    db.add(meeting)
    notifications.notify(
        db, user_id=faculty.user_id, type=NotificationType.MEETING_UPDATE,
        title="New meeting request",
        message=f"{student.user.full_name} ({student.roll_number}) requested: "
                f"{payload.title}",
        link="/mentorship",
    )
    audit.record(db, action=AuditAction.CREATE, entity_type="mentor_meeting",
                 actor=user, description=f"Requested meeting with {faculty.user.full_name}")
    db.commit()
    db.refresh(meeting)
    return _meeting_out(meeting)


@router.post("/meetings/{meeting_id}/decision", response_model=MeetingOut)
def decide_meeting(meeting_id: int, payload: MeetingDecision, db: DbSession,
                   user: CurrentUser,
                   faculty=Depends(get_optional_faculty)) -> MeetingOut:
    meeting = db.get(MentorMeeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    if faculty is None or meeting.faculty_id != faculty.id:
        if not user.has_role(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN):
            raise PermissionDeniedError("Only the mentor can respond to this request.")
    if payload.status == MeetingStatus.APPROVED and not (
        payload.scheduled_at or meeting.proposed_slot
    ):
        raise BusinessRuleError("Provide a date and time when approving a meeting.")

    if meeting.status == MeetingStatus.REQUESTED and meeting.responded_at is None:
        meeting.responded_at = dt.datetime.now(dt.timezone.utc)
    meeting.status = payload.status
    meeting.scheduled_at = payload.scheduled_at or meeting.proposed_slot
    meeting.location = payload.location or meeting.location
    meeting.outcome_notes = payload.outcome_notes or meeting.outcome_notes

    notifications.notify(
        db, user_id=meeting.student.user_id, type=NotificationType.MEETING_UPDATE,
        title=f"Meeting {payload.status.value.lower()}",
        message=(f"{meeting.title} — "
                 f"{meeting.scheduled_at:%d %b %Y, %H:%M}" if meeting.scheduled_at
                 else meeting.title),
        link="/mentorship",
    )
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="mentor_meeting",
                 entity_id=meeting.id, actor=user,
                 description=f"Meeting marked {payload.status.value}")
    db.commit()
    db.refresh(meeting)
    return _meeting_out(meeting)


# ── assignment management ─────────────────────────────────────────────────
@router.get("/assignments", response_model=list[dict])
def list_assignments(
    db: DbSession, faculty_id: int | None = None,
    _: User = Depends(require_permission(P["MENTORSHIP_MANAGE"])),
) -> list[dict]:
    stmt = select(MentorAssignment).where(MentorAssignment.is_active.is_(True))
    if faculty_id:
        stmt = stmt.where(MentorAssignment.faculty_id == faculty_id)
    return [
        {
            "id": a.id, "student_id": a.student_id,
            "student_name": a.student.user.full_name,
            "roll_number": a.student.roll_number,
            "semester": a.student.current_semester,
            "faculty_id": a.faculty_id, "faculty_name": a.faculty.user.full_name,
            "assigned_at": a.assigned_at,
        }
        for a in db.scalars(stmt.order_by(MentorAssignment.faculty_id))
    ]


@router.post("/assignments", response_model=Message)
def assign_mentor(
    student_id: int, faculty_id: int, db: DbSession,
    user: User = Depends(require_permission(P["MENTORSHIP_MANAGE"])),
) -> Message:
    student = db.get(Student, student_id)
    faculty = db.get(Faculty, faculty_id)
    if student is None or faculty is None:
        raise NotFoundError("Student or faculty member not found.")
    scope.assert_can_mentor(db, faculty)

    year = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    existing = db.scalar(select(MentorAssignment).where(
        MentorAssignment.student_id == student_id,
        MentorAssignment.academic_year_id == (year.id if year else None),
    ))
    previous_faculty_id = existing.faculty_id if existing else None
    if existing:
        existing.faculty_id = faculty_id
        existing.is_active = True
        existing.assigned_by_user_id = user.id
        existing.assigned_at = utcnow()
    else:
        db.add(MentorAssignment(
            student_id=student_id, faculty_id=faculty_id,
            academic_year_id=year.id if year else None,
            assigned_by_user_id=user.id, assigned_at=utcnow(),
        ))

    notifications.notify(
        db, user_id=student.user_id, type=NotificationType.MENTOR_ANNOUNCEMENT,
        title="Mentor assigned",
        message=f"{faculty.user.full_name} is now your faculty mentor.",
        link="/mentorship",
    )
    audit.record(
        db, action=AuditAction.MENTOR_ASSIGN if previous_faculty_id is None
        else AuditAction.MENTOR_OVERRIDE,
        entity_type="mentor_assignment", entity_id=student_id, actor=user,
        description=f"Assigned {faculty.user.full_name} as mentor for "
                    f"{student.roll_number}",
        meta={"from_faculty_id": previous_faculty_id, "to_faculty_id": faculty_id},
    )
    db.commit()
    return Message(message="Mentor assigned.")
