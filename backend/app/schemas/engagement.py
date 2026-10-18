from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.models.enums import (
    AnnouncementCategory, AudienceType, MeetingMode, MeetingStatus, NotificationType,
    Priority,
)
from app.schemas.common import ORMModel
from app.schemas.fields import Url, block, line, optional


class MentorProfile(BaseModel):
    faculty_id: int
    full_name: str
    designation: str
    department_name: str | None = None
    department_code: str | None = None
    cabin: str | None = None
    email: str | None = None
    phone: str | None = None
    specialization: str | None = None
    qualification: str | None = None
    avatar_url: str | None = None
    bio: str | None = None


class MenteeRow(ORMModel):
    student_id: int
    full_name: str
    roll_number: str
    email: str | None = None
    phone: str | None = None
    department_code: str | None = None
    program_name: str | None = None
    semester: int
    division: str | None = None
    cpi: float | None = None
    backlog_count: int = 0
    avatar_url: str | None = None
    open_meetings: int = 0


class MeetingOut(ORMModel):
    id: int
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    faculty_id: int
    faculty_name: str | None = None
    title: str
    agenda: str | None = None
    requested_at: dt.datetime | None = None
    proposed_slot: dt.datetime | None = None
    scheduled_at: dt.datetime | None = None
    duration_minutes: int
    mode: MeetingMode
    location: str | None = None
    status: MeetingStatus
    outcome_notes: str | None = None


class MeetingRequest(BaseModel):
    title: line(200, min_length=3)
    agenda: optional(block(2000)) = None
    proposed_slot: dt.datetime | None = None
    duration_minutes: int = Field(default=30, ge=10, le=240)
    mode: MeetingMode = MeetingMode.IN_PERSON
    faculty_id: int | None = None


class MeetingDecision(BaseModel):
    status: MeetingStatus
    scheduled_at: dt.datetime | None = None
    location: optional(line(200)) = None
    outcome_notes: optional(block(5000)) = None


class AnnouncementOut(ORMModel):
    id: int
    title: str
    body: str
    category: AnnouncementCategory
    priority: Priority
    audience_type: AudienceType
    audience_ref_id: int | None = None
    audience_label: str | None = None
    published_by_user_id: int | None = None
    published_by_name: str | None = None
    published_at: dt.datetime | None = None
    expires_at: dt.datetime | None = None
    is_pinned: bool
    is_published: bool
    link_url: str | None = None
    attachment_url: str | None = None


class AnnouncementCreate(BaseModel):
    title: line(200, min_length=3)
    body: block(10000, min_length=1)
    category: AnnouncementCategory = AnnouncementCategory.GENERAL
    priority: Priority = Priority.NORMAL
    audience_type: AudienceType = AudienceType.ALL
    audience_ref_id: int | None = None
    audience_ref_value: optional(line(60)) = None
    expires_at: dt.datetime | None = None
    is_pinned: bool = False
    is_published: bool = True
    link_url: optional(Url) = None


class AnnouncementUpdate(BaseModel):
    title: optional(line(200, min_length=3)) = None
    body: optional(block(10000, min_length=1)) = None
    category: AnnouncementCategory | None = None
    priority: Priority | None = None
    expires_at: dt.datetime | None = None
    is_pinned: bool | None = None
    is_published: bool | None = None


class NotificationOut(ORMModel):
    id: int
    type: NotificationType
    title: str
    message: str | None = None
    link: str | None = None
    priority: Priority
    is_read: bool
    read_at: dt.datetime | None = None
    created_at: dt.datetime


class NotificationSummary(BaseModel):
    unread: int
    items: list[NotificationOut] = Field(default_factory=list)


class MarkReadRequest(BaseModel):
    ids: list[int] | None = None
    all: bool = False
