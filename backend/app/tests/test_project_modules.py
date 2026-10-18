"""Semester VII and VIII projects, as rows on the one internship engine.

* Two Semester VII programmes run side by side, told apart by admission batch:
  the Minor Project for the earlier schemes, the Seminar for 2024 on.
* The Semester VIII Major Project offers two tracks. The track decides what
  registering asks for (no host for an in-house project; a company and its
  supervisor for an industry internship) and which stages apply.
* Assigning a mentor or guide completes the coordinator's allocation stage —
  for every programme, the Summer Internship included.
* Each programme type maps to exactly one coordinator role, and an unmapped
  type no longer falls through to the Summer Internship coordinator.
"""
from __future__ import annotations

import pytest

from app.models.enums import (
    AssignedRole, CoordinationDomain, DocumentType, InternshipType, ProgramStatus,
    ReportFrequency, Role, StageStatus,
)
from app.models.identity import FacultyRoleAssignment, UserRole
from app.models.internships import InternshipProgram, InternshipStage
from app.services import internships as engine
from app.services import scope

from app.tests.test_internship_windows import _student  # noqa: F401

TRACKS = [
    {"key": "PROJECT", "label": "Major Project (in-house)", "requires_organization": False,
     "requires_industry_mentor": False, "organization_types": [],
     "stages": ["GUIDE_ALLOCATION", "SYNOPSIS", "EVALUATION"]},
    {"key": "INDUSTRY", "label": "Industry Internship", "requires_organization": True,
     "requires_industry_mentor": True, "organization_types": ["COMPANY", "STARTUP"],
     "stages": ["GUIDE_ALLOCATION", "OFFER_LETTER", "SYNOPSIS", "EVALUATION"]},
]


def _program(db, world, code, ptype, semester, config, stages):
    program = InternshipProgram(
        code=code, name=code, type=ptype, department_id=world.departments["ICT"].id,
        target_semester=semester, announce_from_semester=semester,
        status=ProgramStatus.REGISTRATION_OPEN, requires_organization=False,
        report_frequency=ReportFrequency.NONE, config=config)
    db.add(program)
    db.flush()
    for i, (scode, owner, doc) in enumerate(stages, 1):
        db.add(InternshipStage(program_id=program.id, code=scode, name=scode, sequence=i,
                               owner_role=owner, requires_document=doc is not None,
                               document_type=doc))
    db.flush()
    return program


@pytest.fixture
def coordinator(db, world):
    """A Projects and Major Project coordinator for ICT — nothing else."""
    for domain in (CoordinationDomain.PROJECT, CoordinationDomain.MAJOR_PROJECT):
        db.add(FacultyRoleAssignment(faculty_id=world.plain.faculty.id, role=AssignedRole.COORDINATOR,
                                     domain=domain, department_id=world.departments["ICT"].id,
                                     is_active=True))
    db.add(UserRole(user_id=world.plain.user.id, role=Role.INTERNSHIP_COORDINATOR))
    db.flush()
    return world.plain


@pytest.fixture
def semester_seven(db, world):
    minor = _program(db, world, "MP7", InternshipType.MINOR_PROJECT, 7, {"admission_years": {"to": 2023}},
                     [("SYNOPSIS", "STUDENT", DocumentType.SYNOPSIS),
                      ("GUIDE_ALLOCATION", "COORDINATOR", None), ("EVALUATION", "FACULTY", None)])
    seminar = _program(db, world, "SEM7", InternshipType.SEMINAR, 7, {"admission_years": {"from": 2024}},
                       [("TOPIC", "STUDENT", DocumentType.SYNOPSIS), ("EVALUATION", "FACULTY", None)])
    return minor, seminar


@pytest.fixture
def major(db, world):
    return _program(db, world, "MP8", InternshipType.MAJOR_PROJECT, 8, {"tracks": TRACKS},
                    [("GUIDE_ALLOCATION", "COORDINATOR", None),
                     ("OFFER_LETTER", "STUDENT", DocumentType.OFFER_LETTER),
                     ("SYNOPSIS", "STUDENT", DocumentType.SYNOPSIS), ("EVALUATION", "FACULTY", None)])


def _codes(api, login, student):
    rows = api.get("/api/v1/internships/programs", headers=login(student.user.email)).json()
    return {p["code"]: p for p in rows}


# ── Semester VII: the batch decides ───────────────────────────────────────
def test_the_batch_decides_between_minor_project_and_seminar(api, db, world, login, semester_seven):
    earlier = _student(db, world, "23BIT701", semester=7)
    earlier.admission_year = 2023
    later = _student(db, world, "24BIT701", semester=7)
    later.admission_year = 2024
    db.flush()
    assert set(_codes(api, login, earlier)) & {"MP7", "SEM7"} == {"MP7"}
    assert set(_codes(api, login, later)) & {"MP7", "SEM7"} == {"SEM7"}


def test_a_student_outside_the_batch_cannot_register(api, db, world, login, semester_seven):
    minor, _seminar = semester_seven
    later = _student(db, world, "24BIT702", semester=7)
    later.admission_year = 2024
    db.flush()
    response = api.post(f"/api/v1/internships/programs/{minor.id}/enroll",
                        headers=login(later.user.email), json={})
    assert response.status_code in (400, 409, 422)
    assert "2023 or earlier" in response.text


def test_the_minor_project_needs_no_host_organisation(api, db, world, login, semester_seven):
    minor, _seminar = semester_seven
    student = _student(db, world, "23BIT703", semester=7)
    student.admission_year = 2023
    db.flush()
    response = api.post(f"/api/v1/internships/programs/{minor.id}/enroll",
                        headers=login(student.user.email), json={})
    assert response.status_code == 201, response.text


