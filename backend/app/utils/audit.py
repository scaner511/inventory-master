"""Registro de auditoría reutilizable."""
from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    db: Session,
    action: str,
    user_id: int | None,
    detail: str | None = None,
    product_name: str | None = None,
    quantity: int | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        user_id=user_id,
        detail=detail,
        product_name=product_name,
        quantity=quantity,
    )
    db.add(entry)
    db.commit()
    return entry
