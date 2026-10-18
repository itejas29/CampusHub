"""Bugs found by walking every module end to end against the seeded demo data.

Each test names the behaviour that was broken. Grouped by module:

* **CSSI** — a registration went through with no NGO, or with a company in
  place of one; registering twice overwrote the first record; a student could
  delete a document their mentor had already verified.
* **Summer Internship** — report #50 of an 8-report programme was accepted; a
  review could set any status, or send a report back without saying why; the
  programme export always failed; a mentor could allocate presentation slots.
* **NPTEL** — a student could set their own final score; "pending" counted as
  a decision; a certificate was rejected without a reason, and a verified one
  could be replaced; the Department Admin's queue held every department.
* **Electives** — a seat showed on every student screen the moment the
  allocation ran, before publishing; a round with committed seats reopened.
* **Minors** — re-applying after withdrawing failed with a database error; a
  coordinator's application list held every department; the registration
  window compared a zoned and an unzoned time (a 500 on sign-in under SQLite).
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.academics import ElectiveAllocation, MoocRegistration
from app.models.enums import (
    AllocationStatus, DocumentType, EnrollmentStatus, InternshipType, ProgramStatus,
    ReportFrequency, Role, SubmissionStatus, VerificationStatus,
)
from app.models.identity import UserRole
from app.models.internships import (
    InternshipDocument, InternshipEnrollment, InternshipProgram, InternshipReport,
)
from app.models.minors import MinorApplication
from app.models.system import StoredFile
from app.services import minors as minor_service

from app.tests.test_internship_windows import (  # noqa: F401  (fixtures)
    _enrol, _open_registration, _student, cssi,
)
from app.tests.test_registration_rounds_api import (  # noqa: F401  (fixtures)
    WINDOWS, campus, move, payload,
)

NOW = dt.datetime.now(dt.timezone.utc)
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


# ── CSSI ──────────────────────────────────────────────────────────────────
def test_a_cssi_registration_needs_an_organisation(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT101")
    response = api.post(f"/api/v1/internships/programs/{cssi.id}/enroll",
                        headers=login(student.user.email),
                        json={"industry_mentor_name": "Asha", "industry_mentor_phone": "98"})
    assert response.status_code == 422
    assert "organisation" in response.text


def test_cssi_accepts_only_an_ngo_as_host(api, db, world, login, cssi):
    cssi.allowed_organization_types = ["NGO"]
    db.flush()
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT102")
    response = _enrol(api, login, student, cssi,
                      new_organization={"name": "Acme Ltd", "type": "COMPANY"})
    assert response.status_code == 422
    assert "ngo" in response.text.lower()


def test_registering_twice_is_refused_rather_than_overwriting(api, db, world, login, cssi):
    _open_registration(api, login, world, cssi)
    student = _student(db, world, "25BIT103")
    assert _enrol(api, login, student, cssi).status_code == 201
    again = _enrol(api, login, student, cssi,
                   new_organization={"name": "Another NGO", "type": "NGO"})
    assert again.status_code == 409
    enrollment = db.scalar(select(InternshipEnrollment).where(
        InternshipEnrollment.student_id == student.id))
    assert enrollment.organization.name == "NGO for 25BIT103"


# ── a Summer Internship record to act on ──────────────────────────────────
@pytest.fixture
def summer(db, world):
    db.add(UserRole(user_id=world.summer_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    program = InternshipProgram(
        code="SI-T", name="Summer Internship", type=InternshipType.SUMMER,
        department_id=world.departments["ICT"].id, target_semester=6,
        announce_from_semester=6, status=ProgramStatus.REGISTRATION_OPEN,
        report_frequency=ReportFrequency.WEEKLY, expected_report_count=8,
        allowed_organization_types=["COMPANY"], config={})
    db.add(program)
    db.flush()
    student = _student(db, world, "23BIT201", semester=6)
    enrollment = InternshipEnrollment(program_id=program.id, student_id=student.id,
                                      mentor_faculty_id=world.mentor_ict.faculty.id,
                                      status=EnrollmentStatus.IN_PROGRESS)
    db.add(enrollment)
    db.flush()
    return program, student, enrollment


def _document(db, enrollment, status):
    stored = StoredFile(filename="doc.pdf", storage_key="k/doc.pdf", original_name="doc.pdf",
                        content_type="application/pdf", size_bytes=len(PDF),
                        category="CERTIFICATE")
    db.add(stored)
    db.flush()
    doc = InternshipDocument(enrollment_id=enrollment.id, document_type=DocumentType.CERTIFICATE,
                             title="Certificate", file_id=stored.id, status=status,
                             submitted_at=NOW)
    db.add(doc)
    db.flush()
    return doc


@pytest.mark.parametrize("status", [SubmissionStatus.VERIFIED, SubmissionStatus.UNDER_REVIEW])
def test_a_student_cannot_delete_a_verified_or_in_review_document(api, db, world, login, summer, status):
    _program, student, enrollment = summer
    doc = _document(db, enrollment, status)
    response = api.delete(f"/api/v1/internships/documents/{doc.id}",
                          headers=login(student.user.email))
    assert response.status_code in (400, 409, 422)
    assert db.get(InternshipDocument, doc.id) is not None


def test_a_report_number_outside_the_schedule_is_refused(api, db, world, login, summer):
    _program, student, enrollment = summer
    body = {"report_type": "WEEKLY", "summary": "Built the ingestion pipeline."}
    url = f"/api/v1/internships/enrollments/{enrollment.id}/reports"
    assert api.post(url, headers=login(student.user.email),
                    json={**body, "sequence_number": 9}).status_code == 422
    assert api.post(url, headers=login(student.user.email),
                    json={**body, "sequence_number": 8}).status_code == 201


def _report(db, enrollment, status=SubmissionStatus.SUBMITTED):
    report = InternshipReport(enrollment_id=enrollment.id, report_type="WEEKLY",
                              sequence_number=1, summary="Week one: onboarding.",
                              status=status, submitted_at=NOW)
    db.add(report)
    db.flush()
    return report


@pytest.mark.parametrize("body", [{"status": "NOT_SUBMITTED"}, {"status": "SUBMITTED"},
                                  {"status": "REJECTED"}, {"status": "REJECTED", "feedback": "  "}])
def test_a_report_review_is_a_real_decision_with_a_reason_to_send_back(api, db, world, login, summer, body):
    _program, _student_, enrollment = summer
    report = _report(db, enrollment)
    response = api.post(f"/api/v1/internships/reports/{report.id}/review",
                        headers=login(world.mentor_ict.email), json=body)
    assert response.status_code == 422


def test_an_approved_report_cannot_be_overwritten(api, db, world, login, summer):
    _program, student, enrollment = summer
    _report(db, enrollment, SubmissionStatus.APPROVED)
    response = api.post(f"/api/v1/internships/enrollments/{enrollment.id}/reports",
                        headers=login(student.user.email),
                        json={"report_type": "WEEKLY", "sequence_number": 1,
                              "summary": "Rewriting history after approval."})
    assert response.status_code in (400, 409, 422)


def test_the_programme_export_downloads(api, db, world, login, summer):
    program, student, _enrollment = summer
    response = api.get(f"/api/v1/internships/programs/{program.id}/export",
                       headers=login(world.summer_ict.email))
    assert response.status_code == 200, response.text
    assert student.roll_number in response.text and "Mentor ICT" in response.text


def test_only_the_coordinator_allocates_a_presentation_slot(api, db, world, login, summer):
    _program, _student_, enrollment = summer
    response = api.post(f"/api/v1/internships/enrollments/{enrollment.id}/presentation",
                        headers=login(world.mentor_ict.email),
                        json={"scheduled_at": (NOW + dt.timedelta(days=3)).isoformat()})
    assert response.status_code == 403


# ── NPTEL ─────────────────────────────────────────────────────────────────
@pytest.fixture
def mooc(db, world, campus):
    """A registration with a certificate, in ICT, awaiting the coordinator."""
    from app.models.academics import Course, CourseOffering
    from app.models.enums import AssignedRole, CoordinationDomain, OfferingStatus
    from app.models.identity import FacultyRoleAssignment

    course = Course(code="NPTEL-X", title="NPTEL Course", department_id=world.departments["ICT"].id,
                    credits=3, platform="NPTEL")
    db.add(course)
    db.flush()
    offering = CourseOffering(course_id=course.id,
                              semester_id=campus.offerings["OE1"][0].semester_id,
                              status=OfferingStatus.OPEN)
    db.add(offering)
    db.flush()
    # Not world.plain: the campus fixture makes them HoD, who holds no role.
    db.add(FacultyRoleAssignment(faculty_id=world.summer_ict.faculty.id, role=AssignedRole.COORDINATOR,
                                 domain=CoordinationDomain.MOOC,
                                 department_id=world.departments["ICT"].id, is_active=True,
                                 assigned_at=NOW))
    stored = StoredFile(filename="cert.pdf", storage_key="k/cert.pdf", original_name="cert.pdf",
                        content_type="application/pdf", size_bytes=10, category="CERTIFICATE")
    db.add(stored)
    db.flush()
    reg = MoocRegistration(student_id=world.student_a.student.id, course_offering_id=offering.id,
                           platform="NPTEL", certificate_file_id=stored.id,
                           verification_status=VerificationStatus.PENDING)
    db.add(reg)
    db.flush()
    return reg


def test_a_student_cannot_set_their_own_nptel_score(api, db, world, login, mooc):
    response = api.patch(f"/api/v1/mooc/{mooc.id}", headers=login(world.student_a.email),
                         json={"final_score": 99})
    assert response.status_code == 200
    db.refresh(mooc)
    assert mooc.final_score is None


@pytest.mark.parametrize("body", [{"verification_status": "PENDING"},
                                  {"verification_status": "REJECTED"}])
def test_an_nptel_decision_is_verify_or_reject_with_a_reason(api, db, world, login, mooc, body):
    response = api.post(f"/api/v1/mooc/admin/{mooc.id}/verify",
                        headers=login(world.summer_ict.email), json=body)
    assert response.status_code == 422


def test_a_verified_nptel_certificate_cannot_be_replaced(api, db, world, login, mooc):
    mooc.verification_status = VerificationStatus.VERIFIED
    db.flush()
    response = api.post(f"/api/v1/mooc/{mooc.id}/certificate",
                        headers=login(world.student_a.email),
                        files={"file": ("c.pdf", PDF, "application/pdf")})
    assert response.status_code in (400, 409, 422)


def test_the_department_admin_queue_holds_only_their_department(api, db, world, login, mooc):
    from app.models.identity import Student

    office = world.summer_cse          # give a CSE account the Department Admin role
    db.add(UserRole(user_id=office.user.id, role=Role.DEPARTMENT_ADMIN))
    db.flush()
    rows = api.get("/api/v1/mooc/admin/registrations", headers=login(office.email)).json()
    departments = {db.get(Student, r["student_id"]).department_id for r in rows}
    assert world.departments["ICT"].id not in departments


# ── electives ─────────────────────────────────────────────────────────────
@pytest.fixture
def allocated_round(api, db, world, login, campus, make_student):
    """A round that has run (seats written) but is not yet published."""
    headers = login(campus.open.email)
    created = api.post(WINDOWS, headers=headers, json=payload(campus, code="OE1-AUDIT"))
    rid = created.json()["id"]
    offerings = campus.offerings["OE1"]
    api.post(f"{WINDOWS}/{rid}/offerings", headers=headers,
             json={"offering_ids": [o.id for o in offerings]})
    assert move(api, headers, rid, "OPEN").status_code == 200
    student = make_student("B.TECH-ICT", 2024, semester=3)
    db.add(ElectiveAllocation(student_id=student.id,
                              curriculum_component_id=campus.components["OE1"].id,
                              course_offering_id=offerings[0].id,
                              status=AllocationStatus.ALLOCATED))
    db.flush()
    assert move(api, headers, rid, "LOCKED").status_code == 200
    return rid, student, headers


def _student_headers(api, db, student):
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(str(student.user_id))}"}


def test_a_seat_is_hidden_from_the_student_until_the_round_is_published(api, db, world, campus, allocated_round):
    rid, student, headers = allocated_round
    me = _student_headers(api, db, student)
    assert api.get("/api/v1/electives/allocations/me", headers=me).json() == []
    assert move(api, headers, rid, "ALLOCATED").status_code == 200
    assert api.get("/api/v1/electives/allocations/me", headers=me).json() == []
    assert move(api, headers, rid, "PUBLISHED").status_code == 200
    assert len(api.get("/api/v1/electives/allocations/me", headers=me).json()) == 1


def test_a_round_with_committed_seats_cannot_reopen(api, db, world, campus, allocated_round):
    rid, _student_, headers = allocated_round
    response = move(api, headers, rid, "OPEN")
    assert response.status_code in (400, 409, 422)
    assert "already allocated" in response.text


# ── minors ────────────────────────────────────────────────────────────────
def test_the_minor_window_compares_times_whatever_their_zone(db):
    from types import SimpleNamespace

    naive = SimpleNamespace(application_opens_at=dt.datetime(2020, 1, 1),
                            application_closes_at=dt.datetime(2999, 1, 1))
    assert minor_service.application_window_open(naive) is True


@pytest.fixture
def minor(db, world):
    from app.models.minors import MinorProgram

    program = MinorProgram(code="MIN-T", name="Minor in Testing",
                           department_id=world.departments["CSE"].id, capacity=10,
                           eligible_from_semester=3, min_cpi=7.0, max_backlogs=0,
                           application_opens_at=NOW - dt.timedelta(days=1),
                           application_closes_at=NOW + dt.timedelta(days=10),
                           rules={"ranking": {"criteria": [{"field": "cpi", "direction": "desc"}]}})
    db.add(program)
    db.flush()
    return program


def test_withdrawing_then_applying_again_works(api, db, world, login, minor):
    world.student_a.student.current_semester = 3      # applications are made in Semester III
    db.flush()
    headers = login(world.student_a.email)
    assert api.post("/api/v1/minors/apply", headers=headers,
                    json={"preferences": [minor.id]}).status_code == 201
    assert api.delete("/api/v1/minors/applications", headers=headers).status_code == 200
    again = api.post("/api/v1/minors/apply", headers=headers, json={"preferences": [minor.id]})
    assert again.status_code == 201, again.text


def test_a_minor_coordinator_sees_only_applications_in_their_scope(api, db, world, login, minor):
    from app.models.enums import AssignedRole, CoordinationDomain
    from app.models.identity import FacultyRoleAssignment

    # A CSE student applying to the CSE minor is nothing to do with ICT.
    cse = _student(db, world, "24BCE001", semester=4, dept="CSE")
    db.add(MinorApplication(student_id=cse.id, minor_program_id=minor.id, preference_order=1,
                            status="SUBMITTED", submitted_at=NOW, cpi_at_application=8))
    db.add(FacultyRoleAssignment(faculty_id=world.plain.faculty.id, role=AssignedRole.COORDINATOR,
                                 domain=CoordinationDomain.MINOR,
                                 department_id=world.departments["ICT"].id, is_active=True,
                                 assigned_at=NOW))
    db.flush()
    response = api.get("/api/v1/minors/applications", headers=login(world.plain.email))
    assert response.status_code == 200, response.text
    assert all(r["student_id"] != cse.id for r in response.json())
