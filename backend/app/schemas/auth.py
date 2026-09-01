from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class StudentContext(ORMModel):
    id: int
    roll_number: str
    program_id: int
    program_name: str | None = None
    department_id: int
    department_code: str | None = None
    current_semester: int
    division: str | None = None
    batch: str | None = None
    cpi: float | None = None
    backlog_count: int = 0
    admission_year: int


class CoordinationOut(ORMModel):
    #: COORDINATOR or MENTOR — independent grants over the same scope shape.
    role: str = "COORDINATOR"
    domain: str
    department_id: int | None = None
    department_code: str | None = None
    department_name: str | None = None
    is_institution_wide: bool = False


class FacultyContext(ORMModel):
    id: int
    employee_code: str
    department_id: int
    department_code: str | None = None
    designation: str
    cabin: str | None = None
    is_mentor: bool = True
    #: Domains this faculty coordinates, and over which department.
    coordinations: list[CoordinationOut] = Field(default_factory=list)
    #: Internship types they actually mentor students for — drives navigation.
    mentors_programs: list[str] = Field(default_factory=list)


class CurrentUser(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    phone: str | None = None
    avatar_url: str | None = None
    is_active: bool
    roles: list[Role]
    permissions: list[str]
    student: StudentContext | None = None
    faculty: FacultyContext | None = None
    academic_year: str | None = None
    current_semester_label: str | None = None
    last_login_at: dt.datetime | None = None


class AuthResponse(BaseModel):
    tokens: TokenPair
    user: CurrentUser
