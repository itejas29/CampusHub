from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.models.enums import (
    AllocationStatus, ComponentType, CurriculumStatus, MoocPlatform, MoocStatus,
    OfferingStatus, RegistrationWindowStatus, RoundSelectionMode, RoundStage,
    SourceScope, StudentRegistrationState, VerificationStatus,
)
from app.schemas.common import ORMModel


class ElectiveTypeOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None = None
    component_type: ComponentType
    selection_mode: str
    min_preferences: int
    max_preferences: int


class CourseOut(ORMModel):
    id: int
    code: str
    title: str
    credits: float
    department_id: int | None = None
    department_code: str | None = None
    department_name: str | None = None
    offering_school: str | None = None
    lecture_hours: int
    tutorial_hours: int
    practical_hours: int
    description: str | None = None
    prerequisites: str | None = None
    syllabus_url: str | None = None
    specialization_area: str | None = None
    platform: MoocPlatform | None = None
    provider_url: str | None = None
    duration_weeks: int | None = None
    is_active: bool


class CourseCreate(BaseModel):
    code: str = Field(max_length=30)
    title: str = Field(max_length=200)
    credits: float = Field(default=3, ge=0, le=30)
    department_id: int | None = None
    offering_school: str | None = None
    lecture_hours: int = 3
    tutorial_hours: int = 0
    practical_hours: int = 0
    description: str | None = None
    prerequisites: str | None = None
    syllabus_url: str | None = None
    specialization_area: str | None = None
    platform: MoocPlatform | None = None
    provider_url: str | None = None
    duration_weeks: int | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    credits: float | None = Field(default=None, ge=0, le=30)
    description: str | None = None
    prerequisites: str | None = None
    syllabus_url: str | None = None
    specialization_area: str | None = None
    is_active: bool | None = None


class CurriculumComponentOut(ORMModel):
    id: int
    curriculum_id: int
    semester_number: int
    code: str
    title: str
    component_type: ComponentType
    source_scope: SourceScope
    scope_label: str | None = None
    credits: float
    sequence: int
    is_elective: bool
    description: str | None = None
    elective_type_id: int | None = None
    elective_type_code: str | None = None
    config: dict = Field(default_factory=dict)
    #: Declarative cross-programme rules (schools, departments, programmes).
    eligibility: dict = Field(default_factory=dict)
    selection_mode: str | None = None
    #: Fixed course filling a non-choice slot (a core course, or an Open
    #: Elective a programme prescribes by name as CSBS does).
    course_code: str | None = None
    course_title: str | None = None
    course_category: str | None = None
    delivery_mode: str | None = None
    #: Set when the source was ambiguous — surfaced so an unconfirmed reading
    #: never passes as settled policy.
    source_confidence: str | None = None
    source_note: str | None = None
    # Contextual, filled in for the signed-in student.
    #: The registration round governing this slot for them, if any. Slots of
    #: one semester in the same two-stage round are chosen together.
    round_id: int | None = None
    round_two_stage: bool | None = None
    is_unlocked: bool | None = None
    status_label: str | None = None
    allocated_course: str | None = None
    offering_count: int | None = None


class CurriculumSemesterOut(BaseModel):
    semester_number: int
    label: str
    is_current: bool = False
    is_completed: bool = False
    components: list[CurriculumComponentOut]
    total_credits: float = 0


class CurriculumSourceOut(BaseModel):
    """Where a curriculum version came from. Curriculum data is policy data, so
    an administrator has to be able to see the document behind a rule."""

    url: str | None = None
    title: str | None = None
    publisher: str | None = None
    retrieved_at: dt.date | None = None
    academic_year: str | None = None
    confidence: str | None = None
    verified_at: dt.datetime | None = None
    verified_by: str | None = None
    review_notes: str | None = None


class CurriculumOut(ORMModel):
    id: int
    program_id: int
    program_name: str | None = None
    program_code: str | None = None
    department_code: str | None = None
    school: str | None = None
    name: str
    version: str
    effective_from_year: int
    effective_to_year: int | None = None
    batch_label: str | None = None
    total_credits: int | None = None
    status: CurriculumStatus = CurriculumStatus.DRAFT
    is_active: bool
    published_at: dt.datetime | None = None
    source: CurriculumSourceOut | None = None
    component_count: int = 0
    flagged_component_count: int = 0
    semesters: list[CurriculumSemesterOut] = Field(default_factory=list)


