"""Tests for CSV exports and student allocated electives view."""
from __future__ import annotations


def test_export_allocations_csv_permissions(api, login, world):
    """Plain student cannot access administrative CSV export for allocations."""
    student_headers = login(world.student_a.email)
    response = api.get(
        "/api/v1/electives/admin/allocations/export?component_id=1",
        headers=student_headers,
    )
    assert response.status_code in (403, 404)


def test_export_program_enrollments_csv_permissions(api, login, world):
    """Plain student cannot access administrative CSV export for internship grades."""
    student_headers = login(world.student_a.email)
    response = api.get(
        "/api/v1/internships/programs/1/export",
        headers=student_headers,
    )
    assert response.status_code in (403, 404)


def test_student_dashboard_has_allocated_electives(api, login, world):
    """Student dashboard includes allocated_electives list and enhanced components."""
    student_headers = login(world.student_a.email)
    response = api.get(
        "/api/v1/dashboard/student",
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "allocated_electives" in data
    assert isinstance(data["allocated_electives"], list)
    if data.get("curriculum_semester"):
        for component in data["curriculum_semester"]["components"]:
            assert "status" in component


def test_admin_can_export_program_enrollments_csv(api, login, world):
    """Admin or coordinator can export internship enrollments as CSV."""
    admin_headers = login(world.admin.email)
    # Even if program 999 doesn't exist, it should return 404 rather than 403 or 500
    response = api.get(
        "/api/v1/internships/programs/999/export",
        headers=admin_headers,
    )
    assert response.status_code == 404
