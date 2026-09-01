"""In-app notification fan-out.

Phase 1 writes rows only. An email/SMS transport can subscribe to the same
``dispatch`` entry point later without touching call sites.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.models.engagement import Notification
from app.models.enums import NotificationType, Priority


def notify(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    title: str,
    message: str | None = None,
    link: str | None = None,
    priority: Priority = Priority.NORMAL,
    meta: dict[str, Any] | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id, type=type, title=title, message=message, link=link,
        priority=priority, meta=meta or {},
    )
    db.add(notification)
    return notification


def notify_many(db: Session, *, user_ids: Iterable[int], **kwargs: Any) -> list[Notification]:
    return [notify(db, user_id=uid, **kwargs) for uid in dict.fromkeys(user_ids)]
