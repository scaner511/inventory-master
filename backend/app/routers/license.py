"""Rutas de licencia del sistema."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, license_status, require_admin
from app.utils import licenses as license_service

router = APIRouter(prefix="/api/license", tags=["license"])


class ActivateRequest(BaseModel):
    key: str


class GenerateRequest(BaseModel):
    seed: str | None = None


@router.get("/status")
def status(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return license_status(db)


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


@router.post("/generate")
def generate(
    data: GenerateRequest | None = None,
    db: Session = Depends(get_db),
    _user=Depends(require_admin),
):
    """Genera una clave nueva (solo administradores)."""
    key = license_service.generate_new_key(data.seed if data else "")
    return {"key": key}
