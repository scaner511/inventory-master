"""Calculadora de cotizaciones: enlaces públicos por cliente.

Diseño:
- Cada cliente puede crear hasta ``tenants.calculator_link_limit`` enlaces
  (10 por defecto). Solo el Super Admin puede subir ese límite.
- Cada enlace se vincula a UN dispositivo, y ese vínculo lo aprueba
  manualmente el administrador del cliente.
- El enlace público es ``/calculator/public/<token>``. El navegador envía un
  identificador propio (``device_id``) guardado en localStorage.

Los enlaces viven en la base de PLATAFORMA porque son control de acceso, no
datos de negocio del cliente.
"""
from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import CalculatorLink, Tenant, User
from app.schemas import (
    CalculatorLinkCreate,
    CalculatorLinkExpirationUpdate,
    CalculatorLinkOut,
    CalculatorLinksOut,
    CalculatorProductItem,
    CalculatorPublicAccessIn,
    CalculatorPublicStatusOut,
    calculator_products_from_raw,
    modules_from_raw,
)

DEFAULT_LINK_LIMIT = 10

admin_router = APIRouter(prefix="/api/calculator", tags=["calculator"])
public_router = APIRouter(prefix="/api/calculator/public", tags=["calculator-public"])


def _tenant_limit(tenant: Tenant | None) -> int:
    if tenant is None or not tenant.calculator_link_limit:
        return DEFAULT_LINK_LIMIT
    return int(tenant.calculator_link_limit)


def _used_links(db: Session, tenant_id: int) -> int:
    """Enlaces que ocupan cupo (todos menos los revocados)."""
    return (
        db.query(func.count(CalculatorLink.id))
        .filter(
            CalculatorLink.tenant_id == tenant_id,
            CalculatorLink.status != "revoked",
        )
        .scalar()
        or 0
    )


def _get_link(db: Session, user: User, link_id: int) -> CalculatorLink:
    link = db.get(CalculatorLink, link_id)
    if link is None or link.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    return link


def _clear_device(link: CalculatorLink) -> None:
    link.device_id = None
    link.device_name = None
    link.approved_at = None


def _clear_pending(link: CalculatorLink) -> None:
    link.pending_device_id = None
    link.pending_device_name = None
    link.pending_requested_at = None


def _is_expired(link: CalculatorLink) -> bool:
    """Indica si el enlace tiene fecha de vencimiento y ya expiró."""
    return link.expires_at is not None and datetime.utcnow() >= link.expires_at


def _custom_products(tenant: Tenant | None) -> list[CalculatorProductItem]:
    """Productos personalizados del cliente (vacío si la función está apagada)."""
    if tenant is None or not tenant.calculator_custom_enabled:
        return []
    return calculator_products_from_raw(tenant.calculator_products)


def _generate_token(db: Session) -> str:
    """Token público irrepetible y suficientemente largo para no adivinarse."""
    token = secrets.token_urlsafe(24)
    while db.query(CalculatorLink).filter(CalculatorLink.token == token).first():
        token = secrets.token_urlsafe(24)
    return token


# =============================== ADMIN ===============================


