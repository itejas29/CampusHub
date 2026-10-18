"""Coordinator tools added after the module audit.

* **Stages and rubric** — the coordinator edits them; a stage with submitted
  work cannot be removed; a rubric is fixed once marks exist; each pending
  item is confirmed on the record.
* **Final marks wait for the work** — every mandatory stage approved and its
  document verified.
* **One marker per student** — the student's mentor, not a group lead.
* **Teams and guide preferences** — formed by students, one guide per team,
  allocated by preference.
* **Early registration** — Semester VIII registration opens in Semester VII;
  work still waits for Semester VIII.
"""
from __future__ import annotations

import pytest

from app.models.enums import (
    AssignedRole, CoordinationDomain, DocumentType, EvaluationStatus, InternshipType,
    ProgramStatus, ReportFrequency, Role, StageStatus,
)
from app.models.identity import FacultyRoleAssignment, UserRole
from app.models.internships import (
    EvaluationCriteria, InternshipEnrollment, InternshipEvaluation, InternshipGroup,
    InternshipProgram, InternshipStage,
)
from app.services import internships as engine

from app.tests.test_internship_windows import _student  # noqa: F401


@pytest.fixture
def coordinator(db, world):
    db.add(FacultyRoleAssignment(faculty_id=world.plain.faculty.id, role=AssignedRole.COORDINATOR,
                                 domain=CoordinationDomain.PROJECT,
                                 department_id=world.departments["ICT"].id, is_active=True))
    db.add(UserRole(user_id=world.plain.user.id, role=Role.INTERNSHIP_COORDINATOR))
    db.flush()
    return world.plain


@pytest.fixture
def project(db, world):
    program = InternshipProgram(
        code="MP7-T", name="Minor Project", type=InternshipType.MINOR_PROJECT,
        department_id=world.departments["ICT"].id, target_semester=7, announce_from_semester=7,
        status=ProgramStatus.REGISTRATION_OPEN, requires_organization=False,
        report_frequency=ReportFrequency.NONE,
        config={"team_size": {"min": 1, "max": 3}, "guide_preferences": 2,
                "requires_faculty_confirmation": ["stages", "rubric"]})
    db.add(program)
    db.flush()
    for i, (code, owner, doc) in enumerate([("SYNOPSIS", "STUDENT", DocumentType.SYNOPSIS),
                                            ("GUIDE_ALLOCATION", "COORDINATOR", None),
                                            ("EVALUATION", "FACULTY", None)], 1):
        db.add(InternshipStage(program_id=program.id, code=code, name=code.title(), sequence=i,
                               owner_role=owner, requires_document=doc is not None, document_type=doc))
    db.add(EvaluationCriteria(program_id=program.id, code="WORK", name="Work", max_marks=100, sequence=1))
    db.flush()
    return program


def _register(api, login, student, program):
    response = api.post(f"/api/v1/internships/programs/{program.id}/enroll",
                        headers=login(student.user.email), json={})
    assert response.status_code == 201, response.text
    return response.json()


def _students(db, world, n):
    return [_student(db, world, f"23BIT9{i:02d}", semester=7) for i in range(n)]


# ── stages and rubric ─────────────────────────────────────────────────────
def _stage_items(program):
    return [{"id": s.id, "name": s.name, "owner_role": s.owner_role,
             "requires_document": s.requires_document,
             "document_type": s.document_type.value if s.document_type else None}
            for s in sorted(program.stages, key=lambda s: s.sequence)]


def test_a_new_stage_reaches_every_record(api, db, world, login, coordinator, project):
    student = _students(db, world, 1)[0]
    enrollment = _register(api, login, student, project)
    items = _stage_items(project)
    items.insert(1, {"name": "Literature Review", "owner_role": "STUDENT",
                     "requires_document": True, "document_type": "REPORT"})
    response = api.put(f"/api/v1/internships/programs/{project.id}/stages",
                       headers=login(coordinator.email), json={"stages": items})
    assert response.status_code == 200, response.text
    record = api.get(f"/api/v1/internships/enrollments/{enrollment['id']}",
                     headers=login(student.user.email)).json()
    assert [s["stage"]["code"] for s in record["stages"]][:2] == ["SYNOPSIS", "LITERATURE_REVIEW"]


