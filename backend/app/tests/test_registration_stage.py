"""Summer Internship registration, as the coordinator and the student meet it.

* The coordinator opens registration for the Semester VI cohort — the
  semester the programme is announced and run in; Semester V is refused.
* Registering completes the Registration stage: the form *is* the
  registration. It used to stay "In progress" for the student to mark complete
  and the mentor to approve, with nothing to check, blocking the offer letter.
  It is not a review, so nobody is scored for it.
"""
from __future__ import annotations

import pytest

from app.models.enums import InternshipType, Role, StageStatus
from app.models.identity import UserRole
from app.models.internships import EnrollmentStageProgress, InternshipProgram, InternshipStage

from app.tests.test_internship_windows import REGISTRATION, _student


@pytest.fixture
def summer(db, world):
    db.add(UserRole(user_id=world.summer_ict.user.id, role=Role.INTERNSHIP_COORDINATOR))
    program = InternshipProgram(
        code="SI-W", name="Summer Internship", type=InternshipType.SUMMER,
        department_id=world.departments["ICT"].id, target_semester=6, announce_from_semester=6,
        requires_organization=False, config={"windows": ["REGISTRATION"]},
    )
    db.add(program)
    db.flush()
    for sequence, (code, owner, document) in enumerate(
            [("REGISTRATION", "STUDENT", False), ("MENTOR_ALLOCATION", "COORDINATOR", False),
             ("OFFER_LETTER", "STUDENT", True)], start=1):
        db.add(InternshipStage(program_id=program.id, code=code, name=code.title(),
                               sequence=sequence, owner_role=owner, requires_document=document,
                               document_type="OFFER_LETTER" if document else None))
    db.flush()
    return program


def _open(api, login, world, program, semester):
    return api.post(f"/api/v1/internships/programs/{program.id}/windows",
                    headers=login(world.summer_ict.email),
                    json={**REGISTRATION, "title": "Summer Internship registration",
                          "cohort_semester": semester})


def test_summer_registration_opens_for_semester_six_only(api, db, world, login, summer):
    assert _open(api, login, world, summer, 5).status_code in (400, 409, 422)
    assert _open(api, login, world, summer, 6).status_code == 201


def test_registering_completes_the_registration_stage(api, db, world, login, summer):
    _open(api, login, world, summer, 6)
    student = _student(db, world, "22BIT301", semester=6)
    response = api.post(f"/api/v1/internships/programs/{summer.id}/enroll",
                        headers=login(student.user.email), json={})
    assert response.status_code == 201, response.text
    rows = {p.stage.code: p for p in db.query(EnrollmentStageProgress).filter_by(
        enrollment_id=response.json()["id"])}
    assert rows["REGISTRATION"].status == StageStatus.APPROVED
    assert rows["REGISTRATION"].submitted_at is None      # never scored as anyone's review
    assert rows["OFFER_LETTER"].status == StageStatus.PENDING


def test_approving_a_stage_verifies_its_document(api, db, world, login, summer):
    from app.models.enums import SubmissionStatus
    from app.models.internships import InternshipDocument, InternshipEnrollment

    _open(api, login, world, summer, 6)
    student = _student(db, world, "22BIT302", semester=6)
    eid = api.post(f"/api/v1/internships/programs/{summer.id}/enroll",
                   headers=login(student.user.email), json={}).json()["id"]
    enrollment = db.get(InternshipEnrollment, eid)
    offer = db.query(InternshipStage).filter_by(program_id=summer.id, code="OFFER_LETTER").one()
    from app.models.enums import FileCategory
    from app.models.system import StoredFile

    stored = StoredFile(filename="offer.pdf", original_name="offer.pdf", content_type="application/pdf",
                        size_bytes=10, category=FileCategory.OFFER_LETTER, storage_key="t/offer.pdf",
                        uploaded_by_user_id=student.user_id)
    db.add(stored)
    db.flush()
    document = InternshipDocument(enrollment_id=eid, stage_id=offer.id, document_type="OFFER_LETTER",
                                  title="Offer letter", uploaded_by_user_id=student.user_id,
                                  file_id=stored.id, status=SubmissionStatus.SUBMITTED)

    db.add(document)
    db.flush()
    from app.services import internships as engine
    engine.review_stage(db, enrollment=enrollment, stage_id=offer.id, approve=True,
                        actor=world.summer_ict.user)
    assert document.status == SubmissionStatus.VERIFIED
    from app.services import documents as docs
    assert not any("Offer" in b for b in docs.progress(db, enrollment)["blockers"])
