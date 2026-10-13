"""Password hashing and JWT issue/verify.

bcrypt is used directly rather than through passlib to avoid the well-known
passlib/bcrypt version-detection breakage.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]
_BCRYPT_MAX_BYTES = 72
#: Tolerated disagreement between the clock that issued a token and the one
#: verifying it.
CLOCK_SKEW_LEEWAY = dt.timedelta(seconds=5)


def _prepare(password: str) -> bytes:
    # bcrypt silently truncates past 72 bytes; truncate explicitly so behaviour
    # is identical between hashing and verification.
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _create_token(subject: str, token_type: TokenType, expires: dt.timedelta,
                  claims: dict[str, Any] | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": str(uuid.uuid4()),
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | int, roles: list[str] | None = None) -> str:
    return _create_token(
        str(subject),
        "access",
        dt.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        {"roles": roles or []},
    )


def create_refresh_token(subject: str | int) -> str:
    return _create_token(
        str(subject), "refresh", dt.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Raises jwt.PyJWTError on any invalid/expired/mistyped token."""
    # A few seconds of leeway, as RFC 7519 allows for clock skew. Without it a
    # token is rejected as "issued in the future" whenever the host clock is
    # stepped back between issue and first use — which a virtualised clock
    # (Docker Desktop, any NTP correction) does now and then, signing a user
    # out a moment after they signed in.
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                         leeway=CLOCK_SKEW_LEEWAY)
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return payload
