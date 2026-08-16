"""Rutas de licencia del sistema."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, license_status
from app.models import License
from app.utils import licenses as license_service
from app.utils import offline_license

router = APIRouter(prefix="/api/license", tags=["license"])


class ActivateRequest(BaseModel):
    key: str


class OfflineActivateRequest(BaseModel):
    key: str


def _get_or_create_machine_code(db: Session) -> str:
    """Devuelve el código de activación almacenado en la BD.

    Si la columna ``machine_code`` está vacía (base antigua o primera vez),
    lo calcula una vez a partir del hardware y lo guarda para siempre.
    Esto evita que el código cambie si el servidor (p. ej. Render) cambia
    de instancia entre reinicios.
    """
    lic = db.get(License, 1)
    if lic is None:
        lic = License(id=1)
        db.add(lic)
    if not lic.machine_code:
        lic.machine_code = offline_license.get_activation_code()
        db.commit()
    return lic.machine_code


@router.get("/status")
def status(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return license_status(db)


@router.get("/machine-code")
def machine_code(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Código de activación de este equipo para la licencia offline."""
    return {"code": _get_or_create_machine_code(db)}


@router.post("/offline/activate")
def activate_offline(
    data: OfflineActivateRequest,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Valida y activa una licencia offline ligada a este equipo (HMAC-SHA256)."""
    result = offline_license.validate_license(
        data.key,
        activation_code=_get_or_create_machine_code(db),
    )
    if not result["valid"]:
        reason = {
            "formato_invalido": "Formato de clave inválido. Debe ser: LIC.<datos>.<firma>",
            "firma_invalida": "La firma de la clave es inválida.",
            "codigo_no_coincide": "La clave no corresponde a este equipo.",
            "expirada": "La licencia ya expiró.",
        }.get(result["reason"], "Clave inválida.")
        raise HTTPException(status_code=400, detail=reason)

    lic = db.get(License, 1)
    if lic is None:
        lic = License(id=1)
        db.add(lic)
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
    result = license_service.activate_license(db, data.key)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Licencia activada correctamente", "expires_at": result["expires_at"]}