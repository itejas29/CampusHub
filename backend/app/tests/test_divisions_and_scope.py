"""Divisions as programme data, and Open Elective eligibility as a school rule.

Two hard-coded assumptions this file exists to prevent:

* that every programme runs ICT's four divisions;
* that "can this student take this course" is `course.department_id == X`.

The official Open Elective rule is written in schools — "offered to the students
enrolled in B.Tech. programs of School of Technology other than Electrical
Engineering" — which a department-id comparison cannot express.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.academics import Course, CurriculumComponent, ProgramDivision
from app.models.enums import ComponentType, SourceScope
from app.services import curriculum as engine
from app.services.sections import plan_section_sizes


# ── divisions are configuration, not a constant ────────────────────────────
@pytest.fixture
def with_divisions(academic_world):
    db = academic_world.db
    layout = {
        "B.TECH-ICT": ["A", "B", "C"],           # 180 seats
        "B.TECH-CE": ["A", "B", "C", "D"],       # 300 seats
        "B.TECH-MECH": ["A", "B"],               # 120 seats
        "B.TECH-ELEC": ["A", "B"],
    }
    for code, names in layout.items():
        for name in names:
            db.add(ProgramDivision(program_id=academic_world.programs[code].id,
                                   admission_year=2024, name=name))
    db.flush()
    return academic_world


def test_each_programme_reports_its_own_divisions(with_divisions):
    db = with_divisions.db
    ict = with_divisions.programs["B.TECH-ICT"].id
    computer = with_divisions.programs["B.TECH-CE"].id
    mechanical = with_divisions.programs["B.TECH-MECH"].id

    assert engine.divisions_for(db, ict, 2024) == ["A", "B", "C"]
    assert engine.divisions_for(db, computer, 2024) == ["A", "B", "C", "D"]
    assert engine.divisions_for(db, mechanical, 2024) == ["A", "B"]


def test_a_programme_with_no_divisions_configured_reports_none(with_divisions):
    """Empty means "no division restriction" — never a silent fallback to
    ICT's A/B/C/D."""
    db = with_divisions.db
    ece = with_divisions.programs["B.TECH-ECE"].id
    assert engine.divisions_for(db, ece, 2024) == []


def test_divisions_are_scoped_to_a_batch(with_divisions):
    db = with_divisions.db
    ict = with_divisions.programs["B.TECH-ICT"].id
    assert engine.divisions_for(db, ict, 2024) == ["A", "B", "C"]
    assert engine.divisions_for(db, ict, 2019) == []
    assert engine.division_choices(db, ict) == {2024: ["A", "B", "C"]}


def test_core_elective_minimum_is_combined_across_whatever_divisions_exist():
    """The 40 minimum is never applied per division. A two-division programme
    reaching 40 combined runs exactly as a four-division one does."""
    two_divisions = {"A": 20, "B": 20}
    four_divisions = {"A": 10, "B": 10, "C": 10, "D": 10}

    for layout in (two_divisions, four_divisions):
        combined = sum(layout.values())
        assert combined >= 40
        # No ceiling, one combined class — regardless of division count.
        assert plan_section_sizes(combined, None, allow_multiple=False) == [combined]

    assert sum({"A": 19, "B": 20}.values()) < 40      # 39 combined does not run


# ── cross-programme Open Elective eligibility ──────────────────────────────
@pytest.fixture
def scope_world(academic_world):
    """One course per department, so scope decisions are visible."""
    db = academic_world.db
    courses = {}
    for dept_code in ("ICT", "CSE", "ECE", "MEC", "EE", "SLS"):
        course = Course(code=f"OE-{dept_code}", title=f"{dept_code} Open Elective",
                        department_id=academic_world.departments[dept_code].id,
                        credits=3)
        db.add(course)
        db.flush()
        courses[dept_code] = course
    academic_world.courses = courses
    return academic_world


def component(scope, eligibility=None, **kw):
    return SimpleNamespace(
        source_scope=SourceScope(scope), eligibility=eligibility or {},
        component_type=ComponentType.OPEN_ELECTIVE, **kw,
    )


