"""Sign-in safety: password guessing, temporary passwords, and demo accounts.

**Throttling.** Failed sign-ins are counted under three keys, each with its
own limit inside a 15-minute window:

* the account from one address — the ordinary case, a few wrong guesses;
* the account from anywhere — a slower limit, so guessing from many
  addresses still stops;
* one address across all accounts — spraying one password at many accounts.
  Set high: a whole campus can sit behind one address.

While demo accounts are on, they are counted only under the address: their
password is published, and locking one would stop a presentation.

A locked key answers "too many attempts" whether or not the account exists,

so throttling never reveals which emails are registered.

**Temporary passwords.** There is no email yet, so a forgotten password is
reset by the registrar (anyone) or a department office (its own students),
who reads a one-time password to the person. It must be replaced at the next
sign-in, and issuing it signs the account out everywhere.

**Demo accounts** share one published password. While `DEMO_MODE` is on they
cannot change it (one visitor would lock everyone else out of a shared demo
login) and no *real* account can be given a password (anyone holding the demo
registrar's password could take it over). With `DEMO_MODE` off, demo accounts
cannot sign in at all.
"""
from __future__ import annotations

import datetime as dt
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError, ValidationError
from app.core.security import hash_password
from app.models.enums import AuditAction, Role
from app.models.identity import Faculty, Student, User
from app.models.system import LoginThrottle
from app.services import audit

WINDOW = dt.timedelta(minutes=15)
LOCK = dt.timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class Limit:
    prefix: str
    failures: int


ACCOUNT_FROM_ADDRESS = Limit("acct-ip", 5)
ACCOUNT_ANYWHERE = Limit("acct", 20)
ADDRESS_ANY_ACCOUNT = Limit("ip", 100)

#: Real accounts sign in at an address the seed gives them; demo personas use
#: the bare demo domain. A real PDEU address is never a demo account.
DEMO_DOMAIN = "@campushub.example.com"
REAL_PLACEHOLDER_DOMAINS = ("@faculty.campushub.example.com", "@students.campushub.example.com")

COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890",
    "qwerty123", "campus@123", "campushub", "pdeu@123", "pdeu1234", "pdpu@123",
    "welcome@123", "admin@123", "abcd@1234", "iloveyou", "india@123",
}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def is_demo_account(user: User) -> bool:
    email = user.email.lower()
    return email.endswith(DEMO_DOMAIN) and not email.endswith(REAL_PLACEHOLDER_DOMAINS)


def client_address(request) -> str:
    """The caller's address. Behind Railway's proxy every request arrives from
    the proxy; the proxy appends the real client as the *last* X-Forwarded-For
    entry, which the client cannot forge (earlier entries it can)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


# ── throttling ───────────────────────────────────────────────────────────
def _keys(email: str, address: str, *, demo: bool) -> list[tuple[Limit, str]]:
    email = email.strip().lower()[:200]
    keys = [(ADDRESS_ANY_ACCOUNT, f"{ADDRESS_ANY_ACCOUNT.prefix}:{address}")]
    # A demo login's password is published, so guessing it gains nothing — and
    # a few typos in a room sharing one address would lock it mid-presentation.
    if not (demo and settings.DEMO_MODE):
        keys += [(ACCOUNT_FROM_ADDRESS, f"{ACCOUNT_FROM_ADDRESS.prefix}:{address}:{email}"),
                 (ACCOUNT_ANYWHERE, f"{ACCOUNT_ANYWHERE.prefix}:{email}")]
    return keys



def _row(db: Session, key: str) -> LoginThrottle | None:
    return db.scalar(select(LoginThrottle).where(LoginThrottle.key == key))


def assert_not_throttled(db: Session, email: str, address: str, *, demo: bool) -> None:
    now = utcnow()
    for _limit, key in _keys(email, address, demo=demo):
        row = _row(db, key)
        locked = _aware(row.locked_until) if row else None
        if locked and locked > now:
            minutes = max(1, int((locked - now).total_seconds() // 60) + 1)
            raise AuthenticationError(
                f"Too many sign-in attempts. Try again in {minutes} minute"
                f"{'' if minutes == 1 else 's'}.", code="too_many_attempts", status_code=429)



def record_failure(db: Session, email: str, address: str, *, demo: bool) -> None:
    now = utcnow()
    for limit, key in _keys(email, address, demo=demo):
        row = _row(db, key)
        if row is None:
            # Two failures at the same instant may both try to create the key.
            try:
                with db.begin_nested():
                    row = LoginThrottle(key=key, failures=0, window_started_at=now)
                    db.add(row)
                    db.flush()
            except IntegrityError:
                row = _row(db, key)

        if now - _aware(row.window_started_at) > WINDOW:
            row.failures, row.window_started_at, row.locked_until = 0, now, None
        row.failures += 1
        if row.failures >= limit.failures:
            row.locked_until = now + LOCK
    db.flush()


def record_success(db: Session, email: str, address: str) -> None:
    """A correct password clears the account's own counters, not the address's."""
    email = email.strip().lower()[:200]
    for key in (f"{ACCOUNT_FROM_ADDRESS.prefix}:{address}:{email}",
                f"{ACCOUNT_ANYWHERE.prefix}:{email}"):
        row = _row(db, key)
        if row is not None:
            db.delete(row)
    db.flush()


def assert_may_sign_in(user: User) -> None:
    if not settings.DEMO_MODE and is_demo_account(user):
        raise AuthenticationError("Demo accounts are switched off on this portal.")


# ── passwords ────────────────────────────────────────────────────────────
def check_password_policy(password: str, user: User) -> None:
    """At least 10 characters, a letter and a digit, not a common password and
    not built from the person's own name or email."""
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("both letters and digits")
    if problems:
        raise ValidationError("Use a password with " + " and ".join(problems) + ".")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        raise ValidationError("That password is too common — choose another.")
    personal = [user.email.split("@")[0].lower(), *(part.lower() for part in
                re.split(r"[\s.]+", user.full_name or "") if len(part) >= 4)]
    if any(part and len(part) >= 4 and part in lowered for part in personal):
        raise ValidationError("Don't use your name or email in your password.")


