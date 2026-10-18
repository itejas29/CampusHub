"""Idempotent demo seeder:  python -m app.seed.run  [--reset]

Populates a complete, coherent dataset so the portal is usable immediately:
the ICT curriculum, elective catalogues, CSSI and Summer Internship programmes
with live progress, clubs, events, mentors, notifications and audit history.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random
import secrets
import sys
import uuid
from pathlib import Path

from slugify import slugify
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.academics import (
    Course, CourseOffering, Curriculum, CurriculumComponent, ElectiveAllocation,
    ElectivePreference, ElectiveRegistrationWindow, ElectiveType, MoocRegistration,
    Program, ProgramDivision,
)
from app.models.community import (
    Club, ClubMember, Event, EventInterest, EventRegistration,
)
from app.models.engagement import (
    Announcement, MentorAssignment, MentorMeeting, Notification,
)
from app.models.enums import (
    INTERNSHIP_DOMAINS, MinorCourseResultStatus,
    AllocationStatus, CurriculumStatus, RegistrationWindowStatus,
    SourceConfidence, AnnouncementCategory, AudienceType, AuditAction, ClubCategory,
    ClubMemberRole, ComponentType, CoordinationDomain, DocumentType, EnrollmentStatus,
    EvaluationStatus, FileCategory,
    EvaluatorRole, EventMode, EventStatus, EventType, InternshipType, InternshipWindowKind,
    MeetingMode,
    AssignedRole, MeetingStatus, MinorApplicationStatus, MinorEnrollmentStatus, MoocPlatform,
    MoocStatus, NotificationType, OfferingStatus, OrganizationType, PreferenceStatus,
    Priority, ProgramStatus, RegistrationStatus, ReportFrequency, ReportType, Role,
    SemesterTerm, SourceScope, StageStatus, SubmissionStatus, VerificationStatus,
)
from app.models.identity import (
    AcademicYear, Department, Faculty, FacultyRoleAssignment, Semester, Student,
    User, UserRole,
)
from app.models.internships import (
    EnrollmentStageProgress, EvaluationCriteria, EvaluationScore, InternshipDocument,
    InternshipEnrollment, InternshipEvaluation, InternshipGroup, InternshipProgram,
    InternshipProject, InternshipReport, InternshipStage, InternshipWindow, Organization,
)
from app.models.minors import (
    MinorApplication, MinorCourse, MinorCourseResult, MinorEnrollment, MinorProgram,
)
from app.models.system import AuditLog, StoredFile
from app.storage import get_storage
from app.services import sections
from app.seed import data as D
from app.services import registration as registration_service
from app.services import scope as scope_service
from app.services import internships as internship_engine
from app.seed import curriculum_import
from app.services import curriculum as curriculum_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Cited in the seeded Minor policy so an administrator can open the rule.
MINOR_SOURCE_URL = (
    "https://api.pdeu.ac.in/pdpu/resources/btech-academic-rules-2024.pdf"
)

rng = random.Random(20250827)
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.date()
PASSWORD = settings.SEED_DEFAULT_PASSWORD
#: Every demo account shares one password, so hash it once rather than ~800
#: times (bcrypt at 12 rounds costs ~250ms per call).
_PASSWORD_HASH = hash_password(PASSWORD)



# ── demo document generation ──────────────────────────────────────────────
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


def _demo_pdf(title: str) -> bytes:
    """Smallest valid single-page PDF carrying a title line."""
    text = title.replace("(", "").replace(")", "")[:70]
    content = f"BT /F1 14 Tf 60 760 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def store_demo_file(db: Session, *, name: str, category: FileCategory,
                    uploader_id: int | None, image: bool = False) -> StoredFile:
    """Write a real file through the configured storage backend."""
    data = _PNG_1x1 if image else _demo_pdf(name)
    extension = ".png" if image else ".pdf"
    key = f"{category.value.lower()}/{uuid.uuid4().hex}{extension}"
    saved = get_storage().save(
        data, key=key, content_type="image/png" if image else "application/pdf"
    )
    record = StoredFile(
        filename=key.split("/")[-1], original_name=f"{slugify(name)}{extension}",
        content_type=saved.content_type, size_bytes=saved.size_bytes,
        storage_backend=saved.backend, storage_key=saved.key, category=category,
        uploaded_by_user_id=uploader_id,
        checksum=hashlib.sha256(data).hexdigest(),
    )
    db.add(record)
    db.flush()
    return record


def log(message: str) -> None:
    print(f"  {message}")


def reset(db: Session) -> None:
    """Rebuild the schema through Alembic so the migration path is the one tested."""
    from alembic import command
    from alembic.config import Config

    log("Rebuilding schema via Alembic (downgrade base → upgrade head)…")
    db.close()
    engine.dispose()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def already_seeded(db: Session) -> bool:
    return db.scalar(select(Department).limit(1)) is not None


# ── helpers ───────────────────────────────────────────────────────────────
def make_user(db: Session, *, name: str, email: str, roles: list[Role],
              phone: str | None = None) -> User:
    user = User(email=email.lower(), hashed_password=_PASSWORD_HASH,
                full_name=name, phone=phone, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role=role))
    return user


def make_course(db: Session, code: str, title: str, credits: float,
                department: Department | None, *, school: str | None = None,
                specialization: str | None = None,
                platform: MoocPlatform | None = None, provider_url: str | None = None,
                duration_weeks: int | None = None, description: str | None = None
                ) -> Course:
    course = Course(
        code=code, title=title, credits=credits,
        department_id=department.id if department else None,
        offering_school=school, specialization_area=specialization,
        platform=platform, provider_url=provider_url, duration_weeks=duration_weeks,
        description=description or f"{title}. Syllabus and evaluation scheme are "
                                   "published by the offering department.",
        lecture_hours=3, tutorial_hours=0, practical_hours=0,
    )
    db.add(course)
    db.flush()
    return course


def make_offering(db: Session, course: Course, semester: Semester,
                  component: CurriculumComponent, *,
                  min_students_to_run: int = 40,
                  section_capacity: int | None = None,
                  allow_multiple_sections: bool = False,
                  eligible_divisions: list[str] | None = None,
                  status: OfferingStatus = OfferingStatus.OPEN,
                  opens_days: int = -10, closes_days: int = 21,
                  coordinator: Faculty | None = None) -> CourseOffering:
    """Capacity rules differ per elective family — see services/sections.py.

    Open Elective:  section_capacity=75, allow_multiple_sections=True
    Core Elective:  section_capacity=None (no ceiling), single combined class
    """
    offering = CourseOffering(
        course_id=course.id, semester_id=semester.id,
        curriculum_component_id=component.id,
        elective_type_id=component.elective_type_id,
        min_students_to_run=min_students_to_run,
        section_capacity=section_capacity,
        allow_multiple_sections=allow_multiple_sections,
        eligible_divisions=eligible_divisions or [],
        seats_filled=0, status=status,
        registration_opens_at=NOW + dt.timedelta(days=opens_days),
        registration_closes_at=NOW + dt.timedelta(days=closes_days),
        coordinator_faculty_id=coordinator.id if coordinator else None,
        venue=f"Block {rng.randint(4, 7)}-{rng.randint(101, 220)}",
        schedule_note=rng.choice(["Mon & Wed, 10:00–11:30", "Tue & Thu, 14:00–15:30",
                                  "Wed & Fri, 09:00–10:30"]),
    )
    db.add(offering)
    db.flush()
    return offering


# ── seeding steps ─────────────────────────────────────────────────────────
#: How each curriculum internship component is carried out. The engine is one
#: engine; programmes differ only in this configuration — which is the whole
#: point of `InternshipProgram` being a row rather than a subclass.
#:
#: Rural Internship is typed CSSI because it fills the same slot under the same
#: Academic Rules clause (3 weeks of community work at the end of the first
#: year) and must therefore be coordinated through the same scope. Its name and
#: description keep it distinguishable.
INTERNSHIP_TEMPLATES = {
    "CSSI": {
        "type": InternshipType.CSSI, "label": "Civic and Social Service Internship",
        "group": True, "orgs": ["NGO"], "reports": ReportFrequency.NONE,
        "report_count": 0, "industry_mentor": False, "closes_after_target": True,
        "domain": CoordinationDomain.CSSI,
        "stages": "CSSI", "criteria": "CSSI",
        "blurb": "Three weeks of community service undertaken at the end of "
                 "Semester II, with the report and viva at the start of the "
                 "next odd semester.",
    },
    "RI": {
        "type": InternshipType.CSSI, "label": "Rural Internship",
        "group": True, "orgs": ["NGO"], "reports": ReportFrequency.NONE,
        "report_count": 0, "industry_mentor": False, "closes_after_target": True,
        "domain": CoordinationDomain.CSSI,
        "stages": "CSSI", "criteria": "CSSI",
        "blurb": "Three weeks of rural community engagement. Petroleum "
                 "Engineering runs this in place of CSSI.",
    },
    "SI": {
        "type": InternshipType.SUMMER, "label": "Summer Internship",
        "group": False, "orgs": ["COMPANY", "STARTUP", "RESEARCH_LAB"],
        "reports": ReportFrequency.WEEKLY, "report_count": 8,
        "industry_mentor": True, "closes_after_target": False,
        "domain": CoordinationDomain.SUMMER_INTERNSHIP,
        "stages": "SUMMER", "criteria": "SUMMER",
        "blurb": "Industry internship carried out over the break after "
                 "Semester VI and assessed in Semester VII.",
    },
    "IT": {
        "type": InternshipType.SUMMER, "label": "Industrial Training / IEP",
        "group": False, "orgs": ["COMPANY", "STARTUP", "RESEARCH_LAB"],
        "reports": ReportFrequency.FORTNIGHTLY, "report_count": 3,
        "industry_mentor": True, "closes_after_target": False,
        "domain": CoordinationDomain.SUMMER_INTERNSHIP,
        "stages": "SUMMER", "criteria": "SUMMER",
        "blurb": "Six weeks of industrial training in the non-teaching period "
                 "of the third year. The 2020-scheme equivalent of the Summer "
                 "Internship.",
    },
}

STAGE_SETS = {"CSSI": D.CSSI_STAGES, "SUMMER": D.SUMMER_STAGES}
CRITERIA_SETS = {"CSSI": D.CSSI_CRITERIA, "SUMMER": D.SUMMER_CRITERIA}


def seed_internship_programs_for_curricula(db: Session, year, semesters,
                                           faculty_by_code) -> list:
    """One internship programme per (department, internship component) actually
    in a published curriculum.

    Nothing here decides *which* programmes have CSSI — the curriculum does.
    Petroleum gets a Rural Internship instead, the 2020-scheme cohorts get
    Industrial Training in Semester VI rather than a Semester VII Summer
    Internship, and Biotechnology gets nothing at all because its curriculum is
    still a draft. All of that falls out of the data.
    """
    created = []
    coordinators = {
        assignment.department_id: assignment.faculty_id
        for assignment in db.scalars(select(FacultyRoleAssignment).where(
            FacultyRoleAssignment.role == AssignedRole.COORDINATOR))
    }
    seen: set[tuple[int, str]] = set()

    for curriculum in db.scalars(select(Curriculum).where(
            Curriculum.status == CurriculumStatus.PUBLISHED)):
        program = db.get(Program, curriculum.program_id)
        department_id = program.department_id
        for component in db.scalars(select(CurriculumComponent).where(
                CurriculumComponent.curriculum_id == curriculum.id,
                CurriculumComponent.component_type == ComponentType.INTERNSHIP)):
            template = INTERNSHIP_TEMPLATES.get(component.code)
            if template is None:                 # Industrial Orientation, etc.
                continue
            # ICT already has hand-built CSSI and Summer programmes carrying the
            # live demo records; don't duplicate them.
            if department_id == ict_department_id(db) and template["type"] in (
                    InternshipType.CSSI, InternshipType.SUMMER):
                continue
            key = (department_id, component.code)
            if key in seen:
                continue
            seen.add(key)

            department = db.get(Department, department_id)
            target = component.semester_number
            code = f"{component.code}-{department.code}-{year.label[:4]}"
            internship = InternshipProgram(
                code=code,
                name=f"{template['label']} — {department.short_name or department.code}",
                type=template["type"], description=template["blurb"],
                academic_year_id=year.id,
                semester_id=semesters[min(target, 8)].id,
                department_id=department_id,
                target_semester=target,
                # Floated one semester ahead so students can line up a host over
                # the break — the rule the Academic Rules describe for every
                # internship type, not a CSSI special case.
                announce_from_semester=max(target - 1, 1),
                visible_to_semester=target if template["closes_after_target"] else None,
                credits=float(component.credits),
                requires_group=template["group"], default_group_size=10 if template["group"] else 0,
                requires_organization=True,
                allowed_organization_types=template["orgs"],
                report_frequency=template["reports"],
                expected_report_count=template["report_count"],
                requires_industry_mentor=template["industry_mentor"],
                registration_opens_at=NOW - dt.timedelta(days=45),
                registration_closes_at=NOW + dt.timedelta(days=30),
                start_date=TODAY - dt.timedelta(days=30),
                end_date=TODAY + dt.timedelta(days=30),
                status=ProgramStatus.REGISTRATION_OPEN,
                coordinator_faculty_id=coordinators.get(department_id),
                config={"curriculum_component": component.code,
                        "curriculum_version": curriculum.version},
            )
            db.add(internship)
            db.flush()
            for index, (scode, name, desc, needs_doc, doc_type, owner) in enumerate(
                    STAGE_SETS[template["stages"]], 1):
                db.add(InternshipStage(
                    program_id=internship.id, code=scode, name=name, description=desc,
                    sequence=index, is_mandatory=True, requires_document=needs_doc,
                    document_type=DocumentType(doc_type) if doc_type else None,
                    owner_role=owner,
                ))
            for index, (ccode, name, desc, max_marks, weight) in enumerate(
                    CRITERIA_SETS[template["criteria"]], 1):
                db.add(EvaluationCriteria(
                    program_id=internship.id, code=ccode, name=name, description=desc,
                    max_marks=max_marks, weight=weight, sequence=index,
                    evaluator_role=(EvaluatorRole.INDUSTRY_MENTOR if ccode == "INDUSTRY"
                                    else EvaluatorRole.FACULTY_MENTOR),
                ))
            created.append(internship)
    db.flush()
    return created


def ict_department_id(db: Session) -> int | None:
    department = db.scalar(select(Department).where(Department.code == "ICT"))
    return department.id if department else None


def seed_program_cohorts(db: Session, programs: dict, departments: dict) -> list[Student]:
    """Realistic cohorts for every programme other than ICT.

    Divisions are read back from `program_divisions` — the rows the curriculum
    import created from each programme's own configuration — so CSBS produces one
    division and Computer Engineering four, without this function knowing either
    number.
    """
    taken = {roll for (roll,) in db.execute(select(Student.roll_number))}
    seen_names = {name for (name,) in db.execute(select(User.full_name))}
    created: list[Student] = []

    named: dict[str, list[tuple]] = {}
    for program_code, *rest in D.NAMED_PROGRAM_STUDENTS:
        named.setdefault(program_code, []).append(tuple(rest))

    for program_code, prefix, dept_code, batches in D.PROGRAM_COHORTS:
        program = programs.get(program_code)
        if program is None:            # a programme with no imported curriculum
            continue
        rows: list[tuple] = []
        for admission_year, semester, per_division in batches:
            divisions = curriculum_engine.divisions_for(db, program.id, admission_year)
            if not divisions:
                divisions = ["A"]
            rows.extend(D.generate_program_cohort(
                rng, prefix, admission_year, semester, divisions, per_division,
                taken, seen_names,
            ))
        for row in named.get(program_code, []):
            name, roll, sem, division, cpi, backlogs, admission = row
            if roll not in taken:
                taken.add(roll)
                seen_names.add(name)
                rows.insert(0, (name, roll, sem, division, cpi, backlogs, admission))

        for name, roll, sem, division, cpi, backlogs, admission in rows:
            email = f"{slugify(name, separator='.')}.{roll[-3:]}@campushub.example.com"
            user = make_user(db, name=name, email=email, roles=[Role.STUDENT],
                             phone=f"+91 9{rng.randint(100000000, 999999999)}")
            student = Student(
                user_id=user.id, roll_number=roll,
                enrollment_number=f"PDEU{admission}{prefix}{roll[-3:]}",
                program_id=program.id, department_id=departments[dept_code].id,
                admission_year=admission, current_semester=sem, division=division,
                batch=f"{admission}-{admission + 4}", cpi=cpi, backlog_count=backlogs,
                guardian_name=f"{name.split()[-1]} family contact",
                guardian_phone=f"+91 9{rng.randint(100000000, 999999999)}",
                address=f"{rng.randint(1, 90)}, Sector {rng.randint(1, 30)}, "
                        "Gandhinagar, Gujarat",
            )
            db.add(student)
            db.flush()
            created.append(student)
    return created


def seed(db: Session) -> None:
    log("Departments, programmes and academic calendar…")
    departments = {}
    for code, name, short, school in D.DEPARTMENTS:
        department = Department(code=code, name=name, short_name=short, school=school,
                                description=f"{name}, {school}.")
        db.add(department)
        db.flush()
        departments[code] = department

    # Programmes are created by the curriculum import below, from the researched
    # official documents — see docs/PHASE3B-RESEARCH.md. Nothing is invented
    # here, so the portal cannot offer a programme the university does not run.
    programs: dict[str, Program] = {}

    year = AcademicYear(label="2025-26", start_date=dt.date(2025, 7, 1),
                        end_date=dt.date(2026, 6, 30), is_current=True)
    previous = AcademicYear(label="2024-25", start_date=dt.date(2024, 7, 1),
                            end_date=dt.date(2025, 6, 30), is_current=False)
    db.add_all([previous, year])
    db.flush()

    semesters: dict[int, Semester] = {}
    for number in range(1, 9):
        term = SemesterTerm.ODD if number % 2 else SemesterTerm.EVEN
        semester = Semester(
            academic_year_id=year.id, number=number, term=term,
            start_date=dt.date(2025, 7, 15) if term is SemesterTerm.ODD
            else dt.date(2026, 1, 5),
            end_date=dt.date(2025, 11, 30) if term is SemesterTerm.ODD
            else dt.date(2026, 5, 20),
            is_current=(number == 6),
        )
        db.add(semester)
        db.flush()
        semesters[number] = semester

    # The terms the *next* cohort will take their electives in. A course is
    # offered once per slot per term, so the courses students choose ahead for
    # are next year's offerings, not a second copy of this year's.
    upcoming = AcademicYear(label="2026-27", start_date=dt.date(2026, 7, 1),
                            end_date=dt.date(2027, 6, 30), is_current=False)
    db.add(upcoming)
    db.flush()
    next_semesters: dict[int, Semester] = {}
    for number in (4, 5, 7):
        term = SemesterTerm.ODD if number % 2 else SemesterTerm.EVEN
        semester = Semester(
            academic_year_id=upcoming.id, number=number, term=term,
            start_date=dt.date(2026, 7, 15) if term is SemesterTerm.ODD
            else dt.date(2027, 1, 5),
            end_date=dt.date(2026, 11, 30) if term is SemesterTerm.ODD
            else dt.date(2027, 5, 20),
            is_current=False,
        )
        db.add(semester)
        db.flush()
        next_semesters[number] = semester

    log("Elective types…")
    elective_types = {}
    for code, name, component_type, mode, min_p, max_p, description in [
        ("OPEN", "Open Elective", ComponentType.OPEN_ELECTIVE, "PREFERENCE", 3, 5,
         "Broadening elective taken outside the parent department."),
        ("PROGRAM_CORE", "Program Core Elective", ComponentType.PROGRAM_CORE_ELECTIVE,
         "PREFERENCE", 2, 4,
         "Specialisation elective within the programme's own tracks."),
        ("MOOC", "NPTEL / SWAYAM / MOOC", ComponentType.MOOC, "DIRECT", 1, 1,
         "Certified online course completed on an approved external platform."),
        ("MINOR", "Minor Specialisation", ComponentType.MINOR, "PREFERENCE", 1, 3,
         "Structured minor taken in another department."),
    ]:
        etype = ElectiveType(code=code, name=name, component_type=component_type,
                             selection_mode=mode, min_preferences=min_p,
                             max_preferences=max_p, description=description)
        db.add(etype)
        db.flush()
        elective_types[code] = etype

    # ── researched curricula ──────────────────────────────────────────────
    # research → extract → normalize → review → import → verify → publish.
    # The review step happened before this line: docs/PHASE3B-RESEARCH.md is the
    # artefact, and `publish=True` is that review being acted on. Even then the
    # importer only publishes versions whose source was fully confirmed —
    # Biotechnology, whose official structure stops at Semester II, stays DRAFT
    # no matter what is asked of it.
    log("Importing researched PDEU curricula…")
    report = curriculum_import.run_import(db, publish=True)
    log(f"  {report.summary()}")
    log(f"  published: {len(report.published)} · "
        f"held for review: {len(report.held_for_review)} · "
        f"flagged for faculty confirmation: {len(report.flagged)}")
    for label in report.held_for_review:
        log(f"    held: {label}")
    programs = {p.code: p for p in db.scalars(select(Program))}
    departments = {d.code: d for d in db.scalars(select(Department))}

    log("ICT elective slots (2024-28 scheme)…")
    # ICT runs on the 2024-28 scheme alone — the one the department's handbook
    # describes and the college now offers. Every ICT batch in the demo is
    # governed by it whatever its admission year: no earlier version exists, and
    # `resolve_curriculum` hands a batch outside every window the newest
    # open-ended one. The slots below are therefore the handbook's own —
    # OE1, OE2-MOOC, OE3, OE4 and PE1…PE5 — not a second, hand-built set.
    ict_curriculum = db.scalar(select(Curriculum).where(
        Curriculum.program_id == programs["B.TECH-ICT"].id,
        Curriculum.version == "2024-28",
    ))
    if ict_curriculum is None:
        raise RuntimeError("The ICT 2024-28 curriculum was not imported.")
    components: dict[str, CurriculumComponent] = {
        c.code: c for c in db.scalars(select(CurriculumComponent).where(
            CurriculumComponent.curriculum_id == ict_curriculum.id))
    }

    # Divisions for every ICT batch in the demo cohort, so the Core Elective
    # allocator has division data for all of them.
    for _label, admission_year, _sem in D.YEAR_GROUPS:
        for name in D.ICT_DIVISIONS:
            existing = db.scalar(select(ProgramDivision).where(
                ProgramDivision.program_id == programs["B.TECH-ICT"].id,
                ProgramDivision.admission_year == admission_year,
                ProgramDivision.name == name,
            ))
            if existing is None:
                db.add(ProgramDivision(program_id=programs["B.TECH-ICT"].id,
                                       admission_year=admission_year, name=name,
                                       capacity=D.STUDENTS_PER_DIVISION))
    db.flush()

    log("Faculty accounts…")
    faculty_by_code: dict[str, Faculty] = {}
    source_url = D.ICT_FACULTY_SOURCE["source"]["url"]
    for name, email, emp_code, dept, designation, cabin, spec, extra in D.FACULTY:
        roles = [Role.FACULTY] + [Role(r) for r in extra]
        real = D.ICT_FACULTY_DETAILS.get(emp_code)
        if real:
            # A real PDEU faculty member: published details only, no invented
            # phone, and no `rng` draw — so generated students do not shift.
            user = make_user(db, name=name, email=email, roles=roles, phone=None)
            # Nobody knows this password; a demo cannot sign in as a real person.
            user.hashed_password = hash_password(secrets.token_urlsafe(32))
            degree = real.get("highest_degree") or {}
            faculty = Faculty(
                user_id=user.id, employee_code=emp_code,
                department_id=departments[dept].id, designation=designation, cabin=None,
                specialization=spec,
                qualification=", ".join(filter(None, [degree.get("degree"),
                                                      degree.get("institution")]))[:150] or None,
                public_email=real["official_email"], public_phone=None,
                profile_url=source_url, is_mentor=True, is_demo=False,
                bio=(f"{designation}, {departments[dept].name}, School of Technology. "
                     f"Research areas: {'; '.join(real['research_areas']) or 'not published'}. "
                     f"Source: PDEU faculty list, retrieved "
                     f"{D.ICT_FACULTY_SOURCE['source']['retrieved_at']}."),
            )
        else:
            mobile = f"+91 98{rng.randint(10000000, 99999999)}"
            office = f"+91 79 232{rng.randint(10000, 99999)}"
            user = make_user(db, name=name, email=email, roles=roles, phone=mobile)
            faculty = Faculty(
                user_id=user.id, employee_code=emp_code,
                department_id=departments[dept].id, designation=designation, cabin=cabin,
                specialization=spec, qualification="Ph.D.", public_email=email,
                public_phone=office, is_mentor=True, is_demo=True,
                bio=(f"Demo account — a fictional {designation.lower()} used to "
                     f"demonstrate the portal, not a PDEU faculty member. "
                     f"Research interests: {spec}."),
            )
        db.add(faculty)
        db.flush()
        faculty_by_code[emp_code] = faculty
    for name, email, emp_code, dept in D.DEPARTMENT_OFFICES:
        office_user = make_user(db, name=name, email=email,
                                roles=[Role.FACULTY, Role.DEPARTMENT_ADMIN])
        db.add(Faculty(
            user_id=office_user.id, employee_code=emp_code,
            department_id=departments[dept].id, designation="Department Office",
            public_email=email, is_mentor=False, is_demo=True,
            bio=f"Administrative office of {departments[dept].name}.",
        ))
    db.flush()

    # Appointed before anything else is handed out, so that every later step —
    # role grants, mentor pools, group leads — is refused by the same rules the
    # API applies if it ever tries to give the HoD a mentee or a module.
    for dept_code, emp_code in D.HEADS_OF_DEPARTMENT.items():
        scope_service.set_hod(db, departments[dept_code], faculty_by_code[emp_code])

    log("Administrator accounts…")
    admin_user = make_user(db, name="Registrar Office", email="admin@campushub.example.com",
                           roles=[Role.SUPER_ADMIN])
    club_admin_user = make_user(db, name="Student Activity Office",
                                email="clubs@campushub.example.com",
                                roles=[Role.CLUB_ADMIN])

    log("Scoped role assignments (role × domain × department)…")
    for emp_code, assigned_role, domain, dept_code in D.ROLE_ASSIGNMENTS:
        faculty = faculty_by_code.get(emp_code)
        if faculty is None:
            continue
        scope_service.assert_can_hold_scoped_role(db, faculty)
        db.add(FacultyRoleAssignment(
            faculty_id=faculty.id, role=AssignedRole(assigned_role),
            domain=CoordinationDomain(domain),
            department_id=departments[dept_code].id if dept_code else None,
            academic_year_id=year.id, assigned_by_user_id=admin_user.id,
            assigned_at=NOW - dt.timedelta(days=120), is_active=True,
            notes="Seeded assignment.",
        ))
        # Only *coordinating* an internship implies the coarse route-guard role.
        # A Mentor grant never does.
        if assigned_role == "COORDINATOR" and CoordinationDomain(domain) in INTERNSHIP_DOMAINS:
            existing = db.scalar(select(UserRole).where(
                UserRole.user_id == faculty.user_id,
                UserRole.role == Role.INTERNSHIP_COORDINATOR,
            ))
            if existing is None:
                db.add(UserRole(user_id=faculty.user_id,
                                role=Role.INTERNSHIP_COORDINATOR))
                # Written now, so a second internship grant to the same person
                # (Projects and Major Project) finds it instead of adding again.
                db.flush()
    db.flush()

    log("Students (ICT — four divisions, full cohort)…")
    students: list[Student] = []
    for name, roll, sem, division, cpi, backlogs, admission in D.generate_cohort(rng):
        if name == D.REPLACED:
            # Same draws as a created student, so later values do not shift.
            rng.randint(100000000, 999999999); rng.randint(100000000, 999999999)
            rng.randint(1, 90); rng.randint(1, 30)
            continue
        email = f"{slugify(name, separator='.')}.{roll[-3:]}@campushub.example.com"
        user = make_user(db, name=name, email=email, roles=[Role.STUDENT],
                         phone=f"+91 9{rng.randint(100000000, 999999999)}")
        student = Student(
            user_id=user.id, roll_number=roll,
            enrollment_number=f"PDEU{admission}{roll[-3:]}",
            program_id=programs["B.TECH-ICT"].id,
            department_id=departments["ICT"].id, admission_year=admission,
            current_semester=sem, division=division, batch=f"{admission}-{admission + 4}",
            cpi=cpi, backlog_count=backlogs,
            guardian_name=f"{name.split()[-1]} family contact",
            guardian_phone=f"+91 9{rng.randint(100000000, 999999999)}",
            address=f"{rng.randint(1, 90)}, Sector {rng.randint(1, 30)}, Gandhinagar, Gujarat",
        )
        db.add(student)
        db.flush()
        students.append(student)

    log("Students for the other verified programmes…")
    program_students = seed_program_cohorts(db, programs, departments)
    log(f"  {len(program_students)} students across "
        f"{len({s.program_id for s in program_students})} programmes")

    log("Course catalogue…")
    courses: dict[str, Course] = {}
    for code, title, credits, dept, school in D.OPEN_ELECTIVES_OTHER_SCHOOL:
        courses[code] = make_course(db, code, title, credits, departments[dept],
                                    school=school)
    for code, title, credits, dept in D.OPEN_ELECTIVES_FOET:
        courses[code] = make_course(db, code, title, credits, departments[dept],
                                    school="FoET")
    for code, title, credits, weeks, url in D.MOOC_COURSES:
        platform = MoocPlatform.NPTEL if code.startswith("NPTEL") else MoocPlatform.SWAYAM
        courses[code] = make_course(db, code, title, credits, None,
                                    platform=platform, provider_url=url,
                                    duration_weeks=weeks,
                                    description=f"{weeks}-week certified course on "
                                                f"{platform.value}. Proctored exam "
                                                "required for credit.")

    log("Course offerings…")
    offerings: dict[str, list[CourseOffering]] = {}
    ict_coordinator = faculty_by_code["ICT-F-106"]      # Open Electives
    core_coordinator = faculty_by_code["ICT-F-107"]     # Program Core Electives

    # Open Electives: 40 to run, 75 PER SECTION, extra sections open on demand.
    OPEN_ELECTIVE_RULES = dict(
        min_students_to_run=40, section_capacity=75, allow_multiple_sections=True,
    )
    # Core Electives: same 40 minimum but counted across the participating
    # divisions combined, and NO upper limit — one combined class.
    CORE_ELECTIVE_RULES = dict(
        min_students_to_run=40, section_capacity=None,
        allow_multiple_sections=False, eligible_divisions=D.ICT_DIVISIONS,
    )

    offerings["OE1"] = [
        make_offering(db, courses[c[0]], semesters[4], components["OE1"],
                      coordinator=ict_coordinator, **OPEN_ELECTIVE_RULES)
        for c in D.OPEN_ELECTIVES_OTHER_SCHOOL
    ]
    offerings["OE3"] = [
        make_offering(db, courses[c[0]], semesters[6], components["OE3"],
                      coordinator=ict_coordinator, **OPEN_ELECTIVE_RULES)
        for c in D.OPEN_ELECTIVES_FOET
    ]
    offerings["OE4"] = [
        make_offering(db, courses[c[0]], semesters[7], components["OE4"],
                      coordinator=ict_coordinator, **OPEN_ELECTIVE_RULES)
        for c in D.OPEN_ELECTIVES_FOET[:5]
    ]
    # MOOC is an external platform course: no classroom, so no section limit.
    offerings["OE2-MOOC"] = [
        make_offering(db, courses[c[0]], semesters[5], components["OE2-MOOC"],
                      min_students_to_run=0, closes_days=35)
        for c in D.MOOC_COURSES
    ]
    # Program Electives offer the subjects the handbook lists for each
    # semester. It gives one basket per semester, not per slot: Program Elective
    # 2 and 3 draw on the Semester VI basket, 4 and 5 on the Semester VII one.
    catalogue = {c.code: c for c in db.scalars(select(Course))}
    basket_of = {"PE1": "PE1", "PE2": "PE2", "PE3": "PE2", "PE4": "PE4", "PE5": "PE4"}

    def handbook_basket(slot_code: str) -> list[Course]:
        codes = (components[basket_of[slot_code]].config or {}).get("options", [])
        basket = [catalogue[code] for code in codes if code in catalogue]
        for course in basket:
            # These are ICT's own specialisation subjects; a few arrive from
            # the shared catalogue with no owning department recorded.
            if course.department_id is None:
                course.department_id = departments["ICT"].id
        return basket

    for pe_code, semester_number in [
        ("PE1", 5), ("PE2", 6), ("PE3", 6), ("PE4", 7), ("PE5", 7),
    ]:
        offerings[pe_code] = [
            make_offering(db, course, semesters[semester_number],
                          components[pe_code], coordinator=core_coordinator,
                          **CORE_ELECTIVE_RULES)
            for course in handbook_basket(pe_code)
        ]

    log("Elective registration rounds…")
    # Rounds make elective registration a workflow rather than a pair of dates on
    # each course. Seeded across the lifecycle so a demo can show every student
    # state without waiting for a clock: OE1 is live, OE3 is locked while
    # allocation is prepared, and OE4's results are published.
    ict_program = programs["B.TECH-ICT"]
    windows: dict[str, ElectiveRegistrationWindow] = {}
    for code, title, component_code, semester_number, status, opens, closes in [
        ("OE1-2025-LIVE", "Open Elective 1 — Semester IV", "OE1", 4,
         RegistrationWindowStatus.OPEN, -3, 10),
        ("OE3-2025-LOCKED", "Open Elective 3 — Semester VI", "OE3", 6,
         RegistrationWindowStatus.LOCKED, -30, -2),
        ("OE4-2025-PUBLISHED", "Open Elective 4 — Semester VII", "OE4", 7,
         RegistrationWindowStatus.PUBLISHED, -60, -30),
        ("PE1-2025-LIVE", "Program Elective 1 — Semester V", "PE1", 5,
         RegistrationWindowStatus.OPEN, -2, 12),
    ]:
        component_type = (ComponentType.PROGRAM_CORE_ELECTIVE
                          if component_code.startswith("PE")
                          else ComponentType.OPEN_ELECTIVE)
        window = ElectiveRegistrationWindow(
            code=code, title=title, component_type=component_type,
            academic_year_id=year.id, semester_id=semesters[semester_number].id,
            department_id=departments["ICT"].id, status=status,
            opens_at=NOW + dt.timedelta(days=opens),
            closes_at=NOW + dt.timedelta(days=closes),
            eligible_semesters=[semester_number],
            eligible_program_ids=[ict_program.id],
            eligible_divisions=list(D.ICT_DIVISIONS),
            min_preferences=3, max_preferences=5,
            locked_at=(NOW - dt.timedelta(days=1)
                       if status != RegistrationWindowStatus.OPEN else None),
            allocated_at=(NOW - dt.timedelta(hours=12)
                          if status == RegistrationWindowStatus.PUBLISHED else None),
            published_at=(NOW - dt.timedelta(hours=6)
                          if status == RegistrationWindowStatus.PUBLISHED else None),
            description=f"Seeded round for {title}.",
        )
        db.add(window)
        db.flush()
        windows[component_code] = window
        for offering in offerings.get(component_code, []):
            offering.registration_window_id = window.id
    db.flush()

    # Early choice filling, as the department actually runs it: an elective
    # for Semester N is chosen mid-way through Semester N-1, so the timetable
    # can be built over the vacation. Opening that round, with its deadline, is
    # the coordinator's job (Administration → Registration Rounds), so the
    # courses for the *next* cohort are put on offer here and left in no round:
    #   · Open Elective 1  — for the Open Elective coordinator to open to Sem III
    #   · Program Elective 1 — for the Core Elective coordinator to open to Sem IV
    #   · Program Electives 4 and 5 — for a two-stage round (interest, shortlist,
    #     final) opened to Sem VI, as the department runs its Sem VII electives
    # They are next year's offerings (2026-27): a course is offered once per
    # slot per term, and belongs to one round at a time.
    offerings["OE1-NEXT"] = [
        make_offering(db, courses[c[0]], next_semesters[4], components["OE1"],
                      coordinator=ict_coordinator, **OPEN_ELECTIVE_RULES)
        for c in D.OPEN_ELECTIVES_OTHER_SCHOOL
    ]
    offerings["PE1-NEXT"] = [
        make_offering(db, course, next_semesters[5], components["PE1"],
                      coordinator=core_coordinator, **CORE_ELECTIVE_RULES)
        for course in handbook_basket("PE1")
    ]
    for pe_code in ("PE4", "PE5"):
        offerings[f"{pe_code}-NEXT"] = [
            make_offering(db, course, next_semesters[7], components[pe_code],
                          coordinator=core_coordinator, **CORE_ELECTIVE_RULES)
            for course in handbook_basket(pe_code)
        ]
    for window in windows.values():
        registration_service.validate_round(db, window)
    db.flush()

    log("Minor programmes (official Annexure II catalogue)…")
    minors: dict[str, MinorProgram] = {}
    for code, name, dept, credits, min_cpi, max_backlogs, capacity in D.MINOR_PROGRAMS:
        minor = MinorProgram(
            code=code, name=name, department_id=departments[dept].id,
            academic_year_id=year.id, total_credits=credits, capacity=capacity,
            eligible_from_semester=3, min_cpi=min_cpi, max_backlogs=max_backlogs,
            excluded_department_ids=[departments[dept].id],
            allocation_strategy="manual",
            # CONFIRMED policy, not a worked example: "The admission to the
            # Minor specialization will be as per merit based on latest CPI and
            # on pro rata basis." — Academic Rules 2024, Annexure II.
            #
            # CPI ranking is therefore official *here* and only here. The
            # "pro rata basis" half is left unimplemented and configurable: the
            # rules never say pro rata across what (departments? applicants per
            # branch?), and that is not a gap worth guessing at.
            rules={
                "ranking": {
                    "criteria": [
                        {"field": "cpi", "direction": "desc"},
                        {"field": "backlog_count", "direction": "asc"},
                        {"field": "preference_order", "direction": "asc"},
                        {"field": "submitted_at", "direction": "asc"},
                    ],
                },
                "source": "B.Tech. Academic Rules (batch 2024 onward), Annexure II.",
                "source_url": MINOR_SOURCE_URL,
                "continuation_rule": (
                    "A minimum CPI of 7.5 must be maintained throughout the B.Tech "
                    "programme; registration is cancelled if it falls below."
                ),
                "pro_rata": {
                    "status": "REQUIRES_FACULTY_CONFIRMATION",
                    "note": "Annexure II says admission is 'as per merit based on "
                            "latest CPI and on pro rata basis' without defining the "
                            "pro rata denominator. Not implemented.",
                },
                "offered_semesters": [3, 4, 5, 6, 7],
                "partner_departments": D.MINOR_PARTNER_DEPARTMENTS.get(code, []),
            },
            application_opens_at=NOW - dt.timedelta(days=14),
            application_closes_at=NOW + dt.timedelta(days=28),
            coordinator_faculty_id=faculty_by_code["ICT-F-102"].id,
            description=f"{name} — {credits} additional credits, offered from "
                        "Semester III to Semester VII to students of every "
                        f"department except {departments[dept].name}.",
        )
        db.add(minor)
        db.flush()
        minors[code] = minor
        for index, (mc_code, mc_title, mc_credits, mc_sem) in enumerate(
                D.MINOR_COURSES[code], 1):
            course = make_course(db, mc_code, mc_title, mc_credits, departments[dept])
            db.add(MinorCourse(minor_program_id=minor.id, course_id=course.id,
                               sequence=index,
                               # Annexure II states the semester each course is
                               # preferably offered in; III is the first.
                               semester_offset=max(mc_sem - 2, 1),
                               is_mandatory=True))
    db.flush()

    log("Organisations (NGOs and companies)…")
    ngos = []
    for name, field, city, district, state in D.NGOS:
        org = Organization(
            name=name, type=OrganizationType.NGO, field_of_work=field, city=city,
            district=district, state=state, country="India",
            address=f"{rng.randint(1, 60)}, {city}, {state}",
            phone=f"+91 79 2{rng.randint(1000000, 9999999)}",
            email=f"contact@{slugify(name)}.example.com",
            contact_person=f"{rng.choice(['Mr.', 'Ms.', 'Dr.'])} "
                           f"{rng.choice(['Shah', 'Patel', 'Desai', 'Mehta'])}",
            contact_designation="Programme Coordinator", is_verified=True,
            description=f"{name} works on {field.lower()} in and around {city}.",
        )
        db.add(org)
        db.flush()
        ngos.append(org)

    companies = []
    for name, otype, field, city, state in D.COMPANIES:
        org = Organization(
            name=name, type=OrganizationType(otype), field_of_work=field, city=city,
            state=state, country="India", is_verified=True,
            website=f"https://{slugify(name)}.example.com",
            contact_person="Talent Team", contact_designation="HR",
            description=f"{name} — {field}.",
        )
        db.add(org)
        db.flush()
        companies.append(org)

    log("Internship programmes (CSSI + Summer Internship)…")
    cssi = InternshipProgram(
        code="CSSI-2025", name="Community and Social Service Internship",
        type=InternshipType.CSSI,
        description="Compulsory social internship carried out in Semester III. The "
                    "coordinator floats it during Semester II so students can line up "
                    "an approved NGO over the break; the certificate is submitted once "
                    "Semester III begins, and a presentation slot is allocated after "
                    "it is verified.",
        academic_year_id=year.id, semester_id=semesters[2].id,
        department_id=departments["ICT"].id,
        # Floated in Semester II so students can line up an NGO over the break;
        # carried out, submitted and presented in Semester III. Students past
        # Semester III no longer see it.
        target_semester=3, announce_from_semester=2, visible_to_semester=3,
        credits=2,
        requires_group=True, default_group_size=10, requires_organization=True,
        allowed_organization_types=["NGO"], report_frequency=ReportFrequency.NONE,
        # CSSI asks each student for their NGO supervisor's name and number.
        expected_report_count=0, requires_industry_mentor=True,
        registration_opens_at=NOW - dt.timedelta(days=45),
        registration_closes_at=NOW + dt.timedelta(days=15),
        start_date=TODAY - dt.timedelta(days=40), end_date=TODAY + dt.timedelta(days=25),
        status=ProgramStatus.REGISTRATION_OPEN,
        coordinator_faculty_id=faculty_by_code["ICT-F-104"].id,
        # Run in coordinator-opened windows: registration in Semester II, then
        # posters, presentations and marks in Semester III.
        config={"group_size_configurable": True,
                "windows": ["REGISTRATION", "PRESENTATION"]},
    )
    summer = InternshipProgram(
        code="SI-2025", name="Summer Internship",
        type=InternshipType.SUMMER,
        description="Semester VII industry internship. Students are allocated a faculty "
                    "mentor, submit periodic reports, and are evaluated jointly by the "
                    "faculty mentor and the industry mentor.",
        academic_year_id=year.id, semester_id=semesters[7].id,
        department_id=departments["ICT"].id,
        # Announced in Semester VI, carried out over the following break, and
        # still visible in Semester VII while it is being assessed.
        target_semester=6, announce_from_semester=6, visible_to_semester=None,
        credits=4,
        requires_group=False, default_group_size=0, requires_organization=True,
        allowed_organization_types=["COMPANY", "STARTUP", "RESEARCH_LAB"],
        report_frequency=ReportFrequency.WEEKLY, expected_report_count=8,
        requires_industry_mentor=True,
        registration_opens_at=NOW - dt.timedelta(days=60),
        registration_closes_at=NOW + dt.timedelta(days=30),
        start_date=TODAY - dt.timedelta(days=35), end_date=TODAY + dt.timedelta(days=21),
        status=ProgramStatus.REGISTRATION_OPEN,
        coordinator_faculty_id=faculty_by_code["ICT-F-102"].id,
    )
    db.add_all([cssi, summer])
    db.flush()

    for program, stages in ((cssi, D.CSSI_STAGES), (summer, D.SUMMER_STAGES)):
        for index, (code, name, desc, needs_doc, doc_type, owner) in enumerate(stages, 1):
            db.add(InternshipStage(
                program_id=program.id, code=code, name=name, description=desc,
                sequence=index, is_mandatory=True, requires_document=needs_doc,
                document_type=DocumentType(doc_type) if doc_type else None,
                owner_role=owner,
            ))
    for program, criteria in ((cssi, D.CSSI_CRITERIA), (summer, D.SUMMER_CRITERIA)):
        for index, (code, name, desc, max_marks, weight) in enumerate(criteria, 1):
            db.add(EvaluationCriteria(
                program_id=program.id, code=code, name=name, description=desc,
                max_marks=max_marks, weight=weight, sequence=index,
                # The industry component originates outside the institution;
                # tagging it lets the API refuse student-entered marks.
                evaluator_role=(EvaluatorRole.INDUSTRY_MENTOR if code == "INDUSTRY"
                                else EvaluatorRole.FACULTY_MENTOR),
            ))
    db.flush()

    log("CSSI groups…")
    cssi_groups = []
    # Led by the faculty who actually hold a CSSI Mentor grant — deliberately
    # NOT the CSSI coordinator, so the two roles stay visibly distinct.
    for index, emp_code in enumerate(D.mentors_for("CSSI", "ICT"), 1):
        group = InternshipGroup(
            program_id=cssi.id, name=f"Group {index}",
            faculty_id=faculty_by_code[emp_code].id, capacity=cssi.default_group_size,
            # Rostered mentors take a fixed slot rather than an `rng` draw, so
            # adding them leaves every later random value — names included — alone.
            meeting_schedule=(
                ["Friday 15:00, faculty cabin", "Wednesday 16:00, Seminar Room 2"][index % 2]
                if emp_code in {row[2] for row in D.ICT_FACULTY_ROSTER}
                else rng.choice(["Friday 15:00, faculty cabin",
                                 "Wednesday 16:00, Seminar Room 2"])
            ),
        )
        db.add(group)
        db.flush()
        cssi_groups.append(group)

    log("Mentor assignments…")
    mentor_pool = [faculty_by_code[c] for c in
                   ["ICT-F-101", "ICT-F-102", "ICT-F-106", "ICT-F-104"]]
    for mentor in mentor_pool:
        scope_service.assert_can_mentor(db, mentor)
    for index, student in enumerate(students):
        mentor = mentor_pool[index % len(mentor_pool)]
        db.add(MentorAssignment(
            student_id=student.id, faculty_id=mentor.id, academic_year_id=year.id,
            assigned_by_user_id=admin_user.id, assigned_at=NOW - dt.timedelta(days=90),
            is_active=True,
        ))
    db.flush()

    if D.REAL_STUDENTS:
        log(f"Real students from seed/private ({len(D.REAL_STUDENTS)})…")
        for real in D.REAL_STUDENTS:
            for label in {real["division"]}:
                if db.scalar(select(ProgramDivision).where(
                        ProgramDivision.program_id == programs["B.TECH-ICT"].id,
                        ProgramDivision.admission_year == real["admission_year"],
                        ProgramDivision.name == label)) is None:
                    db.add(ProgramDivision(program_id=programs["B.TECH-ICT"].id,
                                           admission_year=real["admission_year"], name=label))
                    db.flush()
            user = make_user(db, name=real["name"],
                             email=f"{real['roll_number'].lower()}@students.campushub.example.com",
                             roles=[Role.STUDENT], phone=None)
            # Real people never sign in to a demo.
            user.hashed_password = hash_password(secrets.token_urlsafe(32))
            student = Student(
                user_id=user.id, roll_number=real["roll_number"],
                program_id=programs["B.TECH-ICT"].id, department_id=departments["ICT"].id,
                admission_year=real["admission_year"], current_semester=real["semester"],
                division=real["division"],
                batch=f"{real['admission_year']}-{real['admission_year'] + 4}",
                cpi=None, backlog_count=0,   # not in the list; nothing is invented
            )
            db.add(student)
            db.flush()
            students.append(student)

    log("Internship programmes for the other verified curricula…")
    extra = seed_internship_programs_for_curricula(db, year, semesters, faculty_by_code)
    log(f"  {len(extra)} programmes: "
        + ", ".join(sorted({p.name for p in extra}))[:150])

    seed_internship_records(db, cssi, summer, cssi_groups, students, ngos, companies,
                            faculty_by_code, admin_user)
    log("Semester VII and VIII projects…")
    seed_project_programs(db, year, semesters, departments, faculty_by_code, students, companies)
    seed_academic_activity(db, components, offerings, courses, students, elective_types,
                           minors, faculty_by_code, admin_user)
    seed_community(db, students, faculty_by_code, club_admin_user)
    seed_engagement(db, students, faculty_by_code, admin_user, departments)

    # The dataset must obey the rule it demonstrates: no HoD ends up with a
    # mentee, an internship student, a group or a scoped role.
    db.flush()
    # ...and no internship mentor carries more students than their programme allows.
    for program in db.scalars(select(InternshipProgram)):
        cap = internship_engine.mentor_capacity(program)
        for faculty_id, count in db.execute(
            select(InternshipEnrollment.mentor_faculty_id, func.count())
            .where(InternshipEnrollment.program_id == program.id,
                   InternshipEnrollment.mentor_faculty_id.is_not(None))
            .group_by(InternshipEnrollment.mentor_faculty_id)
        ):
            if count > cap:
                raise RuntimeError(
                    f"Seed gave one {program.code} mentor {count} students; "
                    f"the programme allows {cap}."
                )
    for dept_code, emp_code in D.HEADS_OF_DEPARTMENT.items():
        load = scope_service.mentoring_load(db, faculty_by_code[emp_code])
        if load:
            raise RuntimeError(
                f"Seed gave the {dept_code} HoD {', '.join(load)}; an HoD holds none."
            )

    db.commit()


PROJECT_PROGRAMS = [
    # (code, name, type, semester, credits, admission years, stages, criteria,
    #  reports, tracks, what still needs confirming, description)
    ("MP7-2025", "Minor Project (Semester VII)", InternshipType.MINOR_PROJECT, 7, 3,
     {"to": 2023}, D.MINOR_PROJECT_STAGES, D.MINOR_PROJECT_CRITERIA,
     (ReportFrequency.NONE, 0), None,
     ["credits", "stages", "rubric", "admission batches", "team size", "guide preferences"],
     "A guided project in Semester VII for the schemes before 2024-28. Register a "
     "topic, work with your faculty guide, and present at mid-semester and at the end."),
    ("SEM7-2025", "Seminar (Semester VII)", InternshipType.SEMINAR, 7, 1,
     {"from": 2024}, D.SEMINAR_STAGES, D.SEMINAR_CRITERIA,
     (ReportFrequency.NONE, 0), None,
     ["stages", "rubric", "guide preferences"],
     "The 1-credit Semester VII Seminar of the 2024-28 scheme: a topic studied in "
     "depth under a faculty guide, written up and presented."),
    ("MP8-2025", "Major Project / Industry Internship (Semester VIII)",
     InternshipType.MAJOR_PROJECT, 8, 12, None, D.MAJOR_PROJECT_STAGES,
     D.MAJOR_PROJECT_CRITERIA, (ReportFrequency.MONTHLY, 4), D.MAJOR_PROJECT_TRACKS,
     ["stages", "rubric", "report cadence", "credits for batches before 2024", "team size",
      "guide preferences"],
     "The 12-credit Semester VIII Major / Comprehensive Project. Take it as an "
     "in-house project with a faculty guide, or as a full-semester industry "
     "internship with a guide and a supervisor at the host."),
]


def make_project_program(db, spec, year, semesters, departments, faculty_by_code):
    """One Semester VII / VIII programme, with its stages and rubric."""
    (code, name, ptype, sem, credits, batches, stages, criteria, (freq, count),
     tracks, unconfirmed, blurb) = spec
    config = {"requires_faculty_confirmation": list(unconfirmed),
              # Rank up to three guides; a seminar is individual, a project
              # may be done in a team of up to four (or alone).
              "guide_preferences": 3}
    if ptype != InternshipType.SEMINAR:
        config["team_size"] = {"min": 1, "max": 4}
    early = sem - 1 if tracks else None
    if early:
        # Semester VIII registration opens in Semester VII, so an
        # industry-track student can line up a company ahead of time.
        config["register_from_semester"] = early
    if batches:
        config["admission_years"] = batches
    if tracks:
        config["tracks"] = tracks
    program = InternshipProgram(
        code=code, name=name, type=ptype, description=blurb,
        academic_year_id=year.id, semester_id=semesters[sem].id,
        department_id=departments["ICT"].id, target_semester=sem,
        # Offered in its own semester only; a student who registered keeps
        # their record afterwards. Left open-ended, the Semester VII Minor
        # Project was being offered to Semester VIII students as well.
        announce_from_semester=early or sem, visible_to_semester=sem, credits=credits,
        requires_group=False, default_group_size=0,
        # A track decides for Semester VIII; Semester VII has no host.
        requires_organization=False, allowed_organization_types=[],
        report_frequency=freq, expected_report_count=count,
        requires_industry_mentor=False,
        registration_opens_at=NOW - dt.timedelta(days=20),
        registration_closes_at=NOW + dt.timedelta(days=20),
        start_date=TODAY - dt.timedelta(days=30), end_date=TODAY + dt.timedelta(days=90),
        status=ProgramStatus.REGISTRATION_OPEN,
        coordinator_faculty_id=faculty_by_code["ICT-F-103"].id,
        config=config,
    )
    db.add(program)
    db.flush()
    for index, (scode, sname, desc, needs_doc, doc_type, owner) in enumerate(stages, 1):
        db.add(InternshipStage(
            program_id=program.id, code=scode, name=sname, description=desc,
            sequence=index, is_mandatory=True, requires_document=needs_doc,
            document_type=DocumentType(doc_type) if doc_type else None, owner_role=owner))
    for index, (ccode, cname, desc, max_marks, weight) in enumerate(criteria, 1):
        db.add(EvaluationCriteria(
            program_id=program.id, code=ccode, name=cname, description=desc,
            max_marks=max_marks, weight=weight, sequence=index,
            evaluator_role=EvaluatorRole.FACULTY_MENTOR))
    db.flush()
    return program


def seed_project_programs(db, year, semesters, departments, faculty_by_code,
                          students, companies) -> list:
    """Semester VII and VIII projects: rows on the one internship engine."""
    created = [make_project_program(db, spec, year, semesters, departments, faculty_by_code)
               for spec in PROJECT_PROGRAMS]
    minor_project, _seminar, major = created
    seed_project_samples(db, minor_project, major, departments, faculty_by_code,
                         students, companies)
    return created


def seed_project_samples(db, minor_project, major, departments, faculty_by_code,
                         students, companies) -> None:
    """A few fictional students already under way, so the coordinator and guide
    screens have something to show.

    Never a real student (the real Semester VII cohort gets no invented work),
    and not the two demo sign-ins left to register live: Arjun Verma (VII) and
    Pooja Shah (VIII). Either programme may be None (already present).
    """
    left_to_register = {"21BIT021", "21BIT081"}
    def generated(semester):
        return [s for s in students
                if s.current_semester == semester and s.roll_number not in left_to_register
                and s.user.email.endswith("@campushub.example.com")
                and "@students." not in s.user.email
                and s.department_id == departments["ICT"].id]
    guides = [faculty_by_code[c] for c in ("ICT-F-101", "ICT-F-106", "ICT-F-107")]
    if minor_project is not None:
        for index, student in enumerate([s for s in generated(7) if s.admission_year <= 2023][:9]):
            _seed_project_record(db, minor_project, student, guides[index % 3], index)
    if major is not None:
        for index, student in enumerate(generated(8)[:8]):
            track = "INDUSTRY" if index % 2 else "PROJECT"
            _seed_project_record(db, major, student, guides[index % 3], index, track=track,
                                 company=companies[index % len(companies)] if track == "INDUSTRY" else None)
    db.flush()


def _seed_project_record(db, program, student, guide, index, *, track=None, company=None):
    enrollment = internship_engine.enroll_student(db, program=program, student=student, track=track)
    enrollment.mentor_faculty_id = guide.id
    enrollment.status = EnrollmentStatus.MENTOR_ASSIGNED
    if company is not None:
        enrollment.organization_id = company.id
        enrollment.industry_mentor_name = "Ms. Kavita Rao"
        enrollment.industry_mentor_phone = "+91 98250 00000"
    db.flush()
    db.refresh(enrollment)
    # Spread how far each student has got: synopsis approved, guide assigned,
    # and for some a mid-semester review waiting for the guide.
    for progress in sorted(enrollment.stage_progress, key=lambda p: p.stage.sequence):
        if progress.status == StageStatus.SKIPPED:
            continue
        if progress.stage.code in ("SYNOPSIS", "GUIDE_ALLOCATION", "OFFER_LETTER"):
            progress.status = StageStatus.APPROVED
            progress.submitted_at = NOW - dt.timedelta(days=18 - index % 5)
            progress.reviewed_at = NOW - dt.timedelta(days=15 - index % 5)
            progress.reviewed_by_user_id = guide.user_id
        elif progress.stage.code == "MID_REVIEW" and index % 3 == 0:
            progress.status = StageStatus.SUBMITTED
            progress.submitted_at = NOW - dt.timedelta(days=2 + index % 4)
    internship_engine._advance_current_stage(db, enrollment)
    enrollment.status = EnrollmentStatus.IN_PROGRESS


def seed_internship_records(db, cssi, summer, cssi_groups, students, ngos, companies,
                            faculty_by_code, admin_user) -> None:
    # The cohort registered in Semester II through the coordinator's window,
    # which has since closed. The presentation window is left for the
    # coordinator to open in the demo — that is the step that tells every
    # student their mentor and starts the marks clock.
    db.add(InternshipWindow(
        program_id=cssi.id, kind=InternshipWindowKind.REGISTRATION,
        title="CSSI registration — Semester II",
        message=("CSSI (Community and Social Service Internship) is a compulsory "
                 "2-credit internship with an approved NGO, carried out over the break "
                 "and presented in Semester III. Register your NGO and your NGO "
                 "supervisor's name and phone number before the deadline."),
        opens_at=NOW - dt.timedelta(days=60), closes_at=NOW - dt.timedelta(days=30),
        cohort_semester=2, opened_by_user_id=faculty_by_code["ICT-F-104"].user_id,
    ))
    log("CSSI enrolments with live stage progress…")
    cssi_stages = list(db.scalars(
        select(InternshipStage).where(InternshipStage.program_id == cssi.id)
        .order_by(InternshipStage.sequence)
    ))
    # First-year and second-year students take CSSI.
    # CSSI is carried out in Semester III, so only those students hold a record.
    cssi_students = [s for s in students if s.current_semester == 3]
    for index, student in enumerate(cssi_students):
        group = cssi_groups[index % len(cssi_groups)]
        # Vary how far each student has progressed so the UI shows real spread.
        reached = min(2 + (index % 6), len(cssi_stages))
        enrollment = InternshipEnrollment(
            program_id=cssi.id, student_id=student.id, group_id=group.id,
            mentor_faculty_id=group.faculty_id,
            organization_id=ngos[index % len(ngos)].id,
            # The NGO's own contact supervises — taken from the NGO row, not
            # drawn from `rng`, so later generated values do not shift.
            industry_mentor_name=ngos[index % len(ngos)].contact_person,
            industry_mentor_phone=ngos[index % len(ngos)].phone,
            status=EnrollmentStatus.IN_PROGRESS,
            registered_at=NOW - dt.timedelta(days=38),
            start_date=cssi.start_date, end_date=cssi.end_date,
        )
        db.add(enrollment)
        db.flush()

        for position, stage in enumerate(cssi_stages):
            if position < reached - 1:
                status = StageStatus.APPROVED
            elif position == reached - 1:
                status = StageStatus.SUBMITTED if index % 3 == 0 else StageStatus.IN_PROGRESS
            else:
                status = StageStatus.PENDING
            db.add(EnrollmentStageProgress(
                enrollment_id=enrollment.id, stage_id=stage.id, status=status,
                submitted_at=(NOW - dt.timedelta(days=20 - position)
                              if status in (StageStatus.APPROVED, StageStatus.SUBMITTED)
                              else None),
                reviewed_at=(NOW - dt.timedelta(days=18 - position)
                             if status == StageStatus.APPROVED else None),
                reviewed_by_user_id=(faculty_by_code["ICT-F-101"].user_id
                                     if status == StageStatus.APPROVED else None),
            ))
        enrollment.current_stage_id = cssi_stages[min(reached - 1,
                                                      len(cssi_stages) - 1)].id

        # Proof-of-work artefacts for stages the student has already cleared.
        approved_codes = {
            stage.code for position, stage in enumerate(cssi_stages)
            if position < reached - 1
        }
        doc_plan = [
            ("PROOF_OF_WORK", DocumentType.PHOTO, FileCategory.PHOTO,
             "Field visit photograph", True),
            ("CERTIFICATE", DocumentType.CERTIFICATE, FileCategory.CERTIFICATE,
             "NGO completion certificate", False),
            ("POSTER", DocumentType.POSTER, FileCategory.POSTER,
             "Summary poster", False),
            ("PRESENTATION", DocumentType.PRESENTATION, FileCategory.OTHER,
             "Final presentation", False),
        ]
        stage_by_code = {stage.code: stage for stage in cssi_stages}
        for code, doc_type, category, title, image in doc_plan:
            if code not in approved_codes:
                continue
            stored = store_demo_file(
                db, name=f"{student.roll_number} {title}", category=category,
                uploader_id=student.user_id, image=image,
            )
            # Vary the review state so every status is represented in the demo.
            status = [
                SubmissionStatus.VERIFIED, SubmissionStatus.VERIFIED,
                SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW,
                SubmissionStatus.REJECTED,
            ][(index + len(code)) % 5]
            reviewed = status in (SubmissionStatus.VERIFIED,
                                  SubmissionStatus.REJECTED)
            db.add(InternshipDocument(
                enrollment_id=enrollment.id,
                stage_id=stage_by_code[code].id, document_type=doc_type,
                title=title, file_id=stored.id,
                uploaded_by_user_id=student.user_id,
                week_number=None, status=status,
                submitted_at=NOW - dt.timedelta(days=12),
                reviewed_by_user_id=(group.faculty_id and
                                     faculty_by_code["ICT-F-101"].user_id)
                if reviewed else None,
                reviewed_at=NOW - dt.timedelta(days=9) if reviewed else None,
                review_comment=("Clear evidence, accepted."
                                if status is SubmissionStatus.VERIFIED
                                else "Scanned copy is unreadable — please "
                                     "re-upload a clearer PDF."
                                if status is SubmissionStatus.REJECTED else None),
            ))

        ngo = ngos[index % len(ngos)]
        db.add(InternshipProject(
            enrollment_id=enrollment.id,
            title=f"{ngo.field_of_work} outreach with {ngo.name}",
            problem_statement=(
                f"{ngo.name} lacks a reliable way to track the reach of its "
                f"{ngo.field_of_work.lower()} programme across {ngo.city}, which makes "
                "it difficult to demonstrate impact to funders."
            ),
            approach=(
                "Ran a structured survey with beneficiaries and volunteers, digitised "
                "three years of paper records into a spreadsheet, and produced a "
                "monthly reporting template the staff can maintain without technical "
                "help."
            ),
            outcomes="A working record-keeping template and a summary report handed "
                     "over to the organisation.",
            beneficiaries=f"Approximately {rng.randint(40, 220)} community members.",
        ))

    log("Summer Internship enrolments…")
    summer_stages = list(db.scalars(
        select(InternshipStage).where(InternshipStage.program_id == summer.id)
        .order_by(InternshipStage.sequence)
    ))
    summer_criteria = list(db.scalars(
        select(EvaluationCriteria).where(EvaluationCriteria.program_id == summer.id)
        .order_by(EvaluationCriteria.sequence)
    ))
    summer_students = [s for s in students if s.current_semester >= 6]
    # Only faculty holding a Summer Internship *Mentor* grant take mentees. The
    # Summer coordinator (ICT-F-102) is not among them, so "SI Students" stays a
    # mentor screen rather than something every coordinator inherits.
    mentors = [faculty_by_code[c]
               for c in D.mentors_for("SUMMER_INTERNSHIP", "ICT")]
    # Consecutive roll numbers share a mentor, in blocks no larger than the
    # programme's cap — exactly what the coordinator's roll-number run produces.
    summer_students = sorted(summer_students, key=lambda s: s.roll_number)
    sizes = internship_engine.split_by_roll(
        len(summer_students), len(mentors), internship_engine.mentor_capacity(summer))
    mentor_by_position = [m for m, n in zip(mentors, sizes) for _ in range(n)]
    # With PDEU's real ICT roster, the unconfirmed 10-per-mentor cap cannot seat
    # two generated cohorts. The rest are left registered and *awaiting a
    # mentor* — the coordinator's screen then shows the shortfall honestly
    # instead of the seed inventing faculty to hide it.
    for index, student in enumerate(summer_students):
        mentor = mentor_by_position[index] if index < len(mentor_by_position) else None
        company = companies[index % len(companies)]
        reached = min(3 + (index % 6), len(summer_stages))
        completed = index == 0  # one fully-evaluated record so the UI shows a finished flow

        enrollment = InternshipEnrollment(
            program_id=summer.id, student_id=student.id,
            mentor_faculty_id=mentor.id if mentor else None, organization_id=company.id,
            status=(EnrollmentStatus.REGISTERED if mentor is None
                    else EnrollmentStatus.COMPLETED if completed
                    else EnrollmentStatus.IN_PROGRESS),
            registered_at=NOW - dt.timedelta(days=50),
            start_date=summer.start_date, end_date=summer.end_date,
            location=f"{company.city}, {company.state}",
            stipend=rng.choice([0, 15000, 25000, 35000]),
            industry_mentor_name=rng.choice(["Nikhil Raghavan", "Sara Qureshi",
                                             "Vikram Balan", "Latika Menon"]),
            industry_mentor_email=f"mentor@{slugify(company.name)}.example.com",
            industry_mentor_designation=rng.choice(["Senior Engineer", "Team Lead",
                                                    "Principal Researcher"]),
            industry_mentor_feedback=(
                "Consistent, took ownership of the assigned module and communicated "
                "blockers early." if index % 2 == 0 else None
            ),
        )
        db.add(enrollment)
        db.flush()
        if mentor is None:
            # Registered, nothing else: no mentor has reviewed or marked anything.
            internship_engine.initialise_stage_progress(db, enrollment=enrollment, program=summer)
            continue

        for position, stage in enumerate(summer_stages):
            if completed or position < reached - 1:
                status = StageStatus.APPROVED
            elif position == reached - 1:
                status = StageStatus.SUBMITTED if index % 2 else StageStatus.IN_PROGRESS
            else:
                status = StageStatus.PENDING
            db.add(EnrollmentStageProgress(
                enrollment_id=enrollment.id, stage_id=stage.id, status=status,
                submitted_at=(NOW - dt.timedelta(days=25 - position)
                              if status in (StageStatus.APPROVED, StageStatus.SUBMITTED)
                              else None),
                reviewed_at=(NOW - dt.timedelta(days=23 - position)
                             if status == StageStatus.APPROVED else None),
            ))
        if not completed:
            enrollment.current_stage_id = summer_stages[
                min(reached - 1, len(summer_stages) - 1)
            ].id

        summer_docs = [
            ("OFFER_LETTER", DocumentType.OFFER_LETTER, FileCategory.OFFER_LETTER,
             "Offer letter"),
            ("FINAL_REPORT", DocumentType.REPORT, FileCategory.REPORT,
             "Final internship report"),
            ("CERTIFICATE", DocumentType.CERTIFICATE, FileCategory.CERTIFICATE,
             "Completion certificate"),
        ]
        summer_stage_by_code = {stage.code: stage for stage in summer_stages}
        cleared = {
            stage.code for position, stage in enumerate(summer_stages)
            if completed or position < reached - 1
        }
        for code, doc_type, category, title in summer_docs:
            if code not in cleared:
                continue
            stored = store_demo_file(
                db, name=f"{student.roll_number} {title}", category=category,
                uploader_id=student.user_id,
            )
            status = (SubmissionStatus.VERIFIED if completed
                      else [SubmissionStatus.VERIFIED, SubmissionStatus.SUBMITTED,
                            SubmissionStatus.UNDER_REVIEW,
                            SubmissionStatus.REJECTED][(index + len(code)) % 4])
            reviewed = status in (SubmissionStatus.VERIFIED,
                                  SubmissionStatus.REJECTED)
            db.add(InternshipDocument(
                enrollment_id=enrollment.id,
                stage_id=summer_stage_by_code[code].id, document_type=doc_type,
                title=title, file_id=stored.id,
                uploaded_by_user_id=student.user_id,
                status=status, submitted_at=NOW - dt.timedelta(days=16),
                reviewed_by_user_id=mentor.user_id if reviewed else None,
                reviewed_at=NOW - dt.timedelta(days=13) if reviewed else None,
                review_comment=("Accepted."
                                if status is SubmissionStatus.VERIFIED
                                else "Missing the organisation's letterhead — "
                                     "please resubmit."
                                if status is SubmissionStatus.REJECTED else None),
            ))

        db.add(InternshipProject(
            enrollment_id=enrollment.id,
            title=f"{company.field_of_work} project at {company.name}",
            problem_statement=f"Improve throughput of the {company.field_of_work.lower()} "
                              "pipeline currently limited by manual steps.",
            approach="Profiled the existing pipeline, replaced the manual stage with an "
                     "automated job, and added regression checks.",
            technologies="Python, PostgreSQL, Docker",
        ))

        # Weekly reports — a realistic partial submission history.
        weeks_done = 8 if completed else max(1, reached - 2)
        # Deliberately skip a middle week for some students so the profile shows
        # a NOT_SUBMITTED gap holding the reporting stage open.
        skipped_week = None if completed else (3 if index % 3 == 1 else None)
        for week in range(1, weeks_done + 1):
            if week == skipped_week:
                continue
            period_start = summer.start_date + dt.timedelta(days=(week - 1) * 7)
            approved = completed or week < weeks_done
            db.add(InternshipReport(
                enrollment_id=enrollment.id, report_type=ReportType.WEEKLY,
                sequence_number=week, title=f"Week {week} report",
                period_start=period_start,
                period_end=period_start + dt.timedelta(days=6),
                summary=f"Week {week}: worked on the assigned module, attended the "
                        "team stand-up and reviewed the previous week's feedback.",
                tasks_completed="Implemented the assigned tickets and wrote unit tests.",
                challenges=("Environment setup took longer than expected."
                            if week == 1 else "No significant blockers."),
                next_plan="Continue with the next milestone.",
                hours_spent=rng.randint(30, 45),
                status=(SubmissionStatus.VERIFIED if approved
                        else SubmissionStatus.SUBMITTED),
                submitted_at=NOW - dt.timedelta(days=(weeks_done - week + 1) * 7),
                reviewed_at=(NOW - dt.timedelta(days=(weeks_done - week) * 7 + 2)
                             if approved else None),
                reviewed_by_user_id=mentor.user_id if approved else None,
                feedback="Clear and on schedule." if approved else None,
            ))

        if completed:
            evaluation = InternshipEvaluation(
                enrollment_id=enrollment.id, evaluator_user_id=mentor.user_id,
                evaluator_role=EvaluatorRole.FACULTY_MENTOR, evaluation_round=1,
                status=EvaluationStatus.FINALISED, is_absent=False,
                comments="Strong technical contribution and consistent reporting "
                         "throughout the internship period.",
                submitted_at=NOW - dt.timedelta(days=3),
            )
            db.add(evaluation)
            db.flush()
            total = 0.0
            maximum = 0.0
            for criterion in summer_criteria:
                marks = round(float(criterion.max_marks) * rng.uniform(0.72, 0.94), 1)
                db.add(EvaluationScore(evaluation_id=evaluation.id,
                                       criteria_id=criterion.id, marks=marks))
                total += marks * float(criterion.weight)
                maximum += float(criterion.max_marks) * float(criterion.weight)
            evaluation.total_marks = round(total, 2)
            evaluation.max_marks = round(maximum, 2)
            enrollment.final_marks = evaluation.total_marks
            # No letter grade is derived — grade boundaries are not yet supplied.
    db.flush()


def seed_academic_activity(db, components, offerings, courses, students, elective_types,
                           minors, faculty_by_code, admin_user) -> None:
    log("Elective preferences and allocations…")
    sem6 = [s for s in students if s.current_semester == 6]
    sem7 = [s for s in students if s.current_semester == 7]
    sem4 = [s for s in students if s.current_semester == 4]

    def submit_preferences(cohort, component, pool, *, days_ago, weights=None):
        """Give every student a ranked list, skewed so demand is uneven.

        Uneven demand is the point: some courses clear the 40 minimum and need
        several sections, others fall short and cannot run.
        """
        for index, student in enumerate(cohort):
            ranked = (rng.choices(pool, weights=weights, k=len(pool))
                      if weights else list(pool))
            picks, seen = [], set()
            for offering in ranked:
                if offering.id not in seen:
                    seen.add(offering.id)
                    picks.append(offering)
                if len(picks) == 3:
                    break
            while len(picks) < 3:
                extra = rng.choice(pool)
                if extra.id not in seen:
                    seen.add(extra.id)
                    picks.append(extra)
            for order, offering in enumerate(picks, 1):
                db.add(ElectivePreference(
                    student_id=student.id, curriculum_component_id=component.id,
                    course_offering_id=offering.id, preference_order=order,
                    status=PreferenceStatus.SUBMITTED,
                    submitted_at=NOW - dt.timedelta(days=days_ago,
                                                    minutes=index),
                ))

    # ── Sem VI Open Elective 3 ────────────────────────────────────────────
    # Weighted so the two most popular courses draw well past 75 (forcing extra
    # sections) while the least popular falls under 40 and cannot run.
    oe3_pool = offerings["OE3"]
    oe3_weights = [40, 30, 14, 8, 4, 3, 1][:len(oe3_pool)]
    submit_preferences(sem6, components["OE3"], oe3_pool, days_ago=12,
                       weights=oe3_weights)

    # ── Sem VI Program Elective 2 ─────────────────────────────────────────
    # Core electives combine divisions, so demand concentrates on a few tracks.
    pce2_pool = offerings["PE2"]
    pce2_weights = [30, 22, 16, 12, 8, 5, 3, 2, 1, 1, 1, 1][:len(pce2_pool)]
    submit_preferences(sem6, components["PE2"], pce2_pool, days_ago=9,
                       weights=pce2_weights)

    # ── Sem VII: already allocated, with sections formed ──────────────────
    for component_code in ("OE4", "PE4"):
        component = components[component_code]
        pool = offerings[component_code]
        weights = [35, 25, 20, 12, 8, 5, 3, 2, 1, 1, 1, 1][:len(pool)]
        for student in sem7:
            offering = rng.choices(pool, weights=weights, k=1)[0]
            db.add(ElectiveAllocation(
                student_id=student.id, curriculum_component_id=component.id,
                course_offering_id=offering.id, status=AllocationStatus.CONFIRMED,
                allocation_round=1, strategy="preference_order",
                preference_order_granted=rng.randint(1, 2),
                allocated_by_user_id=admin_user.id,
                allocated_at=NOW - dt.timedelta(days=40),
            ))
            offering.seats_filled += 1

    # ── Sem IV Open Elective 1: preferences in, allocation not yet run ────
    submit_preferences(sem4[:-1], components["OE1"], offerings["OE1"],
                       days_ago=4,
                       weights=[35, 28, 18, 10, 6, 3][:len(offerings["OE1"])])
    db.flush()

    log("Forming class sections for allocated courses…")
    for component_code in ("OE4", "PE4"):
        for offering in offerings[component_code]:
            report = sections.assess(db, offering)
            if report.runs:
                sections.distribute(db, offering, actor=admin_user)
    db.flush()

    log("NPTEL registrations…")
    nptel_component = components["OE2-MOOC"]
    mooc_offerings = offerings["OE2-MOOC"]
    for index, student in enumerate(sem6 + sem7):
        offering = mooc_offerings[index % len(mooc_offerings)]
        stage = index % 4
        status = [MoocStatus.REGISTERED, MoocStatus.EXAM_SCHEDULED,
                  MoocStatus.CERTIFICATE_UPLOADED, MoocStatus.COMPLETED][stage]
        verification = {
            MoocStatus.COMPLETED: VerificationStatus.VERIFIED,
            MoocStatus.CERTIFICATE_UPLOADED: VerificationStatus.PENDING,
        }.get(status, VerificationStatus.PENDING)
        db.add(MoocRegistration(
            student_id=student.id, course_offering_id=offering.id,
            curriculum_component_id=nptel_component.id,
            platform=offering.course.platform or MoocPlatform.NPTEL,
            platform_registration_id=f"NPTEL25CS{rng.randint(100000, 999999)}",
            course_url=offering.course.provider_url, status=status,
            exam_date=(TODAY + dt.timedelta(days=21)
                       if status != MoocStatus.REGISTERED else None),
            exam_city="Ahmedabad" if status != MoocStatus.REGISTERED else None,
            exam_fee_paid=status != MoocStatus.REGISTERED,
            exam_fee_reference=(f"TXN{rng.randint(10**9, 10**10 - 1)}"
                                if status != MoocStatus.REGISTERED else None),
            verification_status=verification,
            verified_at=(NOW - dt.timedelta(days=6)
                         if verification == VerificationStatus.VERIFIED else None),
            verified_by_user_id=(faculty_by_code["ICT-F-105"].user_id
                                 if verification == VerificationStatus.VERIFIED else None),
            final_score=(round(rng.uniform(62, 92), 1)
                         if status == MoocStatus.COMPLETED else None),
        ))
        offering.seats_filled += 1
    db.flush()

    log("Minor applications and enrolments…")
    eligible = [s for s in students if s.current_semester >= 3
                and s.cpi is not None and float(s.cpi) >= 7.0]
    minor_list = list(minors.values())
    if not minor_list:
        db.flush()
        return

    # One minor is deliberately over-subscribed so a coordinator can see a real
    # cut-off when running an allocation round: more applicants than seats.
    contested = minor_list[0]
    # Applications are made in Semester III, so the open round's applicants are
    # the Semester III cohort; the students already holding a seat applied when
    # they were in Semester III and have moved on since.
    contenders = [s for s in eligible if s.current_semester == 3
                  and s.department_id != contested.department_id]
    contenders = contenders[: contested.capacity + 18]

    for index, student in enumerate(contenders):
        db.add(MinorApplication(
            student_id=student.id, minor_program_id=contested.id,
            academic_year_id=contested.academic_year_id, preference_order=1,
            status=MinorApplicationStatus.SUBMITTED,
            cpi_at_application=student.cpi,
            backlogs_at_application=student.backlog_count,
            semester_at_application=student.current_semester,
            motivation="I want to broaden my technical base beyond my own "
                       "department and apply these skills in my final-year project.",
            submitted_at=NOW - dt.timedelta(days=12, minutes=index * 37),
        ))

    # A handful of already-settled records on the other minors, so the student
    # view shows an active enrolment as well as pending preferences.
    named = {roll for _n, roll, *_ in D.NAMED_STUDENTS}
    settled = [s for s in eligible if s not in contenders and s.current_semester >= 4
               and s.roll_number not in named][:6]
    for index, student in enumerate(settled):
        choices = [m for m in minor_list[1:] if m.department_id != student.department_id]
        if not choices:
            continue
        picks = rng.sample(choices, min(2, len(choices)))
        for order, minor in enumerate(picks, 1):
            allocated = index < 2 and order == 1
            application = MinorApplication(
                student_id=student.id, minor_program_id=minor.id,
                academic_year_id=minor.academic_year_id, preference_order=order,
                status=(MinorApplicationStatus.ALLOCATED if allocated
                        else MinorApplicationStatus.SUBMITTED),
                cpi_at_application=student.cpi,
                backlogs_at_application=student.backlog_count,
                semester_at_application=3,
                motivation="I want to broaden my technical base beyond ICT and apply "
                           "these skills in my final-year project.",
                submitted_at=NOW - dt.timedelta(days=10 - index),
                decided_at=NOW - dt.timedelta(days=4) if allocated else None,
                reviewed_by_user_id=admin_user.id if allocated else None,
            )
            db.add(application)
            db.flush()
            if allocated:
                minor.seats_filled += 1
                enrollment = MinorEnrollment(
                    student_id=student.id, minor_program_id=minor.id,
                    application_id=application.id, status=MinorEnrollmentStatus.ACTIVE,
                    started_semester=3,
                )
                db.add(enrollment)
                db.flush()
                seed_minor_results(db, enrollment, student, rng)

    # Seats that show the minor as a programme. Ananya Menon (a demo sign-in)
    # applied in Semester III and is now in Semester IV; a generated CSE
    # student does the same in ICT's own IoT minor, so its coordinator has a
    # student to grade and to record fees for.
    ananya = next((s for s in students if s.roll_number == "23BIT911"), None)
    iot = minors.get("MIN-IOT")
    # `students` is the ICT cohort; the IoT minor is ICT's, so its student
    # comes from another department.
    cse_student = db.scalar(select(Student).where(
        Student.department_id != iot.department_id, Student.current_semester == 4,
        Student.cpi >= 7.5, Student.backlog_count == 0).order_by(Student.roll_number)
    ) if iot else None
    for student, minor in ((ananya, minors.get("MIN-CDS")), (cse_student, iot)):
        if student is None or minor is None or minor.department_id == student.department_id:
            continue
        application = MinorApplication(
            student_id=student.id, minor_program_id=minor.id, academic_year_id=minor.academic_year_id,
            preference_order=1, status=MinorApplicationStatus.ALLOCATED,
            cpi_at_application=student.cpi, backlogs_at_application=student.backlog_count,
            semester_at_application=3, submitted_at=NOW - dt.timedelta(days=150),
            decided_at=NOW - dt.timedelta(days=140), reviewed_by_user_id=admin_user.id,
            motivation="To add a second specialisation alongside my programme.")
        db.add(application)
        db.flush()
        minor.seats_filled += 1
        enrollment = MinorEnrollment(student_id=student.id, minor_program_id=minor.id,
                                     application_id=application.id,
                                     status=MinorEnrollmentStatus.ACTIVE, started_semester=3)
        db.add(enrollment)
        db.flush()
        seed_minor_results(db, enrollment, student, rng)
    db.flush()


#: Fictional results for demo students: a grade for every course of a finished
#: semester, and this semester's courses still in progress.
DEMO_GRADES = [("A", 84), ("B+", 76), ("A+", 91), ("B", 68)]


def seed_minor_results(db, enrollment, student, rng) -> None:
    from app.services import minor_portal

    program = enrollment.minor_program
    for course in program.courses:
        sem = minor_portal.course_semester(program, course)
        if sem > student.current_semester:
            continue
        if sem == student.current_semester:
            db.add(MinorCourseResult(enrollment_id=enrollment.id, minor_course_id=course.id,
                                     status=MinorCourseResultStatus.IN_PROGRESS))
            continue
        grade, marks = rng.choice(DEMO_GRADES)
        db.add(MinorCourseResult(enrollment_id=enrollment.id, minor_course_id=course.id,
                                 grade=grade, marks=marks, status=MinorCourseResultStatus.PASSED,
                                 recorded_at=NOW - dt.timedelta(days=60)))
    db.flush()
    db.refresh(enrollment)
    minor_portal._recount(db, enrollment)


def seed_community(db, students, faculty_by_code, club_admin_user) -> None:
    log("Clubs, memberships and events…")
    advisors = list(faculty_by_code.values())
    clubs: dict[str, Club] = {}
    for index, (name, category, description, tagline, instagram, founded) in enumerate(
        D.CLUBS
    ):
        club = Club(
            name=name, slug=slugify(name), category=ClubCategory(category),
            tagline=tagline, description=(
                f"{description}. {name} runs workshops, competitions and open sessions "
                "through the academic year and welcomes members from every department."
            ),
            instagram_url=instagram, email=f"{slugify(name)}@campushub.example.com",
            faculty_advisor_id=advisors[index % len(advisors)].id,
            founded_year=founded, is_active=True,
        )
        db.add(club)
        db.flush()
        clubs[name] = club

    for index, student in enumerate(students):
        for club in rng.sample(list(clubs.values()), rng.randint(1, 3)):
            if db.scalar(select(ClubMember).where(
                ClubMember.club_id == club.id, ClubMember.student_id == student.id
            )):
                continue
            role = ClubMemberRole.MEMBER
            if index % 6 == 0:
                role = ClubMemberRole.CORE
            db.add(ClubMember(
                club_id=club.id, student_id=student.id, role=role,
                joined_at=NOW - dt.timedelta(days=rng.randint(60, 400)),
                position_title="Core Team" if role is ClubMemberRole.CORE else None,
            ))
    db.flush()
    # One head per club, drawn from existing members.
    for club in clubs.values():
        member = db.scalar(select(ClubMember).where(ClubMember.club_id == club.id)
                           .limit(1))
        if member:
            member.role = ClubMemberRole.HEAD
            member.position_title = "Club Head"
    db.flush()

    events: list[Event] = []
    for title, club_name, etype, offset, venue, capacity, speaker, summary in D.EVENTS:
        start = NOW + dt.timedelta(days=offset, hours=rng.choice([1, 3, 5]))
        status = EventStatus.COMPLETED if offset < 0 else EventStatus.PUBLISHED
        event = Event(
            club_id=clubs[club_name].id, title=title, slug=slugify(title),
            event_type=EventType(etype), summary=summary,
            description=(
                f"{summary}\n\nOrganised by {club_name}. Registration closes 24 hours "
                "before the session begins. Bring your student ID; laptops are required "
                "for hands-on sessions."
            ),
            start_at=start, end_at=start + dt.timedelta(hours=rng.choice([2, 3, 4])),
            venue=venue, mode=EventMode.OFFLINE, registration_required=True,
            registration_deadline=start - dt.timedelta(days=1), capacity=capacity,
            speaker=speaker, tags=[etype.title(), club_name],
            status=status, created_by_user_id=club_admin_user.id,
            published_at=NOW - dt.timedelta(days=rng.randint(2, 20)),
        )
        db.add(event)
        db.flush()
        events.append(event)

    for event in events:
        for student in rng.sample(students, rng.randint(3, min(9, len(students)))):
            db.add(EventRegistration(
                event_id=event.id, student_id=student.id,
                status=(RegistrationStatus.ATTENDED
                        if event.status is EventStatus.COMPLETED
                        else RegistrationStatus.REGISTERED),
                registered_at=NOW - dt.timedelta(days=rng.randint(1, 10)),
            ))
        for student in rng.sample(students, rng.randint(2, min(7, len(students)))):
            if db.scalar(select(EventInterest).where(
                EventInterest.event_id == event.id,
                EventInterest.student_id == student.id
            )):
                continue
            db.add(EventInterest(event_id=event.id, student_id=student.id,
                                 is_interested=True))
    db.flush()


def seed_engagement(db, students, faculty_by_code, admin_user, departments) -> None:
    log("Announcements, meetings and notifications…")
    program_ids = dict(db.execute(select(InternshipProgram.code, InternshipProgram.id)).all())
    for title, body, category, priority, audience, pinned, ref in D.ANNOUNCEMENTS:
        db.add(Announcement(
            title=title, body=body, category=AnnouncementCategory(category),
            priority=Priority(priority), audience_type=AudienceType(audience),
            audience_ref_id=program_ids[ref] if isinstance(ref, str) else ref,
            published_by_user_id=admin_user.id,
            published_at=NOW - dt.timedelta(days=rng.randint(1, 14)),
            expires_at=NOW + dt.timedelta(days=45), is_pinned=pinned,
            is_published=True,
        ))
    db.add(Announcement(
        title="Mentor meeting slots for this fortnight",
        body="I am available on Tuesday and Thursday afternoons for mentee meetings. "
             "Please raise a meeting request through the portal with a short agenda so "
             "I can prepare.",
        category=AnnouncementCategory.MENTORSHIP, priority=Priority.NORMAL,
        audience_type=AudienceType.MENTEES,
        audience_ref_id=faculty_by_code["ICT-F-101"].id,
        published_by_user_id=faculty_by_code["ICT-F-101"].user_id,
        published_at=NOW - dt.timedelta(days=2), is_published=True,
    ))
    db.flush()

    assignments = list(db.scalars(select(MentorAssignment)))
    meeting_titles = [
        ("Semester VI elective guidance", "Which specialisation track fits a career in "
                                          "machine learning?"),
        ("Internship progress check-in", "Review of the last two weekly reports and "
                                         "the plan for the final report."),
        ("Backlog clearance plan", "Discuss a study plan for the pending subject."),
        ("Minor application advice", "Whether to apply for the AI or Robotics minor."),
    ]
    for index, assignment in enumerate(assignments[:8]):
        title, agenda = meeting_titles[index % len(meeting_titles)]
        status = [MeetingStatus.REQUESTED, MeetingStatus.APPROVED,
                  MeetingStatus.COMPLETED, MeetingStatus.APPROVED][index % 4]
        scheduled = (NOW + dt.timedelta(days=rng.randint(1, 9), hours=2)
                     if status in (MeetingStatus.APPROVED, MeetingStatus.COMPLETED)
                     else None)
        if status is MeetingStatus.COMPLETED:
            scheduled = NOW - dt.timedelta(days=rng.randint(2, 12))
        db.add(MentorMeeting(
            student_id=assignment.student_id, faculty_id=assignment.faculty_id,
            requested_by_user_id=assignment.student.user_id, title=title, agenda=agenda,
            requested_at=NOW - dt.timedelta(days=rng.randint(1, 15)),
            proposed_slot=NOW + dt.timedelta(days=rng.randint(2, 10)),
            scheduled_at=scheduled, duration_minutes=30, mode=MeetingMode.IN_PERSON,
            location=assignment.faculty.cabin, status=status,
            outcome_notes=("Agreed on a weekly check-in until the end of the semester."
                           if status is MeetingStatus.COMPLETED else None),
            thread_key=f"mentor:{assignment.faculty_id}:student:{assignment.student_id}",
        ))
    db.flush()

    # A notification is a claim about one student, so each goes only to the
    # students it is true of. Sending all three to everyone told a first-year
    # that "Open Elective 3 closes in 5 days" and that a mentor had approved an
    # internship stage they are years away from.
    furthest_approved_stage: dict[int, str] = {}
    for student_id, stage_name in db.execute(
        select(InternshipEnrollment.student_id, InternshipStage.name)
        .join(EnrollmentStageProgress,
              EnrollmentStageProgress.enrollment_id == InternshipEnrollment.id)
        .join(InternshipStage, InternshipStage.id == EnrollmentStageProgress.stage_id)
        .where(EnrollmentStageProgress.status == StageStatus.APPROVED)
        .order_by(InternshipStage.sequence)
    ):
        furthest_approved_stage[student_id] = stage_name

    for student in students:
        specs = [(NotificationType.EVENT_ANNOUNCEMENT, "New event: HackTheCampus 2.0",
                  "Registrations are open. 150 seats.", "/events", Priority.NORMAL, False)]
        # Open Elective 3 is a Semester VI slot in both ICT schemes.
        if student.current_semester == 6:
            specs.insert(0, (
                NotificationType.ELECTIVE_DEADLINE, "Open Elective 3 closes in 5 days",
                "Submit your ranked preferences before the window closes.",
                "/academics/open-electives", Priority.HIGH, False))
        stage_name = furthest_approved_stage.get(student.id)
        if stage_name:
            specs.append((
                NotificationType.INTERNSHIP_STAGE, "Internship stage approved",
                f"Your faculty mentor approved the {stage_name} stage.",
                "/internships", Priority.NORMAL, True))
        for ntype, title, message, link, priority, is_read in specs:
            db.add(Notification(
                user_id=student.user_id, type=ntype, title=title, message=message,
                link=link, priority=priority, is_read=is_read,
                read_at=NOW - dt.timedelta(days=1) if is_read else None,
            ))
    for faculty in faculty_by_code.values():
        db.add(Notification(
            user_id=faculty.user_id, type=NotificationType.INTERNSHIP_SUBMISSION,
            title="Submissions awaiting your review",
            message="Some of your assigned students have submitted internship stages.",
            link="/internships/my-students", priority=Priority.NORMAL,
        ))
    db.add(Notification(
        user_id=admin_user.id, type=NotificationType.SYSTEM,
        title="Demo data loaded",
        message="CampusHub Phase 1 demo dataset seeded successfully.",
        link="/admin", priority=Priority.NORMAL,
    ))
    db.flush()

    log("Audit trail…")
    audit_specs = [
        (AuditAction.ALLOCATION_RUN, "curriculum_component",
         "Ran 'preference_order' allocation for OE3"),
        (AuditAction.MENTOR_ASSIGN, "mentor_assignment",
         "Assigned faculty mentors for the 2025-26 academic year"),
        (AuditAction.PUBLISH, "announcement",
         "Published 'Open Elective preference window is now open'"),
        (AuditAction.CREATE, "internship_program",
         "Created internship programme CSSI-2025"),
        (AuditAction.EVALUATION_SUBMIT, "internship_evaluation",
         "Summer Internship evaluation finalised"),
        (AuditAction.UPDATE, "minor_program",
         "Updated seat capacity for Minor in Artificial Intelligence"),
    ]
    for index, (action, entity, description) in enumerate(audit_specs):
        db.add(AuditLog(
            actor_user_id=admin_user.id,
            actor_label=f"{admin_user.full_name} <{admin_user.email}>",
            action=action, entity_type=entity, entity_id=index + 1,
            description=description, meta={"seeded": True}, ip_address="127.0.0.1",
            created_at=NOW - dt.timedelta(days=index, hours=index * 2),
        ))
    db.flush()


def print_credentials(db: Session) -> None:
    print("\n" + "=" * 74)
    print("  CampusHub demo accounts — password for every account:", PASSWORD)
    print("=" * 74)
    rows = [
        ("SUPER_ADMIN", "admin@campushub.example.com", "Full system administration"),
        ("DEPARTMENT_ADMIN (ICT office)", "ict.office@campushub.example.com",
         "ICT data administration · cannot appoint"),
        ("COORDINATOR — Open Electives", "vikram.joshi@campushub.example.com",
         "Runs Open Elective rounds, ICT only"),
        ("COORDINATOR — Core Electives", "leena.nambiar@campushub.example.com",
         "Runs Core Elective rounds, ICT only"),
        ("COORDINATOR — Summer (ICT)", "priya.nair@campushub.example.com",
         "Summer Internship coordinator, ICT only"),
        ("COORDINATOR — CSSI (ICT)", "sneha.iyer@campushub.example.com",
         "CSSI coordinator, ICT only"),
        ("COORDINATOR — NPTEL (ICT)", "meera.krishnan@campushub.example.com",
         "Approves NPTEL certificates for ICT"),
        ("COORDINATOR — Summer (CSE)", "kunal.shah@campushub.example.com",
         "Same domain, different department"),
        ("FACULTY (mentor only)", "anand.mehta@campushub.example.com",
         "Mentor · CSSI Group 1 · no coordination"),
        ("CLUB_ADMIN", "clubs@campushub.example.com", "Clubs and events management"),
    ]
    for sem in range(1, 9):
        st = db.scalar(select(Student).where(Student.current_semester == sem).order_by(Student.roll_number))
        if st:
            rows.append((f"STUDENT (Sem {sem})", st.user.email,
                         f"{st.roll_number} · Semester {st.current_semester}"))
    for role, email, note in rows:
        print(f"  {role:<34} {email:<44} {note}")
    print("=" * 74 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed CampusHub demo data.")
    parser.add_argument("--reset", action="store_true",
                        help="Drop and recreate all tables before seeding.")
    parser.add_argument("--force", action="store_true",
                        help="Seed even if data already exists (may duplicate).")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reset:
            reset(db)
        elif already_seeded(db) and not args.force:
            print("Database already contains data — nothing to do. "
                  "Use --reset to rebuild the demo dataset.")
            print_credentials(db)
            return 0

        print("Seeding CampusHub demo data…")
        seed(db)
        print("Done.")
        print_credentials(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
