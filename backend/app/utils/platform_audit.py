"""Registro de eventos de PLATAFORMA (cuentas y licencias) del Super Admin.

Vive en la base de la plataforma, separado del historial de negocio
(AuditLog) que cada cliente guarda en SU PROPIA base de datos.
"""
from sqlalchemy.orm import Session

from app.models import PlatformAuditLog


def record_platform_audit(
    db: Session,
    action: str,
    user_id: int | None = None,
    tenant_id: int | None = None,
    detail: str | None = None,
) -> PlatformAuditLog:
    entry = PlatformAuditLog(action=action, user_id=user_id, tenant_id=tenant_id, detail=detail)
    db.add(entry)
    db.commit()
    return entry