def set_password(db: Session, user: User, password: str, *, actor: User) -> None:
    """The person's own new password: checked, then every other session ends."""
    if settings.DEMO_MODE and is_demo_account(user):
        raise PermissionDeniedError(
            "Demo accounts share one password so everyone can try them; it can't be changed.")
    check_password_policy(password, user)
    user.hashed_password = hash_password(password)
    user.must_change_password = False
    user.sessions_valid_after = utcnow()
    audit.record(db, action=AuditAction.UPDATE, entity_type="user", entity_id=user.id,
                 actor=actor, description="Changed password")


# ── temporary passwords ──────────────────────────────────────────────────
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"   # no 0/O, 1/l/I


def temporary_password() -> str:
    # Readable aloud or over the phone; always holds a letter and a digit.
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(12))
        if re.search(r"[A-Za-z]", candidate) and re.search(r"\d", candidate):
            return f"{candidate[:4]}-{candidate[4:8]}-{candidate[8:]}"


def assert_can_reset(db: Session, actor: User, target: User) -> None:
    if target.id == actor.id:
        raise PermissionDeniedError("Change your own password from your profile.")
    if target.has_role(Role.SUPER_ADMIN):
        raise PermissionDeniedError("A registrar account's password can't be reset here.")
    if settings.DEMO_MODE:
        raise PermissionDeniedError(
            "Passwords can be issued only once demo accounts are switched off (DEMO_MODE): "
            "while anyone can sign in as the demo registrar, no account's password may be "
            "set from here.")
    if actor.has_role(Role.SUPER_ADMIN):
        return
    if actor.has_role(Role.DEPARTMENT_ADMIN):
        office = db.scalar(select(Faculty).where(Faculty.user_id == actor.id))
        student = db.scalar(select(Student).where(Student.user_id == target.id))
        # Students only: an office able to reset a coordinator or the HoD
        # could sign in as them.
        if office is not None and student is not None \
                and student.department_id == office.department_id \
                and set(target.roles) == {Role.STUDENT}:
            return
        raise PermissionDeniedError("A department office may reset its own students' passwords only.")
    raise PermissionDeniedError("Only the registrar or a department office can reset passwords.")


def issue_temporary_password(db: Session, target: User, *, actor: User) -> str:
    assert_can_reset(db, actor, target)
    password = temporary_password()
    target.hashed_password = hash_password(password)
    target.must_change_password = True
    target.sessions_valid_after = utcnow()
    target.is_active = True
    audit.record(db, action=AuditAction.UPDATE, entity_type="user", entity_id=target.id,
                 actor=actor, description=f"Issued a temporary password to {target.full_name}")
    return password


def session_version(user: User) -> int:
    """Changes whenever the password does; every token carries the version it
    was issued under. 0 for an account whose password was never changed — so
    tokens issued before this existed stay valid."""
    valid_after = _aware(user.sessions_valid_after)
    return int(valid_after.timestamp() * 1_000_000) if valid_after else 0


def token_still_valid(user: User, claims: dict) -> bool:
    """A token issued before the account's last password change is refused."""
    return int(claims.get("sv") or 0) == session_version(user)

