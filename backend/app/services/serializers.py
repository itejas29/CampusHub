"""ORM → schema helpers shared by routers, so shapes stay consistent."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.academics import Course, CourseOffering, CurriculumComponent, as_utc
from app.models.community import Club, Event, EventInterest, EventRegistration
from app.models.enums import EventStatus, RegistrationStatus
from app.models.identity import Faculty, Student, User
from app.models.system import StoredFile
from app.schemas.academics import (
    CourseOfferingOut, CourseOut, CurriculumComponentOut, SectionOut,
)
from app.schemas.community import ClubOut, EventOut
from app.schemas.identity import FacultyOut, StudentOut
from app.services.files import signed_url


def course_out(course: Course) -> CourseOut:
    return CourseOut(
        id=course.id, code=course.code, title=course.title,
        credits=float(course.credits),
        department_id=course.department_id,
        department_code=course.department.code if course.department else None,
        department_name=course.department.name if course.department else None,
        offering_school=course.offering_school,
        lecture_hours=course.lecture_hours, tutorial_hours=course.tutorial_hours,
        practical_hours=course.practical_hours, description=course.description,
        prerequisites=course.prerequisites, syllabus_url=course.syllabus_url,
        specialization_area=course.specialization_area, platform=course.platform,
        provider_url=course.provider_url, duration_weeks=course.duration_weeks,
        is_active=course.is_active,
    )


def section_out(section, *, breakdown: list[dict] | None = None) -> SectionOut:
    return SectionOut(
        id=section.id, course_offering_id=section.course_offering_id,
        name=section.name, capacity=section.capacity,
        seats_filled=section.seats_filled,
        seats_available=section.seats_available, is_full=section.is_full,
        faculty_id=section.faculty_id,
        faculty_name=section.faculty.user.full_name if section.faculty else None,
        venue=section.venue, schedule_note=section.schedule_note,
        is_active=section.is_active, division_breakdown=breakdown or [],
    )


def offering_out(
    offering: CourseOffering, *, is_open: bool | None = None,
    my_preference_order: int | None = None, include_sections: bool = True,
) -> CourseOfferingOut:
    component = offering.curriculum_component
    coordinator = offering.__dict__.get("_coordinator")
    return CourseOfferingOut(
        id=offering.id, course=course_out(offering.course),
        semester_id=offering.semester_id,
        semester_number=offering.semester.number if offering.semester else None,
        curriculum_component_id=offering.curriculum_component_id,
        component_code=component.code if component else None,
        component_title=component.title if component else None,
        elective_type_id=offering.elective_type_id,
        min_students_to_run=offering.min_students_to_run,
        section_capacity=offering.section_capacity,
        allow_multiple_sections=offering.allow_multiple_sections,
        eligible_divisions=list(offering.eligible_divisions or []),
        seats_filled=offering.seats_filled,
        sections_needed=offering.sections_needed,
        is_viable=offering.is_viable,
        sections=[section_out(s) for s in offering.sections if s.is_active]
        if include_sections else [],
        status=offering.status,
        registration_opens_at=offering.registration_opens_at,
        registration_closes_at=offering.registration_closes_at,
        venue=offering.venue, schedule_note=offering.schedule_note,
        coordinator_name=coordinator, notes=offering.notes,
        is_open=is_open, my_preference_order=my_preference_order,
    )


def component_out(
    component: CurriculumComponent, *, is_unlocked: bool | None = None,
    status_label: str | None = None, allocated_course: str | None = None,
    offering_count: int | None = None, round_id: int | None = None,
    round_two_stage: bool | None = None,
) -> CurriculumComponentOut:
    return CurriculumComponentOut(
        id=component.id, curriculum_id=component.curriculum_id,
        semester_number=component.semester_number, code=component.code,
        title=component.title, component_type=component.component_type,
        source_scope=component.source_scope, scope_label=component.scope_label,
        credits=float(component.credits), sequence=component.sequence,
        is_elective=component.is_elective, description=component.description,
        elective_type_id=component.elective_type_id,
        elective_type_code=component.elective_type.code if component.elective_type else None,
        config=component.config or {},
        eligibility=component.eligibility or {},
        selection_mode=component.selection_mode,
        course_code=component.course.code if component.course else None,
        course_title=component.course.title if component.course else None,
        course_category=(component.course.category.value
                        if component.course and component.course.category else None),
        delivery_mode=(component.course.delivery_mode.value
                       if component.course else None),
        source_confidence=(component.source_confidence.value
                           if component.source_confidence else None),
        source_note=component.source_note,
        is_unlocked=is_unlocked,
        status_label=status_label, allocated_course=allocated_course,
        offering_count=offering_count, round_id=round_id,
        round_two_stage=round_two_stage,
    )


def student_out(student: Student, user: User | None = None) -> StudentOut:
    user = user or student.user
    return StudentOut(
        id=student.id, user_id=student.user_id, full_name=user.full_name,
        email=user.email, phone=user.phone, avatar_url=user.avatar_url,
        roll_number=student.roll_number, enrollment_number=student.enrollment_number,
        program_id=student.program_id,
        program_name=student.program.name if student.program else None,
        department_id=student.department_id,
        department_code=student.department.code if student.department else None,
        admission_year=student.admission_year,
        current_semester=student.current_semester, division=student.division,
        batch=student.batch, cpi=float(student.cpi) if student.cpi is not None else None,
        backlog_count=student.backlog_count, status=student.status,
    )


def faculty_out(faculty: Faculty, *, mentee_count: int = 0) -> FacultyOut:
    user = faculty.user
    return FacultyOut(
        id=faculty.id, user_id=faculty.user_id, full_name=user.full_name,
        email=user.email, employee_code=faculty.employee_code,
        department_id=faculty.department_id,
        department_code=faculty.department.code if faculty.department else None,
        department_name=faculty.department.name if faculty.department else None,
        designation=faculty.designation, cabin=faculty.cabin,
        public_email=faculty.public_email or user.email,
        public_phone=faculty.public_phone, specialization=faculty.specialization,
        qualification=faculty.qualification, avatar_url=user.avatar_url,
        bio=faculty.bio, is_mentor=faculty.is_mentor, is_active=faculty.is_active,
        is_demo=faculty.is_demo, profile_url=faculty.profile_url,
        mentee_count=mentee_count,
    )


def club_out(club: Club, *, member_count: int = 0, upcoming: int = 0,
             head_name: str | None = None, is_member: bool | None = None) -> ClubOut:
    advisor = club.faculty_advisor
    return ClubOut(
        id=club.id, name=club.name, slug=club.slug, category=club.category,
        tagline=club.tagline, description=club.description, logo_url=club.logo_url,
        instagram_url=club.instagram_url, linkedin_url=club.linkedin_url,
        website_url=club.website_url, email=club.email, founded_year=club.founded_year,
        faculty_advisor_id=club.faculty_advisor_id,
        faculty_advisor_name=advisor.user.full_name if advisor else None,
        is_active=club.is_active, member_count=member_count,
        upcoming_event_count=upcoming, head_name=head_name, is_member=is_member,
    )


def event_out(
    event: Event, *, registration_count: int = 0, interest_count: int = 0,
    my_registration: RegistrationStatus | None = None, am_i_interested: bool = False,
    now=None,
) -> EventOut:
    import datetime as dt

    now = now or dt.datetime.now(dt.timezone.utc)
    seats_available = (
        max(event.capacity - registration_count, 0) if event.capacity else None
    )
    deadline = as_utc(event.registration_deadline or event.start_at)
    registration_open = (
        event.status == EventStatus.PUBLISHED
        and event.registration_required
        and deadline > now
        and (seats_available is None or seats_available > 0)
    )
    return EventOut(
        id=event.id, title=event.title, slug=event.slug, event_type=event.event_type,
        summary=event.summary, description=event.description, start_at=event.start_at,
        end_at=event.end_at, venue=event.venue, mode=event.mode,
        meeting_url=event.meeting_url,
        registration_required=event.registration_required,
        registration_deadline=event.registration_deadline, capacity=event.capacity,
        poster_url=event.poster_url, external_url=event.external_url,
        speaker=event.speaker, tags=event.tags or [], status=event.status,
        club_id=event.club_id, club_name=event.club.name if event.club else None,
        club_slug=event.club.slug if event.club else None,
        registration_count=registration_count, interest_count=interest_count,
        seats_available=seats_available,
        is_full=bool(event.capacity and registration_count >= event.capacity),
        registration_open=registration_open,
        my_registration_status=my_registration, am_i_interested=am_i_interested,
    )


def event_counts(db: Session, event_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    if not event_ids:
        return {}, {}
    regs = dict(db.execute(
        select(EventRegistration.event_id, func.count(EventRegistration.id))
        .where(EventRegistration.event_id.in_(event_ids),
               EventRegistration.status != RegistrationStatus.CANCELLED)
        .group_by(EventRegistration.event_id)
    ).all())
    interests = dict(db.execute(
        select(EventInterest.event_id, func.count(EventInterest.id))
        .where(EventInterest.event_id.in_(event_ids),
               EventInterest.is_interested.is_(True))
        .group_by(EventInterest.event_id)
    ).all())
    return regs, interests


def file_url(db: Session, file_id: int | None) -> str | None:
    if not file_id:
        return None
    return signed_url(db.get(StoredFile, file_id))


def elective_path(component, *, detail: bool = True) -> str:
    """Front-end route for an elective component.

    Open and Core electives are separate screens, so a single "/electives" path
    404s. The component's own type decides which one, rather than every caller
    guessing.

    A MOOC/NPTEL slot has its own screen and no per-component workspace: sending
    it to the Open Elective workspace opened a preference form for a slot that
    is settled by registering one external course.
    """
    from app.models.enums import ComponentType

    component_type = getattr(component, "component_type", None)
    if component_type == ComponentType.MOOC:
        return "/academics/nptel"
    base = ("/academics/core-electives"
            if component_type == ComponentType.PROGRAM_CORE_ELECTIVE
            else "/academics/open-electives")
    return f"{base}/{component.id}" if detail else base
