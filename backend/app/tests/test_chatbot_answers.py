"""The assistant answers from the asker's own records, and links only to real pages.

* "What is my name?" is answered with the name, roll number and semester.
* A student's meeting requests are listed with their status; asking how to
  request one names their mentor and opens the request form.
* A faculty member sees the requests waiting for their reply.
* An unmatched question says so, rather than giving the same help text as if
  it had been answered.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest

from app.models.engagement import MentorAssignment, MentorMeeting
from app.models.enums import MeetingStatus

NOW = dt.datetime.now(dt.timezone.utc)
APP_ROUTES = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src" / "App.tsx"


def ask(api, headers, question):
    response = api.post("/api/v1/chatbot/query", json={"query": question}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def mentored(db, world):
    db.add(MentorAssignment(student_id=world.student_a.student.id,
                            faculty_id=world.mentor_ict.faculty.id, is_active=True))
    db.add(MentorMeeting(student_id=world.student_a.student.id, faculty_id=world.mentor_ict.faculty.id,
                         title="Elective guidance", requested_at=NOW - dt.timedelta(hours=3),
                         status=MeetingStatus.REQUESTED))
    db.flush()


def test_a_student_asking_their_name_gets_it(api, world, login):
    reply = ask(api, login(world.student_a.email), "what is my name")["reply"]
    assert "Student A" in reply and world.student_a.student.roll_number in reply
    assert "Semester:** 4" in reply


def test_a_student_sees_their_meeting_requests(api, world, login, mentored):
    reply = ask(api, login(world.student_a.email), "I requested a meeting, what happened?")["reply"]
    assert "Elective guidance" in reply and "Requested" in reply


def test_asking_how_to_request_a_meeting_names_the_mentor_and_opens_the_form(api, world, login, mentored):
    data = ask(api, login(world.student_a.email), "How do I request a meeting with my mentor?")
    assert "Mentor ICT" in data["reply"]
    assert any(link["path"] == "/mentorship?request=1" for link in data["action_links"])


def test_a_faculty_member_sees_requests_waiting_for_them(api, world, login, mentored):
    reply = ask(api, login(world.mentor_ict.email), "show pending meeting requests")["reply"]
    assert "Waiting for your reply (1)" in reply and "Student A" in reply


def test_an_unmatched_question_says_it_was_not_understood(api, world, login):
    reply = ask(api, login(world.student_a.email), "what's the canteen menu")["reply"]
    assert "couldn't match" in reply


def test_every_link_the_assistant_gives_is_a_page_the_app_has(api, world, login, mentored):
    routes = {"/"} | {"/" + p for p in re.findall(r'path="([^"]+)"', APP_ROUTES.read_text())}
    questions = ["hi", "my name", "who is my mentor", "my meetings", "internship status",
                 "are electives open", "minor", "nptel", "my cpi", "attendance", "grading"]
    for email, extra in [(world.student_a.email, []),
                         (world.mentor_ict.email, ["my mentees", "what needs review", "my score", "my roles"])]:
        headers = login(email)
        for question in questions + extra:
            for link in ask(api, headers, question)["action_links"]:
                assert link["path"].split("?")[0] in routes, (question, link["path"])
