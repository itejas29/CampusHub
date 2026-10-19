"""Test fixtures. The suite is deliberately database-free: it exercises the
pure logic (security, RBAC, eligibility, allocation) that carries the rules."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest


@pytest.fixture
def student():
    """A Semester VI ICT student, matching the seeded demo data."""
    return SimpleNamespace(
        id=1, user_id=1, roll_number="22BIT001", program_id=1, department_id=1,
        admission_year=2022, current_semester=6, division="A", cpi=8.42,
        backlog_count=0,
    )


@pytest.fixture
def component_factory():
    def make(*, semester_number=6, source_scope="ANY", code="OE3",
             title="Open Elective 3"):
        from app.models.enums import SourceScope

        return SimpleNamespace(
            id=1, code=code, title=title, semester_number=semester_number,
            source_scope=SourceScope(source_scope), credits=3,
        )

    return make


@pytest.fixture
def now():
    return dt.datetime.now(dt.timezone.utc)


# ── database-backed fixtures ───────────────────────────────────────────────
# Most of this suite is deliberately database-free. Curriculum *resolution*,
# though, is a question about rows — which version governs which batch, and
# whether one programme's structure can leak into another's — so it needs a real
# session. SQLite in memory keeps it fast and dependency-free.
#
# Production runs PostgreSQL, so the same suite can run there too:
#     CAMPUSHUB_TEST_DATABASE_URL=postgresql://user:pass@host:port/db pytest
# The schema is built once; each test runs in a transaction that is rolled back,
# the app's own commits becoming savepoints inside it. Use a database that holds
# nothing else — it is dropped and rebuilt.
_PG_URL = __import__("os").environ.get("CAMPUSHUB_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def _pg_engine():
    from sqlalchemy import create_engine

    import app.models  # noqa: F401  (registers every mapper)
    from app.core.config import Settings
    from app.db.base import Base

    url = Settings(DATABASE_URL=_PG_URL).sqlalchemy_url
    engine = create_engine(url, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(request):
    if _PG_URL:
        from sqlalchemy.orm import Session

        engine = request.getfixturevalue("_pg_engine")
        connection = engine.connect()
        outer = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint",
                          expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
            connection.close()
        return

    from sqlalchemy import create_engine

    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401  (registers every mapper)
    from app.db.base import Base

    # TestClient serves requests on a worker thread, so the in-memory database
    # has to be one shared connection rather than one per thread — otherwise the
    # app thread opens a second, empty database and every lookup misses.
    engine = create_engine(
        "sqlite://", future=True, poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def academic_world(db):
    """Departments and programmes shaped like the verified PDEU structure.

    Deliberately spans both engineering schools, because the official Open
    Elective rule is written in schools, not departments.
    """
    from app.models.academics import Program
    from app.models.identity import Department

    departments, programs = {}, {}
    for code, name, school in [
        ("ICT", "Information and Communication Technology", "SoT"),
        ("CSE", "Computer Science and Engineering", "SoT"),
        ("ECE", "Electronics and Communication Engineering", "SoT"),
        ("MEC", "Mechanical Engineering", "SoT"),
        ("EE", "Electrical Engineering", "SoET"),
        ("SLS", "School of Liberal Studies", "SLS"),
    ]:
        department = Department(code=code, name=name, school=school)
        db.add(department)
        db.flush()
        departments[code] = department

    for code, name, dept in [
        ("B.TECH-ICT", "B.Tech. Information and Communication Technology", "ICT"),
        ("B.TECH-CE", "B.Tech. Computer Engineering", "CSE"),
        ("B.TECH-ECE", "B.Tech. Electronics and Communications Engineering", "ECE"),
        ("B.TECH-MECH", "B.Tech. Mechanical Engineering", "MEC"),
        ("B.TECH-ELEC", "B.Tech. Electrical Engineering", "EE"),
    ]:
        program = Program(code=code, name=name, department_id=departments[dept].id)
        db.add(program)
        db.flush()
        programs[code] = program

    db.flush()
    return SimpleNamespace(db=db, departments=departments, programs=programs)


@pytest.fixture
def make_student(academic_world):
    """A student on a given programme and batch, with no curriculum assumed."""
    from app.models.enums import Role
    from app.models.identity import Student, User

    counter = {"n": 0}

    def make(program_code, admission_year, semester=4, division="A", cpi=8.0,
             backlogs=0):
        counter["n"] += 1
        n = counter["n"]
        program = academic_world.programs[program_code]
        user = User(email=f"student{n}@example.com", hashed_password="x",
                    full_name=f"Student {n}")
        academic_world.db.add(user)
        academic_world.db.flush()
        student = Student(
            user_id=user.id, roll_number=f"ROLL{n:04d}", program_id=program.id,
            department_id=program.department_id, admission_year=admission_year,
            current_semester=semester, division=division, cpi=cpi,
            backlog_count=backlogs,
        )
        academic_world.db.add(student)
        academic_world.db.flush()
        return student

    return make


@pytest.fixture
def make_curriculum(academic_world):
    """A published (by default) curriculum version with a bounded batch window."""
    from app.models.academics import Curriculum, CurriculumComponent
    from app.models.enums import ComponentType, CurriculumStatus, SourceScope

    def make(program_code, version, from_year, to_year=None, components=(),
             status=CurriculumStatus.PUBLISHED):
        curriculum = Curriculum(
            program_id=academic_world.programs[program_code].id,
            name=f"{program_code} {version}", version=version,
            effective_from_year=from_year, effective_to_year=to_year,
            status=status, is_active=True,
        )
        academic_world.db.add(curriculum)
        academic_world.db.flush()
        for sem, code, title, ctype, scope in components:
            academic_world.db.add(CurriculumComponent(
                curriculum_id=curriculum.id, semester_number=sem, code=code,
                title=title, component_type=ComponentType(ctype),
                source_scope=SourceScope(scope), credits=3, sequence=1,
                is_elective=ctype != "CORE",
            ))
        academic_world.db.flush()
        return curriculum

    return make


# ── API-level fixtures ─────────────────────────────────────────────────────
# The scope rules are only really proved end to end: a coordinator who can reach
# one department's data through the HTTP surface but not another's. These build
# a small but complete world and drive it through a real client.
@pytest.fixture
def api(db):
    """A TestClient bound to the in-memory database."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def world(db, academic_world):
    """People with the roles and scoped grants the RBAC rules talk about.

    Deliberately includes two coordinators of *different* modules in the *same*
    department, and the same module in two departments, because those are the
    pairs that a naive permission check collapses together.
    """
    import datetime as dt
    from types import SimpleNamespace

    from app.core.security import hash_password
    from app.models.enums import (
        AssignedRole, CoordinationDomain, Role, StudentStatus,
    )
    from app.models.identity import (
        Faculty, FacultyRoleAssignment, Student, User, UserRole,
    )

    password = "Test@12345"
    hashed = hash_password(password)

    def user(name, email, *roles):
        row = User(email=email, hashed_password=hashed, full_name=name)
        db.add(row)
        db.flush()
        for role in roles:
            db.add(UserRole(user_id=row.id, role=role))
        db.flush()
        return row

    def faculty(name, email, dept, code, *grants):
        account = user(name, email, Role.FACULTY)
        row = Faculty(user_id=account.id, employee_code=code,
                      department_id=academic_world.departments[dept].id,
                      designation="Assistant Professor")
        db.add(row)
        db.flush()
        for role, domain, scope_dept in grants:
            db.add(FacultyRoleAssignment(
                faculty_id=row.id, role=role, domain=domain,
                department_id=(academic_world.departments[scope_dept].id
                               if scope_dept else None),
                is_active=True, assigned_at=dt.datetime.now(dt.timezone.utc)))
        db.flush()
        return SimpleNamespace(user=account, faculty=row, email=email)

    def student(name, email, program, dept, roll, semester=4, division="A"):
        account = user(name, email, Role.STUDENT)
        row = Student(
            user_id=account.id, roll_number=roll,
            program_id=academic_world.programs[program].id,
            department_id=academic_world.departments[dept].id,
            admission_year=2024, current_semester=semester, division=division,
            cpi=8.0, backlog_count=0, status=StudentStatus.ACTIVE)
        db.add(row)
        db.flush()
        return SimpleNamespace(user=account, student=row, email=email)

    admin = user("Super Admin", "admin@test.example.com", Role.SUPER_ADMIN)

    return SimpleNamespace(
        db=db, password=password, departments=academic_world.departments,
        programs=academic_world.programs, admin=admin,
        # Summer Internship coordinator for ICT — and nothing else.
        summer_ict=faculty(
            "Summer ICT", "summer.ict@test.example.com", "ICT", "F-SI-ICT",
            (AssignedRole.COORDINATOR, CoordinationDomain.SUMMER_INTERNSHIP, "ICT")),
        # CSSI coordinator for ICT — a different module, same department.
        cssi_ict=faculty(
            "CSSI ICT", "cssi.ict@test.example.com", "ICT", "F-CSSI-ICT",
            (AssignedRole.COORDINATOR, CoordinationDomain.CSSI, "ICT")),
        # The same module as summer_ict, but a different department.
        summer_cse=faculty(
            "Summer CSE", "summer.cse@test.example.com", "CSE", "F-SI-CSE",
            (AssignedRole.COORDINATOR, CoordinationDomain.SUMMER_INTERNSHIP, "CSE")),
        # A mentor, not a coordinator. Mentoring never implies coordinating.
        mentor_ict=faculty(
            "Mentor ICT", "mentor.ict@test.example.com", "ICT", "F-M-ICT",
            (AssignedRole.MENTOR, CoordinationDomain.CSSI, "ICT")),
        # Plain faculty: no grants at all.
        plain=faculty("Plain Faculty", "plain@test.example.com", "ICT", "F-PLAIN"),
        student_a=student("Student A", "a@test.example.com", "B.TECH-ICT", "ICT",
                          "24BIT900"),
        student_b=student("Student B", "b@test.example.com", "B.TECH-ICT", "ICT",
                          "24BIT901"),
    )


@pytest.fixture
def login(api, world):
    """Sign in and return the auth header for a seeded account."""
    def _login(email):
        response = api.post("/api/v1/auth/login",
                            json={"email": email, "password": world.password})
        assert response.status_code == 200, response.text
        token = response.json()["tokens"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _login
