from __future__ import annotations

import pytest

from app.core.rbac import P, ROLE_PERMISSIONS, has_permission, permissions_for
from app.models.enums import Role


def test_super_admin_holds_every_permission():
    granted = permissions_for([Role.SUPER_ADMIN])
    for permission in P.values():
        assert has_permission([Role.SUPER_ADMIN], permission), permission
    assert "*" in granted


@pytest.mark.parametrize("permission", [
    P["ELECTIVE_ALLOCATE"], P["STUDENT_MANAGE"], P["AUDIT_VIEW"],
    P["MOOC_VERIFY"], P["MINOR_MANAGE"], P["SYSTEM_ADMIN"],
])
def test_student_cannot_reach_administrative_permissions(permission):
    assert not has_permission([Role.STUDENT], permission)


def test_student_can_reach_own_workflows():
    for permission in (P["ELECTIVE_APPLY"], P["MOOC_APPLY"], P["MINOR_APPLY"],
                       P["INTERNSHIP_SUBMIT"], P["EVENT_REGISTER"]):
        assert has_permission([Role.STUDENT], permission)


def test_faculty_cannot_read_the_audit_log():
    assert not has_permission([Role.FACULTY], P["AUDIT_VIEW"])


def test_faculty_cannot_reach_institution_wide_reporting():
    """Regression: `reports:view` gates the admin dashboard, whose activity
    panel is audit-log data. Granting it to FACULTY leaked audit entries to a
    role explicitly denied `audit:view`."""
    assert not has_permission([Role.FACULTY], P["REPORT_VIEW"])


@pytest.mark.parametrize("role", [
    Role.DEPARTMENT_ADMIN, Role.INTERNSHIP_COORDINATOR, Role.CLUB_ADMIN,
    Role.SUPER_ADMIN,
])
def test_admin_roles_keep_institution_wide_reporting(role):
    assert has_permission([role], P["REPORT_VIEW"])


def test_department_admin_retains_faculty_capabilities():
    """DEPARTMENT_ADMIN derives from the faculty set; narrowing FACULTY must not
    silently narrow it."""
    for permission in (P["INTERNSHIP_EVALUATE"], P["MENTORSHIP_FACULTY"],
                       P["REPORT_VIEW"], P["AUDIT_VIEW"]):
        assert has_permission([Role.DEPARTMENT_ADMIN], permission), permission


def test_only_audit_holders_see_audit_data():
    """Any role with reports:view but not audit:view must not be handed audit
    rows — the dashboard checks this separately."""
    for role in (Role.CLUB_ADMIN, Role.INTERNSHIP_COORDINATOR):
        if has_permission([role], P["REPORT_VIEW"]):
            assert not has_permission([role], P["AUDIT_VIEW"]) or role is Role.SUPER_ADMIN


def test_faculty_can_evaluate_but_not_configure_academics():
    assert has_permission([Role.FACULTY], P["INTERNSHIP_EVALUATE"])
    assert not has_permission([Role.FACULTY], P["ACADEMIC_MANAGE"])


def test_club_admin_is_scoped_to_community_features():
    assert has_permission([Role.CLUB_ADMIN], P["EVENT_MANAGE"])
    assert not has_permission([Role.CLUB_ADMIN], P["ELECTIVE_ALLOCATE"])
    assert not has_permission([Role.CLUB_ADMIN], P["STUDENT_MANAGE"])


def test_multiple_roles_union_their_permissions():
    roles = [Role.FACULTY, Role.INTERNSHIP_COORDINATOR]
    assert has_permission(roles, P["INTERNSHIP_MANAGE"])   # from coordinator
    assert has_permission(roles, P["MENTORSHIP_FACULTY"])  # from faculty


def test_every_role_is_present_in_the_matrix():
    assert set(ROLE_PERMISSIONS) == set(Role)
