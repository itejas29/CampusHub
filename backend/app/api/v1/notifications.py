from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.core.deps import CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.models.engagement import Notification
from app.schemas.common import Message
from app.schemas.engagement import MarkReadRequest, NotificationOut, NotificationSummary

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationSummary)
def list_notifications(db: DbSession, user: CurrentUser,
                       unread_only: bool = Query(False),
                       limit: int = Query(20, ge=1, le=100)) -> NotificationSummary:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    items = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit))
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    )) or 0
    return NotificationSummary(
        unread=int(unread),
        items=[NotificationOut.model_validate(n) for n in items],
    )


@router.post("/read", response_model=Message)
def mark_read(payload: MarkReadRequest, db: DbSession, user: CurrentUser) -> Message:
    now = dt.datetime.now(dt.timezone.utc)
    stmt = update(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)
    )
    if not payload.all:
        if not payload.ids:
            raise NotFoundError("Provide notification ids, or set 'all' to true.")
        stmt = stmt.where(Notification.id.in_(payload.ids))
    result = db.execute(stmt.values(is_read=True, read_at=now))
    db.commit()
    return Message(message=f"{result.rowcount or 0} notification(s) marked as read.")


@router.delete("/{notification_id}", response_model=Message)
def delete_notification(notification_id: int, db: DbSession,
                        user: CurrentUser) -> Message:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise NotFoundError("Notification not found.")
    db.delete(notification)
    db.commit()
    return Message(message="Notification dismissed.")
