"""Curriculum is served as data; the frontend renders whatever it receives."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, get_current_user, require_permission
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.rbac import P
from app.models.academics import (
    Course, CourseOffering, Curriculum, CurriculumComponent, ElectiveAllocation,
    ElectiveType, Program, ProgramDivision,
)
from app.models.enums import AuditAction, ComponentType, CurriculumStatus, SourceConfidence
from app.models.identity import Department, Student, User
from app.schemas.academics import (
    CurriculumComponentIn, CurriculumOut, CurriculumSemesterOut, CurriculumSourceOut,
    CurriculumVersionIn, ElectiveTypeOut, ProgramDivisionIn, ProgramDivisionOut,
)
from app.schemas.common import Message
from app.schemas.identity import ProgramOut
from app.services import audit
from app.services import curriculum as curriculum_engine
from app.services.eligibility import active_curriculum
from app.services.serializers import component_out

router = APIRouter(prefix="/curriculum", tags=["curriculum"])

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII",
         9: "IX", 10: "X"}


def _build(db, curriculum: Curriculum, student: Student | None = None,
           *, with_semesters: bool = True) -> CurriculumOut:
    # The admin list renders a dozen curricula at once and only needs the
    # counts, so loading ~70 component rows per curriculum (and then a second
    # query for their offerings) is work nobody asked for.
    if not with_semesters:
        totals = db.execute(
            select(func.count(CurriculumComponent.id),
                   func.count(CurriculumComponent.id).filter(
                       CurriculumComponent.source_confidence
                       == SourceConfidence.REQUIRES_FACULTY_CONFIRMATION))
            .where(CurriculumComponent.curriculum_id == curriculum.id)
        ).one()
        return _summary_out(db, curriculum, component_count=int(totals[0] or 0),
                            flagged=int(totals[1] or 0))

    components = list(db.scalars(
        select(CurriculumComponent)
        .where(CurriculumComponent.curriculum_id == curriculum.id)
        .order_by(CurriculumComponent.semester_number, CurriculumComponent.sequence)
    ))
    offering_counts = dict(db.execute(
        select(CourseOffering.curriculum_component_id, func.count(CourseOffering.id))
        .where(CourseOffering.curriculum_component_id.in_([c.id for c in components] or [0]))
        .group_by(CourseOffering.curriculum_component_id)
    ).all())

    allocations: dict[int, str] = {}
    if student:
        rows = db.execute(
            select(ElectiveAllocation.curriculum_component_id, Course.code, Course.title)
            .join(CourseOffering, CourseOffering.id == ElectiveAllocation.course_offering_id)
            .join(Course, Course.id == CourseOffering.course_id)
            .where(ElectiveAllocation.student_id == student.id)
        ).all()
        allocations = {r[0]: f"{r[1]} · {r[2]}" for r in rows}

    by_semester: dict[int, list] = {}
    for component in components:
        unlocked = status_label = None
        if student:
            unlocked = component.semester_number <= student.current_semester
            if component.id in allocations:
                status_label = "Allocated"
            elif not component.is_elective:
                status_label = "Core"
            elif unlocked:
                status_label = "Action needed"
            else:
                status_label = "Upcoming"
        by_semester.setdefault(component.semester_number, []).append(
            component_out(
                component, is_unlocked=unlocked, status_label=status_label,
                allocated_course=allocations.get(component.id),
                offering_count=offering_counts.get(component.id, 0),
            )
        )

    semesters = [] if not with_semesters else [
        CurriculumSemesterOut(
            semester_number=number,
            label=f"Semester {ROMAN.get(number, number)}",
            is_current=bool(student and student.current_semester == number),
            is_completed=bool(student and student.current_semester > number),
            components=items,
            total_credits=round(sum(c.credits for c in items), 1),
        )
        for number, items in sorted(by_semester.items())
    ]
    program = curriculum.program
    department = db.get(Department, program.department_id) if program else None
    flagged = sum(
        1 for c in components
        if c.source_confidence == SourceConfidence.REQUIRES_FACULTY_CONFIRMATION
    )
    return CurriculumOut(
        id=curriculum.id, program_id=curriculum.program_id,
        program_name=program.name if program else None,
        program_code=program.code if program else None,
        department_code=department.code if department else None,
        school=department.school if department else None,
        name=curriculum.name, version=curriculum.version,
        effective_from_year=curriculum.effective_from_year,
        effective_to_year=curriculum.effective_to_year,
        batch_label=_batch_label(curriculum),
        total_credits=curriculum.total_credits, status=curriculum.status,
        is_active=curriculum.is_active, published_at=curriculum.published_at,
        source=_source_out(db, curriculum),
        component_count=len(components), flagged_component_count=flagged,
        semesters=semesters,
    )


def _summary_out(db, curriculum: Curriculum, *, component_count: int,
                 flagged: int) -> CurriculumOut:
    """The list view: metadata and counts, no semester tree."""
    program = curriculum.program
    department = db.get(Department, program.department_id) if program else None
    return CurriculumOut(
        id=curriculum.id, program_id=curriculum.program_id,
        program_name=program.name if program else None,
        program_code=program.code if program else None,
        department_code=department.code if department else None,
        school=department.school if department else None,
        name=curriculum.name, version=curriculum.version,
        effective_from_year=curriculum.effective_from_year,
        effective_to_year=curriculum.effective_to_year,
        batch_label=_batch_label(curriculum),
        total_credits=curriculum.total_credits, status=curriculum.status,
        is_active=curriculum.is_active, published_at=curriculum.published_at,
        source=_source_out(db, curriculum),
        component_count=component_count, flagged_component_count=flagged,
        semesters=[],
    )


def _batch_label(curriculum: Curriculum) -> str:
    """Which admission batches this version governs, in words."""
    if curriculum.effective_to_year is None:
        return f"{curriculum.effective_from_year} batch onward"
    if curriculum.effective_to_year == curriculum.effective_from_year:
        return f"{curriculum.effective_from_year} batch"
    return f"{curriculum.effective_from_year}–{curriculum.effective_to_year} batches"


def _source_out(db, curriculum: Curriculum) -> CurriculumSourceOut | None:
    if not any([curriculum.source_url, curriculum.source_title,
                curriculum.source_confidence, curriculum.review_notes]):
        return None
    verifier = (db.get(User, curriculum.verified_by_user_id)
                if curriculum.verified_by_user_id else None)
    return CurriculumSourceOut(
        url=curriculum.source_url, title=curriculum.source_title,
        publisher=curriculum.source_publisher, retrieved_at=curriculum.retrieved_at,
        academic_year=curriculum.academic_year_label,
        confidence=(curriculum.source_confidence.value
                    if curriculum.source_confidence else None),
        verified_at=curriculum.verified_at,
        verified_by=verifier.full_name if verifier else None,
        review_notes=curriculum.review_notes,
    )


@router.get("/me", response_model=CurriculumOut)
def my_curriculum(db: DbSession, user: CurrentUser) -> CurriculumOut:
    """The signed-in student's curriculum, annotated with their progress."""
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise NotFoundError("No student record is linked to this account.")
    curriculum = active_curriculum(db, student)
    if curriculum is None:
        raise NotFoundError("No curriculum has been published for your programme yet.")
    return _build(db, curriculum, student)


