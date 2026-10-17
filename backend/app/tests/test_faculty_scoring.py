"""The faculty performance score — its rules, and who may see it.

* Reviewing within 3 days earns +2, within 7 days +1, later −1; a submission
  still waiting after 7 days costs −2 until it is reviewed.
* Marks entered by the presentation deadline earn +3; missing ones cost −5.
* Answering a meeting request within 2 days earns +1; ignoring it past 3 days
  costs −1.
* Work is credited to whoever did it; waiting work is the mentor's.
* A faculty member sees only their own score; the HoD sees the department;
  nobody else sees anyone's.
* Real faculty are not scored until the portal runs on real activity — their
  score would otherwise be made of seeded demo data.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models.engagement import MentorMeeting
from app.models.enums import (
    InternshipType, InternshipWindowKind, MeetingStatus, StageStatus, StudentStatus,
)
from app.models.identity import Student, User
from app.models.internships import (
    EnrollmentStageProgress, InternshipEnrollment, InternshipProgram, InternshipStage,
    InternshipWindow,
)
from app.core.config import settings
from app.services import faculty_scoring as scoring
from app.services import scope

NOW = dt.datetime.now(dt.timezone.utc)
ago = lambda days: NOW - dt.timedelta(days=days)  # noqa: E731


@pytest.fixture(autouse=True)
def live_scoring(monkeypatch):
    """The rule tests score the fixture's (non-demo) faculty as a live portal would."""
    monkeypatch.setattr(settings, "SCORE_REAL_FACULTY", True)


@pytest.mark.parametrize("review_days, expected", [
    (1, ("ON_TIME", 2)), (3, ("ON_TIME", 2)), (5, ("ON_TIME", 1)), (7, ("ON_TIME", 1)),
    (9, ("LATE", -1)),
])
def test_review_points_follow_the_turnaround(review_days, expected):
    outcome, points, _ = scoring.score_review(ago(20), ago(20) + dt.timedelta(days=review_days), NOW)
    assert (outcome, points) == expected


def test_a_waiting_submission_costs_nothing_until_it_is_overdue():
    assert scoring.score_review(ago(5), None, NOW) is None
    assert scoring.score_review(ago(9), None, NOW)[:2] == ("OVERDUE", -2)


def test_meeting_requests_are_scored_on_the_answer_time():
    assert scoring.score_meeting(ago(10), ago(9), False, NOW)[:2] == ("ON_TIME", 1)
    assert scoring.score_meeting(ago(10), ago(4), False, NOW)[:2] == ("LATE", 0)
    assert scoring.score_meeting(ago(5), None, True, NOW)[:2] == ("OVERDUE", -1)
    assert scoring.score_meeting(ago(1), None, True, NOW) is None


@pytest.fixture
def cohort(db, world):
    """A CSSI programme with two of the ICT mentor's students."""
    program = InternshipProgram(code="CSSI-S", name="CSSI", type=InternshipType.CSSI,
                                department_id=world.departments["ICT"].id,
                                config={"windows": ["REGISTRATION", "PRESENTATION"]})
    db.add(program)
    db.flush()
    stage = InternshipStage(program_id=program.id, code="POSTER", name="Poster", sequence=1)
    db.add(stage)
    rows = []
    for i in range(2):
        user = User(email=f"sc{i}@test.example.com", hashed_password="x", full_name=f"Scored {i}")
        db.add(user)
        db.flush()
        student = Student(user_id=user.id, roll_number=f"25BIT8{i}0",
                          program_id=world.programs["B.TECH-ICT"].id,
                          department_id=world.departments["ICT"].id, admission_year=2025,
                          current_semester=3, division="A", cpi=8, backlog_count=0,
                          status=StudentStatus.ACTIVE)
        db.add(student)
        db.flush()
        e = InternshipEnrollment(program_id=program.id, student_id=student.id,
                                 mentor_faculty_id=world.mentor_ict.faculty.id)
        db.add(e)
        db.flush()
        rows.append(e)
    db.flush()
    return program, stage, rows


def _stage(db, enrollment, stage, submitted, reviewed=None, by=None):
    db.add(EnrollmentStageProgress(
        enrollment_id=enrollment.id, stage_id=stage.id,
        status=StageStatus.APPROVED if reviewed else StageStatus.SUBMITTED,
        submitted_at=submitted, reviewed_at=reviewed, reviewed_by_user_id=by))
    db.flush()


def test_work_is_credited_to_the_reviewer_and_waiting_work_to_the_mentor(db, world, cohort):
    _program, stage, (a, b) = cohort
    mentor = world.mentor_ict
    _stage(db, a, stage, ago(10), ago(9), by=mentor.user.id)       # +2, the mentor
    _stage(db, b, stage, ago(12), ago(2), by=world.plain.user.id)   # −1, the reviewer
    scores = scoring.department_scores(db, world.departments["ICT"].id, now=NOW)
    assert scores[mentor.faculty.id].points == 2
    assert scores[world.plain.faculty.id].points == -1


