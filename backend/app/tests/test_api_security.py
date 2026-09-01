"""Security review, driven through the HTTP surface.

Every check here is one of the scenarios the Phase 4 brief named. They run
against a real client and a real database rather than against the service
functions, because that is where an authorisation gap actually bites: a route
that forgot its guard passes every unit test of the logic behind it.
"""
from __future__ import annotations

import pytest

ANON = {}


# ── authentication ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("path", [
    "/api/v1/auth/me",
    "/api/v1/curriculum/me",
    "/api/v1/electives/components",
    "/api/v1/notifications",
    "/api/v1/internships/enrollments/me",
    "/api/v1/students",
])
def test_protected_routes_reject_anonymous_callers(api, world, path):
    assert api.get(path, headers=ANON).status_code == 401


@pytest.mark.parametrize("token", [
    "Bearer garbage",
    "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.wrong-signature",
    "Basic YWRtaW46YWRtaW4=",
])
def test_forged_tokens_are_rejected(api, world, token):
    response = api.get("/api/v1/auth/me", headers={"Authorization": token})
    assert response.status_code == 401


def test_a_refresh_token_is_not_accepted_as_an_access_token(api, world):
    """Token types are distinct. A long-lived refresh token must not open the
    API on its own."""
    response = api.post("/api/v1/auth/login",
                        json={"email": world.student_a.email,
                              "password": world.password})
    refresh = response.json()["tokens"]["refresh_token"]
    assert api.get("/api/v1/auth/me",
                   headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_login_does_not_reveal_whether_an_account_exists(api, world):
    """Both answers must look the same, or the endpoint becomes a user oracle."""
    missing = api.post("/api/v1/auth/login",
                       json={"email": "nobody@test.example.com",
                             "password": "whatever1!"})
    wrong = api.post("/api/v1/auth/login",
                     json={"email": world.student_a.email, "password": "wrong-one1!"})
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_the_password_hash_is_never_returned(api, world, login):
    response = api.get("/api/v1/auth/me", headers=login(world.student_a.email))
    assert response.status_code == 200
    body = response.text.lower()
    assert "hashed_password" not in body and "$2b$" not in body


# ── IDOR: one student must not reach another's records ─────────────────────
def test_a_student_cannot_read_another_students_record(api, world, login):
    headers = login(world.student_a.email)
    victim = world.student_b.student.id
    response = api.get(f"/api/v1/students/{victim}", headers=headers)
    assert response.status_code in (401, 403)


def test_a_student_cannot_list_the_student_directory(api, world, login):
    headers = login(world.student_a.email)
    assert api.get("/api/v1/students", headers=headers).status_code == 403


def test_a_student_cannot_reach_admin_elective_endpoints(api, world, login):
    headers = login(world.student_a.email)
    for path in ("/api/v1/electives/admin/preferences?component_id=1",
                 "/api/v1/electives/admin/allocations?component_id=1",
                 "/api/v1/electives/admin/windows"):
        assert api.get(path, headers=headers).status_code == 403, path


def test_a_student_cannot_read_the_audit_log(api, world, login):
    headers = login(world.student_a.email)
    assert api.get("/api/v1/admin/audit-logs", headers=headers).status_code == 403


def test_plain_faculty_cannot_read_the_audit_log(api, world, login):
    """Audit access is a permission, not a side effect of being staff."""
    headers = login(world.plain.email)
    assert api.get("/api/v1/admin/audit-logs", headers=headers).status_code == 403


def test_a_super_admin_can_read_the_audit_log(api, world, login):
    headers = login(world.admin.email)
    assert api.get("/api/v1/admin/audit-logs", headers=headers).status_code == 200


# ── file access ────────────────────────────────────────────────────────────
def test_file_metadata_requires_more_than_being_signed_in(api, world, login, db):
    """The pre-Phase-4 hole: any authenticated user could read any file row and
    receive a directly-fetchable URL for it."""
    from app.models.enums import FileCategory
    from app.models.system import StoredFile

    stored = StoredFile(
        filename="secret.pdf", original_name="secret.pdf",
        content_type="application/pdf", size_bytes=10,
        storage_backend="local", storage_key="certificates/secret.pdf",
        category=FileCategory.CERTIFICATE,
        uploaded_by_user_id=world.student_b.user.id, checksum="x")
    db.add(stored)
    db.flush()

    intruder = login(world.student_a.email)
    response = api.get(f"/api/v1/files/{stored.id}", headers=intruder)
    assert response.status_code == 403

    owner = login(world.student_b.email)
    allowed = api.get(f"/api/v1/files/{stored.id}", headers=owner)
    assert allowed.status_code == 200
    # Even the owner never receives the storage key.
    assert "certificates/secret.pdf" not in allowed.text
    assert allowed.json()["url"].startswith("/api/v1/files/")


def test_downloading_another_students_file_is_refused(api, world, login, db):
    from app.models.enums import FileCategory
    from app.models.system import StoredFile

    stored = StoredFile(
        filename="b.pdf", original_name="b.pdf", content_type="application/pdf",
        size_bytes=10, storage_backend="local", storage_key="reports/b.pdf",
        category=FileCategory.REPORT,
        uploaded_by_user_id=world.student_b.user.id, checksum="x")
    db.add(stored)
    db.flush()

    intruder = login(world.student_a.email)
    assert api.get(f"/api/v1/files/{stored.id}/download",
                   headers=intruder).status_code == 403


def test_a_forged_download_token_does_not_bypass_authorisation(api, world, login, db):
    from app.models.enums import FileCategory
    from app.models.system import StoredFile

    stored = StoredFile(
        filename="b.pdf", original_name="b.pdf", content_type="application/pdf",
        size_bytes=10, storage_backend="local", storage_key="reports/b2.pdf",
        category=FileCategory.REPORT,
        uploaded_by_user_id=world.student_b.user.id, checksum="x")
    db.add(stored)
    db.flush()

    intruder = login(world.student_a.email)
    response = api.get(f"/api/v1/files/{stored.id}/download?token=9999999999.{'0' * 32}",
                       headers=intruder)
    assert response.status_code == 403


# ── scoped roles: the pairs a naive check collapses ────────────────────────
def test_a_summer_coordinator_does_not_gain_cssi(api, world, login, db):
    """Both are internships. Coordinating one grants nothing over the other."""
    from app.models.enums import CoordinationDomain
    from app.services import scope

    user = world.summer_ict.user
    assert scope.coordinates(db, user, CoordinationDomain.SUMMER_INTERNSHIP,
                             world.departments["ICT"].id)
    assert not scope.coordinates(db, user, CoordinationDomain.CSSI,
                                 world.departments["ICT"].id)


def test_a_coordinator_is_confined_to_their_own_department(api, world, db):
    from app.models.enums import CoordinationDomain
    from app.services import scope

    user = world.summer_ict.user
    assert scope.coordinates(db, user, CoordinationDomain.SUMMER_INTERNSHIP,
                             world.departments["ICT"].id)
    assert not scope.coordinates(db, user, CoordinationDomain.SUMMER_INTERNSHIP,
                                 world.departments["CSE"].id)


def test_the_same_module_in_two_departments_stays_separate(api, world, db):
    from app.models.enums import CoordinationDomain
    from app.services import scope

    assert not scope.coordinates(db, world.summer_cse.user,
                                 CoordinationDomain.SUMMER_INTERNSHIP,
                                 world.departments["ICT"].id)
    assert scope.coordinates(db, world.summer_cse.user,
                             CoordinationDomain.SUMMER_INTERNSHIP,
                             world.departments["CSE"].id)


def test_a_mentor_does_not_become_a_coordinator(api, world, db):
    """Mentor and Coordinator are independent grants over the same scope shape."""
    from app.models.enums import CoordinationDomain
    from app.services import scope

    user = world.mentor_ict.user
    assert scope.mentors(db, user, CoordinationDomain.CSSI,
                         world.departments["ICT"].id)
    assert not scope.coordinates(db, user, CoordinationDomain.CSSI,
                                 world.departments["ICT"].id)


def test_a_mentor_cannot_reach_coordinator_endpoints(api, world, login):
    headers = login(world.mentor_ict.email)
    assert api.get("/api/v1/electives/admin/windows",
                   headers=headers).status_code == 403


def test_plain_faculty_holds_no_scoped_grants(api, world, db):
    from app.models.enums import CoordinationDomain
    from app.services import scope

    for domain in CoordinationDomain:
        assert not scope.coordinates(db, world.plain.user, domain,
                                     world.departments["ICT"].id)


# ── input validation and mass assignment ───────────────────────────────────
def test_a_student_cannot_promote_themselves_through_the_profile_endpoint(
    api, world, login
):
    """Mass assignment: fields the schema does not declare must be ignored."""
    headers = login(world.student_a.email)
    response = api.patch("/api/v1/me/profile", headers=headers, json={
        "full_name": "Renamed", "cpi": 10.0, "current_semester": 8,
        "roll_number": "HACKED", "is_active": True, "id": 1,
    })
    assert response.status_code in (200, 422)
    world.db.refresh(world.student_a.student)
    assert world.student_a.student.roll_number == "24BIT900"
    assert float(world.student_a.student.cpi) == 8.0
    assert world.student_a.student.current_semester == 4


def test_sql_injection_in_a_query_parameter_is_harmless(api, world, login):
    """Queries are parameterised, so this is data, never syntax."""
    headers = login(world.admin.email)
    response = api.get("/api/v1/students?search=%27%3B+DROP+TABLE+students%3B--",
                       headers=headers)
    assert response.status_code == 200
    assert world.db.query(type(world.student_a.student)).count() >= 2


def test_an_unknown_id_is_a_clean_404_not_a_stack_trace(api, world, login):
    headers = login(world.admin.email)
    response = api.get("/api/v1/students/999999", headers=headers)
    assert response.status_code == 404
    assert "Traceback" not in response.text
    assert "sqlalchemy" not in response.text.lower()
