from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AssignedRole, CoordinationDomain, Role, StudentStatus
from app.schemas.common import ORMModel


class DepartmentBase(BaseModel):
    code: str = Field(max_length=20)
    name: str = Field(max_length=150)
    short_name: str | None = None
    school: str = "FoET"
    description: str | None = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    school: str | None = None
    description: str | None = None
    is_active: bool | None = None


class DepartmentOut(ORMModel, DepartmentBase):
    id: int
    is_active: bool
    student_count: int = 0
    faculty_count: int = 0
    program_count: int = 0


class ProgramOut(ORMModel):
    id: int
    code: str
    name: str
    short_name: str | None = None
    degree_type: str
    duration_years: int
    total_semesters: int
    department_id: int
    department_code: str | None = None
    #: "SoT" / "SoET" — Open Elective eligibility is written in schools, so the
    #: frontend needs it to explain why a course is or is not on offer.
    school: str | None = None
    curriculum_versions: int = 0
    is_active: bool


class AcademicYearOut(ORMModel):
    id: int
    label: str
    start_date: dt.date
    end_date: dt.date
    is_current: bool


class SemesterOut(ORMModel):
    id: int
    number: int
    term: str
    academic_year_id: int
    academic_year_label: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool


class StudentOut(ORMModel):
    id: int
    user_id: int
    full_name: str
    email: EmailStr
    phone: str | None = None
    avatar_url: str | None = None
    roll_number: str
    enrollment_number: str | None = None
    program_id: int
    program_name: str | None = None
    department_id: int
    department_code: str | None = None
    admission_year: int
    current_semester: int
    division: str | None = None
    batch: str | None = None
    cpi: float | None = None
    backlog_count: int
    status: StudentStatus


class StudentDetail(StudentOut):
    date_of_birth: dt.date | None = None
    gender: str | None = None
    address: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    mentor_name: str | None = None
    mentor_id: int | None = None


class StudentCreate(BaseModel):
    full_name: str = Field(max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    roll_number: str = Field(max_length=30)
    enrollment_number: str | None = None
    program_id: int
    department_id: int
    admission_year: int = Field(ge=2000, le=2100)
    current_semester: int = Field(default=1, ge=1, le=12)
    division: str | None = None
    batch: str | None = None
    phone: str | None = None
    cpi: float | None = Field(default=None, ge=0, le=10)


class StudentUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    current_semester: int | None = Field(default=None, ge=1, le=12)
    division: str | None = None
    batch: str | None = None
    cpi: float | None = Field(default=None, ge=0, le=10)
    backlog_count: int | None = Field(default=None, ge=0)
    status: StudentStatus | None = None
    address: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None


class FacultyOut(ORMModel):
    id: int
    user_id: int
    full_name: str
    email: EmailStr
    employee_code: str
    department_id: int
    department_code: str | None = None
    department_name: str | None = None
    designation: str
    cabin: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    specialization: str | None = None
    qualification: str | None = None
    avatar_url: str | None = None
    bio: str | None = None
    is_mentor: bool
    is_active: bool
    mentee_count: int = 0


class FacultyCreate(BaseModel):
    full_name: str = Field(max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    employee_code: str = Field(max_length=30)
    department_id: int
    designation: str = Field(max_length=100)
    cabin: str | None = None
    specialization: str | None = None
    qualification: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    is_mentor: bool = True
    extra_roles: list[Role] = Field(default_factory=list)


class FacultyUpdate(BaseModel):
    full_name: str | None = None
    designation: str | None = None
    cabin: str | None = None
    specialization: str | None = None
    qualification: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    bio: str | None = None
    is_mentor: bool | None = None
    is_active: bool | None = None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    cabin: str | None = None
    public_email: str | None = None
    public_phone: str | None = None
    specialization: str | None = None
    bio: str | None = None


# ── coordinator role assignments ──────────────────────────────────────────
class RoleAssignmentOut(ORMModel):
    id: int
    faculty_id: int
    faculty_name: str | None = None
    employee_code: str | None = None
    faculty_department_code: str | None = None
    designation: str | None = None
    role: AssignedRole = AssignedRole.COORDINATOR
    role_label: str | None = None
    domain: CoordinationDomain
    domain_label: str | None = None
    department_id: int | None = None
    department_code: str | None = None
    department_name: str | None = None
    is_institution_wide: bool = False
    academic_year_id: int | None = None
    academic_year_label: str | None = None
    assigned_by_name: str | None = None
    assigned_at: dt.datetime | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    is_active: bool
    #: Active *and* inside its validity window — what the Status column shows.
    is_current: bool = True
    notes: str | None = None


class RoleAssignmentCreate(BaseModel):
    faculty_id: int
    #: Coordinator or Mentor. Independent grants — neither implies the other.
    role: AssignedRole = AssignedRole.COORDINATOR
    domain: CoordinationDomain
    #: Omit for an institution-wide assignment.
    department_id: int | None = None
    academic_year_id: int | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    notes: str | None = Field(default=None, max_length=500)


class RoleAssignmentUpdate(BaseModel):
    """Edit an existing assignment. Every field is optional."""

    department_id: int | None = None
    academic_year_id: int | None = None
    starts_on: dt.date | None = None
    ends_on: dt.date | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


class RoleDefinition(BaseModel):
    """A role an administrator may grant, and what it permits inside a scope."""

    value: str
    label: str
    description: str


class DomainCoverage(BaseModel):
    """One row of the coverage matrix: a domain × department cell."""

    domain: CoordinationDomain
    domain_label: str | None = None
    department_id: int | None = None
    department_code: str | None = None
    department_name: str | None = None
    coordinators: list[RoleAssignmentOut] = Field(default_factory=list)
    mentors: list[RoleAssignmentOut] = Field(default_factory=list)


class RoleMatrix(BaseModel):
    """Who coordinates what, and where nobody does."""

    domains: list[str]
    roles: list[RoleDefinition] = Field(default_factory=list)
    coverage: list[DomainCoverage] = Field(default_factory=list)
    gaps: list[dict] = Field(default_factory=list)
    #: One row per faculty member listing ALL their active grants, so a person
    #: holding Coordinator and Mentor roles reads as one entry, not two.
    faculty_summary: list[dict] = Field(default_factory=list)
