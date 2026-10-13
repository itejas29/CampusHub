"""An announcement reaches the people it was addressed to, on every screen.

The Announcements page always filtered by audience. The dashboard panel did
not: it listed every published notice, so a first-year's dashboard carried the
Semester VI elective deadline and another mentor's note to their own mentees.
Both screens now ask ``services.announcements.visible_to``; these tests pin that
rule and prove the dashboard panel obeys it.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models.engagement import Announcement, MentorAssignment
from app.models.enums import AudienceType, InternshipType
from app.models.internships import InternshipEnrollment, InternshipProgram
from app.services import announcements as audience

NOW = dt.datetime(2026, 10, 13, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def notices(db, world):
    """One notice per audience the seeded demo data uses."""
    cssi = InternshipProgram(code="CSSI-T", name="CSSI", type=InternshipType.CSSI)
    summer = InternshipProgram(code="SI-T", name="Summer Internship",
                               type=InternshipType.SUMMER)
    db.add_all([cssi, summer])
    db.flush()

    def publish(title, audience_type, ref=None, **extra):
        db.add(Announcement(
            title=title, body=title, audience_type=audience_type, audience_ref_id=ref,
            published_at=NOW - dt.timedelta(days=1), is_published=True, **extra))

    publish("for everyone", AudienceType.ALL)
    publish("semester six elective window", AudienceType.SEMESTER, 6)
    publish("semester five nptel", AudienceType.SEMESTER, 5)
    publish("cssi groups", AudienceType.INTERNSHIP_PROGRAM, cssi.id)
    publish("summer reports", AudienceType.INTERNSHIP_PROGRAM, summer.id)
    publish("mentor slots", AudienceType.MENTEES, world.mentor_ict.faculty.id)
    publish("unpublished draft", AudienceType.ALL, is_pinned=True)
    db.flush()
    draft = db.query(Announcement).filter_by(title="unpublished draft").one()
    draft.is_published = False
    publish("expired", AudienceType.ALL, expires_at=NOW - dt.timedelta(hours=1))
    db.flush()
    return type("Notices", (), {"cssi": cssi, "summer": summer})


def titles(db, account):
    return {a.title for a in db.scalars(audience.visible_to(db, account.user, NOW))}


def in_semester(db, account, semester):
    account.student.current_semester = semester
    db.flush()
    return account


# ── the rule ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("semester", [1, 2, 3, 4, 7, 8])
def test_a_student_outside_the_addressed_semester_sees_only_the_general_notice(
        db, world, notices, semester):
    assert titles(db, in_semester(db, world.student_a, semester)) == {"for everyone"}


@pytest.mark.parametrize("semester,notice", [
    (5, "semester five nptel"), (6, "semester six elective window"),
])
def test_a_semester_notice_reaches_that_semester(db, world, notices, semester, notice):
    assert titles(db, in_semester(db, world.student_a, semester)) == {
        "for everyone", notice}


def test_an_internship_notice_reaches_the_students_enrolled_on_that_programme(
        db, world, notices):
    db.add(InternshipEnrollment(program_id=notices.cssi.id,
                                student_id=world.student_a.student.id))
    db.flush()

    assert titles(db, in_semester(db, world.student_a, 3)) == {
        "for everyone", "cssi groups"}
    # Same semester, same department, not enrolled: not addressed.
    assert titles(db, in_semester(db, world.student_b, 3)) == {"for everyone"}


def test_a_mentors_notice_reaches_their_own_mentees_only(db, world, notices):
    db.add(MentorAssignment(
        student_id=world.student_a.student.id, faculty_id=world.mentor_ict.faculty.id,
        assigned_at=NOW, is_active=True))
    db.flush()

    assert "mentor slots" in titles(db, in_semester(db, world.student_a, 1))
    assert "mentor slots" not in titles(db, in_semester(db, world.student_b, 1))


def test_an_ended_mentorship_no_longer_carries_the_mentors_notices(db, world, notices):
    db.add(MentorAssignment(
        student_id=world.student_a.student.id, faculty_id=world.mentor_ict.faculty.id,
        assigned_at=NOW, is_active=False))
    db.flush()

    assert "mentor slots" not in titles(db, world.student_a)


def test_a_mentor_sees_the_notice_they_addressed_to_their_mentees(db, world, notices):
    assert "mentor slots" in titles(db, world.mentor_ict)
    assert "mentor slots" not in titles(db, world.plain)


def test_drafts_and_expired_notices_reach_nobody(db, world, notices):
    for account in (world.student_a, world.mentor_ict):
        assert not titles(db, account) & {"unpublished draft", "expired"}


# ── the dashboard panel obeys it ───────────────────────────────────────────
def dashboard_titles(api, headers, path):
    response = api.get(f"/api/v1/dashboard/{path}", headers=headers)
    assert response.status_code == 200, response.text
    return {a["title"] for a in response.json()["announcements"]}


def test_a_first_years_dashboard_carries_no_notice_meant_for_someone_else(
        api, world, login, db, notices):
    """Regression for the leak itself."""
    in_semester(db, world.student_a, 1)

    assert dashboard_titles(api, login(world.student_a.email), "student") == {
        "for everyone"}


def test_the_dashboard_and_the_announcements_page_agree(api, world, login, db, notices):
    in_semester(db, world.student_a, 6)
    headers = login(world.student_a.email)

    page = api.get("/api/v1/announcements", headers=headers)
    assert page.status_code == 200
    assert dashboard_titles(api, headers, "student") == {
        a["title"] for a in page.json()} == {"for everyone", "semester six elective window"}


def test_the_faculty_dashboard_does_not_show_student_semester_notices(
        api, world, login, notices):
    assert dashboard_titles(api, login(world.plain.email), "faculty") == {"for everyone"}
