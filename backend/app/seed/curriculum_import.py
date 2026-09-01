"""Import researched curricula from ``curriculum/<programme>/<version>.json``.

The pipeline the data goes through is deliberate:

    research → extract → normalize → **review** → import → verify → publish

This module is the *import* step. It never publishes on its own: everything
lands as ``DRAFT`` unless a caller explicitly asks for publication, because a
published curriculum is what students are actually served and web-sourced data
must be reviewed by a human before it becomes university policy inside the
portal. `docs/PHASE3B-RESEARCH.md` is the review artefact.

Re-running is safe. Programmes, departments, courses and curriculum versions are
matched on their natural keys and updated in place, so an import is a
convergence rather than a duplication.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.academics import (
    Course, Curriculum, CurriculumComponent, ElectiveType, Program, ProgramDivision,
)
from app.models.enums import (
    ComponentType, CourseCategory, CurriculumStatus, DeliveryMode, SourceConfidence,
    SourceScope,
)
from app.models.identity import Department

#: backend/curriculum
CURRICULUM_DIR = pathlib.Path(__file__).resolve().parents[2] / "curriculum"

#: Only these are safe to publish straight from an import — the rest stay DRAFT
#: until a person confirms them, however the caller is invoked.
PUBLISHABLE = {SourceConfidence.CONFIRMED_OFFICIAL_SOURCE}


@dataclass
class ImportReport:
    programs: int = 0
    curriculums: int = 0
    components: int = 0
    courses: int = 0
    divisions: int = 0
    published: list[str] = field(default_factory=list)
    held_for_review: list[str] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.programs} programmes · {self.curriculums} curriculum versions · "
                f"{self.components} components · {self.courses} courses · "
                f"{self.divisions} divisions")


# ── loading ────────────────────────────────────────────────────────────────
def load_documents(root: pathlib.Path | None = None) -> list[dict]:
    root = root or CURRICULUM_DIR
    docs = []
    for path in sorted(root.glob("*/*.json")):
        with path.open() as fh:
            doc = json.load(fh)
        doc["_path"] = str(path.relative_to(root.parent))
        docs.append(doc)
    return docs


def load_catalogue(root: pathlib.Path | None = None) -> list[dict]:
    root = root or CURRICULUM_DIR
    path = root / "courses.json"
    if not path.exists():
        return []
    with path.open() as fh:
        return json.load(fh)["courses"]


# ── upserts ────────────────────────────────────────────────────────────────
def _department(db: Session, spec: dict) -> Department:
    department = db.scalar(select(Department).where(Department.code == spec["code"]))
    if department is None:
        department = Department(code=spec["code"], name=spec["name"],
                                short_name=spec.get("short_name"), school=spec["school"])
        db.add(department)
        db.flush()
    else:
        department.name = spec["name"]
        department.school = spec["school"]
        if spec.get("short_name"):
            department.short_name = spec["short_name"]
    return department


def _program(db: Session, spec: dict, department: Department) -> tuple[Program, bool]:
    program = db.scalar(select(Program).where(Program.code == spec["code"]))
    created = program is None
    if created:
        program = Program(code=spec["code"], name=spec["name"],
                          department_id=department.id)
        db.add(program)
    program.name = spec["name"]
    program.short_name = spec.get("short_name")
    program.department_id = department.id
    program.degree_type = spec.get("degree_type", "B.Tech")
    program.duration_years = spec.get("duration_years", 4)
    program.total_semesters = spec.get("total_semesters", 8)
    program.is_active = True
    db.flush()
    return program, created


def import_courses(db: Session, catalogue: list[dict],
                   report: ImportReport) -> dict[str, Course]:
    """Load the shared course catalogue.

    A course studied by several programmes — Mathematics-1, Environment Science
    — is one row, not one row per department. `is_shared` records that, and such
    a course deliberately has no owning department.
    """
    by_code: dict[str, Course] = {}
    departments = {d.code: d for d in db.scalars(select(Department))}
    for spec in catalogue:
        course = db.scalar(select(Course).where(Course.code == spec["code"]))
        if course is None:
            course = Course(code=spec["code"], title=spec["title"])
            db.add(course)
            report.courses += 1
        course.title = spec["title"]
        course.credits = spec["credits"]
        course.lecture_hours = spec["lecture_hours"]
        course.tutorial_hours = spec["tutorial_hours"]
        course.practical_hours = spec["practical_hours"]
        course.delivery_mode = DeliveryMode(spec["delivery"])
        course.is_shared = spec["shared"]
        course.specialization_area = spec.get("specialization_area")
        course.offering_school = spec.get("offering_school")
        try:
            course.category = CourseCategory(spec["category"])
        except ValueError:
            course.category = CourseCategory.OTHER
        owner = spec.get("department")
        course.department_id = departments[owner].id if owner in departments else None
        db.flush()
        by_code[course.code] = course
    return by_code


def _divisions(db: Session, program: Program, doc: dict, report: ImportReport) -> None:
    """Divisions for the batches this curriculum version governs."""
    spec = doc.get("divisions") or {}
    names = spec.get("names") or []
    if not names:
        return
    curriculum = doc["curriculum"]
    start = curriculum["effective_from_year"]
    end = curriculum.get("effective_to_year") or (dt.date.today().year)
    for year in range(start, max(start, end) + 1):
        for name in names:
            existing = db.scalar(
                select(ProgramDivision).where(
                    ProgramDivision.program_id == program.id,
                    ProgramDivision.admission_year == year,
                    ProgramDivision.name == name,
                )
            )
            if existing is None:
                db.add(ProgramDivision(
                    program_id=program.id, admission_year=year, name=name,
                    notes=spec.get("rationale"),
                ))
                report.divisions += 1
    db.flush()


def _confidence(value: str | None) -> SourceConfidence | None:
    if not value:
        return None
    try:
        return SourceConfidence(value)
    except ValueError:
        return None


def import_document(db: Session, doc: dict, courses: dict[str, Course],
                    elective_types: dict[str, ElectiveType],
                    report: ImportReport, *, publish: bool = False) -> Curriculum:
    department = _department(db, doc["program"]["department"])
    program, created = _program(db, doc["program"], department)
    if created:
        report.programs += 1

    spec = doc["curriculum"]
    source = doc.get("source", {})
    confidence = _confidence(source.get("confidence"))

    curriculum = db.scalar(
        select(Curriculum).where(Curriculum.program_id == program.id,
                                 Curriculum.version == spec["version"])
    )
    if curriculum is None:
        curriculum = Curriculum(program_id=program.id, version=spec["version"],
                                name=spec["name"],
                                effective_from_year=spec["effective_from_year"])
        db.add(curriculum)
        report.curriculums += 1
    curriculum.name = spec["name"]
    curriculum.effective_from_year = spec["effective_from_year"]
    curriculum.effective_to_year = spec.get("effective_to_year")
    curriculum.total_credits = spec.get("total_credits")
    curriculum.is_active = True
    curriculum.source_url = source.get("url")
    curriculum.source_title = source.get("title")
    curriculum.source_publisher = source.get("publisher")
    curriculum.academic_year_label = source.get("academic_year")
    curriculum.source_confidence = confidence
    if source.get("retrieved_at"):
        curriculum.retrieved_at = dt.date.fromisoformat(source["retrieved_at"])
    curriculum.review_notes = spec.get("incomplete_note")

    # Publication is a deliberate act, and only ever for a version whose source
    # was fully confirmed. Everything else is held for a person to look at.
    label = f"{program.code} {curriculum.version}"
    wanted = CurriculumStatus(spec.get("status", "DRAFT"))
    if publish and wanted == CurriculumStatus.PUBLISHED and confidence in PUBLISHABLE:
        curriculum.status = CurriculumStatus.PUBLISHED
        curriculum.published_at = dt.datetime.now(dt.timezone.utc)
        report.published.append(label)
    elif curriculum.status != CurriculumStatus.PUBLISHED:
        curriculum.status = (CurriculumStatus.ARCHIVED
                             if wanted == CurriculumStatus.ARCHIVED
                             else CurriculumStatus.DRAFT)
        report.held_for_review.append(label)
    db.flush()

    _divisions(db, program, doc, report)

    # Components are rebuilt from the document so a re-import converges rather
    # than accumulating stale slots.
    existing = {c.code: c for c in db.scalars(
        select(CurriculumComponent).where(
            CurriculumComponent.curriculum_id == curriculum.id)
    )}
    seen: set[str] = set()
    for semester in doc["semesters"]:
        for item in semester["components"]:
            seen.add(item["code"])
            component = existing.get(item["code"])
            if component is None:
                component = CurriculumComponent(curriculum_id=curriculum.id,
                                                code=item["code"])
                db.add(component)
                report.components += 1
            component.semester_number = semester["number"]
            component.title = item["title"]
            component.component_type = ComponentType(item["component_type"])
            component.source_scope = SourceScope(item["source_scope"])
            component.scope_label = item.get("scope_label")
            component.credits = item["credits"]
            component.sequence = item["sequence"]
            component.is_elective = item["is_elective"]
            component.selection_mode = item.get("selection_mode")
            component.eligibility = item.get("eligibility") or {}
            component.source_note = item.get("note")
            component.source_confidence = _confidence(item.get("confidence"))
            if component.source_confidence == SourceConfidence.REQUIRES_FACULTY_CONFIRMATION:
                report.flagged.append(f"{label} · {component.code}")
            course_code = item.get("course")
            component.course_id = (courses[course_code].id
                                   if course_code in courses else None)
            component.elective_type_id = _elective_type_id(component, elective_types)
            component.config = {
                "options": [o["course"] for o in item.get("options", [])],
                "department_basket": [b["course"] for b in
                                      item.get("department_basket", [])],
            }
    for code, component in existing.items():
        if code not in seen:
            db.delete(component)
    db.flush()
    return curriculum


def _elective_type_id(component: CurriculumComponent,
                      elective_types: dict[str, ElectiveType]) -> int | None:
    mapping = {
        ComponentType.OPEN_ELECTIVE: "OPEN",
        ComponentType.PROGRAM_CORE_ELECTIVE: "CORE",
        ComponentType.MOOC: "MOOC",
    }
    key = mapping.get(component.component_type)
    kind = elective_types.get(key) if key else None
    return kind.id if kind else None


def run_import(db: Session, *, publish: bool = False,
               root: pathlib.Path | None = None) -> ImportReport:
    """Import every curriculum document found under `root`."""
    report = ImportReport()
    elective_types = {t.code: t for t in db.scalars(select(ElectiveType))}
    docs = load_documents(root)
    # Departments must exist before the shared catalogue can be attributed.
    for doc in docs:
        _department(db, doc["program"]["department"])
    db.flush()
    courses = import_courses(db, load_catalogue(root), report)
    for doc in docs:
        import_document(db, doc, courses, elective_types, report, publish=publish)
    return report
