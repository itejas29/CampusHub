"""Shapes for the unified student profile.

Sections are optional rather than always-present: a caller who may see the
personal details but not the evaluation gets `evaluations: []` and a
`visible_sections` list that says why, instead of a partially-filled object that
looks like the student has no marks.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.models.enums import StudentStatus


class ProfilePersonal(BaseModel):
    student_id: int
    full_name: str
    email: str
    phone: str | None = None
    roll_number: str
    enrollment_number: str | None = None
    program_name: str | None = None
    program_code: str | None = None
    department_code: str | None = None
    school: str | None = None
    batch: str | None = None
    division: str | None = None
    admission_year: int
    current_semester: int
    status: StudentStatus


class ProfileAcademic(BaseModel):
    curriculum_name: str | None = None
    curriculum_version: str | None = None
    curriculum_status: str | None = None
    batch_label: str | None = None
    #: CPI is shown on a profile, but it is an input to Minor eligibility only.
    cpi: float | None = None
    backlog_count: int = 0
    current_semester_components: list[dict] = Field(default_factory=list)
    elective_allocations: list[dict] = Field(default_factory=list)
    mooc_registrations: list[dict] = Field(default_factory=list)
    minor_name: str | None = None
    minor_status: str | None = None


class ProfileInternship(BaseModel):
    enrollment_id: int
    program_name: str
    program_type: str | None = None
    status: str
    organization: str | None = None
    faculty_mentor: str | None = None
    progress_percent: float = 0
    completed_items: int = 0
    total_items: int = 0


class ProfileDocument(BaseModel):
    enrollment_id: int
    group: str | None = None
    label: str
    document_type: str | None = None
    week: int | None = None
    #: NOT_SUBMITTED is synthesised, so a missing mandatory item stays visible
    #: rather than silently disappearing from the list.
    status: str = "NOT_SUBMITTED"
    is_mandatory: bool = True
    file_id: int | None = None
    #: A signed, expiring link — never a storage key.
    file_url: str | None = None
    submitted_at: dt.datetime | None = None
    reviewer_comment: str | None = None


class ProfileEvaluation(BaseModel):
    enrollment_id: int
    evaluator_role: str
    status: str
    total_marks: float | None = None
    max_marks: float | None = None
    remarks: str | None = None
    grade: str | None = None
    scores: list[dict] = Field(default_factory=list)


class ProfileMentor(BaseModel):
    faculty_id: int
    full_name: str | None = None
    email: str | None = None
    cabin: str | None = None
    designation: str | None = None
    department_code: str | None = None
    #: False when the caller may see who the mentor is but not what was said.
    meetings_visible: bool = False
    recent_meetings: list[dict] = Field(default_factory=list)


class StudentProfileOut(BaseModel):
    personal: ProfilePersonal
    academic: ProfileAcademic | None = None
    internships: list[ProfileInternship] = Field(default_factory=list)
    documents: list[ProfileDocument] = Field(default_factory=list)
    evaluations: list[ProfileEvaluation] = Field(default_factory=list)
    mentor: ProfileMentor | None = None
    #: What this caller was allowed to see, so the UI can explain a gap rather
    #: than rendering an empty tab that looks like missing data.
    visible_sections: list[str] = Field(default_factory=list)