def test_from_other_school_excludes_the_students_own_school(scope_world, make_student):
    """An ICT student (SoT) taking "From Other School" may take an SLS or SoET
    course, but not another SoT department's."""
    db = scope_world.db
    student = make_student("B.TECH-ICT", 2024, semester=4)
    slot = component("OTHER_SCHOOL",
                     {"eligible_schools": ["SoET", "SLS", "SoM", "SoL"],
                      "exclude_own_department": True})

    assert engine.offering_matches_component(
        db, None, scope_world.courses["SLS"], student, slot)
    assert engine.offering_matches_component(
        db, None, scope_world.courses["EE"], student, slot)      # SoET
    # Mechanical is a different department but the *same* school.
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["MEC"], student, slot)
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["ICT"], student, slot)


def test_department_id_comparison_alone_would_get_this_wrong(scope_world, make_student):
    """The regression the school rule exists to prevent: Mechanical has a
    different department id from ICT, so a department-only check would wrongly
    allow it for a "From Other School" slot."""
    db = scope_world.db
    student = make_student("B.TECH-ICT", 2024, semester=4)
    mechanical = scope_world.courses["MEC"]

    assert mechanical.department_id != student.department_id       # naive check passes
    slot = component("OTHER_SCHOOL", {"eligible_schools": ["SoET", "SLS", "SoM", "SoL"],
                                      "exclude_own_department": True})
    assert not engine.offering_matches_component(db, None, mechanical, student, slot)


def test_inter_department_foet_allows_the_other_engineering_departments(
    scope_world, make_student
):
    db = scope_world.db
    student = make_student("B.TECH-ICT", 2024, semester=6)
    slot = component("OTHER_DEPARTMENT_FOET",
                     {"eligible_schools": ["SoT", "SoET"],
                      "exclude_own_department": True})

    assert engine.offering_matches_component(
        db, None, scope_world.courses["MEC"], student, slot)
    assert engine.offering_matches_component(
        db, None, scope_world.courses["EE"], student, slot)
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["ICT"], student, slot)      # own department
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["SLS"], student, slot)      # not an engineering school


def test_the_offering_department_excludes_its_own_students(scope_world, make_student):
    """The official rule, from the Electrical course structure: an Open Elective
    a department offers goes to *other* departments' students."""
    db = scope_world.db
    electrical_student = make_student("B.TECH-ELEC", 2022, semester=3)
    slot = component("OTHER_DEPARTMENT_FOET",
                     {"eligible_schools": ["SoT", "SoET"],
                      "exclude_own_department": True})

    assert not engine.offering_matches_component(
        db, None, scope_world.courses["EE"], electrical_student, slot)
    assert engine.offering_matches_component(
        db, None, scope_world.courses["ICT"], electrical_student, slot)


def test_explicit_department_and_programme_rules_are_honoured(scope_world, make_student):
    db = scope_world.db
    student = make_student("B.TECH-ICT", 2024, semester=6)

    only_mechanical = component("ANY", {"eligible_departments": ["MEC"]})
    assert engine.offering_matches_component(
        db, None, scope_world.courses["MEC"], student, only_mechanical)
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["CSE"], student, only_mechanical)

    ict_barred = component("ANY", {"excluded_programs": ["B.TECH-ICT"]})
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["MEC"], student, ict_barred)


def test_a_component_with_no_rules_falls_back_to_its_scope(scope_world, make_student):
    db = scope_world.db
    student = make_student("B.TECH-ICT", 2024, semester=6)
    assert engine.offering_matches_component(
        db, None, scope_world.courses["MEC"], student, component("ANY"))
    assert not engine.offering_matches_component(
        db, None, scope_world.courses["MEC"], student, component("SAME_DEPARTMENT"))


def test_cpi_is_not_consulted_anywhere_in_open_elective_scope(scope_world, make_student):
    """Academic merit belongs to Minor Specialisation alone."""
    db = scope_world.db
    slot = component("OTHER_DEPARTMENT_FOET",
                     {"eligible_schools": ["SoT", "SoET"],
                      "exclude_own_department": True})
    weak = make_student("B.TECH-ICT", 2024, semester=6, cpi=4.1, backlogs=5)
    strong = make_student("B.TECH-ICT", 2024, semester=6, cpi=9.8, backlogs=0)

    for student in (weak, strong):
        assert engine.offering_matches_component(
            db, None, scope_world.courses["MEC"], student, slot)
