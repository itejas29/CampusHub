"""Eligibility checks derived from curriculum configuration — never hard-coded.

Whether a student may see NPTEL, an Open Elective or a Minor is answered by
walking Program → Curriculum → CurriculumComponent for their current semester.
Nothing here mentions "ICT" or "Semester V".
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academics import (
    Course, CourseOffering, Curriculum, CurriculumComponent, as_utc,
)
from app.models.enums import ComponentType, OfferingStatus, SourceScope
from app.models.identity import Student
from app.models.minors import MinorProgram
from app.services import curriculum as curriculum_engine


@dataclass(slots=True)
class EligibilityResult:
    eligible: bool
    reasons: list[str]

    @classmethod
    def ok(cls) -> "EligibilityResult":
        return cls(True, [])

    @classmethod
    def blocked(cls, *reasons: str) -> "EligibilityResult":
        return cls(False, list(reasons))


def active_curriculum(db: Session, student: Student) -> Curriculum | None:
    """The curriculum version governing this student's batch.

    Delegates to `services.curriculum`, which resolves through the version's
    *batch window* rather than "the newest one that started before I did". That
    distinction is what keeps a 2022 ECE student on the 2020-24 structure while a
    2024 ECE student gets 2024-28.
    """
    return curriculum_engine.resolve_curriculum(db, student)


def components_for_semester(
    db: Session, student: Student, semester_number: int | None = None
) -> list[CurriculumComponent]:
    curriculum = active_curriculum(db, student)
    if curriculum is None:
        return []
    return curriculum_engine.components_for(db, curriculum, semester_number)


#: The sidebar section each kind of student-chosen slot is acted on in.
ELECTIVE_SECTIONS = {
    ComponentType.OPEN_ELECTIVE: "open_electives",
    ComponentType.PROGRAM_CORE_ELECTIVE: "core_electives",
    ComponentType.MOOC: "nptel",
}


def reached_elective_sections(components, current_semester: int) -> list[str]:
    """Elective sections that already concern a student, from their curriculum.

    A section applies once the curriculum has placed a slot of that kind in a
    semester the student has reached — the same unlock rule as
    `student_can_access_component`. A first-year in a programme whose first Open
    Elective sits in Semester IV is therefore offered none of them, and a
    curriculum with no MOOC slot at all never offers NPTEL. Past semesters keep
    their section: that is where an allocation already made is read.
    """
    reached = {
        c.component_type for c in components
        if c.semester_number <= current_semester
    }
    return [section for kind, section in ELECTIVE_SECTIONS.items() if kind in reached]


def student_can_access_component(
    student: Student, component: CurriculumComponent
) -> EligibilityResult:
    """A component unlocks in the semester the curriculum places it in."""
    if component.semester_number > student.current_semester:
        return EligibilityResult.blocked(
            f"{component.title} opens in semester {component.semester_number}; "
            f"you are in semester {student.current_semester}."
        )
    return EligibilityResult.ok()


def offering_allowed(
    db: Session, offering: CourseOffering, course: Course, student: Student,
    component: CurriculumComponent,
) -> bool:
    """Full check: the component's declarative rules *and* its source scope.

    Use this from the API. `offering_matches_scope` below is the scope half on
    its own, kept because it needs no session and carries the rule that the unit
    tests pin down.
    """
    return curriculum_engine.offering_matches_component(
        db, offering, course, student, component
    )


def offering_matches_scope(
    offering: CourseOffering, course: Course, student: Student,
    component: CurriculumComponent,
) -> bool:
    """Enforce "From Other School" / "From Other Department of FoET" rules."""
    scope = component.source_scope
    if scope == SourceScope.ANY:
        return True
    if scope == SourceScope.SAME_DEPARTMENT:
        return course.department_id == student.department_id
    if scope == SourceScope.OTHER_DEPARTMENT_FOET:
        return course.department_id != student.department_id
    if scope == SourceScope.OTHER_SCHOOL:
        # Owned by a different department, and outside the student's own school.
        return course.department_id != student.department_id
    if scope == SourceScope.EXTERNAL_PLATFORM:
        return course.platform is not None
    return True


def offering_window_open(offering: CourseOffering, now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(dt.timezone.utc)
    if offering.status != OfferingStatus.OPEN:
        return False
    opens_at = as_utc(offering.registration_opens_at)
    closes_at = as_utc(offering.registration_closes_at)
    if opens_at and now < opens_at:
        return False
    if closes_at and now > closes_at:
        return False
    return True


def check_minor_eligibility(
    student: Student, minor: MinorProgram, now: dt.datetime | None = None
) -> EligibilityResult:
    """All thresholds come from the MinorProgram row, so policy is configurable."""
    now = now or dt.datetime.now(dt.timezone.utc)
    reasons: list[str] = []

    if not minor.is_active:
        reasons.append("This minor is not currently offered.")
    if student.current_semester < minor.eligible_from_semester:
        reasons.append(
            f"Registration opens from semester {minor.eligible_from_semester} "
            f"(you are in semester {student.current_semester})."
        )
    # A minor is taken outside the student's own department.
    if minor.department_id == student.department_id:
        reasons.append("A minor must be taken from a department other than your own.")
    if minor.excluded_department_ids and student.department_id in minor.excluded_department_ids:
        reasons.append("Students of your department are not eligible for this minor.")
    if minor.min_cpi is not None:
        if student.cpi is None:
            reasons.append(f"A CPI of at least {minor.min_cpi} is required; "
                           "your CPI is not on record yet.")
        elif float(student.cpi) < float(minor.min_cpi):
            reasons.append(f"Requires a CPI of at least {minor.min_cpi} "
                           f"(yours is {student.cpi}).")
    if minor.max_backlogs is not None and student.backlog_count > minor.max_backlogs:
        reasons.append(
            f"Allowed backlogs: {minor.max_backlogs}; you currently have "
            f"{student.backlog_count}."
        )
    if minor.seats_available <= 0:
        reasons.append("No seats remain in this minor.")
    if minor.application_opens_at and now < minor.application_opens_at:
        reasons.append("Applications have not opened yet.")
    if minor.application_closes_at and now > minor.application_closes_at:
        reasons.append("The application window has closed.")

    return EligibilityResult(not reasons, reasons)