class ProgramDivisionOut(ORMModel):
    id: int
    program_id: int
    admission_year: int
    name: str
    capacity: int | None = None
    is_active: bool = True
    student_count: int = 0
    notes: str | None = None


class CurriculumVersionIn(BaseModel):
    """Create or revise a curriculum version."""

    program_id: int
    version: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=180)
    effective_from_year: int = Field(ge=1990, le=2100)
    effective_to_year: int | None = Field(default=None, ge=1990, le=2100)
    total_credits: int | None = Field(default=None, ge=0, le=400)
    source_url: str | None = None
    source_title: str | None = None
    review_notes: str | None = None


class CurriculumComponentIn(BaseModel):
    semester_number: int = Field(ge=1, le=12)
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=180)
    component_type: ComponentType
    source_scope: SourceScope = SourceScope.ANY
    scope_label: str | None = None
    credits: float = Field(default=3, ge=0, le=60)
    sequence: int = 1
    is_elective: bool = True
    elective_type_id: int | None = None
    selection_mode: str | None = None
    eligibility: dict = Field(default_factory=dict)
    course_id: int | None = None
    description: str | None = None


class ProgramDivisionIn(BaseModel):
    program_id: int
    admission_year: int = Field(ge=1990, le=2100)
    name: str = Field(min_length=1, max_length=10)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    notes: str | None = None


class SectionOut(ORMModel):
    id: int
    course_offering_id: int
    name: str
    #: None means no ceiling (Program Core Electives).
    capacity: int | None = None
    seats_filled: int
    seats_available: int | None = None
    is_full: bool = False
    faculty_id: int | None = None
    faculty_name: str | None = None
    venue: str | None = None
    schedule_note: str | None = None
    is_active: bool = True
    division_breakdown: list[dict] = Field(default_factory=list)


class CourseOfferingOut(ORMModel):
    id: int
    course: CourseOut
    semester_id: int
    semester_number: int | None = None
    curriculum_component_id: int | None = None
    component_code: str | None = None
    component_title: str | None = None
    elective_type_id: int | None = None
    # Capacity rules differ per elective family — see services/sections.py.
    min_students_to_run: int = 40
    section_capacity: int | None = None
    allow_multiple_sections: bool = False
    eligible_divisions: list[str] = Field(default_factory=list)
    seats_filled: int
    sections_needed: int = 0
    is_viable: bool = False
    sections: list[SectionOut] = Field(default_factory=list)
    status: OfferingStatus
    registration_opens_at: dt.datetime | None = None
    registration_closes_at: dt.datetime | None = None
    venue: str | None = None
    schedule_note: str | None = None
    coordinator_name: str | None = None
    notes: str | None = None
    # Student-context flags
    is_open: bool | None = None
    my_preference_order: int | None = None


class CourseOfferingCreate(BaseModel):
    course_id: int
    semester_id: int
    curriculum_component_id: int | None = None
    elective_type_id: int | None = None
    min_students_to_run: int = Field(default=40, ge=0, le=1000)
    #: 75 for Open Electives (per section); leave null for Core Electives.
    section_capacity: int | None = Field(default=None, ge=1, le=1000)
    allow_multiple_sections: bool = False
    eligible_divisions: list[str] = Field(default_factory=list)
    status: OfferingStatus = OfferingStatus.DRAFT
    registration_opens_at: dt.datetime | None = None
    registration_closes_at: dt.datetime | None = None
    coordinator_faculty_id: int | None = None
    venue: str | None = None
    schedule_note: str | None = None
    notes: str | None = None


class CourseOfferingUpdate(BaseModel):
    min_students_to_run: int | None = Field(default=None, ge=0, le=1000)
    section_capacity: int | None = Field(default=None, ge=1, le=1000)
    allow_multiple_sections: bool | None = None
    eligible_divisions: list[str] | None = None
    status: OfferingStatus | None = None
    registration_opens_at: dt.datetime | None = None
    registration_closes_at: dt.datetime | None = None
    coordinator_faculty_id: int | None = None
    venue: str | None = None
    schedule_note: str | None = None
    notes: str | None = None


