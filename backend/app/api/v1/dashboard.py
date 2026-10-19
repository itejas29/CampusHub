"""Role-aware dashboards. Every number is a real query against seeded data —
no synthetic analytics."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, get_optional_faculty, require_permission
from app.core.errors import PermissionDeniedError
from app.core.rbac import P, has_permission
from app.models.academics import (
    Course, CourseOffering, CurriculumComponent, ElectiveAllocation, ElectivePreference,
    ElectiveRegistrationWindow, MoocRegistration,
)
from app.models.community import Club, Event, EventRegistration
from app.models.engagement import Announcement, MentorAssignment, MentorMeeting
from app.models.enums import (
    AllocationStatus, ComponentType, EnrollmentStatus, EventStatus, MeetingStatus,
    MinorApplicationStatus, PreferenceStatus, RegistrationStatus, Role, StageStatus,
    SubmissionStatus, VerificationStatus,
)
from app.models.identity import Department, Faculty, FacultyRoleAssignment, Student, User
from app.models.internships import (
    EnrollmentStageProgress, InternshipEnrollment, InternshipGroup, InternshipProgram,
    InternshipReport,
)
from app.models.minors import MinorApplication, MinorEnrollment
from app.models.system import AuditLog
from app.schemas.admin import (
    ActivityItem, AdminDashboard, BreakdownItem, DeadlineItem, FacultyDashboard,
    HodDashboard, ProgressItem, StatCard, StudentDashboard,
)
from app.services import announcements as announcement_audience
from app.services import mooc_rounds, registration, scope
from app.services import internship_windows as program_windows
from app.services import documents as docs
from app.services import serializers
from app.services import internships as engine
from app.services.eligibility import components_for_semester
from app.services.requirements import current_mooc_registration, requirement_state

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _count(db, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _event_dicts(db, limit: int = 5, student: Student | None = None) -> list[dict]:
    now = utcnow()
    events = list(db.scalars(
        select(Event).where(Event.status == EventStatus.PUBLISHED,
                            Event.start_at >= now)
        .order_by(Event.start_at).limit(limit)
    ))
    registered: set[int] = set()
    if student and events:
        registered = set(db.scalars(
            select(EventRegistration.event_id).where(
                EventRegistration.student_id == student.id,
                EventRegistration.event_id.in_([e.id for e in events]),
                EventRegistration.status != RegistrationStatus.CANCELLED,
            )
        ))
    return [
        {
            "id": e.id, "title": e.title, "start_at": e.start_at.isoformat(),
            "venue": e.venue, "club": e.club.name if e.club else None,
            "event_type": e.event_type.value,
            "is_registered": e.id in registered,
        }
        for e in events
    ]


def _announcement_dicts(db, user: User, limit: int = 4) -> list[dict]:
    # The same audience rule as the Announcements page. This panel once had no
    # audience filter, and showed every account every notice.
    rows = db.scalars(
        announcement_audience.visible_to(db, user)
        .order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": a.id, "title": a.title, "category": a.category.value,
            "priority": a.priority.value,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "excerpt": (a.body[:160] + "…") if len(a.body) > 160 else a.body,
        }
        for a in rows
    ]


# ── student ───────────────────────────────────────────────────────────────
@router.get("/student", response_model=StudentDashboard)
def student_dashboard(db: DbSession, user: CurrentUser) -> StudentDashboard:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise PermissionDeniedError("This dashboard is only available to students.")
    now = utcnow()

    components = components_for_semester(db, student, student.current_semester)
    allocations = list(db.scalars(select(ElectiveAllocation).where(
        ElectiveAllocation.student_id == student.id,
        ElectiveAllocation.status.in_([AllocationStatus.ALLOCATED,
                                       AllocationStatus.CONFIRMED]),
        registration.visible_allocations(),
    )))
    enrollments = list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.student_id == student.id
    )))
    registered_events = _count(db, select(EventRegistration).where(
        EventRegistration.student_id == student.id,
        EventRegistration.status != RegistrationStatus.CANCELLED,
    ))
    allocated_ids = {a.curriculum_component_id for a in allocations}
    # A MOOC slot is settled by a registration, never by an allocation.
    mooc_rows: dict[int, list[MoocRegistration]] = {}
    for mooc_row in db.scalars(select(MoocRegistration).where(
        MoocRegistration.student_id == student.id
    )):
        mooc_rows.setdefault(mooc_row.curriculum_component_id, []).append(mooc_row)
    ranked_ids = set(db.scalars(select(ElectivePreference.curriculum_component_id).where(
        ElectivePreference.student_id == student.id,
        ElectivePreference.status == PreferenceStatus.SUBMITTED,
    )))
    states = {
        c.id: requirement_state(
            c, allocated=c.id in allocated_ids,
            preferences_submitted=c.id in ranked_ids,
            mooc_registration=current_mooc_registration(mooc_rows.get(c.id, ())),
        )
        for c in components
    }
    pending_components = [c for c in components if states[c.id].needs_action]

    stats = [
        StatCard(key="semester", label="Current semester",
                 value=student.current_semester,
                 hint=student.program.name if student.program else None),
        StatCard(key="cpi", label="CPI",
                 value=float(student.cpi) if student.cpi is not None else 0,
                 hint=f"{student.backlog_count} backlog(s)"),
        # Linked to the slot that is actually waiting. A semester with no
        # elective slot at all (I-III for most programmes) has nowhere to send
        # the student, so it carries no link rather than a guess.
        StatCard(key="pending_electives", label="Elective actions pending",
                 value=len(pending_components),
                 link=(serializers.elective_path(pending_components[0])
                       if pending_components else None)),
        StatCard(key="events", label="Events registered", value=registered_events,
                 link="/events"),
    ]

    # Action items: open elective windows and internship stages awaiting the student.
    action_items: list[DeadlineItem] = []
    mooc_live = mooc_rounds.round_for_student(db, student)
    for component in pending_components:
        closes = db.scalar(
            select(func.min(CourseOffering.registration_closes_at)).where(
                CourseOffering.curriculum_component_id == component.id,
                CourseOffering.registration_closes_at.is_not(None),
            )
        )
        if component.component_type == ComponentType.MOOC:
            # No preference list here — the student takes one course, or NCC.
            if mooc_rows.get(component.id):
                # In a round the choice stands and only the certificate is redone;
                # without one, the student registers again.
                step = (" — the certificate was not accepted, submit it again"
                        if mooc_live is not None
                        else " — registration was not accepted, register again")
            elif mooc_live is not None:
                step = " — choose an NPTEL course or NCC"
                closes = mooc_live[0].closes_at
            else:
                step = " — register a course"
        else:
            step = " — submit preferences"
        action_items.append(DeadlineItem(
            title=f"{component.title}{step}",
            due_at=closes, context=component.scope_label or component.code,
            link=serializers.elective_path(component), kind="elective",
        ))

    # Rounds a coordinator has opened ahead of the semester the slot sits in.
    # These are not this semester's requirements, so they are not in the list
    # above — but the student is being asked to choose, so they belong here and
    # in the pending count.
    early_pending = []
    for component, window in registration.early_rounds(db, student):
        status = registration.status_for(db, component, student, now)
        if status.can_submit and not registration.has_submitted(db, student, component):
            early_pending.append(component)
            action_items.append(DeadlineItem(
                title=f"{component.title} — choice filling open for "
                      f"Semester {component.semester_number}",
                due_at=status.closes_at, context=window.title,
                link=serializers.elective_path(component), kind="elective",
            ))
    # A MOOC slot carried over from an earlier semester is not in this
    # semester's list, but it is still the student's to clear.
    if mooc_live is not None and mooc_live[1].carry_over:
        round_, _ = mooc_live
        component = db.get(CurriculumComponent, round_.curriculum_component_id)
        chosen = db.scalar(select(MoocRegistration).where(
            MoocRegistration.mooc_round_id == round_.id,
            MoocRegistration.student_id == student.id))
        title = component.title if component else "NPTEL / NCC"
        action_items.append(DeadlineItem(
            title=(f"{title} — carried over: choose an NPTEL course or NCC" if not chosen
                   else f"{title} — carried over: submit your certificate"),
            due_at=round_.closes_at if not chosen else None,
            context=round_.title, link="/academics/nptel", kind="elective",
        ))
    if early_pending:
        pending_stat = next(s for s in stats if s.key == "pending_electives")
        pending_stat.value = len(pending_components) + len(early_pending)
        pending_stat.link = (pending_stat.link
                             or serializers.elective_path(early_pending[0]))

    progress: list[ProgressItem] = []
    for enrollment in enrollments:
        # Both the bar and the to-do list come from documents_, not from a
        # stored percentage: the count of stages actually evidenced and the
        # specific submissions holding the rest up.
        state = docs.progress(db, enrollment)
        progress.append(ProgressItem(
            label=enrollment.program.name,
            completed=state["completed"], total=state["total"],
            link=f"/internships/{enrollment.program_id}",
        ))
        for group in docs.expected_documents(db, enrollment):
            for item in group.items:
                if item.status == SubmissionStatus.REJECTED:
                    action_items.append(DeadlineItem(
                        title=f"{enrollment.program.code}: {item.label} was returned",
                        due_at=None,
                        context=item.review_comment or "Upload a corrected file",
                        link=f"/internships/{enrollment.program_id}", kind="internship",
                    ))
                elif item.is_mandatory and item.status == SubmissionStatus.NOT_SUBMITTED:
                    action_items.append(DeadlineItem(
                        title=f"{enrollment.program.code}: {item.label} not submitted",
                        due_at=item.period_end, context="Awaiting your upload",
                        link=f"/internships/{enrollment.program_id}", kind="internship",
                    ))
                elif item.awaits_review:
                    action_items.append(DeadlineItem(
                        title=f"{enrollment.program.code}: {item.label} awaiting verification",
                        due_at=None, context="With your mentor for review",
                        link=f"/internships/{enrollment.program_id}", kind="internship",
                    ))

    minor = db.scalar(select(MinorEnrollment).where(
        MinorEnrollment.student_id == student.id
    ))
    if minor and minor.minor_program:
        total = float(minor.minor_program.total_credits) or 1
        progress.append(ProgressItem(
            label=f"Minor · {minor.minor_program.name}",
            completed=int(float(minor.credits_completed)), total=int(total),
            link="/academics/minors",
        ))

    assignment = db.scalar(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id, MentorAssignment.is_active.is_(True)
    ))
    mentor = None
    if assignment:
        faculty = assignment.faculty
        mentor = {
            "id": faculty.id, "name": faculty.user.full_name,
            "designation": faculty.designation,
            "department": faculty.department.name if faculty.department else None,
            "cabin": faculty.cabin,
            "email": faculty.public_email or faculty.user.email,
            "phone": faculty.public_phone,
            "avatar_url": faculty.user.avatar_url,
        }

    alloc_by_component = {a.curriculum_component_id: a for a in allocations}
    allocated_electives = [
        {
            "id": a.id,
            "component_id": a.curriculum_component_id,
            "component_code": a.curriculum_component.code if a.curriculum_component else None,
            "component_title": a.curriculum_component.title if a.curriculum_component else None,
            "component_type": a.curriculum_component.component_type.value if a.curriculum_component else None,
            "course_offering_id": a.course_offering_id,
            "course_code": a.course_offering.course.code if a.course_offering and a.course_offering.course else None,
            "course_title": a.course_offering.course.title if a.course_offering and a.course_offering.course else None,
            "credits": float(a.course_offering.course.credits) if a.course_offering and a.course_offering.course else (float(a.curriculum_component.credits) if a.curriculum_component else 3.0),
            "section_name": a.section.name if a.section else None,
            "preference_order_granted": a.preference_order_granted,
            "status": a.status.value,
            "link": serializers.elective_path(a.curriculum_component) if a.curriculum_component else None,
        }
        for a in allocations
    ]

    semester_view = None
    if components:
        semester_view = {
            "semester_number": student.current_semester,
            "total_credits": round(sum(float(c.credits) for c in components), 1),
            "components": [
                {
                    "id": c.id, "code": c.code, "title": c.title,
                    "component_type": c.component_type.value,
                    "scope_label": c.scope_label,
                    "credits": float(c.credits),
                    "status": states[c.id].label,
                    "allocated_course_code": (
                        alloc_by_component[c.id].course_offering.course.code
                        if c.id in alloc_by_component and alloc_by_component[c.id].course_offering and alloc_by_component[c.id].course_offering.course
                        else None
                    ),
                    "allocated_course_title": (
                        alloc_by_component[c.id].course_offering.course.title
                        if c.id in alloc_by_component and alloc_by_component[c.id].course_offering and alloc_by_component[c.id].course_offering.course
                        else None
                    ),
                    "allocated_section": (
                        alloc_by_component[c.id].section.name
                        if c.id in alloc_by_component and alloc_by_component[c.id].section
                        else None
                    ),
                    "preference_order_granted": (
                        alloc_by_component[c.id].preference_order_granted
                        if c.id in alloc_by_component
                        else None
                    ),
                }
                for c in components
            ],
        }

    return StudentDashboard(
        stats=stats, curriculum_semester=semester_view,
        allocated_electives=allocated_electives,
        action_items=action_items[:6], progress=progress,
        upcoming_events=_event_dicts(db, student=student),
        announcements=_announcement_dicts(db, user), mentor=mentor,
    )


# ── head of department ────────────────────────────────────────────────────
@router.get("/hod", response_model=HodDashboard)
def hod_dashboard(db: DbSession, user: CurrentUser,
                  department_code: str | None = None) -> HodDashboard:
    """Who runs each module of the department, and which have nobody.

    Deliberately carries no mentee or review queue: a Head of Department has
    neither. Everything here is read-only — the one thing they *do* is appoint,
    and that happens on the role assignment screen this links to.
    """
    from app.api.v1.roles import DOMAIN_LABELS
    from app.models.enums import AssignedRole, CoordinationDomain

    if user.has_role(Role.SUPER_ADMIN):
        # The registrar oversees every department and may see what its Head
        # sees — read-only here, as it is for the Head. (The HoD is a real
        # person who cannot sign in to the demo; this is how their screen is
        # shown.)
        department = db.scalar(select(Department).where(
            Department.code == (department_code or "ICT").upper()))
    else:
        department = scope.hod_department(db, user)
    if department is None:
        raise PermissionDeniedError(
            "This dashboard is only available to a Head of Department."
        )

    faculty_rows = list(db.scalars(select(Faculty).where(
        Faculty.department_id == department.id, Faculty.is_active.is_(True))))
    student_count = _count(db, select(Student).where(
        Student.department_id == department.id))
    grants = [
        a for a in db.scalars(select(FacultyRoleAssignment).where(
            FacultyRoleAssignment.department_id == department.id,
            FacultyRoleAssignment.is_active.is_(True)))
        if a.is_current()
    ]

    modules = []
    for domain in CoordinationDomain:
        held = [a for a in grants if a.domain == domain]
        coordinators = [a for a in held if a.role == AssignedRole.COORDINATOR]
        modules.append({
            "domain": domain.value, "label": DOMAIN_LABELS[domain],
            "coordinators": [
                {"assignment_id": a.id, "faculty_id": a.faculty_id,
                 "name": a.faculty.user.full_name,
                 "designation": a.faculty.designation}
                for a in coordinators
            ],
            "mentor_count": sum(1 for a in held if a.role == AssignedRole.MENTOR),
            # Mentors alone do not run a module.
            "is_covered": bool(coordinators),
        })
    uncovered = sum(1 for m in modules if not m["is_covered"])

    now = utcnow()
    windows = list(db.scalars(
        select(ElectiveRegistrationWindow)
        .where(ElectiveRegistrationWindow.department_id == department.id)
        .order_by(ElectiveRegistrationWindow.opens_at.desc().nullslast())
        .limit(8)
    ))
    rounds = [
        {
            "id": w.id, "code": w.code, "title": w.title,
            "component_type": w.component_type.value, "status": w.status.value,
            "opens_at": w.opens_at.isoformat() if w.opens_at else None,
            "closes_at": w.closes_at.isoformat() if w.closes_at else None,
            "is_accepting": w.is_open_at(now),
            "eligible_student_count": registration.count_students_in_window(db, w),
        }
        for w in windows
    ]

    stats = [
        StatCard(key="faculty", label="Faculty", value=len(faculty_rows),
                 hint=department.name, link="/faculty"),
        StatCard(key="students", label="Students", value=student_count),
        StatCard(key="uncovered", label="Modules without a coordinator",
                 value=uncovered, hint=f"of {len(modules)} modules",
                 link="/admin/roles"),
        StatCard(key="open_rounds", label="Rounds accepting preferences",
                 value=sum(1 for r in rounds if r["is_accepting"])),
    ]
    hod = db.get(Faculty, department.hod_faculty_id) if department.hod_faculty_id else None
    return HodDashboard(
        department={"id": department.id, "code": department.code,
                    "name": department.name},
        hod_name=hod.user.full_name if hod else None,

        stats=stats, modules=modules, rounds=rounds,
        announcements=_announcement_dicts(db, user),
    )


# ── faculty ───────────────────────────────────────────────────────────────
@router.get("/faculty", response_model=FacultyDashboard)
def faculty_dashboard(db: DbSession, user: CurrentUser,
                      faculty=Depends(get_optional_faculty)) -> FacultyDashboard:
    if faculty is None:
        raise PermissionDeniedError("This dashboard is only available to faculty.")

    mentee_count = _count(db, select(MentorAssignment).where(
        MentorAssignment.faculty_id == faculty.id, MentorAssignment.is_active.is_(True)
    ))
    my_enrollments = list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.mentor_faculty_id == faculty.id
    )))
    enrollment_ids = [e.id for e in my_enrollments] or [0]

    pending_stages = list(db.scalars(
        select(EnrollmentStageProgress).where(
            EnrollmentStageProgress.enrollment_id.in_(enrollment_ids),
            EnrollmentStageProgress.status == StageStatus.SUBMITTED,
        ).order_by(EnrollmentStageProgress.submitted_at)
    ))
    pending_reports = list(db.scalars(
        select(InternshipReport).where(
            InternshipReport.enrollment_id.in_(enrollment_ids),
            InternshipReport.status == SubmissionStatus.SUBMITTED,
        ).order_by(InternshipReport.submitted_at)
    ))
    pending_evaluations = sum(
        1 for e in my_enrollments
        if e.status in (EnrollmentStatus.UNDER_EVALUATION, EnrollmentStatus.SUBMITTED)
    )
    open_meetings = list(db.scalars(
        select(MentorMeeting).where(MentorMeeting.faculty_id == faculty.id,
                                    MentorMeeting.status.in_([MeetingStatus.REQUESTED,
                                                              MeetingStatus.APPROVED]))
        .order_by(MentorMeeting.requested_at.desc()).limit(6)
    ))

    stats = [
        StatCard(key="mentees", label="Assigned mentees", value=mentee_count,
                 link="/mentorship/mentees"),
        StatCard(key="internship_students", label="Internship students",
                 value=len(my_enrollments), link="/internships/my-students"),
        StatCard(key="pending_reviews", label="Awaiting my review",
                 value=len(pending_stages) + len(pending_reports)),
        StatCard(key="pending_evaluations", label="Evaluations pending",
                 value=pending_evaluations),
    ]

    reviews = [
        {
            "type": "stage", "id": p.id, "enrollment_id": p.enrollment_id,
            "student": p.enrollment.student.user.full_name,
            "roll_number": p.enrollment.student.roll_number,
            "label": p.stage.name,
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            "link": f"/internships/students/{p.enrollment_id}",
        }
        for p in pending_stages[:6]
    ] + [
        {
            "type": "report", "id": r.id, "enrollment_id": r.enrollment_id,
            "student": db.get(InternshipEnrollment, r.enrollment_id).student.user.full_name,
            "roll_number": db.get(InternshipEnrollment,
                                  r.enrollment_id).student.roll_number,
            "label": f"{r.report_type.value.title()} report #{r.sequence_number}",
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "link": f"/internships/students/{r.enrollment_id}",
        }
        for r in pending_reports[:6]
    ]

    mentees = db.scalars(
        select(MentorAssignment).where(MentorAssignment.faculty_id == faculty.id,
                                       MentorAssignment.is_active.is_(True)).limit(6)
    )
    groups = db.scalars(select(InternshipGroup).where(
        InternshipGroup.faculty_id == faculty.id
    ))

    return FacultyDashboard(
        stats=stats, pending_reviews=reviews,
        mentees_preview=[
            {
                "student_id": a.student_id, "name": a.student.user.full_name,
                "roll_number": a.student.roll_number,
                "semester": a.student.current_semester,
                "cpi": float(a.student.cpi) if a.student.cpi is not None else None,
                "avatar_url": a.student.user.avatar_url,
            }
            for a in mentees
        ],
        internship_groups=[
            {
                "id": g.id, "name": g.name, "program_id": g.program_id,
                "program": g.program.name if g.program else None,
                "capacity": g.capacity,
                "member_count": _count(db, select(InternshipEnrollment).where(
                    InternshipEnrollment.group_id == g.id
                )),
            }
            for g in groups
        ],
        upcoming_meetings=[
            {
                "id": m.id, "title": m.title,
                "student": m.student.user.full_name,
                "status": m.status.value,
                "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                "proposed_slot": m.proposed_slot.isoformat() if m.proposed_slot else None,
            }
            for m in open_meetings
        ],
        announcements=_announcement_dicts(db, user),
        portfolios=_coordination_portfolios(db, user),
    )


def _stat(label: str, value: int, hint: str | None = None,
          tone: str = "default") -> dict:
    return {"label": label, "value": value, "hint": hint, "tone": tone}


def _program_stats(db, program: InternshipProgram) -> list[dict]:
    in_program = InternshipEnrollment.program_id == program.id
    registered = _count(db, select(InternshipEnrollment).where(in_program))
    unassigned = _count(db, select(InternshipEnrollment).where(
        in_program, InternshipEnrollment.mentor_faculty_id.is_(None)))
    mentors = int(db.scalar(
        select(func.count(func.distinct(InternshipEnrollment.mentor_faculty_id)))
        .where(in_program, InternshipEnrollment.mentor_faculty_id.is_not(None))
    ) or 0)
    enrollment_ids = select(InternshipEnrollment.id).where(in_program)
    to_review = _count(db, select(EnrollmentStageProgress).where(
        EnrollmentStageProgress.enrollment_id.in_(enrollment_ids),
        EnrollmentStageProgress.status == StageStatus.SUBMITTED,
    )) + _count(db, select(InternshipReport).where(
        InternshipReport.enrollment_id.in_(enrollment_ids),
        InternshipReport.status == SubmissionStatus.SUBMITTED,
    ))
    load = f"~{registered / mentors:.1f} per mentor" if mentors else None
    return [
        _stat("Registered", registered),
        _stat("Mentors", mentors, load),
        _stat("Awaiting mentor", unassigned, tone="warning" if unassigned else "success"),
        _stat("Submissions to review", to_review, tone="warning" if to_review else "default"),
    ]


def _coordination_portfolios(db, user: User) -> list[dict]:
    """What each coordinated module looks like right now, for that scope only.

    An internship coordination expands to one entry per programme it governs,
    so the dashboard can link to the real programme id rather than a guess.
    """
    from app.models.enums import INTERNSHIP_DOMAINS, AssignedRole, CoordinationDomain as D
    from app.models.minors import MinorProgram

    now = utcnow()
    out: list[dict] = []
    for c in scope.coordinations_for(db, user, AssignedRole.COORDINATOR):
        base = {
            "domain": c.domain.value, "department_id": c.department_id,
            "department_code": c.department_code,
            "department_name": c.department_name,
            "is_institution_wide": c.is_institution_wide,
            "program_id": None, "program_name": None, "stats": [],
        }
        in_dept = (lambda col: col == c.department_id) if c.department_id else None

        if c.domain in INTERNSHIP_DOMAINS:
            programs = [
                p for p in db.scalars(select(InternshipProgram).order_by(InternshipProgram.id))
                if scope.domain_for_program(p) == c.domain
                and (c.department_id is None or p.department_id == c.department_id)
            ]
            if not programs:
                out.append(base)
            for p in programs:
                out.append({**base, "program_id": p.id, "program_name": p.name,
                            "stats": _program_stats(db, p),
                            # Where a window-run cycle stands, step by step.
                            "windows": [
                                {"kind": kind.value,
                                 "state": (w.state_at(now) if (w := program_windows.get(
                                     db, p.id, kind)) else "NOT_STARTED"),
                                 "closes_at": w.closes_at.isoformat() if w else None}
                                for kind in program_windows.kinds_for(p)
                            ]})
            continue

        if c.domain in (D.OPEN_ELECTIVE, D.CORE_ELECTIVE):
            ctype = (ComponentType.OPEN_ELECTIVE if c.domain == D.OPEN_ELECTIVE
                     else ComponentType.PROGRAM_CORE_ELECTIVE)
            stmt = select(ElectiveRegistrationWindow).where(
                ElectiveRegistrationWindow.component_type == ctype)
            if in_dept:
                stmt = stmt.where(in_dept(ElectiveRegistrationWindow.department_id))
            windows = list(db.scalars(stmt))
            accepting = sum(1 for w in windows if w.is_open_at(now))
            awaiting = sum(1 for w in windows if w.status.value in ("LOCKED", "ALLOCATED"))
            base["stats"] = [
                _stat("Rounds", len(windows)),
                _stat("Accepting choices", accepting, tone="success" if accepting else "default"),
                _stat("Awaiting allocation or publish", awaiting,
                      tone="warning" if awaiting else "default"),
            ]
        elif c.domain == D.MINOR:
            programs = select(MinorProgram.id)
            if in_dept:
                programs = programs.where(in_dept(MinorProgram.department_id))
            pending = _count(db, select(MinorApplication).where(
                MinorApplication.minor_program_id.in_(programs),
                MinorApplication.status.in_([MinorApplicationStatus.SUBMITTED,
                                             MinorApplicationStatus.UNDER_REVIEW]),
            ))
            base["stats"] = [
                _stat("Tracks", _count(db, programs)),
                _stat("Applications to review", pending,
                      tone="warning" if pending else "default"),
            ]
        elif c.domain == D.MOOC:
            stmt = select(MoocRegistration).where(
                MoocRegistration.verification_status == VerificationStatus.PENDING,
                MoocRegistration.certificate_file_id.is_not(None),
            )
            if in_dept:
                stmt = stmt.join(Student, Student.id == MoocRegistration.student_id) \
                           .where(in_dept(Student.department_id))
            pending = _count(db, stmt)
            base["stats"] = [_stat("Certificates to verify", pending,
                                   tone="warning" if pending else "success")]
        elif c.domain == D.MENTORSHIP:
            stmt = select(MentorAssignment).where(MentorAssignment.is_active.is_(True))
            if in_dept:
                stmt = stmt.join(Student, Student.id == MentorAssignment.student_id) \
                           .where(in_dept(Student.department_id))
            pairs = list(db.scalars(stmt))
            base["stats"] = [
                _stat("Students with a mentor", len(pairs)),
                _stat("Faculty mentors", len({a.faculty_id for a in pairs})),
            ]
        out.append(base)
    return out


# ── administration ────────────────────────────────────────────────────────
@router.get("/admin", response_model=AdminDashboard)
def admin_dashboard(
    db: DbSession,
    user: User = Depends(require_permission(P["REPORT_VIEW"])),
) -> AdminDashboard:
    now = utcnow()
    students = _count(db, select(Student))
    faculty = _count(db, select(Faculty))
    departments = _count(db, select(Department))
    active_events = _count(db, select(Event).where(
        Event.status == EventStatus.PUBLISHED, Event.start_at >= now
    ))
    clubs = _count(db, select(Club).where(Club.is_active.is_(True)))

    pending_minor = _count(db, select(MinorApplication).where(
        MinorApplication.status == MinorApplicationStatus.SUBMITTED
    ))
    pending_mooc = _count(db, select(MoocRegistration).where(
        MoocRegistration.verification_status == VerificationStatus.PENDING,
        MoocRegistration.certificate_file_id.is_not(None),
    ))
    pending_stage_reviews = _count(db, select(EnrollmentStageProgress).where(
        EnrollmentStageProgress.status == StageStatus.SUBMITTED
    ))
    pending_evaluations = _count(db, select(InternshipEnrollment).where(
        InternshipEnrollment.status.in_([EnrollmentStatus.SUBMITTED,
                                         EnrollmentStatus.UNDER_EVALUATION])
    ))
    unallocated_prefs = _count(db, select(ElectivePreference).where(
        ElectivePreference.preference_order == 1
    )) - _count(db, select(ElectiveAllocation))

    stats = [
        StatCard(key="students", label="Students", value=students,
                 link="/admin/students"),
        StatCard(key="faculty", label="Faculty", value=faculty, link="/admin/faculty"),
        StatCard(key="departments", label="Departments", value=departments,
                 link="/admin/departments"),
        StatCard(key="clubs", label="Active clubs", value=clubs, link="/admin/clubs"),
        StatCard(key="events", label="Upcoming events", value=active_events,
                 link="/admin/events"),
        StatCard(key="internship_enrollments", label="Internship enrolments",
                 value=_count(db, select(InternshipEnrollment)),
                 link="/admin/internships"),
    ]

    pending_actions = [
        StatCard(key="minor_applications", label="Minor applications to review",
                 value=pending_minor, link="/admin/minors"),
        StatCard(key="mooc_verification", label="NPTEL certificates to verify",
                 value=pending_mooc, link="/admin/nptel"),
        StatCard(key="stage_reviews", label="Internship submissions to review",
                 value=pending_stage_reviews, link="/admin/internships"),
        StatCard(key="evaluations", label="Evaluations pending",
                 value=pending_evaluations, link="/admin/internships"),
        StatCard(key="elective_allocation", label="Elective preferences unallocated",
                 value=max(unallocated_prefs, 0), link="/admin/electives"),
    ]

    by_semester = [
        BreakdownItem(label=f"Semester {row[0]}", value=int(row[1]), total=students)
        for row in db.execute(
            select(Student.current_semester, func.count(Student.id))
            .group_by(Student.current_semester).order_by(Student.current_semester)
        ).all()
    ]

    internship_progress = []
    for program in db.scalars(select(InternshipProgram).order_by(InternshipProgram.code)):
        total = _count(db, select(InternshipEnrollment).where(
            InternshipEnrollment.program_id == program.id
        ))
        done = _count(db, select(InternshipEnrollment).where(
            InternshipEnrollment.program_id == program.id,
            InternshipEnrollment.status == EnrollmentStatus.COMPLETED,
        ))
        if total:
            internship_progress.append(
                BreakdownItem(label=program.code, value=done, total=total)
            )

    # The activity panel is audit-log data, so it is included only for callers
    # who also hold `audit:view` — never widened by `reports:view` alone.
    activity: list[ActivityItem] = []
    if has_permission(user.roles, P["AUDIT_VIEW"]):
        activity = [
            ActivityItem(
                id=log.id, actor=log.actor_label, action=log.action.value,
                entity_type=log.entity_type, entity_id=log.entity_id,
                description=log.description, created_at=log.created_at,
            )
            for log in db.scalars(
                select(AuditLog).order_by(AuditLog.created_at.desc()).limit(12)
            )
        ]

    return AdminDashboard(
        stats=stats, students_by_semester=by_semester,
        internship_progress=internship_progress, pending_actions=pending_actions,
        recent_activity=activity, upcoming_events=_event_dicts(db, limit=6),
    )
