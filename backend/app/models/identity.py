"""Users, roles, org structure, academic calendar, students and faculty."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String,
    Text, UniqueConstraint, false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import (
    AssignedRole, CoordinationDomain, Role, SemesterTerm, StudentStatus,
)

if TYPE_CHECKING:
    from app.models.academics import Program


def role_enum(*, name: str) -> SAEnum:
    return SAEnum(Role, native_enum=False, length=32, name=name,
                  values_callable=lambda e: [m.value for m in e])


class User(PKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[dt.datetime | None] = mapped_column()
    #: Set when the registrar issues a temporary password; nothing but choosing
    #: a new one is allowed until it is cleared (services/accounts.py).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False,
                                                       server_default=false(), nullable=False)
    #: Tokens issued before this moment are refused — a password change or reset
    #: signs the account out everywhere.
    sessions_valid_after: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


    role_links: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    student: Mapped["Student | None"] = relationship(back_populates="user", uselist=False)
    faculty: Mapped["Faculty | None"] = relationship(back_populates="user", uselist=False)

    @property
    def roles(self) -> list[Role]:
        return [link.role for link in self.role_links]

    def has_role(self, *roles: Role) -> bool:
        owned = set(self.roles)
        return any(r in owned for r in roles)


class UserRole(PKMixin, Base):
    """A user may hold several roles (e.g. FACULTY + INTERNSHIP_COORDINATOR)."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_roles_user_id_role"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[Role] = mapped_column(role_enum(name="role_enum"), nullable=False)
    scope_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )

    user: Mapped["User"] = relationship(back_populates="role_links")


class Department(PKMixin, TimestampMixin, Base):
    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50))
    # PDEU groups departments under schools/faculties, e.g. "FoET".
    school: Mapped[str] = mapped_column(String(120), nullable=False, default="FoET")
    description: Mapped[str | None] = mapped_column(Text)
    hod_faculty_id: Mapped[int | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL", use_alter=True)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    programs: Mapped[list["Program"]] = relationship(back_populates="department")


class AcademicYear(PKMixin, TimestampMixin, Base):
    __tablename__ = "academic_years"

    label: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # "2025-26"
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    semesters: Mapped[list["Semester"]] = relationship(back_populates="academic_year")


class Semester(PKMixin, TimestampMixin, Base):
    """A concrete run of semester `number` inside an academic year."""

    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint("academic_year_id", "number", name="uq_semesters_academic_year_id_number"),
    )

    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id", ondelete="CASCADE"), index=True, nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..8
    term: Mapped[SemesterTerm] = mapped_column(
        SAEnum(SemesterTerm, native_enum=False, length=16, name="semester_term"),
        nullable=False,
    )
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    academic_year: Mapped["AcademicYear"] = relationship(back_populates="semesters")

    @property
    def label(self) -> str:
        return f"Semester {self.number}"


class Faculty(PKMixin, TimestampMixin, Base):
    __tablename__ = "faculty"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    designation: Mapped[str] = mapped_column(String(100), nullable=False)
    # Publicly visible contact details (students see these on mentor cards).
    cabin: Mapped[str | None] = mapped_column(String(60))
    public_email: Mapped[str | None] = mapped_column(String(255))
    public_phone: Mapped[str | None] = mapped_column(String(20))
    specialization: Mapped[str | None] = mapped_column(String(255))
    qualification: Mapped[str | None] = mapped_column(String(150))
    profile_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(Text)
    is_mentor: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: A fictional persona for demonstrations — never a real PDEU faculty member.
    #: Screens label these so a demo cannot be mistaken for the real roster.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                          server_default="false")

    user: Mapped["User"] = relationship(back_populates="faculty")
    department: Mapped["Department"] = relationship(foreign_keys=[department_id])
    role_assignments: Mapped[list["FacultyRoleAssignment"]] = relationship(
        back_populates="faculty", cascade="all, delete-orphan", lazy="selectin"
    )

    def coordinates(self, domain: CoordinationDomain,
                    department_id: int | None = None) -> bool:
        """True when this faculty *coordinates* `domain` over `department_id`."""
        return scope_matches(self.role_assignments, domain, department_id,
                             role=AssignedRole.COORDINATOR)

    def mentors(self, domain: CoordinationDomain,
                department_id: int | None = None) -> bool:
        """True when this faculty is an assigned *mentor* for that scope.

        Independent of `coordinates()` — neither role implies the other.
        """
        return scope_matches(self.role_assignments, domain, department_id,
                             role=AssignedRole.MENTOR)


