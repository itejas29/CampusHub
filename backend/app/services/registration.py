"""Elective registration rounds: who may act, and when.

The rule this module exists to hold is that **the backend decides**. A closing
time rendered as a countdown in the browser is a courtesy — a student with a
skewed clock, a stale tab, or a hand-written request must still be refused. So
every write path calls `assert_can_submit()`, and the student-facing state is
*derived* from the window, the clock and the student's own rows rather than
stored anywhere it could drift out of step.

    DRAFT -> OPEN -> LOCKED -> ALLOCATED -> PUBLISHED -> CLOSED
              |        |           |            |
        may submit   frozen   run allocation  results visible

**A round, not the semester, is what opens registration early.** At PDEU choice
filling for a Semester N elective starts mid-way through Semester N-1, so the
timetable can be built over the vacation. The curriculum alone would refuse that
student ("opens in semester N"); a round the coordinator has aimed at their
current semester is what lets them in — see `access_for`. With no round there
is no early access.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationError
from app.models.academics import (
    CourseOffering, CurriculumComponent, ElectiveAllocation, ElectivePreference,
    ElectiveRegistrationWindow,
)
from app.models.enums import (
    REGISTRATION_STATE_LABEL, AllocationStatus, PreferenceStatus,
    RegistrationWindowStatus, StudentRegistrationState,
)
from app.models.identity import Student

#: Transitions a coordinator may make, in order. Anything else is refused, so a
#: round cannot be published without having been allocated.
ALLOWED_TRANSITIONS: dict[RegistrationWindowStatus, set[RegistrationWindowStatus]] = {
    RegistrationWindowStatus.DRAFT: {RegistrationWindowStatus.OPEN},
    RegistrationWindowStatus.OPEN: {RegistrationWindowStatus.LOCKED,
                                    RegistrationWindowStatus.DRAFT},
    RegistrationWindowStatus.LOCKED: {RegistrationWindowStatus.ALLOCATED,
                                      RegistrationWindowStatus.OPEN},
    RegistrationWindowStatus.ALLOCATED: {RegistrationWindowStatus.PUBLISHED,
                                         RegistrationWindowStatus.LOCKED},
    RegistrationWindowStatus.PUBLISHED: {RegistrationWindowStatus.CLOSED},
    RegistrationWindowStatus.CLOSED: set(),
}


#: A round a student can already see: opened at least once and not yet wound
#: up. A DRAFT is the coordinator's private work; a CLOSED round is history.
STUDENT_VISIBLE = (
    RegistrationWindowStatus.OPEN, RegistrationWindowStatus.LOCKED,
    RegistrationWindowStatus.ALLOCATED, RegistrationWindowStatus.PUBLISHED,
)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass(slots=True)
class RegistrationStatus:
    """One student's standing in one round."""

    state: StudentRegistrationState
    window: ElectiveRegistrationWindow | None
    can_submit: bool
    reason: str | None = None
    closes_at: dt.datetime | None = None
    opens_at: dt.datetime | None = None
    preference_count: int = 0
    min_preferences: int = 1
    max_preferences: int = 5

    @property
    def label(self) -> str:
        return REGISTRATION_STATE_LABEL[self.state]


def window_for(db: Session, component: CurriculumComponent,
               student: Student) -> ElectiveRegistrationWindow | None:
    """The round governing this component for this student, if any.

    A component's offerings carry the link, so the round is found through the
    courses actually on offer rather than by guessing from names.
    """
    # DISTINCT over the ids, not the rows: the window carries JSON columns, and
    # Postgres has no equality operator for json, so SELECT DISTINCT on the
    # whole row fails there even though SQLite accepts it.
    window_ids = {
        row for (row,) in db.execute(
            select(CourseOffering.registration_window_id)
            .where(CourseOffering.curriculum_component_id == component.id,
                   CourseOffering.registration_window_id.is_not(None))
            .distinct()
        )
    }
    if not window_ids:
        return None
    windows = list(db.scalars(
        select(ElectiveRegistrationWindow)
        .where(ElectiveRegistrationWindow.id.in_(window_ids))
    ))
    eligible = [
        w for w in windows
        if w.accepts_students_from(student.program_id, student.current_semester,
                                   student.division)
    ]
    if not eligible:
        return None
    # Prefer the round that is actually live, then the furthest along.
    now = utcnow()
    for window in eligible:
        if window.is_open_at(now):
            return window
    order = list(RegistrationWindowStatus)
    return max(eligible, key=lambda w: order.index(w.status))


