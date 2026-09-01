from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from slugify import slugify
from sqlalchemy import func, or_, select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.rbac import P
from app.models.community import Club, ClubMember, Event, EventInterest, EventRegistration
from app.models.enums import (
    AuditAction, EventStatus, EventType, NotificationType, RegistrationStatus, Role,
)
from app.models.identity import Student, User
from app.schemas.common import Message
from app.schemas.community import (
    EventCreate, EventOut, EventRegistrationOut, EventUpdate, InterestRequest,
)
from app.services import audit, notifications
from app.services.serializers import event_counts, event_out

router = APIRouter(prefix="/events", tags=["events"])


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _student_context(db, student: Student | None, event_ids: list[int]):
    if student is None or not event_ids:
        return {}, set()
    regs = {
        r.event_id: r.status for r in db.scalars(
            select(EventRegistration).where(
                EventRegistration.student_id == student.id,
                EventRegistration.event_id.in_(event_ids),
            )
        )
    }
    interests = {
        i.event_id for i in db.scalars(
            select(EventInterest).where(
                EventInterest.student_id == student.id,
                EventInterest.event_id.in_(event_ids),
                EventInterest.is_interested.is_(True),
            )
        )
    }
    return regs, interests


@router.get("", response_model=list[EventOut])
def list_events(
    db: DbSession, user: CurrentUser,
    scope: str = Query("upcoming", pattern="^(upcoming|past|all)$"),
    club_id: int | None = None,
    event_type: EventType | None = None,
    status: EventStatus | None = None,
    q: str | None = None,
    limit: int = Query(60, ge=1, le=200),
) -> list[EventOut]:
    stmt = select(Event)
    # Drafts are visible only to people who can manage events.
    if not user.has_role(Role.SUPER_ADMIN, Role.CLUB_ADMIN, Role.DEPARTMENT_ADMIN):
        stmt = stmt.where(Event.status.in_(
            [EventStatus.PUBLISHED, EventStatus.COMPLETED, EventStatus.CANCELLED]
        ))
    now = utcnow()
    if scope == "upcoming":
        stmt = stmt.where(Event.start_at >= now).order_by(Event.start_at)
    elif scope == "past":
        stmt = stmt.where(Event.start_at < now).order_by(Event.start_at.desc())
    else:
        stmt = stmt.order_by(Event.start_at.desc())

    if club_id:
        stmt = stmt.where(Event.club_id == club_id)
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if status:
        stmt = stmt.where(Event.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Event.title.ilike(pattern), Event.summary.ilike(pattern)))

    events = list(db.scalars(stmt.limit(limit)))
    ids = [e.id for e in events]
    regs, interests = event_counts(db, ids)
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    my_regs, my_interests = _student_context(db, student, ids)
    return [
        event_out(e, registration_count=regs.get(e.id, 0),
                  interest_count=interests.get(e.id, 0),
                  my_registration=my_regs.get(e.id),
                  am_i_interested=e.id in my_interests, now=now)
        for e in events
    ]


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: DbSession, user: CurrentUser) -> EventOut:
    event = db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Event not found.")
    regs, interests = event_counts(db, [event.id])
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    my_regs, my_interests = _student_context(db, student, [event.id])
    return event_out(event, registration_count=regs.get(event.id, 0),
                     interest_count=interests.get(event.id, 0),
                     my_registration=my_regs.get(event.id),
                     am_i_interested=event.id in my_interests)


