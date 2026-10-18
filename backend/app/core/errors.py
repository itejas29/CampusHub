"""Domain exceptions + centralised handlers producing one error envelope."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base for expected, user-facing failures."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None,
                 code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class BusinessRuleError(AppError):
    """A workflow/eligibility rule blocked the action."""

    status_code = status.HTTP_409_CONFLICT
    code = "rule_violation"


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


#: What a form calls a field, where its name says something else.
_FIELD_LABELS = {
    "industry_mentor_name": "Supervisor's name",
    "industry_mentor_phone": "Supervisor's phone",
    "industry_mentor_email": "Supervisor's email",
    "industry_mentor_designation": "Supervisor's designation",
    "guardian_phone": "Guardian's phone",
    "guardian_name": "Guardian's name",
    "public_phone": "Public phone",
    "public_email": "Public email",
}


def _field_label(loc: tuple) -> str:
    names = [str(p) for p in loc[1:] if isinstance(p, str) and "[" not in p]
    if not names:
        return "This field"
    last = names[-1]
    return _FIELD_LABELS.get(last) or last.replace("_", " ").capitalize()


def _human(msg: str) -> str:
    # pydantic prefixes the validators' own messages; they are written for people.
    return msg.removeprefix("Value error, ")


def validation_message(errors: list[dict]) -> str:
    """One sentence a person can act on: which field, and what to type."""
    if not errors:
        return "The submitted data is invalid."
    first = errors[0]
    text = f"{_field_label(tuple(first['loc']))}: {_human(first['msg'])}"
    if len(errors) > 1:
        text += f" (and {len(errors) - 1} more)"
    return text


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {401: "not_authenticated", 403: "permission_denied", 404: "not_found"}
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(codes.get(exc.status_code, "http_error"), str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][-1]),
                "message": _human(err["msg"]),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("validation_error", validation_message(exc.errors()), fields),
        )


    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope(
                "conflict",
                "That operation conflicts with existing data "
                "(a duplicate, or a referenced record is missing).",
            ),
        )