# ── Semester VIII: the track decides ──────────────────────────────────────
@pytest.fixture
def finalist(db, world):
    return _student(db, world, "22BIT801", semester=8)


def _enrol(api, login, student, program, **body):
    return api.post(f"/api/v1/internships/programs/{program.id}/enroll",
                    headers=login(student.user.email), json=body)


def test_a_track_must_be_chosen(api, db, world, login, major, finalist):
    response = _enrol(api, login, finalist, major)
    assert response.status_code == 422 and "Choose" in response.text
    assert _enrol(api, login, finalist, major, track="ABROAD").status_code == 422


def test_the_in_house_track_needs_no_host_and_skips_industry_stages(api, db, world, login, major, finalist):
    response = _enrol(api, login, finalist, major, track="PROJECT")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["track"] == "PROJECT" and body["track_label"] == "Major Project (in-house)"
    skipped = {s["stage"]["code"] for s in body["stages"] if s["status"] == "SKIPPED"}
    assert skipped == {"OFFER_LETTER"}
    expected = api.get(f"/api/v1/internships/enrollments/{body['id']}/documents/expected",
                       headers=login(finalist.user.email)).json()
    assert not any("OFFER" in i["key"].upper() or "Offer" in i["label"]
                   for g in expected for i in g["items"])


@pytest.mark.parametrize("body", [
    {},                                                                    # no host
    {"new_organization": {"name": "Seva", "type": "NGO"},                  # wrong kind
     "industry_mentor_name": "Asha Patel", "industry_mentor_phone": "9811111111"},
    {"new_organization": {"name": "Zeta", "type": "STARTUP"}},             # no supervisor
])
def test_the_industry_track_needs_a_company_and_its_supervisor(api, db, world, login, major, finalist, body):
    assert _enrol(api, login, finalist, major, track="INDUSTRY", **body).status_code == 422


def test_the_industry_track_registers_with_a_company_and_supervisor(api, db, world, login, major, finalist):
    response = _enrol(api, login, finalist, major, track="INDUSTRY",
                      new_organization={"name": "Zeta", "type": "STARTUP"},
                      industry_mentor_name="Mr Iyer", industry_mentor_phone="9811111111")
    assert response.status_code == 201, response.text
    assert not any(s["status"] == "SKIPPED" for s in response.json()["stages"])


# ── allocation completes the coordinator's stage ──────────────────────────
def test_assigning_a_guide_completes_the_allocation_stage(api, db, world, login, coordinator, major, finalist):
    enrollment_id = _enrol(api, login, finalist, major, track="PROJECT").json()["id"]
    response = api.post(f"/api/v1/internships/enrollments/{enrollment_id}/mentor",
                        headers=login(coordinator.email),
                        json={"mentor_faculty_id": world.mentor_ict.faculty.id, "reason": "Guide"})
    assert response.status_code == 200, response.text
    stages = {s["stage"]["code"]: s["status"] for s in api.get(
        f"/api/v1/internships/enrollments/{enrollment_id}", headers=login(finalist.user.email)).json()["stages"]}
    assert stages["GUIDE_ALLOCATION"] == StageStatus.APPROVED.value
    # Taking the guide away reopens it.
    api.post(f"/api/v1/internships/enrollments/{enrollment_id}/mentor", headers=login(coordinator.email),
             json={"mentor_faculty_id": None, "reason": "Reallocating"})
    stages = {s["stage"]["code"]: s["status"] for s in api.get(
        f"/api/v1/internships/enrollments/{enrollment_id}", headers=login(finalist.user.email)).json()["stages"]}
    # It is the student's current step again.
    assert stages["GUIDE_ALLOCATION"] == StageStatus.IN_PROGRESS.value


# ── who runs what ─────────────────────────────────────────────────────────
def test_only_the_project_coordinator_manages_the_project_programmes(db, world, coordinator, major, semester_seven):
    minor, seminar = semester_seven
    for program in (major, minor, seminar):
        assert scope.can_manage_program(db, coordinator.user, program)
        assert not scope.can_manage_program(db, world.summer_ict.user, program)
        assert not scope.can_manage_program(db, world.cssi_ict.user, program)


def test_an_unmapped_programme_type_has_no_coordinator(db, world):
    program = _program(db, world, "R1", InternshipType.RESEARCH, 6, {}, [])
    assert scope.domain_for_program(program) is None
    assert not scope.can_manage_program(db, world.summer_ict.user, program)


def test_appointing_a_project_coordinator_grants_the_route_role(api, db, world, login):
    from app.models.identity import User

    response = api.post("/api/v1/admin/roles", headers=login("admin@test.example.com"),
                        json={"faculty_id": world.mentor_ict.faculty.id, "role": "COORDINATOR",
                              "domain": "MAJOR_PROJECT",
                              "department_id": world.departments["ICT"].id})
    assert response.status_code == 201, response.text
    db.expire_all()
    assert db.get(User, world.mentor_ict.user.id).has_role(Role.INTERNSHIP_COORDINATOR)


def test_batches_are_read_from_configuration():
    from types import SimpleNamespace

    p = SimpleNamespace(config={"admission_years": {"from": 2024}})
    assert engine.governs_batch(p, 2024) and not engine.governs_batch(p, 2023)
    assert engine.governs_batch(SimpleNamespace(config={}), 1999)