def status_for(db: Session, component: CurriculumComponent, student: Student,
               now: dt.datetime | None = None) -> RegistrationStatus:
    """Derive what this student may do with this component right now."""
    now = now or utcnow()
    window = window_for(db, component, student)

    preference_count = db.scalar(
        select(func.count(ElectivePreference.id)).where(
            ElectivePreference.student_id == student.id,
            ElectivePreference.curriculum_component_id == component.id)
    ) or 0

    allocation = db.scalar(select(ElectiveAllocation).where(
        ElectiveAllocation.student_id == student.id,
        ElectiveAllocation.curriculum_component_id == component.id,
        ElectiveAllocation.status != AllocationStatus.DROPPED,
    ))

    etype = component.elective_type
    minimum = (window.min_preferences if window and window.min_preferences
               else (etype.min_preferences if etype else 1))
    maximum = (window.max_preferences if window and window.max_preferences
               else (etype.max_preferences if etype else 5))

    base = dict(window=window, preference_count=preference_count,
                min_preferences=minimum, max_preferences=maximum,
                opens_at=window.opens_at_utc if window else None,
                closes_at=window.closes_at_utc if window else None)

    # An allocation the coordinator has published outranks everything else.
    if allocation is not None and (window is None or window.results_visible):
        return RegistrationStatus(
            state=StudentRegistrationState.ALLOCATED, can_submit=False,
            reason="A seat has been allocated; preferences are final.", **base)

    if window is None:
        # No round configured. Fall back to the per-offering dates, which is how
        # offerings created before rounds existed still behave.
        return _legacy_status(db, component, student, now, base)

    if window.status == RegistrationWindowStatus.DRAFT:
        return RegistrationStatus(
            state=StudentRegistrationState.NOT_OPEN, can_submit=False,
            reason="Registration has not opened yet.", **base)

    if window.status == RegistrationWindowStatus.OPEN:
        if window.opens_at_utc and now < window.opens_at_utc:
            return RegistrationStatus(
                state=StudentRegistrationState.NOT_OPEN, can_submit=False,
                reason=f"Registration opens on {_when(window.opens_at_utc)}.", **base)
        if window.closes_at_utc and now >= window.closes_at_utc:
            # The clock has passed the deadline even though the coordinator has
            # not locked the round yet. The deadline wins.
            return RegistrationStatus(
                state=StudentRegistrationState.LOCKED, can_submit=False,
                reason=f"The deadline passed on {_when(window.closes_at_utc)}.", **base)
        state = (StudentRegistrationState.SUBMITTED if preference_count
                 else StudentRegistrationState.OPEN)
        return RegistrationStatus(state=state, can_submit=True, **base)

    if window.status == RegistrationWindowStatus.LOCKED:
        return RegistrationStatus(
            state=StudentRegistrationState.LOCKED, can_submit=False,
            reason="Preferences are locked while allocation is prepared.", **base)

    if window.status == RegistrationWindowStatus.ALLOCATED:
        return RegistrationStatus(
            state=StudentRegistrationState.LOCKED, can_submit=False,
            reason="Allocation has run; results have not been published yet.", **base)

    # PUBLISHED or CLOSED, with no seat for this student.
    return RegistrationStatus(
        state=StudentRegistrationState.CLOSED, can_submit=False,
        reason=("This round is closed." if not preference_count else
                "This round is closed. No seat was allocated from your preferences."),
        **base)


def _legacy_status(db, component, student, now, base) -> RegistrationStatus:
    """Behaviour for offerings not attached to a round.

    Preserves the pre-Phase-4 rule so existing data keeps working: registration
    is open when at least one offering's own window is open.
    """
    from app.services.eligibility import offering_window_open

    # The semester gate comes first. A course offering left open by a
    # coordinator is not a reason to tell a Semester IV student that their
    # Semester VII elective is available — the curriculum decides when a
    # component unlocks, and the dates only decide when registration runs
    # within that.
    if component.semester_number > student.current_semester:
        return RegistrationStatus(
            state=StudentRegistrationState.NOT_OPEN, can_submit=False,
            reason=f"{component.title} opens in semester "
                   f"{component.semester_number}; you are in semester "
                   f"{student.current_semester}.", **base)

    offerings = list(db.scalars(select(CourseOffering).where(
        CourseOffering.curriculum_component_id == component.id)))
    if any(offering_window_open(o, now) for o in offerings):
        state = (StudentRegistrationState.SUBMITTED if base["preference_count"]
                 else StudentRegistrationState.OPEN)
        return RegistrationStatus(state=state, can_submit=True, **base)
    return RegistrationStatus(
        state=StudentRegistrationState.NOT_OPEN, can_submit=False,
        reason="Registration is not open for this component.", **base)


