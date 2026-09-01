"""Curriculum resolution: the right structure for the right batch.

The failure this file exists to prevent is the quiet one — a student being shown
another programme's requirements, or their own programme's *newer* requirements,
because the lookup keyed on department and semester instead of on the curriculum
version their batch was admitted under.
"""
from __future__ import annotations

import pytest

from app.models.enums import ComponentType, CurriculumStatus
from app.services import curriculum as engine

# ICT 2024-28, abbreviated to the components that carry the rules.
ICT_2024 = [
    (3, "CSSI", "Civic and Social Service Internship", "INTERNSHIP", "ANY"),
    (4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL"),
    (5, "OE2-MOOC", "Open Elective 2 (NPTEL/SWAYAM/MOOC)", "MOOC", "EXTERNAL_PLATFORM"),
    (5, "PE1", "Program Elective 1", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT"),
]
# ECE 2020-24: Open Electives start a semester earlier and there is no MOOC slot.
ECE_2020 = [
    (3, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_DEPARTMENT_FOET"),
    (4, "OE2", "Open Elective 2", "OPEN_ELECTIVE", "OTHER_DEPARTMENT_FOET"),
    (5, "CE1", "Core Elective 1", "PROGRAM_CORE_ELECTIVE", "SAME_DEPARTMENT"),
    (6, "IT", "Industrial Training / IEP", "INTERNSHIP", "ANY"),
]
ECE_2024 = [
    (3, "CSSI", "Civic and Social Service Internship", "INTERNSHIP", "ANY"),
    (4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL"),
    (5, "OE2-MOOC", "Open Elective 2 (NPTEL/SWAYAM/MOOC)", "MOOC", "EXTERNAL_PLATFORM"),
    (7, "SI", "Summer Internship", "INTERNSHIP", "ANY"),
]


def test_batch_window_picks_the_curriculum_the_student_was_admitted_under(
    db, make_curriculum, make_student
):
    make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, ECE_2020)
    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)

    older = make_student("B.TECH-ECE", 2022, semester=7)
    newer = make_student("B.TECH-ECE", 2024, semester=4)

    assert engine.resolve_curriculum(db, older).version == "2020-24"
    assert engine.resolve_curriculum(db, newer).version == "2024-28"


def test_old_batch_does_not_receive_new_curriculum_components(
    db, make_curriculum, make_student
):
    """The 2020-24 ECE structure has no MOOC slot. A 2022 student must not get one
    simply because a newer version of their own programme introduced it."""
    make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, ECE_2020)
    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)

    student = make_student("B.TECH-ECE", 2022, semester=7)
    context = engine.build_context(db, student)

    assert not context.has(ComponentType.MOOC)
    codes = {a.component.code for a in context.available}
    assert codes == {"OE1", "OE2", "CE1", "IT"}
    assert "CSSI" not in codes and "SI" not in codes


def test_new_batch_receives_only_its_own_version(db, make_curriculum, make_student):
    make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, ECE_2020)
    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)

    student = make_student("B.TECH-ECE", 2024, semester=8)
    codes = {c.code for c in engine.eligible_components(db, student)}

    assert codes == {"CSSI", "OE1", "OE2-MOOC", "SI"}
    assert "CE1" not in codes          # a Core Elective is 2020-scheme only


def test_open_elective_semester_differs_between_versions(
    db, make_curriculum, make_student
):
    """OE1 is Semester III in 2020-24 and Semester IV in 2024-28. A Semester III
    student on each version must therefore see different things."""
    make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, ECE_2020)
    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)

    old_sem3 = make_student("B.TECH-ECE", 2022, semester=3)
    new_sem3 = make_student("B.TECH-ECE", 2024, semester=3)

    old_codes = {c.code for c in engine.eligible_components(db, old_sem3)}
    new_codes = {c.code for c in engine.eligible_components(db, new_sem3)}

    assert "OE1" in old_codes            # unlocked in Semester III
    assert "OE1" not in new_codes        # still a semester away
    assert "CSSI" in new_codes


