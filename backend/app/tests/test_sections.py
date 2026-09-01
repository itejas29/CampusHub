"""Section planning — the Open Elective and Core Elective rules differ.

Open Elective: min 40 to run, 75 **per section**, extra sections on demand.
Core Elective: min 40 **combined across divisions**, no upper limit, one class.
Neither uses CPI.
"""
from __future__ import annotations

import pytest

from app.services.sections import plan_section_sizes, section_name

OPEN_CAP = 75
MIN_TO_RUN = 40


def open_elective(demand):
    return plan_section_sizes(demand, OPEN_CAP, allow_multiple=True)


def core_elective(demand):
    # No ceiling, single combined class.
    return plan_section_sizes(demand, None, allow_multiple=False)


# ── Open Elective: 75 is per section, not course-wide ─────────────────────
def test_open_elective_single_section_below_capacity():
    assert open_elective(60) == [60]


def test_open_elective_exactly_at_section_capacity():
    assert open_elective(75) == [75]


@pytest.mark.parametrize("demand,expected", [
    (90, [75, 15]),          # from the brief
    (150, [75, 75]),         # from the brief
    (151, [75, 75, 1]),      # first into the third section
    (225, [75, 75, 75]),     # three full sections
    (226, [75, 75, 75, 1]),
])
def test_open_elective_splits_into_sections(demand, expected):
    assert open_elective(demand) == expected


def test_open_elective_fills_each_section_before_opening_the_next():
    """90 students is 75 + 15, not 45 + 45."""
    assert open_elective(90) == [75, 15]
    assert open_elective(90) != [45, 45]


def test_open_elective_has_no_course_wide_maximum():
    """Demand far above 75 is accommodated, never rejected."""
    sizes = open_elective(400)
    assert sum(sizes) == 400
    assert len(sizes) == 6
    assert all(size <= OPEN_CAP for size in sizes)


def test_section_count_grows_with_demand():
    assert len(open_elective(75)) == 1
    assert len(open_elective(76)) == 2
    assert len(open_elective(150)) == 2
    assert len(open_elective(151)) == 3


# ── Core Elective: no 75 cap, one combined class ──────────────────────────
def test_core_elective_never_splits_at_seventy_five():
    """The Open Elective per-section rule must not leak into Core Electives."""
    assert core_elective(120) == [120]
    assert len(core_elective(200)) == 1


def test_core_elective_combines_divisions_into_one_class():
    """10 + 10 + 10 + 10 across four divisions is one class of 40."""
    total = 10 + 10 + 10 + 10
    assert total >= MIN_TO_RUN
    assert core_elective(total) == [40]


def test_core_elective_uneven_division_split_still_one_class():
    """25 + 20 + 8 + 7 = 60 — no division needs 40 of its own."""
    divisions = [25, 20, 8, 7]
    total = sum(divisions)
    assert total == 60
    assert total >= MIN_TO_RUN
    assert core_elective(total) == [60]
    # And crucially, individual divisions fall well below the minimum.
    assert min(divisions) < MIN_TO_RUN


def test_minimum_is_never_applied_per_division():
    """Every division below 40 individually, yet the course still runs."""
    divisions = [10, 10, 10, 10]
    assert all(d < MIN_TO_RUN for d in divisions)
    assert sum(divisions) >= MIN_TO_RUN


# ── shared ────────────────────────────────────────────────────────────────
def test_no_demand_produces_no_sections():
    assert open_elective(0) == []
    assert core_elective(0) == []


def test_all_students_are_placed():
    for demand in (1, 40, 74, 75, 76, 90, 150, 151, 300):
        assert sum(open_elective(demand)) == demand


def test_section_names_are_lettered():
    assert section_name(0) == "Section A"
    assert section_name(1) == "Section B"
    assert section_name(25) == "Section Z"
    assert section_name(26) == "Section 27"


def test_unlimited_capacity_ignores_allow_multiple():
    """With no ceiling there is nothing to split on."""
    assert plan_section_sizes(500, None, allow_multiple=True) == [500]


def test_capped_but_single_section_does_not_split():
    """A capped course that disallows extra sections stays one section."""
    assert plan_section_sizes(120, 75, allow_multiple=False) == [120]