@router.get("/programs", response_model=list[ProgramOut])
def list_programs(db: DbSession, _: CurrentUser,
                  department_id: int | None = None) -> list[ProgramOut]:
    stmt = select(Program).where(Program.is_active.is_(True)).order_by(Program.name)
    if department_id:
        stmt = stmt.where(Program.department_id == department_id)
    return [
        ProgramOut(
            id=p.id, code=p.code, name=p.name, short_name=p.short_name,
            degree_type=p.degree_type,
            duration_years=p.duration_years, total_semesters=p.total_semesters,
            department_id=p.department_id,
            department_code=p.department.code if p.department else None,
            school=p.department.school if p.department else None,
            is_active=p.is_active,
        )
        for p in db.scalars(stmt)
    ]


@router.get("/elective-types", response_model=list[ElectiveTypeOut])
def elective_types(db: DbSession, _: CurrentUser) -> list[ElectiveTypeOut]:
    return [
        ElectiveTypeOut.model_validate(t)
        for t in db.scalars(
            select(ElectiveType).where(ElectiveType.is_active.is_(True))
            .order_by(ElectiveType.code)
        )
    ]


@router.get("", response_model=list[CurriculumOut])
def list_curriculums(db: DbSession, _: CurrentUser,
                     program_id: int | None = None,
                     status: CurriculumStatus | None = None,
                     include_semesters: bool = True) -> list[CurriculumOut]:
    """Every recorded version, newest batch first.

    Historical versions are listed alongside current ones — they are never
    deleted, because a cohort part-way through its degree must keep seeing the
    structure it was admitted under.
    """
    stmt = select(Curriculum).order_by(Curriculum.effective_from_year.desc(),
                                       Curriculum.version)
    if program_id:
        stmt = stmt.where(Curriculum.program_id == program_id)
    if status:
        stmt = stmt.where(Curriculum.status == status)
    return [_build(db, c, with_semesters=include_semesters) for c in db.scalars(stmt)]


