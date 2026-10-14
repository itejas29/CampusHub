"""Role-aware, confidentiality-guarded conversational assistant service."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.academics import Course, CourseOffering, ElectiveRegistrationWindow
from app.models.engagement import Announcement, MentorMeeting
from app.models.enums import (
    AllocationStatus, AssignedRole, CoordinationDomain, EnrollmentStatus,
    MeetingStatus, RegistrationStatus, Role, SubmissionStatus,
)
from app.models.identity import Department, Faculty, FacultyRoleAssignment, Student, User
from app.models.internships import InternshipEnrollment, InternshipReport
from app.models.minors import MinorProgram
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
# Context-Aware Knowledge & Live Data Answering Engine
# ─────────────────────────────────────────────────────────────────────────────

def answer_query_contextually(
    user: User,
    query: str,
    context: dict[str, Any],
    db: Session,
) -> tuple[str, list[ChatActionLink], list[str]]:
    """Generate high-fidelity, role-appropriate responses with live DB context and navigation actions."""
    q_lower = query.lower()
    links: list[ChatActionLink] = []
    suggestions: list[str] = []

    # 1. Greetings & Capabilities
    if any(q_lower.strip() in (g, g + "!", g + ".") for g in ["hi", "hello", "hey", "hola", "greetings", "good morning", "good afternoon"]):
        name = user.full_name
        if user.has_role(Role.STUDENT):
            return (
                f"Hello **{name}**! 👋 I am your CampusHub Academic Assistant.\n\n"
                f"I can help you check your **internship weekly report status**, **assigned mentor**, "
                f"**CPI & credit requirements**, **elective registration rounds**, or institutional policies.\n\n"
                f"How may I assist you today?",
                [
                    ChatActionLink(title="My Internships", path="/internships/my-internship"),
                    ChatActionLink(title="Electives", path="/electives"),
                    ChatActionLink(title="Academic Progress", path="/progress"),
                ],
                [
                    "What is my internship status?",
                    "Who is my assigned mentor?",
                    "What is the minimum attendance policy?",
                    "Are elective registrations open?",
                ],
            )
        elif user.has_role(Role.FACULTY, Role.HOD):
            faculty_info = context.get("faculty") or {}
            dept_name = faculty_info.get("department_name", "your department")
            badge = context.get("role_badge", "Faculty")
            return (
                f"Hello **{name}** ({badge})! 👋\n\n"
                f"I can assist you with mentee weekly report reviews, internship coordination, "
                f"meeting schedules, and departmental guidance for {dept_name}.\n\n"
                f"What would you like to check?",
                [
                    ChatActionLink(title="My Mentees", path="/internships/my-students"),
                    ChatActionLink(title="Mentorship Meetings", path="/mentorship"),
                ],
                [
                    "How many weekly reports need my review?",
                    "Show my assigned mentees",
                    "List departmental registration rounds",
                ],
            )
        else:
            return (
                f"Hello **{name}** (Administrator)! 👋\n\n"
                f"I can provide live statistics on student enrollments, registration rounds, "
                f"department coordinators, and platform status.",
                [
                    ChatActionLink(title="Admin Dashboard", path="/dashboard"),
                    ChatActionLink(title="Registration Rounds", path="/admin/rounds"),
                ],
                [
                    "Show department summary",
                    "What registration rounds are active?",
                    "List all coordinators",
                ],
            )

    # 2. Student-Specific Live Context Queries
    if user.has_role(Role.STUDENT) and context.get("student"):
        s_data = context["student"]
        student_id = s_data["id"]

        # A. CPI / Grades / Academic Standing
        if any(k in q_lower for k in ["my cpi", "my cgpa", "my grade", "my marks", "my performance"]):
            cpi_val = s_data["cpi"] if s_data["cpi"] is not None else "N/A"
            backlogs = s_data["backlog_count"]
            status_text = "Good Standing" if backlogs == 0 else f"{backlogs} Active Backlog(s)"
            return (
                f"### 🎓 Your Academic Standing\n\n"
                f"- **Roll Number:** `{s_data['roll_number']}`\n"
                f"- **Department:** {s_data['department_name']} (Semester {s_data['semester']})\n"
                f"- **Current CPI:** **{cpi_val}**\n"
                f"- **Backlog Status:** {status_text}\n\n"
                f"> **Note:** A minimum CPI of **7.00** and zero active backlogs are required to be eligible for Minor Specialisation programmes.",
                [ChatActionLink(title="View Full Profile", path="/profile")],
                ["Am I eligible for minor?", "What is my internship status?", "Attendance policy"],
            )

        # B. Internship Status & Assigned Mentor
        if any(k in q_lower for k in ["internship", "weekly report", "daily log", "mentor"]):
            enrollment = db.scalar(
                select(InternshipEnrollment).where(
                    InternshipEnrollment.student_id == student_id,
                    InternshipEnrollment.status != EnrollmentStatus.WITHDRAWN,
                )
            )
            if not enrollment:
                return (
                    f"You do not have an active internship enrollment at this moment.\n\n"
                    f"If you are registering for Summer Internship or CSSI, please visit the Internships portal to view available openings and program guidelines.",
                    [ChatActionLink(title="Internships Portal", path="/internships")],
                    ["Who is my mentor?", "Are elective registrations open?"],
                )

            mentor_name = "Not Assigned"
            mentor_dept = ""
            if enrollment.mentor and enrollment.mentor.user:
                mentor_name = enrollment.mentor.user.full_name
                if enrollment.mentor.department:
                    mentor_dept = f" ({enrollment.mentor.department.code})"

            reports = db.scalars(
                select(InternshipReport).where(InternshipReport.enrollment_id == enrollment.id)
            ).all()
            approved_count = sum(1 for r in reports if r.status == SubmissionStatus.APPROVED)
            submitted_count = sum(1 for r in reports if r.status == SubmissionStatus.SUBMITTED)

            report_summary = (
                f"- **Total Weekly Reports Submitted:** {len(reports)}\n"
                f"- **Approved Reports:** {approved_count}\n"
                f"- **Pending Mentor Review:** {submitted_count}"
            )

            return (
                f"### 💼 Active Internship Record\n\n"
                f"- **Program:** {enrollment.program.name if enrollment.program else 'Internship'}\n"
                f"- **Company / Host Org:** {enrollment.organization.name if enrollment.organization else 'PDEU Internal'}\n"
                f"- **Assigned Faculty Mentor:** **{mentor_name}**{mentor_dept}\n"
                f"- **Enrollment Status:** `{enrollment.status.value}`\n\n"
                f"#### 📝 Weekly Reports Overview\n"
                f"{report_summary}\n\n"
                f"Remember to submit your weekly logs by Sunday 23:59 each week for your mentor to evaluate.",
                [
                    ChatActionLink(title="Open My Internship", path="/internships/my-internship"),
                    ChatActionLink(title="Submit Report", path="/internships/my-internship?tab=reports"),
                ],
                ["What electives can I choose?", "Attendance policy", "My CPI"],
            )

        # C. Elective Registration & Rounds
        if any(k in q_lower for k in ["elective", "registration round", "open elective", "core elective"]):
            windows = db.scalars(
                select(ElectiveRegistrationWindow).where(
                    ElectiveRegistrationWindow.target_semester == s_data["semester"],
                    ElectiveRegistrationWindow.status == RegistrationStatus.OPEN,
                )
            ).all()

            if windows:
                round_lines = "\n".join(
                    f"- **{w.name}** (Type: `{w.elective_type.value}`): Open until {w.closes_at.strftime('%Y-%m-%d %H:%M') if w.closes_at else 'TBD'}"
                    for w in windows
                )
                return (
                    f"### 📚 Active Elective Registration Rounds\n\n"
                    f"The following registration round(s) are currently **OPEN** for your semester ({s_data['semester']}):\n\n"
                    f"{round_lines}\n\n"
                    f"Make sure to submit and rank your preferences before the closing deadline. Allocations use Gale-Shapley matching based on your preference order and CPI ranking.",
                    [ChatActionLink(title="Go to Electives", path="/electives")],
                    ["Am I eligible for minor?", "What is my internship status?"],
                )
            else:
                return (
                    f"### 📚 Elective Registration Status\n\n"
                    f"There are currently **no open elective registration windows** for Semester {s_data['semester']}.\n\n"
                    f"You can view past allocations, syllabus details, or check back when the coordinator opens the next registration round.",
                    [ChatActionLink(title="View Electives", path="/electives")],
                    ["What is my internship status?", "Am I eligible for minor?"],
                )

        # D. Minor Specialisation
        if any(k in q_lower for k in ["minor", "specialisation", "specialization"]):
            minors = db.scalars(
                select(MinorProgram).where(
                    MinorProgram.department_id != s_data["department_id"],
                    MinorProgram.is_active.is_(True),
                )
            ).all()

            minor_names = [f"- **{m.name}** (Offered by {m.department.name if m.department else 'Other Dept'})" for m in minors]
            cpi = s_data["cpi"] or 0.0
            eligible = (cpi >= 7.0 and s_data["backlog_count"] == 0)
            elig_status = "✅ **Eligible**" if eligible else "❌ **Ineligible** (Requires CPI ≥ 7.00 and 0 active backlogs)"

            return (
                f"### 🎯 Minor Specialisation Guidelines\n\n"
                f"- **Your Eligibility:** {elig_status} (Your CPI: {s_data['cpi']}, Backlogs: {s_data['backlog_count']})\n"
                f"- **Key Rule:** Under PDEU rules, you cannot take a minor offered by your own department ({s_data['department_name']}). You must choose an inter-departmental minor.\n\n"
                f"#### Available Minors:\n"
                f"{(chr(10).join(minor_names)) if minor_names else 'No active external minors registered.'}\n\n"
                f"Completing a minor requires 18–20 additional credits across Semesters 4 to 8.",
                [ChatActionLink(title="Explore Minors", path="/minors")],
                ["What is my CPI?", "Are elective registrations open?"],
            )

    # 3. Faculty / Mentor / Coordinator Live Context Queries
    if user.has_role(Role.FACULTY, Role.HOD) and context.get("faculty"):
        f_data = context["faculty"]
        faculty_id = f_data["id"]

        # A. Assigned Mentees & Pending Reviews
        if any(k in q_lower for k in ["mentee", "my student", "weekly report", "review", "submission"]):
            mentees = db.scalars(
                select(InternshipEnrollment).where(
                    InternshipEnrollment.mentor_faculty_id == faculty_id,
                    InternshipEnrollment.status != EnrollmentStatus.WITHDRAWN,
                )
            ).all()

            pending_reports = db.scalars(
                select(InternshipReport)
                .join(InternshipEnrollment)
                .where(
                    InternshipEnrollment.mentor_faculty_id == faculty_id,
                    InternshipReport.status == SubmissionStatus.SUBMITTED,
                )
            ).all()

            mentee_lines = [
                f"- **{m.student.user.full_name}** (`{m.student.roll_number}`) · {m.organization.name if m.organization else 'PDEU Internal'}"
                for m in mentees[:5] if m.student and m.student.user
            ]
            if len(mentees) > 5:
                mentee_lines.append(f"- *...and {len(mentees) - 5} more mentees*")

            return (
                f"### 👥 Mentorship & Review Summary\n\n"
                f"- **Total Assigned Mentees:** {len(mentees)}\n"
                f"- **Weekly Reports Pending Review:** **{len(pending_reports)}**\n\n"
                f"#### Active Mentees:\n"
                f"{(chr(10).join(mentee_lines)) if mentee_lines else 'No mentees currently assigned to you.'}\n\n"
                f"You can review submitted reports, score daily logs, and provide feedback directly in the Mentee portal.",
                [
                    ChatActionLink(title="Review Mentees", path="/internships/my-students"),
                    ChatActionLink(title="Mentorship Meetings", path="/mentorship"),
                ],
                ["Show department registration rounds", "List departmental coordinators"],
            )

        # B. HOD-Specific Queries
        if f_data.get("is_hod") and any(k in q_lower for k in ["coordinator", "hod", "department", "summary"]):
            dept_id = f_data["department_id"]
            coordinators = db.scalars(
                select(FacultyRoleAssignment).where(
                    FacultyRoleAssignment.department_id == dept_id,
                    FacultyRoleAssignment.is_active.is_(True),
                )
            ).all()

            coord_lines = [
                f"- **{c.faculty.user.full_name if c.faculty and c.faculty.user else 'Faculty'}**: `{c.domain.value}` ({c.role.value})"
                for c in coordinators
            ]

            return (
                f"### 🏛️ Department Coordination Roster ({f_data['department_code']})\n\n"
                f"- **Department:** {f_data['department_name']}\n"
                f"- **Active Department Coordinators:** {len(coordinators)}\n\n"
                f"#### Appointed Coordinators:\n"
                f"{(chr(10).join(coord_lines)) if coord_lines else 'No active coordinator assignments in this department.'}\n\n"
                f"As HOD, you can assign faculty as coordinators for Summer Internship, CSSI, Electives, and Minors from the Administration panel.",
                [ChatActionLink(title="Manage Coordinators", path="/admin/coordinators")],
                ["How many reports need review?", "Show active registration rounds"],
            )

    # 4. Institutional Policies & Academic FAQs (Available to all roles)
    if any(k in q_lower for k in ["attendance", "minimum attendance", "attendance policy", "85%"]):
        return (
            f"### 📋 PDEU Academic Attendance Regulations\n\n"
            f"- **Standard Minimum:** **85%** cumulative attendance is mandatory in each enrolled course to be eligible for end-semester examinations.\n"
            f"- **Medical / Condonation Range (75%–84%):** Allowed only with valid documentation (Medical Certificate / official Dean approval) submitted within 3 working days.\n"
            f"- **Below 75% Attendance:** Results in strict **Detention (FA Grade)** in the course. The student must repeat the course in a subsequent semester.\n\n"
            f"> Faculty record attendance on CampusHub, and low attendance notices are dispatched at 80% and 75% thresholds.",
            [ChatActionLink(title="View Academic Regulations", path="/curriculum")],
            ["What is the grading system?", "What is the minor policy?"],
        )

    if any(k in q_lower for k in ["grading", "grade scale", "marks scale", "cpi calculation", "letter grade"]):
        return (
            f"### 📊 PDEU 10-Point Grading System\n\n"
            f"| Letter Grade | Grade Point | Qualitative Meaning |\n"
            f"| :---: | :---: | :--- |\n"
            f"| **S** | **10.0** | Outstanding |\n"
            f"| **A+** | **9.0** | Excellent |\n"
            f"| **A** | **8.0** | Very Good |\n"
            f"| **B+** | **7.0** | Good |\n"
            f"| **B** | **6.0** | Above Average |\n"
            f"| **C** | **5.0** | Average |\n"
            f"| **P** | **4.0** | Pass |\n"
            f"| **F** | **0.0** | Fail (Repeat Course) |\n\n"
            f"- **Semester Performance Index (SPI):** Weighted sum of credits × grade points divided by total credits registered in that semester.\n"
            f"- **Cumulative Performance Index (CPI):** Cumulative weighted average across all completed semesters.",
            [ChatActionLink(title="Curriculum Explorer", path="/curriculum")],
            ["Attendance policy", "Minor policy"],
        )

    if any(k in q_lower for k in ["nptel", "mooc", "swayam", "online course"]):
        return (
            f"### 🌐 NPTEL / MOOC Course Guidelines\n\n"
            f"- **Credit Equivalency:** 8-week NPTEL courses map to **2 or 3 credits**; 12-week courses map to **3 or 4 credits** as designated in your curriculum.\n"
            f"- **Verification Process:**\n"
            f"  1. Register for university-approved NPTEL courses at the start of semester.\n"
            f"  2. Complete exam and obtain e-certificate from NPTEL / SWAYAM.\n"
            f"  3. Upload the original certificate (PDF) on CampusHub under **Academics → NPTEL**.\n"
            f"  4. The NPTEL Coordinator verifies the certificate against official scores before credits are transferred to your transcript.",
            [ChatActionLink(title="NPTEL Portal", path="/nptel")],
            ["What electives are open?", "My CPI"],
        )

    # Fallback response with role-aware help
    return (
        f"I can assist you with university academic procedures, enrollment queries, and guidelines on CampusHub.\n\n"
        f"You can ask me questions like:\n"
        f"- *\"What is my internship status?\"*\n"
        f"- *\"Who is my assigned mentor?\"*\n"
        f"- *\"What is the minimum attendance requirement?\"*\n"
        f"- *\"What is the PDEU grading scale?\"*\n"
        f"- *\"Are elective registration rounds open?\"*\n\n"
        f"Feel free to click any suggestion below or type your query!",
        [ChatActionLink(title="Dashboard", path="/dashboard")],
        [
            "What is my internship status?",
            "What is the minimum attendance policy?",
            "What is the grading system?",
            "Are elective registrations open?",
        ],
    )


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