def test_an_overdue_submission_counts_against_the_mentor(db, world, cohort):
    _program, stage, (a, _b) = cohort
    _stage(db, a, stage, ago(10))
    score = scoring.department_scores(db, world.departments["ICT"].id, now=NOW)[world.mentor_ict.faculty.id]
    assert (score.points, score.overdue) == (-2, 1)


def test_marks_missing_at_the_deadline_cost_points(db, world, cohort):
    program, _stage, _rows = cohort
    db.add(InternshipWindow(program_id=program.id, kind=InternshipWindowKind.PRESENTATION,
                            title="P", message="m", opens_at=ago(20), closes_at=ago(1)))
    db.flush()
    score = scoring.department_scores(db, world.departments["ICT"].id, now=NOW)[world.mentor_ict.faculty.id]
    assert score.missed == 2 and score.by_category["MARKS"] == -10


def test_an_unanswered_meeting_request_counts_against_the_mentor(db, world):
    db.add(MentorMeeting(student_id=world.student_a.student.id, faculty_id=world.mentor_ict.faculty.id,
                         title="Help with NGO", requested_at=ago(6), status=MeetingStatus.REQUESTED))
    db.flush()
    score = scoring.department_scores(db, world.departments["ICT"].id, now=NOW)[world.mentor_ict.faculty.id]
    assert score.by_category["MEETING"] == -1


def test_the_rate_needs_enough_activity_before_a_band_is_shown():
    s = scoring.Score(faculty_id=1)
    assert s.band == "Not enough activity" and s.on_time_rate is None


# ── who sees what ─────────────────────────────────────────────────────────
def test_a_faculty_member_sees_their_own_score(api, world, login):
    response = api.get("/api/v1/faculty-scores/me", headers=login(world.mentor_ict.email))
    assert response.status_code == 200, response.text
    assert response.json()["faculty_id"] == world.mentor_ict.faculty.id


def test_students_have_no_score_and_see_none(api, world, login):
    headers = login(world.student_a.email)
    assert api.get("/api/v1/faculty-scores/me", headers=headers).status_code == 403
    assert api.get("/api/v1/faculty-scores/department", headers=headers).status_code == 403
    url = f"/api/v1/faculty-scores/faculty/{world.mentor_ict.faculty.id}"
    assert api.get(url, headers=headers).status_code == 403


def test_a_faculty_member_cannot_see_a_colleagues_score(api, world, login):
    url = f"/api/v1/faculty-scores/faculty/{world.mentor_ict.faculty.id}"
    assert api.get(url, headers=login(world.plain.email)).status_code == 403
    assert api.get("/api/v1/faculty-scores/department", headers=login(world.plain.email)).status_code == 403


def test_the_hod_sees_their_department_without_themselves(api, db, world, login):
    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)
    db.flush()
    response = api.get("/api/v1/faculty-scores/department", headers=login(world.plain.email))
    assert response.status_code == 200, response.text
    ids = {r["faculty_id"] for r in response.json()["faculty"]}
    assert world.mentor_ict.faculty.id in ids and world.plain.faculty.id not in ids
    assert world.summer_cse.faculty.id not in ids          # another department
    cse = world.departments["CSE"].id
    assert api.get(f"/api/v1/faculty-scores/department?department_id={cse}",
                   headers=login(world.plain.email)).status_code == 403


# ── real people are not judged on demo data ───────────────────────────────
def test_real_faculty_are_not_scored_until_scoring_is_switched_on(db, world, cohort, monkeypatch):
    _program, stage, (a, _b) = cohort
    _stage(db, a, stage, ago(10))
    monkeypatch.setattr(settings, "SCORE_REAL_FACULTY", False)
    assert world.mentor_ict.faculty.id not in scoring.department_scores(db, world.departments["ICT"].id, now=NOW)
    world.mentor_ict.faculty.is_demo = True
    db.flush()
    assert scoring.department_scores(db, world.departments["ICT"].id, now=NOW)[world.mentor_ict.faculty.id].points == -2


def test_the_hod_still_sees_unscored_real_faculty_marked_as_such(api, db, world, login, monkeypatch):
    monkeypatch.setattr(settings, "SCORE_REAL_FACULTY", False)
    scope.set_hod(db, world.departments["ICT"], world.plain.faculty)
    db.flush()
    rows = api.get("/api/v1/faculty-scores/department", headers=login(world.plain.email)).json()["faculty"]
    mentor = next(r for r in rows if r["faculty_id"] == world.mentor_ict.faculty.id)
    assert mentor["is_scored"] is False and mentor["band"] == "Not scored yet"
