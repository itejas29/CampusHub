"""File handling: what a client claims is never what gets trusted.

Phase 4 closed two real holes, and these tests keep them closed:

* uploads were served from a public ``/media`` static mount, so any stored
  document was readable by anyone who knew or guessed its object key;
* ``GET /files/{id}`` returned that URL to *any* signed-in user, so walking the
  id space handed out other students' certificates.
"""
from __future__ import annotations

import time

import pytest

from app.core.errors import ValidationError
from app.services.files import (
    SIGNED_URL_TTL_SECONDS, _assert_signature_matches, sanitize_filename,
    sign_file_token, verify_file_token,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"


# ── the bytes must match the declared type ─────────────────────────────────
def test_a_real_pdf_passes():
    _assert_signature_matches(PDF, "application/pdf")


@pytest.mark.parametrize("payload", [
    b"<script>alert(1)</script>",
    b"#!/bin/sh\nrm -rf /",
    b"GIF89a",
    PNG,                                    # a real PNG, but claimed as a PDF
])
def test_content_type_alone_is_not_believed(payload):
    """Content-Type comes from the browser and is trivially forged."""
    with pytest.raises(ValidationError, match="do not match its type"):
        _assert_signature_matches(payload, "application/pdf")


def test_an_image_claimed_as_another_image_is_rejected():
    with pytest.raises(ValidationError):
        _assert_signature_matches(JPEG, "image/png")


def test_office_documents_accept_any_zip_member_signature():
    for prefix in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        _assert_signature_matches(
            prefix + b"rest",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def test_an_unlisted_type_is_not_signature_checked():
    """Types with no known magic simply skip this check rather than failing
    closed on a format we have no signature for."""
    _assert_signature_matches(b"anything", "application/octet-stream")


# ── filenames are echoed back in a header, so they are sanitised ───────────
@pytest.mark.parametrize("raw,expected", [
    ("report.pdf", "report.pdf"),
    ("../../etc/passwd", "passwd"),
    ("..\\..\\windows\\system32", "system32"),
    ("/absolute/path/thing.pdf", "thing.pdf"),
    ('bad"quote.pdf', "bad_quote.pdf"),
    ("", "upload"),
    (None, "upload"),
])
def test_filenames_are_reduced_to_a_safe_name(raw, expected):
    assert sanitize_filename(raw) == expected


def test_header_injection_via_filename_is_neutralised():
    """A newline in a filename could otherwise split the Content-Disposition
    header and inject one of its own."""
    dirty = 'week1.pdf"\r\nX-Injected: yes'
    clean = sanitize_filename(dirty)
    assert "\r" not in clean and "\n" not in clean and '"' not in clean


def test_control_characters_are_stripped():
    assert "\x00" not in sanitize_filename("null\x00byte.pdf")


def test_a_very_long_filename_is_truncated():
    assert len(sanitize_filename("a" * 500 + ".pdf")) <= 120


# ── signed links ───────────────────────────────────────────────────────────
def test_a_signed_token_verifies_for_its_own_file():
    expires = int(time.time()) + SIGNED_URL_TTL_SECONDS
    token = sign_file_token(42, expires)
    assert verify_file_token(42, token)


def test_a_token_does_not_work_for_a_different_file():
    """Otherwise one legitimately-issued link would unlock every file."""
    expires = int(time.time()) + SIGNED_URL_TTL_SECONDS
    token = sign_file_token(42, expires)
    assert not verify_file_token(43, token)


def test_an_expired_token_is_refused():
    token = sign_file_token(42, int(time.time()) - 1)
    assert not verify_file_token(42, token)


@pytest.mark.parametrize("token", [None, "", "garbage", "notanumber.abc",
                                   "9999999999.deadbeef"])
def test_forged_and_malformed_tokens_are_refused(token):
    assert not verify_file_token(42, token)


def test_the_signature_is_not_guessable_from_the_expiry():
    """The expiry is public in the URL; the digest must still be unforgeable."""
    expires = int(time.time()) + SIGNED_URL_TTL_SECONDS
    assert not verify_file_token(42, f"{expires}.{'0' * 32}")


# ── the storage key never leaves the backend ───────────────────────────────
def test_uploads_are_not_mounted_as_static_files():
    """The public mount is what made every document readable without a login."""
    import app.main as main_module

    mounted = [getattr(r, "path", "") for r in main_module.app.routes]
    assert "/media" not in mounted
    assert not any(str(p).startswith("/media") for p in mounted)


def test_the_file_response_schema_returns_a_download_link_not_a_key():
    from app.schemas.admin import FileOut

    assert "storage_key" not in FileOut.model_fields
    assert "url" in FileOut.model_fields
