"""One active faculty mentor per student, in any academic year (QA-15).

The department's rule, confirmed by the project owner on 24 Oct 2026. Before:
the only guard was a unique (student_id, academic_year_id) constraint, so

* two active rows with a NULL academic year were accepted (NULLs never collide);
* assigning a mentor in a new academic year left last year's assignment active
  beside the new one — two mentors.

Now `services/mentoring.assign` retires the old assignment (kept, inactive, as
history) and a partial unique index refuses a second active row outright.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.engagement import MentorAssignment
from app.models.identity import AcademicYear
from app.services import mentoring
from app.tests.test_pg_concurrency import committed  # noqa: F401  (fixture)

NOW = dt.datetime.now(dt.timezone.utc)
ASSIGN = "/api/v1/mentorship/assignments"


@pytest.fixture
def years(db):
    last = AcademicYear(label="2025-26", start_date=dt.date(2025, 7, 1),
                        end_date=dt.date(2026, 6, 30), is_current=False)
    this = AcademicYear(label="2026-27", start_date=dt.date(2026, 7, 1),
                        end_date=dt.date(2027, 6, 30), is_current=True)
    db.add_all([last, this])
    db.flush()
    return type("Years", (), {"last": last, "this": this})


def active(db, student):
    return list(db.scalars(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id, MentorAssignment.is_active.is_(True))))


def row(db, student, faculty, year=None, is_active=True, days_ago=10):
    a = MentorAssignment(student_id=student.id, faculty_id=faculty.id,
                         academic_year_id=year.id if year else None, is_active=is_active,
                         assigned_at=NOW - dt.timedelta(days=days_ago))
    db.add(a)
    db.flush()
    return a


def assign(api, login, world, student, faculty):
    return api.post(ASSIGN, headers=login(world.admin.email),
                    params={"student_id": student.id, "faculty_id": faculty.id})


# ── the rule through the API ───────────────────────────────────────────────
def test_reassigning_in_the_same_year_keeps_one_active_mentor(api, login, db, world, years):
    s = world.student_a.student
    assert assign(api, login, world, s, world.mentor_ict.faculty).status_code == 200
    assert assign(api, login, world, s, world.plain.faculty).status_code == 200
    rows = active(db, s)
    assert [r.faculty_id for r in rows] == [world.plain.faculty.id]


def test_a_new_academic_year_retires_last_years_mentor(api, login, db, world, years):
    s = world.student_a.student
    old = row(db, s, world.mentor_ict.faculty, years.last)
    assert assign(api, login, world, s, world.plain.faculty).status_code == 200
    db.refresh(old)
    assert old.is_active is False                      # kept, as history
    rows = active(db, s)
    assert len(rows) == 1 and rows[0].faculty_id == world.plain.faculty.id
    assert rows[0].academic_year_id == years.this.id


def test_an_assignment_with_no_academic_year_is_retired_too(api, login, db, world, years):
    s = world.student_a.student
    old = row(db, s, world.mentor_ict.faculty, None)
    assert assign(api, login, world, s, world.plain.faculty).status_code == 200
    db.refresh(old)
    assert old.is_active is False and len(active(db, s)) == 1


def test_assigning_with_no_current_year_still_keeps_one(api, login, db, world):
    s = world.student_a.student
    assign(api, login, world, s, world.mentor_ict.faculty)
    assign(api, login, world, s, world.plain.faculty)
    assert [r.faculty_id for r in active(db, s)] == [world.plain.faculty.id]


def test_the_previous_mentor_is_recorded_as_an_override(api, login, db, world, years):
    from app.models.system import AuditLog
    s = world.student_a.student
    row(db, s, world.mentor_ict.faculty, years.last)
    assign(api, login, world, s, world.plain.faculty)
    entry = db.scalars(select(AuditLog).where(AuditLog.entity_type == "mentor_assignment")
                       .order_by(AuditLog.id.desc())).first()
    assert entry.action == "MENTOR_OVERRIDE"
    assert entry.meta["from_faculty_id"] == world.mentor_ict.faculty.id


def test_the_new_mentor_sees_the_student_and_the_old_one_does_not(api, login, db, world, years):
    s = world.student_a.student
    row(db, s, world.mentor_ict.faculty, years.last)
    assign(api, login, world, s, world.plain.faculty)
    old = api.get("/api/v1/mentorship/my-mentees", headers=login(world.mentor_ict.email))
    new = api.get("/api/v1/mentorship/my-mentees", headers=login(world.plain.email))
    assert s.id not in [m["student_id"] for m in old.json()]
    assert s.id in [m["student_id"] for m in new.json()]


# ── the database refuses a second active row ───────────────────────────────
@pytest.mark.parametrize("first_year, second_year", [
    (None, None), ("last", "this"), ("this", None),
])
def test_the_database_refuses_two_active_mentors(db, world, years, first_year, second_year):
    s = world.student_a.student
    row(db, s, world.mentor_ict.faculty, getattr(years, first_year) if first_year else None)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            row(db, s, world.plain.faculty,
                getattr(years, second_year) if second_year else None)


def test_inactive_history_is_unlimited(db, world, years):
    s = world.student_a.student
    row(db, s, world.mentor_ict.faculty, None, is_active=False)
    row(db, s, world.plain.faculty, None, is_active=False)
    row(db, s, world.mentor_ict.faculty, years.last, is_active=False)
    row(db, s, world.plain.faculty, years.this, is_active=True)
    assert len(active(db, s)) == 1


def test_two_students_each_keep_their_own_mentor(db, world, years):
    row(db, world.student_a.student, world.mentor_ict.faculty, years.this)
    row(db, world.student_b.student, world.mentor_ict.faculty, years.this)
    assert mentoring.duplicate_active(db) == {}


def test_the_service_retires_and_reports(db, world, years):
    s = world.student_a.student
    old = row(db, s, world.mentor_ict.faculty, years.last)
    result = mentoring.assign(db, s, world.plain.faculty, actor_user_id=None)
    assert result.previous_faculty_id == world.mentor_ict.faculty.id
    assert result.retired == [old]


# ── PostgreSQL: concurrency and the migration ──────────────────────────────
PG = os.environ.get("CAMPUSHUB_TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(not PG, reason="needs PostgreSQL (CAMPUSHUB_TEST_DATABASE_URL)")


@needs_pg
def test_simultaneous_assignments_leave_one_active_mentor(committed_for_mentors):
    import asyncio

    from app.tests.test_pg_concurrency import _at_once
    db, admin_headers, student, mentors = committed_for_mentors
    calls = [
        (lambda m: (lambda c: c.post(ASSIGN, headers=admin_headers,
                                     params={"student_id": student, "faculty_id": m})))(m)
        for m in mentors
    ]
    responses = asyncio.run(_at_once(calls))
    assert all(r.status_code in (200, 409) for r in responses), [r.text for r in responses]
    db.expire_all()
    rows = list(db.scalars(select(MentorAssignment).where(
        MentorAssignment.student_id == student, MentorAssignment.is_active.is_(True))))
    assert len(rows) == 1


@pytest.fixture
def committed_for_mentors(committed):
    from app.core.security import create_access_token, hash_password
    from app.models.enums import Role
    from app.models.identity import Faculty, User, UserRole
    from app.tests.test_pg_concurrency import _campus, _people, _students

    db = committed
    ict, _cse, program = _campus(db)
    db.add(AcademicYear(label="2026-27", start_date=dt.date(2026, 7, 1),
                        end_date=dt.date(2027, 6, 30), is_current=True))
    student_users, _ = _people(db, 1, Role.STUDENT)
    (student,) = _students(db, student_users, ict, program, 3)
    mentors = []
    for i in range(8):
        user = User(email=f"mentor{i}@race.example.org", full_name=f"Mentor {i}",
                    hashed_password=hash_password("unused-password-1"))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role=Role.FACULTY))
        faculty = Faculty(user_id=user.id, employee_code=f"RACE-M{i}",
                          department_id=ict.id, designation="Assistant Professor")
        db.add(faculty)
        db.flush()
        mentors.append(faculty.id)
    admin = User(email="admin@race.example.org", full_name="Race Admin",
                 hashed_password=hash_password("unused-password-1"))
    db.add(admin)
    db.flush()
    db.add(UserRole(user_id=admin.id, role=Role.SUPER_ADMIN))
    db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(admin.id, ['SUPER_ADMIN'])}"}
    return db, headers, student.id, mentors


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    backend = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env,
                          capture_output=True, text=True, timeout=600)


@needs_pg
def test_the_migration_keeps_the_newest_and_audits_the_rest():
    """From an empty database to 0018, plant duplicates, then upgrade to 0019."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    from app.core.config import Settings
    base = make_url(Settings(DATABASE_URL=PG).sqlalchemy_url)
    scratch = base.set(database=f"{base.database}_migrate")
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{scratch.database}"'))
        c.execute(text(f'CREATE DATABASE "{scratch.database}"'))
    url = scratch.render_as_string(hide_password=False)
    try:
        first = _alembic(url, "upgrade", "0018_account_security")
        assert first.returncode == 0, first.stderr[-2000:]
        engine = create_engine(url)
        with engine.begin() as c:
            # Rows only: foreign keys are not what this test is about.
            c.execute(text("SET session_replication_role = replica"))
            c.execute(text(
                "INSERT INTO mentor_assignments (id, student_id, faculty_id, academic_year_id,"
                " is_active, assigned_at) VALUES"
                " (1, 7, 100, NULL, true, '2025-08-01T00:00:00Z'),"
                " (2, 7, 101, NULL, true, '2026-08-01T00:00:00Z'),"   # newest: kept
                " (3, 7, 102, 1, true, '2025-09-01T00:00:00Z'),"
                " (4, 7, 103, NULL, false, '2024-08-01T00:00:00Z'),"  # history: untouched
                " (5, 8, 104, NULL, true, NULL)"))                   # single: untouched
        second = _alembic(url, "upgrade", "head")
        assert second.returncode == 0, second.stderr[-2000:]
        with engine.connect() as c:
            state = dict(c.execute(text(
                "SELECT id, is_active FROM mentor_assignments ORDER BY id")).all())
            audits = c.execute(text(
                "SELECT entity_id FROM audit_logs WHERE actor_label = 'migration 0019' "
                "ORDER BY entity_id")).scalars().all()
            index = c.execute(text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = "
                "'uq_mentor_assignments_one_active_per_student'")).scalar_one()
        assert state == {1: False, 2: True, 3: False, 4: False, 5: True}
        assert audits == [1, 3]
        assert "WHERE is_active" in index
        down = _alembic(url, "downgrade", "0018_account_security")
        assert down.returncode == 0, down.stderr[-2000:]
        up = _alembic(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr[-2000:]
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)'))
        admin.dispose()
