"""Validated field types for everything the API accepts.

The server is the one place a rule cannot be skipped — a form can be bypassed,
a request cannot. Each type cleans the value (trims, collapses whitespace,
normalises a phone number) and refuses what is not plausibly what the field
asks for, with a message that says what to type instead.

Typing "99" as a supervisor's phone, or "n n" as their name, used to be
accepted. These types are used by every request schema; the screens mirror
the same checks (`frontend/src/lib/validation.ts`) so a mistake shows before
submitting.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, EmailStr  # noqa: F401  (re-exported)

# ── helpers ───────────────────────────────────────────────────────────────
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏  ‪-‮⁦-⁩]")
_SPACES = re.compile(r"\s+")


def _clean_line(value):
    """One line of text: no control or bidi-override characters, single spaces."""
    if value is None or not isinstance(value, str):
        return value
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL.sub("", value)
    return _SPACES.sub(" ", value).strip()


def _clean_block(value):
    """Multi-line text: lines kept, control characters dropped, ends trimmed."""
    if value is None or not isinstance(value, str):
        return value
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    value = _CONTROL.sub("", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _empty_to_none(value):
    return None if isinstance(value, str) and not value.strip() else value


def optional(kind):
    """`kind`, or nothing. A blank box in a form arrives as "" and means "not
    given" — it becomes None before `kind` checks it, so a blank optional
    phone is not refused as an invalid one."""
    return Annotated[kind | None, BeforeValidator(_empty_to_none)]


def _no_markup(value: str | None) -> str | None:
    if value and re.search(r"[<>]", value):
        raise ValueError("Remove the < and > characters.")
    return value


def line(max_length: int, *, min_length: int = 1):
    """A single line of plain text, `min_length`..`max_length` characters."""
    def check(value: str | None) -> str | None:
        if value is None:
            return None
        _no_markup(value)
        if len(value) < min_length:
            raise ValueError(f"Enter at least {min_length} characters.")
        if len(value) > max_length:
            raise ValueError(f"Keep it to {max_length} characters.")
        return value
    return Annotated[str, BeforeValidator(_clean_line), AfterValidator(check)]


def block(max_length: int, *, min_length: int = 0):
    """Multi-line text (descriptions, comments), up to `max_length` characters."""
    def check(value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) < min_length:
            raise ValueError(f"Write at least {min_length} characters.")
        if len(value) > max_length:
            raise ValueError(f"Keep it to {max_length} characters.")
        return value
    return Annotated[str, BeforeValidator(_clean_block), AfterValidator(check)]


# ── people ────────────────────────────────────────────────────────────────
_NAME_CHARS = re.compile(r"^[^\W\d_]+(?:[ .'\-][^\W\d_]*)*\.?$", re.UNICODE)


def _without_marks(value: str) -> str:
    """Drop combining marks so the vowel signs of Indic scripts count as part of
    their letter — "राम शर्मा" is a name."""
    return "".join(ch for ch in unicodedata.normalize("NFC", value)
                   if not unicodedata.category(ch).startswith("M"))


def _person_name(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 100:
        raise ValueError("Keep the name to 100 characters.")
    bare = _without_marks(value)
    if not _NAME_CHARS.match(bare) or not any(len(re.sub(r"[.'\-]", "", p)) >= 2 for p in bare.split(" ")):
        raise ValueError("Enter a real name — letters only, at least one word of two letters "
                         "(e.g. “Asha Patel” or “Dr. R. K. Shah”).")
    return value


#: A person's name: letters (any script), spaces, . ' - ; no digits; at least
#: one word of two or more letters — "n n" and "a1" are refused.
PersonName = Annotated[str, BeforeValidator(_clean_line), AfterValidator(_person_name)]


# ── phone ─────────────────────────────────────────────────────────────────
def _phone(value: str | None) -> str | None:
    """Indian mobile, Indian landline with STD code, or an international number.

    Returned normalised: "+91 98765 43210" for a mobile, "0XX-XXXXXXXX" for a
    landline, "+<country> <number>" for an international one.
    """
    if value is None:
        return None
    raw = value.strip()
    if not re.fullmatch(r"[+()\d\s.\-]{1,25}", raw):
        raise ValueError("Enter a phone number using digits only (spaces, - and + are fine).")
    digits = re.sub(r"\D", "", raw)
    international = raw.startswith("+") and not digits.startswith("91")
    if international:
        if not 8 <= len(digits) <= 15:
            raise ValueError("An international number has 8 to 15 digits after the +.")
        return f"+{digits}"
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        if len(set(digits)) == 1:
            raise ValueError("That is not a real phone number.")
        return f"+91 {digits[:5]} {digits[5:]}"
    # With the trunk 0 an Indian number is always 11 digits: a landline's STD
    # code and number (079 2327 5000), or a mobile written 0 98765 43210. The
    # two cannot be told apart, so it is kept as typed, digits only.
    if len(digits) == 11 and digits[0] == "0" and digits[1] != "0" and len(set(digits[1:])) > 1:
        return digits
    raise ValueError("Enter a 10-digit mobile number (starting 6–9), a landline with its "
                     "STD code, or an international number starting with +.")


Phone = Annotated[str, AfterValidator(_phone)]


# ── identifiers, places, links ────────────────────────────────────────────
def _pattern(regex: str, message: str, *, upper: bool = False):
    compiled = re.compile(regex)

    def check(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper() if upper else value.strip()
        if not compiled.fullmatch(value):
            raise ValueError(message)
        return value
    return check


#: PDEU roll numbers: two digits of the year, the programme letters, a serial —
#: 24BIT031, 24BCB001.
RollNumber = Annotated[str, AfterValidator(_pattern(
    r"\d{2}[A-Z]{2,4}\d{3,4}[A-Z]?", "Enter a roll number like 24BIT031.", upper=True))]

def identifier(max_length: int = 40):
    """Course, programme, round, division and employee codes, references:
    letters, digits and - _ . / , up to `max_length`."""
    return Annotated[str, AfterValidator(_pattern(
        rf"[A-Za-z0-9][A-Za-z0-9._/\-]{{0,{max_length - 1}}}",
        f"Use letters, digits and - _ . / only (up to {max_length})."))]


Code = identifier(40)


#: An Indian PIN code.
Pincode = Annotated[str, AfterValidator(_pattern(
    r"[1-9]\d{5}", "Enter a 6-digit PIN code."))]

#: A grade as departments write it: O, A+, B, AB, F …
Grade = Annotated[str, AfterValidator(_pattern(
    r"[A-Z]{1,2}[+\-]?", "Enter a grade like A+, B or O.", upper=True))]


def _url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > 500:
        raise ValueError("Keep the link to 500 characters.")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(:\d{2,5})?(/[^\s<>\"]*)?", value):
        raise ValueError("Enter a web address starting with https://")
    return value


#: An http(s) link to a real host — never javascript:, data: or a bare word.
Url = Annotated[str, AfterValidator(_url)]


def place(max_length: int = 80):
    """A city, district, state or country: letters, spaces, . ' - ( ) &"""
    def check(value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) > max_length:
            raise ValueError(f"Keep it to {max_length} characters.")
        if not re.fullmatch(r"[^\W\d_][^\W\d_ .'\-()&]*(?:[ .'\-()&]+[^\W\d_]+)*\.?\)?", value):
            raise ValueError("Use letters only for a place name.")
        return value
    return Annotated[str, BeforeValidator(_clean_line), AfterValidator(check)]



# ── free-form data ────────────────────────────────────────────────────────
def json_object(max_bytes: int = 10_000):
    """A JSON object kept small. Some requests carry free-form settings or
    stage data that is stored as sent; without a bound one request could
    store megabytes."""

    def check(value: dict) -> dict:
        if len(json.dumps(value, default=str)) > max_bytes:
            raise ValueError(f"Too much data — keep it under {max_bytes // 1000} KB.")
        return value
    return Annotated[dict, AfterValidator(check)]


# ── exports ───────────────────────────────────────────────────────────────

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """A CSV cell that a spreadsheet will not run as a formula.

    Exports carry text students typed (organisation names, titles). A cell
    beginning with = + - or @ is executed by Excel and Sheets when opened
    ("CSV injection"); prefixing an apostrophe shows it as text instead.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value
