"""Historial de movimientos (auditoría) de UN cliente.

Los registros viven en la base de datos del cliente. Los nombres de usuario
se resuelven desde la base de la PLATAFORMA (los usuarios de negocio no
comparten base con el cliente).
"""
from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal as PlatformSessionLocal
from app.deps import get_tenant_db, require_admin
from app.models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _username_map(user_ids: set[int]) -> dict[int, str | None]:
    """Resuelve los nombres de usuario (plataforma) para los ids dados."""
    if not user_ids:
        return {}
    pldb = PlatformSessionLocal()
    try:
        rows = pldb.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
    finally:
        pldb.close()
    return {r[0]: r[1] for r in rows}


@router.get("")
def list_audit(
    q: str | None = Query(default=None),
    day: date | None = Query(default=None),
    db: Session = Depends(get_tenant_db),
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

    usernames = _username_map({e.user_id for e in entries if e.user_id})
    result = []
    for e in entries:
        result.append(
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "username": usernames.get(e.user_id),
                "action": e.action,
                "detail": e.detail,
                "product_name": e.product_name,
                "quantity": e.quantity,
            }
        )
    return result


@router.get("/export")
def export_audit(db: Session = Depends(get_tenant_db), user: User = Depends(require_admin)):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == user.tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .all()
    )
    usernames = _username_map({r.user_id for r in rows if r.user_id})
    data = [
        {
            "ID": r.id,
            "Fecha": r.timestamp,
            "Usuario": usernames.get(r.user_id, f"id {r.user_id}" if r.user_id else ""),
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