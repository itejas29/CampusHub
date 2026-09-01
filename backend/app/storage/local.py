from __future__ import annotations

from pathlib import Path

from app.core.errors import NotFoundError
from app.storage.base import SavedObject, StorageBackend


class LocalStorage(StorageBackend):
    """Development backend. Files land under ``LOCAL_STORAGE_DIR`` and are served
    by the ``/media`` static mount."""

    name = "local"

    def __init__(self, root: str, public_url_prefix: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_url_prefix = public_url_prefix.rstrip("/")

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        # Refuse keys that escape the storage root.
        if not candidate.is_relative_to(self.root):
            raise ValueError("invalid storage key")
        return candidate

    def save(self, data: bytes, *, key: str, content_type: str) -> SavedObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return SavedObject(key=key, url=self.url(key), size_bytes=len(data),
                           content_type=content_type, backend=self.name)

    def url(self, key: str) -> str:
        return f"{self.public_url_prefix}/{key}"

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def open(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError("File not found in storage.")
        return path.read_bytes()
