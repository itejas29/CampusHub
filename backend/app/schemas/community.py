from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import (
    ClubCategory, ClubMemberRole, EventMode, EventStatus, EventType, RegistrationStatus,
)
from app.schemas.common import ORMModel
from app.schemas.fields import Url, block, line, optional


class ClubMemberOut(ORMModel):
    id: int
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    avatar_url: str | None = None
    role: ClubMemberRole
    position_title: str | None = None
    joined_at: dt.datetime | None = None


class ClubOut(ORMModel):
    id: int
    name: str
    slug: str
    category: ClubCategory
    tagline: str | None = None
    description: str | None = None
    logo_url: str | None = None
    instagram_url: str | None = None
    linkedin_url: str | None = None
    website_url: str | None = None
    email: str | None = None
    founded_year: int | None = None
    faculty_advisor_id: int | None = None
    faculty_advisor_name: str | None = None
    is_active: bool
    member_count: int = 0
    upcoming_event_count: int = 0
    head_name: str | None = None
    is_member: bool | None = None


class ClubDetail(ClubOut):
    members: list[ClubMemberOut] = Field(default_factory=list)
    events: list["EventOut"] = Field(default_factory=list)


class ClubCreate(BaseModel):
    name: line(150, min_length=2)
    category: ClubCategory = ClubCategory.TECHNICAL
    tagline: optional(line(200)) = None
    description: optional(block(5000)) = None
    instagram_url: optional(Url) = None
    linkedin_url: optional(Url) = None
    website_url: optional(Url) = None
    email: optional(EmailStr) = None
    founded_year: int | None = Field(default=None, ge=1950, le=2100)
    faculty_advisor_id: int | None = None


class ClubUpdate(BaseModel):
    name: optional(line(150, min_length=2)) = None
    category: ClubCategory | None = None
    tagline: optional(line(200)) = None
    description: optional(block(5000)) = None
    instagram_url: optional(Url) = None
    linkedin_url: optional(Url) = None
    website_url: optional(Url) = None
    email: optional(EmailStr) = None
    faculty_advisor_id: int | None = None
    is_active: bool | None = None


class EventOut(ORMModel):
    id: int
    title: str
    slug: str
    event_type: EventType
    summary: str | None = None
    description: str | None = None
    start_at: dt.datetime
    end_at: dt.datetime | None = None
    venue: str | None = None
    mode: EventMode
    meeting_url: str | None = None
    registration_required: bool
    registration_deadline: dt.datetime | None = None
    capacity: int | None = None
    poster_url: str | None = None
    external_url: str | None = None
    speaker: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: EventStatus
    club_id: int | None = None
    club_name: str | None = None
    club_slug: str | None = None
    registration_count: int = 0
    interest_count: int = 0
    seats_available: int | None = None
    is_full: bool = False
    registration_open: bool = True
    # Student context
    my_registration_status: RegistrationStatus | None = None
    am_i_interested: bool = False


class EventCreate(BaseModel):
    title: line(200, min_length=3)
    club_id: int | None = None
    event_type: EventType = EventType.EVENT
    summary: optional(line(300)) = None
    description: optional(block(5000)) = None
    start_at: dt.datetime
    end_at: dt.datetime | None = None
    venue: optional(line(180)) = None
    mode: EventMode = EventMode.OFFLINE
    meeting_url: optional(Url) = None
    registration_required: bool = True
    registration_deadline: dt.datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    poster_url: optional(Url) = None
    external_url: optional(Url) = None
    speaker: optional(line(200)) = None
    tags: list[line(40)] = Field(default_factory=list, max_length=15)
    status: EventStatus = EventStatus.DRAFT


class EventUpdate(BaseModel):
    title: optional(line(200, min_length=3)) = None
    event_type: EventType | None = None
    summary: optional(line(300)) = None
    description: optional(block(5000)) = None
    start_at: dt.datetime | None = None
    end_at: dt.datetime | None = None
    venue: optional(line(180)) = None
    mode: EventMode | None = None
    meeting_url: optional(Url) = None
    registration_required: bool | None = None
    registration_deadline: dt.datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    poster_url: optional(Url) = None
    external_url: optional(Url) = None
    speaker: optional(line(200)) = None
    tags: list[line(40)] | None = Field(default=None, max_length=15)
    status: EventStatus | None = None


class EventRegistrationOut(ORMModel):
    id: int
    event_id: int
    event_title: str | None = None
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    department_code: str | None = None
    semester: int | None = None
    email: str | None = None
    status: RegistrationStatus
    registered_at: dt.datetime | None = None


class InterestRequest(BaseModel):
    interested: bool = True


class CalendarItem(BaseModel):
    id: str
    title: str
    start_at: dt.datetime
    end_at: dt.datetime | None = None
    all_day: bool = False
    kind: str  # event | deadline | meeting | academic
    category: str | None = None
    location: str | None = None
    link: str | None = None
    status: str | None = None


ClubDetail.model_rebuild()
