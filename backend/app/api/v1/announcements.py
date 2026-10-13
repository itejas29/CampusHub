from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.errors import NotFoundError
from app.core.rbac import P
from app.models.engagement import Announcement, MentorAssignment
from app.models.enums import AudienceType, AuditAction, NotificationType, Role
from app.models.identity import Faculty, Student, User
from app.schemas.common import Message
from app.schemas.engagement import (
    AnnouncementCreate, AnnouncementOut, AnnouncementUpdate,
)
from app.services import announcements as announcement_audience
from app.services import audit, notifications
from app.services.serializers import file_url

router = APIRouter(prefix="/announcements", tags=["announcements"])


def _out(db, announcement: Announcement) -> AnnouncementOut:
    publisher = (db.get(User, announcement.published_by_user_id)
                 if announcement.published_by_user_id else None)
    labels = {
        AudienceType.ALL: "Everyone",
        AudienceType.MENTEES: "My mentees",
        AudienceType.ROLE: announcement.audience_ref_value or "Role",
    }
    return AnnouncementOut(
        id=announcement.id, title=announcement.title, body=announcement.body,
        category=announcement.category, priority=announcement.priority,
        audience_type=announcement.audience_type,
        audience_ref_id=announcement.audience_ref_id,
        audience_label=labels.get(announcement.audience_type,
                                  announcement.audience_type.value.title()),
        published_by_user_id=announcement.published_by_user_id,
        published_by_name=publisher.full_name if publisher else None,
        published_at=announcement.published_at, expires_at=announcement.expires_at,
        is_pinned=announcement.is_pinned, is_published=announcement.is_published,
        link_url=announcement.link_url,
        attachment_url=file_url(db, announcement.attachment_file_id),
    )


@router.get("", response_model=list[AnnouncementOut])
def list_announcements(db: DbSession, user: CurrentUser,
                       limit: int = Query(50, ge=1, le=200)) -> list[AnnouncementOut]:
    stmt = announcement_audience.visible_to(db, user).order_by(
        Announcement.is_pinned.desc(), Announcement.published_at.desc()
    ).limit(limit)
    return [_out(db, a) for a in db.scalars(stmt)]


@router.get("/manage", response_model=list[AnnouncementOut])
def list_all(
    db: DbSession,
    user: User = Depends(require_permission(P["ANNOUNCEMENT_PUBLISH"])),
) -> list[AnnouncementOut]:
    stmt = select(Announcement).order_by(Announcement.created_at.desc())
    if not user.has_role(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN):
        stmt = stmt.where(Announcement.published_by_user_id == user.id)
    return [_out(db, a) for a in db.scalars(stmt.limit(200))]


@router.post("", response_model=AnnouncementOut, status_code=201)
def create_announcement(
    payload: AnnouncementCreate, db: DbSession,
    user: User = Depends(require_permission(P["ANNOUNCEMENT_PUBLISH"])),
) -> AnnouncementOut:
    data = payload.model_dump()
    # A faculty member posting to MENTEES always scopes to their own mentees.
    if data["audience_type"] == AudienceType.MENTEES:
        faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
        if faculty is None:
            from app.core.errors import PermissionDeniedError

            raise PermissionDeniedError("Only faculty can post to their mentees.")
        data["audience_ref_id"] = faculty.id

    announcement = Announcement(
        **data, published_by_user_id=user.id,
        published_at=dt.datetime.now(dt.timezone.utc) if data["is_published"] else None,
    )
    db.add(announcement)
    db.flush()

    if announcement.is_published:
        _fan_out(db, announcement)
    audit.record(db, action=AuditAction.PUBLISH, entity_type="announcement",
                 entity_id=announcement.id, actor=user,
                 description=f"Published announcement '{announcement.title}'")
    db.commit()
    db.refresh(announcement)
    return _out(db, announcement)


def _fan_out(db, announcement: Announcement) -> None:
    """Create in-app notifications for the targeted audience."""
    stmt = select(User.id).where(User.is_active.is_(True))
    audience = announcement.audience_type

    if audience == AudienceType.DEPARTMENT:
        stmt = stmt.join(Student, Student.user_id == User.id).where(
            Student.department_id == announcement.audience_ref_id
        )
    elif audience == AudienceType.PROGRAM:
        stmt = stmt.join(Student, Student.user_id == User.id).where(
            Student.program_id == announcement.audience_ref_id
        )
    elif audience == AudienceType.SEMESTER:
        stmt = stmt.join(Student, Student.user_id == User.id).where(
            Student.current_semester == announcement.audience_ref_id
        )
    elif audience == AudienceType.MENTEES:
        stmt = (
            stmt.join(Student, Student.user_id == User.id)
            .join(MentorAssignment, MentorAssignment.student_id == Student.id)
            .where(MentorAssignment.faculty_id == announcement.audience_ref_id,
                   MentorAssignment.is_active.is_(True))
        )
    elif audience not in (AudienceType.ALL, AudienceType.ROLE):
        return  # Club / internship audiences fan out from their own modules.

    user_ids = list(db.scalars(stmt))
    notifications.notify_many(
        db, user_ids=user_ids,
        type=(NotificationType.MENTOR_ANNOUNCEMENT if audience == AudienceType.MENTEES
              else NotificationType.SYSTEM),
        title=announcement.title,
        message=announcement.body[:180],
        link="/announcements",
    )


@router.patch("/{announcement_id}", response_model=AnnouncementOut)
def update_announcement(
    announcement_id: int, payload: AnnouncementUpdate, db: DbSession,
    user: User = Depends(require_permission(P["ANNOUNCEMENT_PUBLISH"])),
) -> AnnouncementOut:
    announcement = db.get(Announcement, announcement_id)
    if announcement is None:
        raise NotFoundError("Announcement not found.")
    if (announcement.published_by_user_id != user.id
            and not user.has_role(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN)):
        from app.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You can only edit announcements you published.")

    was_published = announcement.is_published
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(announcement, field, value)
    if not was_published and announcement.is_published:
        announcement.published_at = dt.datetime.now(dt.timezone.utc)
        _fan_out(db, announcement)
    audit.record(db, action=AuditAction.UPDATE, entity_type="announcement",
                 entity_id=announcement.id, actor=user, description="Updated announcement")
    db.commit()
    db.refresh(announcement)
    return _out(db, announcement)


@router.delete("/{announcement_id}", response_model=Message)
def delete_announcement(
    announcement_id: int, db: DbSession,
    user: User = Depends(require_permission(P["ANNOUNCEMENT_PUBLISH"])),
) -> Message:
    announcement = db.get(Announcement, announcement_id)
    if announcement is None:
        raise NotFoundError("Announcement not found.")
    db.delete(announcement)
    audit.record(db, action=AuditAction.DELETE, entity_type="announcement",
                 entity_id=announcement_id, actor=user, description="Deleted announcement")
    db.commit()
    return Message(message="Announcement removed.")
