"""Unified calendar feed: events, elective deadlines, mentor meetings."""
from __future__ import annotations

from types import SimpleNamespace

import datetime as dt

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.core.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.models.academics import CourseOffering, CurriculumComponent
from app.models.community import Event, EventRegistration
from app.models.engagement import MentorMeeting
from app.models.enums import EventStatus, MeetingStatus, RegistrationStatus
from app.models.identity import Faculty, Student
from app.models.internships import InternshipEnrollment, InternshipProgram
from app.services import serializers
from app.schemas.community import CalendarItem

router = APIRouter(prefix="/calendar", tags=["calendar"])

#: The longest span one request may cover. The month grid asks for six weeks and
#: the dashboard for about three months; the default is 150 days.
MAX_RANGE = dt.timedelta(days=400)


@router.get("", response_model=list[CalendarItem])
def calendar(
    db: DbSession, user: CurrentUser,
    start: dt.datetime | None = Query(None),
    end: dt.datetime | None = Query(None),
) -> list[CalendarItem]:
    now = dt.datetime.now(dt.timezone.utc)
    # A time without a zone is UTC, like everything the app stores. Left naive
    # it cannot be compared with the deadlines built below (a 500 before).
    start = _utc(start) or now - dt.timedelta(days=30)
    end = _utc(end) or now + dt.timedelta(days=120)
    if end < start:
        raise ValidationError("The end of the range is before its start.")
    if end - start > MAX_RANGE:
        raise ValidationError(
            f"Ask for at most {MAX_RANGE.days} days at a time.")
    items: list[CalendarItem] = []

    student = db.scalar(select(Student).where(Student.user_id == user.id))
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))

    # Published events
    registered_ids: set[int] = set()
    if student:
        registered_ids = set(db.scalars(
            select(EventRegistration.event_id).where(
                EventRegistration.student_id == student.id,
                EventRegistration.status != RegistrationStatus.CANCELLED,
            )
        ))
    for event in db.scalars(
        select(Event).where(Event.status == EventStatus.PUBLISHED,
                            Event.start_at.between(start, end))
        .order_by(Event.start_at)
    ):
        items.append(CalendarItem(
            id=f"event-{event.id}", title=event.title, start_at=event.start_at,
            end_at=event.end_at, kind="event",
            category=event.event_type.value,
            location=event.venue or event.mode.value,
            link=f"/events/{event.id}",
            status="Registered" if event.id in registered_ids else None,
        ))

    # Elective / registration deadlines relevant to this student's curriculum
    if student:
        rows = db.execute(
            select(CourseOffering.registration_closes_at, CurriculumComponent.title,
                   CurriculumComponent.id, CurriculumComponent.component_type)
            .join(CurriculumComponent,
                  CurriculumComponent.id == CourseOffering.curriculum_component_id)
            .where(CourseOffering.registration_closes_at.is_not(None),
                   CourseOffering.registration_closes_at.between(start, end),
                   CurriculumComponent.semester_number <= student.current_semester)
        ).all()
        seen: set[int] = set()
        for closes_at, title, component_id, component_type in rows:
            if component_id in seen:
                continue
            seen.add(component_id)
            items.append(CalendarItem(
                id=f"deadline-{component_id}",
                title=f"{title} — preference deadline",
                start_at=closes_at, kind="deadline", category="Academics",
                # Open and Core electives are separate screens.
                link=serializers.elective_path(
                    SimpleNamespace(id=component_id, component_type=component_type)),
            ))

        for enrollment in db.scalars(
            select(InternshipEnrollment).where(
                InternshipEnrollment.student_id == student.id
            )
        ):
            program: InternshipProgram = enrollment.program
            if program.end_date:
                deadline = dt.datetime.combine(
                    program.end_date, dt.time(23, 59), tzinfo=dt.timezone.utc
                )
                if start <= deadline <= end:
                    items.append(CalendarItem(
                        id=f"internship-{program.id}",
                        title=f"{program.name} — final submission",
                        start_at=deadline, kind="deadline", category="Internship",
                        link=f"/internships/{program.id}",
                    ))

    # Mentor meetings
    meeting_filter = []
    if student:
        meeting_filter.append(MentorMeeting.student_id == student.id)
    if faculty:
        meeting_filter.append(MentorMeeting.faculty_id == faculty.id)
    if meeting_filter:
        for meeting in db.scalars(
            select(MentorMeeting).where(
                or_(*meeting_filter),
                MentorMeeting.status.in_([MeetingStatus.APPROVED,
                                          MeetingStatus.RESCHEDULED]),
                MentorMeeting.scheduled_at.is_not(None),
                MentorMeeting.scheduled_at.between(start, end),
            )
        ):
            items.append(CalendarItem(
                id=f"meeting-{meeting.id}", title=meeting.title,
                start_at=meeting.scheduled_at,
                end_at=meeting.scheduled_at + dt.timedelta(
                    minutes=meeting.duration_minutes
                ),
                kind="meeting", category="Mentorship",
                location=meeting.location or meeting.mode.value,
                link="/mentorship", status=meeting.status.value,
            ))

    # SQLite returns these columns without their zone; the app stores UTC.
    # Unzoned, they cannot be sorted beside the deadlines built above, and a
    # browser would read them as local time.
    for item in items:
        item.start_at = _utc(item.start_at)
        item.end_at = _utc(item.end_at)
    return sorted(items, key=lambda i: i.start_at)


def _utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=dt.timezone.utc)
