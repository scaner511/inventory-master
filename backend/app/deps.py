"""Dependencias compartidas de FastAPI (autenticación y autorización)."""
from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import License, Setting, Tenant, TenantLicense, User
from app.utils.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Devuelve el usuario autenticado a partir del token JWT."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise unauthorized

    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise unauthorized

    # Si el usuario pertenece a un cliente desactivado, se bloquea el acceso.
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.is_active:
            raise HTTPException(status_code=403, detail="El cliente al que perteneces está desactivado")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Solo administradores de un cliente (tenant)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    """Solo el Super Admin global (crea clientes y administra todo)."""
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Acceso restringido al Super Admin")
    return user


def require_privileged(user: User = Depends(get_current_user)) -> User:
    """Super Admin o administrador de un cliente (acceso a backups/Dirve).

    El Super Admin actúa a nivel global (tenant NULL); el administrador solo
    sobre su propio cliente.
    """
    if user.role not in ("superadmin", "admin"):
        raise HTTPException(status_code=403, detail="Acceso restringido al administrador")
    return user


def get_or_create_settings(db: Session) -> Setting:
    setting = db.get(Setting, 1)
    if setting is None:
        setting = Setting(id=1, company_name="Mi Empresa", low_stock_threshold=settings.low_stock_threshold)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def _license_status_row(db: Session, user: User | None) -> dict:
    """Estado de la licencia a partir de la fila activa (tenant o global)."""
    if user is not None and user.tenant_id is not None:
        lic = (
            db.query(TenantLicense)
            .filter(TenantLicense.tenant_id == user.tenant_id)
            .first()
        )
        if lic is not None:
            days_left = (
                (lic.expires_at - datetime.now().date()).days
                if lic.expires_at
                else 0
            )
            return {
                "required": True,
                "active": bool(lic.is_active and days_left >= 0),
                "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
                "days_left": days_left,
            }
        return {"required": True, "active": False, "expires_at": None, "days_left": 0}

    lic = db.get(License, 1)
    if lic is None or not lic.is_active or lic.expires_at is None:
        return {"required": True, "active": False, "expires_at": None, "days_left": 0}

    days_left = (lic.expires_at - datetime.now().date()).days
    return {
        "required": True,
        "active": days_left >= 0,
        "expires_at": lic.expires_at.isoformat(),
        "days_left": days_left,
    }


def license_status(db: Session, user: User | None = None) -> dict:
    """Devuelve el estado de la licencia: {required, active, expires_at, days_left}.

    La licencia es POR CLIENTE: cada tenant tiene su propia expiración
    (tabla tenant_licenses) y el pago solo extiende la suya. El Super Admin
    es el operador del sistema y NO está sujeto a licencia ni a vencimiento.
    """
    if user is not None and user.role == "superadmin":
        return {"required": False, "active": True, "expires_at": None, "days_left": None}

    return _license_status_row(db, user)


def require_valid_license(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bloquea la app si la licencia del cliente está vencida o no activa.

    El Super Admin (operador del sistema) queda EXENTO: solo los clientes
    (admins y operadores de cada tenant) están sujetos a su propia licencia.
    """
    status_info = license_status(db, user)
    if not status_info["active"]:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "LICENSE_BLOCKED",
                "message": "Licencia vencida o no activada",
                "license": status_info,
            },
        )
    return status_info