@router.get("/{curriculum_id}", response_model=CurriculumOut)
def get_curriculum(curriculum_id: int, db: DbSession, _: CurrentUser) -> CurriculumOut:
    curriculum = db.get(Curriculum, curriculum_id)
    if curriculum is None:
        raise NotFoundError("Curriculum not found.")
    return _build(db, curriculum)


@router.get("/{curriculum_id}/components", response_model=list[dict])
def curriculum_components(
    curriculum_id: int, db: DbSession,
    _: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
    component_type: ComponentType | None = Query(None),
) -> list[dict]:
    stmt = select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == curriculum_id
    )
    if component_type:
        stmt = stmt.where(CurriculumComponent.component_type == component_type)
    return [
        component_out(c).model_dump()
        for c in db.scalars(stmt.order_by(CurriculumComponent.semester_number,
                                          CurriculumComponent.sequence))
    ]


# ── divisions ──────────────────────────────────────────────────────────────
@router.get("/programs/{program_id}/divisions", response_model=list[ProgramDivisionOut])
def program_divisions(program_id: int, db: DbSession, _: CurrentUser,
                      admission_year: int | None = None) -> list[ProgramDivisionOut]:
    """The divisions a programme actually runs, by admission batch.

    A/B/C/D is ICT's shape, not a constant — CSBS runs one division and Computer
    Engineering four — so the Core Elective allocator and the admin screens read
    this rather than assuming.
    """
    stmt = select(ProgramDivision).where(ProgramDivision.program_id == program_id)
    if admission_year is not None:
        stmt = stmt.where(ProgramDivision.admission_year == admission_year)
    divisions = list(db.scalars(
        stmt.order_by(ProgramDivision.admission_year.desc(), ProgramDivision.name)))

    counts = dict(db.execute(
        select(Student.division, func.count(Student.id))
        .where(Student.program_id == program_id)
        .group_by(Student.division)
    ).all())
    return [
        ProgramDivisionOut(
            id=d.id, program_id=d.program_id, admission_year=d.admission_year,
            name=d.name, capacity=d.capacity, is_active=d.is_active,
            student_count=counts.get(d.name, 0), notes=d.notes,
        )
        for d in divisions
    ]


@router.post("/divisions", response_model=ProgramDivisionOut, status_code=201)
def create_division(payload: ProgramDivisionIn, db: DbSession,
                    user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                    ) -> ProgramDivisionOut:
    if db.get(Program, payload.program_id) is None:
        raise NotFoundError("Programme not found.")
    existing = db.scalar(select(ProgramDivision).where(
        ProgramDivision.program_id == payload.program_id,
        ProgramDivision.admission_year == payload.admission_year,
        ProgramDivision.name == payload.name,
    ))
    if existing is not None:
        raise BusinessRuleError(
            f"Division {payload.name} already exists for the "
            f"{payload.admission_year} batch of this programme."
        )
    division = ProgramDivision(**payload.model_dump())
    db.add(division)
    db.flush()
    audit.record(db, actor=user, action=AuditAction.CREATE,
                 entity_type="program_division", entity_id=division.id,
                 description=f"Division {division.name} added for "
                         f"{division.admission_year}.")
    db.commit()
    return ProgramDivisionOut(
        id=division.id, program_id=division.program_id,
        admission_year=division.admission_year, name=division.name,
        capacity=division.capacity, is_active=division.is_active,
        student_count=0, notes=division.notes,
    )