@router.post("/{event_id}/register", response_model=EventOut)
def register(event_id: int, db: DbSession, user: CurrentUser) -> EventOut:
    event = db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Event not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise BusinessRuleError("Only students can register for events.")
    if event.status != EventStatus.PUBLISHED:
        raise BusinessRuleError("This event is not open for registration.")
    if not event.registration_required:
        raise BusinessRuleError("This event does not require registration.")

    deadline = event.registration_deadline or event.start_at
    if utcnow() > deadline:
        raise BusinessRuleError("The registration deadline has passed.")

    existing = db.scalar(select(EventRegistration).where(
        EventRegistration.event_id == event_id,
        EventRegistration.student_id == student.id,
    ))
    if existing and existing.status != RegistrationStatus.CANCELLED:
        raise BusinessRuleError("You are already registered for this event.")

    taken = db.scalar(select(func.count(EventRegistration.id)).where(
        EventRegistration.event_id == event_id,
        EventRegistration.status != RegistrationStatus.CANCELLED,
    )) or 0
    status = RegistrationStatus.REGISTERED
    if event.capacity and taken >= event.capacity:
        status = RegistrationStatus.WAITLISTED

    if existing:
        existing.status = status
        existing.registered_at = utcnow()
        existing.cancelled_at = None
    else:
        db.add(EventRegistration(event_id=event_id, student_id=student.id,
                                 status=status, registered_at=utcnow()))

    notifications.notify(
        db, user_id=user.id, type=NotificationType.REGISTRATION_CONFIRMED,
        title=("Added to waitlist" if status == RegistrationStatus.WAITLISTED
               else "Registration confirmed"),
        message=f"{event.title} — {event.start_at:%d %b %Y, %H:%M}",
        link=f"/events/{event.id}",
    )
    audit.record(db, action=AuditAction.CREATE, entity_type="event_registration",
                 entity_id=event_id, actor=user,
                 description=f"Registered for {event.title}")
    db.commit()
    return get_event(event_id, db, user)


@router.delete("/{event_id}/register", response_model=EventOut)
def cancel_registration(event_id: int, db: DbSession, user: CurrentUser) -> EventOut:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise BusinessRuleError("Only students can cancel registrations.")
    registration = db.scalar(select(EventRegistration).where(
        EventRegistration.event_id == event_id,
        EventRegistration.student_id == student.id,
        EventRegistration.status != RegistrationStatus.CANCELLED,
    ))
    if registration is None:
        raise BusinessRuleError("You are not registered for this event.")
    event = db.get(Event, event_id)
    if event and event.start_at < utcnow():
        raise BusinessRuleError("This event has already taken place.")

    registration.status = RegistrationStatus.CANCELLED
    registration.cancelled_at = utcnow()

    # Promote the first waitlisted student, if any.
    if event and event.capacity:
        waiting = db.scalar(
            select(EventRegistration)
            .where(EventRegistration.event_id == event_id,
                   EventRegistration.status == RegistrationStatus.WAITLISTED)
            .order_by(EventRegistration.registered_at).limit(1)
        )
        if waiting:
            waiting.status = RegistrationStatus.REGISTERED
            promoted = db.get(Student, waiting.student_id)
            if promoted:
                notifications.notify(
                    db, user_id=promoted.user_id,
                    type=NotificationType.REGISTRATION_CONFIRMED,
                    title="A seat opened up",
                    message=f"You are now registered for {event.title}.",
                    link=f"/events/{event.id}",
                )
    db.commit()
    return get_event(event_id, db, user)


@router.post("/{event_id}/interest", response_model=EventOut)
def toggle_interest(event_id: int, payload: InterestRequest, db: DbSession,
                    user: CurrentUser) -> EventOut:
    event = db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Event not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise BusinessRuleError("Only students can mark interest.")

    row = db.scalar(select(EventInterest).where(
        EventInterest.event_id == event_id, EventInterest.student_id == student.id
    ))
    if row is None:
        db.add(EventInterest(event_id=event_id, student_id=student.id,
                             is_interested=payload.interested))
    else:
        row.is_interested = payload.interested
    db.commit()
    return get_event(event_id, db, user)


