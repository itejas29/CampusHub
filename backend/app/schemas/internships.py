from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import (
    DocumentType, EnrollmentStatus, EvaluationStatus, EvaluatorRole, InternshipType,
    OrganizationType, ProgramStatus, ReportFrequency, ReportType, StageStatus,
    SubmissionStatus,
    ProgramPhase,
)
from app.schemas.common import ORMModel


class OrganizationOut(ORMModel):
    id: int
    name: str
    type: OrganizationType
    field_of_work: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    country: str
    pincode: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    contact_person: str | None = None
    contact_designation: str | None = None
    is_verified: bool


class OrganizationCreate(BaseModel):
    name: str = Field(max_length=200)
    type: OrganizationType = OrganizationType.NGO
    field_of_work: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    country: str = "India"
    pincode: str | None = None
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    website: str | None = None
    contact_person: str | None = None
    contact_designation: str | None = None


class StageOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None = None
    sequence: int
    is_mandatory: bool
    requires_document: bool
    document_type: DocumentType | None = None
    owner_role: str


class StageProgressOut(BaseModel):
    stage: StageOut
    status: StageStatus
    submitted_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None
    remarks: str | None = None
    is_current: bool = False


class EvaluationCriteriaOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None = None
    max_marks: float
    weight: float
    sequence: int
    evaluator_role: EvaluatorRole
    #: True for components a student must never fill in (industry mentor).
    is_external: bool = False


class InternshipProgramOut(ORMModel):
    id: int
    code: str
    name: str
    type: InternshipType
    description: str | None = None
    department_id: int | None = None
    target_semester: int | None = None
    announce_from_semester: int | None = None
    visible_to_semester: int | None = None
    phase: ProgramPhase = ProgramPhase.ACTIVE
    #: One sentence explaining the phase to this student; null when active.
    phase_note: str | None = None
    credits: float
    requires_group: bool
    default_group_size: int
    requires_organization: bool
    allowed_organization_types: list[str] = Field(default_factory=list)
    report_frequency: ReportFrequency
    expected_report_count: int
    requires_industry_mentor: bool
    registration_opens_at: dt.datetime | None = None
    registration_closes_at: dt.datetime | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    status: ProgramStatus
    coordinator_name: str | None = None
    stages: list[StageOut] = Field(default_factory=list)
    criteria: list[EvaluationCriteriaOut] = Field(default_factory=list)
    #: Students one mentor may carry, and whether a coordinator has confirmed it
    #: (False = the portal's default of 10, not a confirmed PDEU rule).
    mentor_capacity: int = 10
    mentor_capacity_confirmed: bool = False
    #: Set once the coordinator locks the mentor allocation; while locked, only
    #: the mentors listed can hold students — see services/mentor_allocation.
    mentor_allocation_locked_at: dt.datetime | None = None
    mentor_allocation_ids: list[int] = Field(default_factory=list)
    #: Whether the person asking may manage this programme (coordinator scope).
    can_manage: bool = False
    #: The coordinator role that runs it ("CSSI", "PROJECT", …).
    coordination_domain: str | None = None
    #: Ways to take the programme, each with what registering asks for.
    tracks: list[dict] = Field(default_factory=list)
    #: "for students admitted in 2024 or later" — empty when every batch.
    batch_note: str | None = None
    #: What the department still has to confirm (stages, rubric, credits).
    needs_confirmation: list[str] = Field(default_factory=list)
    #: Window kinds this programme runs (e.g. ["REGISTRATION", "PRESENTATION"]);
    #: empty means the older semester-only rules apply.
    window_kinds: list[str] = Field(default_factory=list)
    # Aggregates
    enrolled_count: int = 0
    completed_count: int = 0
    group_count: int = 0
    # Student context
    my_enrollment_id: int | None = None
    can_enroll: bool = False
    enroll_blocked_reason: str | None = None


class InternshipProgramCreate(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=180)
    type: InternshipType
    description: str | None = None
    department_id: int | None = None
    academic_year_id: int | None = None
    target_semester: int | None = None
    credits: float = 2
    requires_group: bool = False
    default_group_size: int = Field(default=10, ge=1, le=100)
    requires_organization: bool = True
    report_frequency: ReportFrequency = ReportFrequency.NONE
    expected_report_count: int = 0
    requires_industry_mentor: bool = False
    registration_opens_at: dt.datetime | None = None
    registration_closes_at: dt.datetime | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    coordinator_faculty_id: int | None = None


class InternshipProgramUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProgramStatus | None = None
    default_group_size: int | None = Field(default=None, ge=1, le=100)
    report_frequency: ReportFrequency | None = None
    expected_report_count: int | None = Field(default=None, ge=0, le=60)
    registration_opens_at: dt.datetime | None = None
    registration_closes_at: dt.datetime | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    coordinator_faculty_id: int | None = None
    #: Setting the cap is how a coordinator confirms it. Stored in `config`.
    mentor_capacity: int | None = Field(default=None, ge=1, le=60)


class GroupOut(ORMModel):
    id: int
    program_id: int
    name: str
    faculty_id: int | None = None
    faculty_name: str | None = None
    faculty_designation: str | None = None
    faculty_cabin: str | None = None
    faculty_email: str | None = None
    capacity: int
    member_count: int = 0
    meeting_schedule: str | None = None


class GroupCreate(BaseModel):
    name: str = Field(max_length=80)
    faculty_id: int | None = None
    capacity: int = Field(default=10, ge=1, le=100)
    meeting_schedule: str | None = None


class ProjectDetailOut(ORMModel):
    title: str | None = None
    problem_statement: str | None = None
    approach: str | None = None
    outcomes: str | None = None
    technologies: str | None = None
    beneficiaries: str | None = None
    extra: dict = Field(default_factory=dict)


class ProjectDetailUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=250)
    problem_statement: str | None = None
    approach: str | None = None
    outcomes: str | None = None
    technologies: str | None = None
    beneficiaries: str | None = None
    extra: dict | None = None


class DocumentOut(ORMModel):
    id: int
    document_type: DocumentType
    title: str | None = None
    file_id: int
    file_name: str | None = None
    file_url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    status: SubmissionStatus
    stage_id: int | None = None
    remarks: str | None = None
    created_at: dt.datetime


class ReportOut(ORMModel):
    id: int
    report_type: ReportType
    sequence_number: int
    title: str | None = None
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    summary: str | None = None
    tasks_completed: str | None = None
    challenges: str | None = None
    next_plan: str | None = None
    hours_spent: float | None = None
    file_url: str | None = None
    status: SubmissionStatus
    submitted_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None
    feedback: str | None = None


class ReportSubmit(BaseModel):
    report_type: ReportType = ReportType.WEEKLY
    sequence_number: int = Field(default=1, ge=1, le=60)
    title: str | None = Field(default=None, max_length=200)
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    summary: str = Field(min_length=10, max_length=5000)
    tasks_completed: str | None = None
    challenges: str | None = None
    next_plan: str | None = None
    hours_spent: float | None = Field(default=None, ge=0, le=400)
    file_id: int | None = None


class ReportReview(BaseModel):
    status: SubmissionStatus
    feedback: str | None = None


class EvaluationScoreIn(BaseModel):
    criteria_id: int
    marks: float | None = Field(default=None, ge=0)
    is_absent: bool = False
    comments: str | None = None


class EvaluationScoreOut(ORMModel):
    id: int
    criteria_id: int
    criteria_name: str | None = None
    max_marks: float | None = None
    marks: float | None = None
    is_absent: bool
    comments: str | None = None


class EvaluationSubmit(BaseModel):
    scores: list[EvaluationScoreIn] = Field(default_factory=list)
    is_absent: bool = False
    comments: str | None = None
    grade: str | None = Field(default=None, max_length=10)
    finalise: bool = False


class EvaluationOut(ORMModel):
    id: int
    enrollment_id: int
    evaluator_user_id: int | None = None
    evaluator_name: str | None = None
    evaluator_role: EvaluatorRole
    evaluation_round: int
    status: EvaluationStatus
    is_absent: bool
    total_marks: float | None = None
    max_marks: float | None = None
    grade: str | None = None
    comments: str | None = None
    submitted_at: dt.datetime | None = None
    scores: list[EvaluationScoreOut] = Field(default_factory=list)


class EnrollmentSummary(ORMModel):
    """Row shape for "My Students" / coordinator tables."""

    id: int
    program_id: int
    program_code: str | None = None
    program_type: str | None = None
    program_name: str | None = None
    #: The track chosen, for a programme that offers several (Semester VIII).
    track: str | None = None
    track_label: str | None = None
    #: Project team (Semester VII / VIII): id, name, leader, members, is_fixed.
    team: dict | None = None
    #: Guides ranked by the student (or their team), most preferred first.
    guide_preferences: list[dict] = Field(default_factory=list)
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    department_code: str | None = None
    division: str | None = None
    semester: int | None = None
    avatar_url: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    mentor_faculty_id: int | None = None
    mentor_name: str | None = None
    organization_id: int | None = None
    organization_name: str | None = None
    status: EnrollmentStatus
    current_stage: str | None = None
    progress_percent: int = 0
    evaluation_status: EvaluationStatus | None = None
    final_marks: float | None = None
    final_grade: str | None = None


