"""Programs, curriculum, courses, offerings, elective preference/allocation, MOOC.

The curriculum is *data*, not code: a program's semester structure is expressed
as ``CurriculumComponent`` rows, so adding a second department is a seeding
exercise rather than a frontend change.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import (
    AllocationStatus, ComponentType, CourseCategory, CurriculumStatus, DeliveryMode,
    MoocOption, MoocOutcome, MoocPlatform, MoocRoundStatus, MoocStatus, OfferingStatus,
    PreferenceStatus,
    RegistrationWindowStatus, RoundSelectionMode, RoundStage, SourceConfidence,
    SourceScope, VerificationStatus,
)


def as_utc(moment: dt.datetime | None) -> dt.datetime | None:
    """Treat a stored timestamp as UTC when it carries no zone.

    A deadline comparison must never raise. Postgres hands back aware values,
    but a naive one can arrive from another backend or from a client that omits
    the offset — and "can\'t compare offset-naive and offset-aware datetimes" at
    the moment a student submits is not an acceptable failure.
    """
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=dt.timezone.utc)


def _enum(e, name: str, length: int = 40) -> SAEnum:
    return SAEnum(e, native_enum=False, length=length, name=name,
                  values_callable=lambda x: [m.value for m in x])


class Program(PKMixin, TimestampMixin, Base):
    __tablename__ = "programs"

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(60))
    degree_type: Mapped[str] = mapped_column(String(40), nullable=False, default="B.Tech")
    duration_years: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    total_semesters: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped["Department"] = relationship(back_populates="programs")  # noqa: F821
    curriculums: Mapped[list["Curriculum"]] = relationship(back_populates="program")
    divisions: Mapped[list["ProgramDivision"]] = relationship(
        back_populates="program", cascade="all, delete-orphan",
        order_by="ProgramDivision.admission_year.desc(), ProgramDivision.name",
    )


class ProgramDivision(PKMixin, TimestampMixin, Base):
    """One teaching division of one programme, for one admission batch.

    Divisions are *data*, never a hard-coded A/B/C/D. ICT runs three, Computer
    Engineering four, CSBS one — driven by intake, not by a constant — and the
    Core Elective allocator reads whatever rows exist here rather than assuming
    ICT's shape.
    """

    __tablename__ = "program_divisions"
    __table_args__ = (
        UniqueConstraint("program_id", "admission_year", "name",
                         name="uq_program_divisions_program_year_name"),
        Index("ix_program_divisions_program_year", "program_id", "admission_year"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: The admission batch this division belongs to (2024, 2025, …).
    admission_year: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(10), nullable=False)      # "A"
    capacity: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(),
                                            nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped["Program"] = relationship(back_populates="divisions")


class ElectiveType(PKMixin, TimestampMixin, Base):
    """Lookup describing a *family* of electives and how it is selected."""

    __tablename__ = "elective_types"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[ComponentType] = mapped_column(
        _enum(ComponentType, "component_type"), nullable=False
    )
    # PREFERENCE = ranked list then allocation, DIRECT = first-come registration.
    selection_mode: Mapped[str] = mapped_column(String(20), default="PREFERENCE", nullable=False)
    min_preferences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_preferences: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Curriculum(PKMixin, TimestampMixin, Base):
    __tablename__ = "curriculums"
    __table_args__ = (
        UniqueConstraint("program_id", "version", name="uq_curriculums_program_id_version"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)          # "2024-28"
    #: First admission batch governed by this version.
    effective_from_year: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Last admission batch governed by it. NULL means "still current".
    #: Bounding the window is what lets a 2022 ECE student keep the 2020-24
    #: structure while a 2024 ECE student gets 2024-28 — the two are genuinely
    #: different curricula, not revisions of one another.
    effective_to_year: Mapped[int | None] = mapped_column(Integer)
    total_credits: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[CurriculumStatus] = mapped_column(
        _enum(CurriculumStatus, "curriculum_status", 20),
        default=CurriculumStatus.DRAFT, nullable=False,
    )
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # ── source traceability ───────────────────────────────────────────────
    # Curriculum data is university policy data. An administrator must be able
    # to see exactly which document a rule came from, and how confident the
    # import was, before trusting it.
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_title: Mapped[str | None] = mapped_column(String(300))
    source_publisher: Mapped[str | None] = mapped_column(String(180))
    source_date: Mapped[dt.date | None] = mapped_column(Date)
    retrieved_at: Mapped[dt.date | None] = mapped_column(Date)
    academic_year_label: Mapped[str | None] = mapped_column(String(20))
    source_confidence: Mapped[SourceConfidence | None] = mapped_column(
        _enum(SourceConfidence, "source_confidence", 40)
    )
    verified_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: Anything the import could not confirm — shown to admins verbatim.
    review_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    program: Mapped["Program"] = relationship(back_populates="curriculums")

    def governs_batch(self, admission_year: int) -> bool:
        """Does this version apply to a student admitted in `admission_year`?"""
        if admission_year < self.effective_from_year:
            return False
        if self.effective_to_year is not None and admission_year > self.effective_to_year:
            return False
        return True

    @property
    def is_published(self) -> bool:
        return self.status == CurriculumStatus.PUBLISHED
    components: Mapped[list["CurriculumComponent"]] = relationship(
        back_populates="curriculum", cascade="all, delete-orphan",
        order_by="CurriculumComponent.semester_number, CurriculumComponent.sequence",
    )


class CurriculumComponent(PKMixin, TimestampMixin, Base):
    """One requirement slot in one semester — e.g. "Open Elective 1 (Sem IV)".

    ``source_scope`` carries the PDEU rule about *where* the course may come
    from ("From Other School", "From Other Department of FoET", ...).
    """

    __tablename__ = "curriculum_components"
    __table_args__ = (
        UniqueConstraint("curriculum_id", "code", name="uq_curriculum_components_curriculum_id_code"),
        Index("ix_curriculum_components_curriculum_sem", "curriculum_id", "semester_number"),
    )

    curriculum_id: Mapped[int] = mapped_column(
        ForeignKey("curriculums.id", ondelete="CASCADE"), index=True, nullable=False
    )
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)     # "OE1", "PCE3"
    title: Mapped[str] = mapped_column(String(180), nullable=False)   # "Open Elective 1"
    component_type: Mapped[ComponentType] = mapped_column(
        _enum(ComponentType, "cc_component_type"), nullable=False
    )
    elective_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("elective_types.id", ondelete="SET NULL")
    )
    source_scope: Mapped[SourceScope] = mapped_column(
        _enum(SourceScope, "source_scope"), default=SourceScope.ANY, nullable=False
    )
    # Human-readable restriction shown in the UI, e.g. "From Other School".
    scope_label: Mapped[str | None] = mapped_column(String(120))
    credits: Mapped[float] = mapped_column(Numeric(4, 1), default=3, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_elective: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: For a fixed (non-choice) slot — a core course, or an Open Elective the
    #: programme prescribes by name as CSBS does — the course that fills it.
    #: NULL for genuine choice slots, whose options are CourseOfferings.
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True
    )
    #: PREFERENCE = ranked list then allocation, DIRECT = straight registration.
    #: Overrides the elective type's default for one slot.
    selection_mode: Mapped[str | None] = mapped_column(String(20))
    #: Declarative cross-programme eligibility, evaluated by
    #: `services/curriculum.component_eligibility`. Keys, all optional:
    #:   eligible_schools      ["SoT", "SoET"]  — course owner's school
    #:   eligible_departments  ["MEC", "CIV"]
    #:   eligible_programs     ["B.TECH-ICT"]
    #:   excluded_departments  ["ICT"]
    #:   excluded_programs     ["B.TECH-ICT"]
    #:   exclude_own_department / exclude_own_program   (bool)
    #: Empty means "fall back to source_scope alone".
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    #: Set when the source was ambiguous or two documents disagreed. Surfaced
    #: to administrators so an unconfirmed reading never passes as settled.
    source_confidence: Mapped[SourceConfidence | None] = mapped_column(
        _enum(SourceConfidence, "cc_source_confidence", 40)
    )
    source_note: Mapped[str | None] = mapped_column(Text)
    # Free-form extension point so new policy needs no migration.
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    curriculum: Mapped["Curriculum"] = relationship(back_populates="components")
    elective_type: Mapped["ElectiveType | None"] = relationship()
    course: Mapped["Course | None"] = relationship(lazy="joined")

    @property
    def needs_confirmation(self) -> bool:
        return self.source_confidence == SourceConfidence.REQUIRES_FACULTY_CONFIRMATION


class Course(PKMixin, TimestampMixin, Base):
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    # For courses offered by another school, the owning school name.
    offering_school: Mapped[str | None] = mapped_column(String(120))
    credits: Mapped[float] = mapped_column(Numeric(4, 1), default=3, nullable=False)
    lecture_hours: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    tutorial_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    practical_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    prerequisites: Mapped[str | None] = mapped_column(Text)
    syllabus_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    syllabus_url: Mapped[str | None] = mapped_column(String(500))
    #: The course's syllabus as the offering department publishes it: units
    #: (title, topics, hours), course outcomes and references. Revised by the
    #: coordinator; `syllabus_updated_at` dates the version students see.
    syllabus: Mapped[dict | None] = mapped_column(JSON)
    syllabus_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Program-core-elective grouping: "Artificial Intelligence", "Embedded and VLSI", ...
    specialization_area: Mapped[str | None] = mapped_column(String(120), index=True)
    #: The category letter the PDEU course-structure tables print (BSC, ESC,
    #: HSC, PC, PE, OE, Pro, IND).
    category: Mapped[CourseCategory | None] = mapped_column(
        _enum(CourseCategory, "course_category", 12), index=True
    )
    #: Theory / practical / project classification, derived from the L-T-P split.
    delivery_mode: Mapped[DeliveryMode] = mapped_column(
        _enum(DeliveryMode, "course_delivery_mode", 24),
        default=DeliveryMode.THEORY, nullable=False,
    )
    #: True when several programmes study the same course (Mathematics-1,
    #: Environment Science…). One row is shared rather than duplicated per
    #: programme, so the catalogue does not grow a copy for every department.
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # MOOC-only metadata.
    platform: Mapped[MoocPlatform | None] = mapped_column(_enum(MoocPlatform, "course_platform"))
    provider_url: Mapped[str | None] = mapped_column(String(500))
    duration_weeks: Mapped[int | None] = mapped_column(Integer)
    #: The rest of the department's NPTEL sheet: discipline, the professors
    #: (SME), the institute and the coordinating institute.
    provider_details: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped["Department | None"] = relationship()  # noqa: F821


class ElectiveRegistrationWindow(PKMixin, TimestampMixin, Base):
    """One registration round, and the authority on whether it is open.

    Deadlines are enforced here and checked server-side on every write. A
    countdown in the browser is a courtesy, never a control: a student whose
    clock is wrong, or who keeps a stale tab open, is refused by the API.

    Eligibility is expressed the same way the curriculum expresses it — by
    programme, semester and division — so a round can span several programmes
    (an Open Elective basket) or narrow to a few divisions of one, without any
    of that being hard-coded.
    """

    __tablename__ = "elective_registration_windows"
    __table_args__ = (
        Index("ix_elective_windows_status", "status"),
        Index("ix_elective_windows_dept_type", "department_id", "component_type"),
    )

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[ComponentType] = mapped_column(
        _enum(ComponentType, "window_component_type"), nullable=False
    )
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL"), index=True
    )
    semester_id: Mapped[int | None] = mapped_column(
        ForeignKey("semesters.id", ondelete="SET NULL")
    )
    #: Scope for coordinator RBAC. NULL means institution-wide.
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[RegistrationWindowStatus] = mapped_column(
        _enum(RegistrationWindowStatus, "registration_window_status", 20),
        default=RegistrationWindowStatus.DRAFT, server_default="DRAFT", nullable=False,
    )
    opens_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # ── eligibility, all optional; empty means "not narrowed by this key" ──
    eligible_semesters: Mapped[list] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    eligible_program_ids: Mapped[list] = mapped_column(JSON, default=list, server_default="[]",
                                                       nullable=False)
    eligible_divisions: Mapped[list] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    # ── preference limits, overriding the elective type's defaults ─────────
    min_preferences: Mapped[int | None] = mapped_column(Integer)
    max_preferences: Mapped[int | None] = mapped_column(Integer)
    #: Stamped as the coordinator drives the round forward, for the audit trail.
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    allocated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    # ── how students choose, and the coordinator's numbers for this round ──
    # None of these is a university constant: the department changes them year
    # to year, so each round carries its own.
    selection_mode: Mapped[RoundSelectionMode] = mapped_column(
        _enum(RoundSelectionMode, "round_selection_mode", 20),
        default=RoundSelectionMode.RANKED, server_default="RANKED", nullable=False,
    )
    #: Two-stage rounds only: INTEREST, then FINAL once the shortlist is set.
    stage: Mapped[RoundStage | None] = mapped_column(_enum(RoundStage, "round_stage", 20))
    #: Exactly how many subjects each student ticks in the interest round.
    interest_pick_count: Mapped[int | None] = mapped_column(Integer)
    #: Exactly how many shortlisted subjects each student takes.
    final_pick_count: Mapped[int | None] = mapped_column(Integer)
    #: Fewest students a course needs to run. Copied to the round's courses.
    min_students_to_run: Mapped[int | None] = mapped_column(Integer)
    #: Most students in one section (Open Electives split into sections).
    section_capacity: Mapped[int | None] = mapped_column(Integer)
    #: When the interest round closed, kept once the final round reuses the dates.
    interest_closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    offerings: Mapped[list["CourseOffering"]] = relationship(
        back_populates="registration_window"
    )

    @property
    def is_two_stage(self) -> bool:
        return self.selection_mode == RoundSelectionMode.TWO_STAGE

    @property
    def pick_count(self) -> int | None:
        """How many subjects a student ticks in the stage now running."""
        if not self.is_two_stage:
            return None
        return (self.final_pick_count if self.stage == RoundStage.FINAL
                else self.interest_pick_count)

    def is_open_at(self, now: dt.datetime) -> bool:
        """Open *and* inside its time window. Both halves must hold."""
        if self.status != RegistrationWindowStatus.OPEN:
            return False
        opens_at, closes_at = self.opens_at_utc, self.closes_at_utc
        if opens_at and now < opens_at:
            return False
        if closes_at and now >= closes_at:
            return False
        return True

    @property
    def opens_at_utc(self) -> dt.datetime | None:
        return as_utc(self.opens_at)

    @property
    def closes_at_utc(self) -> dt.datetime | None:
        return as_utc(self.closes_at)

    def accepts_students_from(self, program_id: int, semester: int,
                              division: str | None) -> bool:
        """Does this round cover that student at all?"""
        if self.eligible_program_ids and program_id not in self.eligible_program_ids:
            return False
        if self.eligible_semesters and semester not in self.eligible_semesters:
            return False
        if self.eligible_divisions and (division or "") not in self.eligible_divisions:
            return False
        return True

    @property
    def results_visible(self) -> bool:
        """Allocation is only visible once the coordinator publishes it."""
        return self.status in (RegistrationWindowStatus.PUBLISHED,
                               RegistrationWindowStatus.CLOSED)


class CourseOffering(PKMixin, TimestampMixin, Base):
    """A course made available for a specific semester and curriculum slot."""

    __tablename__ = "course_offerings"
    __table_args__ = (
        UniqueConstraint("course_id", "semester_id", "curriculum_component_id",
                         name="uq_course_offerings_course_id_semester_id"),
        Index("ix_course_offerings_component_status", "curriculum_component_id", "status"),
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    curriculum_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_components.id", ondelete="SET NULL"), index=True
    )
    elective_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("elective_types.id", ondelete="SET NULL")
    )
    coordinator_faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL")
    )
    #: The registration round this offering belongs to. When set, the round
    #: decides whether registration is open; the per-offering dates below stay
    #: as a fallback for offerings that predate rounds.
    registration_window_id: Mapped[int | None] = mapped_column(
        ForeignKey("elective_registration_windows.id", ondelete="SET NULL"), index=True
    )
    # ── viability and capacity ────────────────────────────────────────────
    # A course runs only if demand reaches this. Applies to BOTH families.
    min_students_to_run: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    # Per-SECTION ceiling, not a course-wide cap. 75 for Open Electives.
    # NULL means no ceiling — Program Core Electives run one combined class
    # however large, so they must not inherit the Open Elective rule.
    section_capacity: Mapped[int | None] = mapped_column(Integer)
    # Open Electives split into Section A/B/C… as demand grows; Core Electives
    # normally stay a single combined class across the eligible divisions.
    allow_multiple_sections: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Core Electives are division-based. NULL/empty = open to every division.
    # The 40-student minimum is checked across ALL listed divisions combined,
    # never per division.
    eligible_divisions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    seats_filled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[OfferingStatus] = mapped_column(
        _enum(OfferingStatus, "offering_status"), default=OfferingStatus.DRAFT, nullable=False
    )
    registration_opens_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str | None] = mapped_column(String(80))
    schedule_note: Mapped[str | None] = mapped_column(String(180))
    # Declarative eligibility, evaluated by services/eligibility.py.
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    course: Mapped["Course"] = relationship(lazy="joined")
    semester: Mapped["Semester"] = relationship()  # noqa: F821
    curriculum_component: Mapped["CurriculumComponent | None"] = relationship()
    registration_window: Mapped["ElectiveRegistrationWindow | None"] = relationship(
        back_populates="offerings", lazy="joined"
    )
    sections: Mapped[list["CourseSection"]] = relationship(
        back_populates="offering", cascade="all, delete-orphan",
        order_by="CourseSection.name", lazy="selectin",
    )

    @property
    def total_capacity(self) -> int | None:
        """Capacity across all sections; None when unlimited."""
        if self.section_capacity is None:
            return None
        if not self.allow_multiple_sections:
            return self.section_capacity
        # Multi-section courses grow on demand, so there is no fixed ceiling.
        return None

    @property
    def is_viable(self) -> bool:
        """Has demand reached the minimum needed to run the course?"""
        return self.seats_filled >= self.min_students_to_run

    @property
    def sections_needed(self) -> int:
        """How many sections the current demand requires."""
        if self.section_capacity is None or not self.allow_multiple_sections:
            return 1
        if self.seats_filled <= 0:
            return 0
        return -(-self.seats_filled // self.section_capacity)   # ceil


class CourseSection(PKMixin, TimestampMixin, Base):
    """One class section of a course offering.

    Open Electives are capped at `CourseOffering.section_capacity` (75) *per
    section* and spawn Section A, B, C… as demand grows. Program Core Electives
    normally run a single combined section across the eligible divisions with no
    ceiling.
    """

    __tablename__ = "course_sections"
    __table_args__ = (
        UniqueConstraint("course_offering_id", "name",
                         name="uq_course_sections_course_offering_id_name"),
    )

    course_offering_id: Mapped[int] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)   # "Section A"
    #: Copied from the offering when created, so a single section can later be
    #: widened or narrowed without changing the course-level rule.
    capacity: Mapped[int | None] = mapped_column(Integer)
    seats_filled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL")
    )
    venue: Mapped[str | None] = mapped_column(String(80))
    schedule_note: Mapped[str | None] = mapped_column(String(180))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    offering: Mapped["CourseOffering"] = relationship(back_populates="sections")
    faculty: Mapped["Faculty | None"] = relationship(lazy="joined")  # noqa: F821

    @property
    def seats_available(self) -> int | None:
        if self.capacity is None:
            return None
        return max(self.capacity - self.seats_filled, 0)

    @property
    def is_full(self) -> bool:
        return self.capacity is not None and self.seats_filled >= self.capacity


class ElectiveRoundChoice(PKMixin, TimestampMixin, Base):
    """A subject a student ticked in one stage of a two-stage round.

    Unranked by design: in the interest round a tick is a vote, and in the
    final round it is a subject the student will take. A subject is a course,
    not an offering, because one course can be offered in several of the
    round's slots (Program Elective 4 and 5 share a basket).
    """

    __tablename__ = "elective_round_choices"
    __table_args__ = (
        UniqueConstraint("registration_window_id", "stage", "student_id", "course_id",
                         name="uq_elective_round_choices_window_stage_student_course"),
        Index("ix_elective_round_choices_window_stage", "registration_window_id", "stage"),
    )

    registration_window_id: Mapped[int] = mapped_column(
        ForeignKey("elective_registration_windows.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[RoundStage] = mapped_column(_enum(RoundStage, "round_choice_stage", 20),
                                              nullable=False)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    course: Mapped["Course"] = relationship(lazy="joined")


class ElectivePreference(PKMixin, TimestampMixin, Base):
    """A student's ranked choice for one curriculum component."""

    __tablename__ = "elective_preferences"
    __table_args__ = (
        UniqueConstraint("student_id", "curriculum_component_id", "preference_order",
                         name="uq_elective_preferences_student_id_component_order"),
        UniqueConstraint("student_id", "course_offering_id",
                         name="uq_elective_preferences_student_id_course_offering_id"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    curriculum_component_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_components.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_offering_id: Mapped[int] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    preference_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PreferenceStatus] = mapped_column(
        _enum(PreferenceStatus, "preference_status"),
        default=PreferenceStatus.SUBMITTED, nullable=False,
    )
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    course_offering: Mapped["CourseOffering"] = relationship(lazy="joined")
    curriculum_component: Mapped["CurriculumComponent"] = relationship(lazy="joined")


class ElectiveAllocation(PKMixin, TimestampMixin, Base):
    """Outcome of running an allocation strategy (or a manual override)."""

    __tablename__ = "elective_allocations"
    __table_args__ = (
        UniqueConstraint("student_id", "curriculum_component_id",
                         name="uq_elective_allocations_student_id_curriculum_component_id"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    curriculum_component_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_components.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_offering_id: Mapped[int] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Which class section the student sits in. NULL until sections are formed.
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_sections.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[AllocationStatus] = mapped_column(
        _enum(AllocationStatus, "allocation_status"),
        default=AllocationStatus.ALLOCATED, nullable=False,
    )
    allocation_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Which strategy produced this row (see services/allocation).
    strategy: Mapped[str | None] = mapped_column(String(60))
    score: Mapped[float | None] = mapped_column(Numeric(8, 3))
    preference_order_granted: Mapped[int | None] = mapped_column(Integer)
    allocated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    allocated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)

    course_offering: Mapped["CourseOffering"] = relationship(lazy="joined")
    curriculum_component: Mapped["CurriculumComponent"] = relationship(lazy="joined")
    section: Mapped["CourseSection | None"] = relationship(lazy="joined")


class MoocRound(PKMixin, TimestampMixin, Base):
    """One semester's NPTEL / NCC choice, run by the department's coordinator.

    Replaces the Google Form: the approved course list, the deadline, who has
    chosen what. It stays the record for the semester — certificates come in
    while it is locked, and closing it records each student's outcome.
    """

    __tablename__ = "mooc_rounds"

    title: Mapped[str] = mapped_column(String(180), nullable=False)
    #: What the coordinator tells the students (the email, in effect).
    message: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    #: The curriculum's MOOC slot this round settles (e.g. OE2 in Semester V).
    curriculum_component_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_components.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    status: Mapped[MoocRoundStatus] = mapped_column(
        _enum(MoocRoundStatus, "mooc_round_status", 20),
        default=MoocRoundStatus.DRAFT, server_default="DRAFT", nullable=False,
    )
    #: Which semesters' students choose in it. Students carrying the slot
    #: over from an earlier round are included whatever their semester.
    eligible_semesters: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    opens_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: The NPTEL portal's own last date to register. Shown to students; the
    #: portal does not check that they registered there.
    platform_deadline: Mapped[dt.date | None] = mapped_column(Date)
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def closes_at_utc(self) -> dt.datetime | None:
        return as_utc(self.closes_at)

    @property
    def opens_at_utc(self) -> dt.datetime | None:
        return as_utc(self.opens_at)

    def is_open_at(self, now: dt.datetime) -> bool:
        if self.status != MoocRoundStatus.OPEN:
            return False
        if self.opens_at_utc and now < self.opens_at_utc:
            return False
        return not (self.closes_at_utc and now >= self.closes_at_utc)


class MoocRoundCourse(PKMixin, TimestampMixin, Base):
    """A course on a round's approved list. The next semester's round can copy
    the list, or the coordinator can change it."""

    __tablename__ = "mooc_round_courses"
    __table_args__ = (
        UniqueConstraint("mooc_round_id", "course_id",
                         name="uq_mooc_round_courses_round_course"),
    )

    mooc_round_id: Mapped[int] = mapped_column(
        ForeignKey("mooc_rounds.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )

    course: Mapped["Course"] = relationship(lazy="joined")


class MoocRoundOutcome(PKMixin, TimestampMixin, Base):
    """What closing a round decided for one student on the slot."""

    __tablename__ = "mooc_round_outcomes"
    __table_args__ = (
        UniqueConstraint("mooc_round_id", "student_id",
                         name="uq_mooc_round_outcomes_round_student"),
    )

    mooc_round_id: Mapped[int] = mapped_column(
        ForeignKey("mooc_rounds.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    curriculum_component_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_components.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    outcome: Mapped[MoocOutcome] = mapped_column(
        _enum(MoocOutcome, "mooc_outcome", 20), nullable=False
    )
    #: The student's semester when the round closed, for the record.
    semester_at_close: Mapped[int | None] = mapped_column(Integer)


class MoocRegistration(PKMixin, TimestampMixin, Base):
    """NPTEL / SWAYAM registration + certificate verification lifecycle.

    In a round, one row per student: the course they chose (or NCC), then the
    certificate — or their report that they did not pass.
    """

    __tablename__ = "mooc_registrations"
    __table_args__ = (
        UniqueConstraint("student_id", "course_offering_id",
                         name="uq_mooc_registrations_student_id_course_offering_id"),
        UniqueConstraint("mooc_round_id", "student_id",
                         name="uq_mooc_registrations_round_student"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Registrations made before rounds point at an offering; a round's point
    #: at the course itself (`course_id`), or at nothing for NCC.
    course_offering_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_offerings.id", ondelete="CASCADE"), index=True
    )
    mooc_round_id: Mapped[int | None] = mapped_column(
        ForeignKey("mooc_rounds.id", ondelete="CASCADE"), index=True
    )
    option: Mapped[MoocOption] = mapped_column(
        _enum(MoocOption, "mooc_option", 10), default=MoocOption.NPTEL, server_default="NPTEL",
        nullable=False,
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), index=True
    )
    curriculum_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("curriculum_components.id", ondelete="SET NULL")
    )
    platform: Mapped[MoocPlatform] = mapped_column(
        _enum(MoocPlatform, "mooc_platform"), default=MoocPlatform.NPTEL, nullable=False
    )
    platform_registration_id: Mapped[str | None] = mapped_column(String(80))
    course_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[MoocStatus] = mapped_column(
        _enum(MoocStatus, "mooc_status"), default=MoocStatus.REGISTERED, nullable=False
    )
    exam_date: Mapped[dt.date | None] = mapped_column()
    exam_city: Mapped[str | None] = mapped_column(String(80))
    exam_fee_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exam_fee_reference: Mapped[str | None] = mapped_column(String(80))
    certificate_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL")
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus, "mooc_verification_status"),
        default=VerificationStatus.PENDING, nullable=False,
    )
    verified_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    final_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    grade: Mapped[str | None] = mapped_column(String(10))
    remarks: Mapped[str | None] = mapped_column(Text)

    course_offering: Mapped["CourseOffering | None"] = relationship(lazy="joined")
    course: Mapped["Course | None"] = relationship(lazy="joined")

    @property
    def subject_title(self) -> str | None:
        """What the student is taking: NCC, the round's course, or the
        offering a registration made before rounds points at."""
        if self.option == MoocOption.NCC:
            return "NCC certification"
        if self.course is not None:
            return self.course.title
        return self.course_offering.course.title if self.course_offering else None
