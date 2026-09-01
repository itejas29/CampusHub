"""The curriculum engine: one place that answers "what applies to this student?".

Every screen that needs to know whether a student sees an Open Elective, an
NPTEL slot, a Minor or an internship asks this module. Nothing here names a
programme or a semester number — the answer is walked out of the data:

    Student
      └─ Program
           └─ Curriculum      chosen by the student's *admission batch*
                └─ Semester
                     └─ CurriculumComponent
                          └─ eligibility rules

The batch step is the one that is easy to skip and expensive to get wrong. Two
ECE students sitting in the same Semester V lecture hall can be governed by two
different curricula — the 2020-24 structure has no MOOC component at all — so
resolution must go through `Curriculum.governs_batch`, never through
``student.department + semester``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academics import (
    Course, CourseOffering, Curriculum, CurriculumComponent, Program, ProgramDivision,
)
from app.models.enums import ComponentType, CurriculumStatus, SourceScope
from app.models.identity import Department, Student


# ── curriculum resolution ──────────────────────────────────────────────────
def resolve_curriculum(db: Session, student: Student,
                       *, allow_unpublished: bool = False) -> Curriculum | None:
    """The curriculum version governing this student's batch.

    Published versions whose batch window contains the student's admission year
    win. When several match (a data error, or an overlapping revision) the most
    recent `effective_from_year` is used, which is the newest structure the
    student could legitimately be on.

    When no window contains the student — a batch admitted before anything was
    recorded, say — it falls back to the newest *open-ended* version, so they see
    the structure currently in force rather than an empty screen. A version whose
    window has been closed is never used as a fallback: handing a 2024 student a
    2016-19 curriculum that has been explicitly superseded would be worse than
    admitting there is none. Nor does it ever cross into another programme.
    """
    stmt = select(Curriculum).where(Curriculum.program_id == student.program_id)
    if not allow_unpublished:
        stmt = stmt.where(Curriculum.status == CurriculumStatus.PUBLISHED)
    candidates = list(db.scalars(stmt.order_by(Curriculum.effective_from_year.desc())))

    for curriculum in candidates:
        if curriculum.governs_batch(student.admission_year):
            return curriculum
    for curriculum in candidates:
        if curriculum.effective_to_year is None:
            return curriculum
    return None


def curriculum_versions(db: Session, program_id: int) -> list[Curriculum]:
    """Every version recorded for a programme, newest batch first.

    Historical versions are kept, never deleted — a graduating cohort must keep
    seeing the structure it was admitted under.
    """
    return list(db.scalars(
        select(Curriculum)
        .where(Curriculum.program_id == program_id)
        .order_by(Curriculum.effective_from_year.desc(), Curriculum.version)
    ))


def components_for(db: Session, curriculum: Curriculum,
                   semester_number: int | None = None,
                   component_type: ComponentType | None = None,
                   ) -> list[CurriculumComponent]:
    stmt = select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == curriculum.id
    )
    if semester_number is not None:
        stmt = stmt.where(CurriculumComponent.semester_number == semester_number)
    if component_type is not None:
        stmt = stmt.where(CurriculumComponent.component_type == component_type)
    return list(db.scalars(stmt.order_by(
        CurriculumComponent.semester_number, CurriculumComponent.sequence)))


# ── the eligibility answer ─────────────────────────────────────────────────
@dataclass(slots=True)
class ComponentAvailability:
    """One curriculum requirement, resolved for one student."""

    component: CurriculumComponent
    is_unlocked: bool                 # the semester has arrived
    is_current: bool                  # it is *this* semester's requirement
    reasons: list[str] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        if not self.component.is_elective:
            return "Core"
        if self.is_current:
            return "Action needed"
        if self.is_unlocked:
            return "Open"
        return "Upcoming"


@dataclass(slots=True)
class StudentCurriculumContext:
    """Everything the dashboard, elective and internship screens need."""

    student: Student
    curriculum: Curriculum | None
    program: Program | None
    available: list[ComponentAvailability]

    def of_type(self, *types: ComponentType) -> list[ComponentAvailability]:
        return [a for a in self.available if a.component.component_type in types]

    @property
    def current_semester_components(self) -> list[ComponentAvailability]:
        return [a for a in self.available if a.is_current]

    def has(self, component_type: ComponentType) -> bool:
        """Does this student's curriculum contain such a component at all?

        This is the question the dashboard must ask before offering NPTEL or an
        internship — not "is it semester five".
        """
        return any(a.component.component_type == component_type for a in self.available)


def build_context(db: Session, student: Student,
                  *, up_to_current_semester: bool = False) -> StudentCurriculumContext:
    """Resolve the whole curriculum for one student, annotated with progress."""
    curriculum = resolve_curriculum(db, student)
    program = db.get(Program, student.program_id)
    if curriculum is None:
        return StudentCurriculumContext(student, None, program, [])

    available: list[ComponentAvailability] = []
    for component in components_for(db, curriculum):
        unlocked = component.semester_number <= student.current_semester
        if up_to_current_semester and not unlocked:
            continue
        reasons: list[str] = []
        if not unlocked:
            reasons.append(
                f"{component.title} opens in semester {component.semester_number}; "
                f"you are in semester {student.current_semester}."
            )
        available.append(ComponentAvailability(
            component=component, is_unlocked=unlocked,
            is_current=component.semester_number == student.current_semester,
            reasons=reasons,
        ))
    return StudentCurriculumContext(student, curriculum, program, available)


def eligible_components(db: Session, student: Student,
                        component_type: ComponentType | None = None,
                        ) -> list[CurriculumComponent]:
    """Components the student may act on right now.

    The single entry point every page should use, so eligibility is never
    re-derived (and never re-guessed) screen by screen.
    """
    context = build_context(db, student, up_to_current_semester=True)
    items = [a.component for a in context.available if a.is_unlocked]
    if component_type is not None:
        items = [c for c in items if c.component_type == component_type]
    return items


# ── cross-programme scope, for Open Electives ──────────────────────────────
# Scope is evaluated once per *offering*, and a student's elective list can hold
# a hundred of them. Resolving the same handful of departments and programmes
# for each one turned one screen into ~220 queries, so the lookups are memoised
# for the life of the session — these rows do not change mid-request.
def _lookup_cache(db: Session, bucket: str) -> dict:
    cache = db.info.setdefault("_scope_cache", {})
    return cache.setdefault(bucket, {})


def _department(db: Session, department_id: int | None) -> "Department | None":
    if department_id is None:
        return None
    cache = _lookup_cache(db, "departments")
    if department_id not in cache:
        cache[department_id] = db.get(Department, department_id)
    return cache[department_id]


def _program(db: Session, program_id: int | None) -> "Program | None":
    if program_id is None:
        return None
    cache = _lookup_cache(db, "programs")
    if program_id not in cache:
        cache[program_id] = db.get(Program, program_id)
    return cache[program_id]


def _department_school(db: Session, department_id: int | None) -> str | None:
    department = _department(db, department_id)
    return department.school if department else None


def offering_matches_component(
    db: Session, offering: CourseOffering, course: Course, student: Student,
    component: CurriculumComponent,
) -> bool:
    """May this student choose this offering for this curriculum slot?

    Two layers, in order:

    1. Declarative rules on the component (`eligibility`) — schools, departments
       and programmes, which is what the official Open Elective rule is actually
       written in: *"offered to the students enrolled in B.Tech. programs of
       School of Technology other than Electrical Engineering."*
    2. `source_scope`, the coarse fallback, for components with no explicit rule.

    Rules are AND-ed. An empty rule set means "not constrained by that key".
    """
    rules = component.eligibility or {}
    course_school = _department_school(db, course.department_id) or course.offering_school
    student_department = _department(db, student.department_id)
    student_school = student_department.school if student_department else None
    student_program = _program(db, student.program_id)
    program_code = student_program.code if student_program else None

    if rules:
        schools = rules.get("eligible_schools")
        if schools and course_school not in schools:
            return False
        departments = rules.get("eligible_departments")
        if departments:
            code = _department_code(db, course.department_id)
            if code not in departments:
                return False
        excluded = rules.get("excluded_departments") or []
        if student_department and student_department.code in excluded:
            return False
        programs = rules.get("eligible_programs")
        if programs and program_code not in programs:
            return False
        if program_code in (rules.get("excluded_programs") or []):
            return False
        if rules.get("exclude_own_department") and \
                course.department_id == student.department_id:
            return False
        if rules.get("exclude_own_program"):
            # A course owned by the student's own programme's department.
            if course.department_id == student.department_id:
                return False

    scope = component.source_scope
    if scope == SourceScope.ANY:
        return True
    if scope == SourceScope.SAME_DEPARTMENT:
        return course.department_id == student.department_id
    if scope == SourceScope.OTHER_DEPARTMENT_FOET:
        return course.department_id != student.department_id
    if scope == SourceScope.OTHER_SCHOOL:
        # Owned outside the student's own school — the literal reading of
        # "From Other School". Falls back to the department test when the
        # course's school is unknown.
        if course_school and student_school:
            return course_school != student_school
        return course.department_id != student.department_id
    if scope == SourceScope.EXTERNAL_PLATFORM:
        return course.platform is not None
    return True


def _department_code(db: Session, department_id: int | None) -> str | None:
    department = _department(db, department_id)
    return department.code if department else None


# ── divisions ──────────────────────────────────────────────────────────────
def divisions_for(db: Session, program_id: int,
                  admission_year: int | None = None) -> list[str]:
    """The division names actually configured for a programme (and batch).

    Returns [] when none are configured, which the allocator reads as "no
    division restriction" rather than as ICT's A/B/C/D.
    """
    stmt = select(ProgramDivision).where(
        ProgramDivision.program_id == program_id,
        ProgramDivision.is_active.is_(True),
    )
    if admission_year is not None:
        stmt = stmt.where(ProgramDivision.admission_year == admission_year)
    rows = list(db.scalars(stmt.order_by(ProgramDivision.name)))
    return sorted({row.name for row in rows})


def division_choices(db: Session, program_id: int) -> dict[int, list[str]]:
    """Divisions grouped by admission batch, for the admin screens."""
    rows = db.scalars(
        select(ProgramDivision)
        .where(ProgramDivision.program_id == program_id)
        .order_by(ProgramDivision.admission_year.desc(), ProgramDivision.name)
    )
    grouped: dict[int, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.admission_year, []).append(row.name)
    return grouped
