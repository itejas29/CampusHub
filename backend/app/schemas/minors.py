from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.models.enums import MinorApplicationStatus, MinorEnrollmentStatus
from app.schemas.common import ORMModel


class MinorCourseOut(ORMModel):
    id: int
    course_id: int
    course_code: str | None = None
    course_title: str | None = None
    credits: float | None = None
    sequence: int
    semester_offset: int
    is_mandatory: bool
    is_completed: bool = False


class MinorProgramOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None = None
    department_id: int
    department_name: str | None = None
    total_credits: float
    capacity: int
    seats_filled: int
    seats_available: int
    eligible_from_semester: int
    min_cpi: float | None = None
    max_backlogs: int | None = None
    allocation_strategy: str
    application_opens_at: dt.datetime | None = None
    application_closes_at: dt.datetime | None = None
    coordinator_name: str | None = None
    is_active: bool
    courses: list[MinorCourseOut] = Field(default_factory=list)
    #: Whether the person asking coordinates this minor.
    can_manage: bool = False
    #: The semesters in which students apply (by default the first eligible one).
    application_semesters: list[int] = Field(default_factory=list)
    #: Fee per semester, set by the coordinator; empty until announced.
    fees: list[dict] = Field(default_factory=list)
    # Published rules, read from the programme's `rules` JSON. These were
    # already recorded against the official source but never reached the client,
    # so a student could not see the conditions they were signing up to.
    continuation_rule: str | None = None
    rule_source: str | None = None
    rule_source_url: str | None = None
    offered_semesters: list[int] = Field(default_factory=list)
    # Whether the registration round is currently accepting applications.
    window_open: bool = True
    # Student context
    is_eligible: bool | None = None
    eligibility_notes: list[str] = Field(default_factory=list)
    my_application_status: MinorApplicationStatus | None = None


class MinorProgramCreate(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=180)
    department_id: int
    description: str | None = None
    total_credits: float = Field(default=18, ge=0, le=100)
    capacity: int = Field(default=30, ge=1, le=1000)
    eligible_from_semester: int = Field(default=3, ge=1, le=12)
    min_cpi: float | None = Field(default=None, ge=0, le=10)
    max_backlogs: int | None = Field(default=None, ge=0)
    allocation_strategy: str = "manual"
    application_opens_at: dt.datetime | None = None
    application_closes_at: dt.datetime | None = None
    coordinator_faculty_id: int | None = None


class MinorProgramUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    total_credits: float | None = Field(default=None, ge=0, le=100)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    eligible_from_semester: int | None = Field(default=None, ge=1, le=12)
    min_cpi: float | None = Field(default=None, ge=0, le=10)
    max_backlogs: int | None = Field(default=None, ge=0)
    allocation_strategy: str | None = None
    application_opens_at: dt.datetime | None = None
    application_closes_at: dt.datetime | None = None
    is_active: bool | None = None


class MinorApplicationOut(ORMModel):
    id: int
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    minor_program_id: int
    minor_name: str | None = None
    minor_department: str | None = None
    preference_order: int
    status: MinorApplicationStatus
    cpi_at_application: float | None = None
    backlogs_at_application: int | None = None
    semester_at_application: int | None = None
    motivation: str | None = None
    allocation_score: float | None = None
    submitted_at: dt.datetime | None = None
    decided_at: dt.datetime | None = None
    remarks: str | None = None


class MinorApplyRequest(BaseModel):
    preferences: list[int] = Field(min_length=1, max_length=5,
                                   description="Minor program ids, most preferred first")
    motivation: str | None = Field(default=None, max_length=2000)


class MinorDecisionRequest(BaseModel):
    status: MinorApplicationStatus
    remarks: str | None = None


class MinorEnrollmentOut(ORMModel):
    id: int
    minor_program_id: int
    minor_name: str | None = None
    minor_department: str | None = None
    status: MinorEnrollmentStatus
    started_semester: int | None = None
    credits_completed: float
    total_credits: float | None = None
    progress_percent: int = 0
    courses: list[MinorCourseOut] = Field(default_factory=list)
    #: Semester by semester: courses with this student's results, and the fee.
    plan: list[dict] = Field(default_factory=list)
    current_semester: int | None = None


class MinorResultIn(BaseModel):
    enrollment_id: int
    marks: float | None = Field(default=None, ge=0, le=100)
    grade: str | None = Field(default=None, max_length=4)
    status: str = "IN_PROGRESS"


class MinorResultsIn(BaseModel):
    results: list[MinorResultIn] = Field(min_length=1, max_length=500)


class MinorFeeIn(BaseModel):
    semester: int = Field(ge=1, le=10)
    amount: float = Field(ge=0, le=10_000_000)
    due_on: dt.date | None = None
    note: str | None = Field(default=None, max_length=300)


class MinorFeesIn(BaseModel):
    fees: list[MinorFeeIn] = Field(default_factory=list, max_length=10)


class MinorPaymentIn(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    reference: str | None = Field(default=None, max_length=80)
    paid_on: dt.date | None = None


class MinorWorkspace(BaseModel):
    is_eligible: bool
    eligibility_notes: list[str] = Field(default_factory=list)
    programs: list[MinorProgramOut] = Field(default_factory=list)
    applications: list[MinorApplicationOut] = Field(default_factory=list)
    enrollment: MinorEnrollmentOut | None = None


class RankedApplicantOut(BaseModel):
    """One applicant's position in a minor allocation round."""
    application_id: int
    student_id: int
    student_name: str
    roll_number: str
    department: str | None = None
    cpi: float | None = None
    backlog_count: int | None = None
    preference_order: int
    submitted_at: dt.datetime | None = None
    rank: int
    within_capacity: bool
    note: str | None = None


class RankingCriterion(BaseModel):
    field: str
    direction: str = "desc"
    label: str | None = None


class MinorAllocationPreview(BaseModel):
    """A dry run: what a round WOULD do, with nothing written."""
    program_id: int
    program_name: str
    capacity: int
    seats_filled: int
    seats_available: int
    applicants: int
    would_allocate: int
    criteria: list[RankingCriterion] = Field(default_factory=list)
    ranking: list[RankedApplicantOut] = Field(default_factory=list)


class MinorAllocationResult(BaseModel):
    program_id: int
    allocated: int
    waitlisted: int
    seats_filled: int
    ranking: list[RankedApplicantOut] = Field(default_factory=list)


class RankingPolicyUpdate(BaseModel):
    """Set the ranking policy for one minor. No formula is assumed by default."""
    criteria: list[RankingCriterion] = Field(min_length=1)
