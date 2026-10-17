"""Coordinator-run windows on an internship programme.

The department runs CSSI in steps the coordinator opens, each with a deadline:

1. **Registration** — before the break, students record the NGO and its
   supervisor's name and number. The window is what lets a Semester II student
   write at all: no window, no early access (the same principle as elective
   rounds). It closes on the deadline unless the coordinator extends it.
2. **Mentor allocation** — only once a registration window has been opened.
3. **Presentation** — in Semester III the coordinator opens it with the poster
   deadline and presentation day(s); every student is told their faculty
   mentor. Posters go to the mentor; the mentor records marks; marks lock when
   the window closes.

None of this is CSSI-specific code. A programme opts in by listing the kinds
in ``config["windows"]``; one that lists none keeps the semester-only rules.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationError
from app.models.enums import (
    AuditAction, InternshipWindowKind as Kind, NotificationType, Priority, StudentStatus,
)
from app.models.identity import Faculty, Student, User
from app.models.internships import InternshipEnrollment, InternshipProgram, InternshipWindow
from app.services import audit, notifications

#: The order a programme's windows run in. A later kind needs the earlier closed.
SEQUENCE = (Kind.REGISTRATION, Kind.PRESENTATION)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def _when(value: dt.datetime | dt.date | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, dt.datetime):
        # Students read deadlines in IST; the API stores UTC.
        local = _aware(value).astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))
        return local.strftime("%d %b %Y, %I:%M %p IST")
    return value.strftime("%d %b %Y")


# ── configuration ──────────────────────────────────────────────────────────
def kinds_for(program: InternshipProgram) -> list[Kind]:
    configured = (program.config or {}).get("windows") or []
    return [k for k in SEQUENCE if k.value in configured]


def uses_windows(program: InternshipProgram) -> bool:
    return bool(kinds_for(program))


def get(db: Session, program_id: int, kind: Kind) -> InternshipWindow | None:
    return db.scalar(select(InternshipWindow).where(
        InternshipWindow.program_id == program_id, InternshipWindow.kind == kind))


def windows(db: Session, program: InternshipProgram) -> list[InternshipWindow]:
    rows = {w.kind: w for w in db.scalars(select(InternshipWindow).where(
        InternshipWindow.program_id == program.id))}
    return [rows[k] for k in kinds_for(program) if k in rows]


# ── what each window permits ───────────────────────────────────────────────
def _closed_message(window: InternshipWindow | None, what: str, now: dt.datetime) -> str:
    if window is None:
        return f"{what} has not opened yet — the coordinator has not started this window."
    if window.state_at(now) == "SCHEDULED":
        return f"{what} opens on {_when(window.opens_at)}."
    ended = window.closed_early_at or window.closes_at
    return (f"{what} closed on {_when(ended)}. Ask the coordinator if the deadline "
            "needs to be extended.")


def registration_window(db: Session, program: InternshipProgram) -> InternshipWindow | None:
    return get(db, program.id, Kind.REGISTRATION) if Kind.REGISTRATION in kinds_for(program) else None


def assert_can_register(db: Session, program: InternshipProgram, student: Student,
                        *, already_enrolled: bool, now: dt.datetime | None = None) -> None:
    """Registration and its edits are allowed only inside the open window.

    The window admits its cohort's semester — which may be the semester *before*
    the programme runs. A student who registered keeps edit access for as long
    as the window stays open, even if their semester has since advanced.
    """
    now = now or utcnow()
    window = registration_window(db, program)
    if window is None or not window.is_open_at(now):
        raise BusinessRuleError(_closed_message(window, "Registration", now))
    if program.department_id is not None and student.department_id != program.department_id:
        raise BusinessRuleError(f"{program.name} is run for another department.")
    if not already_enrolled and window.cohort_semester is not None \
            and student.current_semester != window.cohort_semester:
        raise BusinessRuleError(
            f"This registration window is for Semester {window.cohort_semester} students; "
            f"you are in Semester {student.current_semester}."
        )


def assert_can_allocate_mentors(db: Session, program: InternshipProgram,
                                now: dt.datetime | None = None) -> None:
    """Mentors are assigned only after the coordinator has started the cycle."""
    if Kind.REGISTRATION not in kinds_for(program):
        return
    now = now or utcnow()
    window = get(db, program.id, Kind.REGISTRATION)
    if window is None or window.state_at(now) == "SCHEDULED":
        raise BusinessRuleError(
            "Open the registration window before assigning mentors — students "
            "register first, then mentors are allocated."
        )


def presentation_window(db: Session, program: InternshipProgram) -> InternshipWindow | None:
    return get(db, program.id, Kind.PRESENTATION) if Kind.PRESENTATION in kinds_for(program) else None


def assert_can_submit_poster(db: Session, program: InternshipProgram,
                             now: dt.datetime | None = None) -> None:
    if Kind.PRESENTATION not in kinds_for(program):
        return
    now = now or utcnow()
    window = get(db, program.id, Kind.PRESENTATION)
    if window is None or not window.is_open_at(now):
        raise BusinessRuleError(_closed_message(window, "Poster submission", now))
    due = _aware(window.submission_due_at)
    if due is not None and now > due:
        raise BusinessRuleError(
            f"Posters were due to your mentor by {_when(due)}. Ask the coordinator "
            "if the deadline needs to be extended."
        )


def assert_marks_open(db: Session, program: InternshipProgram,
                      now: dt.datetime | None = None) -> None:
    """Marks are entered while the presentation window is open, then locked."""
    if Kind.PRESENTATION not in kinds_for(program):
        return
    now = now or utcnow()
    window = get(db, program.id, Kind.PRESENTATION)
    if window is None or window.state_at(now) == "SCHEDULED":
        raise BusinessRuleError(
            "Marks open with the presentation window, which the coordinator has "
            "not started yet."
        )
    if not window.is_open_at(now):
        ended = window.closed_early_at or window.closes_at
        raise BusinessRuleError(
            f"Marks are locked: the {program.name} deadline passed on {_when(ended)}. "
            "Only the coordinator can extend it."
        )


# ── the mentor list students are sent ─────────────────────────────────────
@dataclass(slots=True)
class MentorGroup:
    faculty_id: int
    name: str
    designation: str | None
    email: str | None
    cabin: str | None
    students: list[tuple[str, str]]   # (roll number, name), roll order

    @property
    def roll_range(self) -> str:
        if not self.students:
            return ""
        first, last = self.students[0][0], self.students[-1][0]
        return first if first == last else f"{first}–{last}"


def mentor_roster(db: Session, program: InternshipProgram) -> list[MentorGroup]:
    groups: dict[int, MentorGroup] = {}
    rows = db.execute(
        select(InternshipEnrollment, Student)
        .join(Student, Student.id == InternshipEnrollment.student_id)
        .where(InternshipEnrollment.program_id == program.id,
               InternshipEnrollment.mentor_faculty_id.is_not(None))
        .order_by(Student.roll_number)
    ).all()
    for enrollment, student in rows:
        group = groups.get(enrollment.mentor_faculty_id)
        if group is None:
            faculty = db.get(Faculty, enrollment.mentor_faculty_id)
            group = groups[enrollment.mentor_faculty_id] = MentorGroup(
                faculty_id=faculty.id, name=faculty.user.full_name,
                designation=faculty.designation,
                email=faculty.public_email or faculty.user.email, cabin=faculty.cabin,
                students=[],
            )
        group.students.append((student.roll_number, student.user.full_name))
    return sorted(groups.values(), key=lambda g: g.students[0][0])


# ── opening, extending, closing ────────────────────────────────────────────
def _validate_dates(kind: Kind, opens_at: dt.datetime, closes_at: dt.datetime,
                    submission_due_at: dt.datetime | None,
                    presentation_from: dt.date | None, presentation_to: dt.date | None,
                    now: dt.datetime) -> None:
    if closes_at <= opens_at:
        raise ValidationError("The deadline must be after the opening date.")
    if closes_at <= now:
        raise ValidationError("The deadline is already in the past.")
    if kind is Kind.PRESENTATION:
        if submission_due_at is None or presentation_from is None:
            raise ValidationError(
                "Give the poster deadline and the presentation date for this window.")
        if not (opens_at <= submission_due_at <= closes_at):
            raise ValidationError("The poster deadline must fall inside the window.")
        last_day = presentation_to or presentation_from
        if presentation_from > last_day:
            raise ValidationError("The presentation dates are in the wrong order.")
        if not (opens_at.date() <= presentation_from and last_day <= closes_at.date()):
            raise ValidationError("Presentations must take place inside the window.")


def open_window(db: Session, program: InternshipProgram, kind: Kind, *, title: str,
                message: str, opens_at: dt.datetime, closes_at: dt.datetime,
                cohort_semester: int | None = None,
                submission_due_at: dt.datetime | None = None,
                presentation_from: dt.date | None = None,
                presentation_to: dt.date | None = None,
                actor: User, now: dt.datetime | None = None) -> InternshipWindow:
    now = now or utcnow()
    opens_at, closes_at = _aware(opens_at), _aware(closes_at)
    submission_due_at = _aware(submission_due_at)
    if kind not in kinds_for(program):
        raise BusinessRuleError(f"{program.name} does not run a {kind.value.lower()} window.")
    if get(db, program.id, kind) is not None:
        raise BusinessRuleError(
            f"The {kind.value.lower()} window has already been opened — extend or "
            "reopen it instead.")
    if not message.strip():
        raise ValidationError("Write the message students will receive.")
    _validate_dates(kind, opens_at, closes_at, submission_due_at,
                    presentation_from, presentation_to, now)

    if kind is Kind.REGISTRATION:
        allowed = {program.announce_from_semester or program.target_semester,
                   program.target_semester} - {None}
        if cohort_semester is None and allowed:
            cohort_semester = min(allowed)
        if allowed and cohort_semester not in allowed:
            raise ValidationError(
                f"Registration may be aimed at Semester "
                f"{' or '.join(str(s) for s in sorted(allowed))} for {program.name}.")
    else:
        earlier = get(db, program.id, Kind.REGISTRATION)
        if Kind.REGISTRATION in kinds_for(program):
            if earlier is None:
                raise BusinessRuleError("Run the registration window first.")
            if earlier.is_open_at(now):
                raise BusinessRuleError(
                    "Registration is still open. Close it before opening presentations.")
        unassigned = db.scalar(
            select(InternshipEnrollment.id).where(
                InternshipEnrollment.program_id == program.id,
                InternshipEnrollment.mentor_faculty_id.is_(None)).limit(1))
        if unassigned is not None:
            raise BusinessRuleError(
                "Some registered students have no faculty mentor yet. Allocate mentors "
                "first — this window tells every student who their mentor is.")

    window = InternshipWindow(
        program_id=program.id, kind=kind, title=title.strip() or program.name,
        message=message.strip(), opens_at=opens_at, closes_at=closes_at,
        cohort_semester=cohort_semester if kind is Kind.REGISTRATION else None,
        submission_due_at=submission_due_at, presentation_from=presentation_from,
        presentation_to=presentation_to, opened_by_user_id=actor.id,
    )
    db.add(window)
    db.flush()
    audit.record(db, action=AuditAction.PUBLISH, entity_type="internship_window",
                 entity_id=window.id, actor=actor,
                 description=f"Opened the {kind.value.lower()} window for {program.code}",
                 meta={"opens_at": opens_at.isoformat(), "closes_at": closes_at.isoformat()})
    _notify(db, program, window, headline="opens")
    return window


def update_window(db: Session, window: InternshipWindow, *, actor: User,
                  closes_at: dt.datetime | None = None, opens_at: dt.datetime | None = None,
                  message: str | None = None, submission_due_at: dt.datetime | None = None,
                  presentation_from: dt.date | None = None,
                  presentation_to: dt.date | None = None,
                  now: dt.datetime | None = None) -> InternshipWindow:
    """Extend, reschedule or reopen. Students and mentors hear about it."""
    now = now or utcnow()
    program = db.get(InternshipProgram, window.program_id)
    new_opens = _aware(opens_at) or _aware(window.opens_at)
    new_closes = _aware(closes_at) or _aware(window.closes_at)
    new_due = _aware(submission_due_at) or _aware(window.submission_due_at)
    new_from = presentation_from or window.presentation_from
    new_to = presentation_to or window.presentation_to
    _validate_dates(window.kind, new_opens, new_closes, new_due, new_from, new_to, now)

    before = _when(window.closed_early_at or window.closes_at)
    was_closed = not window.is_open_at(now) and window.state_at(now) == "CLOSED"
    window.opens_at, window.closes_at = new_opens, new_closes
    window.submission_due_at, window.presentation_from, window.presentation_to = (
        new_due, new_from, new_to)
    if message is not None and message.strip():
        window.message = message.strip()
    window.closed_early_at = None
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_window",
                 entity_id=window.id, actor=actor,
                 description=(f"{'Reopened' if was_closed else 'Updated'} the "
                              f"{window.kind.value.lower()} window for {program.code}: "
                              f"deadline {before} → {_when(new_closes)}"))
    _notify(db, program, window, headline="reopened" if was_closed else "updated")
    return window


def close_window(db: Session, window: InternshipWindow, *, actor: User,
                 now: dt.datetime | None = None) -> InternshipWindow:
    """Close before the deadline — e.g. once every student has registered."""
    now = now or utcnow()
    if not window.is_open_at(now):
        raise BusinessRuleError("This window is not open.")
    window.closed_early_at = now
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="internship_window",
                 entity_id=window.id, actor=actor,
                 description=f"Closed the {window.kind.value.lower()} window early")
    return window


# ── notifications ─────────────────────────────────────────────────────────
def _dates_block(window: InternshipWindow) -> str:
    lines = [f"Opens: {_when(window.opens_at)}"]
    if window.kind is Kind.PRESENTATION:
        lines.append(f"Poster to your mentor by: {_when(window.submission_due_at)}")
        when = _when(window.presentation_from)
        if window.presentation_to and window.presentation_to != window.presentation_from:
            when += f" to {_when(window.presentation_to)}"
        lines.append(f"Presentation: {when}")
        lines.append(f"Marks deadline (work closes): {_when(window.closes_at)}")
    else:
        lines.append(f"Deadline: {_when(window.closes_at)}")
    return "\n".join(lines)


def _notify(db: Session, program: InternshipProgram, window: InternshipWindow,
            *, headline: str) -> int:
    link = f"/internships/{program.id}"
    verb = {"opens": "is open", "reopened": "has been reopened",
            "updated": "dates have changed"}[headline]
    sent = 0
    if window.kind is Kind.REGISTRATION:
        enrolled = set(db.scalars(select(InternshipEnrollment.student_id).where(
            InternshipEnrollment.program_id == program.id)))
        query = select(Student).where(Student.status == StudentStatus.ACTIVE)
        if program.department_id is not None:
            query = query.where(Student.department_id == program.department_id)
        if window.cohort_semester is not None:
            query = query.where(Student.current_semester == window.cohort_semester)
        recipients = {s.user_id for s in db.scalars(query)}
        recipients |= {s.user_id for s in db.scalars(
            select(Student).where(Student.id.in_(enrolled)))} if enrolled else set()
        notifications.notify_many(
            db, user_ids=recipients, type=NotificationType.INTERNSHIP_WINDOW,
            title=f"{program.name}: registration {verb}",
            message=f"{window.message}\n\n{_dates_block(window)}",
            link=link, priority=Priority.HIGH,
            meta={"window_id": window.id, "kind": window.kind.value},
        )
        return len(recipients)

    roster = mentor_roster(db, program)
    listing = "\n".join(f"• {g.name} — {g.roll_range} ({len(g.students)})" for g in roster)
    for group in roster:
        mentor = db.get(Faculty, group.faculty_id)
        for roll, _name in group.students:
            student = db.scalar(select(Student).where(Student.roll_number == roll))
            notifications.notify(
                db, user_id=student.user_id, type=NotificationType.INTERNSHIP_WINDOW,
                title=f"{program.name}: posters and presentations — your mentor is {group.name}",
                message=(f"{window.message}\n\nYour faculty mentor: {group.name}"
                         f"{f', {group.designation}' if group.designation else ''}"
                         f"{f' · Cabin {group.cabin}' if group.cabin else ''}"
                         f"{f' · {group.email}' if group.email else ''}\n\n"
                         f"{_dates_block(window)}\n\nMentors assigned:\n{listing}"),
                link=link, priority=Priority.HIGH,
                meta={"window_id": window.id, "kind": window.kind.value},
            )
            sent += 1
        notifications.notify(
            db, user_id=mentor.user_id, type=NotificationType.INTERNSHIP_WINDOW,
            title=f"{program.name}: {len(group.students)} students present to you",
            message=(f"Your students: {group.roll_range}. Posters reach you in the portal; "
                     f"record each student's marks after their presentation.\n\n"
                     f"{_dates_block(window)}\n\nMarks lock at the deadline."),
            link="/internships/review", priority=Priority.HIGH,
            meta={"window_id": window.id, "kind": window.kind.value},
        )
    return sent