# ── cross-programme isolation ──────────────────────────────────────────────
def test_ict_student_does_not_receive_ece_curriculum(
    db, make_curriculum, make_student
):
    make_curriculum("B.TECH-ICT", "2024-28", 2024, None, ICT_2024)
    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)

    ict = make_student("B.TECH-ICT", 2024, semester=5)
    resolved = engine.resolve_curriculum(db, ict)

    assert resolved.program_id == ict.program_id
    codes = {c.code for c in engine.eligible_components(db, ict)}
    assert "PE1" in codes                # ICT's own
    assert "SI" not in codes             # ECE's Sem VII slot must not leak in


def test_programme_with_no_curriculum_gets_nothing_rather_than_someone_elses(
    db, make_curriculum, make_student
):
    make_curriculum("B.TECH-ICT", "2024-28", 2024, None, ICT_2024)
    orphan = make_student("B.TECH-MECH", 2024, semester=5)

    assert engine.resolve_curriculum(db, orphan) is None
    assert engine.eligible_components(db, orphan) == []


def test_draft_curriculum_is_never_served_to_a_student(
    db, make_curriculum, make_student
):
    """Biotechnology's published structure stops at Semester II, so its import
    stays a draft. A draft must not reach students."""
    make_curriculum("B.TECH-MECH", "2024-28", 2024, None, ICT_2024,
                    status=CurriculumStatus.DRAFT)
    student = make_student("B.TECH-MECH", 2024, semester=5)

    assert engine.resolve_curriculum(db, student) is None
    assert engine.resolve_curriculum(db, student, allow_unpublished=True) is not None


def test_archived_version_still_serves_the_cohort_it_governs_when_republished(
    db, make_curriculum, make_student
):
    """Archiving is a lifecycle state, not a delete. The data survives so a
    historical cohort can always be reconstructed."""
    archived = make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, ECE_2020,
                               status=CurriculumStatus.ARCHIVED)
    student = make_student("B.TECH-ECE", 2022, semester=7)

    assert engine.resolve_curriculum(db, student) is None
    assert engine.components_for(db, archived) != []      # rows are still there

    archived.status = CurriculumStatus.PUBLISHED
    db.flush()
    assert engine.resolve_curriculum(db, student).version == "2020-24"


@pytest.mark.parametrize(
    "admission_year,expected",
    [(2019, None), (2020, "2020-24"), (2023, "2020-24"), (2024, "2024-28"),
     (2026, "2024-28")],
)
def test_batch_window_boundaries(db, make_curriculum, make_student,
                                 admission_year, expected):
    make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, ECE_2020)
    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)
    student = make_student("B.TECH-ECE", admission_year, semester=5)

    resolved = engine.resolve_curriculum(db, student)
    if expected is None:
        # Admitted before any recorded version: falls back to the newest of
        # their own programme rather than showing nothing at all.
        assert resolved.version == "2024-28"
    else:
        assert resolved.version == expected


def test_component_unlocks_in_the_semester_the_curriculum_places_it_in(
    db, make_curriculum, make_student
):
    make_curriculum("B.TECH-ICT", "2024-28", 2024, None, ICT_2024)
    student = make_student("B.TECH-ICT", 2024, semester=4)
    context = engine.build_context(db, student)

    by_code = {a.component.code: a for a in context.available}
    assert by_code["OE1"].is_unlocked and by_code["OE1"].is_current
    assert by_code["CSSI"].is_unlocked and not by_code["CSSI"].is_current
    assert not by_code["OE2-MOOC"].is_unlocked
    assert by_code["OE2-MOOC"].status_label == "Upcoming"
    assert "opens in semester 5" in by_code["OE2-MOOC"].reasons[0]


def test_a_superseded_window_is_never_used_as_a_fallback(
    db, make_curriculum, make_student
):
    """A student outside every window falls back to the version currently in
    force — never to one that has been explicitly closed off."""
    make_curriculum("B.TECH-ECE", "2016-19", 2016, 2019, ECE_2020)
    student = make_student("B.TECH-ECE", 2024, semester=4)
    assert engine.resolve_curriculum(db, student) is None

    make_curriculum("B.TECH-ECE", "2024-28", 2024, None, ECE_2024)
    assert engine.resolve_curriculum(db, student).version == "2024-28"
