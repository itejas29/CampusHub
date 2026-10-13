"""Open Electives, Program Core Electives and the allocation entry point.

The same routes serve every elective family — which components a student sees
comes from the curriculum, never from a hard-coded list.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import (
    CurrentStudent, CurrentUser, DbSession, require_permission,
    require_permission_or_coordination, request_context,
)
from app.core.errors import (
    BusinessRuleError, ConflictError, NotFoundError, ValidationError,
)
from app.core.rbac import P
from app.models.academics import (
    Course, CourseOffering, CourseSection, CurriculumComponent, ElectiveAllocation,
    ElectivePreference, ElectiveRegistrationWindow, Program,
)
from app.models.enums import (
    AllocationStatus, AuditAction, ComponentType, CoordinationDomain,
    NotificationType, OfferingStatus, PreferenceStatus, RegistrationWindowStatus, Role,
)
from app.models.identity import Department, Faculty, Student, User
from app.schemas.academics import (
    AllocationOut, AllocationRunResult, AllocationStrategyOut, CurriculumComponentOut,
    DistributeResult, ElectiveWorkspace, ManualAllocationRequest, MoveStudentRequest,
    PreferenceOut, PreferenceSubmit, RegistrationWindowIn, RegistrationWindowOut,
    RegistrationWindowUpdate, RunAllocationRequest, SectionCreate, SectionOut,
    SectionUpdate, ViabilityOut, WindowOfferingLink,
)
from app.schemas.common import Message
from app.services import audit, notifications, registration, scope, sections
from app.services.allocation import Candidate, SeatPool, available_strategies, get_strategy
from app.services.eligibility import (
    components_for_semester, offering_allowed, offering_window_open,
    student_can_access_component,
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
    result = []
    for offering in offerings:
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
        unlocked = component.semester_number <= student.current_semester
        allocation = allocations.get(component.id)
        if allocation:
            label = allocation.status.value.title()
        elif not unlocked:
            label = "Upcoming"
        elif pref_counts.get(component.id):
            label = "Preferences submitted"
        elif component.semester_number < student.current_semester:
            # Past-semester slot with no allocation record — already handled
            # outside the portal (or before it existed).
            label = "Completed"
        else:
            label = "Not started"
        offerings = _eligible_offerings(db, student, component)
        out.append(component_out(
            component, is_unlocked=unlocked, status_label=label,
            allocated_course=(
                f"{allocation.course_offering.course.code} · "
                f"{allocation.course_offering.course.title}"
                if allocation and allocation.course_offering else None
            ),
            offering_count=len(offerings),
        ))
    return out


@router.get("/components/{component_id}/workspace", response_model=ElectiveWorkspace)
def component_workspace(component_id: int, db: DbSession,
                        student: CurrentStudent) -> ElectiveWorkspace:
    """One call powering an elective screen: rules, options, my state."""
    component = db.get(CurriculumComponent, component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")

    access = student_can_access_component(student, component)
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
    )


@router.post("/preferences", response_model=list[PreferenceOut])
def submit_preferences(payload: PreferenceSubmit, db: DbSession,
                       student: CurrentStudent, user: CurrentUser) -> list[PreferenceOut]:
    component = db.get(CurriculumComponent, payload.curriculum_component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")

    access = student_can_access_component(student, component)
    if not access.eligible:
        raise BusinessRuleError(access.reasons[0])

    # The registration round decides, not the browser. A stale tab, a skewed
    # clock or a hand-written request is refused here with the real reason.
    reg = registration.assert_can_submit(db, component, student)

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
def strategies(_: User = Depends(require_permission(P["ELECTIVE_MANAGE"]))
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
    _: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> list[PreferenceOut]:
    rows = db.scalars(
        select(ElectivePreference)
        .where(ElectivePreference.curriculum_component_id == component_id)
        .order_by(ElectivePreference.student_id, ElectivePreference.preference_order)
    )
    return [_preference_out(p) for p in rows]


@router.get("/admin/allocations", response_model=list[AllocationOut])
def component_allocations(
    component_id: int, db: DbSession,
    _: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> list[AllocationOut]:
    rows = db.scalars(
        select(ElectiveAllocation)
        .where(ElectiveAllocation.curriculum_component_id == component_id)
        .order_by(ElectiveAllocation.student_id)
    )
    return [_allocation_out(db, a) for a in rows]


@router.post("/admin/allocate", response_model=AllocationRunResult)
def run_allocation(
    payload: RunAllocationRequest, db: DbSession, request_ctx=Depends(request_context),
    user: User = Depends(require_permission(P["ELECTIVE_ALLOCATE"])),
) -> AllocationRunResult:
    """Run a registered allocation strategy. Defaults to a dry run."""
    component = db.get(CurriculumComponent, payload.curriculum_component_id)
    if component is None:
        raise NotFoundError("That curriculum component does not exist.")

    strategy = get_strategy(payload.strategy)
    if not strategy.is_available:
        raise BusinessRuleError(
            f"The '{strategy.key}' strategy is not enabled: {strategy.description}"
        )

    prefs = list(db.scalars(
        select(ElectivePreference)
        .where(ElectivePreference.curriculum_component_id == component.id,
               ElectivePreference.status == PreferenceStatus.SUBMITTED)
    ))
    if not prefs:
        raise BusinessRuleError("No preferences have been submitted for this component.")

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
    offerings = list(db.scalars(
        select(CourseOffering).where(
            CourseOffering.curriculum_component_id == component.id
        )
    ))
    # Capacity here is the *course-wide* ceiling used by the strategy. Open
    # Electives have none — demand above one section opens another section
    # rather than turning students away — so we pass a very large pool and let
    # services/sections.py do the splitting afterwards.
    UNLIMITED = 10_000
    pools = {
        o.id: SeatPool(
            course_offering_id=o.id,
            capacity=(o.section_capacity
                      if (o.section_capacity is not None
                          and not o.allow_multiple_sections)
                      else UNLIMITED),
            seats_taken=o.seats_filled,
        )
        for o in offerings
    }

    outcome = strategy.allocate(candidates, pools, config=payload.config)
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
            )
            db.add(allocation)
            if not award.waitlisted:
                offering = db.get(CourseOffering, award.course_offering_id)
                if offering:
                    offering.seats_filled += 1
            student = db.get(Student, award.student_id)
            if student:
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
            description=f"Ran '{strategy.key}' allocation for {component.code}",
            meta={"allocated": outcome.allocated_count,
                  "waitlisted": len(outcome.awards) - outcome.allocated_count,
                  "unallocated": len(outcome.unallocated_student_ids)},
            **request_ctx,
        )
        db.commit()
        preview = [
            _allocation_out(db, a) for a in db.scalars(
                select(ElectiveAllocation)
                .where(ElectiveAllocation.curriculum_component_id == component.id)
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
    user: User = Depends(require_permission(P["ELECTIVE_ALLOCATE"])),
) -> AllocationOut:
    offering = db.get(CourseOffering, payload.course_offering_id)
    student = db.get(Student, payload.student_id)
    if offering is None or student is None:
        raise NotFoundError("Student or course offering not found.")
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
    _: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> list[ViabilityOut]:
    """Which courses clear the minimum, and how each would be split.

    Reads first-preference demand by default so a coordinator can see the
    outcome *before* running allocation.
    """
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
    _: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> list[SectionOut]:
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFoundError("Course offering not found.")
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
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> SectionOut:
    """Open an extra section by hand, beyond what demand alone requires."""
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFoundError("Course offering not found.")

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
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> SectionOut:
    section = db.get(CourseSection, section_id)
    if section is None:
        raise NotFoundError("Section not found.")
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
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> DistributeResult:
    """Create the sections the current demand needs and place students in them.

    Students already sitting in a valid section keep their place, so a
    coordinator's manual moves survive a re-run.
    """
    offering = db.get(CourseOffering, offering_id)
    if offering is None:
        raise NotFoundError("Course offering not found.")

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
    user: User = Depends(require_permission(P["ELECTIVE_MANAGE"])),
) -> AllocationOut:
    """Rebalance: move one student between sections of the same course."""
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
    return (CoordinationDomain.CORE_ELECTIVE
            if component_type == ComponentType.PROGRAM_CORE_ELECTIVE
            else CoordinationDomain.MOOC
            if component_type == ComponentType.MOOC
            else CoordinationDomain.OPEN_ELECTIVE)


def _assert_manages_window(db, user, window: ElectiveRegistrationWindow) -> None:
    """A round belongs to a department and an elective family.

    Coordinating Open Electives for ICT grants nothing over Core Electives, and
    nothing over another department — the same scope rule the rest of the portal
    uses, applied here rather than reinvented.
    """
    if user.has_role(Role.SUPER_ADMIN):
        return
    scope.assert_coordinates(db, user, _window_domain(window.component_type),
                             window.department_id)


def _window_out(db, window: ElectiveRegistrationWindow) -> RegistrationWindowOut:
    now = registration.utcnow()
    offering_ids = [
        o.id for o in db.scalars(select(CourseOffering).where(
            CourseOffering.registration_window_id == window.id))
    ]
    eligible_count = registration.count_students_in_window(db, window)
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
        is_past_deadline=bool(window.closes_at and now >= window.closes_at),
        is_accepting=window.is_open_at(now),
    )


@router.get("/admin/windows", response_model=list[RegistrationWindowOut])
def list_windows(
    db: DbSession, component_type: ComponentType | None = Query(None),
    status: RegistrationWindowStatus | None = Query(None),
    user: User = Depends(_manages_electives),
) -> list[RegistrationWindowOut]:
    """Rounds the caller may see, narrowed to the departments they coordinate."""
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
            if scope.coordinates(db, user, _window_domain(window.component_type),
                                 window.department_id):
                visible.append(window)
        windows = visible
    return [_window_out(db, w) for w in windows]


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
    _assert_manages_window(db, user, window)
    db.add(window)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"Registration round {window.code} created")
    db.commit()
    return _window_out(db, window)


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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(window, field, value)
    if window.opens_at and window.closes_at and window.closes_at <= window.opens_at:
        raise ValidationError("The closing time must be after the opening time.")
    audit.record(db, action=AuditAction.UPDATE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"Registration round {window.code} updated",
                 meta=payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return _window_out(db, window)


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
        offering.registration_window_id = window.id
    audit.record(db, action=AuditAction.UPDATE, entity_type="registration_window",
                 entity_id=window.id, actor=user,
                 description=f"{len(payload.offering_ids)} course(s) attached to "
                             f"{window.code}")
    db.commit()
    return _window_out(db, window)


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

    if target == RegistrationWindowStatus.OPEN and window.status == RegistrationWindowStatus.DRAFT:
        if not db.scalar(select(func.count(CourseOffering.id)).where(
                CourseOffering.registration_window_id == window.id)):
            raise BusinessRuleError(
                "Attach at least one course before opening the round — students "
                "would otherwise see an empty list."
            )
        if window.closes_at is None:
            raise BusinessRuleError(
                "Set a closing time before opening the round. Deadlines are "
                "enforced by the server, so the round needs one."
            )

    previous = window.status
    registration.transition(window, target)

    published = 0
    if target == RegistrationWindowStatus.PUBLISHED:
        published = _notify_allocation_published(db, window)

    audit.record(db, action=AuditAction.STATUS_CHANGE,
                 entity_type="registration_window", entity_id=window.id, actor=user,
                 description=f"{window.code}: {previous.value} → {target.value}",
                 meta={"notified": published})
    db.commit()
    return _window_out(db, window)


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
    allocations = {
        a.student_id: a for a in db.scalars(select(ElectiveAllocation).where(
            ElectiveAllocation.course_offering_id.in_(offering_ids),
            ElectiveAllocation.status != AllocationStatus.DROPPED))
    }
    applicants = {
        row for (row,) in db.execute(
            select(ElectivePreference.student_id).where(
                ElectivePreference.course_offering_id.in_(offering_ids)).distinct())
    }
    sent = 0
    for student_id in applicants | set(allocations):
        student = db.get(Student, student_id)
        if student is None:
            continue
        allocation = allocations.get(student_id)
        if allocation and allocation.course_offering:
            course = allocation.course_offering.course
            section = allocation.section.name if allocation.section else None
            message = (f"You have been allocated {course.code} — {course.title}"
                       + (f" ({section})." if section else "."))
        else:
            message = ("No seat could be allocated from your preferences. "
                       "Contact the coordinator for the next step.")
        notifications.notify(
            db, user_id=student.user_id,
            type=NotificationType.ELECTIVE_ALLOCATION,
            title=f"{window.title} — result published",
            message=message, link="/academics/open-electives",
        )
        sent += 1
    return sent


@router.get("/admin/windows/{window_id}", response_model=RegistrationWindowOut)
def get_window(
    window_id: int, db: DbSession,
    user: User = Depends(_manages_electives),
) -> RegistrationWindowOut:
    window = db.get(ElectiveRegistrationWindow, window_id)
    if window is None:
        raise NotFoundError("Registration round not found.")
    _assert_manages_window(db, user, window)
    return _window_out(db, window)
