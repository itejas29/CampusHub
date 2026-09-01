"""Every researched programme, asserted against its official curriculum.

These tests pin the *findings* of the Phase 3B research (docs/PHASE3B-RESEARCH.md)
to the data that ships. They are what stops a later edit quietly flattening every
programme back into ICT's shape — the single most likely way this feature decays.

They read the import documents directly, so they are fast and need no database.
"""
from __future__ import annotations

import pytest

from app.models.enums import ComponentType
from app.seed import curriculum_import

DOCS = {}
for _doc in curriculum_import.load_documents():
    DOCS[f"{_doc['program']['code']}:{_doc['curriculum']['version']}"] = _doc

#: Every B.Tech programme PDEU currently runs, verified against the university's
#: own course catalogue and the 2026-27 admission seat matrix.
EXPECTED_PROGRAMS = {
    "B.TECH-ICT": ("ICT", "SoT"),
    "B.TECH-CE": ("CSE", "SoT"),
    "B.TECH-CSBS": ("CSE", "SoT"),
    "B.TECH-ECE": ("ECE", "SoT"),
    "B.TECH-CIVIL": ("CIV", "SoT"),
    "B.TECH-MECH": ("MEC", "SoT"),
    "B.TECH-CHEM": ("CHM", "SoET"),
    "B.TECH-ELEC": ("EE", "SoET"),
    "B.TECH-PETRO": ("PTE", "SoET"),
    "B.TECH-BIO": ("BIO", "SoET"),
}


def components(key, component_type=None):
    doc = DOCS[key]
    out = []
    for semester in doc["semesters"]:
        for item in semester["components"]:
            if component_type is None or item["component_type"] == component_type:
                out.append((semester["number"], item["code"], item))
    return out


def semesters_of(key, component_type):
    return sorted(sem for sem, _code, _i in components(key, component_type))


# ── programmes ─────────────────────────────────────────────────────────────
def test_every_verified_programme_has_a_curriculum():
    found = {doc["program"]["code"] for doc in DOCS.values()}
    assert found == set(EXPECTED_PROGRAMS)


@pytest.mark.parametrize("code,expected", sorted(EXPECTED_PROGRAMS.items()))
def test_programme_sits_in_the_right_department_and_school(code, expected):
    doc = next(d for d in DOCS.values() if d["program"]["code"] == code)
    department = doc["program"]["department"]
    assert (department["code"], department["school"]) == expected


def test_no_programme_the_university_does_not_run():
    """The brief's list included three programmes PDEU does not offer under
    those names. None of them may exist as a programme."""
    names = " ".join(d["program"]["name"].lower() for d in DOCS.values())
    assert "automobile engineering" not in names
    # CSE is the department; the programme it runs is Computer Engineering.
    codes = {d["program"]["code"] for d in DOCS.values()}
    assert "B.TECH-CSE" not in codes
    assert "B.TECH-CE" in codes


def test_automobile_engineering_survives_only_as_a_mechanical_elective():
    options = [
        option["title"]
        for _sem, _code, item in components("B.TECH-MECH:2024-28")
        for option in item.get("options", [])
    ]
    assert "Automobile Engineering" in options


# ── source traceability ────────────────────────────────────────────────────
@pytest.mark.parametrize("key", sorted(DOCS))
def test_every_curriculum_records_its_official_source(key):
    source = DOCS[key]["source"]
    assert source["url"].startswith("https://api.pdeu.ac.in/")
    assert source["title"] and source["publisher"] and source["retrieved_at"]
    assert source["confidence"] in {
        "CONFIRMED_OFFICIAL_SOURCE", "PARTIAL_SOURCE",
    }


def test_biotechnology_is_marked_partial_and_never_published():
    doc = DOCS["B.TECH-BIO:2023"]
    assert doc["source"]["confidence"] == "PARTIAL_SOURCE"
    assert doc["curriculum"]["status"] == "DRAFT"
    assert "Semester I–II only" in doc["curriculum"]["incomplete_note"]


