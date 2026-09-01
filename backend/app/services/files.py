"""Upload pipeline: validate → store → record a ``files`` row.

Three things are deliberately not trusted here: the browser's Content-Type
header, the filename, and the caller's word that the bytes are what they claim.
The declared type is checked against the file's own magic bytes, the name is
reduced to something safe to echo back, and the storage key is never derived
from anything the user supplied.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
import unicodedata
import uuid
from pathlib import PurePosixPath

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.models.enums import FileCategory
from app.models.identity import User
from app.models.system import StoredFile
from app.storage import get_storage

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg", "image/png", "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

#: The first bytes each accepted format must actually start with. Content-Type
#: is supplied by the client and is trivially forged, so a PDF that begins with
#: ``<script>`` is rejected here regardless of what the header claimed.
#: Formats whose containers are checked structurally (ZIP-based Office files)
#: share the PK signature; the rest are matched exactly.
_MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
    "application/msword": (b"\xd0\xcf\x11\xe0",),
    "application/vnd.ms-powerpoint": (b"\xd0\xcf\x11\xe0",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

#: How long a signed file link stays valid. Long enough to render a page,
#: short enough that a copied URL stops working.
SIGNED_URL_TTL_SECONDS = 15 * 60

_CATEGORY_FOLDER = {
    FileCategory.CERTIFICATE: "certificates",
    FileCategory.REPORT: "reports",
    FileCategory.OFFER_LETTER: "offer-letters",
    FileCategory.POSTER: "posters",
    FileCategory.PHOTO: "photos",
    FileCategory.SYLLABUS: "syllabus",
    FileCategory.AVATAR: "avatars",
    FileCategory.OTHER: "misc",
}


def _safe_extension(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix if 1 < len(suffix) <= 10 and suffix[1:].isalnum() else ""


def sanitize_filename(name: str | None) -> str:
    """Reduce a user-supplied name to something safe to store and echo back.

    The original name is later returned in a ``Content-Disposition`` header, so
    quotes, newlines and control characters have to go — otherwise a crafted
    filename can inject header content. Path separators go too: a name is a
    name, never a location.
    """
    if not name:
        return "upload"
    name = unicodedata.normalize("NFKD", name)
    name = PurePosixPath(name.replace("\\", "/")).name          # strip any path
    name = "".join(ch for ch in name if ch.isprintable())
    name = re.sub(r'[\x00-\x1f\x7f"\\/:*?<>|]+', "_", name).strip(" .")
    name = re.sub(r"_{2,}", "_", name)
    if not name:
        return "upload"
    return name[:120]


def _assert_signature_matches(data: bytes, content_type: str) -> None:
    """The bytes must match the type the client claimed."""
    expected = _MAGIC.get(content_type)
    if not expected:
        return
    if not any(data.startswith(prefix) for prefix in expected):
        raise ValidationError(
            "The file contents do not match its type. Re-export the file and "
            "upload it again."
        )


# ── signed links ───────────────────────────────────────────────────────────
# A browser cannot attach a bearer token to <img src>, so images need a URL that
# carries its own proof. The proof is short-lived and is only ever handed out
# *after* the caller has passed the same authorisation check as a download.
def sign_file_token(file_id: int, expires_at: int) -> str:
    payload = f"{file_id}.{expires_at}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256)
    return f"{expires_at}.{digest.hexdigest()[:32]}"


def verify_file_token(file_id: int, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    raw_expiry, _, _ = token.partition(".")
    try:
        expires_at = int(raw_expiry)
    except ValueError:
        return False
    if expires_at < int(time.time()):
        return False
    return hmac.compare_digest(sign_file_token(file_id, expires_at), token)


async def save_upload(
    db: Session,
    upload: UploadFile,
    *,
    category: FileCategory = FileCategory.OTHER,
    uploaded_by: User | None = None,
) -> StoredFile:
    content_type = upload.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            f"'{content_type}' files are not accepted. Upload a PDF, image or document."
        )

    data = await upload.read()
    if not data:
        raise ValidationError("The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(
            f"File is larger than the {settings.MAX_UPLOAD_SIZE_MB} MB limit."
        )
    _assert_signature_matches(data, content_type)

    folder = _CATEGORY_FOLDER.get(category, "misc")
    key = f"{folder}/{uuid.uuid4().hex}{_safe_extension(upload.filename or '')}"
    stored = get_storage().save(data, key=key, content_type=content_type)

    record = StoredFile(
        filename=PurePosixPath(key).name,
        original_name=sanitize_filename(upload.filename),
        content_type=content_type,
        size_bytes=stored.size_bytes,
        storage_backend=stored.backend,
        storage_key=stored.key,
        category=category,
        uploaded_by_user_id=uploaded_by.id if uploaded_by else None,
        checksum=hashlib.sha256(data).hexdigest(),
    )
    db.add(record)
    db.flush()
    return record


def signed_url(file: StoredFile | None) -> str | None:
    """A time-limited link to one file, routed through the API.

    Deliberately *not* the storage URL. A storage key is an internal detail:
    handing one out makes the object reachable forever, outside every
    authorisation check the application performs.
    """
    if file is None:
        return None
    expires_at = int(time.time()) + SIGNED_URL_TTL_SECONDS
    token = sign_file_token(file.id, expires_at)
    return f"{settings.API_V1_PREFIX}/files/{file.id}/download?token={token}"


def storage_url(file: StoredFile | None) -> str | None:
    """The raw backend URL. Internal use only — never returned to a client."""
    if file is None:
        return None
    return get_storage().url(file.storage_key)
