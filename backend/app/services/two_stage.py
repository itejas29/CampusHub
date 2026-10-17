"""Two-stage elective rounds: interest, shortlist, final choice.

How the ICT department runs its Semester VII electives (Guidelines and
Procedure for Elective Course Offering, B.Tech ICT Semester 7):

1. **Interest.** Students tick exactly the number of subjects the coordinator
   sets. Only the coordinator sees the votes.
2. **Shortlist.** When the interest round closes the coordinator keeps the
   subjects they choose, as many as they choose. The rest leave the round.
3. **Final.** The same students — including anyone who skipped the interest
   round — tick exactly the number of shortlisted subjects they will take.
4. **Finalise.** A subject runs if at least the coordinator's minimum picked
   it. A student whose pick was withdrawn, and a student who never submitted,
   is placed by the department in subjects that run; the coordinator reviews
   every seat before publishing.

Every number here is the coordinator's, set on the round, because the
department changes them from year to year. Nothing below assumes a value.
"""
from __future__ import annotations

import datetime as dt
import itertools
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationError
from app.models.academics import (
    Course, CourseOffering, CurriculumComponent, ElectiveAllocation,
    ElectiveRegistrationWindow, ElectiveRoundChoice,
)
from app.models.enums import (
    AllocationStatus, RegistrationWindowStatus, RoundStage,
)
from app.models.identity import Student

#: What the student is told about a seat the department chose for them.
REASON_CHOSEN = "Your choice"
REASON_WITHDRAWN = ("A subject you chose did not reach the minimum and was "
                    "withdrawn; the department placed you in this one")
REASON_NO_CHOICE = ("You did not submit your choice in time; the department "
                    "placed you in this subject")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── what the round offers ──────────────────────────────────────────────────
def round_offerings(db: Session, window: ElectiveRegistrationWindow) -> list[CourseOffering]:
    return list(db.scalars(select(CourseOffering).where(
        CourseOffering.registration_window_id == window.id).order_by(CourseOffering.id)))


def subjects(db: Session, window: ElectiveRegistrationWindow) -> list[Course]:
    """The subjects of the round: each course once, however many slots offer it."""
    seen: dict[int, Course] = {}
    for offering in round_offerings(db, window):
        seen.setdefault(offering.course_id, offering.course)
    return sorted(seen.values(), key=lambda c: (c.code, c.id))


def choices(db: Session, window: ElectiveRegistrationWindow, stage: RoundStage,
            student_id: int | None = None) -> list[ElectiveRoundChoice]:
    stmt = select(ElectiveRoundChoice).where(
        ElectiveRoundChoice.registration_window_id == window.id,
        ElectiveRoundChoice.stage == stage)
    if student_id is not None:
        stmt = stmt.where(ElectiveRoundChoice.student_id == student_id)
    return list(db.scalars(stmt.order_by(ElectiveRoundChoice.id)))


def submitted_count(db: Session, window: ElectiveRegistrationWindow,
                    stage: RoundStage | None = None) -> int:
    """How many students have ticked their subjects in this stage."""
    stage = stage or window.stage or RoundStage.INTEREST
    return int(db.scalar(
        select(func.count(func.distinct(ElectiveRoundChoice.student_id))).where(
            ElectiveRoundChoice.registration_window_id == window.id,
            ElectiveRoundChoice.stage == stage)) or 0)


# ── the round's own settings ───────────────────────────────────────────────
def validate_settings(db: Session, window: ElectiveRegistrationWindow, *,
                      opening: bool = False) -> None:
    """The coordinator's numbers must make sense for this round's subjects."""
    for name, value in (("interest_pick_count", window.interest_pick_count),
                        ("final_pick_count", window.final_pick_count),
                        ("min_students_to_run", window.min_students_to_run),
                        ("section_capacity", window.section_capacity)):
        if value is not None and value < 1:
            raise ValidationError(f"{name.replace('_', ' ').capitalize()} must be at least 1.")
    if not window.is_two_stage or not opening:
        return
    count = len(subjects(db, window))
    if window.stage in (None, RoundStage.INTEREST):
        if not window.interest_pick_count:
            raise ValidationError(
                "Set how many subjects each student ticks in the interest round.")
        if window.interest_pick_count > count:
            raise ValidationError(
                f"Students are asked to tick {window.interest_pick_count} subjects, but "
                f"the round offers {count}.")
    else:
        assert_final_pick_count(db, window, window.final_pick_count, count)


