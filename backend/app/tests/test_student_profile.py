"""The unified student profile, and who is allowed to see which part of it.

"Staff" is far too wide a rule for a student record. A club administrator has no
business reading an internship evaluation, and a Summer Internship coordinator
for one department has no business reading another department's students. These
tests hold that line at the section level, not just at the endpoint.
"""
from __future__ import annotations

import pytest


def profile(api, headers, student_id):
    return api.get(f"/api/v1/student-profile/{student_id}", headers=headers)


# ── who gets in at all ─────────────────────────────────────────────────────
def test_a_student_sees_their_own_profile_in_full(api, world, login):
    response = profile(api, login(world.student_a.email), world.student_a.student.id)
    assert response.status_code == 200
    assert set(response.json()["visible_sections"]) == {
        "personal", "academic", "internship", "documents", "evaluation", "mentor"}


def test_a_student_cannot_open_another_students_profile(api, world, login):
    response = profile(api, login(world.student_a.email), world.student_b.student.id)
    assert response.status_code == 403
    assert "mentor" in response.json()["error"]["message"]


def test_a_super_admin_sees_everything(api, world, login):
    response = profile(api, login(world.admin.email), world.student_a.student.id)
    assert response.status_code == 200


def test_faculty_with_no_relationship_to_the_student_are_refused(api, world, login):
    """Being staff is not a relationship. The plain faculty member mentors
    nobody and coordinates nothing."""
    response = profile(api, login(world.plain.email), world.student_a.student.id)
    assert response.status_code == 403


def test_an_assigned_mentor_sees_the_full_profile(api, world, login, db):
    import datetime as dt

    from app.models.engagement import MentorAssignment

    db.add(MentorAssignment(
        student_id=world.student_a.student.id,
        faculty_id=world.mentor_ict.faculty.id,
        assigned_at=dt.datetime.now(dt.timezone.utc), is_active=True))
    db.flush()

    response = profile(api, login(world.mentor_ict.email), world.student_a.student.id)
    assert response.status_code == 200
    assert "evaluation" in response.json()["visible_sections"]


def test_a_mentor_of_a_different_student_is_still_refused(api, world, login, db):
    """An assignment is to one student, not to a cohort.

    Holding a MENTOR grant for CSSI in ICT is not a reason to read every ICT
    student's record — mentor access is earned per student, through a mentorship
    assignment or by being the mentor on that student's own internship.
    """
    import datetime as dt

    from app.models.engagement import MentorAssignment

    db.add(MentorAssignment(
        student_id=world.student_a.student.id,
        faculty_id=world.mentor_ict.faculty.id,
        assigned_at=dt.datetime.now(dt.timezone.utc), is_active=True))
    db.flush()

    response = profile(api, login(world.mentor_ict.email), world.student_b.student.id)
    assert response.status_code == 403


def test_a_coordinator_of_another_department_is_refused(api, world, login):
    """The CSE Summer coordinator has no reach into ICT."""
    response = profile(api, login(world.summer_cse.email), world.student_a.student.id)
    assert response.status_code == 403


def test_an_elective_coordinator_sees_the_academic_side_only(api, world, login, db):
    """Scope is per section: coordinating ICT's Open Electives is a reason to
    see a student's curriculum, not their internship evaluation marks."""
    import datetime as dt

    from app.models.enums import AssignedRole, CoordinationDomain
    from app.models.identity import FacultyRoleAssignment

    db.add(FacultyRoleAssignment(
        faculty_id=world.plain.faculty.id, role=AssignedRole.COORDINATOR,
        domain=CoordinationDomain.OPEN_ELECTIVE,
        department_id=world.departments["ICT"].id, is_active=True,
        assigned_at=dt.datetime.now(dt.timezone.utc)))
    db.flush()

    response = profile(api, login(world.plain.email), world.student_a.student.id)
    assert response.status_code == 200
    sections = set(response.json()["visible_sections"])
    assert sections == {"personal", "academic"}
    assert response.json()["evaluations"] == []
    assert response.json()["mentor"] is None


# ── the content itself ─────────────────────────────────────────────────────
def test_the_profile_resolves_the_curriculum_through_the_batch(
    api, world, login, make_curriculum
):
    make_curriculum("B.TECH-ICT", "2024-28", 2024, None,
                    [(4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL")])
    response = profile(api, login(world.admin.email), world.student_a.student.id)
    academic = response.json()["academic"]
    assert academic["curriculum_version"] == "2024-28"
    assert academic["batch_label"] == "2024 onward"
    assert any(c["code"] == "OE1"
               for c in academic["current_semester_components"])


def test_cpi_appears_on_the_profile_but_carries_its_meaning(api, world, login):
    """CPI is shown because a mentor needs it — it remains an input to Minor
    eligibility only, never to elective allocation."""
    response = profile(api, login(world.admin.email), world.student_a.student.id)
    assert response.json()["academic"]["cpi"] == 8.0


def test_a_student_with_no_curriculum_still_renders(api, world, login):
    """No published curriculum is a real state — the profile must explain it,
    not fail."""
    response = profile(api, login(world.admin.email), world.student_a.student.id)
    assert response.status_code == 200
    assert response.json()["academic"]["curriculum_version"] is None


def test_the_profile_never_exposes_a_storage_key(api, world, login):
    response = profile(api, login(world.admin.email), world.student_a.student.id)
    assert "storage_key" not in response.text
    assert "/media/" not in response.text


def test_an_unknown_student_is_a_clean_404(api, world, login):
    response = profile(api, login(world.admin.email), 999999)
    assert response.status_code == 404