class PreferenceItem(BaseModel):
    course_offering_id: int
    preference_order: int = Field(ge=1, le=20)


class PreferenceSubmit(BaseModel):
    curriculum_component_id: int
    preferences: list[PreferenceItem] = Field(min_length=1, max_length=20)


class PreferenceOut(ORMModel):
    id: int
    curriculum_component_id: int
    component_code: str | None = None
    course_offering_id: int
    course_code: str | None = None
    course_title: str | None = None
    preference_order: int
    status: str
    submitted_at: dt.datetime | None = None


class AllocationOut(ORMModel):
    id: int
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    division: str | None = None
    section_id: int | None = None
    section_name: str | None = None
    curriculum_component_id: int
    component_code: str | None = None
    component_title: str | None = None
    course_offering_id: int
    course_code: str | None = None
    course_title: str | None = None
    status: AllocationStatus
    allocation_round: int
    strategy: str | None = None
    preference_order_granted: int | None = None
    is_manual_override: bool
    allocated_at: dt.datetime | None = None
    remarks: str | None = None


class RoundSubjectOut(BaseModel):
    course_id: int
    code: str
    title: str
    credits: float | None = None


class StudentRoundOut(BaseModel):
    """A two-stage round as one student sees it: what to tick, and what they ticked."""

    id: int
    title: str
    stage: RoundStage
    pick_count: int
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    can_submit: bool
    reason: str | None = None
    subjects: list[RoundSubjectOut] = Field(default_factory=list)
    my_course_ids: list[int] = Field(default_factory=list)
    submitted_at: dt.datetime | None = None
    #: Interest ticks the student made earlier, shown during the final stage.
    my_interest_course_ids: list[int] = Field(default_factory=list)
    #: The curriculum slots this round fills, e.g. PE2 and PE3.
    slot_codes: list[str] = Field(default_factory=list)
    slot_titles: list[str] = Field(default_factory=list)


class RoundChoiceSubmit(BaseModel):
    course_ids: list[int] = Field(default_factory=list, max_length=50)


class InterestTallyRow(BaseModel):
    course_id: int
    code: str
    title: str
    votes: int
    #: Still in the round (False once the shortlist dropped it).
    in_round: bool


class InterestTallyOut(BaseModel):
    stage: RoundStage
    voters: int
    eligible_student_count: int
    interest_pick_count: int | None = None
    slot_count: int = 0
    subjects: list[InterestTallyRow] = Field(default_factory=list)


class ShortlistRequest(BaseModel):
    course_ids: list[int] = Field(min_length=1)
    final_pick_count: int = Field(ge=1, le=20)
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime


class FinaliseRequest(BaseModel):
    #: Overrides the round's minimum for this run.
    min_students_to_run: int | None = Field(default=None, ge=1, le=10_000)
    #: Which subjects run, when the coordinator decides rather than the count.
    run_course_ids: list[int] | None = None
    dry_run: bool = True


class FinalSubjectOut(BaseModel):
    course_id: int
    code: str
    title: str
    demand: int
    runs: bool
    seated: int


class FinaliseResult(BaseModel):
    dry_run: bool
    minimum: int
    pick_count: int
    subjects: list[FinalSubjectOut]
    students_placed: int
    by_choice: int
    replaced_withdrawn: int
    placed_no_submission: int
    unplaced: int
    seats_written: int = 0
    notes: list[str] = Field(default_factory=list)


class SubjectIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=200)
    credits: float = Field(default=3, ge=0, le=20)
    description: str | None = None


class SubjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    credits: float | None = Field(default=None, ge=0, le=20)
    description: str | None = None


class SubjectOut(BaseModel):
    offering_id: int
    course_id: int
    code: str
    title: str
    credits: float | None = None
    description: str | None = None
    component_id: int
    registration_window_id: int | None = None