@admin_router.get("/products", response_model=list[CalculatorProductItem])
def list_custom_products(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Productos personalizados de la calculadora del cliente actual.

    Devuelve lista vacía si el Super Admin no habilitó la función para este
    cliente. Solo el Super Admin puede definir el catálogo.
    """
    tenant = db.get(Tenant, user.tenant_id)
    return _custom_products(tenant)


@admin_router.get("/links", response_model=CalculatorLinksOut)
def list_links(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Lista los enlaces del cliente (incluye solicitudes pendientes)."""
    tenant = db.get(Tenant, user.tenant_id)
    links = (
        db.query(CalculatorLink)
        .filter(CalculatorLink.tenant_id == user.tenant_id)
        .order_by(CalculatorLink.created_at.desc())
        .all()
    )
    return CalculatorLinksOut(
        limit=_tenant_limit(tenant),
        used=_used_links(db, user.tenant_id),
        links=links,
    )


@admin_router.post("/links", response_model=CalculatorLinkOut, status_code=201)
def create_link(
    data: CalculatorLinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Crea un enlace nuevo si el cliente aún tiene cupo."""
    tenant = db.get(Tenant, user.tenant_id)
    limit = _tenant_limit(tenant)
    used = _used_links(db, user.tenant_id)
    if used >= limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Alcanzaste el límite de {limit} enlaces públicos. "
                "Solicita al Super Admin que amplíe el límite."
            ),
        )

    label = (data.label or "").strip() or None
    expires_at = (
        datetime.utcnow() + timedelta(days=int(data.expires_in_days))
        if data.expires_in_days is not None
        else None
    )
    link = CalculatorLink(
        tenant_id=user.tenant_id,
        token=_generate_token(db),
        label=label,
        status="available",
        created_by=user.id,
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@admin_router.put("/links/{link_id}/expiration", response_model=CalculatorLinkOut)
def update_link_expiration(
    link_id: int,
    data: CalculatorLinkExpirationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Cambia o renueva la vigencia de un enlace (None = sin vencimiento hasta revocar)."""
    link = _get_link(db, user, link_id)
    if link.status == "revoked":
        raise HTTPException(status_code=400, detail="El enlace está revocado")
    link.expires_at = (
        datetime.utcnow() + timedelta(days=int(data.expires_in_days))
        if data.expires_in_days is not None
        else None
    )
    db.commit()
    db.refresh(link)
    return link


@admin_router.post("/links/{link_id}/approve", response_model=CalculatorLinkOut)
def approve_device(
    link_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Aprueba el dispositivo pendiente y lo vincula al enlace."""
    link = _get_link(db, user, link_id)
    if not link.pending_device_id:
        raise HTTPException(status_code=400, detail="Este enlace no tiene solicitudes pendientes")
    if link.status == "revoked":
        raise HTTPException(status_code=400, detail="El enlace está revocado")

    link.device_id = link.pending_device_id
    link.device_name = link.pending_device_name
    link.status = "active"
    link.approved_at = datetime.utcnow()
    _clear_pending(link)
    db.commit()
    db.refresh(link)
    return link


@admin_router.post("/links/{link_id}/reject", response_model=CalculatorLinkOut)
def reject_device(
    link_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Rechaza la solicitud pendiente; el enlace queda libre para otro equipo."""
    link = _get_link(db, user, link_id)
    _clear_pending(link)
    if link.status == "pending":
        link.status = "available"
    db.commit()
    db.refresh(link)
    return link


@admin_router.post("/links/{link_id}/reset-device", response_model=CalculatorLinkOut)
def reset_device(
    link_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Desvincula el dispositivo actual para poder autorizar otro."""
    link = _get_link(db, user, link_id)
    if link.status == "revoked":
        raise HTTPException(status_code=400, detail="El enlace está revocado")
    _clear_device(link)
    _clear_pending(link)
    link.status = "available"
    db.commit()
    db.refresh(link)
    return link


@admin_router.post("/links/{link_id}/revoke", response_model=CalculatorLinkOut)
def revoke_link(
    link_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Revoca el enlace: deja de permitir acceso y libera cupo."""
    link = _get_link(db, user, link_id)
    link.status = "revoked"
    _clear_device(link)
    _clear_pending(link)
    db.commit()
    db.refresh(link)
    return link


@admin_router.delete("/links/{link_id}", status_code=204)
def delete_link(
    link_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Elimina definitivamente un enlace (útil para limpiar revocados)."""
    link = _get_link(db, user, link_id)
    db.delete(link)
    db.commit()


# =============================== PÚBLICO ===============================


def _public_status(
    link: CalculatorLink,
    tenant: Tenant | None,
    status: str,
    message: str | None = None,
) -> CalculatorPublicStatusOut:
    return CalculatorPublicStatusOut(
        status=status,
        tenant_name=tenant.name if tenant else None,
        label=link.label,
        message=message,
        expires_at=link.expires_at,
        products=_custom_products(tenant),
    )


@public_router.post("/{token}/access", response_model=CalculatorPublicStatusOut)
def public_access(
    token: str,
    data: CalculatorPublicAccessIn,
    db: Session = Depends(get_db),
):
    """Solicita acceso (o consulta el estado) para un dispositivo.

    Es idempotente: el mismo dispositivo puede llamarlo cada pocos segundos
    mientras espera la aprobación del administrador.
    """
    link = db.query(CalculatorLink).filter(CalculatorLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Enlace de calculadora no encontrado")

    tenant = db.get(Tenant, link.tenant_id)
    if tenant is None or not tenant.is_active:
        return _public_status(
            link, tenant, "disabled", "El cliente de este enlace está desactivado."
        )
    if "calculator" not in modules_from_raw(tenant.modules):
        return _public_status(
            link,
            tenant,
            "disabled",
            "La calculadora no está habilitada para este cliente.",
        )
    if link.status == "revoked":
        return _public_status(
            link, tenant, "revoked", "Este enlace fue revocado por el administrador."
        )
    if _is_expired(link):
        return _public_status(
            link, tenant, "expired", "Este enlace venció. Pide al administrador uno nuevo."
        )

    device_id = data.device_id.strip()
    device_name = (data.device_name or "").strip() or None

    if link.status == "active":
        if link.device_id == device_id:
            link.last_seen_at = datetime.utcnow()
            db.commit()
            return _public_status(link, tenant, "active")
        return _public_status(
            link,
            tenant,
            "in_use",
            "Este enlace ya está vinculado a otro dispositivo.",
        )

    # Enlace disponible o con una solicitud pendiente.
    if link.pending_device_id:
        if link.pending_device_id != device_id:
            return _public_status(
                link,
                tenant,
                "in_use",
                "Otro dispositivo ya solicitó este enlace. Espera la decisión del administrador.",
            )
        if device_name and link.pending_device_name != device_name:
            link.pending_device_name = device_name
        link.last_seen_at = datetime.utcnow()
        db.commit()
        return _public_status(
            link,
            tenant,
            "pending",
            "Solicitud enviada. Espera a que el administrador apruebe este dispositivo.",
        )

    link.status = "pending"
    link.pending_device_id = device_id
    link.pending_device_name = device_name
    link.pending_requested_at = datetime.utcnow()
    link.last_seen_at = datetime.utcnow()
    db.commit()
    return _public_status(
        link,
        tenant,
        "pending",
        "Solicitud enviada. Espera a que el administrador apruebe este dispositivo.",
    )


@public_router.get("/{token}/status", response_model=CalculatorPublicStatusOut)
def public_status(
    token: str,
    device_id: str = Query(min_length=8, max_length=128),
    db: Session = Depends(get_db),
):
    """Consulta el estado del enlace SIN reclamarlo (sondeo del navegador).

    El dispositivo solo se registra en ``POST /access``. Este GET permite
    esperar la aprobación o detectar revocaciones/liberaciones sin que un
    equipo desplazado vuelva a solicitar el enlace automáticamente.
    """
    link = db.query(CalculatorLink).filter(CalculatorLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Enlace de calculadora no encontrado")
    tenant = db.get(Tenant, link.tenant_id)
    if tenant is None or not tenant.is_active:
        return _public_status(
            link, tenant, "disabled", "El cliente de este enlace está desactivado."
        )
    if "calculator" not in modules_from_raw(tenant.modules):
        return _public_status(
            link, tenant, "disabled", "La calculadora no está habilitada para este cliente."
        )
    if link.status == "revoked":
        return _public_status(
            link, tenant, "revoked", "Este enlace fue revocado por el administrador."
        )
    if _is_expired(link):
        return _public_status(
            link, tenant, "expired", "Este enlace venció. Pide al administrador uno nuevo."
        )

    device_id = device_id.strip()
    if link.status == "active":
        if link.device_id == device_id:
            return _public_status(link, tenant, "active")
        return _public_status(
            link, tenant, "in_use", "Este enlace ya está vinculado a otro dispositivo."
        )
    if link.pending_device_id:
        if link.pending_device_id == device_id:
            return _public_status(
                link,
                tenant,
                "pending",
                "Solicitud enviada. Espera a que el administrador apruebe este dispositivo.",
            )
        return _public_status(
            link,
            tenant,
            "in_use",
            "Otro dispositivo ya solicitó este enlace. Espera la decisión del administrador.",
        )
    return _public_status(
        link,
        tenant,
        "available",
        "Este enlace no tiene un dispositivo autorizado.",
    )


@public_router.get("/{token}", response_model=CalculatorPublicStatusOut)
def public_info(token: str, db: Session = Depends(get_db)):
    """Datos básicos del enlace (sin revelar el dispositivo vinculado)."""
    link = db.query(CalculatorLink).filter(CalculatorLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Enlace de calculadora no encontrado")
    tenant = db.get(Tenant, link.tenant_id)
    if tenant is None or not tenant.is_active:
        return _public_status(link, tenant, "disabled", "El cliente de este enlace está desactivado.")
    if "calculator" not in modules_from_raw(tenant.modules):
        return _public_status(
            link, tenant, "disabled", "La calculadora no está habilitada para este cliente."
        )
    if link.status == "revoked":
        return _public_status(
            link, tenant, "revoked", "Este enlace fue revocado por el administrador."
        )
    if _is_expired(link):
        return _public_status(
            link, tenant, "expired", "Este enlace venció. Pide al administrador uno nuevo."
        )
    return _public_status(link, tenant, link.status)
