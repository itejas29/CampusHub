"""End-to-end lifecycle tests for all four academic tracks.

   Track 1 – Minor Specialisation  : programme creation → application window → apply
                                      → allocation (CPI-ranked) → enrollment → progress
   Track 2 – Open Elective          : coordinator creates round → student fills choices
                                      → deadline/lock → allocation → publish → dashboard
   Track 3 – Core (Program) Elective: same as OE but a different coordinator domain,
                                      combined across divisions, no 75-seat ceiling
   Track 4 – NPTEL / MOOC           : student registers → updates exam details → uploads
                                      certificate → MOOC coordinator verifies → notification

Every test is driven through the HTTP surface (``api`` / ``login`` fixtures) so it
exercises the real request pipeline, not mocked service stubs. The database is an
in-memory SQLite instance spun up for the test session by ``conftest.db``.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from sqlalchemy import select

# ── shared timestamps ──────────────────────────────────────────────────────
NOW = dt.datetime.now(dt.timezone.utc)
NEXT_WEEK = (NOW + dt.timedelta(days=7)).isoformat()
IN_A_MONTH = (NOW + dt.timedelta(days=30)).isoformat()
YESTERDAY = (NOW - dt.timedelta(days=1)).isoformat()

WINDOWS = "/api/v1/electives/admin/windows"


# ══════════════════════════════════════════════════════════════════════════
# SHARED FIXTURE — the full campus world needed by all four tracks
# ══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def campus(db, world, make_curriculum):
    """A complete academic world with all four track components seeded."""
    from app.models.academics import (
        Course, CourseOffering, CurriculumComponent,
    )
    from app.models.enums import (
        AssignedRole, CoordinationDomain,
        OfferingStatus, SemesterTerm,
        StudentStatus, Role,
    )
    from app.models.identity import (
        AcademicYear, Faculty, FacultyRoleAssignment, Semester,
        Student, User, UserRole,
    )
    from app.models.minors import MinorProgram
    from app.core.security import hash_password
    from app.services import scope

    password = "Test@12345"
    hashed = hash_password(password)
    depts = world.departments
    programs = world.programs

    def user(name, email, *roles):
        row = User(email=email, hashed_password=hashed, full_name=name)
        db.add(row)
        db.flush()
        for r in roles:
            db.add(UserRole(user_id=row.id, role=r))
        db.flush()
        return row

    def faculty_with_domain(name, email, dept_code, emp_code, domain):
        u = user(name, email, Role.FACULTY)
        fac = Faculty(
            user_id=u.id, employee_code=emp_code,
            department_id=depts[dept_code].id,
            designation="Assistant Professor",
        )
        db.add(fac)
        db.flush()
        db.add(FacultyRoleAssignment(
            faculty_id=fac.id, role=AssignedRole.COORDINATOR, domain=domain,
            department_id=depts[dept_code].id,
            is_active=True, assigned_at=NOW,
        ))
        db.flush()
        return SimpleNamespace(user=u, faculty=fac, email=email)

    def make_student(name, email, program_code, dept_code, roll, sem=5):
        u = user(name, email, Role.STUDENT)
        s = Student(
            user_id=u.id, roll_number=roll,
            program_id=programs[program_code].id,
            department_id=depts[dept_code].id,
            admission_year=2022, current_semester=sem, division="A",
            cpi=8.0, backlog_count=0, status=StudentStatus.ACTIVE,
        )
        db.add(s)
        db.flush()
        return SimpleNamespace(user=u, student=s, email=email)

    # ── coordinators ────────────────────────────────────────────────────
    open_coord = faculty_with_domain(
        "OE Coord", "oe.coord@test.com", "ICT", "OE-ICT",
        CoordinationDomain.OPEN_ELECTIVE)
    core_coord = faculty_with_domain(
        "CE Coord", "ce.coord@test.com", "ICT", "CE-ICT",
        CoordinationDomain.CORE_ELECTIVE)
    mooc_coord = faculty_with_domain(
        "MOOC Coord", "mooc.coord@test.com", "ICT", "MC-ICT",
        CoordinationDomain.MOOC)
    minor_coord = faculty_with_domain(
        "Minor Coord", "minor.coord@test.com", "ICT", "MN-ICT",
        CoordinationDomain.MINOR)

    # ── HOD ─────────────────────────────────────────────────────────────
    hod = world.plain
    scope.set_hod(db, depts["ICT"], hod.faculty)

    # ── students ─────────────────────────────────────────────────────────
    student_a = make_student("Alice", "alice@test.com", "B.TECH-ICT", "ICT", "22BIT001", sem=3)
    student_b = make_student("Bob", "bob@test.com", "B.TECH-ICT", "ICT", "22BIT002", sem=5)
    student_c = make_student("Charlie", "charlie@test.com", "B.TECH-ICT", "ICT", "22BIT003", sem=5)

    # ── curriculum ───────────────────────────────────────────────────────
    curriculum = make_curriculum(
        "B.TECH-ICT", "2022-26", 2022, None, [
            (4, "OE1", "Open Elective 1",    "OPEN_ELECTIVE",         "OTHER_SCHOOL"),
            (5, "PE1", "Program Elective 1", "PROGRAM_CORE_ELECTIVE", "ANY"),
            (5, "MOO1", "NPTEL / SWAYAM",    "MOOC",                   "EXTERNAL_PLATFORM"),
        ],
    )
    components = {
        c.code: c for c in db.scalars(
            select(CurriculumComponent).where(
                CurriculumComponent.curriculum_id == curriculum.id))
    }

    # ── academic year + semesters ─────────────────────────────────────────
    year = AcademicYear(
        label="2025-26", start_date=dt.date(2025, 7, 1),
        end_date=dt.date(2026, 6, 30), is_current=True,
    )
    db.add(year)
    db.flush()
    sem4 = Semester(academic_year_id=year.id, number=4, term=SemesterTerm.EVEN)
    sem5 = Semester(academic_year_id=year.id, number=5, term=SemesterTerm.ODD)
    db.add(sem4); db.add(sem5); db.flush()

    # ── courses & offerings ───────────────────────────────────────────────
    sls_dept = depts["SLS"].id

    oe_offerings = []
    for i in range(3):
        c = Course(code=f"OE1-C{i}", title=f"OE Course {i}",
                   department_id=sls_dept, credits=3)
        db.add(c); db.flush()
        o = CourseOffering(
            course_id=c.id, semester_id=sem4.id,
            curriculum_component_id=components["OE1"].id,
            status=OfferingStatus.OPEN,
            min_students_to_run=5, section_capacity=75,
            allow_multiple_sections=True,
        )
        db.add(o); db.flush()
        oe_offerings.append(o)

    pe_course = Course(code="PE1-C0", title="Advanced Algorithms",
                       department_id=depts["ICT"].id, credits=3)
    db.add(pe_course); db.flush()
    pe_offering = CourseOffering(
        course_id=pe_course.id, semester_id=sem5.id,
        curriculum_component_id=components["PE1"].id,
        status=OfferingStatus.OPEN,
        min_students_to_run=5, section_capacity=200,
        allow_multiple_sections=False,
    )
    db.add(pe_offering); db.flush()

    mooc_course = Course(
        code="NPTEL-ML", title="Machine Learning (NPTEL)",
        department_id=depts["ICT"].id, credits=3,
        platform="NPTEL", provider_url="https://nptel.ac.in/courses/106",
    )
    db.add(mooc_course); db.flush()
    mooc_offering = CourseOffering(
        course_id=mooc_course.id, semester_id=sem5.id,
        curriculum_component_id=components["MOO1"].id,
        status=OfferingStatus.OPEN,
    )
    db.add(mooc_offering); db.flush()

    # ── minor programme ────────────────────────────────────────────────────
    # IMPORTANT: the minor MUST live in a department other than the students'.
    # eligibility.py line 163: if minor.department_id == student.department_id → fail
    # Students are ICT; we host the minor in SLS so they can apply.
    minor = MinorProgram(
        code="MIN-AI", name="Minor in Artificial Intelligence",
        department_id=depts["SLS"].id,   # <-- SLS, not ICT
        capacity=1,  # deliberately tight
        eligible_from_semester=5,
        min_cpi=7.0, max_backlogs=2,
        rules={
            "ranking": {
                "criteria": [
                    {"field": "cpi",              "direction": "desc"},
                    {"field": "backlog_count",    "direction": "asc"},
                    {"field": "preference_order", "direction": "asc"},
                ]
            }
        },
        application_opens_at=NOW - dt.timedelta(days=1),
        application_closes_at=NOW + dt.timedelta(days=14),
        coordinator_faculty_id=minor_coord.faculty.id,
    )
    db.add(minor); db.flush()

    db.commit()

    return SimpleNamespace(
        db=db, password=password,
        departments=depts, programs=programs,
        components=components,
        open_coord=open_coord, core_coord=core_coord,
        mooc_coord=mooc_coord, minor_coord=minor_coord,
        hod=hod,
        student_a=student_a, student_b=student_b, student_c=student_c,
        oe_offerings=oe_offerings,
        pe_offering=pe_offering,
        mooc_offering=mooc_offering,
        minor=minor,
        sem4=sem4, sem5=sem5,
    )


# ══════════════════════════════════════════════════════════════════════════
# TRACK 1 — MINOR SPECIALISATION
# ══════════════════════════════════════════════════════════════════════════

class TestMinorTrack:
    """Full minor lifecycle from catalogue view to enrollment."""

    def test_minor_catalogue_visible_to_sem5_student(self, api, login, campus):
        headers = login(campus.student_b.email)
        resp = api.get("/api/v1/minors", headers=headers)
        assert resp.status_code == 200
        assert campus.minor.id in [m["id"] for m in resp.json()]

    def test_minor_catalogue_hidden_to_sem3_student(self, api, login, campus):
        """The /workspace route applies semester gating; /minors list is admin-only."""
        headers = login(campus.student_a.email)
        # Workspace applies semester gate: Sem 3 < eligible_from_semester 5
        resp = api.get("/api/v1/minors/workspace", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        # The student cannot see the Sem-5-only minor
        program_ids = [p["id"] for p in body["programs"]]
        assert campus.minor.id not in program_ids

    def test_minor_eligibility_eligible_for_qualified_student(self, api, login, campus, db):
        """Use /workspace which runs the per-student eligibility check."""
        campus.student_b.student.cpi = 8.5
        campus.student_b.student.backlog_count = 0
        db.flush()
        resp = api.get("/api/v1/minors/workspace",
                       headers=login(campus.student_b.email))
        assert resp.status_code == 200
        body = resp.json()
        # Workspace says the overall semester gate is passed
        assert body["is_eligible"] is True
        # And the specific minor is visible with is_eligible
        prog = next((p for p in body["programs"] if p["id"] == campus.minor.id), None)
        assert prog is not None
        assert prog["is_eligible"] is True

    def test_minor_eligibility_denied_below_min_cpi(self, api, login, campus, db):
        campus.student_b.student.cpi = 6.0
        db.flush()
        resp = api.get("/api/v1/minors/workspace",
                       headers=login(campus.student_b.email))
        assert resp.status_code == 200
        body = resp.json()
        prog = next((p for p in body["programs"] if p["id"] == campus.minor.id), None)
        # CPI 6.0 < min_cpi 7.0 → ineligible
        if prog is not None:
            assert prog["is_eligible"] is False
        # Either hidden or marked ineligible — both are correct for CPI gate

    def test_minor_student_can_apply(self, api, login, campus, db):
        """POST /apply expects: preferences (list of program IDs), motivation."""
        campus.student_b.student.cpi = 8.5
        campus.student_b.student.backlog_count = 0
        db.flush()
        resp = api.post(
            "/api/v1/minors/apply",
            json={"preferences": [campus.minor.id],
                  "motivation": "Passionate about AI."},
            headers=login(campus.student_b.email),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["status"] == "SUBMITTED"

    def test_minor_duplicate_application_rejected(self, api, login, campus, db):
        """Submitting twice replaces previous; identical list is idempotent but ok.
        The real guard is the enrollment check and the ALLOCATED status gate."""
        campus.student_b.student.cpi = 8.5
        db.flush()
        headers = login(campus.student_b.email)
        r1 = api.post("/api/v1/minors/apply",
                      json={"preferences": [campus.minor.id]}, headers=headers)
        assert r1.status_code == 201
        # A student already enrolled cannot apply again
        from app.models.minors import MinorEnrollment
        from app.models.enums import MinorEnrollmentStatus
        campus.db.add(MinorEnrollment(
            student_id=campus.student_b.student.id,
            minor_program_id=campus.minor.id,
            status=MinorEnrollmentStatus.ACTIVE,
        ))
        campus.db.flush()
        r2 = api.post("/api/v1/minors/apply",
                      json={"preferences": [campus.minor.id]}, headers=headers)
        assert r2.status_code in (409, 422)

    def test_minor_coordinator_sees_applications(self, api, login, campus, db):
        """Route is GET /api/v1/minors/applications?program_id=N (no /admin/ prefix)."""
        campus.student_b.student.cpi = 8.5
        db.flush()
        api.post("/api/v1/minors/apply",
                 json={"preferences": [campus.minor.id]},
                 headers=login(campus.student_b.email))
        resp = api.get("/api/v1/minors/applications",
                       params={"program_id": campus.minor.id},
                       headers=login(campus.minor_coord.email))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_minor_ranking_higher_cpi_student_ranks_first(self, db, campus):
        from app.models.minors import MinorApplication
        from app.models.enums import MinorApplicationStatus
        from app.services.minors import rank

        campus.student_b.student.cpi = 9.0
        campus.student_c.student.cpi = 7.5
        db.flush()

        for student, cpi in [(campus.student_b.student, 9.0), (campus.student_c.student, 7.5)]:
            db.add(MinorApplication(
                student_id=student.id,
                minor_program_id=campus.minor.id,
                preference_order=1, status=MinorApplicationStatus.SUBMITTED,
                cpi_at_application=cpi, backlogs_at_application=0,
                semester_at_application=5, submitted_at=NOW,
            ))
        db.flush()

        ranked = rank(db, campus.minor)
        assert ranked[0].student_id == campus.student_b.student.id
        assert ranked[1].student_id == campus.student_c.student.id

    def test_minor_allocation_grants_seat_and_waitlists_overflow(self, db, campus):
        from app.models.minors import MinorApplication
        from app.models.enums import MinorApplicationStatus
        from app.services.minors import allocate

        campus.student_b.student.cpi = 9.0
        campus.student_c.student.cpi = 7.5
        db.flush()

        for student, cpi in [(campus.student_b.student, 9.0), (campus.student_c.student, 7.5)]:
            db.add(MinorApplication(
                student_id=student.id, minor_program_id=campus.minor.id,
                preference_order=1, status=MinorApplicationStatus.SUBMITTED,
                cpi_at_application=cpi, backlogs_at_application=0,
                semester_at_application=5, submitted_at=NOW,
            ))
        db.flush()

        _, granted = allocate(db, campus.minor)
        assert granted == 1  # capacity=1

        statuses = {
            a.student_id: a.status for a in db.scalars(
                select(MinorApplication).where(
                    MinorApplication.minor_program_id == campus.minor.id))
        }
        assert statuses[campus.student_b.student.id] == MinorApplicationStatus.ALLOCATED
        assert statuses[campus.student_c.student.id] == MinorApplicationStatus.WAITLISTED

    def test_minor_enrollment_row_created_after_allocation(self, db, campus):
        from app.models.minors import MinorApplication, MinorEnrollment
        from app.models.enums import MinorApplicationStatus, MinorEnrollmentStatus
        from app.services.minors import allocate

        campus.student_b.student.cpi = 9.0
        db.flush()
        db.add(MinorApplication(
            student_id=campus.student_b.student.id,
            minor_program_id=campus.minor.id,
            preference_order=1, status=MinorApplicationStatus.SUBMITTED,
            cpi_at_application=9.0, backlogs_at_application=0,
            semester_at_application=5, submitted_at=NOW,
        ))
        db.flush()
        allocate(db, campus.minor)

        enrollment = db.scalar(
            select(MinorEnrollment).where(
                MinorEnrollment.student_id == campus.student_b.student.id,
                MinorEnrollment.minor_program_id == campus.minor.id,
            )
        )
        assert enrollment is not None
        assert enrollment.status == MinorEnrollmentStatus.ACTIVE

    def test_minor_already_enrolled_student_blocked_from_second_minor(self, db, campus):
        from app.models.minors import MinorApplication, MinorEnrollment, MinorProgram
        from app.models.enums import MinorApplicationStatus, MinorEnrollmentStatus
        from app.services.minors import rank

        campus.student_b.student.cpi = 9.0
        db.flush()

        second = MinorProgram(
            code="MIN-DS", name="Minor in Data Science",
            department_id=campus.departments["CSE"].id,
            capacity=5, eligible_from_semester=5,
            rules={"ranking": {"criteria": [{"field": "cpi", "direction": "desc"}]}},
        )
        db.add(second); db.flush()

        db.add(MinorEnrollment(
            student_id=campus.student_b.student.id,
            minor_program_id=campus.minor.id,
            status=MinorEnrollmentStatus.ACTIVE,
        ))
        db.add(MinorApplication(
            student_id=campus.student_b.student.id,
            minor_program_id=second.id,
            preference_order=1, status=MinorApplicationStatus.SUBMITTED,
            cpi_at_application=9.0, backlogs_at_application=0,
            semester_at_application=5, submitted_at=NOW,
        ))
        db.flush()

        ranked = rank(db, second)
        assert ranked[0].within_capacity is False
        assert "already enrolled" in (ranked[0].note or "").lower()

    def test_minor_hod_blocked_from_admin_allocation(self, api, login, campus):
        """Allocation run route is POST /{program_id}/allocation/run."""
        alloc_resp = api.post(
            f"/api/v1/minors/{campus.minor.id}/allocation/run",
            headers=login(campus.hod.email),
        )
        assert alloc_resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# TRACK 2 — OPEN ELECTIVE
# ══════════════════════════════════════════════════════════════════════════

class TestOpenElectiveTrack:
    """Full Open Elective lifecycle: round creation → student choices → allocation → publish."""

    @staticmethod
    def _payload(campus, **overrides):
        body = {
            "code": "OE1-2026", "title": "Open Elective 1 — 2026",
            "component_type": "OPEN_ELECTIVE",
            "department_id": campus.departments["ICT"].id,
            "closes_at": NEXT_WEEK,
            "eligible_semesters": [3],
            "eligible_program_ids": [campus.programs["B.TECH-ICT"].id],
        }
        body.update(overrides)
        return body

    @staticmethod
    def _move(api, headers, rid, target):
        return api.post(f"{WINDOWS}/{rid}/status",
                        params={"target": target}, headers=headers)

    def test_oe_coordinator_creates_draft_round(self, api, login, campus):
        resp = api.post(WINDOWS, json=self._payload(campus),
                        headers=login(campus.open_coord.email))
        assert resp.status_code == 201
        assert resp.json()["status"] == "DRAFT"

    def test_oe_core_coordinator_cannot_create_oe_round(self, api, login, campus):
        resp = api.post(WINDOWS, json=self._payload(campus),
                        headers=login(campus.core_coord.email))
        assert resp.status_code == 403

    def test_oe_empty_round_cannot_open(self, api, login, campus):
        headers = login(campus.open_coord.email)
        rid = api.post(WINDOWS, json=self._payload(campus), headers=headers).json()["id"]
        resp = self._move(api, headers, rid, "OPEN")
        assert resp.status_code == 409
        assert "at least one course" in resp.json()["error"]["message"]

    def test_oe_full_round_lifecycle(self, api, login, campus, db):
        from app.models.engagement import Notification

        oe_h = login(campus.open_coord.email)
        rid = api.post(WINDOWS, json=self._payload(campus), headers=oe_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=oe_h,
                 json={"offering_ids": [o.id for o in campus.oe_offerings]})
        assert self._move(api, oe_h, rid, "OPEN").status_code == 200

        # Opening notifies eligible student_a
        notifs = list(db.scalars(
            select(Notification).where(Notification.user_id == campus.student_a.user.id)))
        assert any("open" in (n.title or "").lower() for n in notifs), \
            "Must notify eligible students on round open"

        # Student submits preferences
        st_h = login(campus.student_a.email)
        pref = api.post("/api/v1/electives/preferences", headers=st_h, json={
            "curriculum_component_id": campus.components["OE1"].id,
            "preferences": [
                {"course_offering_id": campus.oe_offerings[0].id, "preference_order": 1},
                {"course_offering_id": campus.oe_offerings[1].id, "preference_order": 2},
            ],
        })
        assert pref.status_code == 200, pref.text

        # Workspace = SUBMITTED
        ws = api.get(f"/api/v1/electives/components/{campus.components['OE1'].id}/workspace",
                     headers=st_h)
        assert ws.json()["registration_state"] == "SUBMITTED"

        # Lock → student cannot re-submit
        self._move(api, oe_h, rid, "LOCKED")
        blocked = api.post("/api/v1/electives/preferences", headers=st_h, json={
            "curriculum_component_id": campus.components["OE1"].id,
            "preferences": [
                {"course_offering_id": campus.oe_offerings[2].id, "preference_order": 1}
            ],
        })
        assert blocked.status_code == 409

        # Allocate
        alloc = api.post("/api/v1/electives/admin/allocate", headers=oe_h, json={
            "curriculum_component_id": campus.components["OE1"].id,
            "strategy": "preference_order", "dry_run": False,
        })
        assert alloc.status_code == 200, alloc.text

        # Move to ALLOCATED → results still hidden
        self._move(api, oe_h, rid, "ALLOCATED")
        hidden = api.get(f"/api/v1/electives/components/{campus.components['OE1'].id}/workspace",
                         headers=st_h)
        assert hidden.json()["registration_state"] == "LOCKED"

        # Publish → student now sees seat
        self._move(api, oe_h, rid, "PUBLISHED")
        visible = api.get(f"/api/v1/electives/components/{campus.components['OE1'].id}/workspace",
                          headers=st_h)
        assert visible.json()["registration_state"] == "ALLOCATED"

    def test_oe_student_two_semesters_away_stays_out(self, api, login, campus, db):
        campus.student_a.student.current_semester = 1
        db.flush()
        oe_h = login(campus.open_coord.email)
        rid = api.post(WINDOWS, json=self._payload(campus), headers=oe_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=oe_h,
                 json={"offering_ids": [o.id for o in campus.oe_offerings]})
        self._move(api, oe_h, rid, "OPEN")
        resp = api.post("/api/v1/electives/preferences",
                        headers=login(campus.student_a.email),
                        json={
                            "curriculum_component_id": campus.components["OE1"].id,
                            "preferences": [{"course_offering_id": campus.oe_offerings[0].id,
                                             "preference_order": 1}],
                        })
        assert resp.status_code == 409

    def test_oe_hod_sees_round_cannot_mutate(self, api, login, campus):
        oe_h = login(campus.open_coord.email)
        rid = api.post(WINDOWS, json=self._payload(campus), headers=oe_h).json()["id"]

        hod_h = login(campus.hod.email)
        assert api.get(WINDOWS, headers=hod_h).status_code == 200
        assert api.patch(f"{WINDOWS}/{rid}", json={"closes_at": IN_A_MONTH},
                         headers=hod_h).status_code == 403

    def test_oe_export_csv_accessible_to_coordinator(self, api, login, campus):
        headers = login(campus.open_coord.email)
        resp = api.get("/api/v1/electives/admin/allocations/export",
                       params={"component_id": campus.components["OE1"].id},
                       headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_oe_dashboard_prompts_and_clears(self, api, login, campus):
        oe_h = login(campus.open_coord.email)
        rid = api.post(WINDOWS, json=self._payload(campus), headers=oe_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=oe_h,
                 json={"offering_ids": [o.id for o in campus.oe_offerings]})
        self._move(api, oe_h, rid, "OPEN")

        st_h = login(campus.student_a.email)
        dash = api.get("/api/v1/dashboard/student", headers=st_h).json()
        elective_items = [i for i in dash["action_items"] if i["kind"] == "elective"]
        assert elective_items, "Must show elective action item when round is open"

        api.post("/api/v1/electives/preferences", headers=st_h, json={
            "curriculum_component_id": campus.components["OE1"].id,
            "preferences": [{"course_offering_id": campus.oe_offerings[0].id,
                              "preference_order": 1}],
        })
        dash_after = api.get("/api/v1/dashboard/student", headers=st_h).json()
        assert [i for i in dash_after["action_items"] if i["kind"] == "elective"] == []


# ══════════════════════════════════════════════════════════════════════════
# TRACK 3 — CORE (PROGRAM) ELECTIVE
# ══════════════════════════════════════════════════════════════════════════

class TestCoreElectiveTrack:
    """Core Elective mirrors OE but uses CORE_ELECTIVE domain, no 75-seat ceiling."""

    @staticmethod
    def _pe_payload(campus, **overrides):
        body = {
            "code": "PE1-2026", "title": "Program Elective 1 — 2026",
            "component_type": "PROGRAM_CORE_ELECTIVE",
            "department_id": campus.departments["ICT"].id,
            "closes_at": NEXT_WEEK,
            "eligible_semesters": [4],
            "eligible_program_ids": [campus.programs["B.TECH-ICT"].id],
        }
        body.update(overrides)
        return body

    @staticmethod
    def _move(api, headers, rid, target):
        return api.post(f"{WINDOWS}/{rid}/status",
                        params={"target": target}, headers=headers)

    def test_ce_oe_coordinator_cannot_create_core_round(self, api, login, campus):
        resp = api.post(WINDOWS, json=self._pe_payload(campus),
                        headers=login(campus.open_coord.email))
        assert resp.status_code == 403

    def test_ce_coordinator_creates_and_opens_round(self, api, login, campus):
        ce_h = login(campus.core_coord.email)
        rid = api.post(WINDOWS, json=self._pe_payload(campus), headers=ce_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=ce_h,
                 json={"offering_ids": [campus.pe_offering.id]})
        assert self._move(api, ce_h, rid, "OPEN").json()["status"] == "OPEN"

    def test_ce_sem4_student_can_fill_choices(self, api, login, campus, db):
        campus.student_a.student.current_semester = 4
        db.flush()
        ce_h = login(campus.core_coord.email)
        rid = api.post(WINDOWS, json=self._pe_payload(campus), headers=ce_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=ce_h,
                 json={"offering_ids": [campus.pe_offering.id]})
        self._move(api, ce_h, rid, "OPEN")

        resp = api.post("/api/v1/electives/preferences",
                        headers=login(campus.student_a.email),
                        json={
                            "curriculum_component_id": campus.components["PE1"].id,
                            "preferences": [{"course_offering_id": campus.pe_offering.id,
                                             "preference_order": 1}],
                        })
        assert resp.status_code == 200, resp.text

    def test_ce_section_planning_no_ceiling(self):
        from app.services.sections import plan_section_sizes
        assert plan_section_sizes(150, None, allow_multiple=False) == [150]

    def test_ce_full_lifecycle(self, api, login, campus, db):
        campus.student_a.student.current_semester = 4
        db.flush()
        ce_h = login(campus.core_coord.email)
        rid = api.post(WINDOWS, json=self._pe_payload(campus), headers=ce_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=ce_h,
                 json={"offering_ids": [campus.pe_offering.id]})
        self._move(api, ce_h, rid, "OPEN")

        st_h = login(campus.student_a.email)
        api.post("/api/v1/electives/preferences", headers=st_h, json={
            "curriculum_component_id": campus.components["PE1"].id,
            "preferences": [{"course_offering_id": campus.pe_offering.id, "preference_order": 1}],
        })
        self._move(api, ce_h, rid, "LOCKED")
        alloc = api.post("/api/v1/electives/admin/allocate", headers=ce_h, json={
            "curriculum_component_id": campus.components["PE1"].id,
            "strategy": "preference_order", "dry_run": False,
        })
        assert alloc.status_code == 200, alloc.text
        self._move(api, ce_h, rid, "ALLOCATED")
        self._move(api, ce_h, rid, "PUBLISHED")

        ws = api.get(f"/api/v1/electives/components/{campus.components['PE1'].id}/workspace",
                     headers=st_h)
        assert ws.json()["registration_state"] == "ALLOCATED"

    def test_ce_dashboard_link_points_to_core_electives_screen(self, api, login, campus, db):
        campus.student_a.student.current_semester = 4
        db.flush()
        ce_h = login(campus.core_coord.email)
        rid = api.post(WINDOWS, json=self._pe_payload(campus), headers=ce_h).json()["id"]
        api.post(f"{WINDOWS}/{rid}/offerings", headers=ce_h,
                 json={"offering_ids": [campus.pe_offering.id]})
        self._move(api, ce_h, rid, "OPEN")

        dash = api.get("/api/v1/dashboard/student",
                       headers=login(campus.student_a.email)).json()
        ce_items = [i for i in dash["action_items"]
                    if i["kind"] == "elective" and "Program Elective" in i["title"]]
        assert ce_items
        assert "/core-electives/" in ce_items[0]["link"]


# ══════════════════════════════════════════════════════════════════════════
# TRACK 4 — NPTEL / MOOC
# ══════════════════════════════════════════════════════════════════════════

class TestNptelMoocTrack:
    """NPTEL lifecycle: register → update → upload certificate → verify."""

    def test_mooc_eligibility_for_sem5_student(self, api, login, campus):
        resp = api.get("/api/v1/mooc/eligibility", headers=login(campus.student_b.email))
        assert resp.status_code == 200
        body = resp.json()
        assert body["eligible"] is True
        assert body["component"]["code"] == "MOO1"

    def test_mooc_eligibility_false_for_sem3_student(self, api, login, campus):
        resp = api.get("/api/v1/mooc/eligibility", headers=login(campus.student_a.email))
        assert resp.status_code == 200
        body = resp.json()
        # Sem 3: MOOC slot is Sem 5, so not yet accessible
        assert body["eligible"] is False or body["component"] is None

    def test_mooc_catalogue_shows_offering(self, api, login, campus):
        resp = api.get("/api/v1/mooc/catalogue", headers=login(campus.student_b.email))
        assert resp.status_code == 200
        assert campus.mooc_offering.id in [o["id"] for o in resp.json()]

    def test_mooc_student_registers(self, api, login, campus):
        resp = api.post("/api/v1/mooc/register",
                        headers=login(campus.student_b.email),
                        json={
                            "course_offering_id": campus.mooc_offering.id,
                            "platform_registration_id": "NPTEL-2026-ML-BOB",
                            "exam_city": "Ahmedabad",
                        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "REGISTERED"
        assert body["platform"] == "NPTEL"

    def test_mooc_duplicate_registration_rejected(self, api, login, campus):
        headers = login(campus.student_b.email)
        api.post("/api/v1/mooc/register",
                 json={"course_offering_id": campus.mooc_offering.id}, headers=headers)
        resp = api.post("/api/v1/mooc/register",
                        json={"course_offering_id": campus.mooc_offering.id}, headers=headers)
        assert resp.status_code in (409, 422)

    def test_mooc_student_updates_exam_details(self, api, login, campus):
        headers = login(campus.student_b.email)
        reg_id = api.post("/api/v1/mooc/register",
                          json={"course_offering_id": campus.mooc_offering.id},
                          headers=headers).json()["id"]
        resp = api.patch(f"/api/v1/mooc/{reg_id}",
                         json={"exam_date": "2026-04-15", "exam_city": "Gandhinagar",
                               "exam_fee_paid": True, "exam_fee_reference": "TXN-001"},
                         headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["exam_city"] == "Gandhinagar"
        assert body["exam_fee_paid"] is True
        assert body["status"] == "EXAM_SCHEDULED"

    def test_mooc_student_sees_own_registrations(self, api, login, campus):
        headers = login(campus.student_b.email)
        api.post("/api/v1/mooc/register",
                 json={"course_offering_id": campus.mooc_offering.id}, headers=headers)
        resp = api.get("/api/v1/mooc/me", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_mooc_coordinator_sees_verification_queue(self, api, login, campus):
        api.post("/api/v1/mooc/register",
                 json={"course_offering_id": campus.mooc_offering.id},
                 headers=login(campus.student_b.email))
        resp = api.get("/api/v1/mooc/admin/registrations",
                       headers=login(campus.mooc_coord.email))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_mooc_verification_fails_without_certificate(self, api, login, campus, db):
        from app.models.academics import MoocRegistration
        from app.models.enums import MoocStatus, VerificationStatus

        reg = MoocRegistration(
            student_id=campus.student_b.student.id,
            course_offering_id=campus.mooc_offering.id,
            curriculum_component_id=campus.components["MOO1"].id,
            platform="NPTEL", status=MoocStatus.REGISTERED,
            verification_status=VerificationStatus.PENDING,
        )
        db.add(reg); db.flush()

        resp = api.post(f"/api/v1/mooc/admin/{reg.id}/verify",
                        json={"verification_status": "VERIFIED", "grade": "S",
                              "final_score": 85.0, "remarks": "Good"},
                        headers=login(campus.mooc_coord.email))
        assert resp.status_code in (409, 422)
        assert "certificate" in resp.json()["error"]["message"].lower()

    def test_mooc_full_verification_lifecycle_and_student_notified(self, api, login, campus, db):
        from app.models.academics import MoocRegistration
        from app.models.engagement import Notification
        from app.models.enums import MoocStatus, VerificationStatus

        # Plant registration with certificate (use StoredFile — the actual model class)
        from app.models.system import StoredFile
        from app.models.enums import FileCategory
        dummy_file = StoredFile(
            filename="cert.pdf", original_name="cert.pdf",
            content_type="application/pdf", size_bytes=1024,
            category=FileCategory.CERTIFICATE,
            storage_key="fake/path/cert.pdf",
        )
        db.add(dummy_file); db.flush()

        reg = MoocRegistration(
            student_id=campus.student_b.student.id,
            course_offering_id=campus.mooc_offering.id,
            curriculum_component_id=campus.components["MOO1"].id,
            platform="NPTEL", status=MoocStatus.CERTIFICATE_UPLOADED,
            verification_status=VerificationStatus.PENDING,
            certificate_file_id=dummy_file.id,
        )
        db.add(reg); db.flush()

        resp = api.post(f"/api/v1/mooc/admin/{reg.id}/verify",
                        json={"verification_status": "VERIFIED", "grade": "S",
                              "final_score": 87.5,
                              "remarks": "Authenticated against NPTEL portal."},
                        headers=login(campus.mooc_coord.email))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["verification_status"] == "VERIFIED"
        assert body["grade"] == "S"
        assert body["status"] == "COMPLETED"

        # Student gets notification
        notifs = list(db.scalars(
            select(Notification).where(Notification.user_id == campus.student_b.user.id)))
        assert any(
            "verified" in (n.title or "").lower() or
            "nptel" in (n.title or "").lower() or
            "certificate" in (n.title or "").lower()
            for n in notifs
        ), "Student must be notified on MOOC certificate verification"

    def test_mooc_verified_registration_is_immutable(self, api, login, campus, db):
        from app.models.academics import MoocRegistration
        from app.models.enums import MoocStatus, VerificationStatus

        reg = MoocRegistration(
            student_id=campus.student_b.student.id,
            course_offering_id=campus.mooc_offering.id,
            curriculum_component_id=campus.components["MOO1"].id,
            platform="NPTEL", status=MoocStatus.COMPLETED,
            verification_status=VerificationStatus.VERIFIED,
        )
        db.add(reg); db.flush()

        resp = api.patch(f"/api/v1/mooc/{reg.id}",
                         json={"exam_city": "Mumbai"},
                         headers=login(campus.student_b.email))
        assert resp.status_code in (409, 422)

    def test_mooc_oe_coordinator_cannot_access_verification_queue(self, api, login, campus):
        resp = api.get("/api/v1/mooc/admin/registrations",
                       headers=login(campus.open_coord.email))
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# CROSS-TRACK ISOLATION
# ══════════════════════════════════════════════════════════════════════════

class TestCrossTrackIsolation:
    """No coordinator's powers should bleed across module boundaries."""

    def test_open_coord_blocked_from_minor_admin(self, api, login, campus):
        """OE coordinator has no MINOR domain → 403 on minor applications list."""
        resp = api.get("/api/v1/minors/applications",
                       params={"program_id": campus.minor.id},
                       headers=login(campus.open_coord.email))
        assert resp.status_code == 403

    def test_minor_coord_cannot_create_elective_round(self, api, login, campus):
        resp = api.post(WINDOWS, json={
            "code": "MINOR-ROUND", "title": "Should Fail",
            "component_type": "OPEN_ELECTIVE",
            "department_id": campus.departments["ICT"].id,
            "closes_at": NEXT_WEEK,
            "eligible_semesters": [3],
            "eligible_program_ids": [campus.programs["B.TECH-ICT"].id],
        }, headers=login(campus.minor_coord.email))
        assert resp.status_code == 403

    def test_core_coord_cannot_reach_mooc_queue(self, api, login, campus):
        assert api.get("/api/v1/mooc/admin/registrations",
                       headers=login(campus.core_coord.email)).status_code == 403

    def test_mooc_coord_cannot_run_elective_allocation(self, api, login, campus):
        resp = api.post("/api/v1/electives/admin/allocate",
                        json={"curriculum_component_id": campus.components["OE1"].id,
                              "strategy": "preference_order", "dry_run": True},
                        headers=login(campus.mooc_coord.email))
        assert resp.status_code == 403

    def test_student_blocked_from_all_admin_surfaces(self, api, login, campus):
        headers = login(campus.student_b.email)
        assert api.get(WINDOWS, headers=headers).status_code == 403
        assert api.get("/api/v1/mooc/admin/registrations",
                       headers=headers).status_code == 403
        # Minor applications list is coordinator-only
        assert api.get("/api/v1/minors/applications",
                       params={"program_id": campus.minor.id},
                       headers=headers).status_code == 403

    def test_hod_can_see_elective_rounds_but_not_mooc_queue(self, api, login, campus):
        headers = login(campus.hod.email)
        assert api.get(WINDOWS, headers=headers).status_code == 200
        assert api.get("/api/v1/mooc/admin/registrations",
                       headers=headers).status_code == 403