def assert_can_submit(db: Session, component: CurriculumComponent,
                      student: Student, now: dt.datetime | None = None) -> RegistrationStatus:
    """Gate every write. Raises with the reason the student is refused."""
    status = status_for(db, component, student, now)
    if not status.can_submit:
        raise BusinessRuleError(
            status.reason or "Registration is not open for this component."
        )
    return status


def assert_can_withdraw(db: Session, component: CurriculumComponent,
                        student: Student, now: dt.datetime | None = None) -> None:
    status = status_for(db, component, student, now)
    if not status.can_submit:
        raise BusinessRuleError(
            status.reason or "Preferences can no longer be changed."
        )


def transition(window: ElectiveRegistrationWindow,
               target: RegistrationWindowStatus) -> None:
    """Move a round forward, refusing anything the lifecycle does not allow."""
    if target == window.status:
        return
    allowed = ALLOWED_TRANSITIONS.get(window.status, set())
    if target not in allowed:
        readable = ", ".join(sorted(s.value for s in allowed)) or "nothing"
        raise BusinessRuleError(
            f"A {window.status.value} round cannot become {target.value}. "
            f"From here it can only move to: {readable}."
        )
    now = utcnow()
    window.status = target
    if target == RegistrationWindowStatus.LOCKED:
        window.locked_at = now
    elif target == RegistrationWindowStatus.ALLOCATED:
        window.allocated_at = now
    elif target == RegistrationWindowStatus.PUBLISHED:
        window.published_at = now


def _window_student_filter(window: ElectiveRegistrationWindow):
    """The WHERE clauses that describe who a round covers."""
    clauses = []
    if window.eligible_program_ids:
        clauses.append(Student.program_id.in_(window.eligible_program_ids))
    if window.eligible_semesters:
        clauses.append(Student.current_semester.in_(window.eligible_semesters))
    if window.eligible_divisions:
        clauses.append(Student.division.in_(window.eligible_divisions))
    return clauses


def students_in_window(db: Session,
                       window: ElectiveRegistrationWindow) -> list[Student]:
    """Everyone the round covers. Only for paths that need the rows themselves
    — publishing results, which must notify each student individually."""
    return list(db.scalars(select(Student).where(*_window_student_filter(window))))


def count_students_in_window(db: Session,
                             window: ElectiveRegistrationWindow) -> int:
    """How many students a round covers, counted in the database.

    The admin list renders one row per round, so loading every covered student
    to call len() on them turned a summary table into hundreds of hydrated
    Student objects per request.
    """
    return int(db.scalar(
        select(func.count(Student.id)).where(*_window_student_filter(window))
    ) or 0)


def _when(moment: dt.datetime) -> str:
    return moment.strftime("%d %b %Y, %H:%M UTC")


# ── early registration ─────────────────────────────────────────────────────
def access_for(db: Session, student: Student, component: CurriculumComponent):
    """May this student act on this slot at all?

    Yes once the curriculum has unlocked it — or, before that, while a round the
    coordinator has opened covers them. The second half is the whole of early
    choice filling: a Semester III student reaches their Semester IV Open
    Elective because a round says so, never because a date on a course did.

    The early path is deliberately narrow. The slot has to be in the student's
    *own* governing curriculum, and the round has to have left DRAFT.
    """
    from app.services.eligibility import active_curriculum, student_can_access_component

    base = student_can_access_component(student, component)
    if base.eligible:
        return base
    curriculum = active_curriculum(db, student)
    if curriculum is None or component.curriculum_id != curriculum.id:
        return base
    window = window_for(db, component, student)
    if window is not None and window.status != RegistrationWindowStatus.DRAFT:
        return type(base).ok()
    return base


