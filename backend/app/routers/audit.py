"""Historial de movimientos (auditoría)."""
from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    q: str | None = Query(default=None),
    day: date | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    query = db.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            AuditLog.action.ilike(like)
            | AuditLog.product_name.ilike(like)
            | AuditLog.detail.ilike(like)
        )
    if day:
        start = datetime(day.year, day.month, day.day)
        end = datetime(day.year, day.month, day.day, 23, 59, 59)
        query = query.filter(AuditLog.timestamp >= start, AuditLog.timestamp <= end)

    entries = query.order_by(AuditLog.timestamp.desc()).limit(500).all()

    result = []
    for e in entries:
        username = None
        if e.user_id:
            user = db.get(User, e.user_id)
            username = user.username if user else None
        result.append(
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "username": username,
                "action": e.action,
                "detail": e.detail,
                "product_name": e.product_name,
                "quantity": e.quantity,
            }
        )
    return result


@router.get("/export")
def export_audit(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == user.tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .all()
    )
    data = [
        {
            "ID": r.id,
            "Fecha": r.timestamp,
            "Usuario": r.user_id,
            "Accion": r.action,
            "Producto": r.product_name,
            "Cantidad": r.quantity,
            "Detalle": r.detail,
        }
        for r in rows
    ]
    df = pd.DataFrame(data)
    buffer = io_bytes(df)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="historial_movimientos.xlsx"'},
    )


def io_bytes(df: pd.DataFrame):
    import io

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer
