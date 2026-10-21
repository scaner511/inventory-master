"""Configuración de la IA de Recepción Inteligente (Puter.js).

La configuración (habilitado, token y modelo) la define el Super Admin por
cliente y vive en la tabla ``tenants`` de la base de plataforma. Estos endpoints
exponen SOLO la config del cliente del usuario autenticado:

- ``GET /api/ai/config``  -> {enabled, token, model} para que el navegador
  inicialice Puter.js con el token del cliente.
- ``GET /api/ai/models``  -> lista de modelos sugeridos (con marca de si son
  gratuitos) para poblar el selector del Super Admin. La lista real se consulta
  en el navegador con ``puter.ai.listModels()``; aquí se devuelve un catálogo
  curado como respaldo cuando no hay token.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Tenant, User
from app.schemas import AiConfigOut, AiModelOut

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Catálogo curado de modelos con visión útiles para OCR/documentos. El sufijo
# ":free" indica variante gratuita (sin costo, con límites del proveedor).
CURATED_MODELS: list[tuple[str, str, bool]] = [
    ("gpt-5.4-nano", "GPT-5.4 Nano (OpenAI)", False),
    ("gpt-4o-mini", "GPT-4o mini (OpenAI)", False),
    ("gpt-4o", "GPT-4o (OpenAI)", False),
    ("google/gemini-2.0-flash", "Gemini 2.0 Flash (Google)", False),
    ("google/gemini-2.0-flash:free", "Gemini 2.0 Flash — GRATIS (Google)", True),
    ("gemini-3-flash-lite", "Gemini 3 Flash Lite (Google)", False),
    ("gemini-3-flash-lite:free", "Gemini 3 Flash Lite — GRATIS (Google)", True),
    ("claude-sonnet-4", "Claude Sonnet 4 (Anthropic)", False),
    ("meta-llama/llama-3.2-11b-vision-instruct", "Llama 3.2 11B Vision (Meta)", False),
    ("meta-llama/llama-3.2-11b-vision-instruct:free", "Llama 3.2 11B Vision — GRATIS (Meta)", True),
]


@router.get("/models", response_model=list[AiModelOut])
def list_ai_models(user: User = Depends(get_current_user)):
    """Catálogo de modelos sugeridos para el selector de IA (Super Admin)."""
    if user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Solo el Super Admin puede ver los modelos")
    return [AiModelOut(id=m, name=n, free=f) for m, n, f in CURATED_MODELS]


@router.get("/config", response_model=AiConfigOut)
def get_ai_config(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Devuelve la config de IA del cliente del usuario autenticado.

    Si el usuario es superadmin (sin tenant), devuelve el estado deshabilitado.
    """
    if user.tenant_id is None:
        return AiConfigOut(enabled=False, token=None, model=None)
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None:
        return AiConfigOut(enabled=False, token=None, model=None)
    token = (tenant.ai_api_key or "").strip() or None
    return AiConfigOut(
        enabled=bool(tenant.ai_enabled) and bool(token),
        token=token,
        model=tenant.ai_model or None,
    )
