from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import SavedObject, StorageBackend
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


@lru_cache
def get_storage() -> StorageBackend:
    if settings.STORAGE_BACKEND == "s3":
        return S3Storage(
            bucket=settings.S3_BUCKET_NAME,
            region=settings.AWS_REGION,
            public_base_url=settings.S3_PUBLIC_BASE_URL,
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return LocalStorage(settings.LOCAL_STORAGE_DIR, settings.LOCAL_STORAGE_PUBLIC_URL)


__all__ = ["StorageBackend", "SavedObject", "get_storage"]
