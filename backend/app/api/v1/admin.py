"""Audit log access and system-level reference data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.models.identity import User
from app.core.rbac import P, ROLE_PERMISSIONS
from app.models.enums import Role
from app.models.system import AuditLog
from app.schemas.admin import AuditLogOut
from app.schemas.common import Page

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def audit_logs(
    db: DbSession,
    entity_type: str | None = Query(None),
    action: str | None = Query(None),
    actor_user_id: int | None = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
    _: User = Depends(require_permission(P["AUDIT_VIEW"])),
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    return Page[AuditLogOut](
        items=[
            AuditLogOut(
                id=r.id, actor_user_id=r.actor_user_id, actor_label=r.actor_label,
                action=r.action.value, entity_type=r.entity_type, entity_id=r.entity_id,
                description=r.description, meta=r.meta or {}, ip_address=r.ip_address,
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=total, page=page, page_size=page_size,
    )


@router.get("/permissions")
def permission_matrix(
    _: User = Depends(require_permission(P["SYSTEM_ADMIN"])),
) -> dict:
    """The authoritative role→permission matrix the backend enforces.

    Distinct from `/admin/roles`, which lists *who* holds which scoped
    coordinator role.
    """
    return {
        "roles": [
            {
                "role": role.value,
                "permissions": sorted(perms) if "*" not in perms else ["*"],
            }
            for role, perms in ROLE_PERMISSIONS.items()
        ],
        "all_permissions": sorted(P.values()),
    }
