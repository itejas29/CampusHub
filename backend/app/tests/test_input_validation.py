"""What the API accepts is checked by the server, whatever a form lets through.

* A phone number is a real one: a 10-digit mobile, a landline with its STD
  code, or an international number. "99" is refused; a mobile is stored as
  "+91 98765 43210".
* A person's name is letters, with one word of two or more — "n n" is not a
  supervisor.
* Links are http(s) only; text loses control characters; markup is refused.
* A blank optional box means "not given", not an invalid value.
* The 422 message names the field and says what to type.
* CSV exports never hand a spreadsheet a formula.
"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.internships import InternshipEnrollment
from app.schemas.fields import Phone, PersonName, Url, csv_safe, line, optional

from app.tests.test_internship_windows import (  # noqa: F401  (fixtures)
    _enrol, _open_registration, _student, cssi,
)


def _valid(kind, value):
    return TypeAdapter(kind).validate_python(value)


# ── the types ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("typed, stored", [
    ("9876543210", "+91 98765 43210"),
    ("+91 98765-43210", "+91 98765 43210"),
    ("098765 43210", "09876543210"),
    ("079 2327 5000", "07923275000"),
    ("+44 20 7946 0958", "+442079460958"),
])
def test_a_real_phone_number_is_accepted_and_normalised(typed, stored):
    assert _valid(Phone, typed) == stored


@pytest.mark.parametrize("typed", [
    "99", "12345", "1234567890", "9999999999", "98765 4321", "phone", "98765432101234",
    "+1 234", "9876543210; drop",
])
def test_a_phone_number_that_cannot_be_dialled_is_refused(typed):
    with pytest.raises(ValidationError):
        _valid(Phone, typed)


@pytest.mark.parametrize("name", ["Asha Patel", "Dr. R. K. Shah", "D'Souza", "राम शर्मा", "Jean-Luc"])
def test_real_names_in_any_script_are_accepted(name):
    assert _valid(PersonName, name) == name


@pytest.mark.parametrize("name", ["n n", "a", "Asha1", "x_y", "<b>Asha</b>", "  ", "...."])
def test_a_name_that_is_not_one_is_refused(name):
    with pytest.raises(ValidationError):
        _valid(PersonName, name)


@pytest.mark.parametrize("link", ["javascript:alert(1)", "data:text/html,x", "example", "ftp://x.org"])
def test_only_web_links_are_accepted(link):
    with pytest.raises(ValidationError):
        _valid(Url, link)


def test_text_loses_control_characters_and_refuses_markup():
    assert _valid(line(50), "  Seva‮  Trust\x00 ") == "Seva Trust"
    with pytest.raises(ValidationError):
        _valid(line(50), "<script>x</script>")


def test_a_blank_optional_box_is_not_given():
    assert _valid(optional(Phone), "") is None
    assert _valid(optional(Url), "   ") is None


def test_a_csv_cell_never_starts_a_formula():
    assert csv_safe("=1+2") == "'=1+2"
    assert csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("Seva Trust") == "Seva Trust" and csv_safe(3.5) == 3.5


# ── through the API ───────────────────────────────────────────────────────
def test_cssi_registration_refuses_a_made_up_supervisor(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT201")
    response = _enrol(api, login, student, cssi, industry_mentor_name="n n", industry_mentor_phone="99")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["message"].startswith("Supervisor's ")
    assert {f["field"] for f in error["details"]} == {"industry_mentor_name", "industry_mentor_phone"}
    assert not db.query(InternshipEnrollment).filter_by(student_id=student.id).count()


def test_cssi_registration_stores_the_supervisors_number_normalised(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT202")
    response = _enrol(api, login, student, cssi, industry_mentor_phone="98765-43210")
    assert response.status_code == 201, response.text
    enrollment = db.query(InternshipEnrollment).filter_by(student_id=student.id).one()
    assert enrollment.industry_mentor_phone == "+91 98765 43210"


def test_a_new_organisation_is_checked_too(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT203")
    response = _enrol(api, login, student, cssi, new_organization={
        "name": "Seva", "type": "NGO", "website": "javascript:alert(1)", "pincode": "12"})
    assert response.status_code == 422
    assert {f["field"] for f in response.json()["error"]["details"]} == {
        "new_organization.website", "new_organization.pincode"}


def test_the_profile_refuses_a_short_phone_and_clears_a_blank_one(api, world, login):
    headers = login(world.student_b.email)
    refused = api.patch("/api/v1/me/profile", headers=headers, json={"phone": "99"})
    assert refused.status_code == 422
    assert refused.json()["error"]["message"].startswith("Phone: Enter a 10-digit mobile number")
    assert api.patch("/api/v1/me/profile", headers=headers, json={"phone": ""}).status_code == 200


def test_stage_data_is_kept_small(api, db, world, login, cssi):
    response = api.post("/api/v1/internships/enrollments/1/stages/submit",
                        headers=login(world.student_b.email),
                        json={"stage_id": 1, "data": {"x": "y" * 20_000}})
    assert response.status_code == 422


def test_the_export_does_not_hand_excel_a_formula(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT204")
    assert _enrol(api, login, student, cssi, new_organization={
        "name": "=1+2 Seva", "type": "NGO"}).status_code == 201
    csv = api.get(f"/api/v1/internships/programs/{cssi.id}/export", headers=login(world.cssi_ict.email))
    assert csv.status_code == 200, csv.text
    assert "'=1+2 Seva" in csv.text
