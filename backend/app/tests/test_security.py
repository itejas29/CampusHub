from __future__ import annotations

import datetime as dt

import jwt
import pytest

from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password,
    verify_password,
)


def test_password_round_trip():
    hashed = hash_password("Campus@123")
    assert hashed != "Campus@123"
    assert verify_password("Campus@123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_password_longer_than_bcrypt_limit_is_handled():
    """bcrypt truncates at 72 bytes; hashing and verification must agree."""
    long_password = "a" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)
    assert verify_password("a" * 72, hashed)


def test_verify_rejects_malformed_hash():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_access_token_carries_subject_and_roles():
    payload = decode_token(create_access_token(7, ["STUDENT"]), expected_type="access")
    assert payload["sub"] == "7"
    assert payload["roles"] == ["STUDENT"]


def test_refresh_token_is_not_accepted_as_access_token():
    token = create_refresh_token(7)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")


def test_tampered_token_is_rejected():
    token = create_access_token(7, ["STUDENT"])
    with pytest.raises(jwt.PyJWTError):
        decode_token(token[:-4] + "aaaa", expected_type="access")


def test_expired_token_is_rejected(monkeypatch):
    from app.core import security

    token = security._create_token(
        "7", "access", dt.timedelta(seconds=-10), {"roles": []}
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, expected_type="access")


def _token_issued(offset_seconds: int) -> str:
    """An access token whose `iat` is that far from the verifying clock."""
    from app.core.config import settings

    issued = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset_seconds)
    return jwt.encode(
        {"sub": "7", "type": "access", "iat": issued,
         "exp": issued + dt.timedelta(minutes=30)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )


def test_a_token_survives_the_clock_stepping_back_a_moment():
    """Regression: with no leeway, a host clock corrected backwards between
    sign-in and the next request made the token "issued in the future", and the
    user was signed out a second after signing in."""
    assert decode_token(_token_issued(3), expected_type="access")["sub"] == "7"


def test_a_token_from_well_into_the_future_is_still_rejected():
    with pytest.raises(jwt.PyJWTError):
        decode_token(_token_issued(120), expected_type="access")
