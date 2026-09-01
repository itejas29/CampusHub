"""The allocation engine — including the guarantee that the unconfigured merit
rule can never run."""
from __future__ import annotations

import datetime as dt

import pytest

from app.core.errors import BusinessRuleError, ValidationError
from app.services.allocation import (
    Candidate, SeatPool, available_strategies, get_strategy,
)
from app.services.allocation.strategies import MeritAllocation

BASE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _candidate(student_id, offering_id, order, minutes=0):
    return Candidate(
        student_id=student_id, course_offering_id=offering_id,
        preference_order=order, submitted_at=BASE + dt.timedelta(minutes=minutes),
    )


def _pools(**capacities):
    return {
        int(key.lstrip("o")): SeatPool(course_offering_id=int(key.lstrip("o")),
                                       capacity=value)
        for key, value in capacities.items()
    }


# ── registry ──────────────────────────────────────────────────────────────
def test_registry_returns_instances_not_classes():
    strategy = get_strategy("preference_order")
    assert not isinstance(strategy, type)
    assert callable(strategy.allocate)


def test_unknown_strategy_is_reported_clearly():
    with pytest.raises(ValidationError) as exc:
        get_strategy("does-not-exist")
    assert "Available:" in str(exc.value)


def test_merit_is_declared_but_unavailable():
    """It must be listable in the UI yet impossible to execute."""
    merit = get_strategy("merit")
    assert merit.is_available is False
    assert merit in available_strategies() or any(
        s.key == "merit" for s in available_strategies()
    )


def test_merit_refuses_to_run_even_if_invoked_directly():
    with pytest.raises(BusinessRuleError) as exc:
        MeritAllocation().allocate([], {}, config=None)
    assert "not been configured" in str(exc.value)


# ── manual ────────────────────────────────────────────────────────────────
def test_manual_strategy_allocates_nothing():
    outcome = get_strategy("manual").allocate(
        [_candidate(1, 10, 1)], _pools(o10=5)
    )
    assert outcome.awards == []
    assert outcome.unallocated_student_ids == [1]


# ── preference order ──────────────────────────────────────────────────────
def test_first_choices_are_granted_when_seats_allow():
    outcome = get_strategy("preference_order").allocate(
        [_candidate(1, 10, 1), _candidate(2, 11, 1)], _pools(o10=5, o11=5)
    )
    assert outcome.allocated_count == 2
    assert all(a.preference_order_granted == 1 for a in outcome.awards)


def test_earlier_submission_wins_a_contested_seat():
    outcome = get_strategy("preference_order").allocate(
        [
            _candidate(1, 10, 1, minutes=30),   # later
            _candidate(2, 10, 1, minutes=0),    # earlier — should win
            _candidate(1, 11, 2, minutes=30),   # student 1's fallback
        ],
        _pools(o10=1, o11=5),
    )
    seated = {a.student_id: a.course_offering_id
              for a in outcome.awards if not a.waitlisted}
    assert seated[2] == 10, "earliest submitter takes the single seat"
    assert seated[1] == 11, "later submitter falls to their second preference"


def test_a_student_is_never_seated_twice():
    outcome = get_strategy("preference_order").allocate(
        [_candidate(1, 10, 1), _candidate(1, 11, 2), _candidate(1, 12, 3)],
        _pools(o10=5, o11=5, o12=5),
    )
    seated = [a for a in outcome.awards if not a.waitlisted]
    assert len(seated) == 1


def test_students_with_no_free_preference_are_waitlisted():
    outcome = get_strategy("preference_order").allocate(
        [_candidate(1, 10, 1, 0), _candidate(2, 10, 1, 10)], _pools(o10=1)
    )
    assert outcome.allocated_count == 1
    waitlisted = [a for a in outcome.awards if a.waitlisted]
    assert [a.student_id for a in waitlisted] == [2]
    assert outcome.unallocated_student_ids == [2]


def test_waitlisting_can_be_disabled_by_config():
    outcome = get_strategy("preference_order").allocate(
        [_candidate(1, 10, 1, 0), _candidate(2, 10, 1, 10)],
        _pools(o10=1), config={"waitlist_unallocated": False},
    )
    assert all(not a.waitlisted for a in outcome.awards)
    assert outcome.unallocated_student_ids == [2]


def test_seats_already_taken_are_respected():
    pools = {10: SeatPool(course_offering_id=10, capacity=2, seats_taken=2)}
    outcome = get_strategy("preference_order").allocate([_candidate(1, 10, 1)], pools)
    assert outcome.allocated_count == 0


def test_input_pools_are_not_mutated():
    pools = _pools(o10=5)
    get_strategy("preference_order").allocate([_candidate(1, 10, 1)], pools)
    assert pools[10].capacity == 5
    assert pools[10].seats_taken == 0


def test_outcome_reports_one_note_per_round():
    outcome = get_strategy("preference_order").allocate(
        [_candidate(1, 10, 1), _candidate(1, 11, 2)], _pools(o10=1, o11=1)
    )
    assert len(outcome.notes) == 2
