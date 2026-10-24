"""Stored files and the audit trail."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON, BigInteger, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PKMixin, TimestampMixin
from app.models.enums import AuditAction, FileCategory


def _enum(e, name: str, length: int = 40) -> SAEnum:
    return SAEnum(e, native_enum=False, length=length, name=name,
                  values_callable=lambda x: [m.value for m in x])


class StoredFile(PKMixin, TimestampMixin, Base):
    """Backend-agnostic file record.

    Business tables reference ``files.id`` and never a filesystem path, so
    swapping the local backend for S3 in production touches only
    ``app/storage``.
    """

    __tablename__ = "files"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # "local" | "s3"
    storage_backend: Mapped[str] = mapped_column(String(20), default="local", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[FileCategory] = mapped_column(
        _enum(FileCategory, "file_category"), default=FileCategory.OTHER, nullable=False
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    checksum: Mapped[str | None] = mapped_column(String(64))


class AuditLog(PKMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
    )

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_label: Mapped[str | None] = mapped_column(String(150))
    action: Mapped[AuditAction] = mapped_column(_enum(AuditAction, "audit_action"),
                                                nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class LoginThrottle(PKMixin, Base):
    """Failed sign-ins counted per key — an account, an address and account, or
    an address — so password guessing is slowed wherever it comes from
    (services/accounts.py). Kept in the database so every API instance agrees."""
    __tablename__ = "login_throttle"

    key: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    window_started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
