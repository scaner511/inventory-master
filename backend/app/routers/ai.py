"""Configuración de la IA de Recepción Inteligente.

La configuración (habilitado, proveedor, token y modelo) la define el Super
Admin por cliente y vive en la tabla ``tenants`` de la base de plataforma. Estos
endpoints exponen SOLO la config del cliente del usuario autenticado:

- ``GET /api/ai/config``  -> {enabled, provider, token, model} para que el
  navegador llame al proveedor (Puter o Gemini) con el token del cliente.
- ``GET /api/ai/models``  -> lista de modelos sugeridos (con marca de si son
  gratuitos) para poblar el selector del Super Admin.

Proveedores soportados:
- ``puter``  : token personal de puter.com (llegada REST a api.puter.com).
- ``gemini`` : API key de Google AI Studio (generativelanguage.googleapis.com).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Tenant, User
from app.schemas import AiConfigOut, AiModelOut

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Catálogo curado de modelos con visión útiles para OCR/documentos.
# El sufijo ":free" indica variante gratuita (sin costo, con límites).
CURATED_MODELS: list[tuple[str, str, str, bool]] = [
    # Puter (ids de la pasarela api.puter.com)
    ("google/gemini-3.8-flash", "Gemini 3.8 Flash (Puter)", "puter", False),
    ("google/gemini-2.0-flash:free", "Gemini 2.0 Flash — GRATIS (Puter)", "puter", True),
    ("gpt-5.4-nano", "GPT-5.4 Nano (Puter)", "puter", False),
    ("gpt-4o-mini", "GPT-4o mini (Puter)", "puter", False),
    ("meta-llama/llama-3.2-11b-vision-instruct:free", "Llama 3.2 11B Vision — GRATIS (Puter)", "puter", True),
    # Gemini directo (ids de Google AI Studio)
    ("gemini-2.5-flash", "Gemini 2.5 Flash (Google)", "gemini", False),
    ("gemini-2.0-flash", "Gemini 2.0 Flash (Google)", "gemini", False),
    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite (Google)", "gemini", False),
]

VALID_PROVIDERS = ("puter", "gemini")


@router.get("/models", response_model=list[AiModelOut])
def list_ai_models(user: User = Depends(get_current_user)):
    """Catálogo de modelos sugeridos para el selector de IA (Super Admin)."""
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Solo el Super Admin puede ver los modelos")
    return [AiModelOut(id=m, name=n, provider=p, free=f) for m, n, p, f in CURATED_MODELS]


@router.get("/config", response_model=AiConfigOut)
def get_ai_config(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Devuelve la config de IA del cliente del usuario autenticado.

    Si el usuario es superadmin (sin tenant), devuelve el estado deshabilitado.
    """
    if user.tenant_id is None:
        return AiConfigOut(enabled=False, provider=None, token=None, model=None)
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        return AiConfigOut(enabled=False, provider=None, token=None, model=None)
    provider = (tenant.ai_provider or "puter").strip().lower()
    if provider not in VALID_PROVIDERS:
        provider = "puter"
    token = (tenant.ai_api_key or "").strip() or None
    return AiConfigOut(
        enabled=bool(tenant.ai_enabled) and bool(token),
        provider=provider,
        token=token,
        model=tenant.ai_model or None,
    )
