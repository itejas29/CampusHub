"""Storage backend contract.

Business code never touches a path or a bucket — it calls ``save``/``url``/
``delete`` on the active backend. Swapping local disk for S3 in production is a
configuration change (``STORAGE_BACKEND=s3``), not a code change.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(slots=True)
class SavedObject:
    key: str
    url: str
    size_bytes: int
    content_type: str
    backend: str


class StorageBackend(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    def save(self, data: bytes, *, key: str, content_type: str) -> SavedObject: ...

    @abc.abstractmethod
    def url(self, key: str) -> str:
        """Publicly resolvable (or pre-signed) URL for a stored object."""

    @abc.abstractmethod
    def delete(self, key: str) -> None: ...

    @abc.abstractmethod
    def open(self, key: str) -> bytes: ...
