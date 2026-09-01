from __future__ import annotations

import datetime as dt

import jwt
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, request_context
from app.core.errors import AuthenticationError
from app.core.rbac import permissions_for
from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password,
    verify_password,
)
from app.models.enums import AssignedRole, AuditAction
from app.models.identity import AcademicYear, Faculty, Semester, Student, User
from app.schemas.auth import (
    AuthResponse, ChangePasswordRequest, CoordinationOut,
    CurrentUser as CurrentUserOut, FacultyContext, LoginRequest, RefreshRequest,
    StudentContext, TokenPair,
)
from app.schemas.common import Message
from app.services import audit, scope

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenPair:
    roles = [r.value for r in user.roles]
    return TokenPair(
        access_token=create_access_token(user.id, roles),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def build_current_user(db, user: User) -> CurrentUserOut:
    student_ctx = faculty_ctx = None

    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student:
        student_ctx = StudentContext(
            id=student.id, roll_number=student.roll_number,
            program_id=student.program_id,
            program_name=student.program.name if student.program else None,
            department_id=student.department_id,
            department_code=student.department.code if student.department else None,
            current_semester=student.current_semester, division=student.division,
            batch=student.batch,
            cpi=float(student.cpi) if student.cpi is not None else None,
            backlog_count=student.backlog_count,
            admission_year=student.admission_year,
        )

    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty:
        faculty_ctx = FacultyContext(
            id=faculty.id, employee_code=faculty.employee_code,
            department_id=faculty.department_id,
            department_code=faculty.department.code if faculty.department else None,
            designation=faculty.designation, cabin=faculty.cabin,
            is_mentor=faculty.is_mentor,
            coordinations=[
                CoordinationOut(
                    role=c.role.value,
                    domain=c.domain.value, department_id=c.department_id,
                    department_code=c.department_code,
                    department_name=c.department_name,
                    is_institution_wide=c.is_institution_wide,
                )
                for c in scope.coordinations_for(db, user, AssignedRole.COORDINATOR)
            ],
            mentors_programs=scope.mentored_program_types(db, user),
        )

    year = db.scalar(select(AcademicYear).where(AcademicYear.is_current.is_(True)))
    current_sem = db.scalar(select(Semester).where(Semester.is_current.is_(True)))

    return CurrentUserOut(
        id=user.id, email=user.email, full_name=user.full_name, phone=user.phone,
        avatar_url=user.avatar_url, is_active=user.is_active, roles=user.roles,
        permissions=sorted(permissions_for(user.roles)),
        student=student_ctx, faculty=faculty_ctx,
        academic_year=year.label if year else None,
        current_semester_label=(
            f"Semester {student.current_semester}" if student
            else (current_sem.label if current_sem else None)
        ),
        last_login_at=user.last_login_at,
    )


def _authenticate(db, email: str, password: str) -> User:
    user = db.scalar(
        select(User).where(func.lower(User.email) == email.strip().lower())
    )
    if user is None or not verify_password(password, user.hashed_password):
        # Same message either way — never reveal which accounts exist.
        raise AuthenticationError("Incorrect email or password.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")
    return user


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: DbSession) -> AuthResponse:
    user = _authenticate(db, payload.email, payload.password)
    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    ctx = request_context(request)
    audit.record(db, action=AuditAction.LOGIN, entity_type="user", entity_id=user.id,
                 actor=user, description="Signed in", **ctx)
    db.commit()
    return AuthResponse(tokens=_tokens(user), user=build_current_user(db, user))


@router.post("/token", response_model=TokenPair, include_in_schema=False)
def token(db: DbSession, form: OAuth2PasswordRequestForm = Depends()) -> TokenPair:
    """OAuth2 password flow — powers the "Authorize" button in /docs."""
    user = _authenticate(db, form.username, form.password)
    db.commit()
    return _tokens(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired refresh token.") from exc
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Account is unavailable.")
    return _tokens(user)


@router.get("/me", response_model=CurrentUserOut)
def me(db: DbSession, user: CurrentUser) -> CurrentUserOut:
    return build_current_user(db, user)


@router.post("/change-password", response_model=Message,
             status_code=status.HTTP_200_OK)
def change_password(payload: ChangePasswordRequest, db: DbSession,
                    user: CurrentUser) -> Message:
    if not verify_password(payload.current_password, user.hashed_password):
        raise AuthenticationError("Your current password is incorrect.")
    user.hashed_password = hash_password(payload.new_password)
    audit.record(db, action=AuditAction.UPDATE, entity_type="user", entity_id=user.id,
                 actor=user, description="Changed password")
    db.commit()
    return Message(message="Password updated.")


@router.post("/logout", response_model=Message)
def logout() -> Message:
    """Tokens are stateless; the client discards them. A server-side deny-list
    can be added in Phase 2 if session revocation becomes a requirement."""
    return Message(message="Signed out.")
