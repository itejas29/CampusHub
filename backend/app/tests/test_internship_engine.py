"""Programme-configured internship behaviour shared by CSSI and Summer."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.models.enums import ReportFrequency
from app.services.internships import compute_totals, expected_report_schedule


def _program(frequency, count=0, start=dt.date(2026, 6, 1), end=dt.date(2026, 7, 27)):
    return SimpleNamespace(
        report_frequency=frequency, expected_report_count=count,
        start_date=start, end_date=end,
    )


def _criterion(id, max_marks, weight=1):
    return SimpleNamespace(id=id, max_marks=max_marks, weight=weight)


# ── reporting cadence ─────────────────────────────────────────────────────
def test_no_schedule_when_reporting_is_disabled():
    """CSSI configures NONE and must produce no report calendar."""
    assert expected_report_schedule(_program(ReportFrequency.NONE)) == []


def test_weekly_cadence_produces_the_configured_number_of_periods():
    schedule = expected_report_schedule(_program(ReportFrequency.WEEKLY, count=8))
    assert len(schedule) == 8
    assert schedule[0]["sequence_number"] == 1
    assert schedule[0]["period_start"] == dt.date(2026, 6, 1)
    assert schedule[0]["period_end"] == dt.date(2026, 6, 7)
    assert schedule[1]["period_start"] == dt.date(2026, 6, 8)


def test_fortnightly_periods_span_two_weeks():
    schedule = expected_report_schedule(_program(ReportFrequency.FORTNIGHTLY, count=2))
    assert (schedule[0]["period_end"] - schedule[0]["period_start"]).days == 13


def test_count_is_derived_from_the_date_range_when_unset():
    schedule = expected_report_schedule(_program(ReportFrequency.WEEKLY, count=0))
    assert len(schedule) == 8   # 56 days / 7


def test_no_schedule_without_a_start_date():
    assert expected_report_schedule(
        _program(ReportFrequency.WEEKLY, count=4, start=None)
    ) == []


# ── evaluation totals ─────────────────────────────────────────────────────
def test_totals_sum_marks_against_the_rubric_maximum():
    criteria = [_criterion(1, 10), _criterion(2, 10), _criterion(3, 30)]
    total, maximum = compute_totals(criteria, {1: 8, 2: 9, 3: 24})
    assert (total, maximum) == (41.0, 50.0)


def test_weights_are_applied_to_both_total_and_maximum():
    criteria = [_criterion(1, 10, weight=2), _criterion(2, 10, weight=1)]
    total, maximum = compute_totals(criteria, {1: 5, 2: 10})
    assert (total, maximum) == (20.0, 30.0)


def test_absence_scores_zero_against_the_full_maximum():
    criteria = [_criterion(1, 10), _criterion(2, 40)]
    total, maximum = compute_totals(criteria, {1: 9, 2: 35}, is_absent=True)
    assert (total, maximum) == (0.0, 50.0)


def test_unscored_criteria_count_towards_the_maximum_but_not_the_total():
    criteria = [_criterion(1, 10), _criterion(2, 10)]
    total, maximum = compute_totals(criteria, {1: 7})
    assert (total, maximum) == (7.0, 20.0)


def test_no_letter_grade_is_derived():
    """Grade boundaries are institutional policy and are not guessed here."""
    result = compute_totals([_criterion(1, 10)], {1: 10})
    assert result == (10.0, 10.0)
    assert len(result) == 2, "compute_totals returns marks only, never a grade"
