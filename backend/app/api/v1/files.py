"""File access. Every path through here is authorised, and none of them leak a
storage key.

The pre-Phase-4 arrangement had two holes that mattered:

* uploads were served from a public ``/media`` mount, so any document was
  readable by anyone who knew or guessed its object key — no login at all;
* ``GET /files/{id}`` returned that public URL to *any* signed-in user, so
  walking the id space handed out other students' certificates.

Both are closed. Metadata is authorised exactly like a download, the only URL
ever returned is a short-lived signed link back to this API, and the raw
``storage_key`` never crosses the boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response

from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.enums import AuditAction, FileCategory
from app.models.system import StoredFile
from app.schemas.admin import FileOut
from app.services import audit
from app.services import documents as docs
from app.services.files import save_upload, signed_url, verify_file_token
from app.storage import get_storage

router = APIRouter(prefix="/files", tags=["files"])


def _file_out(stored: StoredFile) -> FileOut:
    return FileOut(
        id=stored.id, filename=stored.filename, original_name=stored.original_name,
        content_type=stored.content_type, size_bytes=stored.size_bytes,
        category=stored.category.value,
        # A signed link back to this API — never the object's storage location.
        url=signed_url(stored),
        created_at=stored.created_at,
    )


@router.post("", response_model=FileOut, status_code=201)
async def upload(db: DbSession, user: CurrentUser, file: UploadFile = File(...),
                 category: FileCategory = Form(FileCategory.OTHER)) -> FileOut:
    """Generic upload. Business modules attach the returned id to their records.

    The declared content type is verified against the file's magic bytes, and
    the filename is sanitised before it is ever stored or echoed back.
    """
    stored = await save_upload(db, file, category=category, uploaded_by=user)
    audit.record(db, action=AuditAction.UPLOAD, entity_type="file", entity_id=stored.id,
                 actor=user, description=f"Uploaded {stored.original_name}")
    db.commit()

    db.refresh(stored)
    return _file_out(stored)


@router.get("/{file_id}", response_model=FileOut)
def get_file(file_id: int, db: DbSession, user: CurrentUser) -> FileOut:
    """File metadata, authorised the same way a download is.

    Being signed in is not enough: the caller must be entitled to *this* file.
    """
    stored = db.get(StoredFile, file_id)
    if stored is None:
        raise NotFoundError("File not found.")
    docs.assert_can_read_file(db, file_id, user)
    return _file_out(stored)


@router.get("/{file_id}/download")
def download(file_id: int, db: DbSession, user: CurrentUser,
             token: str | None = Query(None)) -> Response:
    """Stream a stored file through the API so access is always checked.

    Two ways in, and both are checked. A signed token is accepted because a
    browser cannot attach a bearer header to ``<img src>`` — but a token is only
    ever issued to a caller who already passed the authorisation check below,
    and it expires. Everything else goes through
    `services/documents.assert_can_read_file`, which scopes internship artefacts
    to the student, their mentor, and the coordinators of that programme.
    """
    stored = db.get(StoredFile, file_id)
    if stored is None:
        raise NotFoundError("File not found.")
    if not verify_file_token(file_id, token):
        docs.assert_can_read_file(db, file_id, user)

    data = get_storage().open(stored.storage_key)
    # The filename is sanitised on upload, so it is safe to echo here; quoting
    # it keeps a stray character from splitting the header regardless.
    safe_name = stored.original_name.replace('"', "")
    return Response(
        content=data, media_type=stored.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            # Never let a browser sniff an uploaded file into something
            # executable, and never let a proxy cache an authorised document.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
