"""Open Electives, Program Core Electives and the allocation entry point.

The same routes serve every elective family — which components a student sees
comes from the curriculum, never from a hard-coded list.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from app.core.deps import (
    CurrentStudent, CurrentUser, DbSession, require_permission,
    require_permission_or_coordination, request_context,
)
from app.core.errors import (
    BusinessRuleError, ConflictError, NotFoundError, PermissionDeniedError,
    ValidationError,
)
from app.core.rbac import P
from app.models.academics import (
    Course, CourseOffering, CourseSection, Curriculum, CurriculumComponent,
    ElectiveAllocation, ElectivePreference, ElectiveRegistrationWindow, Program,
    ProgramDivision,
)
from app.models.enums import (
    AllocationStatus, AuditAction, ComponentType, CoordinationDomain,
    CurriculumStatus, NotificationType, OfferingStatus, PreferenceStatus,
    RegistrationWindowStatus, Role, RoundStage, StudentRegistrationState,
)
from app.models.identity import (
    AcademicYear, Department, Faculty, Semester, Student, User,
)
from app.schemas.academics import (
    AllocationOut, AllocationRunResult, AllocationStrategyOut, CurriculumComponentOut,
    DistributeResult, ElectiveWorkspace, FinaliseRequest, FinaliseResult,
    FinalSubjectOut, InterestTallyOut, InterestTallyRow, ManualAllocationRequest,
    MoveStudentRequest, PreferenceOut, PreferenceSubmit, RegistrationWindowIn,
    RegistrationWindowOut, RegistrationWindowUpdate, RoundChoiceSubmit,
    RoundSubjectOut, RunAllocationRequest, SectionCreate, SectionOut, SectionUpdate,
    ShortlistRequest, StudentRoundOut, SubjectIn, SubjectOut, SubjectUpdate,
    ViabilityOut, WindowOfferingLink,
)
from app.schemas.common import Message
from app.services import audit, notifications, registration, scope, sections, two_stage
from app.services.allocation import Candidate, SeatPool, available_strategies, get_strategy
from app.services.eligibility import (
    components_for_semester, offering_allowed, offering_window_open,
)
from app.services import serializers
from app.services.serializers import component_out, offering_out, section_out

router = APIRouter(prefix="/electives", tags=["electives"])

#: Elective administration is reachable either by the institution-wide
#: permission or by actually coordinating one of the elective families. The
#: department a caller may act on is narrowed per-request, not here.
_manages_electives = require_permission_or_coordination(
    P["ELECTIVE_MANAGE"],
    CoordinationDomain.OPEN_ELECTIVE,
    CoordinationDomain.CORE_ELECTIVE,
    CoordinationDomain.MOOC,
)


def _views_electives(db: DbSession, user: CurrentUser) -> User:
    """Admit anyone who manages electives, plus a Head of Department.

    The HoD reads their department's rounds and drives none of them, so they
    pass this guard and no other: every write route keeps `_manages_electives`.
    """
    if scope.hod_department(db, user) is not None:
        return user
    return _manages_electives(db, user)

def _family_domain(component_type: ComponentType) -> CoordinationDomain:
    return (CoordinationDomain.CORE_ELECTIVE
            if component_type == ComponentType.PROGRAM_CORE_ELECTIVE
            else CoordinationDomain.MOOC
            if component_type == ComponentType.MOOC
            else CoordinationDomain.OPEN_ELECTIVE)


#: How each elective family is named in a refusal.
_FAMILY_LABEL = {
    CoordinationDomain.OPEN_ELECTIVE: "Open Elective",
    CoordinationDomain.CORE_ELECTIVE: "Program Core Elective",
    CoordinationDomain.MOOC: "NPTEL / MOOC",
}


def _component_department_id(db, component: CurriculumComponent) -> int | None:
    """The department whose students this slot belongs to."""
    curriculum = db.get(Curriculum, component.curriculum_id)
    program = db.get(Program, curriculum.program_id) if curriculum else None
    return program.department_id if program else None


def _assert_manages_component(db, user: User, component: CurriculumComponent) -> None:
    """One elective family, one department — for every allocation screen.

    These routes once asked only for the coarse `electives:manage` permission.
    That failed in both directions at once: an appointed coordinator, who holds
    a scoped grant rather than the permission, was refused on their own slot,
    while anyone who did hold it could read and allocate any department's
    students. The slot decides now, the same way a registration round does.
    """
    if user.has_role(Role.SUPER_ADMIN):
        return
    domain = _family_domain(component.component_type)
    scope.assert_coordinates(
        db, user, domain, _component_department_id(db, component),
        permission=P["ELECTIVE_MANAGE"], what=_FAMILY_LABEL[domain],
    )


def _managed_component(db, user: User, component_id: int) -> CurriculumComponent:
    component = db.get(CurriculumComponent, component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")
    _assert_manages_component(db, user, component)
    return component


def _managed_offering(db, user: User, offering_id: int) -> CourseOffering:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFoundError("Course offering not found.")
    component = (db.get(CurriculumComponent, offering.curriculum_component_id)
                 if offering.curriculum_component_id else None)
    if component is None:
        # Not tied to any curriculum slot, so no coordinator's scope covers it.
        if not user.has_role(Role.SUPER_ADMIN):
            raise PermissionDeniedError(
                "This course is not part of an elective slot you coordinate."
            )
    else:
        _assert_manages_component(db, user, component)
    return offering


ELECTIVE_TYPES = (
    ComponentType.OPEN_ELECTIVE,
    ComponentType.PROGRAM_CORE_ELECTIVE,
    ComponentType.MOOC,
)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _preference_out(pref: ElectivePreference) -> PreferenceOut:
    offering = pref.course_offering
    return PreferenceOut(
        id=pref.id, curriculum_component_id=pref.curriculum_component_id,
        component_code=pref.curriculum_component.code if pref.curriculum_component else None,
        course_offering_id=pref.course_offering_id,
        course_code=offering.course.code if offering else None,
        course_title=offering.course.title if offering else None,
        preference_order=pref.preference_order, status=pref.status.value,
        submitted_at=pref.submitted_at,
    )


def _allocation_out(db, alloc: ElectiveAllocation) -> AllocationOut:
    offering = alloc.course_offering
    component = alloc.curriculum_component
    student = db.get(Student, alloc.student_id)
    return AllocationOut(
        id=alloc.id, student_id=alloc.student_id,
        student_name=student.user.full_name if student else None,
        roll_number=student.roll_number if student else None,
        division=student.division if student else None,
        section_id=alloc.section_id,
        section_name=alloc.section.name if alloc.section else None,
        curriculum_component_id=alloc.curriculum_component_id,
        component_code=component.code if component else None,
        component_title=component.title if component else None,
        course_offering_id=alloc.course_offering_id,
        course_code=offering.course.code if offering else None,
        course_title=offering.course.title if offering else None,
        status=alloc.status, allocation_round=alloc.allocation_round,
        strategy=alloc.strategy,
        preference_order_granted=alloc.preference_order_granted,
        is_manual_override=alloc.is_manual_override, allocated_at=alloc.allocated_at,
        remarks=alloc.remarks,
    )


def _eligible_offerings(db, student: Student, component: CurriculumComponent):
    offerings = list(db.scalars(
        select(CourseOffering)
        .where(CourseOffering.curriculum_component_id == component.id)
        .where(CourseOffering.status.in_(
            [OfferingStatus.OPEN, OfferingStatus.CLOSED, OfferingStatus.ALLOCATED]
        ))
    ))
    # A round decides which courses its students choose from. A course belongs
    # to one round at a time, so two cohorts can be choosing for the same slot —
    # Semester IV in their own round, Semester III in next year's — without
    # either seeing the other's list. A student no round covers sees only the
    # courses that are in none.
    window = registration.window_for(db, component, student)
    governing = (window if window is not None
                 and window.status != RegistrationWindowStatus.DRAFT else None)
    result = []
    for offering in offerings:
        if governing is not None:
            if offering.registration_window_id != governing.id:
                continue
        elif offering.registration_window_id is not None:
            continue
        if offering_allowed(db, offering, offering.course, student, component):
            result.append(offering)
    return result


# ── student-facing ────────────────────────────────────────────────────────
@router.get("/components", response_model=list[CurriculumComponentOut])
def my_elective_components(
    db: DbSession, student: CurrentStudent,
    component_type: ComponentType | None = Query(None),
    include_upcoming: bool = Query(True),
) -> list[CurriculumComponentOut]:
    """Every elective slot in this student's curriculum, with unlock state."""
    allowed = (component_type,) if component_type else ELECTIVE_TYPES
    components = [
        c for c in components_for_semester(db, student)
        if c.component_type in allowed
    ]
    if not include_upcoming:
        components = [c for c in components
                      if c.semester_number <= student.current_semester]

    allocations = {
        a.curriculum_component_id: a
        for a in db.scalars(
            select(ElectiveAllocation).where(ElectiveAllocation.student_id == student.id)
        )
    }
    pref_counts = dict(db.execute(
        select(ElectivePreference.curriculum_component_id,
               func.count(ElectivePreference.id))
        .where(ElectivePreference.student_id == student.id)
        .group_by(ElectivePreference.curriculum_component_id)
    ).all())

    out = []
    for component in components:
        # A round can open a slot before the semester the curriculum names.
        unlocked = registration.access_for(db, student, component).eligible
        allocation = allocations.get(component.id)
        if allocation:
            label = allocation.status.value.title()
        elif not unlocked:
            label = "Upcoming"
        else:
            label = _list_label(db, component, student,
                                submitted=bool(pref_counts.get(component.id)))
        offerings = _eligible_offerings(db, student, component)
        governing = registration.window_for(db, component, student)
        if governing is not None and governing.status == RegistrationWindowStatus.DRAFT:
            governing = None
        out.append(component_out(
            component, is_unlocked=unlocked, status_label=label,
            round_id=governing.id if governing else None,
            round_two_stage=governing.is_two_stage if governing else None,
            allocated_course=(
                f"{allocation.course_offering.course.code} · "
                f"{allocation.course_offering.course.title}"
                if allocation and allocation.course_offering else None
            ),
            # Subjects, not offerings: next year's run of a course is the same subject.
            offering_count=len({o.course_id for o in offerings}),
        ))
    return out


