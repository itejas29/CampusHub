from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from slugify import slugify
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.rbac import P
from app.models.community import Club, ClubMember, Event
from app.models.enums import AuditAction, ClubMemberRole, EventStatus
from app.models.identity import Student, User
from app.schemas.common import Message
from app.schemas.community import (
    ClubCreate, ClubDetail, ClubMemberOut, ClubOut, ClubUpdate,
)
from app.services import audit
from app.services.serializers import club_out, event_counts, event_out

router = APIRouter(prefix="/clubs", tags=["clubs"])


def _member_counts(db, club_ids: list[int]) -> dict[int, int]:
    if not club_ids:
        return {}
    return dict(db.execute(
        select(ClubMember.club_id, func.count(ClubMember.id))
        .where(ClubMember.club_id.in_(club_ids), ClubMember.is_active.is_(True))
        .group_by(ClubMember.club_id)
    ).all())


def _upcoming_counts(db, club_ids: list[int]) -> dict[int, int]:
    if not club_ids:
        return {}
    return dict(db.execute(
        select(Event.club_id, func.count(Event.id))
        .where(Event.club_id.in_(club_ids), Event.status == EventStatus.PUBLISHED,
               Event.start_at >= dt.datetime.now(dt.timezone.utc))
        .group_by(Event.club_id)
    ).all())


@router.get("", response_model=list[ClubOut])
def list_clubs(db: DbSession, user: CurrentUser, category: str | None = Query(None),
               q: str | None = Query(None)) -> list[ClubOut]:
    stmt = select(Club).where(Club.is_active.is_(True)).order_by(Club.name)
    if category:
        stmt = stmt.where(Club.category == category)
    if q:
        stmt = stmt.where(Club.name.ilike(f"%{q.strip()}%"))
    clubs = list(db.scalars(stmt))
    ids = [c.id for c in clubs]
    members = _member_counts(db, ids)
    upcoming = _upcoming_counts(db, ids)

    student = db.scalar(select(Student).where(Student.user_id == user.id))
    my_clubs: set[int] = set()
    if student:
        my_clubs = {
            row for row in db.scalars(
                select(ClubMember.club_id).where(ClubMember.student_id == student.id,
                                                 ClubMember.is_active.is_(True))
            )
        }
    heads = {
        row[0]: row[1] for row in db.execute(
            select(ClubMember.club_id, Student.id)
            .join(Student, Student.id == ClubMember.student_id)
            .where(ClubMember.club_id.in_(ids or [0]),
                   ClubMember.role == ClubMemberRole.HEAD)
        ).all()
    }
    head_names = {}
    for club_id, student_id in heads.items():
        s = db.get(Student, student_id)
        if s:
            head_names[club_id] = s.user.full_name

    return [
        club_out(c, member_count=members.get(c.id, 0),
                 upcoming=upcoming.get(c.id, 0), head_name=head_names.get(c.id),
                 is_member=(c.id in my_clubs) if student else None)
        for c in clubs
    ]


@router.get("/{slug}", response_model=ClubDetail)
def get_club(slug: str, db: DbSession, user: CurrentUser) -> ClubDetail:
    club = db.scalar(select(Club).where(Club.slug == slug))
    if club is None:
        club = db.get(Club, slug) if slug.isdigit() else None
    if club is None:
        raise NotFoundError("Club not found.")

    members = list(db.scalars(
        select(ClubMember).where(ClubMember.club_id == club.id,
                                 ClubMember.is_active.is_(True))
        .order_by(ClubMember.role.desc(), ClubMember.id)
    ))
    events = list(db.scalars(
        select(Event).where(Event.club_id == club.id,
                            Event.status == EventStatus.PUBLISHED)
        .order_by(Event.start_at.desc()).limit(12)
    ))
    regs, interests = event_counts(db, [e.id for e in events])
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    head = next((m for m in members if m.role == ClubMemberRole.HEAD), None)

    base = club_out(
        club, member_count=len(members),
        upcoming=sum(1 for e in events if e.start_at >= dt.datetime.now(dt.timezone.utc)),
        head_name=head.student.user.full_name if head else None,
        is_member=(any(m.student_id == student.id for m in members)
                   if student else None),
    )
    return ClubDetail(
        **base.model_dump(),
        members=[
            ClubMemberOut(
                id=m.id, student_id=m.student_id,
                student_name=m.student.user.full_name if m.student else None,
                roll_number=m.student.roll_number if m.student else None,
                avatar_url=m.student.user.avatar_url if m.student else None,
                role=m.role, position_title=m.position_title, joined_at=m.joined_at,
            )
            for m in members
        ],
        events=[
            event_out(e, registration_count=regs.get(e.id, 0),
                      interest_count=interests.get(e.id, 0))
            for e in events
        ],
    )


@router.post("/{club_id}/join", response_model=Message)
def join_club(club_id: int, db: DbSession, user: CurrentUser) -> Message:
    club = db.get(Club, club_id)
    if club is None or not club.is_active:
        raise NotFoundError("Club not found.")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise BusinessRuleError("Only students can join clubs.")

    membership = db.scalar(select(ClubMember).where(
        ClubMember.club_id == club_id, ClubMember.student_id == student.id
    ))
    if membership and membership.is_active:
        raise BusinessRuleError("You are already a member of this club.")
    if membership:
        membership.is_active = True
    else:
        db.add(ClubMember(club_id=club_id, student_id=student.id,
                          role=ClubMemberRole.MEMBER,
                          joined_at=dt.datetime.now(dt.timezone.utc)))
    audit.record(db, action=AuditAction.CREATE, entity_type="club_member",
                 entity_id=club_id, actor=user, description=f"Joined {club.name}")
    db.commit()
    return Message(message=f"You have joined {club.name}.")


@router.delete("/{club_id}/leave", response_model=Message)
def leave_club(club_id: int, db: DbSession, user: CurrentUser) -> Message:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise BusinessRuleError("Only students can leave clubs.")
    membership = db.scalar(select(ClubMember).where(
        ClubMember.club_id == club_id, ClubMember.student_id == student.id,
        ClubMember.is_active.is_(True),
    ))
    if membership is None:
        raise BusinessRuleError("You are not a member of this club.")
    membership.is_active = False
    db.commit()
    return Message(message="Membership removed.")


@router.post("", response_model=ClubOut, status_code=201)
def create_club(
    payload: ClubCreate, db: DbSession,
    user: User = Depends(require_permission(P["CLUB_MANAGE"])),
) -> ClubOut:
    club = Club(**payload.model_dump(), slug=slugify(payload.name))
    db.add(club)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="club", entity_id=club.id,
                 actor=user, description=f"Created club {club.name}")
    db.commit()
    db.refresh(club)
    return club_out(club)


@router.patch("/{club_id}", response_model=ClubOut)
def update_club(
    club_id: int, payload: ClubUpdate, db: DbSession,
    user: User = Depends(require_permission(P["CLUB_MANAGE"])),
) -> ClubOut:
    club = db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Club not found.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(club, field, value)
    if "name" in changes:
        club.slug = slugify(club.name)
    audit.record(db, action=AuditAction.UPDATE, entity_type="club", entity_id=club.id,
                 actor=user, description=f"Updated club {club.name}")
    db.commit()
    db.refresh(club)
    return club_out(club)
