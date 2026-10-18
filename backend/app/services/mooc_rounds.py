"""NPTEL / NCC rounds: the Semester V Open Elective, end to end.

How the ICT department runs it (the coordinator's emails to the 2024 batch,
and the department's answers to the project team):

1. The coordinator circulates an **approved list** of NPTEL courses — 12-week
   courses only, each worth 3 credits — and opens the choice with a deadline.
2. Each student picks **one course from the list, or NCC**. There is no limit
   per course. Students register on the NPTEL portal themselves; the portal
   does not track that, and it is the student's responsibility.
3. At the end of the semester the student submits the **certificate** (NPTEL
   certifies only those who pass; NCC students submit their NCC certificate) —
   or reports that they **did not pass**. The coordinator verifies it.
4. **Closing the semester** records each student's outcome. A slot not
   cleared carries over to the next semester, where the student chooses again
   (the same or an updated list, NPTEL or NCC). Not cleared there either, it
   is a **backlog**.

The department's numbers live here, once: a course must run for
``REQUIRED_WEEKS`` and is worth ``CREDITS``.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.academics import (
    Course, Curriculum, CurriculumComponent, MoocRegistration, MoocRound, MoocRoundCourse,
    MoocRoundOutcome,
)
from app.models.enums import (
    ComponentType, MoocOption, MoocOutcome, MoocPlatform, MoocRoundStatus, MoocStatus,
    VerificationStatus,
)
from app.models.identity import Student

#: Only courses of this length are approved, and each is worth CREDITS
#: (the ICT department's rule, as told to the project team).
REQUIRED_WEEKS = 12
CREDITS = 3


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── who a round is for ─────────────────────────────────────────────────────
@dataclass(slots=True)
class Covered:
    student: Student
    #: Choosing again because the slot was not cleared in an earlier round.
    carry_over: bool


def _latest_outcomes(db: Session, component_id: int,
                     student_ids: list[int] | None = None) -> dict[int, MoocOutcome]:
    stmt = (select(MoocRoundOutcome)
            .where(MoocRoundOutcome.curriculum_component_id == component_id)
            .order_by(MoocRoundOutcome.id))
    if student_ids is not None:
        stmt = stmt.where(MoocRoundOutcome.student_id.in_(student_ids or [0]))
    latest: dict[int, MoocOutcome] = {}
    for row in db.scalars(stmt):
        latest[row.student_id] = MoocOutcome(row.outcome)
    return latest


def _verified_student_ids(db: Session, component_id: int) -> set[int]:
    return set(db.scalars(select(MoocRegistration.student_id).where(
        MoocRegistration.curriculum_component_id == component_id,
        MoocRegistration.verification_status == VerificationStatus.VERIFIED)))


def _governed(db: Session, round_: MoocRound, students) -> list[Student]:
    from app.services.curriculum import resolve_curriculum

    component = db.get(CurriculumComponent, round_.curriculum_component_id)
    curriculum = db.get(Curriculum, component.curriculum_id) if component else None
    if curriculum is None:
        return []
    # Governed by this curriculum, by the portal's one rule for that (an older
    # batch with no version of its own falls back to the newest open-ended one).
    return [s for s in students
            if s.program_id == curriculum.program_id
            and (governing := resolve_curriculum(db, s)) is not None
            and governing.id == curriculum.id]


def _coverage(db: Session, round_: MoocRound, students: list[Student], *,
              include_cleared: bool = False) -> list[Covered]:
    students = _governed(db, round_, students)
    component_id = round_.curriculum_component_id
    latest = _latest_outcomes(db, component_id, [s.id for s in students])
    cleared = _verified_student_ids(db, component_id)
    semesters = set(round_.eligible_semesters or [])
    out: list[Covered] = []
    for student in students:
        if student.id in cleared and not include_cleared:
            continue
        state = latest.get(student.id)
        if state in (MoocOutcome.CLEARED, MoocOutcome.BACKLOG):
            continue
        # A round's own outcomes are written when it closes; while it runs, the
        # earlier rounds are what decide who is carrying over.
        if state == MoocOutcome.CARRIED_OVER:
            out.append(Covered(student, carry_over=True))
        elif student.current_semester in semesters:
            out.append(Covered(student, carry_over=False))
    return out


def covered_students(db: Session, round_: MoocRound, *,
                     include_cleared: bool = False) -> list[Covered]:
    """The students who choose in this round.

    Those in the round's semesters who have not already cleared the slot, and
    — whatever their semester now — anyone carrying it over from an earlier
    round. A student with a backlog is not chosen for again.
    """
    component = db.get(CurriculumComponent, round_.curriculum_component_id)
    curriculum = db.get(Curriculum, component.curriculum_id) if component else None
    if curriculum is None:
        return []
    students = list(db.scalars(select(Student).where(
        Student.program_id == curriculum.program_id).order_by(Student.roll_number)))
    return _coverage(db, round_, students, include_cleared=include_cleared)


def covers(db: Session, round_: MoocRound, student: Student) -> Covered | None:
    found = _coverage(db, round_, [student])
    return found[0] if found else None


def standing(db: Session, student: Student, component_id: int) -> MoocOutcome | None:
    """Cleared, carried over, a backlog — or still undecided (None)."""
    if student.id in _verified_student_ids(db, component_id):
        return MoocOutcome.CLEARED
    return _latest_outcomes(db, component_id, [student.id]).get(student.id)


def round_for_student(db: Session, student: Student) -> tuple[MoocRound, Covered] | None:
    """The live round covering this student, if any: open first, then locked
    (certificates still due), newest first."""
    order = {MoocRoundStatus.OPEN: 0, MoocRoundStatus.LOCKED: 1}
    rounds = sorted(
        db.scalars(select(MoocRound).where(MoocRound.status.in_(
            [MoocRoundStatus.OPEN, MoocRoundStatus.LOCKED]))),
        key=lambda r: (order[r.status], -r.id))
    for round_ in rounds:
        covered = covers(db, round_, student)
        if covered:
            return round_, covered
    return None


# ── the approved list ──────────────────────────────────────────────────────
def approved_courses(db: Session, round_: MoocRound) -> list[Course]:
    return [rc.course for rc in db.scalars(
        select(MoocRoundCourse).where(MoocRoundCourse.mooc_round_id == round_.id)
        .order_by(MoocRoundCourse.id))]


@dataclass(slots=True)
class CourseRow:
    code: str
    title: str
    weeks: int | None = None
    url: str | None = None
    discipline: str | None = None
    instructors: str | None = None
    institute: str | None = None
    coordinating_institute: str | None = None


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    already_listed: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def assert_list_editable(round_: MoocRound) -> None:
    if round_.status == MoocRoundStatus.CLOSED:
        raise BusinessRuleError("This round is closed; its course list is the record.")


def add_course(db: Session, round_: MoocRound, row: CourseRow) -> tuple[Course, str]:
    """Put one course on the list. Returns the course and what happened:
    'added', 'updated' (already in the catalogue) or 'already listed'."""
    assert_list_editable(round_)
    code = row.code.strip()
    title = row.title.strip()
    if not code or not title:
        raise ValidationError("Each course needs its NPTEL course ID and name.")
    if row.weeks != REQUIRED_WEEKS:
        raise ValidationError(
            f"{code}: only {REQUIRED_WEEKS}-week courses are approved"
            + (f" (this one runs {row.weeks} weeks)." if row.weeks else
               " (no duration given)."))
    course = db.scalar(select(Course).where(func.lower(Course.code) == code.lower()))
    state = "updated"
    if course is None:
        course = Course(code=code, title=title)
        db.add(course)
        state = "added"
    course.title = title
    course.platform = MoocPlatform.NPTEL
    course.duration_weeks = REQUIRED_WEEKS
    course.credits = CREDITS
    if row.url:
        course.provider_url = row.url
    if row.coordinating_institute or row.institute:
        course.offering_school = row.coordinating_institute or row.institute
    details = dict(course.provider_details or {})
    for key in ("discipline", "instructors", "institute", "coordinating_institute"):
        value = getattr(row, key)
        if value:
            details[key] = value
    course.provider_details = details
    db.flush()
    if db.scalar(select(MoocRoundCourse).where(
            MoocRoundCourse.mooc_round_id == round_.id,
            MoocRoundCourse.course_id == course.id)):
        return course, "already listed"
    db.add(MoocRoundCourse(mooc_round_id=round_.id, course_id=course.id))
    db.flush()
    return course, state


def import_courses(db: Session, round_: MoocRound, rows: list[CourseRow]) -> ImportResult:
    result = ImportResult()
    if not rows:
        raise ValidationError("No courses were found in that file.")
    for row in rows:
        try:
            course, state = add_course(db, round_, row)
        except ValidationError as exc:
            result.skipped.append((row.code or row.title or "?", exc.message))
            continue
        {"added": result.added, "updated": result.updated,
         "already listed": result.already_listed}[state].append(course.code)
    return result


def remove_course(db: Session, round_: MoocRound, course_id: int) -> None:
    assert_list_editable(round_)
    link = db.scalar(select(MoocRoundCourse).where(
        MoocRoundCourse.mooc_round_id == round_.id, MoocRoundCourse.course_id == course_id))
    if link is None:
        raise NotFoundError("That course is not on this round's list.")
    taken = db.scalar(select(func.count(MoocRegistration.id)).where(
        MoocRegistration.mooc_round_id == round_.id, MoocRegistration.course_id == course_id))
    if taken:
        raise BusinessRuleError(
            f"{taken} student(s) chose this course in this round, so it stays on the list.")
    db.delete(link)


def copy_list(db: Session, round_: MoocRound, source: MoocRound) -> int:
    assert_list_editable(round_)
    have = {c.id for c in approved_courses(db, round_)}
    added = 0
    for course in approved_courses(db, source):
        if course.id not in have:
            db.add(MoocRoundCourse(mooc_round_id=round_.id, course_id=course.id))
            added += 1
    db.flush()
    return added


# ── reading the department's sheet (.xlsx or .csv) ─────────────────────────
_HEADERS = {
    "code": ("course id", "courseid", "course code", "nptel id"),
    "title": ("course name", "course title", "name of the course", "course"),
    "weeks": ("duration", "weeks", "no. of weeks", "number of weeks"),
    "url": ("nptel url", "url", "link", "course url"),
    "discipline": ("discipline",),
    "instructors": ("sme name", "sme", "instructor", "faculty"),
    "institute": ("institute",),
    "coordinating_institute": ("coordinating institute",),
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip().lower()


def _column_map(header: list[str]) -> dict[str, int]:
    cells = [_norm(h) for h in header]
    found: dict[str, int] = {}
    # Exact names first, so "Institute" never claims "Coordinating Institute".
    for key, names in _HEADERS.items():
        for i, cell in enumerate(cells):
            if cell in names and i not in found.values():
                found[key] = i
                break
    return found


def _weeks(value) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def rows_from_table(table: list[list[str]]) -> list[CourseRow]:
    """Find the header row (it names the course ID and name), then read on."""
    for index, row in enumerate(table):
        columns = _column_map(row)
        if "code" in columns and "title" in columns:
            break
    else:
        raise ValidationError(
            "Could not find the header row. The sheet needs at least a "
            "'Course ID' and a 'Course Name' column.")
    out: list[CourseRow] = []
    for raw in table[index + 1:]:
        def cell(key):
            i = columns.get(key)
            value = raw[i] if i is not None and i < len(raw) else ""
            value = re.sub(r"\s+", " ", str(value or "")).strip()
            return value or None
        code, title = cell("code"), cell("title")
        if not code and not title:
            continue
        url = cell("url")
        out.append(CourseRow(
            code=code or "", title=title or "", weeks=_weeks(cell("weeks")),
            url=url.replace(" ", "") if url else None, discipline=cell("discipline"),
            instructors=cell("instructors"), institute=cell("institute"),
            coordinating_institute=cell("coordinating_institute")))
    return out


def _xlsx_table(content: bytes) -> list[list[str]]:
    """The first worksheet of an .xlsx, as rows of text. No dependency needed:
    the format is a zip of XML parts."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        book = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValidationError("That file is not a readable .xlsx workbook.") from exc
    shared: list[str] = []
    if "xl/sharedStrings.xml" in book.namelist():
        root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
        for item in root.findall("m:si", ns):
            shared.append("".join(t.text or "" for t in item.iter(f"{{{ns['m']}}}t")))
    sheets = sorted(n for n in book.namelist()
                    if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
    if not sheets:
        raise ValidationError("That workbook has no worksheet.")
    root = ElementTree.fromstring(book.read(sheets[0]))
    table: list[list[str]] = []
    for row in root.iter(f"{{{ns['m']}}}row"):
        values: dict[int, str] = {}
        for c in row.findall("m:c", ns):
            ref = c.get("r", "")
            letters = re.match(r"[A-Z]+", ref)
            col = 0
            for ch in (letters.group() if letters else ""):
                col = col * 26 + (ord(ch) - 64)
            kind = c.get("t")
            if kind == "s":
                v = c.find("m:v", ns)
                text = shared[int(v.text)] if v is not None and v.text else ""
            elif kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
            else:
                v = c.find("m:v", ns)
                text = v.text if v is not None and v.text else ""
            values[col - 1 if letters else len(values)] = text
        if values:
            width = max(values) + 1
            table.append([values.get(i, "") for i in range(width)])
    return table


def parse_sheet(content: bytes, filename: str) -> list[CourseRow]:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        return rows_from_table(_xlsx_table(content))
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        return rows_from_table([row for row in csv.reader(io.StringIO(text))])
    raise ValidationError("Upload the course list as an .xlsx or .csv file.")


# ── the student's choice and result ────────────────────────────────────────
def choose(db: Session, round_: MoocRound, student: Student, *, option: MoocOption,
           course_id: int | None, now: dt.datetime | None = None) -> MoocRegistration:
    """Record (or change) this student's choice in an open round."""
    now = now or utcnow()
    if not round_.is_open_at(now):
        if round_.status == MoocRoundStatus.OPEN and round_.closes_at_utc \
                and now >= round_.closes_at_utc:
            raise BusinessRuleError("The deadline for choosing has passed.")
        raise BusinessRuleError("Choosing is not open in this round.")
    if covers(db, round_, student) is None:
        raise BusinessRuleError("This round is not for you.")
    course = None
    if option == MoocOption.NPTEL:
        if course_id is None:
            raise ValidationError("Choose a course from the approved list.")
        if course_id not in {c.id for c in approved_courses(db, round_)}:
            raise ValidationError(
                "Choose a course from the approved list; other NPTEL courses are not "
                "accepted.")
        course = db.get(Course, course_id)
    elif course_id is not None:
        raise ValidationError("NCC has no course to choose.")

    reg = db.scalar(select(MoocRegistration).where(
        MoocRegistration.mooc_round_id == round_.id,
        MoocRegistration.student_id == student.id))
    if reg is None:
        reg = MoocRegistration(student_id=student.id, mooc_round_id=round_.id,
                               curriculum_component_id=round_.curriculum_component_id)
        db.add(reg)
    elif reg.certificate_file_id is not None:
        raise BusinessRuleError("A certificate has been submitted; the choice is final.")
    reg.option = option
    reg.course_id = course.id if course else None
    reg.course_offering_id = None
    reg.platform = MoocPlatform.NPTEL if option == MoocOption.NPTEL else MoocPlatform.OTHER
    reg.course_url = course.provider_url if course else None
    reg.status = MoocStatus.REGISTERED
    db.flush()
    return reg


def assert_can_submit_result(round_: MoocRound | None, reg: MoocRegistration) -> None:
    if reg.verification_status == VerificationStatus.VERIFIED:
        raise BusinessRuleError("This has been verified and can no longer be changed.")
    if round_ is not None and round_.status == MoocRoundStatus.CLOSED:
        raise BusinessRuleError("This round's semester is closed.")


def report_failed(db: Session, round_: MoocRound | None, reg: MoocRegistration) -> None:
    """The student did not pass: NPTEL gives them no certificate."""
    assert_can_submit_result(round_, reg)
    reg.status = MoocStatus.FAILED
    reg.certificate_file_id = None
    reg.verification_status = VerificationStatus.PENDING


# ── closing the semester ───────────────────────────────────────────────────
@dataclass
class CloseResult:
    cleared: list[int] = field(default_factory=list)
    carried_over: list[int] = field(default_factory=list)
    backlog: list[int] = field(default_factory=list)
    awaiting_verification: int = 0


def close_round(db: Session, round_: MoocRound, *, force: bool = False) -> CloseResult:
    """Record every covered student's outcome and close the round.

    A certificate still waiting for the coordinator's verification holds the
    close back — closing would carry that student over for the coordinator's
    delay — unless ``force`` says to go ahead.
    """
    if round_.status != MoocRoundStatus.LOCKED:
        raise BusinessRuleError("Lock the round before closing its semester.")
    # Including those verified during this round: clearing it is an outcome.
    covered = covered_students(db, round_, include_cleared=True)
    regs = {r.student_id: r for r in db.scalars(select(MoocRegistration).where(
        MoocRegistration.mooc_round_id == round_.id))}
    waiting = sum(1 for c in covered
                  if (r := regs.get(c.student.id)) is not None
                  and r.certificate_file_id is not None
                  and r.verification_status == VerificationStatus.PENDING)
    result = CloseResult(awaiting_verification=waiting)
    if waiting and not force:
        raise BusinessRuleError(
            f"{waiting} certificate(s) are still waiting for verification. Verify or "
            "reject them first, or close anyway to carry those students over.")
    verified = _verified_student_ids(db, round_.curriculum_component_id)
    for c in covered:
        if c.student.id in verified:
            outcome, bucket = MoocOutcome.CLEARED, result.cleared
        elif c.carry_over:
            outcome, bucket = MoocOutcome.BACKLOG, result.backlog
        else:
            outcome, bucket = MoocOutcome.CARRIED_OVER, result.carried_over
        db.add(MoocRoundOutcome(mooc_round_id=round_.id, student_id=c.student.id,
                                curriculum_component_id=round_.curriculum_component_id,
                                outcome=outcome, semester_at_close=c.student.current_semester))
        bucket.append(c.student.id)
    round_.status = MoocRoundStatus.CLOSED
    round_.closed_at = utcnow()
    db.flush()
    return result


def mooc_component(db: Session, student: Student) -> CurriculumComponent | None:
    from app.services.eligibility import components_for_semester

    components = [c for c in components_for_semester(db, student)
                  if c.component_type == ComponentType.MOOC]
    unlocked = [c for c in components if c.semester_number <= student.current_semester]
    return (unlocked or components or [None])[0]
