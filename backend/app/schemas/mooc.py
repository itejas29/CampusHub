"""NPTEL / NCC rounds — what the coordinator and the student send and see."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.models.enums import (
    MoocOption, MoocOutcome, MoocRoundStatus, MoocStatus, VerificationStatus,
)
from app.schemas.fields import Url, block, identifier, line, optional


class MoocCourseIn(BaseModel):
    """One course of the approved list, as the department's sheet gives it."""

    code: identifier(30)
    title: line(200)
    weeks: int = Field(ge=1, le=52)
    url: optional(Url) = None
    discipline: optional(line(300)) = None
    instructors: optional(line(300)) = None
    institute: optional(line(200)) = None
    coordinating_institute: optional(line(200)) = None


class MoocCourseOut(BaseModel):
    course_id: int
    code: str
    title: str
    weeks: int | None = None
    credits: float | None = None
    url: str | None = None
    discipline: str | None = None
    instructors: str | None = None
    institute: str | None = None
    coordinating_institute: str | None = None
    #: How many students chose it (coordinator views only).
    chosen_count: int | None = None


class MoocRoundIn(BaseModel):
    title: line(180)
    message: optional(block(4000)) = None
    curriculum_component_id: int
    eligible_semesters: list[int] = Field(default_factory=list, max_length=8)
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    platform_deadline: dt.date | None = None
    #: Start from another round's approved list (the previous semester's).
    copy_list_from: int | None = None


class MoocRoundUpdate(BaseModel):
    title: optional(line(180)) = None
    message: optional(block(4000)) = None
    eligible_semesters: list[int] | None = Field(default=None, max_length=8)
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    platform_deadline: dt.date | None = None


class MoocRoundOut(BaseModel):
    id: int
    title: str
    message: str | None = None
    status: MoocRoundStatus
    department_id: int | None = None
    curriculum_component_id: int
    component_code: str | None = None
    component_title: str | None = None
    component_semester: int | None = None
    eligible_semesters: list[int] = Field(default_factory=list)
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    platform_deadline: dt.date | None = None
    locked_at: dt.datetime | None = None
    closed_at: dt.datetime | None = None
    is_open: bool = False
    is_past_deadline: bool = False
    course_count: int = 0
    covered_count: int = 0
    carry_over_count: int = 0
    chosen_count: int = 0
    nptel_count: int = 0
    ncc_count: int = 0
    certificates_waiting: int = 0
    verified_count: int = 0
    failed_count: int = 0
    can_manage: bool = False


class MoocChoiceIn(BaseModel):
    option: MoocOption
    course_id: int | None = None


class MoocChoiceOut(BaseModel):
    registration_id: int
    option: MoocOption
    course: MoocCourseOut | None = None
    status: MoocStatus
    verification_status: VerificationStatus
    certificate_url: str | None = None
    remarks: str | None = None
    updated_at: dt.datetime | None = None


class StudentMoocRoundOut(BaseModel):
    """The round as one student sees it."""

    id: int
    title: str
    message: str | None = None
    status: MoocRoundStatus
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    platform_deadline: dt.date | None = None
    can_choose: bool
    reason: str | None = None
    #: Choosing again: the slot was not cleared in an earlier semester.
    carry_over: bool = False
    courses: list[MoocCourseOut] = Field(default_factory=list)
    choice: MoocChoiceOut | None = None
    #: May submit the certificate, or report a fail, now.
    can_submit_result: bool = False


class StudentMoocStanding(BaseModel):
    """The student's slot overall: their live round, and where they stand."""

    component_id: int | None = None
    component_code: str | None = None
    component_title: str | None = None
    component_semester: int | None = None
    standing: MoocOutcome | None = None
    round: StudentMoocRoundOut | None = None


class MoocRosterRow(BaseModel):
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    semester: int | None = None
    carry_over: bool = False
    registration_id: int | None = None
    option: MoocOption | None = None
    course_code: str | None = None
    course_title: str | None = None
    status: MoocStatus | None = None
    verification_status: VerificationStatus | None = None
    certificate_url: str | None = None


class MoocImportResult(BaseModel):
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    already_listed: list[str] = Field(default_factory=list)
    skipped: list[dict] = Field(default_factory=list)


class MoocCloseRequest(BaseModel):
    #: Close even though certificates still wait for verification.
    force: bool = False


class MoocCloseResult(BaseModel):
    cleared: int
    carried_over: int
    backlog: int
    awaiting_verification: int


class MoocRemindResult(BaseModel):
    notified: int
