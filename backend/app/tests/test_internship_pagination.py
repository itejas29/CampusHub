"""The internship student list, a page at a time (QA-16).

`GET /internships/enrollments` loaded the coordinator's whole cohort, then
searched it in Python. `GET /internships/enrollments/page` counts, filters,
searches and slices in SQL, in a stable order, with a bounded page size; the
unpaged list stays for the screens that need the whole cohort (mentor
allocation) and now searches in SQL too.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event

from app.models.enums import InternshipType, Role
from app.models.identity import UserRole
from app.models.internships import InternshipEnrollment, InternshipProgram, Organization
from app.tests.test_mentor_allocation import _enrol

PAGE = "/api/v1/internships/enrollments/page"
LIST = "/api/v1/internships/enrollments"


@pytest.fixture
def cohort(db, world):
    db.add(UserRole(user_id=world.cssi_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    cssi = InternshipProgram(code="CSSI-ICT-T", name="CSSI (ICT)", type=InternshipType.CSSI,
                             department_id=world.departments["ICT"].id, config={})
    summer = InternshipProgram(code="SI-CSE-T", name="Summer (CSE)",
                               type=InternshipType.SUMMER,
                               department_id=world.departments["CSE"].id, config={})
    db.add_all([cssi, summer])
    db.flush()
    rows = _enrol(db, world, cssi, 23)
    org = Organization(name="Akshar 100% Trust", type="NGO")
    db.add(org)
    db.flush()
    rows[4].organization_id = org.id
    rows[7].mentor_faculty_id = world.mentor_ict.faculty.id
    # Another department's programme the CSSI coordinator must never see.
    db.add(InternshipEnrollment(program_id=summer.id, student_id=world.student_a.student.id))
    db.flush()
    return type("Cohort", (), {"cssi": cssi, "summer": summer, "rows": rows})


def page(api, headers, **params):
    response = api.get(PAGE, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_page_carries_the_total_and_its_size(api, login, cohort, world):
    body = page(api, login(world.cssi_ict.email), page_size=10)
    assert body["total"] == 23 and body["page"] == 1 and body["page_size"] == 10
    assert len(body["items"]) == 10


def test_pages_cover_every_student_once_in_a_stable_order(api, login, cohort, world):
    headers = login(world.cssi_ict.email)
    seen = []
    for n in (1, 2, 3):
        seen += [r["id"] for r in page(api, headers, page=n, page_size=10)["items"]]
    assert seen == sorted(r.id for r in cohort.rows)
    again = [r["id"] for r in page(api, headers, page=2, page_size=10)["items"]]
    assert again == seen[10:20]


def test_a_page_past_the_end_is_empty_not_an_error(api, login, cohort, world):
    body = page(api, login(world.cssi_ict.email), page=9, page_size=10)
    assert body["items"] == [] and body["total"] == 23


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 201},
                                    {"page": -1}])
def test_page_numbers_and_sizes_are_validated(api, login, cohort, world, params):
    assert api.get(PAGE, headers=login(world.cssi_ict.email),
                   params=params).status_code == 422


def test_search_runs_on_name_roll_and_organisation(api, login, cohort, world):
    headers = login(world.cssi_ict.email)
    assert page(api, headers, q="cssi student 12")["total"] == 1
    assert page(api, headers, q="24BIT01")["total"] == 10     # 010 … 019
    assert page(api, headers, q="akshar")["items"][0]["id"] == cohort.rows[4].id


def test_search_wildcards_are_literal(api, login, cohort, world):
    headers = login(world.cssi_ict.email)
    assert page(api, headers, q="100%")["total"] == 1
    assert page(api, headers, q="%")["total"] == 1
    assert page(api, headers, q="_")["total"] == 0


def test_a_coordinator_sees_only_their_programmes(api, login, cohort, world):
    ids = {r["program_id"] for r in page(api, login(world.cssi_ict.email),
                                         page_size=200)["items"]}
    assert ids == {cohort.cssi.id}


def test_a_mentor_sees_only_their_own_students(api, login, cohort, world):
    body = page(api, login(world.mentor_ict.email))
    assert [r["id"] for r in body["items"]] == [cohort.rows[7].id]


def test_a_student_cannot_list_students(api, login, cohort, world):
    assert api.get(PAGE, headers=login(world.student_b.email)).status_code == 403


def test_programme_type_filters_and_unknown_types_are_refused(api, login, cohort, world):
    headers = login(world.cssi_ict.email)
    assert page(api, headers, program_types="CSSI")["total"] == 23
    assert page(api, headers, program_types="SUMMER")["total"] == 0
    assert api.get(PAGE, headers=headers,
                   params={"program_types": "NOPE"}).status_code == 422


def test_a_page_costs_the_same_queries_whatever_its_size(api, login, db, cohort, world):
    # Same composition on both pages (every student has the same mentor), so
    # only the number of rows differs: a mentor's details are loaded once per
    # mentor, which is not the per-row cost this guards against.
    for row in cohort.rows:
        row.mentor_faculty_id = world.mentor_ict.faculty.id
    db.flush()
    headers = login(world.cssi_ict.email)

    def queries(size):
        count = [0]

        def tick(*_):
            count[0] += 1
        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", tick)
        try:
            page(api, headers, page_size=size)
        finally:
            event.remove(engine, "before_cursor_execute", tick)
        return count[0]

    assert queries(20) == queries(5)


def test_the_unpaged_list_still_returns_every_student(api, login, cohort, world):
    response = api.get(LIST, headers=login(world.cssi_ict.email))
    assert response.status_code == 200 and isinstance(response.json(), list)
    assert len(response.json()) == 23
    found = api.get(LIST, headers=login(world.cssi_ict.email), params={"q": "akshar"}).json()
    assert [r["id"] for r in found] == [cohort.rows[4].id]
