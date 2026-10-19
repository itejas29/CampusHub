"""The registrar can open a department's Head-of-Department screen.

The ICT HoD is a real person and cannot sign in to the demo; the registrar,
who oversees every department, sees what the Head sees. Nobody else does.
"""
from __future__ import annotations


def test_the_registrar_sees_a_departments_hod_view(api, world, login):
    response = api.get("/api/v1/dashboard/hod?department_code=ICT", headers=login(world.admin.email))
    assert response.status_code == 200, response.text
    assert response.json()["department"]["code"] == "ICT"


def test_a_faculty_member_does_not(api, world, login):
    response = api.get("/api/v1/dashboard/hod?department_code=ICT", headers=login(world.mentor_ict.email))
    assert response.status_code == 403