def _list_label(db, component: CurriculumComponent, student: Student, *,
                submitted: bool) -> str:
    """The state a slot's card shows, from the same rule as its workspace.

    The card used to say "Not started" whenever the student had not ranked
    anything — even while a round was open and the dashboard and notification
    said choice filling had begun, and even after they had ticked subjects in a
    two-stage round (which are not rankings). It now reads the round.
    """
    reg = registration.status_for(db, component, student)
    window = reg.window
    if window is None:
        if submitted:
            return "Preferences submitted"
        if component.semester_number < student.current_semester:
            # Past-semester slot with no allocation record — already handled
            # outside the portal (or before it existed).
            return "Completed"
        return "Choice filling open" if reg.can_submit else "Not open yet"
    two = window.is_two_stage
    stage = ("Final round" if window.stage == RoundStage.FINAL else "Interest round")
    if reg.state == StudentRegistrationState.SUBMITTED:
        return "Choice submitted" if two else "Preferences submitted"
    if reg.state == StudentRegistrationState.OPEN:
        return f"{stage} open" if two else "Choice filling open"
    if reg.state == StudentRegistrationState.NOT_OPEN:
        return "Not open yet"
    if reg.state == StudentRegistrationState.LOCKED:
        # Locked after they chose: what they need to know is that it counted.
        if reg.preference_count:
            return "Choice submitted" if two else "Preferences submitted"
        return "Choices locked"
    return "Closed"


