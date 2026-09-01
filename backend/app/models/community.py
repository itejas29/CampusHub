"""Clubs, events, registrations and interest tracking."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import (
    ClubCategory, ClubMemberRole, EventMode, EventStatus, EventType, RegistrationStatus,
)


def _enum(e, name: str, length: int = 40) -> SAEnum:
    return SAEnum(e, native_enum=False, length=length, name=name,
                  values_callable=lambda x: [m.value for m in x])


class Club(PKMixin, TimestampMixin, Base):
    __tablename__ = "clubs"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    category: Mapped[ClubCategory] = mapped_column(
        _enum(ClubCategory, "club_category"), default=ClubCategory.TECHNICAL, nullable=False
    )
    tagline: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    cover_url: Mapped[str | None] = mapped_column(String(500))
    instagram_url: Mapped[str | None] = mapped_column(String(300))
    linkedin_url: Mapped[str | None] = mapped_column(String(300))
    website_url: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(255))
    faculty_advisor_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL")
    )
    founded_year: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    faculty_advisor: Mapped["Faculty | None"] = relationship(lazy="joined")  # noqa: F821
    members: Mapped[list["ClubMember"]] = relationship(
        back_populates="club", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(back_populates="club")


class ClubMember(PKMixin, TimestampMixin, Base):
    __tablename__ = "club_members"
    __table_args__ = (
        UniqueConstraint("club_id", "student_id", name="uq_club_members_club_id_student_id"),
    )

    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[ClubMemberRole] = mapped_column(
        _enum(ClubMemberRole, "club_member_role"), default=ClubMemberRole.MEMBER,
        nullable=False,
    )
    position_title: Mapped[str | None] = mapped_column(String(120))
    joined_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    club: Mapped["Club"] = relationship(back_populates="members")
    student: Mapped["Student"] = relationship(lazy="joined")  # noqa: F821


class Event(PKMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_status_start", "status", "start_at"),)

    club_id: Mapped[int | None] = mapped_column(
        ForeignKey("clubs.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True, nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        _enum(EventType, "event_type"), default=EventType.EVENT, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(String(300))
    start_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(String(180))
    mode: Mapped[EventMode] = mapped_column(
        _enum(EventMode, "event_mode"), default=EventMode.OFFLINE, nullable=False
    )
    meeting_url: Mapped[str | None] = mapped_column(String(400))
    registration_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    registration_deadline: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int | None] = mapped_column(Integer)
    poster_url: Mapped[str | None] = mapped_column(String(500))
    poster_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    external_url: Mapped[str | None] = mapped_column(String(400))
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[EventStatus] = mapped_column(
        _enum(EventStatus, "event_status"), default=EventStatus.DRAFT, nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    club: Mapped["Club | None"] = relationship(back_populates="events", lazy="joined")
    registrations: Mapped[list["EventRegistration"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventRegistration(PKMixin, TimestampMixin, Base):
    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "student_id",
                         name="uq_event_registrations_event_id_student_id"),
    )

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        _enum(RegistrationStatus, "registration_status"),
        default=RegistrationStatus.REGISTERED, nullable=False,
    )
    registered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    event: Mapped["Event"] = relationship(back_populates="registrations")
    student: Mapped["Student"] = relationship(lazy="joined")  # noqa: F821


class EventInterest(PKMixin, TimestampMixin, Base):
    """Lightweight "Interested" signal, used for demand forecasting."""

    __tablename__ = "event_interests"
    __table_args__ = (
        UniqueConstraint("event_id", "student_id",
                         name="uq_event_interests_event_id_student_id"),
    )

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    is_interested: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