@router.get("/{event_id}/registrations", response_model=list[EventRegistrationOut])
def list_registrations(
    event_id: int, db: DbSession,
    _: User = Depends(require_permission(P["EVENT_MANAGE"])),
) -> list[EventRegistrationOut]:
    event = db.get(Event, event_id)
    rows = db.scalars(
        select(EventRegistration).where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.registered_at)
    )
    return [
        EventRegistrationOut(
            id=r.id, event_id=r.event_id,
            event_title=event.title if event else None,
            student_id=r.student_id,
            student_name=r.student.user.full_name if r.student else None,
            roll_number=r.student.roll_number if r.student else None,
            department_code=(r.student.department.code
                             if r.student and r.student.department else None),
            semester=r.student.current_semester if r.student else None,
            email=r.student.user.email if r.student else None,
            status=r.status, registered_at=r.registered_at,
        )
        for r in rows
    ]


@router.post("", response_model=EventOut, status_code=201)
def create_event(
    payload: EventCreate, db: DbSession,
    user: User = Depends(require_permission(P["EVENT_MANAGE"])),
) -> EventOut:
    data = payload.model_dump()
    slug_base = slugify(payload.title)
    slug = slug_base
    suffix = 2
    while db.scalar(select(Event).where(Event.slug == slug)):
        slug = f"{slug_base}-{suffix}"
        suffix += 1
    event = Event(**data, slug=slug, created_by_user_id=user.id,
                  published_at=utcnow() if data["status"] == EventStatus.PUBLISHED else None)
    db.add(event)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="event", entity_id=event.id,
                 actor=user, description=f"Created event {event.title}")
    db.commit()
    db.refresh(event)
    return event_out(event)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int, payload: EventUpdate, db: DbSession,
    user: User = Depends(require_permission(P["EVENT_MANAGE"])),
) -> EventOut:
    event = db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Event not found.")
    changes = payload.model_dump(exclude_unset=True)
    was_published = event.status == EventStatus.PUBLISHED
    for field, value in changes.items():
        setattr(event, field, value)
    if "title" in changes:
        event.slug = slugify(event.title)

    newly_published = (not was_published and event.status == EventStatus.PUBLISHED)
    if newly_published:
        event.published_at = utcnow()
        club = db.get(Club, event.club_id) if event.club_id else None
        member_user_ids: list[int] = []
        if club:
            member_user_ids = list(db.scalars(
                select(Student.user_id)
                .join(ClubMember, ClubMember.student_id == Student.id)
                .where(ClubMember.club_id == club.id,
                       ClubMember.is_active.is_(True))
            ))
        notifications.notify_many(
            db, user_ids=member_user_ids, type=NotificationType.EVENT_ANNOUNCEMENT,
            title=f"New event: {event.title}",
            message=f"{event.start_at:%d %b %Y, %H:%M} · {event.venue or event.mode.value}",
            link=f"/events/{event.id}",
        )
    audit.record(
        db, action=AuditAction.PUBLISH if newly_published else AuditAction.UPDATE,
        entity_type="event", entity_id=event.id, actor=user,
        description=("Published event" if newly_published else "Updated event"),
    )
    db.commit()
    db.refresh(event)
    return event_out(event)


@router.delete("/{event_id}", response_model=Message)
def cancel_event(
    event_id: int, db: DbSession,
    user: User = Depends(require_permission(P["EVENT_MANAGE"])),
) -> Message:
    event = db.get(Event, event_id)
    if event is None:
        raise NotFoundError("Event not found.")
    event.status = EventStatus.CANCELLED
    registrations = db.scalars(select(EventRegistration).where(
        EventRegistration.event_id == event_id,
        EventRegistration.status != RegistrationStatus.CANCELLED,
    ))
    for registration in registrations:
        student = db.get(Student, registration.student_id)
        if student:
            notifications.notify(
                db, user_id=student.user_id, type=NotificationType.EVENT_ANNOUNCEMENT,
                title=f"Cancelled: {event.title}",
                message="This event has been cancelled by the organisers.",
                link=f"/events/{event.id}",
            )
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="event",
                 entity_id=event.id, actor=user, description="Cancelled event")
    db.commit()
    return Message(message="Event cancelled and attendees notified.")
