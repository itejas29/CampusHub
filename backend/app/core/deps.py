"""Reusable FastAPI dependencies: current user, role gates, permission gates."""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.rbac import has_permission
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import CoordinationDomain, Role
from app.models.identity import Faculty, Student, User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False
)

DbSession = Annotated[Session, Depends(get_db)]


#: All a person may do while a temporary password is in use.
_WHILE_PASSWORD_MUST_CHANGE = ("/auth/me", "/auth/change-password", "/auth/logout")


def get_current_user(
    request: Request,
    db: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    if not token:
        raise AuthenticationError("Authentication credentials were not provided.")
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Your session has expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    if not user.is_active:
        raise PermissionDeniedError("This account has been deactivated.")
    from app.services import accounts

    if not accounts.token_still_valid(user, payload):

        raise AuthenticationError("Your password was changed. Please sign in again.")
    accounts.assert_may_sign_in(user)
    if user.must_change_password and not request.url.path.endswith(_WHILE_PASSWORD_MUST_CHANGE):
        raise PermissionDeniedError("Choose a new password before continuing.",
                                    code="password_change_required")
    return user



CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    allowed = set(roles)

    def _guard(user: CurrentUser) -> User:
        if Role.SUPER_ADMIN in user.roles or allowed & set(user.roles):
            return user
        names = ", ".join(sorted(r.value for r in allowed))
        raise PermissionDeniedError(f"This action requires one of: {names}.")

    return _guard


def require_permission(permission: str) -> Callable[..., User]:
    def _guard(db: DbSession, user: CurrentUser) -> User:
        if has_permission(user.roles, permission):
            return user
        # A Head of Department covering a seat nobody holds gets what being
        # appointed to it would give (`scope.acting_permissions`). Only an HoD
        # pays the lookup; the handler still narrows to the seat's own scope.
        if user.has_role(Role.HOD):
            from app.services import scope as scope_service

            if permission in scope_service.acting_permissions(db, user):
                return user
        raise PermissionDeniedError(
            f"You do not have the '{permission}' permission."
        )

    return _guard


def require_permission_or_coordination(
    permission: str, *domains: CoordinationDomain
) -> Callable[..., User]:
    """Admit either the institution-wide permission or a scoped coordinator.

    Coordinating a module for one department is a real grant, but it is not the
    institution-wide permission — so a coordinator who holds neither
    `DEPARTMENT_ADMIN` nor `SUPER_ADMIN` would otherwise be locked out of the
    very module they run.

    This dependency only decides *whether the caller coordinates the module at
    all*. It deliberately does not decide **which department**: the handler
    still narrows to the caller's own scope, because that check needs the row
    being acted on. Passing this guard is never permission over everything.
    """

    def _guard(db: DbSession, user: CurrentUser) -> User:
        if has_permission(user.roles, permission):
            return user
        from app.services import scope as scope_service

        for domain in domains:
            if scope_service.coordinates(db, user, domain):
                return user
        raise PermissionDeniedError(
            f"You do not have the '{permission}' permission, and you do not "
            "coordinate this module for any department."
        )

    return _guard


def get_current_student(db: DbSession, user: CurrentUser) -> Student:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise PermissionDeniedError("This area is only available to student accounts.")
    return student


CurrentStudent = Annotated[Student, Depends(get_current_student)]


def get_current_faculty(db: DbSession, user: CurrentUser) -> Faculty:
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))
    if faculty is None:
        raise PermissionDeniedError("This area is only available to faculty accounts.")
    return faculty


CurrentFaculty = Annotated[Faculty, Depends(get_current_faculty)]


def get_optional_faculty(db: DbSession, user: CurrentUser) -> Faculty | None:
    return db.scalar(select(Faculty).where(Faculty.user_id == user.id))


def request_context(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def resolve_student_or_404(db: Session, student_id: int) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")
    return student


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