def test_a_stage_with_submitted_work_cannot_be_removed(api, db, world, login, coordinator, project):
    student = _students(db, world, 1)[0]
    enrollment = _register(api, login, student, project)
    synopsis = next(s for s in project.stages if s.code == "SYNOPSIS")
    api.post(f"/api/v1/internships/enrollments/{enrollment['id']}/stages/submit",
             headers=login(student.user.email), json={"stage_id": synopsis.id, "data": {}})
    items = [i for i in _stage_items(project) if i["id"] != synopsis.id]
    response = api.put(f"/api/v1/internships/programs/{project.id}/stages",
                       headers=login(coordinator.email), json={"stages": items})
    assert response.status_code in (400, 409, 422)
    assert "cannot be removed" in response.text


def test_only_the_programmes_coordinator_edits_it(api, db, world, login, project):
    response = api.put(f"/api/v1/internships/programs/{project.id}/stages",
                       headers=login(world.cssi_ict.email), json={"stages": _stage_items(project)})
    assert response.status_code == 403


def test_the_rubric_is_fixed_once_marks_exist(api, db, world, login, coordinator, project):
    url = f"/api/v1/internships/programs/{project.id}/criteria"
    body = {"criteria": [{"name": "Work", "max_marks": 60}, {"name": "Viva", "max_marks": 40}]}
    assert api.put(url, headers=login(coordinator.email), json=body).status_code == 200
    student = _students(db, world, 1)[0]
    enrollment = _register(api, login, student, project)
    db.add(InternshipEvaluation(enrollment_id=enrollment["id"], evaluator_user_id=coordinator.user.id,
                                status=EvaluationStatus.SUBMITTED, evaluation_round=1))
    db.flush()
    response = api.put(url, headers=login(coordinator.email), json=body)
    assert response.status_code in (400, 409, 422) and "fixed" in response.text


def test_each_pending_item_is_confirmed_on_the_record(api, db, world, login, coordinator, project):
    url = f"/api/v1/internships/programs/{project.id}/confirm"
    response = api.post(url, headers=login(coordinator.email), json={"item": "stages"})
    assert response.status_code == 200 and response.json()["needs_confirmation"] == ["rubric"]
    assert api.post(url, headers=login(coordinator.email), json={"item": "stages"}).status_code == 422


# ── final marks wait for the work ─────────────────────────────────────────
def test_marks_cannot_be_finalised_before_the_work_is_verified(api, db, world, login, project):
    student = _students(db, world, 1)[0]
    enrollment = _register(api, login, student, project)
    row = db.get(InternshipEnrollment, enrollment["id"])
    row.mentor_faculty_id = world.mentor_ict.faculty.id
    db.flush()
    criterion = project.criteria[0]
    response = api.post(f"/api/v1/internships/enrollments/{row.id}/evaluation",
                        headers=login(world.mentor_ict.email),
                        json={"scores": [{"criteria_id": criterion.id, "marks": 80}], "finalise": True})
    assert response.status_code in (400, 409, 422)
    assert "Synopsis" in response.text
    # A draft is still accepted.
    draft = api.post(f"/api/v1/internships/enrollments/{row.id}/evaluation",
                     headers=login(world.mentor_ict.email),
                     json={"scores": [{"criteria_id": criterion.id, "marks": 80}]})
    assert draft.status_code == 200


# ── one marker per student ────────────────────────────────────────────────
def test_a_group_lead_does_not_mark_another_mentors_student(db, world, project):
    group = InternshipGroup(program_id=project.id, name="G1", faculty_id=world.plain.faculty.id, capacity=10)
    db.add(group)
    db.flush()
    student = _students(db, world, 1)[0]
    enrollment = InternshipEnrollment(program_id=project.id, student_id=student.id, group_id=group.id,
                                      mentor_faculty_id=world.mentor_ict.faculty.id)
    db.add(enrollment)
    db.flush()
    assert engine.can_review(enrollment, world.mentor_ict.faculty)
    assert not engine.can_review(enrollment, world.plain.faculty)
    project.config = {**project.config, "group_lead_reviews": True}
    assert engine.can_review(enrollment, world.plain.faculty)