def assert_final_pick_count(db: Session, window: ElectiveRegistrationWindow,
                            pick_count: int | None, subject_count: int) -> None:
    from app.services.registration import round_components

    slots = len(round_components(db, window))
    if not pick_count:
        raise ValidationError("Set how many subjects each student takes.")
    if pick_count > subject_count:
        raise ValidationError(
            f"Each student is to take {pick_count} subjects, but only {subject_count} "
            "are shortlisted.")
    if slots and pick_count > slots:
        raise ValidationError(
            f"This round fills {slots} elective slot(s) in the curriculum, so a "
            f"student can take at most {slots} subject(s) from it.")


def apply_course_rules(db: Session, window: ElectiveRegistrationWindow) -> None:
    """Copy the round's minimum and section size onto its courses, which is
    where the section planner reads them."""
    for offering in round_offerings(db, window):
        if window.min_students_to_run is not None:
            offering.min_students_to_run = window.min_students_to_run
        if window.section_capacity is not None:
            offering.section_capacity = window.section_capacity


# ── the student ticks subjects ─────────────────────────────────────────────
def submit_choices(db: Session, window: ElectiveRegistrationWindow, student: Student,
                   course_ids: list[int], now: dt.datetime | None = None
                   ) -> list[ElectiveRoundChoice]:
    """Replace this student's ticks for the stage now running."""
    now = now or utcnow()
    if not window.is_two_stage:
        raise BusinessRuleError("This round is chosen by ranking, not by ticking subjects.")
    if not window.accepts_students_from(student.program_id, student.current_semester,
                                        student.division):
        raise BusinessRuleError("This registration round is not for you.")
    if not window.is_open_at(now):
        if window.status == RegistrationWindowStatus.OPEN and window.closes_at_utc \
                and now >= window.closes_at_utc:
            raise BusinessRuleError("The deadline for this round has passed.")
        raise BusinessRuleError("This round is not accepting choices right now.")

    wanted = window.pick_count or 0
    if len(set(course_ids)) != len(course_ids):
        raise ValidationError("Each subject can be ticked only once.")
    if len(course_ids) != wanted:
        raise ValidationError(f"Tick exactly {wanted} subject(s); you ticked "
                              f"{len(course_ids)}.")
    on_offer = {c.id for c in subjects(db, window)}
    stray = [cid for cid in course_ids if cid not in on_offer]
    if stray:
        raise ValidationError("One of those subjects is not part of this round.")

    stage = window.stage or RoundStage.INTEREST
    for old in choices(db, window, stage, student.id):
        db.delete(old)
    db.flush()
    made = []
    for course_id in course_ids:
        choice = ElectiveRoundChoice(registration_window_id=window.id, stage=stage,
                                     student_id=student.id, course_id=course_id,
                                     submitted_at=now)
        db.add(choice)
        made.append(choice)
    db.flush()
    return made


# ── the coordinator reads the interest round and shortlists ────────────────
@dataclass(slots=True)
class Tally:
    course: Course
    votes: int


def interest_tally(db: Session, window: ElectiveRegistrationWindow) -> list[Tally]:
    """Votes per subject, most first. Subjects already dropped keep their votes,
    so the coordinator can still see why they went."""
    votes = Counter(c.course_id for c in choices(db, window, RoundStage.INTEREST))
    on_offer = {c.id: c for c in subjects(db, window)}
    voted = {c.course_id: c.course for c in choices(db, window, RoundStage.INTEREST)}
    courses = {**voted, **on_offer}
    return sorted((Tally(course=c, votes=votes.get(cid, 0)) for cid, c in courses.items()),
                  key=lambda t: (-t.votes, t.course.code))