class ElectiveWorkspace(BaseModel):
    """Everything a student needs for one elective component, in one call."""

    component: CurriculumComponentOut
    eligible: bool
    eligibility_notes: list[str] = Field(default_factory=list)
    #: True only when the student may actually write right now. The backend
    #: has already made this decision; the UI reflects it rather than deciding.
    window_open: bool
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    #: Derived state, and the sentence to show for it.
    registration_state: StudentRegistrationState = StudentRegistrationState.NOT_OPEN
    registration_label: str | None = None
    #: Why the student cannot act, when they cannot.
    registration_reason: str | None = None
    window_title: str | None = None
    min_preferences: int = 1
    max_preferences: int = 5
    offerings: list[CourseOfferingOut] = Field(default_factory=list)
    my_preferences: list[PreferenceOut] = Field(default_factory=list)
    my_allocation: AllocationOut | None = None
    #: Set when the governing round is two-stage: the student ticks subjects
    #: for the whole round here instead of ranking this slot's courses.
    round: StudentRoundOut | None = None


class RegistrationWindowOut(ORMModel):
    """A registration round as the coordinator sees it."""

    id: int
    code: str
    title: str
    description: str | None = None
    component_type: ComponentType
    status: RegistrationWindowStatus
    department_id: int | None = None
    department_code: str | None = None
    academic_year_id: int | None = None
    semester_id: int | None = None
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    eligible_semesters: list[int] = Field(default_factory=list)
    eligible_program_ids: list[int] = Field(default_factory=list)
    eligible_program_codes: list[str] = Field(default_factory=list)
    eligible_divisions: list[str] = Field(default_factory=list)
    min_preferences: int | None = None
    max_preferences: int | None = None
    locked_at: dt.datetime | None = None
    allocated_at: dt.datetime | None = None
    published_at: dt.datetime | None = None
    notes: str | None = None
    #: Live counts, so the coordinator can judge whether to lock.
    offering_count: int = 0
    eligible_student_count: int = 0
    submitted_student_count: int = 0
    allocated_count: int = 0
    #: True when the clock has passed the deadline, whatever the status says.
    is_past_deadline: bool = False
    is_accepting: bool = False
    #: The curriculum slots this round's courses belong to.
    slots: list[dict] = Field(default_factory=list)
    #: The semester those slots sit in. A round aimed at the semester before it
    #: is early choice filling.
    slot_semester: int | None = None
    #: False for a Head of Department, who may read a round but not drive it.
    can_manage: bool = False
    selection_mode: RoundSelectionMode = RoundSelectionMode.RANKED
    stage: RoundStage | None = None
    interest_pick_count: int | None = None
    final_pick_count: int | None = None
    min_students_to_run: int | None = None
    section_capacity: int | None = None
    interest_closed_at: dt.datetime | None = None


class RegistrationWindowIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    component_type: ComponentType
    department_id: int | None = None
    academic_year_id: int | None = None
    semester_id: int | None = None
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    eligible_semesters: list[int] = Field(default_factory=list)
    eligible_program_ids: list[int] = Field(default_factory=list)
    eligible_divisions: list[str] = Field(default_factory=list)
    min_preferences: int | None = Field(default=None, ge=1, le=20)
    max_preferences: int | None = Field(default=None, ge=1, le=20)
    notes: str | None = None
    selection_mode: RoundSelectionMode = RoundSelectionMode.RANKED
    interest_pick_count: int | None = Field(default=None, ge=1, le=20)
    final_pick_count: int | None = Field(default=None, ge=1, le=20)
    min_students_to_run: int | None = Field(default=None, ge=1, le=10_000)
    section_capacity: int | None = Field(default=None, ge=1, le=10_000)


class RegistrationWindowUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    opens_at: dt.datetime | None = None
    closes_at: dt.datetime | None = None
    eligible_semesters: list[int] | None = None
    eligible_program_ids: list[int] | None = None
    eligible_divisions: list[str] | None = None
    min_preferences: int | None = Field(default=None, ge=1, le=20)
    max_preferences: int | None = Field(default=None, ge=1, le=20)
    notes: str | None = None
    selection_mode: RoundSelectionMode | None = None
    interest_pick_count: int | None = Field(default=None, ge=1, le=20)
    final_pick_count: int | None = Field(default=None, ge=1, le=20)
    min_students_to_run: int | None = Field(default=None, ge=1, le=10_000)
    section_capacity: int | None = Field(default=None, ge=1, le=10_000)


