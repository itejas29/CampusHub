"""Class-section planning for electives.

The two elective families have genuinely different capacity rules, so this
module keeps them apart rather than sharing one number:

**Open Elective** — drawn from across schools. Runs only if at least
`min_students_to_run` (40) students choose it, and each *section* holds at most
`section_capacity` (75). Demand above 75 opens another section rather than
turning students away:

    90  students → Section A 75, Section B 15
    150 students → Section A 75, Section B 75
    151-225      → three sections

**Program Core Elective** — division-based within a programme. The same 40
minimum applies, but it is checked **across all participating divisions
combined**, never per division (10+10+10+10 = 40 runs as one combined class),
and there is no upper limit, so it stays a single section.

Selection never considers CPI. Academic merit belongs to Minor Specialisation
only — see `services/eligibility.check_minor_eligibility`.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.models.academics import (
    CourseOffering, CourseSection, ElectiveAllocation, ElectivePreference,
)
from app.models.enums import AllocationStatus, AuditAction
from app.models.identity import Student, User
from app.services import audit

#: Section A, B, C… — enough letters for any realistic cohort.
SECTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def section_name(index: int) -> str:
    """0 -> 'Section A'. Falls back to a number past Z."""
    return (f"Section {SECTION_LETTERS[index]}" if index < len(SECTION_LETTERS)
            else f"Section {index + 1}")


def plan_section_sizes(demand: int, section_capacity: int | None,
                       allow_multiple: bool) -> list[int]:
    """How many sections the demand needs, and how many students in each.

    Fills each section to capacity before opening the next, which is what the
    worked examples describe (90 -> 75 + 15, not 45 + 45).
    """
    if demand <= 0:
        return []
    if section_capacity is None or not allow_multiple:
        return [demand]                       # one combined class, no ceiling

    sizes: list[int] = []
    remaining = demand
    while remaining > 0:
        take = min(remaining, section_capacity)
        sizes.append(take)
        remaining -= take
    return sizes


@dataclass(slots=True)
class DivisionBreakdown:
    """Who is in a course/section, by division — the composition view."""

    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def divisions(self) -> list[str]:
        return sorted(self.counts)

    def as_rows(self) -> list[dict]:
        return [{"division": d, "count": self.counts[d]} for d in self.divisions]


@dataclass(slots=True)
class ViabilityReport:
    """Does this course run, and how should it be split?"""

    offering_id: int
    course_code: str
    course_title: str
    demand: int
    min_students_to_run: int
    section_capacity: int | None
    allow_multiple_sections: bool
    runs: bool
    shortfall: int
    planned_sections: list[int]
    existing_sections: int
    division_breakdown: DivisionBreakdown
    eligible_divisions: list[str]
    reason: str


def division_breakdown(db: Session, *, offering_id: int,
                       section_id: int | None = None,
                       from_preferences: bool = False) -> DivisionBreakdown:
    """Division composition of the students attached to an offering/section."""
    if from_preferences:
        stmt = (
            select(Student.division)
            .join(ElectivePreference, ElectivePreference.student_id == Student.id)
            .where(ElectivePreference.course_offering_id == offering_id,
                   ElectivePreference.preference_order == 1)
        )
    else:
        stmt = (
            select(Student.division)
            .join(ElectiveAllocation, ElectiveAllocation.student_id == Student.id)
            .where(ElectiveAllocation.course_offering_id == offering_id,
                   ElectiveAllocation.status != AllocationStatus.DROPPED)
        )
        if section_id is not None:
            stmt = stmt.where(ElectiveAllocation.section_id == section_id)

    counts = Counter(d or "—" for d in db.scalars(stmt))
    return DivisionBreakdown(counts=dict(counts))


def assess(db: Session, offering: CourseOffering, *,
           use_preferences: bool = False) -> ViabilityReport:
    """Report whether a course clears its minimum and how it should be split.

    `use_preferences` measures *demand* (first preferences) before allocation;
    otherwise it measures students already allocated.
    """
    if use_preferences:
        # Demand = how many students put this course first.
        demand = db.scalar(
            select(func.count(ElectivePreference.id)).where(
                ElectivePreference.course_offering_id == offering.id,
                ElectivePreference.preference_order == 1,
            )
        ) or 0
    else:
        demand = db.scalar(
            select(func.count(ElectiveAllocation.id)).where(
                ElectiveAllocation.course_offering_id == offering.id,
                ElectiveAllocation.status != AllocationStatus.DROPPED,
            )
        ) or 0
    demand = int(demand)

    runs = demand >= offering.min_students_to_run
    sizes = plan_section_sizes(
        demand, offering.section_capacity, offering.allow_multiple_sections
    ) if runs else []

    if runs and offering.allow_multiple_sections and len(sizes) > 1:
        reason = (f"{demand} students · {len(sizes)} sections "
                  f"({' + '.join(map(str, sizes))}) at "
                  f"{offering.section_capacity} per section.")
    elif runs and offering.section_capacity is None:
        reason = f"{demand} students in one combined class (no upper limit)."
    elif runs:
        reason = f"{demand} students in a single section."
    else:
        reason = (f"{demand} of {offering.min_students_to_run} required — "
                  f"{offering.min_students_to_run - demand} short, "
                  "the course cannot run.")

    return ViabilityReport(
        offering_id=offering.id,
        course_code=offering.course.code,
        course_title=offering.course.title,
        demand=demand,
        min_students_to_run=offering.min_students_to_run,
        section_capacity=offering.section_capacity,
        allow_multiple_sections=offering.allow_multiple_sections,
        runs=runs,
        shortfall=max(offering.min_students_to_run - demand, 0),
        planned_sections=sizes,
        existing_sections=len([s for s in offering.sections if s.is_active]),
        division_breakdown=division_breakdown(
            db, offering_id=offering.id, from_preferences=use_preferences
        ),
        eligible_divisions=list(offering.eligible_divisions or []),
        reason=reason,
    )


def ensure_sections(db: Session, offering: CourseOffering, needed: int,
                    *, actor: User | None = None) -> list[CourseSection]:
    """Create sections up to `needed`, reusing any that already exist."""
    existing = sorted([s for s in offering.sections], key=lambda s: s.name)
    created: list[CourseSection] = []
    for index in range(len(existing), needed):
        section = CourseSection(
            course_offering_id=offering.id,
            name=section_name(index),
            capacity=offering.section_capacity,
            venue=offering.venue,
            schedule_note=offering.schedule_note,
            faculty_id=offering.coordinator_faculty_id,
        )
        db.add(section)
        created.append(section)
    db.flush()
    if created and actor is not None:
        audit.record(
            db, action=AuditAction.CREATE, entity_type="course_section",
            entity_id=offering.id, actor=actor,
            description=f"Opened {len(created)} section(s) for "
                        f"{offering.course.code}",
            meta={"sections": [s.name for s in created]},
        )
    return existing + created


def distribute(db: Session, offering: CourseOffering,
               *, actor: User | None = None) -> dict:
    """Place every allocated student of this offering into a section.

    Fills each section to capacity before opening the next, and leaves existing
    section assignments untouched so a coordinator's manual moves survive a
    re-run.
    """
    allocations = list(db.scalars(
        select(ElectiveAllocation)
        .where(ElectiveAllocation.course_offering_id == offering.id,
               ElectiveAllocation.status != AllocationStatus.DROPPED)
        .order_by(ElectiveAllocation.id)
    ))
    if not allocations:
        return {"sections": 0, "assigned": 0}

    sizes = plan_section_sizes(
        len(allocations), offering.section_capacity, offering.allow_multiple_sections
    )
    sections = ensure_sections(db, offering, len(sizes), actor=actor)

    # Keep students already placed in a still-valid section.
    by_section: dict[int, list[ElectiveAllocation]] = {s.id: [] for s in sections}
    unplaced: list[ElectiveAllocation] = []
    for allocation in allocations:
        if allocation.section_id in by_section:
            by_section[allocation.section_id].append(allocation)
        else:
            unplaced.append(allocation)

    for allocation in unplaced:
        target = next(
            (s for s in sections
             if s.capacity is None or len(by_section[s.id]) < s.capacity),
            sections[-1],
        )
        allocation.section_id = target.id
        by_section[target.id].append(allocation)

    for section in sections:
        section.seats_filled = len(by_section[section.id])
    offering.seats_filled = len(allocations)

    return {"sections": len(sections), "assigned": len(allocations)}


def move_student(db: Session, *, allocation_id: int, section_id: int,
                 actor: User | None = None, reason: str | None = None) -> ElectiveAllocation:
    """Coordinator rebalance: move one student between sections of the same course."""
    allocation = db.get(ElectiveAllocation, allocation_id)
    if allocation is None:
        raise NotFoundError("Allocation not found.")
    target = db.get(CourseSection, section_id)
    if target is None:
        raise NotFoundError("Section not found.")
    if target.course_offering_id != allocation.course_offering_id:
        raise BusinessRuleError(
            "A student can only be moved between sections of the same course."
        )
    if target.is_full:
        raise BusinessRuleError(
            f"{target.name} is full ({target.capacity} seats). "
            "Open another section or move someone out first."
        )

    previous = db.get(CourseSection, allocation.section_id) if allocation.section_id else None
    allocation.section_id = target.id
    if previous and previous.seats_filled > 0:
        previous.seats_filled -= 1
    target.seats_filled += 1

    audit.record(
        db, action=AuditAction.UPDATE, entity_type="elective_allocation",
        entity_id=allocation.id, actor=actor,
        description=f"Moved student to {target.name}",
        meta={"from_section": previous.name if previous else None,
              "to_section": target.name, "reason": reason},
    )
    return allocation
