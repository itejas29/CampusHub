"""The import pipeline: research → … → review → import → publish.

The rule this file guards is that web-sourced curriculum data does not become
university policy inside the portal without a person deciding it should.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.academics import (
    Course, Curriculum, CurriculumComponent, Program, ProgramDivision,
)
from app.models.enums import ComponentType, CurriculumStatus, SourceConfidence
from app.seed import curriculum_import
from app.services import curriculum as engine


@pytest.fixture
def imported(db):
    """The full researched corpus, imported but *not* published."""
    return curriculum_import.run_import(db), db


@pytest.fixture
def published(db):
    return curriculum_import.run_import(db, publish=True), db


# ── the import itself ──────────────────────────────────────────────────────
def test_import_creates_every_verified_programme(imported):
    report, db = imported
    codes = {p.code for p in db.scalars(select(Program))}
    assert codes == {
        "B.TECH-ICT", "B.TECH-CE", "B.TECH-CSBS", "B.TECH-ECE", "B.TECH-CIVIL",
        "B.TECH-MECH", "B.TECH-CHEM", "B.TECH-ELEC", "B.TECH-PETRO", "B.TECH-BIO",
    }
    assert report.programs == 10


def test_import_creates_both_ece_versions(imported):
    _report, db = imported
    ece = db.scalar(select(Program).where(Program.code == "B.TECH-ECE"))
    versions = {c.version for c in engine.curriculum_versions(db, ece.id)}
    assert versions == {"2020-24", "2024-28"}


def test_batch_windows_do_not_overlap(imported):
    """Every cohort must resolve to exactly one curriculum."""
    _report, db = imported
    for program in db.scalars(select(Program)):
        versions = engine.curriculum_versions(db, program.id)
        for year in range(2018, 2030):
            matching = [v for v in versions if v.governs_batch(year)]
            assert len(matching) <= 1, (
                f"{program.code}: batch {year} matches "
                f"{[v.version for v in matching]}"
            )


def test_shared_courses_are_not_duplicated_per_programme(imported):
    _report, db = imported
    codes = [c.code for c in db.scalars(select(Course))]
    assert len(codes) == len(set(codes))
    shared = list(db.scalars(select(Course).where(Course.is_shared.is_(True))))
    assert len(shared) > 20
    assert all(c.department_id is None for c in shared)


def test_import_is_idempotent(db):
    first = curriculum_import.run_import(db)
    before = db.scalar(select(Curriculum).where(Curriculum.version == "2024-28"))
    counts = (
        len(list(db.scalars(select(Program)))),
        len(list(db.scalars(select(Course)))),
        len(list(db.scalars(select(CurriculumComponent)))),
    )
    second = curriculum_import.run_import(db)
    after = (
        len(list(db.scalars(select(Program)))),
        len(list(db.scalars(select(Course)))),
        len(list(db.scalars(select(CurriculumComponent)))),
    )
    assert counts == after
    assert second.programs == 0 and second.curriculums == 0
    assert first.programs == 10
    assert before is not None


# ── source traceability ────────────────────────────────────────────────────
def test_every_imported_version_records_its_source(imported):
    _report, db = imported
    for curriculum in db.scalars(select(Curriculum)):
        assert curriculum.source_url.startswith("https://api.pdeu.ac.in/")
        assert curriculum.source_title
        assert curriculum.source_publisher == "Pandit Deendayal Energy University"
        assert curriculum.retrieved_at is not None
        assert curriculum.source_confidence is not None


def test_divisions_are_created_per_programme_and_batch(imported):
    _report, db = imported
    computer = db.scalar(select(Program).where(Program.code == "B.TECH-CE"))
    csbs = db.scalar(select(Program).where(Program.code == "B.TECH-CSBS"))

    assert engine.divisions_for(db, computer.id, 2024) == ["A", "B", "C", "D"]
    assert engine.divisions_for(db, csbs.id, 2024) == ["A"]
    # Divisions exist for each batch the version governs, not just the first.
    years = {
        d.admission_year for d in db.scalars(
            select(ProgramDivision).where(ProgramDivision.program_id == computer.id))
    }
    assert 2024 in years and 2025 in years


# ── publication is a deliberate act ────────────────────────────────────────
def test_nothing_is_published_by_a_plain_import(imported):
    report, db = imported
    assert report.published == []
    statuses = {c.status for c in db.scalars(select(Curriculum))}
    assert CurriculumStatus.PUBLISHED not in statuses


def test_publishing_requires_an_explicit_decision(published):
    report, db = published
    assert len(report.published) >= 9
    ict = db.scalar(select(Curriculum).join(Program).where(
        Program.code == "B.TECH-ICT"))
    assert ict.status == CurriculumStatus.PUBLISHED
    assert ict.published_at is not None


def test_partially_sourced_curriculum_is_never_published(published):
    """Biotechnology's official structure stops at Semester II. Asking for
    publication must not override that."""
    report, db = published
    bio = db.scalar(select(Curriculum).join(Program).where(
        Program.code == "B.TECH-BIO"))
    assert bio.status == CurriculumStatus.DRAFT
    assert bio.source_confidence == SourceConfidence.PARTIAL_SOURCE
    assert any("B.TECH-BIO" in label for label in report.held_for_review)
    assert not any("B.TECH-BIO" in label for label in report.published)


def test_a_draft_curriculum_reaches_no_student(published):
    """Built against the *imported* programmes, not the shared fixture world —
    the point is that a real draft from the pipeline serves nothing."""
    _report, db = published
    from app.models.identity import Student, User

    bio_program = db.scalar(select(Program).where(Program.code == "B.TECH-BIO"))
    user = User(email="bio@example.com", hashed_password="x", full_name="Bio Student")
    db.add(user)
    db.flush()
    student = Student(
        user_id=user.id, roll_number="25BBT999", program_id=bio_program.id,
        department_id=bio_program.department_id, admission_year=2025,
        current_semester=2,
    )
    db.add(student)
    db.flush()

    assert engine.resolve_curriculum(db, student) is None
    assert engine.eligible_components(db, student) == []


def test_uncertain_components_are_flagged_on_import(published):
    report, db = published
    assert report.flagged
    flagged = list(db.scalars(select(CurriculumComponent).where(
        CurriculumComponent.source_confidence
        == SourceConfidence.REQUIRES_FACULTY_CONFIRMATION)))
    assert flagged
    for component in flagged:
        assert component.source_note


# ── the structures actually differ ─────────────────────────────────────────
def test_imported_programmes_do_not_all_look_like_ict(published):
    _report, db = published

    def shape(code, version):
        curriculum = db.scalar(select(Curriculum).join(Program).where(
            Program.code == code, Curriculum.version == version))
        return sorted(
            (c.semester_number, c.component_type.value)
            for c in engine.components_for(db, curriculum)
            if c.is_elective or c.component_type in (
                ComponentType.INTERNSHIP, ComponentType.PROJECT)
        )

    ict = shape("B.TECH-ICT", "2024-28")
    mechanical = shape("B.TECH-MECH", "2024-28")
    ece_old = shape("B.TECH-ECE", "2020-24")
    ece_new = shape("B.TECH-ECE", "2024-28")

    assert ict != mechanical           # different Program Elective distribution
    assert ece_old != ece_new          # different curriculum generation
    assert ict == ece_new              # these two genuinely do share a shape


def test_petroleum_has_a_rural_internship_and_no_cssi(published):
    _report, db = published
    curriculum = db.scalar(select(Curriculum).join(Program).where(
        Program.code == "B.TECH-PETRO"))
    codes = {c.code for c in engine.components_for(
        db, curriculum, component_type=ComponentType.INTERNSHIP)}
    assert "RI" in codes
    assert "CSSI" not in codes


def test_the_2020_scheme_has_no_mooc_component(published):
    _report, db = published
    for code in ("B.TECH-ECE", "B.TECH-ELEC"):
        curriculum = db.scalar(select(Curriculum).join(Program).where(
            Program.code == code, Curriculum.version == "2020-24"))
        assert engine.components_for(
            db, curriculum, component_type=ComponentType.MOOC) == []