@router.get("/components/{component_id}/workspace", response_model=ElectiveWorkspace)
def component_workspace(component_id: int, db: DbSession,
                        student: CurrentStudent) -> ElectiveWorkspace:
    """One call powering an elective screen: rules, options, my state."""
    component = db.get(CurriculumComponent, component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")

    access = registration.access_for(db, student, component)
    offerings = _eligible_offerings(db, student, component)

    my_prefs = list(db.scalars(
        select(ElectivePreference)
        .where(ElectivePreference.student_id == student.id,
               ElectivePreference.curriculum_component_id == component.id)
        .order_by(ElectivePreference.preference_order)
    ))
    pref_by_offering = {p.course_offering_id: p.preference_order for p in my_prefs}

    allocation = db.scalar(
        select(ElectiveAllocation).where(
            ElectiveAllocation.student_id == student.id,
            ElectiveAllocation.curriculum_component_id == component.id,
        )
    )
    reg = registration.status_for(db, component, student)
    closes_at = reg.closes_at or min(
        (o.registration_closes_at for o in offerings if o.registration_closes_at),
        default=None,
    )
    return ElectiveWorkspace(
        component=component_out(component, is_unlocked=access.eligible,
                                offering_count=len(offerings)),
        eligible=access.eligible, eligibility_notes=access.reasons,
        window_open=reg.can_submit, closes_at=closes_at, opens_at=reg.opens_at,
        registration_state=reg.state, registration_label=reg.label,
        registration_reason=reg.reason,
        window_title=reg.window.title if reg.window else None,
        min_preferences=reg.min_preferences,
        max_preferences=reg.max_preferences,
        offerings=[
            offering_out(o, is_open=offering_window_open(o),
                         my_preference_order=pref_by_offering.get(o.id))
            for o in offerings
        ],
        my_preferences=[_preference_out(p) for p in my_prefs],
        my_allocation=_allocation_out(db, allocation) if allocation else None,
        round=(_student_round_out(db, reg.window, student)
               if reg.window is not None and reg.window.is_two_stage
               and reg.window.status != RegistrationWindowStatus.DRAFT else None),
    )


def _student_round_out(db, window: ElectiveRegistrationWindow,
                       student: Student) -> StudentRoundOut:
    now = utcnow()
    stage = window.stage or RoundStage.INTEREST
    mine = two_stage.choices(db, window, stage, student.id)
    if window.is_open_at(now):
        can_submit, reason = True, None
    elif window.status == RegistrationWindowStatus.OPEN and window.opens_at_utc \
            and now < window.opens_at_utc:
        can_submit, reason = False, f"Opens on {registration._when(window.opens_at_utc)}."
    elif window.status in (RegistrationWindowStatus.OPEN, RegistrationWindowStatus.LOCKED):
        can_submit = False
        reason = ("The interest round has closed. The coordinator will shortlist "
                  "subjects for the final round." if stage == RoundStage.INTEREST
                  else "Choices are closed while the department finalises the electives.")
    else:
        can_submit, reason = False, "This round is closed."
    interest = ([c.course_id for c in two_stage.choices(
        db, window, RoundStage.INTEREST, student.id)] if stage == RoundStage.FINAL else [])
    slots = sorted(registration.round_components(db, window),
                   key=lambda c: (c.semester_number, c.sequence, c.code))
    return StudentRoundOut(
        id=window.id, title=window.title, stage=stage, pick_count=window.pick_count or 0,
        opens_at=window.opens_at, closes_at=window.closes_at,
        can_submit=can_submit, reason=reason,
        subjects=[RoundSubjectOut(course_id=c.id, code=c.code, title=c.title,
                                  credits=float(c.credits) if c.credits is not None else None)
                  for c in two_stage.subjects(db, window)],
        my_course_ids=[c.course_id for c in mine],
        submitted_at=max((c.submitted_at for c in mine), default=None),
        my_interest_course_ids=interest,
        slot_codes=[c.code for c in slots], slot_titles=[c.title for c in slots],
    )


@router.put("/rounds/{window_id}/choices", response_model=StudentRoundOut)
def submit_round_choices(window_id: int, payload: RoundChoiceSubmit, db: DbSession,
                         student: CurrentStudent, user: CurrentUser) -> StudentRoundOut:
    """Tick subjects in a two-stage round. Replaces earlier ticks for this stage."""
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None or window.status == RegistrationWindowStatus.DRAFT:
        raise NotFoundError("Registration round not found.")
    made = two_stage.submit_choices(db, window, student, payload.course_ids)
    stage = window.stage or RoundStage.INTEREST
    notifications.notify(
        db, user_id=user.id, type=NotificationType.REGISTRATION_CONFIRMED,
        title=f"{window.title}: "
              + ("interest recorded" if stage == RoundStage.INTEREST else "choice recorded"),
        message=f"{len(made)} subject(s) recorded. You can change them until the deadline.",
        link=_round_link(db, window),
    )
    audit.record(db, action=AuditAction.CREATE, entity_type="elective_round_choice",
                 entity_id=window.id, actor=user,
                 description=f"Ticked {len(made)} subject(s) in {window.code} ({stage.value})",
                 meta={"course_ids": payload.course_ids, "stage": stage.value})
    db.commit()
    return _student_round_out(db, window, student)


@router.post("/preferences", response_model=list[PreferenceOut])
def submit_preferences(payload: PreferenceSubmit, db: DbSession,
                       student: CurrentStudent, user: CurrentUser) -> list[PreferenceOut]:
    component = db.get(CurriculumComponent, payload.curriculum_component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")

    access = registration.access_for(db, student, component)
    if not access.eligible:
        raise BusinessRuleError(access.reasons[0])

    # The registration round decides, not the browser. A stale tab, a skewed
    # clock or a hand-written request is refused here with the real reason.
    reg = registration.assert_can_submit(db, component, student)
    if reg.window is not None and reg.window.is_two_stage:
        raise BusinessRuleError(
            "This round is chosen by ticking subjects, not by ranking courses.")

    orders = [p.preference_order for p in payload.preferences]
    if len(set(orders)) != len(orders):
        raise ValidationError("Each preference position may be used only once.")
    offering_ids = [p.course_offering_id for p in payload.preferences]
    if len(set(offering_ids)) != len(offering_ids):
        raise ValidationError("The same course cannot be chosen twice.")

    if len(payload.preferences) < reg.min_preferences:
        raise ValidationError(
            f"Select at least {reg.min_preferences} preference(s)."
        )
    if len(payload.preferences) > reg.max_preferences:
        raise ValidationError(
            f"You may submit at most {reg.max_preferences} preference(s)."
        )

    if db.scalar(select(ElectiveAllocation).where(
        ElectiveAllocation.student_id == student.id,
        ElectiveAllocation.curriculum_component_id == component.id,
        ElectiveAllocation.status.in_(
            [AllocationStatus.ALLOCATED, AllocationStatus.CONFIRMED]
        ),
    )):
        raise BusinessRuleError(
            "A seat has already been allocated for this component; preferences are locked."
        )

    valid_ids = {o.id for o in _eligible_offerings(db, student, component)}
    for item in payload.preferences:
        offering = db.get(CourseOffering, item.course_offering_id)
        if offering is None or offering.id not in valid_ids:
            raise ValidationError(
                "One of the selected courses is not available for this component."
            )
        # When the offering belongs to a round, the round has already been
        # checked above and is the authority; only unattached offerings fall
        # back to their own dates.
        if offering.registration_window_id is None and not offering_window_open(offering):
            raise BusinessRuleError(
                f"Registration for {offering.course.code} is not open."
            )

    # Replace the whole set — a preference list is submitted atomically.
    for old in db.scalars(select(ElectivePreference).where(
        ElectivePreference.student_id == student.id,
        ElectivePreference.curriculum_component_id == component.id,
    )):
        db.delete(old)
    db.flush()

    now = utcnow()
    created = []
    for item in payload.preferences:
        pref = ElectivePreference(
            student_id=student.id, curriculum_component_id=component.id,
            course_offering_id=item.course_offering_id,
            preference_order=item.preference_order,
            status=PreferenceStatus.SUBMITTED, submitted_at=now,
        )
        db.add(pref)
        created.append(pref)

    notifications.notify(
        db, user_id=user.id, type=NotificationType.REGISTRATION_CONFIRMED,
        title=f"{component.title} preferences submitted",
        message=f"{len(created)} preference(s) recorded. You will be notified once "
                "seats are allocated.",
        link=serializers.elective_path(component),
    )
    audit.record(
        db, action=AuditAction.CREATE, entity_type="elective_preference",
        entity_id=component.id, actor=user,
        description=f"Submitted {len(created)} preferences for {component.code}",
        meta={"offering_ids": offering_ids},
    )
    db.commit()
    for pref in created:
        db.refresh(pref)
    return [_preference_out(p) for p in created]


@router.delete("/preferences/{component_id}", response_model=Message)
def withdraw_preferences(component_id: int, db: DbSession, student: CurrentStudent,
                         user: CurrentUser) -> Message:
    component = db.get(CurriculumComponent, component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")
    if db.scalar(select(ElectiveAllocation).where(
        ElectiveAllocation.student_id == student.id,
        ElectiveAllocation.curriculum_component_id == component_id,
    )):
        raise BusinessRuleError("Preferences cannot be withdrawn after allocation.")
    registration.assert_can_withdraw(db, component, student)
    rows = list(db.scalars(select(ElectivePreference).where(
        ElectivePreference.student_id == student.id,
        ElectivePreference.curriculum_component_id == component_id,
    )))
    for row in rows:
        db.delete(row)
    audit.record(db, action=AuditAction.DELETE, entity_type="elective_preference",
                 entity_id=component_id, actor=user,
                 description="Withdrew elective preferences")
    db.commit()
    return Message(message=f"{len(rows)} preference(s) withdrawn.")


@router.get("/allocations/me", response_model=list[AllocationOut])
def my_allocations(db: DbSession, student: CurrentStudent) -> list[AllocationOut]:
    rows = db.scalars(
        select(ElectiveAllocation)
        .where(ElectiveAllocation.student_id == student.id)
        .order_by(ElectiveAllocation.created_at.desc())
    )
    return [_allocation_out(db, a) for a in rows]


# ── coordinator / admin ───────────────────────────────────────────────────
@router.get("/strategies", response_model=list[AllocationStrategyOut])
def strategies(_: User = Depends(_manages_electives)
               ) -> list[AllocationStrategyOut]:
    """Which allocation rules exist and which are cleared for use.

    Declared-but-unavailable rules (e.g. `merit`) are listed so coordinators can
    see what is coming, but the allocate endpoint refuses to run them.
    """
    return [
        AllocationStrategyOut(key=s.key, label=s.label, description=s.description,
                              is_available=s.is_available)
        for s in available_strategies()
    ]


@router.get("/admin/preferences", response_model=list[PreferenceOut])
def component_preferences(
    component_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> list[PreferenceOut]:
    _managed_component(db, user, component_id)
    rows = db.scalars(
        select(ElectivePreference)
        .where(ElectivePreference.curriculum_component_id == component_id)
        .order_by(ElectivePreference.student_id, ElectivePreference.preference_order)
    )
    return [_preference_out(p) for p in rows]


@router.get("/admin/allocations", response_model=list[AllocationOut])
def component_allocations(
    component_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> list[AllocationOut]:
    _managed_component(db, user, component_id)
    rows = db.scalars(
        select(ElectiveAllocation)
        .where(ElectiveAllocation.curriculum_component_id == component_id)
        .order_by(ElectiveAllocation.student_id)
    )
    return [_allocation_out(db, a) for a in rows]


@router.get("/admin/allocations/export")
def export_allocations_csv(
    component_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> Response:
    component = _managed_component(db, user, component_id)
    rows = db.scalars(
        select(ElectiveAllocation)
        .where(ElectiveAllocation.curriculum_component_id == component_id)
        .order_by(ElectiveAllocation.student_id)
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Roll Number", "Student Name", "Division", "Department",
        "Elective Code", "Elective Title", "Allocated Course Code",
        "Allocated Course Title", "Credits", "Section", "Status",
        "Preference Granted", "Strategy", "Allocated At",
    ])
    for a in rows:
        student = db.get(Student, a.student_id)
        student_user = student.user if student else None
        dept = student.department.name if student and student.department else ""
        offering = a.course_offering
        course = offering.course if offering else None
        writer.writerow([
            student.roll_number if student else "",
            student_user.full_name if student_user else "",
            student.division if student else "",
            dept,
            component.code,
            component.title,
            course.code if course else "",
            course.title if course else "",
            float(course.credits) if course else float(component.credits),
            a.section.name if a.section else "",
            a.status.value,
            a.preference_order_granted or "",
            a.strategy or "",
            a.allocated_at.isoformat() if a.allocated_at else "",
        ])

    csv_data = output.getvalue()
    code_slug = component.code.replace(" ", "_")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="allocations_{code_slug}.csv"'},
    )


def _round_to_allocate(db, user: User, component: CurriculumComponent,
                       payload: RunAllocationRequest
                       ) -> ElectiveRegistrationWindow | None:
    """The round a run is for, or None for a slot run without rounds.

    Named by the caller, or inferred when exactly one round has this slot's
    courses. With more than one the caller must say which: guessing is how
    one cohort's run reached the other cohort.
    """
    if payload.registration_window_id is not None:
        window = db.get(ElectiveRegistrationWindow, payload.registration_window_id)
        if window is None:
            raise NotFoundError("Registration round not found.")
    else:
        round_ids = sorted({
            wid for (wid,) in db.execute(
                select(CourseOffering.registration_window_id).where(
                    CourseOffering.curriculum_component_id == component.id,
                    CourseOffering.registration_window_id.is_not(None)))
        })
        if not round_ids:
            return None
        if len(round_ids) > 1:
            raise BusinessRuleError(
                f"{component.title} has courses in {len(round_ids)} registration "
                "rounds. Run allocation from Registration Rounds, for one round "
                "at a time."
            )
        window = db.get(ElectiveRegistrationWindow, round_ids[0])
    _assert_manages_window(db, user, window)
    if component.id not in {c.id for c in registration.round_components(db, window)}:
        raise ValidationError(f"{window.title} has no courses in {component.title}.")
    if not payload.dry_run and window.status != RegistrationWindowStatus.LOCKED:
        raise BusinessRuleError(
            f"{window.title} is {window.status.value.lower()}. Lock the round "
            "before allocating, so no one is still changing their choices."
        )
    return window


@router.post("/admin/allocate", response_model=AllocationRunResult)
def run_allocation(
    payload: RunAllocationRequest, db: DbSession, request_ctx=Depends(request_context),
    user: User = Depends(_manages_electives),
) -> AllocationRunResult:
    """Run a registered allocation strategy. Defaults to a dry run.

    A run is for one round. Two cohorts can be choosing for the same slot at
    once (Semester III ahead, Semester IV now), and a run over the whole slot
    used to seat and notify both. Only the round's courses, and only the
    students it covers, are considered.
    """
    component = _managed_component(db, user, payload.curriculum_component_id)

    strategy = get_strategy(payload.strategy)
    if not strategy.is_available:
        raise BusinessRuleError(
            f"The '{strategy.key}' strategy is not enabled: {strategy.description}"
        )

    window = _round_to_allocate(db, user, component, payload)
    if window is not None and window.is_two_stage:
        raise BusinessRuleError(
            f"{window.title} is a two-stage round. Finalise it from Registration "
            "Rounds instead of running an allocation strategy.")
    offerings = list(db.scalars(
        select(CourseOffering).where(
            CourseOffering.curriculum_component_id == component.id,
            (CourseOffering.registration_window_id == window.id) if window
            else CourseOffering.registration_window_id.is_(None),
        ).order_by(CourseOffering.id)
    ))
    offering_ids = {o.id for o in offerings}
    covered = ({st.id for st in registration.students_in_window(db, window)}
               if window else None)

    prefs = [
        p for p in db.scalars(
            select(ElectivePreference)
            .where(ElectivePreference.curriculum_component_id == component.id,
                   ElectivePreference.status == PreferenceStatus.SUBMITTED)
        )
        if p.course_offering_id in offering_ids
        and (covered is None or p.student_id in covered)
    ]
    already = {
        a.student_id for a in db.scalars(
            select(ElectiveAllocation).where(
                ElectiveAllocation.curriculum_component_id == component.id
            )
        )
    }
    candidates = [
        Candidate(student_id=p.student_id, course_offering_id=p.course_offering_id,
                  preference_order=p.preference_order, submitted_at=p.submitted_at)
        for p in prefs if p.student_id not in already
    ]
    non_submitters = sorted(
        (covered or set()) - {p.student_id for p in prefs} - already)
    if not prefs and not (strategy.key == "first_come_first_served" and non_submitters):
        raise BusinessRuleError("No preferences have been submitted for this component.")

    # Capacity here is the *course-wide* ceiling used by the strategy. Open
    # Electives have none (demand above one section opens another section
    # rather than turning students away), so we pass a very large pool and let
    # services/sections.py do the splitting afterwards. A seat limit set for
    # this run caps every course; first come, first served needs one for the
    # order to matter.
    UNLIMITED = 10_000
    pools = {
        o.id: SeatPool(
            course_offering_id=o.id,
            capacity=min(
                (o.section_capacity
                 if (o.section_capacity is not None
                     and not o.allow_multiple_sections)
                 else UNLIMITED),
                payload.seats_per_course or UNLIMITED,
            ),
            seats_taken=o.seats_filled,
        )
        for o in offerings
    }

    config = dict(payload.config)
    # Who did not submit, and the seed of the random draw, come from the
    # server, never from the request. The seed makes a dry run match the run.
    config["non_submitter_ids"] = non_submitters
    config["seed"] = f"{window.id if window else 0}:{component.id}"
    outcome = strategy.allocate(candidates, pools, config=config)
    preview: list[AllocationOut] = []

    if not payload.dry_run:
        now = utcnow()
        for award in outcome.awards:
            allocation = ElectiveAllocation(
                student_id=award.student_id,
                curriculum_component_id=component.id,
                course_offering_id=award.course_offering_id,
                status=(AllocationStatus.WAITLISTED if award.waitlisted
                        else AllocationStatus.ALLOCATED),
                allocation_round=1, strategy=strategy.key, score=award.score,
                preference_order_granted=award.preference_order_granted,
                allocated_by_user_id=user.id, allocated_at=now,
                remarks=award.reason or None,
            )
            db.add(allocation)
            if not award.waitlisted:
                offering = db.get(CourseOffering, award.course_offering_id)
                if offering:
                    offering.seats_filled += 1
            student = db.get(Student, award.student_id)
            # A round's students hear when the coordinator publishes the
            # results; only a slot with no round is told at run time.
            if student and window is None:
                notifications.notify(
                    db, user_id=student.user_id,
                    type=NotificationType.ELECTIVE_ALLOCATION,
                    title=f"{component.title} allocation published",
                    message=("You have been waitlisted." if award.waitlisted
                             else "A seat has been allocated to you."),
                    link=serializers.elective_path(component),
                )
        db.flush()

        # Form class sections for every course that cleared its minimum.
        for offering in offerings:
            report = sections.assess(db, offering)
            if report.runs:
                sections.distribute(db, offering, actor=user)
            else:
                outcome.notes.append(
                    f"{offering.course.code}: {report.reason}"
                )
        audit.record(
            db, action=AuditAction.ALLOCATION_RUN, entity_type="curriculum_component",
            entity_id=component.id, actor=user,
            description=(f"Ran '{strategy.key}' allocation for {component.code}"
                         + (f" in round {window.code}" if window else "")),
            meta={"registration_window_id": window.id if window else None,
                  "seats_per_course": payload.seats_per_course,
                  "non_submitters": len(non_submitters),
                  "allocated": outcome.allocated_count,
                  "waitlisted": len(outcome.awards) - outcome.allocated_count,
                  "unallocated": len(outcome.unallocated_student_ids)},
            **request_ctx,
        )
        db.commit()
        preview = [
            _allocation_out(db, a) for a in db.scalars(
                select(ElectiveAllocation)
                .where(ElectiveAllocation.curriculum_component_id == component.id,
                       ElectiveAllocation.course_offering_id.in_(offering_ids or [0]))
                .order_by(ElectiveAllocation.id)
            )
        ]
    else:
        for award in outcome.awards:
            student = db.get(Student, award.student_id)
            offering = db.get(CourseOffering, award.course_offering_id)
            preview.append(AllocationOut(
                id=0, student_id=award.student_id,
                student_name=student.user.full_name if student else None,
                roll_number=student.roll_number if student else None,
                curriculum_component_id=component.id, component_code=component.code,
                component_title=component.title,
                course_offering_id=award.course_offering_id,
                course_code=offering.course.code if offering else None,
                course_title=offering.course.title if offering else None,
                status=(AllocationStatus.WAITLISTED if award.waitlisted
                        else AllocationStatus.ALLOCATED),
                allocation_round=1, strategy=strategy.key,
                preference_order_granted=award.preference_order_granted,
                is_manual_override=False, remarks=award.reason,
            ))

    return AllocationRunResult(
        strategy=strategy.key, dry_run=payload.dry_run,
        allocated=outcome.allocated_count,
        waitlisted=len(outcome.awards) - outcome.allocated_count,
        unallocated=len(outcome.unallocated_student_ids), notes=outcome.notes,
        preview=preview,
    )


@router.post("/admin/allocations/manual", response_model=AllocationOut)
def manual_allocation(
    payload: ManualAllocationRequest, db: DbSession,
    request_ctx=Depends(request_context),
    user: User = Depends(_manages_electives),
) -> AllocationOut:
    offering = db.get(CourseOffering, payload.course_offering_id)
    student = db.get(Student, payload.student_id)
    if offering is None or student is None:
        raise NotFoundError("Student or course offering not found.")
    _managed_offering(db, user, offering.id)
    # Open Electives have no course-wide ceiling — a full section simply means
    # another section is opened, so only a single-section capped course blocks.
    if (offering.section_capacity is not None
            and not offering.allow_multiple_sections
            and offering.seats_filled >= offering.section_capacity):
        raise BusinessRuleError(
            f"{offering.course.code} is full "
            f"({offering.section_capacity} seats) and does not open extra sections."
        )

    allocation = db.scalar(select(ElectiveAllocation).where(
        ElectiveAllocation.student_id == payload.student_id,
        ElectiveAllocation.curriculum_component_id == payload.curriculum_component_id,
    ))
    previous_offering_id = allocation.course_offering_id if allocation else None
    if allocation is None:
        allocation = ElectiveAllocation(
            student_id=payload.student_id,
            curriculum_component_id=payload.curriculum_component_id,
        )
        db.add(allocation)
    elif previous_offering_id:
        old = db.get(CourseOffering, previous_offering_id)
        if old and old.seats_filled > 0:
            old.seats_filled -= 1

    allocation.course_offering_id = payload.course_offering_id
    allocation.status = AllocationStatus.ALLOCATED
    allocation.strategy = "manual"
    allocation.is_manual_override = True
    allocation.allocated_by_user_id = user.id
    allocation.allocated_at = utcnow()
    allocation.remarks = payload.remarks
    offering.seats_filled += 1

    notifications.notify(
        db, user_id=student.user_id, type=NotificationType.ELECTIVE_ALLOCATION,
        title="Elective seat assigned",
        message=f"You have been allocated {offering.course.code} · {offering.course.title}.",
        link=serializers.elective_path(offering.curriculum_component,
                                       detail=False),
    )
    audit.record(
        db, action=AuditAction.ALLOCATION_OVERRIDE, entity_type="elective_allocation",
        entity_id=allocation.id, actor=user,
        description=f"Manually allocated {offering.course.code} to {student.roll_number}",
        meta={"from_offering_id": previous_offering_id,
              "to_offering_id": payload.course_offering_id,
              "remarks": payload.remarks},
        **request_ctx,
    )
    db.commit()
    db.refresh(allocation)
    return _allocation_out(db, allocation)


# ── sections and viability ────────────────────────────────────────────────
@router.get("/admin/viability", response_model=list[ViabilityOut])
def viability(
    component_id: int, db: DbSession, use_preferences: bool = Query(True),
    user: User = Depends(_manages_electives),
) -> list[ViabilityOut]:
    """Which courses clear the minimum, and how each would be split.

    Reads first-preference demand by default so a coordinator can see the
    outcome *before* running allocation.
    """
    _managed_component(db, user, component_id)
    offerings = list(db.scalars(
        select(CourseOffering).where(
            CourseOffering.curriculum_component_id == component_id
        )
    ))
    reports = [
        sections.assess(db, offering, use_preferences=use_preferences)
        for offering in offerings
    ]
    return [
        ViabilityOut(
            offering_id=r.offering_id, course_code=r.course_code,
            course_title=r.course_title, demand=r.demand,
            min_students_to_run=r.min_students_to_run,
            section_capacity=r.section_capacity,
            allow_multiple_sections=r.allow_multiple_sections,
            runs=r.runs, shortfall=r.shortfall,
            planned_sections=r.planned_sections,
            existing_sections=r.existing_sections,
            division_breakdown=r.division_breakdown.as_rows(),
            eligible_divisions=r.eligible_divisions, reason=r.reason,
        )
        for r in sorted(reports, key=lambda r: (-r.demand, r.course_code))
    ]


@router.get("/admin/offerings/{offering_id}/sections", response_model=list[SectionOut])
def list_sections(
    offering_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> list[SectionOut]:
    offering = _managed_offering(db, user, offering_id)
    return [
        section_out(
            section,
            breakdown=sections.division_breakdown(
                db, offering_id=offering.id, section_id=section.id
            ).as_rows(),
        )
        for section in offering.sections if section.is_active
    ]


@router.post("/admin/offerings/{offering_id}/sections", response_model=SectionOut,
             status_code=201)
def create_section(
    offering_id: int, payload: SectionCreate, db: DbSession,
    user: User = Depends(_manages_electives),
) -> SectionOut:
    """Open an extra section by hand, beyond what demand alone requires."""
    offering = _managed_offering(db, user, offering_id)

    name = payload.name or sections.section_name(len(offering.sections))
    if any(s.name == name for s in offering.sections):
        raise ConflictError(f"{name} already exists for this course.")

    section = CourseSection(
        course_offering_id=offering.id, name=name,
        capacity=payload.capacity if payload.capacity is not None
        else offering.section_capacity,
        faculty_id=payload.faculty_id,
        venue=payload.venue or offering.venue,
        schedule_note=payload.schedule_note or offering.schedule_note,
    )
    db.add(section)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="course_section",
                 entity_id=section.id, actor=user,
                 description=f"Opened {name} for {offering.course.code}")
    db.commit()
    db.refresh(section)
    return section_out(section)


@router.patch("/admin/sections/{section_id}", response_model=SectionOut)
def update_section(
    section_id: int, payload: SectionUpdate, db: DbSession,
    user: User = Depends(_manages_electives),
) -> SectionOut:
    section = db.get(CourseSection, section_id)
    if section is None:
        raise NotFoundError("Section not found.")
    _managed_offering(db, user, section.course_offering_id)
    changes = payload.model_dump(exclude_unset=True)
    if ("capacity" in changes and changes["capacity"] is not None
            and changes["capacity"] < section.seats_filled):
        raise BusinessRuleError(
            f"{section.name} already holds {section.seats_filled} students; "
            "move some out before reducing the capacity."
        )
    for field, value in changes.items():
        setattr(section, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="course_section",
                 entity_id=section.id, actor=user,
                 description=f"Updated {section.name}",
                 meta={"changes": list(changes)})
    db.commit()
    db.refresh(section)
    return section_out(section)


@router.post("/admin/offerings/{offering_id}/distribute", response_model=DistributeResult)
def distribute_sections(
    offering_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> DistributeResult:
    """Create the sections the current demand needs and place students in them.

    Students already sitting in a valid section keep their place, so a
    coordinator's manual moves survive a re-run.
    """
    offering = _managed_offering(db, user, offering_id)

    report = sections.assess(db, offering)
    if not report.runs:
        raise BusinessRuleError(report.reason)

    result = sections.distribute(db, offering, actor=user)
    db.commit()
    db.refresh(offering)
    return DistributeResult(
        sections=result["sections"], assigned=result["assigned"],
        detail=[
            section_out(
                section,
                breakdown=sections.division_breakdown(
                    db, offering_id=offering.id, section_id=section.id
                ).as_rows(),
            )
            for section in offering.sections if section.is_active
        ],
    )


@router.post("/admin/sections/move", response_model=AllocationOut)
def move_between_sections(
    payload: MoveStudentRequest, db: DbSession,
    user: User = Depends(_manages_electives),
) -> AllocationOut:
    """Rebalance: move one student between sections of the same course."""
    existing = db.get(ElectiveAllocation, payload.allocation_id)
    if existing is None:
        raise NotFoundError("Allocation not found.")
    _managed_offering(db, user, existing.course_offering_id)
    allocation = sections.move_student(
        db, allocation_id=payload.allocation_id, section_id=payload.section_id,
        actor=user, reason=payload.reason,
    )
    db.commit()
    db.refresh(allocation)
    return _allocation_out(db, allocation)


# ── registration rounds ────────────────────────────────────────────────────
# A round is what makes elective registration a workflow rather than a pair of
# dates on each course. The coordinator drives it forward; the student's state
# is derived from it, and every student write is checked against it server-side.

def _window_domain(component_type: ComponentType) -> CoordinationDomain:
    return _family_domain(component_type)


def _assert_manages_window(db, user, window: ElectiveRegistrationWindow) -> None:
    """A round belongs to a department and an elective family.

    Coordinating Open Electives for ICT grants nothing over Core Electives, and
    nothing over another department — the same scope rule the rest of the portal
    uses, applied here rather than reinvented.
    """
    if user.has_role(Role.SUPER_ADMIN):
        return
    domain = _window_domain(window.component_type)
    scope.assert_coordinates(
        db, user, domain, window.department_id, permission=P["ELECTIVE_MANAGE"],
        what=_FAMILY_LABEL[domain],
    )


def _can_manage_window(db, user, window: ElectiveRegistrationWindow) -> bool:
    return user.has_role(Role.SUPER_ADMIN) or scope.coordinates(
        db, user, _window_domain(window.component_type), window.department_id)


def _assert_can_view_window(db, user, window: ElectiveRegistrationWindow) -> None:
    """Reading a round: its coordinator, or the department's Head.

    Oversight is not management. Nothing that changes a round calls this.
    """
    if _can_manage_window(db, user, window):
        return
    if window.department_id is not None and scope.oversees(db, user,
                                                           window.department_id):
        return
    raise PermissionDeniedError(
        "This registration round belongs to another department or module."
    )


def _students_of(db, window: ElectiveRegistrationWindow) -> list[int]:
    return [s.user_id for s in registration.students_in_window(db, window)]


def _round_link(db, window: ElectiveRegistrationWindow) -> str:
    components = registration.round_components(db, window)
    if len(components) == 1:
        return serializers.elective_path(components[0])
    return serializers.elective_path(
        type("Family", (), {"component_type": window.component_type, "id": 0})(),
        detail=False)


def _notify_round_open(db, window: ElectiveRegistrationWindow, *,
                       reopened: bool = False) -> int:
    """Tell every covered student that choice filling is open, and until when."""
    user_ids = _students_of(db, window)
    notifications.notify_many(
        db, user_ids=user_ids, type=NotificationType.ELECTIVE_DEADLINE,
        title=(f"{window.title}: choice filling "
               + ("has reopened" if reopened else "is open")),
        message=("Submit your ranked preferences before "
                 f"{registration._when(window.closes_at_utc)}."),
        link=_round_link(db, window),
    )
    return len(user_ids)


def _notify_deadline_changed(db, window: ElectiveRegistrationWindow) -> int:
    user_ids = _students_of(db, window)
    notifications.notify_many(
        db, user_ids=user_ids, type=NotificationType.ELECTIVE_DEADLINE,
        title=f"{window.title}: deadline changed",
        message=("Choice filling now closes on "
                 f"{registration._when(window.closes_at_utc)}."),
        link=_round_link(db, window),
    )
    return len(user_ids)


def _window_out(db, window: ElectiveRegistrationWindow,
                user: User | None = None) -> RegistrationWindowOut:
    now = registration.utcnow()
    components = registration.round_components(db, window)
    slot_semesters = {c.semester_number for c in components}
    offering_ids = [
        o.id for o in db.scalars(select(CourseOffering).where(
            CourseOffering.registration_window_id == window.id))
    ]
    eligible_count = registration.count_students_in_window(db, window)
    if window.is_two_stage:
        submitted = two_stage.submitted_count(db, window)
    else:
        submitted = db.scalar(
            select(func.count(func.distinct(ElectivePreference.student_id)))
            .where(ElectivePreference.course_offering_id.in_(offering_ids or [0]))
        ) or 0
    allocated = db.scalar(
        select(func.count(ElectiveAllocation.id)).where(
            ElectiveAllocation.course_offering_id.in_(offering_ids or [0]),
            ElectiveAllocation.status != AllocationStatus.DROPPED)
    ) or 0
    department = db.get(Department, window.department_id) if window.department_id else None
    programs = db.scalars(select(Program).where(
        Program.id.in_(window.eligible_program_ids or [0])))
    return RegistrationWindowOut(
        id=window.id, code=window.code, title=window.title,
        description=window.description, component_type=window.component_type,
        status=window.status, department_id=window.department_id,
        department_code=department.code if department else None,
        academic_year_id=window.academic_year_id, semester_id=window.semester_id,
        opens_at=window.opens_at, closes_at=window.closes_at,
        eligible_semesters=window.eligible_semesters or [],
        eligible_program_ids=window.eligible_program_ids or [],
        eligible_program_codes=[p.code for p in programs],
        eligible_divisions=window.eligible_divisions or [],
        min_preferences=window.min_preferences, max_preferences=window.max_preferences,
        locked_at=window.locked_at, allocated_at=window.allocated_at,
        published_at=window.published_at, notes=window.notes,
        offering_count=len(offering_ids),
        eligible_student_count=eligible_count,
        submitted_student_count=int(submitted), allocated_count=int(allocated),
        is_past_deadline=bool(window.closes_at_utc and now >= window.closes_at_utc),
        is_accepting=window.is_open_at(now),
        slots=[{"id": c.id, "code": c.code, "title": c.title,
                "semester_number": c.semester_number,
                "curriculum_id": c.curriculum_id} for c in components],
        slot_semester=(next(iter(slot_semesters)) if len(slot_semesters) == 1 else None),
        can_manage=bool(user and _can_manage_window(db, user, window)),
        selection_mode=window.selection_mode, stage=window.stage,
        interest_pick_count=window.interest_pick_count,
        final_pick_count=window.final_pick_count,
        min_students_to_run=window.min_students_to_run,
        section_capacity=window.section_capacity,
        interest_closed_at=window.interest_closed_at,
    )


@router.get("/admin/slots")
def round_slots(
    db: DbSession, user: User = Depends(_manages_electives),
) -> list[dict]:
    """The curriculum slots the caller may open a round for, with the courses
    on offer for each.

    Narrowed twice, like everything else here: to the elective families the
    caller coordinates, and to the departments they coordinate them for. So the
    Open Elective coordinator for ICT is offered ICT's Open Elective slots and
    nothing else — the form cannot even propose a round they would be refused.
    """
    rows = db.execute(
        select(CurriculumComponent, Curriculum, Program)
        .join(Curriculum, Curriculum.id == CurriculumComponent.curriculum_id)
        .join(Program, Program.id == Curriculum.program_id)
        .where(CurriculumComponent.component_type.in_(
            [ComponentType.OPEN_ELECTIVE, ComponentType.PROGRAM_CORE_ELECTIVE]),
            Curriculum.status == CurriculumStatus.PUBLISHED)
        .order_by(Program.code, Curriculum.effective_from_year.desc(),
                  CurriculumComponent.semester_number, CurriculumComponent.sequence)
    ).all()

    divisions: dict[int, list[str]] = {}
    # The same course is offered again each year, so the form says which year,
    # and whether students already hold seats in it.
    year_of = {sid: label for sid, label in db.execute(
        select(Semester.id, AcademicYear.label)
        .join(AcademicYear, AcademicYear.id == Semester.academic_year_id))}
    seats_in = {oid: n for oid, n in db.execute(
        select(ElectiveAllocation.course_offering_id, func.count(ElectiveAllocation.id))
        .where(ElectiveAllocation.status != AllocationStatus.DROPPED)
        .group_by(ElectiveAllocation.course_offering_id))}
    out = []
    for component, curriculum, program in rows:
        if not (user.has_role(Role.SUPER_ADMIN) or scope.coordinates(
                db, user, _window_domain(component.component_type),
                program.department_id)):
            continue
        if program.id not in divisions:
            divisions[program.id] = sorted({
                name for (name,) in db.execute(
                    select(ProgramDivision.name)
                    .where(ProgramDivision.program_id == program.id).distinct())
            })
        offerings = list(db.scalars(
            select(CourseOffering)
            .where(CourseOffering.curriculum_component_id == component.id)
            .order_by(CourseOffering.id)
        ))
        out.append({
            "component_id": component.id, "code": component.code,
            "title": component.title,
            "component_type": component.component_type.value,
            "semester_number": component.semester_number,
            "scope_label": component.scope_label,
            "credits": float(component.credits),
            "curriculum_id": curriculum.id, "curriculum_version": curriculum.version,
            "program_id": program.id, "program_code": program.code,
            "program_name": program.name, "department_id": program.department_id,
            # Programme data, never a fixed A-D.
            "divisions": divisions[program.id],
            "offerings": [
                {"id": o.id, "course_code": o.course.code,
                 "course_title": o.course.title,
                 "department_code": (o.course.department.code
                                     if o.course.department else None),
                 "registration_window_id": o.registration_window_id,
                 "academic_year": year_of.get(o.semester_id),
                 "seats_taken": int(seats_in.get(o.id, 0))}
                for o in offerings
            ],
        })
    return out


@router.get("/admin/windows", response_model=list[RegistrationWindowOut])
def list_windows(
    db: DbSession, component_type: ComponentType | None = Query(None),
    status: RegistrationWindowStatus | None = Query(None),
    user: User = Depends(_views_electives),
) -> list[RegistrationWindowOut]:
    """Rounds the caller may see: the ones they coordinate, and for a Head of
    Department every round of their department (read-only)."""
    stmt = select(ElectiveRegistrationWindow).order_by(
        ElectiveRegistrationWindow.opens_at.desc().nullslast(),
        ElectiveRegistrationWindow.code,
    )
    if component_type:
        stmt = stmt.where(ElectiveRegistrationWindow.component_type == component_type)
    if status:
        stmt = stmt.where(ElectiveRegistrationWindow.status == status)
    windows = list(db.scalars(stmt))
    if not user.has_role(Role.SUPER_ADMIN):
        visible = []
        for window in windows:
            if (scope.coordinates(db, user, _window_domain(window.component_type),
                                  window.department_id)
                    or (window.department_id is not None
                        and scope.oversees(db, user, window.department_id))):
                visible.append(window)
        windows = visible
    return [_window_out(db, w, user) for w in windows]


@router.post("/admin/windows", response_model=RegistrationWindowOut, status_code=201)
def create_window(
    payload: RegistrationWindowIn, db: DbSession,
    user: User = Depends(_manages_electives),
) -> RegistrationWindowOut:
    if db.scalar(select(ElectiveRegistrationWindow).where(
            ElectiveRegistrationWindow.code == payload.code)):
        raise BusinessRuleError(f"A round with code {payload.code} already exists.")
    if (payload.opens_at and payload.closes_at
            and payload.closes_at <= payload.opens_at):
        raise ValidationError("The closing time must be after the opening time.")
    if (payload.min_preferences and payload.max_preferences
            and payload.min_preferences > payload.max_preferences):
        raise ValidationError(
            "The minimum number of preferences cannot exceed the maximum."
        )
    window = ElectiveRegistrationWindow(**payload.model_dump(),
                                        status=RegistrationWindowStatus.DRAFT)
    if window.is_two_stage:
        window.stage = RoundStage.INTEREST
    _assert_manages_window(db, user, window)
    registration.validate_round(db, window)
    db.add(window)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"Registration round {window.code} created")
    db.commit()
    return _window_out(db, window, user)


@router.patch("/admin/windows/{window_id}", response_model=RegistrationWindowOut)
def update_window(
    window_id: int, payload: RegistrationWindowUpdate, db: DbSession,
    user: User = Depends(_manages_electives),
) -> RegistrationWindowOut:
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    _assert_manages_window(db, user, window)
    if window.status in (RegistrationWindowStatus.ALLOCATED,
                         RegistrationWindowStatus.PUBLISHED,
                         RegistrationWindowStatus.CLOSED):
        raise BusinessRuleError(
            f"This round is {window.status.value.lower()}; its rules can no longer "
            "be changed. Students have already been allocated against them."
        )
    changes = payload.model_dump(exclude_unset=True)
    if ("selection_mode" in changes and changes["selection_mode"] is not None
            and changes["selection_mode"] != window.selection_mode
            and window.status != RegistrationWindowStatus.DRAFT):
        raise BusinessRuleError(
            "How students choose can only be changed while the round is a draft.")
    if changes.get("selection_mode") is None:
        changes.pop("selection_mode", None)
    previous_closes = window.closes_at_utc
    for field, value in changes.items():
        setattr(window, field, value)
    if window.is_two_stage and window.stage is None:
        window.stage = RoundStage.INTEREST
    elif not window.is_two_stage:
        window.stage = None
    two_stage.apply_course_rules(db, window)
    if window.opens_at and window.closes_at and window.closes_at_utc <= window.opens_at_utc:
        raise ValidationError("The closing time must be after the opening time.")
    if (window.min_preferences and window.max_preferences
            and window.min_preferences > window.max_preferences):
        raise ValidationError(
            "The minimum number of preferences cannot exceed the maximum."
        )
    deadline_moved = ("closes_at" in changes and window.closes_at_utc != previous_closes)
    is_live = window.status == RegistrationWindowStatus.OPEN
    if deadline_moved and is_live and (
            window.closes_at_utc is None
            or window.closes_at_utc <= registration.utcnow()):
        # Closing a live round is a decision with its own button (Lock), and
        # its own audit entry. A deadline quietly moved into the past is not it.
        raise ValidationError(
            "The new deadline must be in the future. To stop choice filling "
            "now, lock the round instead."
        )
    registration.validate_round(db, window)

    notified = 0
    if deadline_moved and is_live:
        notified = _notify_deadline_changed(db, window)
    audit.record(db, action=AuditAction.UPDATE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"Registration round {window.code} updated",
                 meta={**payload.model_dump(exclude_unset=True, mode="json"),
                       "previous_closes_at": (previous_closes.isoformat()
                                              if previous_closes else None),
                       "notified": notified})
    db.commit()
    return _window_out(db, window, user)


@router.post("/admin/windows/{window_id}/offerings", response_model=RegistrationWindowOut)
def set_window_offerings(
    window_id: int, payload: WindowOfferingLink, db: DbSession,
    user: User = Depends(_manages_electives),
) -> RegistrationWindowOut:
    """Set exactly which courses this round covers."""
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    _assert_manages_window(db, user, window)
    if window.status != RegistrationWindowStatus.DRAFT:
        raise BusinessRuleError(
            "Courses can only be attached while the round is still a draft."
        )
    for offering in db.scalars(select(CourseOffering).where(
            CourseOffering.registration_window_id == window.id)):
        offering.registration_window_id = None
    for offering_id in payload.offering_ids:
        offering = db.get(CourseOffering, offering_id)
        if offering is None:
            raise NotFoundError(f"Course offering {offering_id} not found.")
        if offering.registration_window_id not in (None, window.id):
            # Attaching it here would silently pull it out of the other round —
            # and out from under the students already choosing in it.
            other = db.get(ElectiveRegistrationWindow, offering.registration_window_id)
            raise BusinessRuleError(
                f"{offering.course.code} is already part of the round "
                f"“{other.title}”. A course belongs to one round at a time."
            )
        offering.registration_window_id = window.id
    db.flush()
    two_stage.apply_course_rules(db, window)
    registration.validate_round(db, window)
    audit.record(db, action=AuditAction.UPDATE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"{len(payload.offering_ids)} course(s) attached to "
                             f"{window.code}")
    db.commit()
    return _window_out(db, window, user)


@router.delete("/admin/windows/{window_id}", response_model=Message)
def delete_window(
    window_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> Message:
    """Delete a round that has not been allocated yet.

    For a coordinator who opened a round by mistake, or a demo that needs its
    courses back: they return to no round, and any choices filled are removed.
    """
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    _assert_manages_window(db, user, window)
    title, code, status = window.title, window.code, window.status
    link = _round_link(db, window)

    outcome = registration.delete_round(db, window)
    if outcome.told_user_ids:
        notifications.notify_many(
            db, user_ids=outcome.told_user_ids, type=NotificationType.ELECTIVE_DEADLINE,
            title=f"{title}: round withdrawn",
            message=("The coordinator has withdrawn this registration round. "
                     "Any choices you filled in it have been removed; you will be "
                     "told when a new round opens."),
            link=link,
        )
    audit.record(db, action=AuditAction.DELETE, entity_type="registration_window",
                 entity_id=window_id, actor=user,
                 description=f"Deleted registration round {code} ({status.value})",
                 meta={"courses_released": outcome.courses_released,
                       "preferences_removed": outcome.preferences_removed,
                       "students_with_choices": outcome.students_with_choices,
                       "notified": len(outcome.told_user_ids)})
    db.commit()
    return Message(message=(
        f"{title} deleted. {outcome.courses_released} course(s) are free for a new "
        f"round; the choices of {outcome.students_with_choices} student(s) were "
        "removed."))


@router.post("/admin/windows/{window_id}/status", response_model=RegistrationWindowOut)
def move_window(
    window_id: int, target: RegistrationWindowStatus, db: DbSession,
    user: User = Depends(_manages_electives),
) -> RegistrationWindowOut:
    """Drive the round forward. Publishing notifies every allocated student."""
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    _assert_manages_window(db, user, window)

    previous = window.status
    if window.is_two_stage and target == RegistrationWindowStatus.ALLOCATED:
        raise BusinessRuleError(
            "A two-stage round is allocated by finalising it, which seats every student.")
    if window.is_two_stage and target == RegistrationWindowStatus.LOCKED \
            and window.stage == RoundStage.INTEREST:
        window.interest_closed_at = utcnow()
    going_live = (target == RegistrationWindowStatus.OPEN
                  and previous in (RegistrationWindowStatus.DRAFT,
                                   RegistrationWindowStatus.LOCKED))
    if going_live:
        # The last point a mistake can be caught before students are told.
        registration.validate_round(db, window, opening=True)

    registration.transition(window, target)

    published = 0
    if target == RegistrationWindowStatus.PUBLISHED:
        published = _notify_allocation_published(db, window)
    elif going_live:
        published = _notify_round_open(
            db, window, reopened=previous == RegistrationWindowStatus.LOCKED)

    audit.record(db, action=AuditAction.STATUS_CHANGE,
                 entity_type="registration_window", entity_id=window.id, actor=user,
                 description=f"{window.code}: {previous.value} → {target.value}",
                 meta={"notified": published})
    db.commit()
    return _window_out(db, window, user)


def _notify_allocation_published(db, window: ElectiveRegistrationWindow) -> int:
    """Tell every student in the round what happened to their preferences.

    Students who were allocated a seat and students who were not both hear back
    — silence after a deadline is its own kind of failure.
    """
    offering_ids = [
        o.id for o in db.scalars(select(CourseOffering).where(
            CourseOffering.registration_window_id == window.id))
    ]
    if not offering_ids:
        return 0
    allocations: dict[int, list[ElectiveAllocation]] = {}
    for a in db.scalars(select(ElectiveAllocation).where(
            ElectiveAllocation.course_offering_id.in_(offering_ids),
            ElectiveAllocation.status != AllocationStatus.DROPPED)
            .order_by(ElectiveAllocation.id)):
        allocations.setdefault(a.student_id, []).append(a)
    applicants = {
        row for (row,) in db.execute(
            select(ElectivePreference.student_id).where(
                ElectivePreference.course_offering_id.in_(offering_ids)).distinct())
    }
    if window.is_two_stage:
        # Everyone the round covered hears, chooser or not.
        applicants |= {s.id for s in registration.students_in_window(db, window)}
    sent = 0
    for student_id in applicants | set(allocations):
        student = db.get(Student, student_id)
        if student is None:
            continue
        seats = [a for a in allocations.get(student_id, []) if a.course_offering]
        if seats:
            def describe(a: ElectiveAllocation) -> str:
                course = a.course_offering.course
                section = a.section.name if a.section else None
                return f"{course.code} — {course.title}" + (f" ({section})" if section else "")
            message = "You have been allocated " + "; ".join(describe(a) for a in seats) + "."
        else:
            message = ("No seat could be allocated from your preferences. "
                       "Contact the coordinator for the next step.")
        notifications.notify(
            db, user_id=student.user_id,
            type=NotificationType.ELECTIVE_ALLOCATION,
            title=f"{window.title} — result published",
            message=message, link=_round_link(db, window),
        )
        sent += 1
    return sent


def _two_stage_window(db, window_id: int) -> ElectiveRegistrationWindow:
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    if not window.is_two_stage:
        raise BusinessRuleError("This round is not a two-stage round.")
    return window


@router.get("/admin/windows/{window_id}/interest", response_model=InterestTallyOut)
def interest_results(window_id: int, db: DbSession,
                     user: User = Depends(_views_electives)) -> InterestTallyOut:
    """The interest round's votes, most first. For the coordinator and the HoD."""
    window = _two_stage_window(db, window_id)
    _assert_can_view_window(db, user, window)
    in_round = {c.id for c in two_stage.subjects(db, window)}
    return InterestTallyOut(
        stage=window.stage or RoundStage.INTEREST,
        voters=two_stage.submitted_count(db, window, RoundStage.INTEREST),
        eligible_student_count=registration.count_students_in_window(db, window),
        interest_pick_count=window.interest_pick_count,
        slot_count=len(registration.round_components(db, window)),
        subjects=[InterestTallyRow(course_id=t.course.id, code=t.course.code,
                                   title=t.course.title, votes=t.votes,
                                   in_round=t.course.id in in_round)
                  for t in two_stage.interest_tally(db, window)],
    )


@router.post("/admin/windows/{window_id}/shortlist", response_model=RegistrationWindowOut)
def shortlist_round(window_id: int, payload: ShortlistRequest, db: DbSession,
                    user: User = Depends(_manages_electives)) -> RegistrationWindowOut:
    """Keep the chosen subjects and open the final round to the same students."""
    window = _two_stage_window(db, window_id)
    _assert_manages_window(db, user, window)
    dropped = two_stage.start_final(
        db, window, keep_course_ids=payload.course_ids,
        final_pick_count=payload.final_pick_count,
        opens_at=payload.opens_at, closes_at=payload.closes_at)
    registration.validate_round(db, window, opening=True)
    kept = ", ".join(c.code for c in two_stage.subjects(db, window))
    notified = _students_of(db, window)
    notifications.notify_many(
        db, user_ids=notified, type=NotificationType.ELECTIVE_DEADLINE,
        title=f"{window.title}: final round is open",
        message=(f"Choose {window.final_pick_count} of the shortlisted subjects ({kept}) "
                 f"before {registration._when(window.closes_at_utc)}."),
        link=_round_link(db, window),
    )
    audit.record(db, action=AuditAction.STATUS_CHANGE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"{window.code}: shortlisted {len(payload.course_ids)} subject(s), "
                             "final round opened",
                 meta={"kept_course_ids": payload.course_ids,
                       "dropped": [c.code for c in dropped],
                       "final_pick_count": payload.final_pick_count,
                       "notified": len(notified)})
    db.commit()
    return _window_out(db, window, user)


@router.post("/admin/windows/{window_id}/finalise", response_model=FinaliseResult)
def finalise_round(window_id: int, payload: FinaliseRequest, db: DbSession,
                   request_ctx=Depends(request_context),
                   user: User = Depends(_manages_electives)) -> FinaliseResult:
    """Decide which subjects run and seat every student. Dry run by default."""
    window = _two_stage_window(db, window_id)
    _assert_manages_window(db, user, window)
    if not payload.dry_run and window.status != RegistrationWindowStatus.LOCKED:
        raise BusinessRuleError(
            f"{window.title} is {window.status.value.lower()}. Lock the final round "
            "before finalising, so no one is still changing their choice.")
    plan = two_stage.plan_final(db, window, minimum=payload.min_students_to_run,
                                run_course_ids=payload.run_course_ids)
    written = 0
    if not payload.dry_run:
        if not plan.placements:
            raise BusinessRuleError(plan.notes[0] if plan.notes
                                    else "Nobody could be seated from this round.")
        written = two_stage.apply_final(db, window, plan, actor_user_id=user.id)
        if payload.min_students_to_run:
            window.min_students_to_run = payload.min_students_to_run
        registration.transition(window, RegistrationWindowStatus.ALLOCATED)
        audit.record(db, action=AuditAction.ALLOCATION_RUN,
                     entity_type="registration_window", entity_id=window.id, actor=user,
                     description=f"Finalised {window.code}: {written} seat(s)",
                     meta={"minimum": plan.minimum,
                           "running": [r.course.code for r in plan.subjects if r.runs],
                           "withdrawn": [r.course.code for r in plan.subjects if not r.runs],
                           "unplaced": len(plan.unplaced_student_ids)},
                     **request_ctx)
        db.commit()
    return FinaliseResult(
        dry_run=payload.dry_run, minimum=plan.minimum, pick_count=plan.pick_count,
        subjects=[FinalSubjectOut(course_id=r.course.id, code=r.course.code,
                                  title=r.course.title, demand=r.demand, runs=r.runs,
                                  seated=r.seated)
                  for r in sorted(plan.subjects, key=lambda r: (-r.demand, r.course.code))],
        students_placed=len({p.student_id for p in plan.placements}),
        by_choice=plan.count(two_stage.REASON_CHOSEN),
        replaced_withdrawn=plan.count(two_stage.REASON_WITHDRAWN),
        placed_no_submission=plan.count(two_stage.REASON_NO_CHOICE),
        unplaced=len(plan.unplaced_student_ids), seats_written=written, notes=plan.notes,
    )


# ── subjects: the coordinator adds, edits and removes them ────────────────
def _subject_out(offering: CourseOffering) -> SubjectOut:
    c = offering.course
    return SubjectOut(offering_id=offering.id, course_id=c.id, code=c.code, title=c.title,
                      credits=float(c.credits) if c.credits is not None else None,
                      description=c.description,
                      component_id=offering.curriculum_component_id,
                      registration_window_id=offering.registration_window_id)


def _assert_subject_editable(db, offering: CourseOffering) -> None:
    if offering.registration_window_id is None:
        return
    window = db.get(ElectiveRegistrationWindow, offering.registration_window_id)
    if window and window.status in (RegistrationWindowStatus.ALLOCATED,
                                    RegistrationWindowStatus.PUBLISHED,
                                    RegistrationWindowStatus.CLOSED):
        raise BusinessRuleError(
            f"{offering.course.code} has been allocated in “{window.title}”, so it can no "
            "longer be changed.")


@router.post("/admin/slots/{component_id}/subjects", response_model=SubjectOut,
             status_code=201)
def add_subject(component_id: int, payload: SubjectIn, db: DbSession,
                user: User = Depends(_manages_electives)) -> SubjectOut:
    """Offer a subject in this slot — a new course, or one already in the catalogue."""
    component = _managed_component(db, user, component_id)
    code = payload.code.strip().upper()
    course = db.scalar(select(Course).where(func.upper(Course.code) == code))
    if course is None:
        course = Course(code=code, title=payload.title.strip(), credits=payload.credits,
                        description=payload.description,
                        department_id=_component_department_id(db, component))
        db.add(course)
        db.flush()
    siblings = list(db.scalars(select(CourseOffering).where(
        CourseOffering.curriculum_component_id == component.id)
        .order_by(CourseOffering.id.desc())))
    template = next((o for o in siblings if o.registration_window_id is None),
                    siblings[0] if siblings else None)
    semester_id = template.semester_id if template else None
    if semester_id is None:
        semester_id = db.scalar(select(Semester.id).order_by(Semester.id.desc()))
    if semester_id is None:
        raise BusinessRuleError("No academic semester exists to offer the subject in.")
    if db.scalar(select(CourseOffering).where(
            CourseOffering.course_id == course.id,
            CourseOffering.semester_id == semester_id,
            CourseOffering.curriculum_component_id == component.id)):
        raise ConflictError(f"{course.code} is already offered in {component.title}.")
    offering = CourseOffering(
        course_id=course.id, semester_id=semester_id, curriculum_component_id=component.id,
        elective_type_id=template.elective_type_id if template else None,
        coordinator_faculty_id=template.coordinator_faculty_id if template else None,
        min_students_to_run=template.min_students_to_run if template else 40,
        section_capacity=template.section_capacity if template else None,
        allow_multiple_sections=template.allow_multiple_sections if template else False,
        eligible_divisions=list(template.eligible_divisions or []) if template else [],
        status=template.status if template else OfferingStatus.OPEN,
        eligibility=dict(template.eligibility or {}) if template else {},
    )
    db.add(offering)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="course_offering",
                 entity_id=offering.id, actor=user,
                 description=f"Added {course.code} to {component.code}")
    db.commit()
    db.refresh(offering)
    return _subject_out(offering)


@router.patch("/admin/subjects/{offering_id}", response_model=SubjectOut)
def edit_subject(offering_id: int, payload: SubjectUpdate, db: DbSession,
                 user: User = Depends(_manages_electives)) -> SubjectOut:
    """Edit a subject's code, name or credits. The course changes everywhere it
    is offered — that is what the department asked for."""
    offering = _managed_offering(db, user, offering_id)
    _assert_subject_editable(db, offering)
    course = offering.course
    changes = payload.model_dump(exclude_unset=True)
    before = {"code": course.code, "title": course.title, "credits": float(course.credits)}
    if changes.get("code"):
        code = changes["code"].strip().upper()
        clash = db.scalar(select(Course).where(func.upper(Course.code) == code,
                                               Course.id != course.id))
        if clash:
            raise ConflictError(f"Another course already uses the code {code}.")
        course.code = code
    if changes.get("title"):
        course.title = changes["title"].strip()
    if changes.get("credits") is not None:
        course.credits = changes["credits"]
    if "description" in changes:
        course.description = changes["description"]
    audit.record(db, action=AuditAction.UPDATE, entity_type="course", entity_id=course.id,
                 actor=user, description=f"Edited subject {course.code}",
                 meta={"before": before, "changes": changes})
    db.commit()
    db.refresh(offering)
    return _subject_out(offering)


@router.delete("/admin/subjects/{offering_id}", response_model=Message)
def remove_subject(offering_id: int, db: DbSession,
                   user: User = Depends(_manages_electives)) -> Message:
    """Take a subject out of this slot. The course stays in the catalogue."""
    offering = _managed_offering(db, user, offering_id)
    _assert_subject_editable(db, offering)
    if db.scalar(select(func.count(ElectiveAllocation.id)).where(
            ElectiveAllocation.course_offering_id == offering.id)):
        raise BusinessRuleError(
            f"Students hold seats in {offering.course.code}, so it cannot be removed.")
    if offering.registration_window_id is not None:
        window = db.get(ElectiveRegistrationWindow, offering.registration_window_id)
        if window and window.status != RegistrationWindowStatus.DRAFT:
            raise BusinessRuleError(
                f"{offering.course.code} is in the live round “{window.title}”. Remove it "
                "while the round is a draft, or shortlist it out of a two-stage round.")
    code = offering.course.code
    for pref in db.scalars(select(ElectivePreference).where(
            ElectivePreference.course_offering_id == offering.id)):
        db.delete(pref)
    db.delete(offering)
    audit.record(db, action=AuditAction.DELETE, entity_type="course_offering",
                 entity_id=offering_id, actor=user, description=f"Removed {code} from its slot")
    db.commit()
    return Message(message=f"{code} removed from the slot.")


@router.get("/admin/windows/{window_id}", response_model=RegistrationWindowOut)
def get_window(
    window_id: int, db: DbSession,
    user: User = Depends(_views_electives),
) -> RegistrationWindowOut:
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    _assert_can_view_window(db, user, window)
    return _window_out(db, window, user)
