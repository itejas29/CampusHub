"""Limits hold when requests arrive at the same instant (PostgreSQL only).

Each limit below is checked, then written. Under simultaneous requests, before
the row locks in app/db/locking.py, every one of them was exceeded on
PostgreSQL (reports/qa/tools reproduces them against a running server):

* a Minor with 3 free seats took 10 students, and its seat counter lost 9 updates;
* an event with 5 places confirmed 7–9 students;
* a mentor capped at 10 ended with 13–15.

SQLite serialises every write, so these only mean something on PostgreSQL:
    CAMPUSHUB_TEST_DATABASE_URL=postgresql://… pytest app/tests/test_pg_concurrency.py
Data here is committed for real (concurrent requests need separate
transactions) and every table is emptied afterwards.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("CAMPUSHUB_TEST_DATABASE_URL"),
                                reason="needs PostgreSQL (CAMPUSHUB_TEST_DATABASE_URL)")

NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def committed(_pg_engine):
    """A session whose commits are real, a client whose requests each get their
    own session (as in production), and an empty database afterwards."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app

    factory = sessionmaker(bind=_pg_engine, expire_on_commit=False)

    def per_request():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = per_request
    session = factory()
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with _pg_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def _people(db, n, role):
    from app.core.security import create_access_token, hash_password
    from app.models.identity import User, UserRole

    users = []
    for i in range(n):
        user = User(email=f"{role.value.lower()}{i}@race.example.org", full_name=f"Race {role.value} {i}",
                    hashed_password=hash_password("unused-password-1"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role=role))
        users.append(user)
    db.flush()
    return users, [{"Authorization": f"Bearer {create_access_token(u.id, [role.value])}"} for u in users]


def _campus(db):
    from app.models.academics import Program
    from app.models.identity import Department

    ict = Department(code="ICT", name="ICT", school="SoT")
    cse = Department(code="CSE", name="CSE", school="SoT")
    db.add_all([ict, cse])
    db.flush()
    program = Program(code="B.TECH-CE", name="B.Tech CE", department_id=cse.id)
    db.add(program)
    db.flush()
    return ict, cse, program


def _students(db, users, department, program, semester):
    from app.models.enums import StudentStatus
    from app.models.identity import Student

    rows = [Student(user_id=u.id, roll_number=f"25BCE{100 + i}", program_id=program.id,
                    department_id=department.id, admission_year=2025, current_semester=semester,
                    division="A", cpi=8.5, backlog_count=0, status=StudentStatus.ACTIVE)
            for i, u in enumerate(users)]
    db.add_all(rows)
    db.flush()
    return rows


async def _at_once(calls):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=__import__("app.main").main.app),
                                 base_url="http://test") as client:
        return await asyncio.gather(*(call(client) for call in calls))


def test_a_minor_never_takes_more_students_than_its_seats(committed):
    from app.models.enums import MinorApplicationStatus, Role
    from app.models.minors import MinorApplication, MinorEnrollment, MinorProgram

    db = committed
    ict, cse, program = _campus(db)
    users, _ = _people(db, 10, Role.STUDENT)
    students = _students(db, users, cse, program, 3)
    _admins, (registrar,) = _people(db, 1, Role.SUPER_ADMIN)
    minor = MinorProgram(code="MIN-R", name="Race Minor", department_id=ict.id, capacity=3,
                         seats_filled=0, eligible_from_semester=3, min_cpi=7.5, max_backlogs=0)
    db.add(minor)
    db.flush()
    apps = [MinorApplication(student_id=s.id, minor_program_id=minor.id, preference_order=1,
                             status=MinorApplicationStatus.SUBMITTED, semester_at_application=3,
                             submitted_at=NOW) for s in students]
    db.add_all(apps)
    db.commit()

    responses = asyncio.run(_at_once([
        (lambda c, a=a: c.post(f"/api/v1/minors/applications/{a.id}/decide", headers=registrar,
                               json={"status": "ALLOCATED"})) for a in apps]))

    assert sorted(r.status_code for r in responses) == [200] * 3 + [409] * 7
    db.expire_all()
    enrolled = db.query(MinorEnrollment).filter_by(minor_program_id=minor.id).count()
    assert enrolled == 3 and db.get(MinorProgram, minor.id).seats_filled == 3


def test_an_event_never_confirms_more_students_than_its_places(committed):
    from app.models.community import Event, EventRegistration
    from app.models.enums import EventStatus, RegistrationStatus, Role

    db = committed
    _ict, cse, program = _campus(db)
    users, heads = _people(db, 20, Role.STUDENT)
    _students(db, users, cse, program, 4)
    event = Event(title="Race Workshop", slug="race-workshop", event_type="WORKSHOP",
                  start_at=NOW + dt.timedelta(days=5), end_at=NOW + dt.timedelta(days=5, hours=2),
                  registration_required=True, capacity=5, status=EventStatus.PUBLISHED)
    db.add(event)
    db.commit()

    responses = asyncio.run(_at_once([
        (lambda c, h=h: c.post(f"/api/v1/events/{event.id}/register", headers=h, json={})) for h in heads]))

    assert all(r.status_code == 200 for r in responses)
    db.expire_all()
    confirmed = db.query(EventRegistration).filter_by(event_id=event.id,
                                                      status=RegistrationStatus.REGISTERED).count()
    waitlisted = db.query(EventRegistration).filter_by(event_id=event.id,
                                                       status=RegistrationStatus.WAITLISTED).count()
    assert (confirmed, waitlisted) == (5, 15)