def scope_matches(assignments, domain: CoordinationDomain,
                  department_id: int | None = None,
                  role: AssignedRole = AssignedRole.COORDINATOR,
                  on: dt.date | None = None) -> bool:
    """Does any current assignment grant `role` over `domain` × `department_id`?

    Every assignment is considered, so a faculty member holding several roles
    keeps the union of them — a Mentor grant never cancels a Coordinator grant.
    Roles are matched exactly: being Mentor for CSSI does not make you its
    Coordinator, and coordinating Summer Internship grants nothing over CSSI.

    Kept free of ORM and session dependencies so the rule can be tested
    directly. ``department_id is None`` on the assignment means institution-wide
    and matches every department.
    """
    for assignment in assignments:
        if assignment.role != role or assignment.domain != domain:
            continue
        if not assignment.is_current(on):
            continue
        if assignment.department_id is None:
            return True
        if department_id is None or assignment.department_id == department_id:
            return True
    return False


def assignments_for(assignments, role: AssignedRole | None = None,
                    on: dt.date | None = None) -> list:
    """Every current assignment, optionally narrowed to one role."""
    return [
        a for a in assignments
        if a.is_current(on) and (role is None or a.role == role)
    ]


class FacultyRoleAssignment(PKMixin, TimestampMixin, Base):
    """Who coordinates what, for which department.

    The coarse ``Role`` says *what kind* of thing a user may do; this table says
    *over which slice*. A faculty member can hold several — e.g. Summer
    Internship coordinator for ICT and NPTEL coordinator for ICT — and two
    different faculty can coordinate the same domain for different departments.

    Only an administrator creates these rows; a coordinator then works inside
    the scope they grant (assigning mentors, approving submissions).
    """

    __tablename__ = "faculty_role_assignments"
    __table_args__ = (
        UniqueConstraint(
            "faculty_id", "role", "domain", "department_id", "academic_year_id",
            name="uq_faculty_role_assignments_faculty_domain_department",
        ),
        Index("ix_faculty_role_assignments_domain_dept", "domain", "department_id"),
        Index("ix_faculty_role_assignments_role", "role", "is_active"),
    )

    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Coordinator or Mentor. Independent grants — one never implies the other.
    role: Mapped[AssignedRole] = mapped_column(
        SAEnum(AssignedRole, native_enum=False, length=24, name="assigned_role",
               values_callable=lambda e: [m.value for m in e]),
        default=AssignedRole.COORDINATOR, nullable=False,
    )
    domain: Mapped[CoordinationDomain] = mapped_column(
        SAEnum(CoordinationDomain, native_enum=False, length=32,
               name="coordination_domain",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    #: NULL means institution-wide (every department).
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), index=True
    )
    #: NULL means it carries across academic years until revoked.
    academic_year_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_years.id", ondelete="SET NULL")
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[dt.datetime | None] = mapped_column()
    #: Optional validity window. NULL on either side means open-ended.
    starts_on: Mapped[dt.date | None] = mapped_column(Date)
    ends_on: Mapped[dt.date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    def is_current(self, on: dt.date | None = None) -> bool:
        """Active *and* inside its validity window."""
        if not self.is_active:
            return False
        today = on or dt.date.today()
        if self.starts_on and today < self.starts_on:
            return False
        if self.ends_on and today > self.ends_on:
            return False
        return True

    faculty: Mapped["Faculty"] = relationship(back_populates="role_assignments",
                                              lazy="joined")
    department: Mapped["Department | None"] = relationship(lazy="joined")


class Student(PKMixin, TimestampMixin, Base):
    __tablename__ = "students"
    __table_args__ = (
        Index("ix_students_program_semester", "program_id", "current_semester"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    roll_number: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    enrollment_number: Mapped[str | None] = mapped_column(String(30), unique=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    admission_year: Mapped[int] = mapped_column(Integer, nullable=False)
    current_semester: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    division: Mapped[str | None] = mapped_column(String(10))
    batch: Mapped[str | None] = mapped_column(String(20))
    # Snapshot values used for eligibility checks; the authoritative source will
    # be the examination system in a later phase.
    cpi: Mapped[float | None] = mapped_column(Numeric(4, 2))
    backlog_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[StudentStatus] = mapped_column(
        SAEnum(StudentStatus, native_enum=False, length=20, name="student_status"),
        default=StudentStatus.ACTIVE, nullable=False,
    )
    date_of_birth: Mapped[dt.date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    guardian_name: Mapped[str | None] = mapped_column(String(150))
    guardian_phone: Mapped[str | None] = mapped_column(String(20))

    user: Mapped["User"] = relationship(back_populates="student")
    program: Mapped["Program"] = relationship(foreign_keys=[program_id])
    department: Mapped["Department"] = relationship(foreign_keys=[department_id])
