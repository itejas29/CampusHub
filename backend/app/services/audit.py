"""Append-only audit trail helper."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AuditAction
from app.models.identity import User
from app.models.system import AuditLog


def record(
    db: Session,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: int | None = None,
    actor: User | None = None,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Stage an audit row. The caller's ``db.commit()`` persists it atomically
    with the change being audited."""
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_label=f"{actor.full_name} <{actor.email}>" if actor else "system",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        meta=meta or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    return entry


def recent(db: Session, *, limit: int = 50, entity_type: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    return list(db.scalars(stmt))
