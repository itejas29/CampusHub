"""One student, seen whole — the view faculty workflows start from.

Faculty were previously served by several partial screens: a mentee row here, an
internship drawer there, documents somewhere else. This assembles the same
records into one authorised response, so opening a student answers "where does
this person actually stand" without five more requests.

Authorisation is the interesting part. "Staff" is far too wide a rule: a club
administrator has no business reading a student's internship evaluation. Access
is granted to the student themselves, their assigned mentor, the coordinators of
a module the student actually participates in, department administrators of
their department, and super admins — and each section is filtered again, so a
caller who may see the academic tab does not thereby see evaluation marks.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.academics import (
    Course, CourseOffering, Curriculum, CurriculumComponent, ElectiveAllocation,
    MoocRegistration, Program,
)
from app.models.engagement import MentorAssignment, MentorMeeting
from app.models.enums import (
    AllocationStatus, ComponentType, CoordinationDomain, MeetingStatus, Role,
)
from app.models.identity import Department, Faculty, Student, User
from app.models.internships import (
    InternshipEnrollment, InternshipEvaluation, InternshipProgram, Organization,
)
from app.models.minors import MinorEnrollment
from app.schemas.student_profile import (
    ProfileAcademic, ProfileDocument, ProfileEvaluation, ProfileInternship,
    ProfileMentor, ProfilePersonal, StudentProfileOut,
)
from app.services import curriculum as curriculum_engine
from app.services import documents as docs
from app.services import scope

router = APIRouter(prefix="/student-profile", tags=["students"])


def _visibility(db, viewer: User, student: Student) -> set[str]:
    """Which sections this viewer may see. Empty means no access at all.

    Returned as a set rather than a boolean because the sections genuinely
    differ: a mentor sees meetings the coordinator does not, and a coordinator
    sees evaluation marks a peer mentor of another module does not.
    """
    everything = {"personal", "academic", "internship", "documents",
                  "evaluation", "mentor"}

    if viewer.has_role(Role.SUPER_ADMIN):
        return everything
    if student.user_id == viewer.id:
        return everything

    faculty = db.scalar(select(Faculty).where(Faculty.user_id == viewer.id))
    if faculty is None:
        return set()

    granted: set[str] = set()

    # A department administrator over the student's own department.
    if (viewer.has_role(Role.DEPARTMENT_ADMIN)
            and faculty.department_id == student.department_id):
        granted |= everything

    # The student's assigned mentor.
    mentored = db.scalar(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id,
        MentorAssignment.faculty_id == faculty.id,
        MentorAssignment.is_active.is_(True)))
    if mentored:
        granted |= everything

    # A coordinator of a module this student actually participates in. Note the
    # scope is checked per programme: coordinating Summer Internship for ICT
    # grants nothing over CSSI, and nothing over another department.
    enrollments = db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.student_id == student.id))
    for enrollment in enrollments:
        program = db.get(InternshipProgram, enrollment.program_id)
        if program is None:
            continue
        if scope.can_manage_program(db, viewer, program):
            granted |= {"personal", "academic", "internship", "documents",
                        "evaluation"}

    # Elective and MOOC coordinators see the academic side within their scope.
    for domain in (CoordinationDomain.OPEN_ELECTIVE, CoordinationDomain.CORE_ELECTIVE,
                   CoordinationDomain.MOOC, CoordinationDomain.MINOR):
        if scope.coordinates(db, viewer, domain, student.department_id):
            granted |= {"personal", "academic"}

    # Being a mentor for a module in a department is NOT a reason to open every
    # student in it. Mentor access is earned per student: either a mentorship
    # assignment (checked above) or being the mentor recorded on one of this
    # student's own internship enrolments.
    mentored_enrollment = db.scalar(select(InternshipEnrollment).where(
        InternshipEnrollment.student_id == student.id,
        InternshipEnrollment.mentor_faculty_id == faculty.id))
    if mentored_enrollment is not None:
        granted |= {"personal", "internship", "documents", "evaluation"}

    return granted


@router.get("/{student_id}", response_model=StudentProfileOut)
def student_profile(student_id: int, db: DbSession,
                    viewer: CurrentUser) -> StudentProfileOut:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")

    sections = _visibility(db, viewer, student)
    if not sections:
        raise PermissionDeniedError(
            "You do not have access to this student's profile. Access is limited "
            "to their mentor, the coordinators of a module they take, and "
            "administrators of their department."
        )

    account = db.get(User, student.user_id)
    program = db.get(Program, student.program_id)
    department = db.get(Department, student.department_id)

    personal = ProfilePersonal(
        student_id=student.id, full_name=account.full_name, email=account.email,
        phone=account.phone, roll_number=student.roll_number,
        enrollment_number=student.enrollment_number,
        program_name=program.name if program else None,
        program_code=program.code if program else None,
        department_code=department.code if department else None,
        school=department.school if department else None,
        batch=student.batch, division=student.division,
        admission_year=student.admission_year,
        current_semester=student.current_semester, status=student.status,
    )

    academic = _academic(db, student) if "academic" in sections else None
    internship = _internships(db, student) if "internship" in sections else []
    documents = _documents(db, student) if "documents" in sections else []
    evaluation = _evaluations(db, student) if "evaluation" in sections else []
    mentor = _mentor(db, student, viewer) if "mentor" in sections else None

    return StudentProfileOut(
        personal=personal, academic=academic, internships=internship,
        documents=documents, evaluations=evaluation, mentor=mentor,
        visible_sections=sorted(sections),
    )


def _academic(db, student: Student) -> ProfileAcademic:
    """Curriculum, electives and minor — all resolved through the batch."""
    curriculum = curriculum_engine.resolve_curriculum(db, student)
    components = (curriculum_engine.components_for(db, curriculum)
                  if curriculum else [])

    allocations = []
    rows = db.scalars(
        select(ElectiveAllocation).where(
            ElectiveAllocation.student_id == student.id,
            ElectiveAllocation.status != AllocationStatus.DROPPED))
    for allocation in rows:
        offering = allocation.course_offering
        component = allocation.curriculum_component
        if offering is None:
            continue
        allocations.append({
            "component": component.title if component else None,
            "component_code": component.code if component else None,
            "course_code": offering.course.code,
            "course_title": offering.course.title,
            "section": allocation.section.name if allocation.section else None,
            "status": allocation.status.value,
        })

    moocs = []
    for registration in db.scalars(select(MoocRegistration).where(
            MoocRegistration.student_id == student.id)):
        offering = registration.course_offering
        moocs.append({
            "course": offering.course.title if offering else None,
            "platform": registration.platform.value,
            "status": registration.status.value,
            "verification": registration.verification_status.value,
        })

    minor = db.scalar(select(MinorEnrollment).where(
        MinorEnrollment.student_id == student.id))

    current = [c for c in components
               if c.semester_number == student.current_semester]
    return ProfileAcademic(
        curriculum_name=curriculum.name if curriculum else None,
        curriculum_version=curriculum.version if curriculum else None,
        curriculum_status=curriculum.status.value if curriculum else None,
        batch_label=(f"{curriculum.effective_from_year}"
                     f"{'–' + str(curriculum.effective_to_year) if curriculum and curriculum.effective_to_year else ' onward'}"
                     if curriculum else None),
        cpi=float(student.cpi) if student.cpi is not None else None,
        backlog_count=student.backlog_count,
        current_semester_components=[
            {"code": c.code, "title": c.title, "type": c.component_type.value,
             "credits": float(c.credits), "is_elective": c.is_elective}
            for c in current
        ],
        elective_allocations=allocations,
        mooc_registrations=moocs,
        minor_name=minor.minor_program.name if minor and minor.minor_program else None,
        minor_status=minor.status.value if minor else None,
    )


def _internships(db, student: Student) -> list[ProfileInternship]:
    out = []
    for enrollment in db.scalars(select(InternshipEnrollment).where(
            InternshipEnrollment.student_id == student.id)):
        program = db.get(InternshipProgram, enrollment.program_id)
        organization = (db.get(Organization, enrollment.organization_id)
                        if enrollment.organization_id else None)
        mentor = (db.get(Faculty, enrollment.mentor_faculty_id)
                  if enrollment.mentor_faculty_id else None)
        progress = docs.progress(db, enrollment)
        out.append(ProfileInternship(
            enrollment_id=enrollment.id,
            program_name=program.name if program else "Internship",
            program_type=program.type.value if program else None,
            status=enrollment.status.value,
            organization=organization.name if organization else None,
            faculty_mentor=(mentor.user.full_name if mentor and mentor.user else None),
            progress_percent=progress.get("percent", 0),
            completed_items=progress.get("completed", 0),
            total_items=progress.get("total", 0),
        ))
    return out


def _documents(db, student: Student) -> list[ProfileDocument]:
    """Expected *and* submitted, flattened across every enrolment.

    `expected_documents` synthesises the NOT_SUBMITTED rows, which is the whole
    point: a missing mandatory report stays on the list instead of quietly
    disappearing because nothing was uploaded for it.
    """
    out = []
    for enrollment in db.scalars(select(InternshipEnrollment).where(
            InternshipEnrollment.student_id == student.id)):
        for group in docs.expected_documents(db, enrollment):
            for item in group.items:
                out.append(ProfileDocument(
                    enrollment_id=enrollment.id,
                    group=group.title,
                    label=item.label,
                    document_type=item.document_type,
                    week=item.week_number,
                    status=item.status.value,
                    is_mandatory=item.is_mandatory,
                    file_id=item.file_id,
                    file_url=item.file_url,
                    submitted_at=item.submitted_at,
                    reviewer_comment=getattr(item, "review_comment", None),
                ))
    return out


def _evaluations(db, student: Student) -> list[ProfileEvaluation]:
    out = []
    for enrollment in db.scalars(select(InternshipEnrollment).where(
            InternshipEnrollment.student_id == student.id)):
        for evaluation in db.scalars(select(InternshipEvaluation).where(
                InternshipEvaluation.enrollment_id == enrollment.id)):
            out.append(ProfileEvaluation(
                enrollment_id=enrollment.id,
                evaluator_role=evaluation.evaluator_role.value,
                status=evaluation.status.value,
                total_marks=(float(evaluation.total_marks)
                             if evaluation.total_marks is not None else None),
                max_marks=(float(evaluation.max_marks)
                           if evaluation.max_marks is not None else None),
                remarks=evaluation.comments,
                grade=evaluation.grade,
                scores=[
                    {"criterion": score.criteria.name if score.criteria else None,
                     "marks": float(score.marks) if score.marks is not None else None,
                     "max_marks": (float(score.criteria.max_marks)
                                   if score.criteria else None),
                     "comment": score.comments}
                    for score in evaluation.scores
                ],
            ))
    return out


def _mentor(db, student: Student, viewer: User) -> ProfileMentor | None:
    assignment = db.scalar(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id,
        MentorAssignment.is_active.is_(True)))
    if assignment is None:
        return None
    faculty = db.get(Faculty, assignment.faculty_id)
    if faculty is None:
        return None

    # Meeting history is between the student and their mentor. A coordinator of
    # an unrelated module has no reason to read it, so it is only included for
    # the student, the mentor themselves, and administrators.
    may_read_meetings = (
        viewer.has_role(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN)
        or student.user_id == viewer.id
        or faculty.user_id == viewer.id
    )
    meetings = []
    if may_read_meetings:
        rows = db.scalars(
            select(MentorMeeting)
            .where(MentorMeeting.student_id == student.id)
            .order_by(MentorMeeting.requested_at.desc().nullslast()).limit(10))
        meetings = [
            {"title": m.title, "status": m.status.value,
             "requested_at": m.requested_at.isoformat() if m.requested_at else None,
             "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
             "mode": m.mode.value if m.mode else None}
            for m in rows
        ]
    return ProfileMentor(
        faculty_id=faculty.id,
        full_name=faculty.user.full_name if faculty.user else None,
        email=faculty.public_email or (faculty.user.email if faculty.user else None),
        cabin=faculty.cabin, designation=faculty.designation,
        department_code=faculty.department.code if faculty.department else None,
        meetings_visible=may_read_meetings, recent_meetings=meetings,
    )
