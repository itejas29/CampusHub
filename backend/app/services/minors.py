"""Minor-specialisation allocation.

Minor Specialisation is the ONLY place in CampusHub where CPI/CGPA may be used
to rank students. Open and Core Electives are allocated on preference alone —
see `services/allocation` and `services/sections`.

The institute has not published a single ranking formula, so none is invented
here. Each `MinorProgram` carries its own policy in `MinorProgram.rules`:

    {
      "ranking": {
        "criteria": [
          {"field": "cpi",              "direction": "desc"},
          {"field": "backlog_count",    "direction": "asc"},
          {"field": "preference_order", "direction": "asc"},
          {"field": "submitted_at",     "direction": "asc"}
        ]
      }
    }

Nothing is ranked until a coordinator configures that policy — running a round
against an unconfigured programme raises rather than silently guessing.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.locking import locked
from app.core.errors import BusinessRuleError

from app.models.enums import MinorApplicationStatus, MinorEnrollmentStatus
from app.models.academics import as_utc
from app.models.identity import Student
from app.models.minors import MinorApplication, MinorEnrollment, MinorProgram


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def application_window_open(program: MinorProgram,
                            now: dt.datetime | None = None) -> bool:
    """Whether the minor's registration round is currently accepting entries.

    An unset bound means "no limit on that side", so a programme with neither
    date configured is treated as permanently open — that is how the seeded
    rounds behave and changing it would silently close them.
    """
    now = as_utc(now or utcnow())
    # as_utc: SQLite hands these back without a zone, and comparing them with
    # an aware "now" raised — signing a Semester VI student in returned a 500.
    opens, closes = as_utc(program.application_opens_at), as_utc(program.application_closes_at)
    if opens and now < opens:
        return False
    if closes and now > closes:
        return False
    return True


def student_can_see_minor(program: MinorProgram, student: Student, *,
                          has_application: bool,
                          now: dt.datetime | None = None) -> bool:
    """Whether a minor programme belongs in this student's view.

    Two gates, deliberately coarse:

    * the student has reached the semester the minor opens from, and
    * the registration round is open.

    Note what is NOT here: CPI and backlog count. A student who is short on
    either still needs to see the programme and the reason they do not qualify —
    hiding it would leave them unable to find out why. Those checks belong in
    check_minor_eligibility(), which blocks the application itself.

    Once the round closes the programme drops out of view, except for a student
    who actually applied: their own record has to outlive the window, otherwise
    an allocated seat becomes invisible the moment registration ends.
    """
    if has_application:
        return True
    if student.current_semester not in application_semesters(program):
        return False
    return application_window_open(program, now)


def application_semesters(program) -> list[int]:
    """The semesters in which a student may apply for this minor.

    The ICT department takes minor applications in Semester III (as described to
    the project team; Annexure II says only that minors run from Semester III).
    A student who did not apply then does not see the minor afterwards; one
    who did keeps it for good. `rules["application_semesters"]` overrides this
    per minor; by default it is the minor's first eligible semester.
    """
    configured = (getattr(program, "rules", None) or {}).get("application_semesters")
    return list(configured) if configured else [program.eligible_from_semester]

# Fields a policy may rank on. Everything is drawn from the application snapshot
# taken at submission time, so a later CPI revision cannot reorder a closed round.
RANKABLE_FIELDS: dict[str, str] = {
    "cpi": "CPI at application",
    "backlog_count": "Backlogs at application",
    "preference_order": "Student's stated preference",
    "submitted_at": "Submission time (earliest first)",
    "semester": "Semester at application",
}

DEFAULT_DIRECTIONS = {"cpi": "desc", "backlog_count": "asc", "preference_order": "asc",
                      "submitted_at": "asc", "semester": "desc"}


@dataclass(slots=True)
class RankedApplicant:
    application_id: int
    student_id: int
    student_name: str
    roll_number: str
    department: str | None
    cpi: float | None
    backlog_count: int | None
    preference_order: int
    submitted_at: dt.datetime | None
    rank: int
    within_capacity: bool
    note: str | None = None


def ranking_policy(program: MinorProgram) -> list[dict[str, str]]:
    """The programme's declared ranking criteria, validated.

    Raises when unconfigured: a minor with real seat scarcity must not be
    allocated by an assumption this code made up.
    """
    policy = (program.rules or {}).get("ranking") or {}
    criteria = policy.get("criteria") or []
    if not criteria:
        raise BusinessRuleError(
            f"{program.name} has no ranking policy configured. Set the ranking "
            "criteria for this minor before running an allocation round.",
        )
    cleaned: list[dict[str, str]] = []
    for entry in criteria:
        field = entry.get("field") if isinstance(entry, dict) else str(entry)
        if field not in RANKABLE_FIELDS:
            raise BusinessRuleError(
                f"'{field}' is not a rankable field. Choose from: "
                f"{', '.join(sorted(RANKABLE_FIELDS))}.",
            )
        direction = (entry.get("direction") if isinstance(entry, dict) else None) \
            or DEFAULT_DIRECTIONS[field]
        if direction not in ("asc", "desc"):
            raise BusinessRuleError(
                f"Ranking direction for '{field}' must be 'asc' or 'desc'.",
            )
        cleaned.append({"field": field, "direction": direction})
    return cleaned


def _sort_key(application: MinorApplication, criteria: list[dict[str, str]]) -> tuple:
    """Build a tuple that sorts ascending for every criterion.

    Descending fields are negated. Missing values sort last on their own
    criterion, so an absent CPI never wins a seat by accident.
    """
    key: list[Any] = []
    for entry in criteria:
        field, descending = entry["field"], entry["direction"] == "desc"
        if field == "cpi":
            raw = application.cpi_at_application
            value = float(raw) if raw is not None else None
        elif field == "backlog_count":
            value = application.backlogs_at_application
        elif field == "preference_order":
            value = application.preference_order
        elif field == "semester":
            value = application.semester_at_application
        else:  # submitted_at
            stamp = application.submitted_at
            value = stamp.timestamp() if stamp else None

        if value is None:
            key.extend((1, 0.0))          # missing → after every present value
        else:
            numeric = float(value)
            key.extend((0, -numeric if descending else numeric))
    key.append(application.id)             # stable, deterministic final tie-break
    return tuple(key)


def rank(db: Session, program: MinorProgram) -> list[RankedApplicant]:
    """Rank every SUBMITTED application for one minor against its own policy."""
    criteria = ranking_policy(program)
    applications = list(db.scalars(
        select(MinorApplication).where(
            MinorApplication.minor_program_id == program.id,
            MinorApplication.status == MinorApplicationStatus.SUBMITTED,
        )
    ))
    applications.sort(key=lambda a: _sort_key(a, criteria))

    # Students already holding a minor cannot take a second seat.
    already_enrolled = set(db.scalars(
        select(MinorEnrollment.student_id).where(
            MinorEnrollment.status == MinorEnrollmentStatus.ACTIVE,
        )
    ))

    seats = max(program.capacity - program.seats_filled, 0)
    out: list[RankedApplicant] = []
    taken = 0
    for position, application in enumerate(applications, start=1):
        student = db.get(Student, application.student_id)
        blocked = application.student_id in already_enrolled
        fits = not blocked and taken < seats
        if fits:
            taken += 1
        cpi = application.cpi_at_application
        out.append(RankedApplicant(
            application_id=application.id,
            student_id=application.student_id,
            student_name=student.user.full_name if student and student.user else "—",
            roll_number=student.roll_number if student else "—",
            department=student.department.short_name if student and student.department else None,
            cpi=float(cpi) if isinstance(cpi, (Decimal, float, int)) else None,
            backlog_count=application.backlogs_at_application,
            preference_order=application.preference_order,
            submitted_at=application.submitted_at,
            rank=position,
            within_capacity=fits,
            note="Already enrolled in another minor" if blocked else None,
        ))
    return out


def allocate(db: Session, program: MinorProgram) -> tuple[list[RankedApplicant], int]:
    """Commit one allocation round. Returns the ranking and the seats granted."""
    # Seats are counted from the programme row: hold it, current, for the round.
    program = locked(db, MinorProgram, program.id)
    ranked = rank(db, program)

    granted = 0
    now = utcnow()
    for entry in ranked:
        application = db.get(MinorApplication, entry.application_id)
        if application is None:
            continue
        if entry.within_capacity:
            db.add(MinorEnrollment(
                student_id=application.student_id,
                minor_program_id=program.id,
                application_id=application.id,
                status=MinorEnrollmentStatus.ACTIVE,
                started_semester=application.semester_at_application,
            ))
            application.status = MinorApplicationStatus.ALLOCATED
            application.allocation_score = float(entry.rank)
            application.decided_at = now
            granted += 1
            # Close the same student's competing preferences.
            for sibling in db.scalars(select(MinorApplication).where(
                MinorApplication.student_id == application.student_id,
                MinorApplication.id != application.id,
                MinorApplication.status == MinorApplicationStatus.SUBMITTED,
            )):
                sibling.status = MinorApplicationStatus.REJECTED
                sibling.decided_at = now
                sibling.remarks = "Closed — another preference was allocated."
        else:
            application.status = MinorApplicationStatus.WAITLISTED
            application.allocation_score = float(entry.rank)
            application.decided_at = now
            application.remarks = entry.note or (
                f"Waitlisted at rank {entry.rank} — capacity is {program.capacity}."
            )
    program.seats_filled += granted
    return ranked, granted