@router.delete("/divisions/{division_id}", response_model=Message)
def delete_division(division_id: int, db: DbSession,
                    user: User = Depends(require_permission(P["ACADEMIC_MANAGE"]))
                    ) -> Message:
    division = db.get(ProgramDivision, division_id)
    if division is None:
        raise NotFoundError("Division not found.")
    enrolled = db.scalar(
        select(func.count(Student.id)).where(
            Student.program_id == division.program_id,
            Student.admission_year == division.admission_year,
            Student.division == division.name,
        )
    )
    if enrolled:
        raise BusinessRuleError(
            f"{enrolled} students are still assigned to division {division.name}. "
            "Move them before removing it."
        )
    audit.record(db, actor=user, action=AuditAction.DELETE,
                 entity_type="program_division", entity_id=division.id,
                 description=f"Division {division.name} removed.")
    name = division.name
    db.delete(division)
    db.commit()
    return Message(message=f"Division {name} removed.")


# ── version management ─────────────────────────────────────────────────────
# A published curriculum is what students are actually served, so it is not
# casually editable: structural changes are refused and the way forward is a new
# revision. That is the whole reason versions carry a batch window.
def _require_editable(curriculum: Curriculum) -> None:
    if curriculum.status == CurriculumStatus.PUBLISHED:
        raise BusinessRuleError(
            f"{curriculum.name} is published and governs the "
            f"{_batch_label(curriculum)}. Editing it would rewrite the rules a "
            "cohort is already studying under. Create a new revision, or "
            "unpublish this version first."
        )


@router.post("/versions", response_model=CurriculumOut, status_code=201)
def create_version(payload: CurriculumVersionIn, db: DbSession,
                   user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                   ) -> CurriculumOut:
    """Start a new curriculum version. Always begins as a draft."""
    if db.get(Program, payload.program_id) is None:
        raise NotFoundError("Programme not found.")
    clash = db.scalar(select(Curriculum).where(
        Curriculum.program_id == payload.program_id,
        Curriculum.version == payload.version,
    ))
    if clash is not None:
        raise BusinessRuleError(
            f"Version {payload.version} already exists for this programme."
        )
    if (payload.effective_to_year is not None
            and payload.effective_to_year < payload.effective_from_year):
        raise BusinessRuleError(
            "The last batch cannot be earlier than the first batch."
        )
    curriculum = Curriculum(**payload.model_dump(), status=CurriculumStatus.DRAFT)
    db.add(curriculum)
    db.flush()
    audit.record(db, actor=user, action=AuditAction.CREATE, entity_type="curriculum",
                 entity_id=curriculum.id,
                 description=f"Curriculum {curriculum.version} drafted.")
    db.commit()
    return _build(db, curriculum)


