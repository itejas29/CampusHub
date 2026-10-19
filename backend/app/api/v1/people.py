"""Students, faculty and departments — directory + administration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.rbac import P
from app.core.security import hash_password
from app.models.academics import Program
from app.models.engagement import MentorAssignment
from app.models.enums import AuditAction, Role, StudentStatus
from app.models.identity import AcademicYear, Department, Faculty, Semester, Student, User, UserRole
from app.schemas.common import Message, Page
from app.schemas.identity import (
    AcademicYearOut, DepartmentCreate, DepartmentHodUpdate, DepartmentOut,
    DepartmentUpdate, FacultyCreate,
    FacultyOut, FacultyUpdate, ProfileUpdate, SemesterOut, StudentCreate, StudentDetail,
    StudentOut, StudentUpdate, TemporaryPassword,
)
from app.services import accounts, audit, scope
from app.services.serializers import faculty_out, student_out

def _assert_manages_department(db, user: User, department_id: int | None) -> None:
    """Student and faculty records are managed department by department.

    `students:manage` and `faculty:manage` are held by department offices and
    internship coordinators; neither may touch another department's people.
    The registrar may act anywhere.
    """
    if user.has_role(Role.SUPER_ADMIN):
        return
    own = db.scalar(select(Faculty.department_id).where(Faculty.user_id == user.id))
    if own is None or own != department_id:
        raise PermissionDeniedError("You can manage people in your own department only.")


def _initial_password(chosen: str | None) -> tuple[str, str | None]:
    """(password to store, temporary password to hand over once).

    Once demo accounts are switched off, a new account always starts on a
    one-time password the person must replace — the faculty form's default was
    the demo password published in the README.
    """
    if settings.DEMO_MODE:
        return chosen or settings.SEED_DEFAULT_PASSWORD, None
    temporary = accounts.temporary_password()
    return temporary, temporary


students_router = APIRouter(prefix="/students", tags=["students"])
faculty_router = APIRouter(prefix="/faculty", tags=["faculty"])
departments_router = APIRouter(prefix="/departments", tags=["departments"])
academic_router = APIRouter(prefix="/academic", tags=["academics"])
me_router = APIRouter(prefix="/me", tags=["profile"])


# ── students ──────────────────────────────────────────────────────────────
@students_router.get("", response_model=Page[StudentOut])
def list_students(
    db: DbSession, q: str | None = Query(None), department_id: int | None = None,
    program_id: int | None = None, semester: int | None = None,
    status: StudentStatus | None = None, division: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    _: User = Depends(require_permission(P["STUDENT_READ"])),
) -> Page[StudentOut]:
    stmt = select(Student).join(User, User.id == Student.user_id)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern),
                              Student.roll_number.ilike(pattern),
                              User.email.ilike(pattern)))
    if department_id:
        stmt = stmt.where(Student.department_id == department_id)
    if program_id:
        stmt = stmt.where(Student.program_id == program_id)
    if semester:
        stmt = stmt.where(Student.current_semester == semester)
    if status:
        stmt = stmt.where(Student.status == status)
    if division:
        stmt = stmt.where(Student.division == division)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Student.roll_number)
        .offset((page - 1) * page_size).limit(page_size)
    )
    return Page[StudentOut](items=[student_out(s) for s in rows], total=int(total),
                            page=page, page_size=page_size)


@students_router.get("/{student_id}", response_model=StudentDetail)
def get_student(student_id: int, db: DbSession,
                _: User = Depends(require_permission(P["STUDENT_READ"]))
                ) -> StudentDetail:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")
    assignment = db.scalar(select(MentorAssignment).where(
        MentorAssignment.student_id == student.id, MentorAssignment.is_active.is_(True)
    ))
    base = student_out(student)
    return StudentDetail(
        **base.model_dump(), date_of_birth=student.date_of_birth,
        gender=student.gender, address=student.address,
        guardian_name=student.guardian_name, guardian_phone=student.guardian_phone,
        mentor_name=assignment.faculty.user.full_name if assignment else None,
        mentor_id=assignment.faculty_id if assignment else None,
    )


@students_router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate, db: DbSession,
    user: User = Depends(require_permission(P["STUDENT_MANAGE"])),
) -> StudentOut:
    if db.scalar(select(User).where(func.lower(User.email) == payload.email.lower())):
        raise ConflictError("A user with that email address already exists.")
    if db.scalar(select(Student).where(Student.roll_number == payload.roll_number)):
        raise ConflictError("That roll number is already in use.")
    _assert_manages_department(db, user, payload.department_id)

    password, temporary = _initial_password(payload.password)
    account = User(email=payload.email.lower(),
                   hashed_password=hash_password(password),
                   full_name=payload.full_name, phone=payload.phone,
                   must_change_password=temporary is not None)
    db.add(account)
    db.flush()
    db.add(UserRole(user_id=account.id, role=Role.STUDENT))

    student = Student(
        user_id=account.id, roll_number=payload.roll_number,
        enrollment_number=payload.enrollment_number, program_id=payload.program_id,
        department_id=payload.department_id, admission_year=payload.admission_year,
        current_semester=payload.current_semester, division=payload.division,
        batch=payload.batch, cpi=payload.cpi,
    )
    db.add(student)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="student",
                 entity_id=student.id, actor=user,
                 description=f"Created student {student.roll_number}")
    db.commit()
    db.refresh(student)
    out = student_out(student)
    out.temporary_password = temporary
    return out


@students_router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int, payload: StudentUpdate, db: DbSession,
    user: User = Depends(require_permission(P["STUDENT_MANAGE"])),
) -> StudentOut:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")
    _assert_manages_department(db, user, student.department_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("full_name", "phone"):
        if field in changes:
            setattr(student.user, field, changes.pop(field))
    for field, value in changes.items():
        setattr(student, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="student",
                 entity_id=student.id, actor=user,
                 description=f"Updated student {student.roll_number}",
                 meta={"changes": list(payload.model_dump(exclude_unset=True))})
    db.commit()
    db.refresh(student)
    return student_out(student)


# ── faculty ───────────────────────────────────────────────────────────────
@faculty_router.get("", response_model=list[FacultyOut])
def list_faculty(db: DbSession, _: CurrentUser, q: str | None = Query(None),
                 department_id: int | None = None,
                 is_mentor: bool | None = None) -> list[FacultyOut]:
    """Faculty directory — readable by every authenticated user."""
    stmt = select(Faculty).join(User, User.id == Faculty.user_id).where(
        Faculty.is_active.is_(True)
    )
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern),
                              Faculty.designation.ilike(pattern),
                              Faculty.specialization.ilike(pattern)))
    if department_id:
        stmt = stmt.where(Faculty.department_id == department_id)
    if is_mentor is not None:
        stmt = stmt.where(Faculty.is_mentor.is_(is_mentor))

    rows = list(db.scalars(stmt.order_by(User.full_name)))
    counts = dict(db.execute(
        select(MentorAssignment.faculty_id, func.count(MentorAssignment.id))
        .where(MentorAssignment.is_active.is_(True))
        .group_by(MentorAssignment.faculty_id)
    ).all())
    return [faculty_out(f, mentee_count=counts.get(f.id, 0)) for f in rows]


@faculty_router.get("/{faculty_id}", response_model=FacultyOut)
def get_faculty(faculty_id: int, db: DbSession, _: CurrentUser) -> FacultyOut:
    faculty = db.get(Faculty, faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")
    count = db.scalar(select(func.count(MentorAssignment.id)).where(
        MentorAssignment.faculty_id == faculty.id, MentorAssignment.is_active.is_(True)
    )) or 0
    return faculty_out(faculty, mentee_count=int(count))


@faculty_router.post("", response_model=FacultyOut, status_code=201)
def create_faculty(
    payload: FacultyCreate, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> FacultyOut:
    if db.scalar(select(User).where(func.lower(User.email) == payload.email.lower())):
        raise ConflictError("A user with that email address already exists.")
    _assert_manages_department(db, user, payload.department_id)
    extra = [r for r in payload.extra_roles if r != Role.FACULTY]
    # Only the registrar grants a system role, and the HoD is appointed through
    # scope.set_hod alone. `faculty:manage` is held by department offices and
    # internship coordinators — this used to let either create a super admin.
    if Role.HOD in extra:
        raise PermissionDeniedError("Appoint a Head of Department from the department, not here.")
    if extra and not user.has_role(Role.SUPER_ADMIN):
        raise PermissionDeniedError("Only the registrar can give a new account extra roles.")

    password, temporary = _initial_password(payload.password)
    account = User(email=payload.email.lower(),
                   hashed_password=hash_password(password),
                   full_name=payload.full_name, must_change_password=temporary is not None)
    db.add(account)
    db.flush()
    db.add(UserRole(user_id=account.id, role=Role.FACULTY))
    for role in extra:
        db.add(UserRole(user_id=account.id, role=role))

    faculty = Faculty(
        user_id=account.id, employee_code=payload.employee_code,
        department_id=payload.department_id, designation=payload.designation,
        cabin=payload.cabin, specialization=payload.specialization,
        qualification=payload.qualification,
        public_email=payload.public_email or payload.email,
        public_phone=payload.public_phone, is_mentor=payload.is_mentor,
    )
    db.add(faculty)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="faculty",
                 entity_id=faculty.id, actor=user,
                 description=f"Created faculty {faculty.employee_code}")
    db.commit()
    db.refresh(faculty)
    out = faculty_out(faculty)
    out.temporary_password = temporary
    return out


@students_router.post("/{student_id}/reset-password", response_model=TemporaryPassword)
def reset_student_password(
    student_id: int, db: DbSession,
    user: User = Depends(require_permission(P["STUDENT_MANAGE"])),
) -> TemporaryPassword:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")
    _assert_manages_department(db, user, student.department_id)
    password = accounts.issue_temporary_password(db, student.user, actor=user)
    db.commit()
    return TemporaryPassword(temporary_password=password, login=student.user.email)


@faculty_router.post("/{faculty_id}/reset-password", response_model=TemporaryPassword)
def reset_faculty_password(
    faculty_id: int, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> TemporaryPassword:
    faculty = db.get(Faculty, faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")
    _assert_manages_department(db, user, faculty.department_id)
    password = accounts.issue_temporary_password(db, faculty.user, actor=user)
    db.commit()
    return TemporaryPassword(temporary_password=password, login=faculty.user.email)


@faculty_router.patch("/{faculty_id}", response_model=FacultyOut)

def update_faculty(
    faculty_id: int, payload: FacultyUpdate, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> FacultyOut:
    faculty = db.get(Faculty, faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")
    _assert_manages_department(db, user, faculty.department_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_mentor"):
        # The mentor flag is how the rest of the portal offers someone as a
        # mentor, so it cannot be switched back on for a Head of Department.
        scope.assert_can_mentor(db, faculty)
    if "full_name" in changes:
        faculty.user.full_name = changes.pop("full_name")
    for field, value in changes.items():
        setattr(faculty, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="faculty",
                 entity_id=faculty.id, actor=user, description="Updated faculty record")
    db.commit()
    db.refresh(faculty)
    return faculty_out(faculty)


@faculty_router.delete("/{faculty_id}", response_model=Message)
def delete_faculty(
    faculty_id: int, db: DbSession,
    user: User = Depends(require_permission(P["FACULTY_MANAGE"])),
) -> Message:
    faculty = db.get(Faculty, faculty_id)
    if faculty is None:
        raise NotFoundError("Faculty member not found.")
    _assert_manages_department(db, user, faculty.department_id)
    if not user.has_role(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN):
        raise PermissionDeniedError("Only the registrar or the department office can deactivate faculty.")
    if faculty.user_id == user.id:
        raise PermissionDeniedError("You can't deactivate your own account.")
    name = faculty.user.full_name

    code = faculty.employee_code
    faculty.user.is_active = False
    audit.record(db, action=AuditAction.DELETE, entity_type="faculty",
                 entity_id=faculty.id, actor=user, description=f"Deactivated faculty {code}")
    db.commit()
    return Message(message=f"Faculty member {name} ({code}) has been deactivated.")


# ── departments ───────────────────────────────────────────────────────────
@departments_router.get("", response_model=list[DepartmentOut])
def list_departments(db: DbSession, _: CurrentUser) -> list[DepartmentOut]:
    departments = list(db.scalars(select(Department).order_by(Department.code)))
    ids = [d.id for d in departments]
    students = dict(db.execute(
        select(Student.department_id, func.count(Student.id))
        .where(Student.department_id.in_(ids or [0]))
        .group_by(Student.department_id)
    ).all())
    faculty = dict(db.execute(
        select(Faculty.department_id, func.count(Faculty.id))
        .where(Faculty.department_id.in_(ids or [0]))
        .group_by(Faculty.department_id)
    ).all())
    programs = dict(db.execute(
        select(Program.department_id, func.count(Program.id))
        .where(Program.department_id.in_(ids or [0]))
        .group_by(Program.department_id)
    ).all())
    return [
        DepartmentOut(
            id=d.id, code=d.code, name=d.name, short_name=d.short_name,
            school=d.school, description=d.description, is_active=d.is_active,
            student_count=students.get(d.id, 0), faculty_count=faculty.get(d.id, 0),
            program_count=programs.get(d.id, 0),
            hod_faculty_id=d.hod_faculty_id, hod_name=_hod_name(db, d),
        )
        for d in departments
    ]


def _hod_name(db, department: Department) -> str | None:
    head = db.get(Faculty, department.hod_faculty_id) if department.hod_faculty_id else None
    return head.user.full_name if head else None


@departments_router.put("/{department_id}/hod", response_model=DepartmentOut)
def set_department_hod(
    department_id: int, payload: DepartmentHodUpdate, db: DbSession,
    user: User = Depends(require_permission(P["DEPARTMENT_MANAGE"])),
) -> DepartmentOut:
    """Appoint the Head of Department. The registrar's office only — an HoD
    does not appoint their own successor."""
    department = db.get(Department, department_id)
    if department is None:
        raise NotFoundError("Department not found.")
    head = None
    if payload.faculty_id is not None:
        head = db.get(Faculty, payload.faculty_id)
        if head is None:
            raise NotFoundError("Faculty member not found.")
    previous_id = department.hod_faculty_id
    scope.set_hod(db, department, head)
    audit.record(
        db, action=AuditAction.UPDATE, entity_type="department",
        entity_id=department.id, actor=user,
        description=(f"{head.user.full_name} appointed Head of {department.code}"
                     if head else f"Head of {department.code} cleared"),
        meta={"from_faculty_id": previous_id, "to_faculty_id": payload.faculty_id},
    )
    db.commit()
    db.refresh(department)
    return DepartmentOut(
        id=department.id, code=department.code, name=department.name,
        short_name=department.short_name, school=department.school,
        description=department.description, is_active=department.is_active,
        hod_faculty_id=department.hod_faculty_id, hod_name=_hod_name(db, department),
    )


@departments_router.post("", response_model=DepartmentOut, status_code=201)
def create_department(
    payload: DepartmentCreate, db: DbSession,
    user: User = Depends(require_permission(P["DEPARTMENT_MANAGE"])),
) -> DepartmentOut:
    if db.scalar(select(Department).where(Department.code == payload.code)):
        raise ConflictError("A department with that code already exists.")
    department = Department(**payload.model_dump())
    db.add(department)
    db.flush()
    audit.record(db, action=AuditAction.CREATE, entity_type="department",
                 entity_id=department.id, actor=user,
                 description=f"Created department {department.code}")
    db.commit()
    db.refresh(department)
    return DepartmentOut(id=department.id, code=department.code, name=department.name,
                         short_name=department.short_name, school=department.school,
                         description=department.description,
                         is_active=department.is_active)


@departments_router.patch("/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: int, payload: DepartmentUpdate, db: DbSession,
    user: User = Depends(require_permission(P["DEPARTMENT_MANAGE"])),
) -> DepartmentOut:
    department = db.get(Department, department_id)
    if department is None:
        raise NotFoundError("Department not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(department, field, value)
    audit.record(db, action=AuditAction.UPDATE, entity_type="department",
                 entity_id=department.id, actor=user, description="Updated department")
    db.commit()
    db.refresh(department)
    return DepartmentOut(id=department.id, code=department.code, name=department.name,
                         short_name=department.short_name, school=department.school,
                         description=department.description,
                         is_active=department.is_active)


# ── academic calendar lookups ─────────────────────────────────────────────
@academic_router.get("/years", response_model=list[AcademicYearOut])
def academic_years(db: DbSession, _: CurrentUser) -> list[AcademicYearOut]:
    return [AcademicYearOut.model_validate(y) for y in db.scalars(
        select(AcademicYear).order_by(AcademicYear.start_date.desc())
    )]


@academic_router.get("/semesters", response_model=list[SemesterOut])
def semesters(db: DbSession, _: CurrentUser,
              academic_year_id: int | None = None) -> list[SemesterOut]:
    stmt = select(Semester).order_by(Semester.number)
    if academic_year_id:
        stmt = stmt.where(Semester.academic_year_id == academic_year_id)
    return [
        SemesterOut(
            id=s.id, number=s.number, term=s.term.value,
            academic_year_id=s.academic_year_id,
            academic_year_label=s.academic_year.label if s.academic_year else None,
            start_date=s.start_date, end_date=s.end_date, is_current=s.is_current,
        )
        for s in db.scalars(stmt)
    ]


# ── own profile ───────────────────────────────────────────────────────────
@me_router.patch("/profile", response_model=Message)
def update_profile(payload: ProfileUpdate, db: DbSession,
                   user: CurrentUser) -> Message:
    changes = payload.model_dump(exclude_unset=True)
    user_fields = {"full_name", "phone"}
    student_fields = {"address", "guardian_name", "guardian_phone"}
    faculty_fields = {"cabin", "public_email", "public_phone", "specialization", "bio"}

    for field in user_fields & changes.keys():
        setattr(user, field, changes[field])

    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student:
        for field in student_fields & changes.keys():
            setattr(student, field, changes[field])

    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty:
        for field in faculty_fields & changes.keys():
            setattr(faculty, field, changes[field])

    audit.record(db, action=AuditAction.UPDATE, entity_type="user", entity_id=user.id,
                 actor=user, description="Updated own profile",
                 meta={"fields": sorted(changes)})
    db.commit()
    return Message(message="Profile updated.")
