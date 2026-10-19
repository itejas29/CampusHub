"""Sign-in safety before real people use the portal.

* Password guessing is throttled — per account from one address, per account
  from anywhere, and per address — and a locked key never reveals whether the
  account exists.
* A password change signs the account out everywhere else; the new password
  must meet the policy.
* There is no email yet, so the registrar (anyone) or a department office (its
  own students) issues a one-time password, which must be replaced before
  anything else. While demo accounts are on, no password may be issued, and a
  shared demo login's password cannot be changed.
* `faculty:manage` (department offices, internship coordinators) never grants
  a system role, and never reaches another department.
* Production refuses the development signing key.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings, settings
from app.core.security import hash_password
from app.models.enums import Role
from app.models.identity import Faculty, User, UserRole

LOGIN = "/api/v1/auth/login"


def attempt(api, email, password, address="10.0.0.1"):
    return api.post(LOGIN, json={"email": email, "password": password},
                    headers={"X-Forwarded-For": f"203.0.113.9, {address}"})


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)


@pytest.fixture
def office(db, world):
    user = User(email="office@test.example.com", hashed_password=hash_password(world.password),
                full_name="ICT Office")
    db.add(user)
    db.flush()
    db.add_all([UserRole(user_id=user.id, role=Role.FACULTY),
                UserRole(user_id=user.id, role=Role.DEPARTMENT_ADMIN)])
    db.add(Faculty(user_id=user.id, employee_code="ICT-OFF", department_id=world.departments["ICT"].id,
                   designation="Department Office", is_mentor=False))
    db.flush()
    return user


# ── throttling ────────────────────────────────────────────────────────────
def test_five_wrong_passwords_lock_that_account_from_that_address(api, world):
    for _ in range(5):
        assert attempt(api, world.student_a.email, "wrong-guess-1").status_code == 401
    locked = attempt(api, world.student_a.email, world.password)
    assert locked.status_code == 429 and "Too many" in locked.json()["error"]["message"]
    # The real student, elsewhere, is not locked out by someone else's guessing.
    assert attempt(api, world.student_a.email, world.password, address="10.0.0.2").status_code == 200


def test_guessing_from_many_addresses_still_locks_the_account(api, world):
    for i in range(20):
        attempt(api, world.student_b.email, "wrong-guess-2", address=f"10.1.0.{i}")
    assert attempt(api, world.student_b.email, world.password, address="10.9.9.9").status_code == 429


def test_an_unknown_address_is_throttled_exactly_like_a_real_one(api, world):
    for _ in range(5):
        assert attempt(api, "nobody@test.example.com", "x").status_code == 401
    assert attempt(api, "nobody@test.example.com", "x").status_code == 429


def test_a_correct_password_clears_the_count(api, world):
    for _ in range(4):
        attempt(api, world.student_a.email, "wrong-guess-3")
    assert attempt(api, world.student_a.email, world.password).status_code == 200
    for _ in range(4):
        attempt(api, world.student_a.email, "wrong-guess-3")
    assert attempt(api, world.student_a.email, world.password).status_code == 200


# ── changing a password ───────────────────────────────────────────────────
def test_a_weak_password_is_refused(api, world, login):
    headers = login(world.student_a.email)
    for weak in ["short1", "onlyletters", "1234567890", "Password123"[:0] + "password123"]:
        response = api.post("/api/v1/auth/change-password", headers=headers,
                            json={"current_password": world.password, "new_password": weak})
        assert response.status_code == 422, weak


def test_changing_the_password_signs_out_every_other_session(api, world, login):
    old = login(world.student_a.email)
    response = api.post("/api/v1/auth/change-password", headers=old,
                        json={"current_password": world.password, "new_password": "river7stone42"})
    assert response.status_code == 200, response.text
    assert api.get("/api/v1/auth/me", headers=old).status_code == 401
    fresh = {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}
    assert api.get("/api/v1/auth/me", headers=fresh).status_code == 200


def test_a_shared_demo_login_cannot_have_its_password_changed(api, db, world):
    user = User(email="demo.person@campushub.example.com", hashed_password=hash_password(world.password),
                full_name="Demo Person")
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role=Role.STUDENT))
    db.flush()
    token = attempt(api, user.email, world.password).json()["tokens"]["access_token"]
    response = api.post("/api/v1/auth/change-password", headers={"Authorization": f"Bearer {token}"},
                        json={"current_password": world.password, "new_password": "river7stone42"})
    assert response.status_code == 403


# ── temporary passwords ───────────────────────────────────────────────────
def test_no_password_is_issued_while_demo_accounts_are_on(api, world, login):
    response = api.post(f"/api/v1/students/{world.student_a.student.id}/reset-password",
                        headers=login(world.admin.email))
    assert response.status_code == 403 and "DEMO_MODE" in response.json()["error"]["message"]


def test_a_temporary_password_must_be_replaced_before_anything_else(api, world, login, real_mode):
    old = login(world.student_a.email)
    issued = api.post(f"/api/v1/students/{world.student_a.student.id}/reset-password",
                      headers=login(world.admin.email))
    assert issued.status_code == 200, issued.text
    temporary = issued.json()["temporary_password"]
    assert api.get("/api/v1/auth/me", headers=old).status_code == 401          # signed out

    signed_in = attempt(api, world.student_a.email, temporary).json()
    assert signed_in["user"]["must_change_password"] is True
    headers = {"Authorization": f"Bearer {signed_in['tokens']['access_token']}"}
    blocked = api.get("/api/v1/dashboard/student", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"

    changed = api.post("/api/v1/auth/change-password", headers=headers,
                       json={"current_password": temporary, "new_password": "river7stone42"})
    assert changed.status_code == 200, changed.text
    fresh = {"Authorization": f"Bearer {changed.json()['tokens']['access_token']}"}
    assert api.get("/api/v1/dashboard/student", headers=fresh).status_code == 200


def test_a_department_office_resets_its_own_students_only(api, world, login, office, real_mode):
    headers = login(office.email)
    assert api.post(f"/api/v1/students/{world.student_a.student.id}/reset-password",
                    headers=headers).status_code == 200
    # Not a faculty member — the office could then sign in as a coordinator.
    assert api.post(f"/api/v1/faculty/{world.mentor_ict.faculty.id}/reset-password",
                    headers=headers).status_code == 403


def test_demo_accounts_cannot_sign_in_once_switched_off(api, db, world, real_mode):
    user = User(email="demo.person@campushub.example.com", hashed_password=hash_password(world.password),
                full_name="Demo Person")
    db.add(user)
    db.flush()
    assert attempt(api, user.email, world.password).status_code == 401
    assert api.get("/api/v1/auth/config").json() == {"demo_mode": False}


# ── who may create whom ───────────────────────────────────────────────────
def test_faculty_manage_never_creates_a_super_admin(api, world, login):
    body = {"full_name": "Shadow Admin", "email": "shadow@test.example.com", "employee_code": "ICT-X1",
            "department_id": world.departments["ICT"].id, "designation": "Assistant Professor",
            "extra_roles": ["SUPER_ADMIN"]}
    response = api.post("/api/v1/faculty", headers=login(world.summer_ict.email), json=body)
    assert response.status_code == 403


def test_no_one_but_the_registrar_manages_another_departments_people(api, world, login):
    body = {"full_name": "Other Dept", "email": "other.dept@test.example.com", "employee_code": "CE-X1",
            "department_id": world.departments["CSE"].id, "designation": "Assistant Professor"}
    assert api.post("/api/v1/faculty", headers=login(world.summer_ict.email), json=body).status_code == 403
    assert api.post("/api/v1/faculty", headers=login(world.admin.email), json=body).status_code == 201


def test_a_new_account_gets_a_one_time_password_once_demo_is_off(api, world, login, real_mode):
    body = {"full_name": "Asha Verma", "email": "asha.verma@test.example.com", "employee_code": "ICT-X2",
            "department_id": world.departments["ICT"].id, "designation": "Assistant Professor",
            "password": "Campus@123"}
    created = api.post("/api/v1/faculty", headers=login(world.admin.email), json=body)
    assert created.status_code == 201, created.text
    temporary = created.json()["temporary_password"]
    assert temporary and attempt(api, body["email"], "Campus@123").status_code == 401
    assert attempt(api, body["email"], temporary).json()["user"]["must_change_password"] is True


# ── configuration ─────────────────────────────────────────────────────────
def test_production_refuses_the_development_signing_key():
    with pytest.raises(ValueError):
        Settings(ENVIRONMENT="production", SECRET_KEY="dev-only-insecure-secret-change-me")
    assert Settings(ENVIRONMENT="production", SECRET_KEY="k" * 64).ENVIRONMENT == "production"


def test_typos_never_lock_a_shared_demo_login(api, db, world):
    user = User(email="demo.typo@campushub.example.com", hashed_password=hash_password(world.password),
                full_name="Demo Typo")
    db.add(user)
    db.flush()
    for _ in range(8):
        attempt(api, user.email, "typo")
    assert attempt(api, user.email, world.password).status_code == 200


def test_an_unknown_email_costs_a_password_check_too(api, world, monkeypatch):
    # Skipping the hash for unknown addresses answered in ~5 ms instead of ~250,
    # telling anyone which emails have accounts (QA probe SEC-9).
    import app.core.security as security

    checked = []
    real = security.verify_password
    monkeypatch.setattr(security, "verify_password", lambda p, h: checked.append(h) or real(p, h))

    assert attempt(api, "nobody.here@test.example.com", "whatever-1").status_code == 401
    assert len(checked) == 1


def test_a_sign_in_that_cannot_get_a_slot_is_told_to_retry(api, world, monkeypatch):
    # bcrypt runs a few at a time so a burst of sign-ins cannot starve the
    # rest of the portal (QA spike test); one that waits too long gets a 503.
    import threading

    from app.services import accounts

    monkeypatch.setattr(accounts, "_HASH_SLOTS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(accounts, "_HASH_WAIT_S", 0.05)
    accounts._HASH_SLOTS.acquire()
    response = attempt(api, world.student_a.email, world.password)
    assert response.status_code == 503 and response.json()["error"]["code"] == "busy"