@router.post("/{curriculum_id}/revise", response_model=CurriculumOut, status_code=201)
def revise_version(curriculum_id: int, version: str, effective_from_year: int,
                   db: DbSession,
                   user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                   ) -> CurriculumOut:
    """Copy a version into a new draft revision for a later batch.

    The published original is closed off at the batch before the new one starts,
    so the two windows never overlap and every cohort resolves to exactly one
    curriculum. The old version stays — students already on it keep it.
    """
    source = db.get(Curriculum, curriculum_id)
    if source is None:
        raise NotFoundError("Curriculum not found.")
    if effective_from_year <= source.effective_from_year:
        raise BusinessRuleError(
            "A revision must start with a later batch than the version it revises."
        )
    clash = db.scalar(select(Curriculum).where(
        Curriculum.program_id == source.program_id, Curriculum.version == version))
    if clash is not None:
        raise BusinessRuleError(f"Version {version} already exists for this programme.")

    revision = Curriculum(
        program_id=source.program_id, version=version,
        name=f"{source.name.rsplit('—', 1)[0].strip()} — {version}",
        effective_from_year=effective_from_year, effective_to_year=None,
        total_credits=source.total_credits, status=CurriculumStatus.DRAFT,
        source_url=source.source_url, source_title=source.source_title,
        source_publisher=source.source_publisher,
        source_confidence=source.source_confidence,
        review_notes=f"Revised from {source.version}. Confirm every component "
                     "against the current official document before publishing.",
    )
    db.add(revision)
    db.flush()
    for component in db.scalars(select(CurriculumComponent).where(
            CurriculumComponent.curriculum_id == source.id)):
        db.add(CurriculumComponent(
            curriculum_id=revision.id, semester_number=component.semester_number,
            code=component.code, title=component.title,
            component_type=component.component_type,
            elective_type_id=component.elective_type_id,
            source_scope=component.source_scope, scope_label=component.scope_label,
            credits=component.credits, sequence=component.sequence,
            is_elective=component.is_elective, description=component.description,
            course_id=component.course_id, selection_mode=component.selection_mode,
            eligibility=dict(component.eligibility or {}),
            source_confidence=component.source_confidence,
            source_note=component.source_note, config=dict(component.config or {}),
        ))
    # Close the previous window so the two never both claim a batch.
    if source.effective_to_year is None:
        source.effective_to_year = effective_from_year - 1
    db.flush()
    audit.record(db, actor=user, action=AuditAction.CREATE, entity_type="curriculum",
                 entity_id=revision.id,
                 description=f"Revision {version} drafted from {source.version}; "
                         f"{source.version} now ends at the "
                         f"{source.effective_to_year} batch.")
    db.commit()
    return _build(db, revision)


@router.post("/{curriculum_id}/publish", response_model=CurriculumOut)
def publish_version(curriculum_id: int, db: DbSession,
                    user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                    ) -> CurriculumOut:
    """Publish a draft. This is the human review step made explicit.

    Refused while any component is still flagged as needing faculty
    confirmation — an unconfirmed reading of a curriculum document must never
    silently become the rule a student is held to.
    """
    curriculum = db.get(Curriculum, curriculum_id)
    if curriculum is None:
        raise NotFoundError("Curriculum not found.")
    if curriculum.status == CurriculumStatus.PUBLISHED:
        return _build(db, curriculum)

    flagged = list(db.scalars(select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == curriculum.id,
        CurriculumComponent.source_confidence
        == SourceConfidence.REQUIRES_FACULTY_CONFIRMATION,
    )))
    if flagged:
        raise BusinessRuleError(
            f"{len(flagged)} component(s) still need faculty confirmation: "
            + ", ".join(c.code for c in flagged[:5])
            + ". Resolve or clear the flags before publishing."
        )
    if not db.scalar(select(func.count(CurriculumComponent.id)).where(
            CurriculumComponent.curriculum_id == curriculum.id)):
        raise BusinessRuleError("A curriculum with no components cannot be published.")

    curriculum.status = CurriculumStatus.PUBLISHED
    curriculum.published_at = dt.datetime.now(dt.timezone.utc)
    curriculum.published_by_user_id = user.id
    curriculum.verified_by_user_id = user.id
    curriculum.verified_at = curriculum.published_at
    audit.record(db, actor=user, action=AuditAction.PUBLISH, entity_type="curriculum",
                 entity_id=curriculum.id,
                 description=f"{curriculum.name} published for the "
                         f"{_batch_label(curriculum)}.")
    db.commit()
    return _build(db, curriculum)


@router.post("/{curriculum_id}/unpublish", response_model=CurriculumOut)
def unpublish_version(curriculum_id: int, db: DbSession,
                      user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                      ) -> CurriculumOut:
    """Return a published version to draft so it can be corrected.

    Refused while students are actually governed by it — pulling the curriculum
    out from under a live cohort is never the right fix; a revision is.
    """
    curriculum = db.get(Curriculum, curriculum_id)
    if curriculum is None:
        raise NotFoundError("Curriculum not found.")
    governed = _governed_student_count(db, curriculum)
    if governed:
        raise BusinessRuleError(
            f"{governed} students are currently governed by this version. "
            "Create a revision for the next batch instead of unpublishing it."
        )
    curriculum.status = CurriculumStatus.DRAFT
    curriculum.published_at = None
    audit.record(db, actor=user, action=AuditAction.STATUS_CHANGE,
                 entity_type="curriculum", entity_id=curriculum.id,
                 description=f"{curriculum.name} returned to draft.")
    db.commit()
    return _build(db, curriculum)


