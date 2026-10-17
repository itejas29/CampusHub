"""Mentor–mentee, announcements and notifications."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import (
    AnnouncementCategory, AudienceType, MeetingMode, MeetingStatus, NotificationType,
    Priority,
)


def _enum(e, name: str, length: int = 40) -> SAEnum:
    return SAEnum(e, native_enum=False, length=length, name=name,
                  values_callable=lambda x: [m.value for m in x])


class MentorAssignment(PKMixin, TimestampMixin, Base):
    __tablename__ = "mentor_assignments"
    __table_args__ = (
        UniqueConstraint("student_id", "academic_year_id",
                         name="uq_mentor_assignments_student_id_academic_year_id"),
        Index("ix_mentor_assignments_faculty_active", "faculty_id", "is_active"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id", ondelete="CASCADE"), index=True, nullable=False
    )
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL")
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    student: Mapped["Student"] = relationship(lazy="joined")   # noqa: F821
    faculty: Mapped["Faculty"] = relationship(lazy="joined")   # noqa: F821


class MentorMeeting(PKMixin, TimestampMixin, Base):
    """Meeting / appointment request between a student and their mentor.

    The data model deliberately covers only request→schedule→complete; real-time
    chat is out of scope for Phase 1 (see ``thread_key`` as its future anchor).
    """

    __tablename__ = "mentor_meetings"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    agenda: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the mentor first answered the request — what response time is measured from.
    responded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_slot: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    mode: Mapped[MeetingMode] = mapped_column(
        _enum(MeetingMode, "meeting_mode"), default=MeetingMode.IN_PERSON, nullable=False
    )
    location: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[MeetingStatus] = mapped_column(
        _enum(MeetingStatus, "meeting_status"), default=MeetingStatus.REQUESTED,
        nullable=False,
    )
    outcome_notes: Mapped[str | None] = mapped_column(Text)
    # Reserved anchor for a future chat thread on this mentor relationship.
    thread_key: Mapped[str | None] = mapped_column(String(80), index=True)

    student: Mapped["Student"] = relationship(lazy="joined")   # noqa: F821
    faculty: Mapped["Faculty"] = relationship(lazy="joined")   # noqa: F821


class Announcement(PKMixin, TimestampMixin, Base):
    __tablename__ = "announcements"
    __table_args__ = (Index("ix_announcements_audience", "audience_type", "audience_ref_id"),)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[AnnouncementCategory] = mapped_column(
        _enum(AnnouncementCategory, "announcement_category"),
        default=AnnouncementCategory.GENERAL, nullable=False,
    )
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "announcement_priority"), default=Priority.NORMAL, nullable=False
    )
    audience_type: Mapped[AudienceType] = mapped_column(
        _enum(AudienceType, "audience_type"), default=AudienceType.ALL, nullable=False
    )
    # Interpretation depends on audience_type (department id, club id, role, ...).
    audience_ref_id: Mapped[int | None] = mapped_column(Integer)
    audience_ref_value: Mapped[str | None] = mapped_column(String(60))
    published_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attachment_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    link_url: Mapped[str | None] = mapped_column(String(400))


class Notification(PKMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "is_read"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        _enum(NotificationType, "notification_type"), default=NotificationType.SYSTEM,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(400))
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "notification_priority"), default=Priority.NORMAL, nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