def start_final(db: Session, window: ElectiveRegistrationWindow, *,
                keep_course_ids: list[int], final_pick_count: int,
                opens_at: dt.datetime | None, closes_at: dt.datetime) -> list[Course]:
    """Keep the shortlisted subjects, drop the rest, and open the final round.

    Returns the subjects dropped. Their courses leave the round and become free
    for another one; their interest votes stay on record.
    """
    if not window.is_two_stage or window.stage != RoundStage.INTEREST:
        raise BusinessRuleError("Only a round in its interest stage can be shortlisted.")
    if window.status != RegistrationWindowStatus.LOCKED:
        raise BusinessRuleError("Lock the interest round before shortlisting.")
    on_offer = {c.id: c for c in subjects(db, window)}
    keep = set(keep_course_ids)
    if not keep:
        raise ValidationError("Shortlist at least one subject.")
    if keep - set(on_offer):
        raise ValidationError("A shortlisted subject is not part of this round.")
    assert_final_pick_count(db, window, final_pick_count, len(keep))
    now = utcnow()
    if closes_at is None or closes_at <= now:
        raise ValidationError("The final round's deadline must be in the future.")
    if opens_at and opens_at >= closes_at:
        raise ValidationError("The closing time must be after the opening time.")

    dropped = [c for cid, c in on_offer.items() if cid not in keep]
    for offering in round_offerings(db, window):
        if offering.course_id not in keep:
            offering.registration_window_id = None
    window.interest_closed_at = window.locked_at or now
    window.stage = RoundStage.FINAL
    window.final_pick_count = final_pick_count
    window.opens_at = opens_at
    window.closes_at = closes_at
    window.status = RegistrationWindowStatus.OPEN
    window.locked_at = None
    db.flush()
    return sorted(dropped, key=lambda c: c.code)


# ── finalising: who runs, who sits where ───────────────────────────────────
@dataclass(slots=True)
class Placement:
    student_id: int
    component_id: int
    course_id: int
    reason: str


@dataclass(slots=True)
class SubjectResult:
    course: Course
    demand: int
    runs: bool
    seated: int = 0


@dataclass
class FinalPlan:
    minimum: int
    pick_count: int
    subjects: list[SubjectResult]
    placements: list[Placement] = field(default_factory=list)
    unplaced_student_ids: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def count(self, reason: str) -> int:
        """Students placed for this reason. A student given every subject they
        chose counts as CHOSEN; one with any other seat counts under that."""
        reasons: dict[int, set[str]] = {}
        for p in self.placements:
            reasons.setdefault(p.student_id, set()).add(p.reason)
        if reason == REASON_CHOSEN:
            return sum(1 for r in reasons.values() if r == {REASON_CHOSEN})
        return sum(1 for r in reasons.values() if reason in r)


def plan_final(db: Session, window: ElectiveRegistrationWindow, *,
               minimum: int | None = None,
               run_course_ids: list[int] | None = None) -> FinalPlan:
    """Work out the final allocation without writing anything.

    `minimum` overrides the round's own; `run_course_ids` lets the coordinator
    decide which subjects run when the counts alone should not (the guideline
    leaves that to the department when too few, or too many, qualify).
    """
    from app.services.registration import round_components, students_in_window

    if not window.is_two_stage or window.stage != RoundStage.FINAL:
        raise BusinessRuleError("Only a round in its final stage can be finalised.")
    minimum = minimum or window.min_students_to_run
    if not minimum:
        raise ValidationError("Set the minimum number of students a subject needs to run.")
    pick_count = window.final_pick_count or 1
    slots = sorted(round_components(db, window),
                   key=lambda c: (c.semester_number, c.sequence, c.id))

    covered = sorted(s.id for s in students_in_window(db, window))
    covered_set = set(covered)
    picks: dict[int, set[int]] = defaultdict(set)
    for choice in choices(db, window, RoundStage.FINAL):
        if choice.student_id in covered_set:
            picks[choice.student_id].add(choice.course_id)
    demand = Counter(cid for chosen in picks.values() for cid in chosen)

    on_offer = subjects(db, window)
    if run_course_ids is not None:
        unknown = set(run_course_ids) - {c.id for c in on_offer}
        if unknown:
            raise ValidationError("A subject chosen to run is not part of this round.")
        running = set(run_course_ids)
    else:
        running = {c.id for c in on_offer if demand.get(c.id, 0) >= minimum}
    results = {c.id: SubjectResult(course=c, demand=demand.get(c.id, 0),
                                   runs=c.id in running) for c in on_offer}
    plan = FinalPlan(minimum=minimum, pick_count=pick_count,
                     subjects=list(results.values()))
    if not running:
        plan.notes.append(
            f"No subject reached {minimum} students. Choose which subject(s) run, "
            "or lower the minimum.")
        plan.unplaced_student_ids = covered
        return plan
    if len(running) < pick_count:
        plan.notes.append(
            f"Only {len(running)} subject(s) run, but each student takes {pick_count}. "
            f"Students can be given at most {len(running)}.")

    already = {
        (a.student_id, a.curriculum_component_id) for a in db.scalars(
            select(ElectiveAllocation).where(
                ElectiveAllocation.curriculum_component_id.in_([s.id for s in slots] or [0]),
                ElectiveAllocation.status != AllocationStatus.DROPPED))
    }
    existing = {(o.curriculum_component_id, o.course_id) for o in round_offerings(db, window)}
    rng = random.Random(f"{window.id}:final")
    running_sorted = sorted(running)
    for student_id in covered:
        open_slots = [s for s in slots if (student_id, s.id) not in already]
        if not open_slots:
            continue
        target = min(pick_count, len(open_slots), len(running))
        mine = sorted(c for c in picks.get(student_id, ()) if c in running)[:target]
        reason_fill = (REASON_WITHDRAWN if picks.get(student_id) else REASON_NO_CHOICE)
        pool = [c for c in running_sorted if c not in mine]
        filled = rng.sample(pool, min(target - len(mine), len(pool)))
        courses = [(c, REASON_CHOSEN) for c in mine] + [(c, reason_fill) for c in filled]
        if not courses:
            plan.unplaced_student_ids.append(student_id)
            continue
        for slot, (course_id, reason) in _match_slots(open_slots, courses, existing):
            plan.placements.append(Placement(student_id=student_id, component_id=slot.id,
                                             course_id=course_id, reason=reason))
            results[course_id].seated += 1
    withdrawn = [r.course.code for r in plan.subjects if not r.runs]
    if withdrawn:
        plan.notes.append(f"Withdrawn (fewer than {minimum}): {', '.join(withdrawn)}.")
    return plan