def test_divisions_are_labelled_as_derived_not_cited():
    """No PDEU document states division counts. The data must say so."""
    for doc in DOCS.values():
        assert doc["divisions"]["confidence"] == "DERIVED_FROM_INTAKE"
        assert doc["divisions"]["names"]


def test_division_counts_differ_by_programme():
    """A/B/C/D is ICT's shape, not a constant."""
    counts = {
        doc["program"]["code"]: len(doc["divisions"]["names"])
        for doc in DOCS.values()
    }
    assert counts["B.TECH-CE"] == 4        # 300 seats
    assert counts["B.TECH-ICT"] == 3       # 180 seats
    assert counts["B.TECH-CSBS"] == 1      # 60 seats
    assert len(set(counts.values())) > 1


# ── elective structure, per programme ──────────────────────────────────────
#: (key, Open Elective semesters, MOOC semesters, Program Elective semesters)
ELECTIVE_SHAPE = [
    ("B.TECH-ICT:2024-28", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    ("B.TECH-CE:2024-28", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    ("B.TECH-CSBS:2024-28", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    ("B.TECH-ECE:2024-28", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    ("B.TECH-CIVIL:2024-28", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    # Mechanical distributes its electives 1 / 1 / 3, not 1 / 2 / 2.
    ("B.TECH-MECH:2024-28", [4, 6, 7], [5], [5, 6, 7, 7, 7]),
    ("B.TECH-CHEM:2024", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    ("B.TECH-PETRO:2024-28", [4, 6, 7], [5], [5, 6, 6, 7, 7]),
    # The 2020 model: Open Electives a semester earlier, and no MOOC slot.
    ("B.TECH-ECE:2020-24", [3, 4, 5, 6], [], [5, 5, 6, 6, 7, 7, 7]),
    ("B.TECH-ELEC:2020-24", [3, 4, 5, 6], [], [5, 6, 6, 7, 7]),
]


@pytest.mark.parametrize("key,open_sems,mooc_sems,pe_sems", ELECTIVE_SHAPE)
def test_elective_structure_matches_the_official_document(key, open_sems, mooc_sems,
                                                          pe_sems):
    assert semesters_of(key, ComponentType.OPEN_ELECTIVE.value) == open_sems
    assert semesters_of(key, ComponentType.MOOC.value) == mooc_sems
    assert semesters_of(key, ComponentType.PROGRAM_CORE_ELECTIVE.value) == pe_sems


def test_mechanical_elective_distribution_is_not_ict_s():
    """The regression that would matter most: flattening every programme into
    ICT's 1 / 2 / 2 elective pattern."""
    ict = semesters_of("B.TECH-ICT:2024-28", "PROGRAM_CORE_ELECTIVE")
    mechanical = semesters_of("B.TECH-MECH:2024-28", "PROGRAM_CORE_ELECTIVE")
    assert ict != mechanical
    assert mechanical.count(7) == 3 and ict.count(7) == 2


# ── MOOC / NPTEL applicability ─────────────────────────────────────────────
def test_mooc_is_present_only_where_the_curriculum_says_so():
    with_mooc = {k for k in DOCS if semesters_of(k, ComponentType.MOOC.value)}
    without = set(DOCS) - with_mooc
    assert "B.TECH-ECE:2020-24" in without      # the 2020 scheme has no MOOC slot
    assert "B.TECH-ELEC:2020-24" in without
    assert "B.TECH-ICT:2024-28" in with_mooc


def test_mooc_slot_is_an_external_platform_component():
    for key in DOCS:
        for _sem, _code, item in components(key, ComponentType.MOOC.value):
            assert item["source_scope"] == "EXTERNAL_PLATFORM"
            assert "MOOC" in item["title"] or "NPTEL" in item["title"]


# ── internships ────────────────────────────────────────────────────────────
def test_petroleum_runs_a_rural_internship_not_cssi():
    """Confirmed from the official syllabus: Petroleum's Semester III component
    is 24INT152T Rural Internship, and the Academic Rules list Rural Internship
    as a distinct internship type."""
    codes = {c for _s, c, _i in components("B.TECH-PETRO:2024-28",
                                           ComponentType.INTERNSHIP.value)}
    assert "RI" in codes and "CSSI" not in codes


def test_biotechnology_places_its_social_internship_in_semester_two():
    sems = [s for s, c, _i in components("B.TECH-BIO:2023",
                                         ComponentType.INTERNSHIP.value)
            if c == "CSSI"]
    assert sems == [2]


def test_the_2020_scheme_has_no_cssi_and_no_summer_internship():
    for key in ("B.TECH-ECE:2020-24", "B.TECH-ELEC:2020-24"):
        codes = {c for _s, c, _i in components(key, ComponentType.INTERNSHIP.value)}
        assert "CSSI" not in codes and "SI" not in codes
        assert "IT" in codes         # Industrial Training in Semester VI instead


@pytest.mark.parametrize("key", [
    "B.TECH-ICT:2024-28", "B.TECH-CE:2024-28", "B.TECH-CSBS:2024-28",
    "B.TECH-ECE:2024-28", "B.TECH-CIVIL:2024-28", "B.TECH-MECH:2024-28",
    "B.TECH-CHEM:2024",
])
def test_cssi_is_credited_in_semester_three_where_it_applies(key):
    """The Academic Rules place CSSI at the end of Semester II, with submission
    and viva at the start of the next odd semester — which is why every current
    course structure credits it in Semester III."""
    sems = [s for s, c, _i in components(key, ComponentType.INTERNSHIP.value)
            if c == "CSSI"]
    assert sems == [3]


def test_summer_internship_sits_in_semester_seven_where_it_exists():
    for key in DOCS:
        sems = [s for s, c, _i in components(key, ComponentType.INTERNSHIP.value)
                if c == "SI"]
        assert sems in ([], [7]), f"{key} places Summer Internship at {sems}"


# ── projects ───────────────────────────────────────────────────────────────
def test_every_complete_curriculum_ends_in_a_final_project():
    for key, doc in DOCS.items():
        if doc["source"]["confidence"] == "PARTIAL_SOURCE":
            continue
        finals = [(s, i) for s, c, i in components(key, ComponentType.PROJECT.value)
                  if c == "MP"]
        assert len(finals) == 1, key
        semester, item = finals[0]
        assert semester == 8
        assert item["credits"] >= 10


# ── cross-programme Open Elective rules ────────────────────────────────────
def test_open_electives_carry_declarative_school_level_rules():
    """The official rule is written in schools and departments, which
    `course.department_id == X` cannot express."""
    for key in DOCS:
        for _sem, code, item in components(key, ComponentType.OPEN_ELECTIVE.value):
            rules = item.get("eligibility")
            if not rules:
                # CSBS prescribes its Open Elective courses by name; there is no
                # basket to constrain.
                assert key.startswith("B.TECH-CSBS"), f"{key} {code} has no rule"
                continue
            assert rules["exclude_own_department"] is True
            assert rules["eligible_schools"]
            assert "pdeu" in rules["rule_source"].lower() or "elective" in \
                   rules["rule_source"].lower()


def test_from_other_school_excludes_the_programmes_own_school():
    for key, doc in DOCS.items():
        own_school = doc["program"]["department"]["school"]
        for _sem, _code, item in components(key, ComponentType.OPEN_ELECTIVE.value):
            if item["source_scope"] != "OTHER_SCHOOL":
                continue
            assert own_school not in item["eligibility"]["eligible_schools"]


def test_csbs_open_electives_are_prescribed_not_a_basket():
    prescribed = [item for _s, _c, item
                  in components("B.TECH-CSBS:2024-28",
                                ComponentType.OPEN_ELECTIVE.value)]
    assert prescribed
    for item in prescribed:
        assert item["selection_mode"] == "DIRECT"
        assert item["confidence"] == "REQUIRES_FACULTY_CONFIRMATION"


# ── flagged uncertainty ────────────────────────────────────────────────────
def test_uncertain_readings_are_flagged_rather_than_asserted():
    """Where two official documents disagree, or a slot is ambiguous, the data
    must say so instead of turning a guess into a rule."""
    flagged = [
        (key, item["code"], item["note"])
        for key in DOCS
        for _sem, _code, item in components(key)
        if item.get("confidence") == "REQUIRES_FACULTY_CONFIRMATION"
    ]
    keys = {k for k, _c, _n in flagged}
    assert "B.TECH-MECH:2024-28" in keys     # named Sem IV Open Elective
    assert "B.TECH-CHEM:2024" in keys        # "Program Elective 3" printed twice
    assert "B.TECH-CSBS:2024-28" in keys     # prescribed Open Electives
    assert "B.TECH-BIO:2023" in keys         # Semester II social internship
    for _key, _code, note in flagged:
        assert note and len(note) > 20


# ── shared course catalogue ────────────────────────────────────────────────
def test_common_courses_are_shared_rather_than_duplicated_per_programme():
    catalogue = {c["code"]: c for c in curriculum_import.load_catalogue()}
    shared = [c for c in catalogue.values() if c["shared"]]
    assert len(shared) > 20
    titles = [c["title"] for c in shared]
    assert any("Environment Science" in t for t in titles)
    # A shared course belongs to no single department.
    assert all(c["department"] is None for c in shared)


def test_course_codes_are_unique_across_the_catalogue():
    catalogue = curriculum_import.load_catalogue()
    codes = [c["code"] for c in catalogue]
    assert len(codes) == len(set(codes))


def test_every_course_is_classified_theory_practical_or_project():
    for course in curriculum_import.load_catalogue():
        assert course["delivery"] in {
            "THEORY", "PRACTICAL", "THEORY_PRACTICAL", "PROJECT",
        }
        assert course["category"]


# ── internship applicability is configuration, not code ────────────────────
def test_every_internship_component_maps_to_a_known_delivery_shape():
    """One engine, many programmes. A new internship code must be given a
    configuration rather than silently producing no programme at all."""
    from app.seed.run import INTERNSHIP_TEMPLATES

    #: Industrial Orientation is a 3-week, zero-credit visit with no document
    #: lifecycle in any official source, so it stays a curriculum component only.
    NO_PROGRAMME = {"IO"}

    codes = {
        code for key in DOCS
        for _sem, code, _item in components(key, ComponentType.INTERNSHIP.value)
    }
    unmapped = codes - set(INTERNSHIP_TEMPLATES) - NO_PROGRAMME
    assert not unmapped, f"internship components with no delivery config: {unmapped}"


def test_internship_delivery_differs_where_the_curricula_differ():
    from app.seed.run import INTERNSHIP_TEMPLATES

    cssi = INTERNSHIP_TEMPLATES["CSSI"]
    summer = INTERNSHIP_TEMPLATES["SI"]
    training = INTERNSHIP_TEMPLATES["IT"]

    # CSSI is group-based, NGO-only and closes after its target semester.
    assert cssi["group"] and cssi["orgs"] == ["NGO"] and cssi["closes_after_target"]
    # Summer Internship is individual, industry-hosted, weekly-reported.
    assert not summer["group"] and summer["industry_mentor"]
    assert summer["report_count"] == 8
    # Industrial Training is the 2020-scheme equivalent, on a different cadence.
    assert training["reports"] != summer["reports"]


def test_petroleums_rural_internship_is_coordinated_through_the_cssi_scope():
    """It fills the same slot under the same Academic Rules clause, so it must
    be coordinated by the same scope rather than becoming an orphan module."""
    from app.models.enums import CoordinationDomain
    from app.seed.run import INTERNSHIP_TEMPLATES

    rural = INTERNSHIP_TEMPLATES["RI"]
    assert rural["domain"] == CoordinationDomain.CSSI
    assert rural["label"] == "Rural Internship"       # still distinguishable
