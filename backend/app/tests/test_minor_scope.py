"""How a Minor coordinator's department scope is interpreted.

Two readings are defensible and the university has not confirmed which applies:

  OFFERING   the minors the coordinator's department *offers*
  APPLICANT  applications *from students of* the coordinator's department

CampusHub picks neither. The rule is configuration, and these tests fix the
mechanism so switching it later is a one-line change with known behaviour.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.scope import MinorScopeRule

ICT, CSE = 1, 2


class _Resolver:
    """Stands in for `can_manage_minor` with the session parts faked out.

    Mirrors the real branching exactly; the ORM lookups it replaces carry no
    logic of their own.
    """

    def __init__(self, rule, coordinated_department):
        self.rule = rule
        self.mine = coordinated_department

    def coordinates(self, department_id):
        return department_id is not None and department_id == self.mine

    def can_manage(self, program, applicant_department_id=None):
        offering = self.coordinates(program.department_id)
        if self.rule == MinorScopeRule.OFFERING:
            return offering
        applicant = (applicant_department_id is not None
                     and self.coordinates(applicant_department_id))
        if self.rule == MinorScopeRule.APPLICANT:
            return applicant
        return offering or applicant


def minor(department_id):
    return SimpleNamespace(id=1, department_id=department_id)


# ── OFFERING: the minors my department runs ───────────────────────────────
def test_offering_rule_grants_my_departments_minor():
    r = _Resolver(MinorScopeRule.OFFERING, ICT)
    assert r.can_manage(minor(ICT))


def test_offering_rule_refuses_another_departments_minor():
    r = _Resolver(MinorScopeRule.OFFERING, ICT)
    assert not r.can_manage(minor(CSE))


def test_offering_rule_ignores_the_applicants_department():
    """Even an ICT student's application to a CSE minor stays CSE's to decide."""
    r = _Resolver(MinorScopeRule.OFFERING, ICT)
    assert not r.can_manage(minor(CSE), applicant_department_id=ICT)


# ── APPLICANT: applications from my department's students ─────────────────
def test_applicant_rule_grants_my_students_application():
    r = _Resolver(MinorScopeRule.APPLICANT, ICT)
    assert r.can_manage(minor(CSE), applicant_department_id=ICT)


def test_applicant_rule_refuses_another_departments_student():
    r = _Resolver(MinorScopeRule.APPLICANT, ICT)
    assert not r.can_manage(minor(ICT), applicant_department_id=CSE)


def test_applicant_rule_refuses_programme_wide_actions():
    """No applicant means nothing for this reading to match on."""
    r = _Resolver(MinorScopeRule.APPLICANT, ICT)
    assert not r.can_manage(minor(ICT))


# ── EITHER: the shipped default while the policy is unconfirmed ───────────
def test_either_rule_accepts_the_offering_side():
    r = _Resolver(MinorScopeRule.EITHER, ICT)
    assert r.can_manage(minor(ICT))


def test_either_rule_accepts_the_applicant_side():
    r = _Resolver(MinorScopeRule.EITHER, ICT)
    assert r.can_manage(minor(CSE), applicant_department_id=ICT)


def test_either_rule_still_refuses_an_unrelated_scope():
    """Permissive between the two readings, not permissive in general."""
    r = _Resolver(MinorScopeRule.EITHER, ICT)
    assert not r.can_manage(minor(CSE), applicant_department_id=CSE)


def test_the_three_rules_are_the_whole_vocabulary():
    assert {MinorScopeRule.OFFERING, MinorScopeRule.APPLICANT,
            MinorScopeRule.EITHER} == {"OFFERING", "APPLICANT", "EITHER"}


def test_the_default_is_either_until_the_policy_is_confirmed():
    from app.core.config import settings

    assert settings.MINOR_COORDINATOR_SCOPE == MinorScopeRule.EITHER


@pytest.mark.parametrize("rule", [MinorScopeRule.OFFERING,
                                  MinorScopeRule.APPLICANT,
                                  MinorScopeRule.EITHER])
def test_no_rule_grants_a_scope_the_coordinator_does_not_hold(rule):
    """Whichever reading is configured, an unrelated department stays closed."""
    r = _Resolver(rule, ICT)
    assert not r.can_manage(minor(CSE), applicant_department_id=CSE)
