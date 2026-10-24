"""The unified calendar: one feed, sorted, whatever database stores the dates.

Every datetime column is ``timezone=True``. PostgreSQL keeps the zone; SQLite
(the tests, the browser tests, local previews) gives the value back without
one. The feed builds some times itself — an internship's final-submission
deadline — with a zone, so the two kinds met in one list.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.models.community import Event
from app.models.enums import EventStatus, InternshipType
from app.models.internships import InternshipEnrollment, InternshipProgram

NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


@pytest.fixture
def feed(api, world, login, db):
    """`student_a`'s calendar with a published event and an internship deadline."""
    db.add(Event(title="Orientation", slug="calendar-orientation",
                 status=EventStatus.PUBLISHED, start_at=NOW + dt.timedelta(days=3)))
    program = InternshipProgram(code="CSSI-CAL", name="CSSI", type=InternshipType.CSSI,
                                department_id=world.departments["ICT"].id,
                                end_date=(NOW + dt.timedelta(days=10)).date())
    db.add(program)
    db.flush()
    db.add(InternshipEnrollment(program_id=program.id, student_id=world.student_a.student.id))
    db.flush()
    # Read back from the database, as a real request does — not the objects
    # still holding the zone they were created with.
    db.expire_all()

    def fetch():
        response = api.get("/api/v1/calendar", headers=login(world.student_a.email))
        assert response.status_code == 200, response.text
        return response.json()

    return fetch


def test_a_student_with_an_internship_gets_their_calendar(feed):
    """Regression: the event (no zone, from SQLite) and the deadline (UTC) could
    not be compared, so every student with an internship got a 500."""
    assert [item["title"] for item in feed()] == ["Orientation", "CSSI — final submission"]


def test_every_calendar_time_carries_its_timezone(feed):
    """A time without an offset is read by the browser as local time — five and
    a half hours off in India."""
    for item in feed():
        assert dt.datetime.fromisoformat(item["start_at"]).tzinfo is not None, item
