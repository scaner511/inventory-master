"""Configuración de la empresa: nombre, logo y umbral de stock."""
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database import get_db
from app.deps import get_current_user, get_or_create_settings, require_superadmin
from app.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_LOGO_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class SettingsUpdate(BaseModel):
    company_name: str | None = None
    low_stock_threshold: int | None = None


class SecurityQuestionUpdate(BaseModel):
    question: str
    answer: str


class SettingsOut(BaseModel):
    company_name: str | None
    low_stock_threshold: int
    logo_url: str | None = None
    has_logo: bool = False


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    setting = get_or_create_settings(db)
    return SettingsOut(
        company_name=setting.company_name,
        low_stock_threshold=setting.low_stock_threshold,
        has_logo=bool(setting.logo_path),
        logo_url=f"/api/settings/logo" if setting.logo_path else None,
    )


@router.put("", response_model=SettingsOut)
def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_superadmin),
):
    setting = get_or_create_settings(db)
    if data.company_name is not None:
        setting.company_name = data.company_name
    if data.low_stock_threshold is not None:
        if data.low_stock_threshold < 1:
            raise HTTPException(status_code=400, detail="El umbral de stock debe ser al menos 1")
        setting.low_stock_threshold = data.low_stock_threshold
    db.commit()
    return SettingsOut(
        company_name=setting.company_name,
        low_stock_threshold=setting.low_stock_threshold,
        has_logo=bool(setting.logo_path),
        logo_url=f"/api/settings/logo" if setting.logo_path else None,
    )


@router.post("/logo")
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(require_superadmin),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_LOGO_EXT:
        raise HTTPException(status_code=400, detail="Formato de imagen no permitido (usa PNG, JPG, JPEG, BMP o WEBP)")

    filename = f"logo_{uuid.uuid4().hex}{ext}"
    dest = app_settings.uploads_path / filename
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    setting = get_or_create_settings(db)
    setting.logo_path = str(dest)
    db.commit()
    return {"message": "Logo configurado correctamente", "logo_url": "/api/settings/logo"}


@router.get("/logo")
def get_logo(db: Session = Depends(get_db)):
    setting = get_or_create_settings(db)
    if not setting.logo_path or not Path(setting.logo_path).exists():
        raise HTTPException(status_code=404, detail="No hay logo configurado")
    return FileResponse(setting.logo_path)


@router.put("/security-question", status_code=200)
def set_security_question(
    data: SecurityQuestionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permite al usuario configurar su pregunta de seguridad para recuperar la contraseña."""
    if len(data.answer.strip()) < 2:
        raise HTTPException(status_code=400, detail="La respuesta debe tener al menos 2 caracteres")
    user.security_question = data.question.strip()
    user.security_answer = data.answer.strip().lower()
    db.commit()
    return {"message": "Pregunta de seguridad guardada correctamente."}
