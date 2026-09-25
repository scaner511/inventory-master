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

    # Sesión única: el token debe pertenecer a la sesión activa actual del
    # usuario. Si la sesión fue cerrada (logout) o reemplazada por otro equipo,
    # el token deja de ser válido de inmediato.
    session_id = payload.get("session_id")
    if user.active_session and session_id != user.active_session:
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


def get_or_create_settings(db: Session, tenant_id: int | None = None) -> Setting:
    """Devuelve (y crea si falta) la configuración de un cliente (tenant).

    ``tenant_id=None`` corresponde al Super Admin global (fila id=1 y valores
    de ejemplo copiados a los tenants nuevos).
    """
    setting = (
        db.query(Setting).filter(Setting.tenant_id == tenant_id).order_by(Setting.id).first()
    )
    if setting is None:
        base = db.query(Setting).filter(Setting.tenant_id.is_(None)).order_by(Setting.id).first()
        setting = Setting(
            tenant_id=tenant_id,
            company_name=base.company_name if base else "Mi Empresa",
            logo_path=base.logo_path if base else None,
            low_stock_threshold=base.low_stock_threshold if base else settings.low_stock_threshold,
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def license_status(db: Session, user: User | None = None) -> dict:
    """Devuelve el estado de la licencia: {required, active, expires_at, days_left}.

    El Super Admin es el operador del sistema y NO está sujeto a licencia
    ni a vencimiento.
    """
    if user is not None and user.role == "superadmin":
        return {"required": False, "active": True, "expires_at": None, "days_left": None}

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


def require_valid_license(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bloquea la app si la licencia está vencida o no activa.

    El Super Admin (operador del sistema) queda EXENTO: solo los clientes
    (admins y operadores de cada tenant) están sujetos a la licencia.
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
