"""Notificaciones internas (campana) del módulo comercial.

Endpoints bajo /api/notifications.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_tenant_db
from app.models import Notification, User
from app.schemas import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(
        Notification.tenant_id == user.tenant_id,
        (Notification.user_id == user.id) | (Notification.user_id.is_(None)),
    )
    if unread_only:
        query = query.filter(Notification.read.is_(False))
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    count = (
        db.query(Notification.id)
        .filter(
            Notification.tenant_id == user.tenant_id,
            (Notification.user_id == user.id) | (Notification.user_id.is_(None)),
            Notification.read.is_(False),
        )
        .count()
    )
    return {"count": count}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    n = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.tenant_id == user.tenant_id,
            (Notification.user_id == user.id) | (Notification.user_id.is_(None)),
        )
        .first()
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    n.read = True
    db.commit()
    db.refresh(n)
    return n


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    (
        db.query(Notification)
        .filter(
            Notification.tenant_id == user.tenant_id,
            (Notification.user_id == user.id) | (Notification.user_id.is_(None)),
            Notification.read.is_(False),
        )
        .update({Notification.read: True}, synchronize_session=False)
    )
    db.commit()
    return {"ok": True}