def early_rounds(db: Session, student: Student) -> list[
        tuple[CurriculumComponent, ElectiveRegistrationWindow]]:
    """Slots of a *later* semester that a visible round has opened to this student.

    This is what makes the sidebar offer "Open Electives" to a Semester III
    student, and what puts the round on their dashboard — both would otherwise
    stay silent until the semester the curriculum names.
    """
    from app.services.eligibility import active_curriculum

    curriculum = active_curriculum(db, student)
    if curriculum is None:
        return []
    # Ids, not rows: the window carries JSON columns, which Postgres cannot
    # SELECT DISTINCT over.
    pairs = db.execute(
        select(CourseOffering.curriculum_component_id,
               CourseOffering.registration_window_id)
        .join(CurriculumComponent,
              CurriculumComponent.id == CourseOffering.curriculum_component_id)
        .join(ElectiveRegistrationWindow,
              ElectiveRegistrationWindow.id == CourseOffering.registration_window_id)
        .where(CurriculumComponent.curriculum_id == curriculum.id,
               CurriculumComponent.semester_number > student.current_semester,
               ElectiveRegistrationWindow.status.in_(STUDENT_VISIBLE))
        .distinct()
    ).all()
    found = []
    for component_id, window_id in pairs:
        window = db.get(ElectiveRegistrationWindow, window_id)
        if window.accepts_students_from(student.program_id, student.current_semester,
                                        student.division):
            found.append((db.get(CurriculumComponent, component_id), window))
    found.sort(key=lambda pair: (pair[0].semester_number, pair[0].sequence))
    return found


def has_submitted(db: Session, student: Student, component: CurriculumComponent) -> bool:
    return bool(db.scalar(select(func.count(ElectivePreference.id)).where(
        ElectivePreference.student_id == student.id,
        ElectivePreference.curriculum_component_id == component.id,
        ElectivePreference.status == PreferenceStatus.SUBMITTED,
    )))


# ── what a round may look like ─────────────────────────────────────────────
def round_components(db: Session,
                     window: ElectiveRegistrationWindow) -> list[CurriculumComponent]:
    """The curriculum slots this round's courses belong to."""
    if window.id is None:
        # Not saved yet, so nothing can be attached. Without this guard the
        # comparison below becomes `IS NULL` and matches every unattached course.
        return []
    ids = {
        row for (row,) in db.execute(
            select(CourseOffering.curriculum_component_id)
            .where(CourseOffering.registration_window_id == window.id,
                   CourseOffering.curriculum_component_id.is_not(None))
            .distinct()
        )
    }
    return [db.get(CurriculumComponent, i) for i in sorted(ids)]


def validate_round(db: Session, window: ElectiveRegistrationWindow, *,
                   opening: bool = False, now: dt.datetime | None = None) -> None:
    """Refuse a round that could not mean anything sensible to a student.

    Checked when courses are attached, when its rules are edited, and — with
    `opening` — at the moment it goes live, which is the last point a mistake
    can be caught before students are told.
    """
    now = now or utcnow()
    components = round_components(db, window)

    wrong_family = [c for c in components if c.component_type != window.component_type]
    if wrong_family:
        raise ValidationError(
            f"{wrong_family[0].title} is not a "
            f"{window.component_type.value.replace('_', ' ').title()} slot. A round "
            "covers one elective family."
        )

    semesters = {c.semester_number for c in components}
    if len(semesters) > 1:
        raise ValidationError(
            "A round covers the slots of one semester. These courses belong to "
            f"semesters {', '.join(str(n) for n in sorted(semesters))}."
        )
    if semesters:
        slot_semester = next(iter(semesters))
        allowed = {slot_semester - 1, slot_semester}
        chosen = set(window.eligible_semesters or [])
        if not chosen:
            raise ValidationError(
                "Choose which semester's students this round is for."
            )
        if not chosen <= allowed:
            raise ValidationError(
                f"These courses are for Semester {slot_semester}. The round can be "
                f"run for students currently in Semester {slot_semester - 1} "
                f"(choosing ahead) or Semester {slot_semester}, not "
                f"{', '.join(str(n) for n in sorted(chosen - allowed))}."
            )

    if opening:
        if not components:
            raise BusinessRuleError(
                "Attach at least one course before opening the round — students "
                "would otherwise see an empty list."
            )
        if not window.eligible_program_ids:
            raise BusinessRuleError(
                "Choose the programme this round is for before opening it."
            )
        closes_at = window.closes_at_utc
        if closes_at is None:
            raise BusinessRuleError(
                "Set a closing time before opening the round. Deadlines are "
                "enforced by the server, so the round needs one."
            )
        if closes_at <= now:
            raise BusinessRuleError(
                "The closing time has already passed. Set a later deadline "
                "before opening the round."
            )
