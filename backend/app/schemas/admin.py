from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StatCard(BaseModel):
    key: str
    label: str
    value: int | float
    hint: str | None = None
    trend_label: str | None = None
    link: str | None = None


class BreakdownItem(BaseModel):
    label: str
    value: int
    total: int | None = None


class ActivityItem(BaseModel):
    id: int
    actor: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    description: str | None = None
    created_at: dt.datetime


class AdminDashboard(BaseModel):
    stats: list[StatCard]
    students_by_semester: list[BreakdownItem] = Field(default_factory=list)
    internship_progress: list[BreakdownItem] = Field(default_factory=list)
    pending_actions: list[StatCard] = Field(default_factory=list)
    recent_activity: list[ActivityItem] = Field(default_factory=list)
    upcoming_events: list[dict] = Field(default_factory=list)


class DeadlineItem(BaseModel):
    title: str
    due_at: dt.datetime | None = None
    context: str | None = None
    link: str | None = None
    kind: str = "deadline"


class ProgressItem(BaseModel):
    label: str
    completed: int
    total: int
    link: str | None = None


class StudentDashboard(BaseModel):
    stats: list[StatCard]
    curriculum_semester: dict | None = None
    allocated_electives: list[dict] = Field(default_factory=list)
    action_items: list[DeadlineItem] = Field(default_factory=list)
    progress: list[ProgressItem] = Field(default_factory=list)
    upcoming_events: list[dict] = Field(default_factory=list)
    announcements: list[dict] = Field(default_factory=list)
    mentor: dict | None = None


class FacultyDashboard(BaseModel):
    stats: list[StatCard]
    pending_reviews: list[dict] = Field(default_factory=list)
    mentees_preview: list[dict] = Field(default_factory=list)
    internship_groups: list[dict] = Field(default_factory=list)
    upcoming_meetings: list[dict] = Field(default_factory=list)
    announcements: list[dict] = Field(default_factory=list)
    #: One entry per module this faculty member coordinates, each carrying
    #: counts queried for that exact scope — never figures typed into the UI.
    portfolios: list[dict] = Field(default_factory=list)


class HodDashboard(BaseModel):
    """A department head's view: who runs each module, and what is in motion."""

    department: dict
    #: Who heads it — the title when the registrar opens this view.
    hod_name: str | None = None
    stats: list[StatCard]
    #: One row per coordination domain — its coordinators, mentors, or the gap.

    modules: list[dict] = Field(default_factory=list)
    #: Registration rounds belonging to the department, newest first.
    rounds: list[dict] = Field(default_factory=list)
    announcements: list[dict] = Field(default_factory=list)


class AuditLogOut(ORMModel):
    id: int
    actor_user_id: int | None = None
    actor_label: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    description: str | None = None
    meta: dict = Field(default_factory=dict)
    ip_address: str | None = None
    created_at: dt.datetime


class FileOut(ORMModel):
    id: int
    filename: str
    original_name: str
    content_type: str
    size_bytes: int
    category: str
    url: str | None = None
    created_at: dt.datetime
