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


# ── what a caller may ask for ──────────────────────────────────────────────
# The portal always sends an ISO time with its zone, but the endpoint is open to
# anyone with a token, and a bad request must be refused, never crash.
def _ask(api, world, login, query):
    return api.get(f"/api/v1/calendar?{query}", headers=login(world.student_a.email))


def test_a_range_without_a_timezone_is_read_as_utc_not_a_crash(feed, api, world, login):
    """Regression (audit finding 3): a naive start was compared with the aware
    internship deadline and the request failed with a 500."""
    response = _ask(api, world, login, "start=2026-01-01T00:00:00&end=2099-01-01T00:00:00")
    # The range is also too long, so it is refused — what matters is that it is
    # a clean 4xx, and a sane naive range works:
    assert response.status_code == 422
    start = (NOW - dt.timedelta(days=1)).replace(tzinfo=None).isoformat()
    end = (NOW + dt.timedelta(days=30)).replace(tzinfo=None).isoformat()
    ok = _ask(api, world, login, f"start={start}&end={end}")
    assert ok.status_code == 200, ok.text
    assert [i["title"] for i in ok.json()] == ["Orientation", "CSSI — final submission"]


def test_a_range_longer_than_a_year_and_a_bit_is_refused(feed, api, world, login):
    """Audit finding 4: a 100-year range was accepted and would scan every row."""
    response = _ask(api, world, login,
                    "start=1990-01-01T00:00:00Z&end=2090-01-01T00:00:00Z")
    assert response.status_code == 422
    assert "400 days" in response.json()["error"]["message"]


def test_the_portals_own_ranges_are_accepted(feed, api, world, login):
    """The month grid and the dashboard's 60-day look-ahead must keep working."""
    start = (NOW - dt.timedelta(days=40)).isoformat().replace("+00:00", "Z")
    end = (NOW + dt.timedelta(days=65)).isoformat().replace("+00:00", "Z")
    assert _ask(api, world, login, f"start={start}&end={end}").status_code == 200
    assert api.get("/api/v1/calendar",
                   headers=login(world.student_a.email)).status_code == 200


def test_an_end_before_the_start_is_refused(feed, api, world, login):
    response = _ask(api, world, login,
                    "start=2026-12-01T00:00:00Z&end=2026-01-01T00:00:00Z")
    assert response.status_code == 422
