"""Dependencias compartidas de FastAPI (autenticación y autorización)."""
from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import License, Setting, Tenant, User
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

    # Si el usuario pertenece a un proveedor desactivado, se bloquea el acceso.
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.is_active:
            raise HTTPException(status_code=403, detail="El proveedor al que perteneces está desactivado")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Solo administradores de un proveedor (tenant)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    """Solo el Super Admin global (crea proveedores y administra todo)."""
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Acceso restringido al Super Admin")
    return user


def get_or_create_settings(db: Session) -> Setting:
    setting = db.get(Setting, 1)
    if setting is None:
        setting = Setting(id=1, company_name="Mi Empresa", low_stock_threshold=settings.low_stock_threshold)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def license_status(db: Session) -> dict:
    """Devuelve el estado de la licencia: {required, active, expires_at, days_left}."""
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


def require_valid_license(db: Session = Depends(get_db)):
    """Bloquea la app si la licencia está vencida o no activa."""
    status_info = license_status(db)
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
