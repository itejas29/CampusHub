"""What a student's dashboard may say about the semester they are in.

The dashboard once showed every student the same Semester VI picture — an Open
Elective allocated, a Core Elective to choose, an NPTEL course verified — so a
first-year saw electives their curriculum does not reach until Semester IV.

Two things keep that from coming back. The ICT curriculum that ships is pinned
here, semester by semester, to the department's own handbook (B.Tech. ICT
Curriculum Handbook, Academic Year 2024-28, w.e.f. July 2024). And the rule that
turns one curriculum slot into "pending" or "settled" is pinned separately, so a
semester with no elective slot can never report elective work.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.models.enums import ComponentType, MoocStatus
from app.seed import curriculum_import
from app.services.eligibility import reached_elective_sections
from app.services.requirements import current_mooc_registration, requirement_state
from app.services.serializers import elective_path

ICT = next(
    doc for doc in curriculum_import.load_documents()
    if doc["program"]["code"] == "B.TECH-ICT" and doc["curriculum"]["version"] == "2024-28"
)
SEMESTERS = {s["number"]: s["components"] for s in ICT["semesters"]}

CHOICE_TYPES = {"OPEN_ELECTIVE", "PROGRAM_CORE_ELECTIVE", "MOOC"}

#: Handbook "Course Outline": semester → (credits, non-core slots by type).
HANDBOOK = {
    1: (20, {}),
    2: (20, {}),
    3: (20, {"INTERNSHIP": 1}),                      # Civic and Social Service Internship
    4: (22, {"OPEN_ELECTIVE": 1}),                   # OE1, from other school
    5: (21, {"MOOC": 1, "PROGRAM_CORE_ELECTIVE": 1}),            # OE2 (NPTEL), PE1
    6: (21, {"OPEN_ELECTIVE": 1, "PROGRAM_CORE_ELECTIVE": 2}),   # OE3, PE2, PE3
    7: (24, {"INTERNSHIP": 1, "OPEN_ELECTIVE": 1,                # Summer Internship, OE4,
             "PROGRAM_CORE_ELECTIVE": 2, "PROJECT": 1}),         # PE4, PE5, Seminar
    8: (12, {"PROJECT": 1}),                         # Major / Comprehensive Project
}


def slot(component_type, *, is_elective=None):
    component_type = ComponentType(component_type)
    if is_elective is None:
        is_elective = component_type.value in CHOICE_TYPES
    return SimpleNamespace(id=1, component_type=component_type, is_elective=is_elective)


def registration(status, created_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)):
    return SimpleNamespace(status=MoocStatus(status), created_at=created_at)


# ── the curriculum that ships matches the handbook ─────────────────────────
@pytest.mark.parametrize("semester", sorted(HANDBOOK))
def test_ict_semester_credits_match_the_handbook(semester):
    credits, _slots = HANDBOOK[semester]
    assert sum(c["credits"] for c in SEMESTERS[semester]) == credits


@pytest.mark.parametrize("semester", sorted(HANDBOOK))
def test_ict_semester_carries_exactly_the_non_core_slots_the_handbook_lists(semester):
    _credits, expected = HANDBOOK[semester]
    found: dict[str, int] = {}
    for component in SEMESTERS[semester]:
        if component["component_type"] != "CORE":
            found[component["component_type"]] = found.get(component["component_type"], 0) + 1
    assert found == expected


def test_ict_programme_totals_160_credits():
    assert sum(credits for credits, _ in HANDBOOK.values()) == 160
    assert ICT["curriculum"]["total_credits"] == 160


@pytest.mark.parametrize("semester", [1, 2, 3])
def test_no_elective_slot_exists_before_semester_four(semester):
    """The whole bug in one line: nothing here for a dashboard to call pending."""
    assert not [c for c in SEMESTERS[semester]
                if c["component_type"] in CHOICE_TYPES or c["is_elective"]]


@pytest.mark.parametrize("semester", [1, 2, 3, 8])
def test_a_semester_without_elective_slots_never_reports_pending_work(semester):
    """Every slot the curriculum actually places there is settled by default —
    even for a student with no allocation and no registration at all."""
    for component in SEMESTERS[semester]:
        state = requirement_state(
            slot(component["component_type"], is_elective=component["is_elective"]),
            allocated=False,
        )
        assert state.needs_action is False
        assert state.label == "Core"


@pytest.mark.parametrize("semester,pending", [(4, 1), (5, 2), (6, 3), (7, 3)])
def test_untouched_elective_slots_are_the_only_pending_work(semester, pending):
    states = [
        requirement_state(
            slot(c["component_type"], is_elective=c["is_elective"]), allocated=False)
        for c in SEMESTERS[semester]
    ]
    assert sum(s.needs_action for s in states) == pending


# ── one slot, one verdict ──────────────────────────────────────────────────
@pytest.mark.parametrize("component_type", ["CORE", "INTERNSHIP", "PROJECT"])
def test_a_compulsory_slot_is_never_pending(component_type):
    state = requirement_state(slot(component_type), allocated=False)
    assert (state.label, state.needs_action) == ("Core", False)


@pytest.mark.parametrize("component_type", ["OPEN_ELECTIVE", "PROGRAM_CORE_ELECTIVE"])
def test_an_elective_is_pending_until_it_is_allocated(component_type):
    assert requirement_state(slot(component_type), allocated=False).needs_action is True
    settled = requirement_state(slot(component_type), allocated=True)
    assert (settled.label, settled.needs_action) == ("Allocated", False)


@pytest.mark.parametrize("component_type", ["OPEN_ELECTIVE", "PROGRAM_CORE_ELECTIVE"])
def test_submitted_preferences_take_the_slot_out_of_the_students_hands(component_type):
    """They have chosen; the next move is the coordinator's. Still calling it
    "Action needed — Choose now" sent students back to a form they had filled."""
    state = requirement_state(slot(component_type), allocated=False,
                              preferences_submitted=True)
    assert (state.label, state.needs_action) == ("Preferences submitted", False)


def test_an_allocation_outranks_the_preferences_that_led_to_it():
    state = requirement_state(slot("OPEN_ELECTIVE"), allocated=True,
                              preferences_submitted=True)
    assert state.label == "Allocated"


def test_preferences_cannot_settle_a_mooc_slot():
    state = requirement_state(slot("MOOC"), allocated=False, preferences_submitted=True)
    assert state.needs_action is True


def test_an_elective_is_not_settled_by_a_mooc_registration():
    """The two records are not interchangeable in either direction."""
    state = requirement_state(slot("OPEN_ELECTIVE"), allocated=False,
                              mooc_registration=registration("VERIFIED"))
    assert state.needs_action is True


def test_a_mooc_slot_with_no_registration_is_pending():
    state = requirement_state(slot("MOOC"), allocated=False)
    assert (state.label, state.needs_action) == ("Action needed", True)


@pytest.mark.parametrize("status", [
    "REGISTERED", "EXAM_SCHEDULED", "CERTIFICATE_UPLOADED", "VERIFIED", "COMPLETED",
])
def test_a_registered_mooc_slot_is_not_pending(status):
    """Regression: a MOOC slot never gets an elective allocation, so judging it
    by one left a verified NPTEL certificate showing "Action needed" for ever."""
    state = requirement_state(slot("MOOC"), allocated=False,
                              mooc_registration=registration(status))
    assert (state.label, state.needs_action) == (status, False)


def test_a_rejected_mooc_registration_hands_the_slot_back_to_the_student():
    state = requirement_state(slot("MOOC"), allocated=False,
                              mooc_registration=registration("REJECTED"))
    assert (state.label, state.needs_action) == ("REJECTED", True)


def test_a_mooc_slot_ignores_a_stray_allocation():
    state = requirement_state(slot("MOOC"), allocated=True)
    assert state.needs_action is True


# ── which registration speaks for the slot ─────────────────────────────────
def test_no_registrations_means_none():
    assert current_mooc_registration([]) is None


def test_a_live_registration_outranks_an_older_and_a_newer_rejection():
    day = lambda n: dt.datetime(2026, 8, n, tzinfo=dt.timezone.utc)  # noqa: E731
    live = registration("REGISTERED", day(5))
    rows = [registration("REJECTED", day(1)), live, registration("REJECTED", day(9))]
    assert current_mooc_registration(rows) is live


def test_the_most_recent_registration_wins_among_equals():
    day = lambda n: dt.datetime(2026, 8, n, tzinfo=dt.timezone.utc)  # noqa: E731
    newest = registration("REJECTED", day(9))
    assert current_mooc_registration([registration("REJECTED", day(1)), newest]) is newest


# ── where the dashboard sends the student ──────────────────────────────────
def test_each_slot_type_links_to_its_own_screen():
    def path(component_type):
        return elective_path(SimpleNamespace(id=42, component_type=ComponentType(component_type)))

    assert path("OPEN_ELECTIVE") == "/academics/open-electives/42"
    assert path("PROGRAM_CORE_ELECTIVE") == "/academics/core-electives/42"
    # The NPTEL screen has no per-component workspace.
    assert path("MOOC") == "/academics/nptel"


# ── which elective screens the sidebar offers ──────────────────────────────
def ict_slots():
    return [
        SimpleNamespace(component_type=ComponentType(c["component_type"]),
                        semester_number=number)
        for number, components in SEMESTERS.items() for c in components
    ]


@pytest.mark.parametrize("semester,sections", [
    (1, set()),
    (2, set()),
    (3, set()),                                              # CSSI is not an elective
    (4, {"open_electives"}),                                 # OE1
    (5, {"open_electives", "core_electives", "nptel"}),      # OE2 (NPTEL), PE1
    (6, {"open_electives", "core_electives", "nptel"}),
    (7, {"open_electives", "core_electives", "nptel"}),
    # Nothing new in VIII, but earlier allocations are still read there.
    (8, {"open_electives", "core_electives", "nptel"}),
])
def test_an_elective_screen_is_offered_from_the_semester_its_first_slot_sits_in(
        semester, sections):
    assert set(reached_elective_sections(ict_slots(), semester)) == sections


def test_a_curriculum_with_no_mooc_slot_never_offers_nptel():
    slots = [s for s in ict_slots() if s.component_type != ComponentType.MOOC]
    assert "nptel" not in reached_elective_sections(slots, 8)


def test_a_student_with_no_curriculum_is_offered_no_elective_screen():
    assert reached_elective_sections([], 6) == []