# ── teams and guide preferences ───────────────────────────────────────────
def test_a_team_shares_its_preferences_and_its_guide(api, db, world, login, coordinator, project):
    lead, mate, solo = _students(db, world, 3)
    lead_e, mate_e, solo_e = (_register(api, login, s, project) for s in (lead, mate, solo))
    headers = login(lead.user.email)
    team = api.post(f"/api/v1/internships/enrollments/{lead_e['id']}/team", headers=headers,
                    json={"name": "Vision"}).json()["team"]
    assert api.post(f"/api/v1/internships/teams/{team['id']}/members", headers=headers,
                    json={"roll_number": mate.roll_number}).status_code == 200
    guides = [world.mentor_ict.faculty.id, world.summer_ict.faculty.id]
    assert api.put(f"/api/v1/internships/enrollments/{mate_e['id']}/guide-preferences",
                   headers=login(mate.user.email), json={"faculty_ids": guides}).status_code in (400, 409, 422)
    assert api.put(f"/api/v1/internships/enrollments/{lead_e['id']}/guide-preferences",
                   headers=headers, json={"faculty_ids": guides}).status_code == 200
    assert api.put(f"/api/v1/internships/enrollments/{solo_e['id']}/guide-preferences",
                   headers=login(solo.user.email), json={"faculty_ids": guides[1:]}).status_code == 200
    response = api.post(f"/api/v1/internships/programs/{project.id}/assign-mentors",
                        headers=login(coordinator.email), json={"by_preference": True})
    assert response.status_code == 200, response.text
    mentors = {e.id: e.mentor_faculty_id for e in db.query(InternshipEnrollment).filter_by(program_id=project.id)}
    assert mentors[lead_e["id"]] == mentors[mate_e["id"]] == guides[0]
    assert mentors[solo_e["id"]] == guides[1]
    # The guide-allocation stage completed for them too.
    lead_row = db.get(InternshipEnrollment, lead_e["id"])
    db.refresh(lead_row)
    allocation = next(p for p in lead_row.stage_progress if p.stage.code == "GUIDE_ALLOCATION")
    assert allocation.status == StageStatus.APPROVED
    # With a guide the team is fixed.
    late = _student(db, world, "23BIT999", semester=7)
    _register(api, login, late, project)
    added = api.post(f"/api/v1/internships/teams/{team['id']}/members", headers=headers,
                     json={"roll_number": late.roll_number})
    assert added.status_code in (400, 409, 422)


def test_a_team_is_capped_at_its_size(api, db, world, login, project):
    students = _students(db, world, 4)
    entries = [_register(api, login, s, project) for s in students]
    headers = login(students[0].user.email)
    team = api.post(f"/api/v1/internships/enrollments/{entries[0]['id']}/team", headers=headers,
                    json={"name": "Big"}).json()["team"]
    for s in students[1:3]:
        assert api.post(f"/api/v1/internships/teams/{team['id']}/members", headers=headers,
                        json={"roll_number": s.roll_number}).status_code == 200
    over = api.post(f"/api/v1/internships/teams/{team['id']}/members", headers=headers,
                    json={"roll_number": students[3].roll_number})
    assert over.status_code in (400, 409, 422) and "at most 3" in over.text


# ── early registration ────────────────────────────────────────────────────
def test_semester_eight_registration_opens_in_semester_seven(db, world):
    from types import SimpleNamespace

    program = SimpleNamespace(target_semester=8, announce_from_semester=7, visible_to_semester=8,
                              config={"register_from_semester": 7})
    assert engine.registers_early(program, 7)
    engine.assert_can_register_now(program, 7)
    with pytest.raises(Exception):
        engine.assert_submissions_open(program, 7)      # work still waits for Semester VIII
    assert not engine.registers_early(SimpleNamespace(**{**program.__dict__, "config": {}}), 7)
