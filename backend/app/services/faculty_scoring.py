"""Faculty performance score: is a faculty member's student-facing work on time?

Every point comes from a dated record the portal already holds, and every point
is listed back to the faculty member with its reason — a score nobody can
explain is not a fair one to show a Head of Department.

What is scored, and only for the faculty member it belongs to:

* **Reviews** — a student's milestone, report or document. Credited to whoever
  reviewed it; while it waits, it is the responsibility of the student's mentor.
* **Marks** — a mentor's evaluation of each of their students, due by the
  close of a presentation window (CSSI). Programmes with no such deadline are
  not scored on marks.
* **Meeting requests** — how quickly the mentor answers.

The headline is a **score out of 100**: each item is placed on its own scale
from the worst outcome its category allows (0) to the best (100) — a review in
three days is 100, in a week 75, late 25, left waiting 0 — and the score is the
average. Forty mentees and four are compared fairly, because more work means
more items, not a bigger number. The points total and the on-time rate are
shown beside it.

The weights below are the department's choice, NOT a PDEU rule
(REQUIRES_FACULTY_CONFIRMATION). They live here and nowhere else.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.engagement import MentorMeeting
from app.models.enums import (
    EvaluationStatus, InternshipWindowKind, MeetingStatus, Role, StageStatus, SubmissionStatus,
)
from app.models.identity import Faculty, Student, User
from app.models.internships import (
    EnrollmentStageProgress, InternshipDocument, InternshipEnrollment, InternshipEvaluation,
    InternshipGroup, InternshipProgram, InternshipReport, InternshipStage, InternshipWindow,
)

#: The scoring policy. Department-set; change it here and the screens follow.
POLICY = {
    "review_fast_days": 3,        # reviewed within → +review_fast
    "review_ok_days": 7,          # reviewed within → +review_ok; later → review_late
    "review_fast": 2,
    "review_ok": 1,
    "review_late": -1,
    "review_overdue": -2,         # still waiting beyond review_ok_days
    "marks_on_time": 3,
    "marks_missed": -5,
    "meeting_fast_days": 2,
    "meeting_fast": 1,
    "meeting_overdue_days": 3,
    "meeting_overdue": -1,
    "period_days": 180,           # the window the score covers by default
}

#: Score bands (out of 100). A faculty member with fewer scored items is shown as such.
BANDS = [(90, "Excellent"), (75, "Good"), (50, "Needs attention"), (0, "At risk")]
MIN_ITEMS_FOR_BAND = 3


def point_range(category: str) -> tuple[int, int]:
    """(worst, best) points one item of `category` can earn under POLICY."""
    p = POLICY
    return {
        "REVIEW": (p["review_overdue"], p["review_fast"]),
        "MARKS": (p["marks_missed"], p["marks_on_time"]),
        "MEETING": (p["meeting_overdue"], p["meeting_fast"]),
    }[category]


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


@dataclass(slots=True)
class Entry:
    when: dt.datetime
    category: str          # REVIEW | MARKS | MEETING
    label: str
    outcome: str           # ON_TIME | LATE | OVERDUE | MISSED
    points: int
    days: float | None = None


@dataclass
class Score:
    faculty_id: int
    points: int = 0
    on_time: int = 0
    late: int = 0
    overdue: int = 0       # still waiting past the limit (reviews, meetings)
    missed: int = 0        # marks missing at the deadline
    pending: int = 0       # waiting, still within the limit — not scored yet
    quality: float = 0.0   # sum over items of where each fell, worst 0 … best 1
    by_category: dict = field(default_factory=lambda: defaultdict(int))
    entries: list[Entry] = field(default_factory=list)

    def add(self, entry: Entry) -> None:
        worst, best = point_range(entry.category)
        self.quality += (entry.points - worst) / (best - worst)
        self.points += entry.points
        self.by_category[entry.category] += entry.points
        if entry.outcome == "ON_TIME":
            self.on_time += 1
        elif entry.outcome == "LATE":
            self.late += 1
        elif entry.outcome == "OVERDUE":
            self.overdue += 1
        elif entry.outcome == "MISSED":
            self.missed += 1
        self.entries.append(entry)

    @property
    def scored(self) -> int:
        return self.on_time + self.late + self.overdue + self.missed

    @property
    def on_time_rate(self) -> float | None:
        return self.on_time / self.scored if self.scored else None

    @property
    def score(self) -> int | None:
        """Out of 100: the average item, worst 0 to best 100."""
        return round(100 * self.quality / self.scored) if self.scored else None

    @property
    def band(self) -> str:
        if self.scored < MIN_ITEMS_FOR_BAND:
            return "Not enough activity"
        return next(label for floor, label in BANDS if (self.score or 0) >= floor)



# ── scoring rules ─────────────────────────────────────────────────────────
def score_review(submitted: dt.datetime, reviewed: dt.datetime | None,
                 now: dt.datetime) -> tuple[str, int, float] | None:
    """(outcome, points, days) for one submission; None while still within time."""
    p = POLICY
    if reviewed is not None:
        days = (reviewed - submitted).total_seconds() / 86400
        if days <= p["review_fast_days"]:
            return "ON_TIME", p["review_fast"], days
        if days <= p["review_ok_days"]:
            return "ON_TIME", p["review_ok"], days
        return "LATE", p["review_late"], days
    waited = (now - submitted).total_seconds() / 86400
    if waited > p["review_ok_days"]:
        return "OVERDUE", p["review_overdue"], waited
    return None


def score_meeting(requested: dt.datetime, responded: dt.datetime | None, still_open: bool,
                  now: dt.datetime) -> tuple[str, int, float] | None:
    p = POLICY
    if responded is not None:
        days = (responded - requested).total_seconds() / 86400
        if days <= p["meeting_fast_days"]:
            return "ON_TIME", p["meeting_fast"], days
        return "LATE", 0, days
    if still_open:
        waited = (now - requested).total_seconds() / 86400
        if waited > p["meeting_overdue_days"]:
            return "OVERDUE", p["meeting_overdue"], waited
    return None


# ── computation ───────────────────────────────────────────────────────────
def is_office(faculty: Faculty) -> bool:
    """A department office account: administration, not a person to score."""
    return not faculty.is_mentor and faculty.user.has_role(Role.DEPARTMENT_ADMIN)


def is_scorable(faculty: Faculty) -> bool:
    """Real faculty are scored only once the portal runs on real activity."""
    if is_office(faculty):
        return False
    return faculty.is_demo or settings.SCORE_REAL_FACULTY


def department_scores(db: Session, department_id: int, *, now: dt.datetime | None = None,
                      period_days: int | None = None) -> dict[int, Score]:
    """Scores for every active faculty member of one department."""
    now = now or utcnow()
    since = now - dt.timedelta(days=period_days or POLICY["period_days"])
    faculty = [f for f in db.scalars(select(Faculty).where(
        Faculty.department_id == department_id, Faculty.is_active.is_(True))
        .options(selectinload(Faculty.user).selectinload(User.role_links))) if is_scorable(f)]
    scores = {f.id: Score(faculty_id=f.id) for f in faculty}
    if not scores:
        return scores
    faculty_by_user = {f.user_id: f.id for f in faculty}

    # Who answers for each enrollment while work waits: its mentor, else the
    # faculty in charge of its group.
    enrollments = {e.id: e for e in db.scalars(select(InternshipEnrollment))}
    group_lead = dict(db.execute(select(InternshipGroup.id, InternshipGroup.faculty_id)).all())

    def responsible(enrollment_id: int) -> int | None:
        e = enrollments.get(enrollment_id)
        if e is None:
            return None
        return e.mentor_faculty_id or (group_lead.get(e.group_id) if e.group_id else None)

    # One query for every label. Loading each student's account per scored
    # item was ~260 queries a call (QA query profile, 10k-student dataset).
    names = {eid: f"{name} ({roll})" for eid, name, roll in db.execute(
        select(InternshipEnrollment.id, User.full_name, Student.roll_number)
        .join(Student, Student.id == InternshipEnrollment.student_id)
        .join(User, User.id == Student.user_id))}

    def student_name(enrollment_id: int) -> str:
        return names.get(enrollment_id, "a student")


    def credit(enrollment_id: int, reviewer_user_id: int | None, submitted, reviewed, what: str):
        submitted, reviewed = _aware(submitted), _aware(reviewed)
        if submitted is None or submitted < since:
            return
        owner = faculty_by_user.get(reviewer_user_id) if reviewed else None
        owner = owner or responsible(enrollment_id)
        if owner not in scores:
            return
        result = score_review(submitted, reviewed, now)
        if result is None:
            scores[owner].pending += 1
            return
        outcome, points, days = result
        scores[owner].add(Entry(when=reviewed or now, category="REVIEW", outcome=outcome,
                                points=points, days=round(days, 1),
                                label=f"{what} — {student_name(enrollment_id)}"))

    stage_names = dict(db.execute(select(InternshipStage.id, InternshipStage.name)).all())
    for row in db.scalars(select(EnrollmentStageProgress).where(
            EnrollmentStageProgress.submitted_at.is_not(None),
            EnrollmentStageProgress.status.in_([StageStatus.SUBMITTED, StageStatus.APPROVED,
                                                StageStatus.REJECTED]))):
        credit(row.enrollment_id, row.reviewed_by_user_id, row.submitted_at,
               row.reviewed_at if row.status != StageStatus.SUBMITTED else None,
               f"Milestone “{stage_names.get(row.stage_id, 'stage')}”")
    for row in db.scalars(select(InternshipReport).where(InternshipReport.submitted_at.is_not(None))):
        reviewed = row.reviewed_at if row.status != SubmissionStatus.SUBMITTED else None
        credit(row.enrollment_id, row.reviewed_by_user_id, row.submitted_at, reviewed,
               f"Report #{row.sequence_number}")
    for row in db.scalars(select(InternshipDocument).where(InternshipDocument.submitted_at.is_not(None))):
        reviewed = row.reviewed_at if row.status not in (SubmissionStatus.SUBMITTED,) else None
        credit(row.enrollment_id, row.reviewed_by_user_id, row.submitted_at, reviewed,
               f"Document “{row.title or row.document_type.value.title()}”")

    # Marks: due by the close of each presentation window that has closed.
    for window in db.scalars(select(InternshipWindow).where(
            InternshipWindow.kind == InternshipWindowKind.PRESENTATION)):
        deadline = _aware(window.closed_early_at) or _aware(window.closes_at)
        if deadline is None or deadline > now or deadline < since:
            continue
        program = db.get(InternshipProgram, window.program_id)
        for e in (x for x in enrollments.values() if x.program_id == window.program_id):
            owner = e.mentor_faculty_id
            if owner not in scores:
                continue
            mentor = db.get(Faculty, owner)
            ev = db.scalar(select(InternshipEvaluation).where(
                InternshipEvaluation.enrollment_id == e.id,
                InternshipEvaluation.evaluator_user_id == mentor.user_id))
            done = (ev is not None and ev.status in (EvaluationStatus.SUBMITTED, EvaluationStatus.FINALISED)
                    and ev.submitted_at is not None and _aware(ev.submitted_at) <= deadline)
            scores[owner].add(Entry(
                when=deadline, category="MARKS",
                outcome="ON_TIME" if done else "MISSED",
                points=POLICY["marks_on_time"] if done else POLICY["marks_missed"],
                label=f"Marks for {student_name(e.id)} — {program.code if program else 'programme'}"))

    # Meeting requests.
    for m in db.scalars(select(MentorMeeting).where(MentorMeeting.faculty_id.in_(scores.keys()))):
        requested = _aware(m.requested_at)
        if requested is None or requested < since:
            continue
        result = score_meeting(requested, _aware(m.responded_at),
                               m.status == MeetingStatus.REQUESTED, now)
        if result is None:
            if m.status == MeetingStatus.REQUESTED:
                scores[m.faculty_id].pending += 1
            continue
        outcome, points, days = result
        scores[m.faculty_id].add(Entry(when=_aware(m.responded_at) or now, category="MEETING",
                                       outcome=outcome, points=points, days=round(days, 1),
                                       label=f"Meeting request — {m.title}"))
    return scores


def faculty_score(db: Session, faculty: Faculty, **kwargs) -> Score:
    return department_scores(db, faculty.department_id, **kwargs).get(
        faculty.id, Score(faculty_id=faculty.id))