class WindowOfferingLink(BaseModel):
    """Attach or detach the courses a round covers."""

    offering_ids: list[int] = Field(default_factory=list)


class AllocationStrategyOut(BaseModel):
    key: str
    label: str
    description: str
    is_available: bool


class RunAllocationRequest(BaseModel):
    curriculum_component_id: int
    #: The round being allocated. Needed when two rounds share the slot (one
    #: cohort choosing ahead while another chooses now); inferred otherwise.
    registration_window_id: int | None = None
    strategy: str = "preference_order"
    dry_run: bool = True
    #: Course-wide seat limit for this run. Empty means the course's own
    #: rule: Open Electives open another section, Core Electives have no cap.
    seats_per_course: int | None = Field(default=None, ge=1, le=10_000)
    config: dict = Field(default_factory=dict)


class AllocationRunResult(BaseModel):
    strategy: str
    dry_run: bool
    allocated: int
    waitlisted: int
    unallocated: int
    notes: list[str] = Field(default_factory=list)
    preview: list[AllocationOut] = Field(default_factory=list)


class ManualAllocationRequest(BaseModel):
    student_id: int
    curriculum_component_id: int
    course_offering_id: int
    remarks: str | None = None


# ── MOOC / NPTEL ──────────────────────────────────────────────────────────
class MoocRegistrationOut(ORMModel):
    id: int
    student_id: int
    student_name: str | None = None
    roll_number: str | None = None
    course_offering_id: int
    course_code: str | None = None
    course_title: str | None = None
    platform: MoocPlatform
    platform_registration_id: str | None = None
    course_url: str | None = None
    status: MoocStatus
    exam_date: dt.date | None = None
    exam_city: str | None = None
    exam_fee_paid: bool
    exam_fee_reference: str | None = None
    certificate_url: str | None = None
    verification_status: VerificationStatus
    verified_at: dt.datetime | None = None
    final_score: float | None = None
    grade: str | None = None
    remarks: str | None = None


class MoocRegisterRequest(BaseModel):
    course_offering_id: int
    platform_registration_id: str | None = Field(default=None, max_length=80)
    exam_date: dt.date | None = None
    exam_city: str | None = None


class MoocUpdateRequest(BaseModel):
    platform_registration_id: str | None = None
    exam_date: dt.date | None = None
    exam_city: str | None = None
    exam_fee_paid: bool | None = None
    exam_fee_reference: str | None = None
    final_score: float | None = Field(default=None, ge=0, le=100)


class MoocVerifyRequest(BaseModel):
    verification_status: VerificationStatus
    grade: str | None = Field(default=None, max_length=10)
    final_score: float | None = Field(default=None, ge=0, le=100)
    remarks: str | None = None


# ── sections and viability ────────────────────────────────────────────────
class ViabilityOut(BaseModel):
    """Whether a course clears its minimum, and how it should be split."""

    offering_id: int
    course_code: str
    course_title: str
    demand: int
    min_students_to_run: int
    section_capacity: int | None = None
    allow_multiple_sections: bool
    runs: bool
    shortfall: int
    planned_sections: list[int] = Field(default_factory=list)
    existing_sections: int = 0
    division_breakdown: list[dict] = Field(default_factory=list)
    eligible_divisions: list[str] = Field(default_factory=list)
    reason: str


class SectionCreate(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    faculty_id: int | None = None
    venue: str | None = None
    schedule_note: str | None = None


class SectionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    capacity: int | None = Field(default=None, ge=1, le=1000)
    faculty_id: int | None = None
    venue: str | None = None
    schedule_note: str | None = None
    is_active: bool | None = None


class MoveStudentRequest(BaseModel):
    allocation_id: int
    section_id: int
    reason: str | None = Field(default=None, max_length=300)


class DistributeResult(BaseModel):
    sections: int
    assigned: int
    detail: list[SectionOut] = Field(default_factory=list)
