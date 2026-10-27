"""One internship engine, configured per programme.

CSSI and Summer Internship are *rows*, not codebases: they differ only in their
``InternshipProgram`` configuration (stages, group size, report frequency,
evaluation criteria).  Adding "Research Internship" later is seed data.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import (
    InternshipWindowKind,
    DocumentType, EnrollmentStatus, EvaluationStatus, EvaluatorRole, InternshipType,
    OrganizationType, ProgramStatus, ReportFrequency, ReportType, StageStatus,
    SubmissionStatus,
)


def _enum(e, name: str, length: int = 40) -> SAEnum:
    return SAEnum(e, native_enum=False, length=length, name=name,
                  values_callable=lambda x: [m.value for m in x])


class Organization(PKMixin, TimestampMixin, Base):
    """NGO / company / lab hosting an internship."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    type: Mapped[OrganizationType] = mapped_column(
        _enum(OrganizationType, "organization_type"), default=OrganizationType.NGO,
        nullable=False,
    )
    field_of_work: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(80), index=True)
    district: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(80), default="India", nullable=False)
    pincode: Mapped[str | None] = mapped_column(String(12))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    contact_person: Mapped[str | None] = mapped_column(String(150))
    contact_designation: Mapped[str | None] = mapped_column(String(120))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class InternshipProgram(PKMixin, TimestampMixin, Base):
    __tablename__ = "internship_programs"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    type: Mapped[InternshipType] = mapped_column(
        _enum(InternshipType, "internship_type"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL"), index=True
    )
    semester_id: Mapped[int | None] = mapped_column(
        ForeignKey("semesters.id", ondelete="SET NULL")
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    #: The semester in which the work is carried out and submissions open.
    target_semester: Mapped[int | None] = mapped_column(Integer)
    #: When the coordinator *floats* the programme. Students in this semester see
    #: what is coming and can start finding a host, but cannot submit yet.
    #: CSSI is announced in Semester II and carried out in Semester III.
    announce_from_semester: Mapped[int | None] = mapped_column(Integer)
    #: Last semester the programme is shown at all. NULL means no upper bound,
    #: which is how Summer Internship behaves for Semester VII and beyond.
    visible_to_semester: Mapped[int | None] = mapped_column(Integer)
    credits: Mapped[float] = mapped_column(Numeric(4, 1), default=2, nullable=False)
    # ── configuration ─────────────────────────────────────────────────────
    requires_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_group_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    requires_organization: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_organization_types: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    report_frequency: Mapped[ReportFrequency] = mapped_column(
        _enum(ReportFrequency, "report_frequency"), default=ReportFrequency.NONE,
        nullable=False,
    )
    expected_report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_industry_mentor: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # ── schedule ──────────────────────────────────────────────────────────
    registration_opens_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[ProgramStatus] = mapped_column(
        _enum(ProgramStatus, "program_status"), default=ProgramStatus.DRAFT, nullable=False
    )
    coordinator_faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL")
    )

    stages: Mapped[list["InternshipStage"]] = relationship(
        back_populates="program", cascade="all, delete-orphan",
        order_by="InternshipStage.sequence",
    )
    groups: Mapped[list["InternshipGroup"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    criteria: Mapped[list["EvaluationCriteria"]] = relationship(
        back_populates="program", cascade="all, delete-orphan",
        order_by="EvaluationCriteria.sequence",
    )


class InternshipStage(PKMixin, TimestampMixin, Base):
    """One step of the workflow stepper, defined as data per programme."""

    __tablename__ = "internship_stages"
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="uq_internship_stages_program_id_code"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("internship_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_document: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_type: Mapped[DocumentType | None] = mapped_column(
        _enum(DocumentType, "stage_document_type")
    )
    # Who moves this stage forward: STUDENT, FACULTY, COORDINATOR.
    owner_role: Mapped[str] = mapped_column(String(30), default="STUDENT", nullable=False)
    due_offset_days: Mapped[int | None] = mapped_column(Integer)

    program: Mapped["InternshipProgram"] = relationship(back_populates="stages")


class InternshipWindow(PKMixin, TimestampMixin, Base):
    """A dated window the programme's coordinator opens, with the message that
    went to students when they did.

    The window is the authority for what a student or mentor may do in that
    step — not the semester alone, and never the browser: every write checks
    it server-side, so a stale tab cannot submit after the deadline. One row per
    kind per programme; extending or reopening moves its dates rather than
    adding a second window.
    """

    __tablename__ = "internship_windows"
    __table_args__ = (
        UniqueConstraint("program_id", "kind", name="uq_internship_windows_program_id_kind"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("internship_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[InternshipWindowKind] = mapped_column(
        _enum(InternshipWindowKind, "internship_window_kind"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    #: What the coordinator told students: what the step is, what to do.
    message: Mapped[str] = mapped_column(Text, nullable=False)
    opens_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Semester of the students a REGISTRATION window admits — the semester
    #: before the programme runs, or the semester it runs in.
    cohort_semester: Mapped[int | None] = mapped_column(Integer)
    #: PRESENTATION: posters are due to the mentor by this moment.
    submission_due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: PRESENTATION: the presentation day(s).
    presentation_from: Mapped[dt.date | None] = mapped_column(Date)
    presentation_to: Mapped[dt.date | None] = mapped_column(Date)
    #: Set when the coordinator closes it before `closes_at`.
    closed_early_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    opened_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    def is_open_at(self, now: dt.datetime) -> bool:
        return (self.closed_early_at is None
                and _aware(self.opens_at) <= now < _aware(self.closes_at))

    def state_at(self, now: dt.datetime) -> str:
        """SCHEDULED, OPEN or CLOSED — derived, so it can never disagree with the clock."""
        if self.is_open_at(now):
            return "OPEN"
        if self.closed_early_at is None and now < _aware(self.opens_at):
            return "SCHEDULED"
        return "CLOSED"


def _aware(value: dt.datetime) -> dt.datetime:
    """SQLite hands back naive datetimes; treat them as the UTC they were stored as."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


class InternshipGroup(PKMixin, TimestampMixin, Base):
    """CSSI-style faculty group. Optional — Summer Internship leaves it null."""

    __tablename__ = "internship_groups"
    __table_args__ = (
        UniqueConstraint("program_id", "name", name="uq_internship_groups_program_id_name"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("internship_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL"), index=True
    )
    capacity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    meeting_schedule: Mapped[str | None] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text)

    program: Mapped["InternshipProgram"] = relationship(back_populates="groups")
    faculty: Mapped["Faculty | None"] = relationship(lazy="joined")  # noqa: F821


class ProjectTeam(PKMixin, TimestampMixin, Base):
    """Students doing one project together (Semester VII / VIII).

    Not an `InternshipGroup`: a group is a faculty-led cohort the coordinator
    forms (CSSI); a team is formed by the students themselves and shares one
    guide. Marks stay individual.
    """

    __tablename__ = "project_teams"

    program_id: Mapped[int] = mapped_column(
        ForeignKey("internship_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    leader_enrollment_id: Mapped[int | None] = mapped_column(
        ForeignKey("internship_enrollments.id", ondelete="SET NULL", use_alter=True,
                   name="fk_project_teams_leader_enrollment_id")
    )


class InternshipEnrollment(PKMixin, TimestampMixin, Base):
    """One student's participation in one internship programme."""

    __tablename__ = "internship_enrollments"
    __table_args__ = (
        UniqueConstraint("program_id", "student_id",
                         name="uq_internship_enrollments_program_id_student_id"),
        Index("ix_internship_enrollments_mentor", "mentor_faculty_id", "status"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("internship_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("internship_groups.id", ondelete="SET NULL"), index=True
    )
    mentor_faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL"), index=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        _enum(EnrollmentStatus, "enrollment_status"),
        default=EnrollmentStatus.REGISTERED, nullable=False,
    )
    current_stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("internship_stages.id", ondelete="SET NULL")
    )
    registered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    # Summer-internship industry mentor (free text; not a portal user).
    #: The track the student chose, for a programme that offers several
    #: (`config["tracks"]`) — Semester VIII: in-house project or industry.
    track: Mapped[str | None] = mapped_column(String(40))
    #: The project team the student belongs to, if any.
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_teams.id", ondelete="SET NULL"), index=True
    )
    #: Faculty ids, most preferred first (`config["guide_preferences"]`).
    guide_preferences: Mapped[list] = mapped_column(JSON, default=list, server_default="[]",
                                                    nullable=False)
    industry_mentor_name: Mapped[str | None] = mapped_column(String(150))
    industry_mentor_email: Mapped[str | None] = mapped_column(String(255))
    industry_mentor_phone: Mapped[str | None] = mapped_column(String(20))
    industry_mentor_designation: Mapped[str | None] = mapped_column(String(120))
    industry_mentor_feedback: Mapped[str | None] = mapped_column(Text)

    #: Presentation slot, allocated by the coordinator once the certificate is
    #: verified — for CSSI this is the last step of the Semester III workflow.
    presentation_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    presentation_venue: Mapped[str | None] = mapped_column(String(120))
    presentation_panel: Mapped[str | None] = mapped_column(String(180))
    stipend: Mapped[float | None] = mapped_column(Numeric(10, 2))
    location: Mapped[str | None] = mapped_column(String(150))
    final_marks: Mapped[float | None] = mapped_column(Numeric(6, 2))
    final_grade: Mapped[str | None] = mapped_column(String(10))
    coordinator_remarks: Mapped[str | None] = mapped_column(Text)

    student: Mapped["Student"] = relationship(lazy="joined")  # noqa: F821
    program: Mapped["InternshipProgram"] = relationship(lazy="joined")
    group: Mapped["InternshipGroup | None"] = relationship()
    organization: Mapped["Organization | None"] = relationship(lazy="joined")
    mentor: Mapped["Faculty | None"] = relationship(lazy="joined")  # noqa: F821
    stage_progress: Mapped[list["EnrollmentStageProgress"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )
    project: Mapped["InternshipProject | None"] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan", uselist=False
    )


class EnrollmentStageProgress(PKMixin, TimestampMixin, Base):
    __tablename__ = "enrollment_stage_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "stage_id",
                         name="uq_enrollment_stage_progress_enrollment_id_stage_id"),
    )

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("internship_enrollments.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("internship_stages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[StageStatus] = mapped_column(
        _enum(StageStatus, "stage_status"), default=StageStatus.PENDING, nullable=False
    )
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    remarks: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    enrollment: Mapped["InternshipEnrollment"] = relationship(back_populates="stage_progress")
    stage: Mapped["InternshipStage"] = relationship(lazy="joined")


class InternshipProject(PKMixin, TimestampMixin, Base):
    """The "Project Details" tab. ``extra`` keeps future fields migration-free."""

    __tablename__ = "internship_projects"

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("internship_enrollments.id", ondelete="CASCADE"), unique=True,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(250))
    problem_statement: Mapped[str | None] = mapped_column(Text)
    approach: Mapped[str | None] = mapped_column(Text)
    outcomes: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[str | None] = mapped_column(String(300))
    beneficiaries: Mapped[str | None] = mapped_column(String(300))
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    enrollment: Mapped["InternshipEnrollment"] = relationship(back_populates="project")


class InternshipDocument(PKMixin, TimestampMixin, Base):
    __tablename__ = "internship_documents"

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("internship_enrollments.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    stage_id: Mapped[int | None] = mapped_column(
        ForeignKey("internship_stages.id", ondelete="SET NULL")
    )
    document_type: Mapped[DocumentType] = mapped_column(
        _enum(DocumentType, "internship_document_type"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200))
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Set for periodic submissions so "Week 3 report" is addressable directly.
    week_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[SubmissionStatus] = mapped_column(
        _enum(SubmissionStatus, "document_status"),
        default=SubmissionStatus.SUBMITTED, nullable=False,
    )
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: Review trail — who decided, when, and why.
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)
    #: Incremented when a student replaces a rejected submission.
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)

    file: Mapped["StoredFile"] = relationship(lazy="joined")  # noqa: F821
    enrollment: Mapped["InternshipEnrollment"] = relationship()
    stage: Mapped["InternshipStage | None"] = relationship()

    @property
    def is_satisfied(self) -> bool:
        """Does this submission satisfy its requirement?"""
        from app.models.enums import SATISFYING_STATUSES

        return self.status in SATISFYING_STATUSES


class InternshipReport(PKMixin, TimestampMixin, Base):
    __tablename__ = "internship_reports"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "report_type", "sequence_number",
                         name="uq_internship_reports_enrollment_id_report_type_sequence"),
    )

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("internship_enrollments.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    report_type: Mapped[ReportType] = mapped_column(
        _enum(ReportType, "report_type"), default=ReportType.WEEKLY, nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    period_end: Mapped[dt.date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    tasks_completed: Mapped[str | None] = mapped_column(Text)
    challenges: Mapped[str | None] = mapped_column(Text)
    next_plan: Mapped[str | None] = mapped_column(Text)
    hours_spent: Mapped[float | None] = mapped_column(Numeric(6, 2))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    status: Mapped[SubmissionStatus] = mapped_column(
        _enum(SubmissionStatus, "report_status"),
        default=SubmissionStatus.DRAFT, nullable=False,
    )
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    feedback: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    @property
    def is_satisfied(self) -> bool:
        from app.models.enums import SATISFYING_STATUSES

        return self.status in SATISFYING_STATUSES


class EvaluationCriteria(PKMixin, TimestampMixin, Base):
    """Data-driven rubric. The frontend renders whatever rows exist here."""

    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="uq_evaluation_criteria_program_id_code"),
    )

    program_id: Mapped[int] = mapped_column(
        ForeignKey("internship_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    max_marks: Mapped[float] = mapped_column(Numeric(6, 2), default=10, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(5, 2), default=1, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    evaluator_role: Mapped[EvaluatorRole] = mapped_column(
        _enum(EvaluatorRole, "evaluator_role"), default=EvaluatorRole.FACULTY_MENTOR,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    program: Mapped["InternshipProgram"] = relationship(back_populates="criteria")


class InternshipEvaluation(PKMixin, TimestampMixin, Base):
    __tablename__ = "internship_evaluations"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "evaluator_user_id", "evaluation_round",
                         name="uq_internship_evaluations_enrollment_id_evaluator_round"),
    )

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("internship_enrollments.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    evaluator_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    evaluator_role: Mapped[EvaluatorRole] = mapped_column(
        _enum(EvaluatorRole, "evaluation_evaluator_role"),
        default=EvaluatorRole.FACULTY_MENTOR, nullable=False,
    )
    evaluation_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        _enum(EvaluationStatus, "evaluation_status"),
        default=EvaluationStatus.PENDING, nullable=False,
    )
    is_absent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_marks: Mapped[float | None] = mapped_column(Numeric(6, 2))
    max_marks: Mapped[float | None] = mapped_column(Numeric(6, 2))
    grade: Mapped[str | None] = mapped_column(String(10))
    comments: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    scores: Mapped[list["EvaluationScore"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan", lazy="selectin"
    )


class EvaluationScore(PKMixin, TimestampMixin, Base):
    __tablename__ = "internship_evaluation_scores"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "criteria_id",
                         name="uq_internship_evaluation_scores_evaluation_id_criteria_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("internship_evaluations.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    criteria_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_criteria.id", ondelete="CASCADE"), nullable=False
    )
    marks: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_absent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)

    evaluation: Mapped["InternshipEvaluation"] = relationship(back_populates="scores")
    criteria: Mapped["EvaluationCriteria"] = relationship(lazy="joined")
