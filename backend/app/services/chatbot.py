"""Role-aware, confidentiality-guarded conversational assistant service."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.academics import ElectiveRegistrationWindow, MoocRegistration
from app.models.engagement import MentorAssignment, MentorMeeting, Notification
from app.models.enums import (
    EnrollmentStatus, MeetingStatus, RegistrationWindowStatus, Role, StageStatus, SubmissionStatus,
)
from app.models.identity import Department, Faculty, FacultyRoleAssignment, Student, User
from app.models.internships import (
    EnrollmentStageProgress, InternshipDocument, InternshipEnrollment, InternshipReport,
    InternshipStage,
)
from app.models.minors import MinorApplication, MinorEnrollment, MinorProgram
from app.services import faculty_scoring as scoring
from app.services import minors as minors_service
from app.services.faculty_scoring import _aware
from app.schemas.chatbot import ChatActionLink, ChatMessageItem, ChatQueryResponse


# ─────────────────────────────────────────────────────────────────────────────
# Confidentiality & Data Privacy Guards
# ─────────────────────────────────────────────────────────────────────────────

SENSITIVE_PATTERNS = [
    # System secrets and infra
    r"(secret_key|database_url|postgres_password|jwt_secret|aws_access_key|\.env|password_hash|seed_default_password)",
    r"(system password|db password|admin password|server credentials|root access)",
    r"(ignore (all )?previous instructions|system prompt|jailbreak|act as (super )?admin|pretend you have admin)",
    # Other students' private data
    r"(other student'?s? (cpi|grades?|cgpa|marks|ranking|phone|email))",
    r"(cpi of|cgpa of|grades? of|marks of|details of) (all |other |another )?student",
    r"(list|show|give me) (all|every) student'?s? (cpi|cgpa|grades?|marks)",
    r"(who (has|got) the highest cpi|highest cgpa|top rankers?)",
    r"(\w+)'s (cpi|grades?|cgpa|marks)",
    r"(disciplinary records?|confidential (notes?|remarks?)|internal faculty remarks)",
    r"(audit logs?|system logs?|who modified|audit trail)",
]

COMPILED_SENSITIVE = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS]


def _check_confidentiality_leakage(query: str, user: User, is_admin: bool) -> tuple[bool, str | None]:
    """Check whether query attempts to access confidential or cross-boundary data."""
    q_lower = query.lower()

    # System credentials & jailbreaks are blocked for everyone
    if any(k in q_lower for k in ["secret_key", "postgres_password", "database_url", "aws_access_key", "jwt_secret", ".env"]):
        return True, "Under CampusHub Security Policy, system credentials, encryption keys, and environment variables are strictly classified and cannot be retrieved through the chat interface."

    if any(k in q_lower for k in ["ignore previous instructions", "act as super admin", "bypass security", "pretend you are admin"]):
        return True, "Prompt overrides and role spoofing attempts are prohibited. CampusHub enforces strict server-side RBAC and data isolation."

    # Non-admins cannot see audit logs
    if not is_admin and any(k in q_lower for k in ["audit log", "audit trail", "system logs"]):
        return True, "Audit logs contain institutional audit trails and are restricted exclusively to Super Administrators. You do not have permission to view audit logs."

    # Students cannot ask for other students' CPI, grades, or personal records
    if user.has_role(Role.STUDENT):
        # Academic performance privacy check
        if any(term in q_lower for term in ["cpi", "cgpa", "grade", "marks", "ranking", "rank", "score"]):
            is_self_query = bool(re.search(r"\b(my|mine)\b", q_lower)) and not any(
                term in q_lower for term in ["all", "other", "another", "everyone", "who", "highest", "top", "batch"]
            )
            if not is_self_query:
                return True, (
                    "Under PDEU Academic Data Privacy Regulations, students may only access their own academic records. "
                    "Information regarding other students' CPI, grades, rankings, or personal details is strictly confidential."
                )

        for pattern in COMPILED_SENSITIVE:
            if pattern.search(query):
                if re.search(r"\bmy (status|mentor|internship|record)\b", q_lower):
                    continue
                return True, (
                    "Under PDEU Academic Data Privacy Regulations, students may only access their own academic records. "
                    "Information regarding other students' CPI, grades, rankings, or personal details is strictly confidential."
                )

        # Disallow administrative actions via chat
        if any(k in q_lower for k in ["change my grade", "update my cpi", "force allocate", "bypass prerequisite", "approve my report"]):
            return True, "The conversational assistant provides read-only informational guidance. Official academic records and approvals must proceed through formal departmental workflows."

    # Faculty who are not admin cannot view all student CPIs globally
    if user.has_role(Role.FACULTY) and not is_admin:
        if any(k in q_lower for k in ["show all student cpi", "list all students with cpi", "highest cpi across university"]):
            return True, "Institutional CPI rosters across all departments are restricted to Heads of Department and Academic Deans."

    return False, None


# ─────────────────────────────────────────────────────────────────────────────
# Role Context Extractor
# ─────────────────────────────────────────────────────────────────────────────

def get_user_role_context(user: User, db: Session) -> dict[str, Any]:
    """Extract role identity, scope, and permissible live data for the user."""
    is_admin = user.has_role(Role.SUPER_ADMIN)
    context: dict[str, Any] = {
        "user_id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": user.roles[0].value if user.roles else "USER",
        "role_badge": "User",
        "is_admin": is_admin,
        "student": None,
        "faculty": None,
        "coordinator_roles": [],
        "is_hod": user.has_role(Role.HOD),
        "department_name": None,
    }

    if user.has_role(Role.STUDENT):
        student = db.scalar(select(Student).where(Student.user_id == user.id))
        if student:
            dept = db.scalar(select(Department).where(Department.id == student.department_id))
            context["student"] = {
                "id": student.id,
                "roll_number": student.roll_number,
                "semester": student.current_semester,
                "cpi": float(student.cpi) if student.cpi is not None else None,
                "backlog_count": student.backlog_count,
                "department_id": student.department_id,
                "department_name": dept.name if dept else "Unknown",
                "department_code": dept.code if dept else "",
            }
            context["role_badge"] = f"Student · {dept.code if dept else ''} Sem {student.current_semester}"

    elif user.has_role(Role.FACULTY, Role.HOD, Role.SUPER_ADMIN):
        faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
        if faculty:
            dept = db.scalar(select(Department).where(Department.id == faculty.department_id))
            is_hod = user.has_role(Role.HOD) or bool(dept and dept.hod_faculty_id == faculty.id)
            roles = db.scalars(
                select(FacultyRoleAssignment).where(
                    FacultyRoleAssignment.faculty_id == faculty.id,
                    FacultyRoleAssignment.is_active.is_(True),
                )
            ).all()

            context["faculty"] = {
                "id": faculty.id,
                "designation": faculty.designation,
                "department_id": faculty.department_id,
                "department_name": dept.name if dept else "Unknown",
                "department_code": dept.code if dept else "",
                "is_hod": is_hod,
            }
            context["is_hod"] = is_hod
            context["coordinator_roles"] = [f"{r.role.value}:{r.domain.value}" for r in roles]

            if is_admin:
                context["role_badge"] = "Super Admin"
            elif is_hod:
                context["role_badge"] = f"HOD · {dept.code if dept else ''}"
            elif roles:
                first_domain = roles[0].domain.value.replace("_", " ").title()
                context["role_badge"] = f"Coord ({first_domain})"
            else:
                context["role_badge"] = f"Faculty · {dept.code if dept else ''}"

    return context


# ─────────────────────────────────────────────────────────────────────────────
# Answering engine
#
# Every answer is read from the asker's own records at the moment they ask —
# nothing is canned except the "what I can do" help. Two rules:
#
# * No university rule is stated that the portal does not hold. Where a
#   question is about policy the portal has no record of (attendance,
#   grading), the answer says so and points to the official source.
# * Every link is a route the app has (App.tsx).
# ─────────────────────────────────────────────────────────────────────────────

Answer = tuple[str, list[ChatActionLink], list[str]]
IST = ZoneInfo("Asia/Kolkata")

STUDENT_SUGGESTIONS = ["What is my name and roll number?", "Who is my mentor?",
                       "Show my meeting requests", "What is my internship status?",
                       "Are elective registrations open?"]
FACULTY_SUGGESTIONS = ["Show pending meeting requests", "Show my mentees",
                       "What needs my review?", "What is my performance score?"]
ADMIN_SUGGESTIONS = ["Who am I signed in as?", "Show a portal summary"]


def _has(q: str, *phrases: str) -> bool:
    """Whole-word match for any phrase — "mentor" does not match "mentorship"
    unless asked for, "rank" does not match "frank"."""
    return any(re.search(rf"\b{re.escape(p)}\b", q) for p in phrases)


def _when(moment: dt.datetime | None) -> str:
    if moment is None:
        return "not set"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(IST).strftime("%d %b %Y, %I:%M %p")


def _human(value: Any) -> str:
    return str(getattr(value, "value", value)).replace("_", " ").capitalize()


def _suggest(user: User) -> list[str]:
    if user.has_role(Role.STUDENT):
        return STUDENT_SUGGESTIONS
    if user.has_role(Role.FACULTY, Role.HOD):
        return FACULTY_SUGGESTIONS
    return ADMIN_SUGGESTIONS


# ── shared answers ────────────────────────────────────────────────────────
def _greeting(user: User, context: dict[str, Any]) -> Answer:
    if user.has_role(Role.STUDENT):
        what = ("your details, your mentor and meeting requests, your internship, open "
                "elective rounds, your minor and your NPTEL courses")
    elif user.has_role(Role.FACULTY, Role.HOD):
        what = ("your meeting requests, your mentees, work waiting for your review, your "
                "roles and your performance score")
    else:
        what = "who you are signed in as and a summary of the portal"
    return (f"Hello **{user.full_name}**! I answer from your own CampusHub records — {what}.\n\n"
            "What would you like to know?", [], _suggest(user))


def _identity(user: User, context: dict[str, Any], db: Session) -> Answer:
    lines = [f"- **Name:** {user.full_name}", f"- **Signed in as:** {user.email}",
             f"- **Role:** {context['role_badge']}"]
    s = context.get("student")
    f = context.get("faculty")
    if s:
        student = db.get(Student, s["id"])
        lines[2:2] = [f"- **Roll number:** `{s['roll_number']}`"]
        lines += [f"- **Programme:** {student.program.name if student.program else '—'}",
                  f"- **Department:** {s['department_name']}",
                  f"- **Semester:** {s['semester']}"
                  + (f" · Division {student.division}" if student.division else ""),
                  f"- **Admission year:** {student.admission_year}"]
    elif f:
        lines += [f"- **Designation:** {f['designation']}",
                  f"- **Department:** {f['department_name']}"]
    return ("### Your details\n\n" + "\n".join(lines),
            [ChatActionLink(title="My profile", path="/profile")], _suggest(user))


def _no_policy_record(topic: str) -> Answer:
    return (f"CampusHub does not hold the official **{topic}** rules, so I won't state them — "
            "a wrong figure here could mislead you.\n\n"
            "Please check PDEU's Academic Rules and Regulations, or ask your department office "
            "or mentor.",
            [ChatActionLink(title="Curriculum", path="/academics/curriculum")],
            ["Who is my mentor?", "What is my internship status?"])


def _fallback(user: User, query: str) -> Answer:
    return (f"I couldn't match “{query.strip()[:120]}” to anything I can look up.\n\n"
            "I answer from your own records — try one of the questions below, or ask it "
            "with a key word such as *mentor*, *meeting*, *internship*, *elective*, *minor* "
            "or *NPTEL*.",
            [ChatActionLink(title="Dashboard", path="/")], _suggest(user))


def _notifications(user: User, db: Session) -> Answer:
    unread = list(db.scalars(select(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc()).limit(5)))
    if not unread:
        return "You have no unread notifications.", [], _suggest(user)
    lines = "\n".join(f"- **{n.title}** — {n.message[:140]}" for n in unread)
    return (f"### Unread notifications\n\n{lines}", [], _suggest(user))


# ── students ──────────────────────────────────────────────────────────────
def _student_mentor(db: Session, student: Student) -> Faculty | None:
    assignment = db.scalar(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id, MentorAssignment.is_active.is_(True))
        .order_by(MentorAssignment.id.desc()))
    return assignment.faculty if assignment else None


def _mentor(db: Session, student: Student) -> Answer:
    mentor = _student_mentor(db, student)
    if mentor is None:
        return ("You have no mentor assigned yet. Your department assigns one; until then "
                "you cannot request a mentor meeting.",
                [ChatActionLink(title="Mentor–Mentee", path="/mentorship")],
                ["What is my internship status?"])
    lines = [f"- **Name:** {mentor.user.full_name}", f"- **Designation:** {mentor.designation}"]
    if mentor.cabin:
        lines.append(f"- **Cabin:** {mentor.cabin}")
    lines.append(f"- **Email:** {mentor.public_email or mentor.user.email}")
    if mentor.public_phone:
        lines.append(f"- **Phone:** {mentor.public_phone}")
    return ("### Your mentor\n\n" + "\n".join(lines),
            [ChatActionLink(title="Request a meeting", path="/mentorship?request=1")],
            ["Show my meeting requests", "How do I request a meeting?"])


def _student_meetings(db: Session, student: Student, q: str) -> Answer:
    mentor = _student_mentor(db, student)
    meetings = list(db.scalars(select(MentorMeeting).where(MentorMeeting.student_id == student.id)
                               .order_by(MentorMeeting.created_at.desc()).limit(5)))
    wants_new = _has(q, "request", "book", "schedule", "arrange", "set up", "want", "need", "how")
    parts = []
    if wants_new or not meetings:
        if mentor is None:
            parts.append("You have no mentor assigned yet, so a meeting cannot be requested.")
        else:
            parts.append(f"To request a meeting with **{mentor.user.full_name}**, press **Request a "
                         "meeting** below, give a subject and, if you like, an agenda, a preferred "
                         "slot, duration and mode. Your mentor is notified and confirms or "
                         "proposes another time.")
    if meetings:
        rows = []
        for m in meetings:
            when = (f"scheduled {_when(m.scheduled_at)}" if m.scheduled_at
                    else f"proposed {_when(m.proposed_slot)}" if m.proposed_slot
                    else f"requested {_when(m.requested_at)}")
            rows.append(f"- **{m.title}** — {_human(m.status)}, {when}"
                        + (f" · {m.location}" if m.location else ""))
        parts.append("### Your meeting requests\n\n" + "\n".join(rows))
    elif not wants_new:
        parts.append("You have not requested any meetings yet.")
    links = [ChatActionLink(title="Request a meeting", path="/mentorship?request=1")] if mentor else []
    links.append(ChatActionLink(title="Mentor–Mentee", path="/mentorship"))
    return "\n\n".join(parts), links, ["Who is my mentor?", "What is my internship status?"]


def _student_internships(db: Session, student: Student) -> Answer:
    enrollments = list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.student_id == student.id,
        InternshipEnrollment.status != EnrollmentStatus.WITHDRAWN)))
    if not enrollments:
        return ("You are not registered for any internship or project right now. When your "
                "coordinator opens registration, it appears on the Internships page.",
                [ChatActionLink(title="Internships", path="/internships")],
                ["Who is my mentor?", "Are elective registrations open?"])
    blocks = []
    for e in enrollments:
        stage = db.get(InternshipStage, e.current_stage_id) if e.current_stage_id else None
        reports = list(db.scalars(select(InternshipReport.status).where(
            InternshipReport.enrollment_id == e.id)))
        lines = [f"- **Status:** {_human(e.status)}",
                 f"- **Mentor:** {e.mentor.user.full_name if e.mentor else 'not assigned yet'}"]
        if e.organization:
            lines.append(f"- **Host:** {e.organization.name}")
        if stage:
            lines.append(f"- **Current stage:** {stage.name}")
        if reports:
            waiting = sum(1 for r in reports if r == SubmissionStatus.SUBMITTED)
            lines.append(f"- **Reports:** {len(reports)} submitted, {waiting} waiting for review")
        blocks.append(f"### {e.program.name if e.program else 'Internship'}\n\n" + "\n".join(lines))
    return ("\n\n".join(blocks),
            [ChatActionLink(title="My internship", path="/internships")],
            ["Who is my mentor?", "Show my meeting requests"])


def _student_electives(db: Session, student: Student) -> Answer:
    now = dt.datetime.now(dt.timezone.utc)
    rounds = [w for w in db.scalars(select(ElectiveRegistrationWindow).where(
                  ElectiveRegistrationWindow.status == RegistrationWindowStatus.OPEN))
              if w.accepts_students_from(student.program_id, student.current_semester, student.division)
              and (w.closes_at is None or _aware(w.closes_at) > now)]
    links = [ChatActionLink(title="Open Electives", path="/academics/open-electives"),
             ChatActionLink(title="Core Electives", path="/academics/core-electives")]
    if not rounds:
        return ("No elective registration round is open for you right now. Your coordinator "
                "opens one before choice filling starts, and you are notified when it does.",
                links, ["What is my internship status?", "Who is my mentor?"])
    lines = "\n".join(f"- **{w.title}** — open until {_when(w.closes_at)}" for w in rounds)
    return (f"### Open for you now\n\n{lines}\n\nFill in your choices before the deadline.",
            links, ["What is my internship status?"])


def _student_minor(db: Session, student: Student) -> Answer:
    link = [ChatActionLink(title="Minor Specialisation", path="/academics/minors")]
    seat = db.scalar(select(MinorEnrollment).where(MinorEnrollment.student_id == student.id))
    if seat:
        return (f"You hold a seat in **{seat.minor_program.name}** ({_human(seat.status)}), with "
                f"{float(seat.credits_completed):g} credits completed so far. This semester's "
                "courses, your results, fees and syllabus are on your minor page.", link, [])
    applications = list(db.scalars(select(MinorApplication).where(
        MinorApplication.student_id == student.id)))
    if applications:
        lines = "\n".join(f"- **{a.minor_program.name}** — {_human(a.status)}" for a in applications)
        return f"### Your minor applications\n\n{lines}", link, []
    open_now = [m for m in db.scalars(select(MinorProgram).where(MinorProgram.is_active.is_(True)))
                if m.department_id != student.department_id
                and student.current_semester in minors_service.application_semesters(m)]
    if not open_now:
        return ("You have not applied for a minor. Minor applications are made in the "
                "semester each minor names (Semester III by default), so there is nothing "
                "to apply for now.", link, [])
    lines = "\n".join(f"- **{m.name}** — CPI ≥ {float(m.min_cpi):g}, at most {m.max_backlogs} "
                      f"backlog(s), {m.capacity} seats" for m in open_now if m.min_cpi is not None)
    return (f"### Minors you can apply for this semester\n\n{lines}\n\n"
            "Eligibility is checked against your record when you apply.", link, [])


def _student_nptel(db: Session, student: Student) -> Answer:
    regs = list(db.scalars(select(MoocRegistration).where(MoocRegistration.student_id == student.id)))
    link = [ChatActionLink(title="NPTEL", path="/academics/nptel")]
    if not regs:
        return ("You have no NPTEL registrations. Register for a course on the NPTEL page; once "
                "you pass, upload the certificate there and the NPTEL coordinator verifies it.",
                link, [])
    lines = "\n".join(f"- **{r.subject_title or 'Course'}** — "
                      f"{_human(r.status)}" for r in regs)
    return f"### Your NPTEL courses\n\n{lines}", link, []


def _student_standing(student: Student) -> Answer:
    cpi = f"{float(student.cpi):.2f}" if student.cpi is not None else "not recorded"
    return (f"### Your academic record\n\n- **CPI:** {cpi}\n- **Backlogs:** {student.backlog_count}\n"
            f"- **Semester:** {student.current_semester}",
            [ChatActionLink(title="My profile", path="/profile")], ["Am I eligible for a minor?"])


def _answer_student(q: str, user: User, context: dict, db: Session) -> Answer | None:
    student = db.get(Student, context["student"]["id"])
    if _has(q, "meeting", "meetings", "appointment", "meet my mentor"):
        return _student_meetings(db, student, q)
    if _has(q, "internship", "cssi", "report", "reports", "project", "seminar", "stage", "ngo"):
        return _student_internships(db, student)
    if _has(q, "mentor", "guide", "advisor"):
        return _mentor(db, student)
    if _has(q, "elective", "electives", "choice filling", "registration round"):
        return _student_electives(db, student)
    if _has(q, "minor", "specialisation", "specialization"):
        return _student_minor(db, student)
    if _has(q, "nptel", "mooc", "swayam"):
        return _student_nptel(db, student)
    if _has(q, "cpi", "cgpa", "backlog", "backlogs", "standing"):
        return _student_standing(student)
    return None


# ── faculty ───────────────────────────────────────────────────────────────
def _faculty_meetings(db: Session, faculty: Faculty) -> Answer:
    waiting = list(db.scalars(select(MentorMeeting).where(
        MentorMeeting.faculty_id == faculty.id, MentorMeeting.status == MeetingStatus.REQUESTED)
        .order_by(MentorMeeting.requested_at)))
    upcoming = list(db.scalars(select(MentorMeeting).where(
        MentorMeeting.faculty_id == faculty.id, MentorMeeting.status == MeetingStatus.APPROVED,
        MentorMeeting.scheduled_at >= dt.datetime.now(dt.timezone.utc))
        .order_by(MentorMeeting.scheduled_at).limit(5)))
    parts = []
    if waiting:
        parts.append(f"### Waiting for your reply ({len(waiting)})\n\n" + "\n".join(
            f"- **{m.student.user.full_name}** (`{m.student.roll_number}`) — {m.title}, "
            f"requested {_when(m.requested_at)}" for m in waiting[:8]))
    else:
        parts.append("No meeting requests are waiting for your reply.")
    if upcoming:
        parts.append("### Coming up\n\n" + "\n".join(
            f"- **{m.student.user.full_name}** — {m.title}, {_when(m.scheduled_at)}" for m in upcoming))
    return ("\n\n".join(parts), [ChatActionLink(title="Meetings", path="/mentorship")],
            ["Show my mentees", "What needs my review?"])


def _faculty_mentees(db: Session, faculty: Faculty) -> Answer:
    mentees = [a.student for a in db.scalars(select(MentorAssignment).where(
        MentorAssignment.faculty_id == faculty.id, MentorAssignment.is_active.is_(True)))]
    interns = list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.mentor_faculty_id == faculty.id,
        InternshipEnrollment.status != EnrollmentStatus.WITHDRAWN)))
    lines = [f"- **Mentees:** {len(mentees)}", f"- **Internship / project students:** {len(interns)}"]
    names = sorted(mentees, key=lambda s: s.roll_number)[:8]
    body = "### Your students\n\n" + "\n".join(lines)
    if names:
        body += "\n\n" + "\n".join(f"- {s.user.full_name} (`{s.roll_number}`)" for s in names)
        if len(mentees) > len(names):
            body += f"\n- …and {len(mentees) - len(names)} more"
    return (body, [ChatActionLink(title="My mentees", path="/mentorship/mentees"),
                   ChatActionLink(title="Internship students", path="/internships/my-students")],
            ["What needs my review?", "Show pending meeting requests"])


def _faculty_reviews(db: Session, faculty: Faculty) -> Answer:
    mine = select(InternshipEnrollment.id).where(InternshipEnrollment.mentor_faculty_id == faculty.id)
    stages = db.scalar(select(func.count(EnrollmentStageProgress.id)).where(
        EnrollmentStageProgress.enrollment_id.in_(mine),
        EnrollmentStageProgress.status == StageStatus.SUBMITTED)) or 0
    reports = db.scalar(select(func.count(InternshipReport.id)).where(
        InternshipReport.enrollment_id.in_(mine),
        InternshipReport.status == SubmissionStatus.SUBMITTED)) or 0
    documents = db.scalar(select(func.count(InternshipDocument.id)).where(
        InternshipDocument.enrollment_id.in_(mine),
        InternshipDocument.status == SubmissionStatus.SUBMITTED)) or 0
    total = stages + reports + documents
    text = ("Nothing is waiting for your review." if not total else
            f"### Waiting for your review ({total})\n\n- **Milestones:** {stages}\n"
            f"- **Reports:** {reports}\n- **Documents:** {documents}")
    return (text, [ChatActionLink(title="Review queue", path="/internships/review")],
            ["What is my performance score?", "Show pending meeting requests"])


def _faculty_score(db: Session, faculty: Faculty) -> Answer:
    if not scoring.is_scorable(faculty):
        return ("You are not scored yet — scoring of real faculty starts once the portal runs "
                "on real activity.", [], [])
    s = scoring.faculty_score(db, faculty)
    if s.score is None:
        return ("Nothing has been scored for you yet. Points appear as you review work, enter "
                "marks and answer meeting requests.", [ChatActionLink(title="Dashboard", path="/")], [])
    return (f"### Your performance score\n\n- **Score:** {s.score} / 100 ({s.band})\n"
            f"- **On time:** {s.on_time} of {s.scored}\n- **Late or overdue:** {s.late + s.overdue}\n"
            f"- **Waiting, still in time:** {s.pending}",
            [ChatActionLink(title="Itemised record", path="/")], ["What needs my review?"])


def _faculty_roles(db: Session, user: User, faculty: Faculty, context: dict) -> Answer:
    roles = list(db.scalars(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.faculty_id == faculty.id, FacultyRoleAssignment.is_active.is_(True))))
    lines = [f"- {_human(r.role)} — {_human(r.domain)}" for r in roles]
    if context.get("is_hod"):
        lines.insert(0, f"- Head of Department — {context['faculty']['department_name']}")
    if faculty.is_mentor:
        lines.append("- Mentor")
    text = "### Your roles\n\n" + ("\n".join(lines) if lines else "You hold no appointed roles.")
    links = [ChatActionLink(title="Roles", path="/admin/roles")] if context.get("is_hod") else []
    return text, links, ["Show my mentees"]


def _hod_coordinators(db: Session, faculty: Faculty) -> Answer:
    roles = list(db.scalars(select(FacultyRoleAssignment).where(
        FacultyRoleAssignment.department_id == faculty.department_id,
        FacultyRoleAssignment.is_active.is_(True))))
    lines = "\n".join(f"- **{r.faculty.user.full_name}** — {_human(r.role)}, {_human(r.domain)}"
                      for r in roles if r.faculty)
    return ("### Appointed in your department\n\n" + (lines or "No one is appointed yet."),
            [ChatActionLink(title="Roles", path="/admin/roles")], [])


def _answer_faculty(q: str, user: User, context: dict, db: Session) -> Answer | None:
    faculty = db.get(Faculty, context["faculty"]["id"])
    if _has(q, "meeting", "meetings", "appointment", "appointments"):
        return _faculty_meetings(db, faculty)
    if _has(q, "review", "reviews", "pending", "submission", "submissions", "approve"):
        return _faculty_reviews(db, faculty)
    if _has(q, "score", "performance", "rating"):
        return _faculty_score(db, faculty)
    if context.get("is_hod") and _has(q, "coordinator", "coordinators", "appointed"):
        return _hod_coordinators(db, faculty)
    if _has(q, "role", "roles", "coordinator", "responsibilities"):
        return _faculty_roles(db, user, faculty, context)
    if _has(q, "mentee", "mentees", "student", "students"):
        return _faculty_mentees(db, faculty)
    return None


# ── registrar ─────────────────────────────────────────────────────────────
def _admin_summary(db: Session) -> Answer:
    students = db.scalar(select(func.count(Student.id))) or 0
    faculty = db.scalar(select(func.count(Faculty.id)).where(Faculty.is_active.is_(True))) or 0
    rounds = db.scalar(select(func.count(ElectiveRegistrationWindow.id)).where(
        ElectiveRegistrationWindow.status == RegistrationWindowStatus.OPEN)) or 0
    return (f"### Portal summary\n\n- **Students:** {students}\n- **Active faculty:** {faculty}\n"
            f"- **Open elective rounds:** {rounds}",
            [ChatActionLink(title="Administration", path="/admin")], [])


def answer_query_contextually(user: User, query: str, context: dict[str, Any],
                              db: Session) -> Answer:
    q = re.sub(r"\s+", " ", query.lower()).strip(" ?!.")
    if q in {"hi", "hello", "hey", "hii", "namaste", "good morning", "good afternoon",
             "good evening", "help", "what can you do"}:
        return _greeting(user, context)
    if _has(q, "my name", "who am i", "about me", "my details", "my profile", "my roll",
            "roll number", "roll no", "my email", "my department", "my semester",
            "which semester", "my division", "my programme", "my program", "signed in as"):
        return _identity(user, context, db)
    if _has(q, "notification", "notifications", "unread"):
        return _notifications(user, db)
    if _has(q, "attendance"):
        return _no_policy_record("attendance")
    if _has(q, "grading", "grade scale", "grading scale", "grade points", "letter grade"):
        return _no_policy_record("grading")

    answer = None
    if context.get("student"):
        answer = _answer_student(q, user, context, db)
    elif context.get("faculty"):
        answer = _answer_faculty(q, user, context, db)
    elif context.get("is_admin") and _has(q, "summary", "statistics", "stats", "overview"):
        answer = _admin_summary(db)
    return answer or _fallback(user, query)


# ─────────────────────────────────────────────────────────────────────────────
# Primary Handler
# ─────────────────────────────────────────────────────────────────────────────

def process_chat_query(user: User, query: str, history: list[ChatMessageItem], db: Session) -> ChatQueryResponse:
    """Process incoming query with role awareness and confidentiality guard."""
    context = get_user_role_context(user, db)
    role_context_str = context["role_badge"]

    # 1. Confidentiality / Anti-Leakage Guard
    is_blocked, block_reason = _check_confidentiality_leakage(
        query=query,
        user=user,
        is_admin=context["is_admin"],
    )

    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%H:%M")

    if is_blocked:
        return ChatQueryResponse(
            reply=f"🔒 **Access Restricted — Privacy & Role Boundary Guard**\n\n{block_reason}",
            role_context=role_context_str,
            suggestions=["What is my academic standing?", "What is the attendance policy?"],
            action_links=[],
            is_confidential_block=True,
            timestamp=now_iso,
        )

    # 2. Answer Query
    reply_text, action_links, suggestions = answer_query_contextually(
        user=user,
        query=query,
        context=context,
        db=db,
    )

    return ChatQueryResponse(
        reply=reply_text,
        role_context=role_context_str,
        suggestions=suggestions,
        action_links=action_links,
        is_confidential_block=False,
        timestamp=now_iso,
    )
