"""The ICT faculty roster is PDEU's published list, and real people are handled
as real people.

* Every entry comes from the source file, which records where it was taken from.
* Nothing PDEU does not publish is invented — no cabin, no phone.
* A real faculty member's login address can never reach their real inbox, and
  they cannot sign in to a demo with the shared demo password.
* No real person is given a coordinator or HoD role the source does not state.
"""
from __future__ import annotations

from app.seed import data as D


def test_the_roster_is_the_published_ict_list_with_its_source():
    source = D.ICT_FACULTY_SOURCE["source"]
    assert source["url"] == "https://pdeu.ac.in/faculties-and-staff"
    assert source["retrieved_at"]
    faculty = D.ICT_FACULTY_SOURCE["faculty"]
    assert len(faculty) == len(D.ICT_FACULTY_ROSTER) > 0
    for person in faculty:
        assert person["name"] and person["designation"]
        assert person["official_email"].lower().endswith("@sot.pdpu.ac.in")


def test_nothing_unpublished_is_invented_for_real_faculty():
    for _name, _email, _code, dept, _designation, cabin, _spec, extra in D.ICT_FACULTY_ROSTER:
        assert dept == "ICT"
        assert cabin is None          # PDEU does not publish cabins
        assert extra == []            # no system roles beyond Faculty
    for person in D.ICT_FACULTY_SOURCE["faculty"]:
        assert "phone" not in person and "cabin" not in person


def test_a_real_faculty_login_can_never_reach_a_real_inbox():
    for _name, email, *_ in D.ICT_FACULTY_ROSTER:
        assert email.endswith("@faculty.campushub.example.com")
        assert "pdpu.ac.in" not in email and "pdeu.ac.in" not in email


def test_no_real_person_holds_a_role_the_source_does_not_state():
    real = {code for _n, _e, code, *_ in D.ICT_FACULTY_ROSTER}
    assert not real & set(D.HEADS_OF_DEPARTMENT.values())
    coordinators = {code for code, role, *_ in D.ROLE_ASSIGNMENTS if role == "COORDINATOR"}
    assert not real & coordinators
    # Mentor grants only make someone eligible for the generated students.
    mentor_roles = {role for code, role, *_ in D.ROLE_ASSIGNMENTS if code in real}
    assert mentor_roles <= {"MENTOR"}
