"""Minor specialization: catalogue, application, allocation and progress."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String,
    Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import (
    MinorApplicationStatus, MinorCourseResultStatus, MinorEnrollmentStatus,
)


def _enum(e, name: str, length: int = 40) -> SAEnum:
    return SAEnum(e, native_enum=False, length=length, name=name,
                  values_callable=lambda x: [m.value for m in x])


class MinorProgram(PKMixin, TimestampMixin, Base):
    """A minor offered by a department. Every eligibility knob is configurable
    so faculty-provided policy can be applied without a code change."""

    __tablename__ = "minor_programs"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)
    total_credits: Mapped[float] = mapped_column(Numeric(4, 1), default=18, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    seats_filled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # ── configurable eligibility ──────────────────────────────────────────
    eligible_from_semester: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    min_cpi: Mapped[float | None] = mapped_column(Numeric(4, 2))
    max_backlogs: Mapped[int | None] = mapped_column(Integer)
    # Departments whose students may NOT take this minor (usually the owner).
    excluded_department_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    allocation_strategy: Mapped[str] = mapped_column(
        String(60), default="manual", nullable=False
    )
    rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    application_opens_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    application_closes_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    coordinator_faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped["Department"] = relationship(lazy="joined")  # noqa: F821
    courses: Mapped[list["MinorCourse"]] = relationship(
        back_populates="minor_program", cascade="all, delete-orphan",
        order_by="MinorCourse.sequence",
    )

    @property
    def seats_available(self) -> int:
        return max(self.capacity - self.seats_filled, 0)


class MinorCourse(PKMixin, TimestampMixin, Base):
    __tablename__ = "minor_courses"
    __table_args__ = (
        UniqueConstraint("minor_program_id", "course_id",
                         name="uq_minor_courses_minor_program_id_course_id"),
    )

    minor_program_id: Mapped[int] = mapped_column(
        ForeignKey("minor_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Offset from the semester in which the minor starts (1 = first minor sem).
    semester_offset: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    minor_program: Mapped["MinorProgram"] = relationship(back_populates="courses")
    course: Mapped["Course"] = relationship(lazy="joined")  # noqa: F821


class MinorApplication(PKMixin, TimestampMixin, Base):
    __tablename__ = "minor_applications"
    __table_args__ = (
        UniqueConstraint("student_id", "minor_program_id", "academic_year_id",
                         name="uq_minor_applications_student_id_minor_program_id"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    minor_program_id: Mapped[int] = mapped_column(
        ForeignKey("minor_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL")
    )
    preference_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[MinorApplicationStatus] = mapped_column(
        _enum(MinorApplicationStatus, "minor_application_status"),
        default=MinorApplicationStatus.SUBMITTED, nullable=False,
    )
    # Snapshot at submission time — merit is judged on these, not on live values.
    cpi_at_application: Mapped[float | None] = mapped_column(Numeric(4, 2))
    backlogs_at_application: Mapped[int | None] = mapped_column(Integer)
    semester_at_application: Mapped[int | None] = mapped_column(Integer)
    motivation: Mapped[str | None] = mapped_column(Text)
    allocation_score: Mapped[float | None] = mapped_column(Numeric(8, 3))
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    remarks: Mapped[str | None] = mapped_column(Text)

    minor_program: Mapped["MinorProgram"] = relationship(lazy="joined")


class MinorEnrollment(PKMixin, TimestampMixin, Base):
    """Created once an application is allocated; tracks minor progress."""

    __tablename__ = "minor_enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "minor_program_id",
                         name="uq_minor_enrollments_student_id_minor_program_id"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True, nullable=False
    )
    minor_program_id: Mapped[int] = mapped_column(
        ForeignKey("minor_programs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("minor_applications.id", ondelete="SET NULL")
    )
    status: Mapped[MinorEnrollmentStatus] = mapped_column(
        _enum(MinorEnrollmentStatus, "minor_enrollment_status"),
        default=MinorEnrollmentStatus.ACTIVE, nullable=False,
    )
    started_semester: Mapped[int | None] = mapped_column(Integer)
    credits_completed: Mapped[float] = mapped_column(Numeric(4, 1), default=0, nullable=False)
    completed_course_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)

    minor_program: Mapped["MinorProgram"] = relationship(lazy="joined")


class MinorCourseResult(PKMixin, TimestampMixin, Base):
    """A minor student's result in one of the minor's courses.

    Recorded by the minor's coordinator. Marks and grade are stored as the
    department gives them — no grading scale is assumed here.
    """

    __tablename__ = "minor_course_results"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "minor_course_id",
                         name="uq_minor_course_results_enrollment_course"),
    )

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("minor_enrollments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    minor_course_id: Mapped[int] = mapped_column(
        ForeignKey("minor_courses.id", ondelete="CASCADE"), nullable=False
    )
    marks: Mapped[float | None] = mapped_column(Numeric(5, 2))
    grade: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[MinorCourseResultStatus] = mapped_column(
        _enum(MinorCourseResultStatus, "minor_course_result_status"),
        default=MinorCourseResultStatus.IN_PROGRESS, nullable=False,
    )
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    recorded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class MinorFeePayment(PKMixin, TimestampMixin, Base):
    """A minor student's fee for one semester, recorded as paid by the department."""

    __tablename__ = "minor_fee_payments"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "semester",
                         name="uq_minor_fee_payments_enrollment_semester"),
    )

    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("minor_enrollments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(80))
    paid_on: Mapped[dt.date | None] = mapped_column(Date)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

