"""Minor Specialisation ranking.

Minor Specialisation is the ONLY module allowed to rank on CPI. The formula
itself is never assumed — each programme declares its own criteria — so these
tests fix the *mechanism*, not any particular institute rule.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.core.errors import BusinessRuleError
from app.services.minors import (
    DEFAULT_DIRECTIONS, RANKABLE_FIELDS, _sort_key, ranking_policy,
)

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def application(app_id, *, cpi=None, backlogs=0, preference=1, minutes=0, semester=5):
    return SimpleNamespace(
        id=app_id, cpi_at_application=cpi, backlogs_at_application=backlogs,
        preference_order=preference, semester_at_application=semester,
        submitted_at=NOW + dt.timedelta(minutes=minutes),
    )


def program(rules):
    return SimpleNamespace(name="Minor in AI", code="MIN-AI", rules=rules)


def order(applications, criteria):
    """Return application ids in the order the policy ranks them."""
    return [a.id for a in sorted(applications, key=lambda a: _sort_key(a, criteria))]


# ── the policy must be declared ───────────────────────────────────────────
def test_unconfigured_programme_refuses_to_rank():
    """No formula is invented when the department has not published one."""
    with pytest.raises(BusinessRuleError) as excinfo:
        ranking_policy(program({}))
    assert "no ranking policy configured" in str(excinfo.value).lower()


def test_ranking_policy_rejects_unknown_field():
    with pytest.raises(BusinessRuleError):
        ranking_policy(program({"ranking": {"criteria": [{"field": "attendance"}]}}))


def test_ranking_policy_rejects_bad_direction():
    with pytest.raises(BusinessRuleError):
        ranking_policy(program(
            {"ranking": {"criteria": [{"field": "cpi", "direction": "sideways"}]}}
        ))


def test_direction_defaults_per_field():
    """A criterion may omit its direction; the sensible default applies."""
    criteria = ranking_policy(program({"ranking": {"criteria": [{"field": "cpi"}]}}))
    assert criteria == [{"field": "cpi", "direction": "desc"}]
    assert DEFAULT_DIRECTIONS["backlog_count"] == "asc"


def test_every_rankable_field_is_documented():
    assert set(RANKABLE_FIELDS) == set(DEFAULT_DIRECTIONS)


# ── the declared policy is what actually orders applicants ────────────────
def test_higher_cpi_ranks_first():
    criteria = [{"field": "cpi", "direction": "desc"}]
    applicants = [application(1, cpi=7.9), application(2, cpi=9.1),
                  application(3, cpi=8.4)]
    assert order(applicants, criteria) == [2, 3, 1]


def test_ascending_criterion_is_honoured():
    """A programme may rank on fewest backlogs instead of highest CPI."""
    criteria = [{"field": "backlog_count", "direction": "asc"}]
    applicants = [application(1, backlogs=3), application(2, backlogs=0),
                  application(3, backlogs=1)]
    assert order(applicants, criteria) == [2, 3, 1]


def test_tie_breaks_fall_through_in_declared_order():
    criteria = [{"field": "cpi", "direction": "desc"},
                {"field": "backlog_count", "direction": "asc"},
                {"field": "preference_order", "direction": "asc"}]
    tied = [
        application(1, cpi=8.5, backlogs=2, preference=1),
        application(2, cpi=8.5, backlogs=0, preference=2),
        application(3, cpi=8.5, backlogs=0, preference=1),
    ]
    # Same CPI → fewest backlogs → then the student's own preference order.
    assert order(tied, criteria) == [3, 2, 1]


def test_missing_cpi_never_outranks_a_recorded_one():
    """An absent CPI must not win a seat by sorting as zero or infinity."""
    criteria = [{"field": "cpi", "direction": "desc"}]
    applicants = [application(1, cpi=None), application(2, cpi=6.0)]
    assert order(applicants, criteria) == [2, 1]


def test_ranking_is_deterministic_for_identical_applicants():
    criteria = [{"field": "cpi", "direction": "desc"}]
    a, b = application(7, cpi=8.0, minutes=5), application(4, cpi=8.0, minutes=5)
    assert order([a, b], criteria) == order([b, a], criteria) == [4, 7]


def test_earlier_submission_wins_when_declared():
    criteria = [{"field": "submitted_at", "direction": "asc"}]
    applicants = [application(1, minutes=90), application(2, minutes=5)]
    assert order(applicants, criteria) == [2, 1]


def test_a_programme_may_rank_without_cpi_at_all():
    """CPI is permitted here — it is not compulsory here either."""
    criteria = ranking_policy(program({"ranking": {"criteria": [
        {"field": "preference_order", "direction": "asc"},
        {"field": "submitted_at", "direction": "asc"},
    ]}}))
    assert all(c["field"] != "cpi" for c in criteria)
    applicants = [application(1, preference=2, minutes=0),
                  application(2, preference=1, minutes=99)]
    assert order(applicants, criteria) == [2, 1]
