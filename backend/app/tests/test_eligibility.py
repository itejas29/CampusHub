"""Curriculum-driven eligibility — the rules that decide what a student sees."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.models.enums import OfferingStatus, SourceScope
from app.services.eligibility import (
    check_minor_eligibility, offering_matches_scope, offering_window_open,
    student_can_access_component,
)


def _course(department_id=None, platform=None):
    return SimpleNamespace(department_id=department_id, platform=platform)


def _offering(status=OfferingStatus.OPEN, opens=None, closes=None):
    return SimpleNamespace(
        status=status, registration_opens_at=opens, registration_closes_at=closes
    )


# ── component unlocking ───────────────────────────────────────────────────
def test_component_in_current_semester_is_accessible(student, component_factory):
    result = student_can_access_component(student, component_factory(semester_number=6))
    assert result.eligible
    assert result.reasons == []


def test_component_from_an_earlier_semester_stays_accessible(student, component_factory):
    assert student_can_access_component(student, component_factory(semester_number=4)).eligible


def test_future_component_is_locked_with_an_explanation(student, component_factory):
    result = student_can_access_component(student, component_factory(semester_number=7))
    assert not result.eligible
    assert "semester 7" in result.reasons[0]


# ── source scope (the "From Other School" rules) ──────────────────────────
def test_other_department_scope_excludes_the_students_own_department(student, component_factory):
    component = component_factory(source_scope="OTHER_DEPARTMENT_FOET")
    own = _course(department_id=student.department_id)
    other = _course(department_id=student.department_id + 1)
    assert not offering_matches_scope(None, own, student, component)
    assert offering_matches_scope(None, other, student, component)


def test_other_school_scope_excludes_the_students_own_department(student, component_factory):
    component = component_factory(source_scope="OTHER_SCHOOL")
    assert not offering_matches_scope(
        None, _course(department_id=student.department_id), student, component
    )
    assert offering_matches_scope(None, _course(department_id=99), student, component)


def test_same_department_scope_requires_the_students_department(student, component_factory):
    component = component_factory(source_scope="SAME_DEPARTMENT")
    assert offering_matches_scope(
        None, _course(department_id=student.department_id), student, component
    )
    assert not offering_matches_scope(None, _course(department_id=99), student, component)


def test_external_platform_scope_requires_a_platform_course(student, component_factory):
    component = component_factory(source_scope="EXTERNAL_PLATFORM")
    assert offering_matches_scope(None, _course(platform="NPTEL"), student, component)
    assert not offering_matches_scope(None, _course(platform=None), student, component)


def test_any_scope_accepts_everything(student, component_factory):
    component = component_factory(source_scope="ANY")
    assert offering_matches_scope(None, _course(department_id=99), student, component)


# ── registration window ───────────────────────────────────────────────────
def test_window_open_only_when_offering_is_open(now):
    assert offering_window_open(_offering(), now)
    assert not offering_window_open(_offering(status=OfferingStatus.DRAFT), now)
    assert not offering_window_open(_offering(status=OfferingStatus.CLOSED), now)


def test_window_respects_open_and_close_timestamps(now):
    day = dt.timedelta(days=1)
    assert not offering_window_open(_offering(opens=now + day), now)
    assert not offering_window_open(_offering(closes=now - day), now)
    assert offering_window_open(_offering(opens=now - day, closes=now + day), now)


# ── minor eligibility (all thresholds configurable) ───────────────────────
def _minor(**overrides):
    base = dict(
        is_active=True, eligible_from_semester=3, department_id=2, min_cpi=7.0,
        max_backlogs=1, excluded_department_ids=[2], capacity=30, seats_filled=0,
        application_opens_at=None, application_closes_at=None,
    )
    base.update(overrides)
    base["seats_available"] = max(base["capacity"] - base["seats_filled"], 0)
    return SimpleNamespace(**base)


def test_eligible_student_passes_every_configured_check(student):
    assert check_minor_eligibility(student, _minor()).eligible


def test_minor_from_the_students_own_department_is_rejected(student):
    result = check_minor_eligibility(student, _minor(department_id=student.department_id))
    assert not result.eligible
    assert any("other than your own" in r for r in result.reasons)


def test_cpi_below_the_configured_threshold_is_rejected(student):
    student.cpi = 6.0
    result = check_minor_eligibility(student, _minor(min_cpi=7.0))
    assert not result.eligible
    assert any("CPI" in r for r in result.reasons)


def test_too_many_backlogs_is_rejected(student):
    student.backlog_count = 3
    result = check_minor_eligibility(student, _minor(max_backlogs=1))
    assert not result.eligible
    assert any("backlog" in r.lower() for r in result.reasons)


def test_semester_below_the_configured_start_is_rejected(student):
    student.current_semester = 2
    result = check_minor_eligibility(student, _minor(eligible_from_semester=3))
    assert not result.eligible
    assert any("semester 3" in r for r in result.reasons)


def test_full_minor_is_rejected(student):
    result = check_minor_eligibility(student, _minor(capacity=30, seats_filled=30))
    assert not result.eligible
    assert any("No seats" in r for r in result.reasons)


def test_closed_application_window_is_rejected(student, now):
    result = check_minor_eligibility(
        student, _minor(application_closes_at=now - dt.timedelta(days=1)), now
    )
    assert not result.eligible
    assert any("closed" in r for r in result.reasons)


def test_thresholds_left_unset_are_not_enforced(student):
    student.cpi = None
    student.backlog_count = 9
    assert check_minor_eligibility(
        student, _minor(min_cpi=None, max_backlogs=None)
    ).eligible