@router.post("/{curriculum_id}/archive", response_model=CurriculumOut)
def archive_version(curriculum_id: int, db: DbSession,
                    user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                    ) -> CurriculumOut:
    """Archive a superseded version.

    Archiving keeps the data — historical curricula are never deleted — it only
    stops the version being served to new students.
    """
    curriculum = db.get(Curriculum, curriculum_id)
    if curriculum is None:
        raise NotFoundError("Curriculum not found.")
    governed = _governed_student_count(db, curriculum)
    if governed:
        raise BusinessRuleError(
            f"{governed} students are still governed by this version and would "
            "lose their curriculum. Archive it once they have graduated."
        )
    curriculum.status = CurriculumStatus.ARCHIVED
    audit.record(db, actor=user, action=AuditAction.STATUS_CHANGE,
                 entity_type="curriculum", entity_id=curriculum.id,
                 description=f"{curriculum.name} archived.")
    db.commit()
    return _build(db, curriculum)


def _governed_student_count(db, curriculum: Curriculum) -> int:
    """How many active students this version currently resolves for."""
    students = db.scalars(select(Student).where(
        Student.program_id == curriculum.program_id))
    return sum(
        1 for s in students
        if (resolved := curriculum_engine.resolve_curriculum(db, s))
        and resolved.id == curriculum.id
    )


@router.post("/{curriculum_id}/components", response_model=dict, status_code=201)
def add_component(curriculum_id: int, payload: CurriculumComponentIn, db: DbSession,
                  user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                  ) -> dict:
    curriculum = db.get(Curriculum, curriculum_id)
    if curriculum is None:
        raise NotFoundError("Curriculum not found.")
    _require_editable(curriculum)
    clash = db.scalar(select(CurriculumComponent).where(
        CurriculumComponent.curriculum_id == curriculum_id,
        CurriculumComponent.code == payload.code))
    if clash is not None:
        raise BusinessRuleError(f"Component {payload.code} already exists here.")
    component = CurriculumComponent(curriculum_id=curriculum_id, **payload.model_dump())
    db.add(component)
    db.flush()
    audit.record(db, actor=user, action=AuditAction.CREATE,
                 entity_type="curriculum_component", entity_id=component.id,
                 description=f"{component.code} added to {curriculum.version}.")
    db.commit()
    return component_out(component).model_dump()


@router.delete("/components/{component_id}", response_model=Message)
def delete_component(component_id: int, db: DbSession,
                     user: User = Depends(require_permission(P["ACADEMIC_MANAGE"]))
                     ) -> Message:
    component = db.get(CurriculumComponent, component_id)
    if component is None:
        raise NotFoundError("Component not found.")
    _require_editable(db.get(Curriculum, component.curriculum_id))
    audit.record(db, actor=user, action=AuditAction.DELETE,
                 entity_type="curriculum_component", entity_id=component.id,
                 description=f"{component.code} removed.")
    code = component.code
    db.delete(component)
    db.commit()
    return Message(message=f"Component {code} removed.")


@router.post("/components/{component_id}/confirm", response_model=dict)
def confirm_component(component_id: int, db: DbSession, note: str | None = None,
                      user: User = Depends(require_permission(P["ACADEMIC_MANAGE"])),
                      ) -> dict:
    """Clear a "requires faculty confirmation" flag once a person has checked it.

    The flag exists because some official documents are ambiguous or disagree.
    Clearing it is a deliberate, audited act by a named person — never a side
    effect of an import.
    """
    component = db.get(CurriculumComponent, component_id)
    if component is None:
        raise NotFoundError("Component not found.")
    component.source_confidence = SourceConfidence.CONFIRMED_OFFICIAL_SOURCE
    if note:
        component.source_note = note
    audit.record(db, actor=user, action=AuditAction.UPDATE,
                 entity_type="curriculum_component", entity_id=component.id,
                 description=f"{component.code} confirmed by {user.full_name}.")
    db.commit()
    return component_out(component).model_dump()
