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
from app.deps import get_current_user, get_or_create_settings, get_tenant_db, require_privileged
from app.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_LOGO_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class SettingsUpdate(BaseModel):
    company_name: str | None = None
    low_stock_threshold: int | None = None
    warehouse1_name: str | None = None
    warehouse2_name: str | None = None
    warehouse3_name: str | None = None
    # ITBIS (%) de la calculadora de cotizaciones (0 a 100).
    itbis_rate: float | None = None
    # Código ISO de la moneda (DOP, USD, EUR, MXN...).
    currency: str | None = None


class SecurityQuestionUpdate(BaseModel):
    question: str
    answer: str


class SettingsOut(BaseModel):
    company_name: str | None
    low_stock_threshold: int
    warehouse1_name: str
    warehouse2_name: str
    warehouse3_name: str
    itbis_rate: float = 18
    currency: str = "DOP"
    logo_url: str | None = None
    has_logo: bool = False


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    setting = get_or_create_settings(db, user.tenant_id)
    return SettingsOut(
        company_name=setting.company_name,
        low_stock_threshold=setting.low_stock_threshold,
        warehouse1_name=setting.warehouse1_name or "Almacén Principal",
        warehouse2_name=setting.warehouse2_name or "Vehículo",
        warehouse3_name=setting.warehouse3_name or "Almacén Secundario",
        itbis_rate=float(setting.itbis_rate) if setting.itbis_rate is not None else 18,
        currency=(setting.currency or "DOP").strip().upper() or "DOP",
        has_logo=bool(setting.logo_path),
        logo_url=f"/api/settings/logo" if setting.logo_path else None,
    )


@router.put("", response_model=SettingsOut)
def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_privileged),
):
    setting = get_or_create_settings(db, user.tenant_id)
    if data.company_name is not None:
        setting.company_name = data.company_name
    if data.low_stock_threshold is not None:
        if data.low_stock_threshold < 1:
            raise HTTPException(status_code=400, detail="El umbral de stock debe ser al menos 1")
        setting.low_stock_threshold = data.low_stock_threshold
    if data.warehouse1_name is not None:
        setting.warehouse1_name = data.warehouse1_name.strip() or "Almacén Principal"
    if data.warehouse2_name is not None:
        setting.warehouse2_name = data.warehouse2_name.strip() or "Vehículo"
    if data.warehouse3_name is not None:
        setting.warehouse3_name = data.warehouse3_name.strip() or "Almacén Secundario"
    if data.itbis_rate is not None:
        if not 0 <= data.itbis_rate <= 100:
            raise HTTPException(status_code=400, detail="El ITBIS debe estar entre 0 y 100")
        setting.itbis_rate = data.itbis_rate
    if data.currency is not None:
        code = data.currency.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise HTTPException(status_code=400, detail="La moneda debe ser un código ISO de 3 letras (ej. DOP, USD)")
        setting.currency = code
    db.commit()
    return SettingsOut(
        company_name=setting.company_name,
        low_stock_threshold=setting.low_stock_threshold,
        warehouse1_name=setting.warehouse1_name or "Almacén Principal",
        warehouse2_name=setting.warehouse2_name or "Vehículo",
        warehouse3_name=setting.warehouse3_name or "Almacén Secundario",
        itbis_rate=float(setting.itbis_rate) if setting.itbis_rate is not None else 18,
        currency=(setting.currency or "DOP").strip().upper() or "DOP",
        has_logo=bool(setting.logo_path),
        logo_url=f"/api/settings/logo" if setting.logo_path else None,
    )


@router.post("/logo")
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_privileged),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_LOGO_EXT:
        raise HTTPException(status_code=400, detail="Formato de imagen no permitido (usa PNG, JPG, JPEG, BMP o WEBP)")

    filename = f"logo_{uuid.uuid4().hex}{ext}"
    dest = app_settings.uploads_path / filename
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    setting = get_or_create_settings(db, user.tenant_id)
    setting.logo_path = str(dest)
    db.commit()
    return {"message": "Logo configurado correctamente", "logo_url": "/api/settings/logo"}


@router.get("/logo")
def get_logo(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    setting = get_or_create_settings(db, user.tenant_id)
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