class PresentationSchedule(BaseModel):
    """Allocate (or clear, by passing null) a presentation slot."""
    scheduled_at: dt.datetime | None = None
    venue: str | None = Field(default=None, max_length=120)
    panel: str | None = Field(default=None, max_length=180)


class PresentationQueueRow(BaseModel):
    enrollment_id: int
    student_name: str
    roll_number: str
    division: str | None = None
    group_name: str | None = None
    #: A slot is only allocated once the certificate has been verified.
    certificate_verified: bool
    presentation_at: dt.datetime | None = None
    presentation_venue: str | None = None
    presentation_panel: str | None = None


class EnrollmentDetail(EnrollmentSummary):
    #: {"min", "max"} when this student may work in a team; None otherwise.
    team_limits: dict | None = None
    #: How many guides may be ranked; 0 when the programme takes none.
    preference_limit: int = 0
    report_frequency: str | None = None
    email: str | None = None
    phone: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    location: str | None = None
    stipend: float | None = None
    industry_mentor_name: str | None = None
    industry_mentor_email: str | None = None
    industry_mentor_phone: str | None = None
    industry_mentor_designation: str | None = None
    industry_mentor_feedback: str | None = None
    coordinator_remarks: str | None = None
    organization: OrganizationOut | None = None
    project: ProjectDetailOut | None = None
    stages: list[StageProgressOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    reports: list[ReportOut] = Field(default_factory=list)
    evaluations: list[EvaluationOut] = Field(default_factory=list)
    criteria: list[EvaluationCriteriaOut] = Field(default_factory=list)
    mentor: dict | None = None
    report_schedule: list[dict] = Field(default_factory=list)
    #: Expected + actual documents, grouped for the Proof of Work tab.
    presentation_at: dt.datetime | None = None
    presentation_venue: str | None = None
    presentation_panel: str | None = None
    document_groups: list[DocumentGroupOut] = Field(default_factory=list)
    #: Stage completion derived from documents, with the reasons it is blocked.
    progress: ProgressOut | None = None


class EnrollRequest(BaseModel):
    organization_id: int | None = None
    new_organization: OrganizationCreate | None = None
    #: The person at the organisation who supervises the student (for CSSI,
    #: the NGO supervisor). Required when the programme requires one.
    industry_mentor_name: str | None = Field(default=None, max_length=150)
    industry_mentor_phone: str | None = Field(default=None, max_length=20)
    industry_mentor_email: EmailStr | None = None
    #: Required when the programme offers tracks (`config["tracks"]`).
    track: str | None = Field(default=None, max_length=40)


class EnrollmentUpdate(BaseModel):
    organization_id: int | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    location: str | None = None
    stipend: float | None = Field(default=None, ge=0)
    industry_mentor_name: str | None = None
    industry_mentor_email: EmailStr | None = None
    industry_mentor_phone: str | None = None
    industry_mentor_designation: str | None = None


class StageActionRequest(BaseModel):
    stage_id: int
    data: dict = Field(default_factory=dict)


class StageReviewRequest(BaseModel):
    stage_id: int
    approve: bool
    remarks: str | None = None


class MentorOverrideRequest(BaseModel):
    mentor_faculty_id: int | None = None
    group_id: int | None = None
    reason: str = Field(default="Assigned by coordinator", min_length=1, max_length=500)


class MentorCapacityOut(BaseModel):
    faculty_id: int
    name: str
    employee_code: str | None = None
    department_code: str | None = None
    designation: str | None = None
    avatar_url: str | None = None
    assigned_count: int
    max_capacity: int = 10
    #: False while `max_capacity` is the unconfirmed portal default.
    capacity_confirmed: bool = False
    remaining_capacity: int
    is_full: bool
    #: In the locked allocation (always False while it is unlocked).
    in_allocation: bool = False


class StudentMentorAssignment(BaseModel):
    enrollment_id: int
    mentor_faculty_id: int | None = None


class BatchMentorAssignRequest(BaseModel):
    assignments: list[StudentMentorAssignment] = []
    auto_distribute: bool = False
    rebalance: bool = False
    allocate_by_roll_no: bool = False
    #: Teams and solo students get their highest-ranked guide with room.
    by_preference: bool = False
    clear_all: bool = False
    faculty_ids: list[int] | None = None
    min_students_per_mentor: int = 2
    max_students_per_mentor: int = 10
    reason: str = "Roll number-wise mentor allocation"


class AllocationMentorAdd(BaseModel):
    faculty_id: int


class AllocationMentorReplace(BaseModel):
    new_faculty_id: int


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamMemberAdd(BaseModel):
    roll_number: str = Field(min_length=3, max_length=20)


class GuidePreferences(BaseModel):
    faculty_ids: list[int] = Field(default_factory=list, max_length=10)


class StageIn(BaseModel):
    #: Omit for a new stage.
    id: int | None = None
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    is_mandatory: bool = True
    requires_document: bool = False
    document_type: DocumentType | None = None
    owner_role: str = "STUDENT"


class CriterionIn(BaseModel):
    id: int | None = None
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    max_marks: float
    weight: float = 1


class StagesReplace(BaseModel):
    stages: list[StageIn] = Field(min_length=1, max_length=30)


class CriteriaReplace(BaseModel):
    criteria: list[CriterionIn] = Field(min_length=1, max_length=20)


class ConfirmItem(BaseModel):
    item: str = Field(min_length=1, max_length=60)


class BatchMentorAssignResponse(BaseModel):
    assigned_count: int
    message: str


# ── expected-vs-actual documents ──────────────────────────────────────────
class ExpectedDocumentOut(ORMModel):
    """One required artefact, submitted or not.

    `status` is NOT_SUBMITTED when nothing has been uploaded — the item still
    appears so a missing mandatory document stays visible.
    """

    key: str
    label: str
    kind: str
    status: SubmissionStatus
    is_mandatory: bool = True
    is_submitted: bool = False
    is_satisfied: bool = False
    awaits_review: bool = False
    document_type: str | None = None
    stage_id: int | None = None
    stage_code: str | None = None
    week_number: int | None = None
    document_id: int | None = None
    report_id: int | None = None
    file_id: int | None = None
    file_name: str | None = None
    #: Present only when a real file exists — never a placeholder link.
    file_url: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None
    submitted_at: dt.datetime | None = None
    reviewed_at: dt.datetime | None = None
    reviewed_by: str | None = None
    review_comment: str | None = None
    revision: int = 1
    period_start: dt.date | None = None
    period_end: dt.date | None = None


class DocumentGroupOut(BaseModel):
    title: str
    submitted: int = 0
    satisfied: int = 0
    total: int = 0
    items: list[ExpectedDocumentOut] = Field(default_factory=list)


class ProgressOut(BaseModel):
    """Progress derived from real stage + document state, not a guess."""

    completed: int
    total: int
    percent: int
    blockers: list[str] = Field(default_factory=list)


class DocumentReviewRequest(BaseModel):
    #: start_review | verify | reject
    decision: str = Field(pattern="^(start_review|verify|reject)$")
    #: Mandatory when rejecting, so the student knows what to fix.
    comment: str | None = Field(default=None, max_length=1000)


# EnrollmentDetail references the document schemas defined above it, so the
# forward references have to be resolved once the module is fully loaded.
EnrollmentDetail.model_rebuild()


# ── coordinator-run windows ───────────────────────────────────────────────
class InternshipWindowOut(ORMModel):
    id: int
    program_id: int
    kind: str
    title: str
    message: str
    opens_at: dt.datetime
    closes_at: dt.datetime
    cohort_semester: int | None = None
    submission_due_at: dt.datetime | None = None
    presentation_from: dt.date | None = None
    presentation_to: dt.date | None = None
    closed_early_at: dt.datetime | None = None
    #: SCHEDULED, OPEN or CLOSED — computed by the server at request time.
    state: str = "SCHEDULED"


class InternshipWindowOpen(BaseModel):
    kind: str
    title: str = Field(default="", max_length=180)
    message: str = Field(min_length=1, max_length=5000)
    opens_at: dt.datetime
    closes_at: dt.datetime
    cohort_semester: int | None = Field(default=None, ge=1, le=10)
    submission_due_at: dt.datetime | None = None
    presentation_from: dt.date | None = None
    presentation_to: dt.date | None = None


class InternshipWindowUpdate(BaseModel):
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    message: str | None = Field(default=None, max_length=5000)
    submission_due_at: dt.datetime | None = None
    presentation_from: dt.date | None = None
    presentation_to: dt.date | None = None


class ProgramWindowsOut(BaseModel):
    kinds: list[str]
    windows: list[InternshipWindowOut]
    can_manage: bool = False
    #: How many students have registered — the coordinator's progress figure.
    registered_count: int = 0
    unassigned_count: int = 0


class MentorRosterStudent(BaseModel):
    roll_number: str
    name: str


class MentorRosterGroup(BaseModel):
    faculty_id: int
    name: str
    designation: str | None = None
    email: str | None = None
    cabin: str | None = None
    roll_range: str
    students: list[MentorRosterStudent]