def _match_slots(slots: list[CurriculumComponent], courses: list[tuple[int, str]],
                 existing: set[tuple[int, int]]):
    """Give each course its own slot, preferring slots that already offer it.

    A student takes at most as many subjects as there are slots, so this is a
    handful of permutations at most.
    """
    best, best_score = None, -1
    for order in itertools.permutations(slots, len(courses)):
        score = sum((slot.id, course[0]) in existing for slot, course in zip(order, courses))
        if score > best_score:
            best, best_score = order, score
            if score == len(courses):
                break
    return list(zip(best, courses))


def apply_final(db: Session, window: ElectiveRegistrationWindow, plan: FinalPlan, *,
                actor_user_id: int | None) -> int:
    """Write the plan: seats, and an offering wherever a slot lacked one."""
    from app.services import sections

    offerings = {(o.curriculum_component_id, o.course_id): o
                 for o in round_offerings(db, window)}
    by_course: dict[int, CourseOffering] = {}
    for offering in offerings.values():
        by_course.setdefault(offering.course_id, offering)

    now = utcnow()
    written = 0
    for p in plan.placements:
        offering = offerings.get((p.component_id, p.course_id))
        if offering is None:
            offering = _copy_offering(db, by_course[p.course_id], p.component_id, window)
            offerings[(p.component_id, p.course_id)] = offering
        db.add(ElectiveAllocation(
            student_id=p.student_id, curriculum_component_id=p.component_id,
            course_offering_id=offering.id, status=AllocationStatus.ALLOCATED,
            allocation_round=1, strategy="two_stage", preference_order_granted=None,
            allocated_by_user_id=actor_user_id, allocated_at=now,
            remarks=None if p.reason == REASON_CHOSEN else p.reason,
        ))
        written += 1
    db.flush()
    running = {r.course.id for r in plan.subjects if r.runs}
    for (_, course_id), offering in offerings.items():
        if course_id in running:
            # The round's minimum decided who runs; the planner only splits.
            offering.min_students_to_run = plan.minimum
            if window.section_capacity is not None:
                offering.section_capacity = window.section_capacity
            sections.distribute(db, offering)
    return written


def _copy_offering(db: Session, source: CourseOffering, component_id: int,
                   window: ElectiveRegistrationWindow) -> CourseOffering:
    """The same course, offered in another of the round's slots."""
    offering = CourseOffering(
        course_id=source.course_id, semester_id=source.semester_id,
        curriculum_component_id=component_id, elective_type_id=source.elective_type_id,
        coordinator_faculty_id=source.coordinator_faculty_id,
        registration_window_id=window.id,
        min_students_to_run=source.min_students_to_run,
        section_capacity=source.section_capacity,
        allow_multiple_sections=source.allow_multiple_sections,
        eligible_divisions=list(source.eligible_divisions or []),
        status=source.status, eligibility=dict(source.eligibility or {}),
    )
    db.add(offering)
    db.flush()
    return offering
