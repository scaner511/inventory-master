"""Rutas de licencia del sistema (por cliente/tenant)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, license_status
from app.models import TenantLicense, User
from app.utils import licenses as license_service
from app.utils import offline_license

router = APIRouter(prefix="/api/license", tags=["license"])


class ActivateRequest(BaseModel):
    key: str


class OfflineActivateRequest(BaseModel):
    key: str


def _target_row(db: Session, user: User) -> TenantLicense:
    """Licencia objetivo del usuario: la de SU cliente (tenant).

    El Super Admin (sin tenant) no necesita licencia; estas rutas solo se
    usan por clientes, pero por robustez si no hay tenant se devuelve None
    y las rutas no hacen nada.
    """
    if user.tenant_id is None:
        return None  # superadmin / operador global: sin licencia por tenant
    return license_service.get_or_create_tenant_license(db, user.tenant_id)


def _machine_code(db: Session, user: User) -> str:
    """Código de activación del equipo/grupo del cliente (semilla global)."""
    return license_service.global_machine_code(db)


@router.get("/status")
def status(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return license_status(db, _user)


@router.get("/machine-code")
def machine_code(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Código de activación de este equipo para la licencia offline."""
    return {"code": _machine_code(db, _user)}


@router.post("/offline/activate")
def activate_offline(
    data: OfflineActivateRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Valida y activa la licencia offline del cliente (HMAC-SHA256)."""
    result = offline_license.validate_license(
        data.key,
        activation_code=_machine_code(db, _user),
    )
    if not result["valid"]:
        reason = {
            "formato_invalido": "Formato de clave inválido. Debe ser: LIC.<datos>.<firma>",
            "firma_invalida": "La firma de la clave es inválida.",
            "codigo_no_coincide": "La clave no corresponde a este equipo.",
            "expirada": "La licencia ya expiró.",
        }.get(result["reason"], "Clave inválida.")
        raise HTTPException(status_code=400, detail=reason)

    lic = _target_row(db, _user)
    if lic is None:
        raise HTTPException(status_code=400, detail="Este usuario no tiene licencia de cliente")
    lic.is_active = True
    lic.activated_at = datetime.now()
    lic.expires_at = date.fromisoformat(result["expires_at"])
    lic.last_key = data.key.strip()
    db.commit()

    return {
        "message": "Licencia activada correctamente",
        "expires_at": result["expires_at"],
        "days_left": result["days_left"],
    }


@router.post("/activate")
def activate(
    data: ActivateRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = license_service.activate_license(db, data.key, tenant_id=_user.tenant_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Licencia activada correctamente", "expires_at": result["expires_at"]}