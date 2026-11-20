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
from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, get_tenant_session
from app.deps import get_current_user, get_tenant_db, require_admin
from app.models import (
    Appointment,
    CalculatorLink,
    Prospect,
    ProspectActivity,
    ProspectHistory,
    Setting,
    Tenant,
    User,
    VisitEvent,
)
from app.schemas import (
    CalculatorLinkBulkCreate,
    CalculatorLinkCreate,
    CalculatorLinkExpirationUpdate,
    CalculatorLinkOut,
    CalculatorLinksOut,
    CalculatorProductItem,
    CalculatorProspectMini,
    CalculatorVisitIn,
    CalculatorVisitOut,
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


def _money_config(tenant: Tenant | None) -> tuple[float, str]:
    """ITBIS (%) y moneda del cliente (configuración de su base de negocio)."""
    if tenant is None:
        return 18.0, "DOP"
    try:
        tdb = get_tenant_session(tenant.id)
        try:
            row = (
                tdb.query(Setting)
                .filter(Setting.tenant_id == tenant.id)
                .order_by(Setting.id)
                .first()
            )
            if row is None:
                return 18.0, "DOP"
            itbis = float(row.itbis_rate) if row.itbis_rate is not None else 18.0
            currency = (row.currency or "DOP").strip().upper() or "DOP"
            return itbis, currency
        finally:
            tdb.close()
    except Exception:
        return 18.0, "DOP"


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


@admin_router.post("/links/bulk", response_model=list[CalculatorLinkOut], status_code=201)
def create_links_bulk(
    data: CalculatorLinkBulkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Genera varios enlaces de una vez (redes de vendedores, sucursales).

    Crea hasta el cupo disponible del cliente; si se piden más de los que
    quedan, solo genera los que caben. Las etiquetas quedan numeradas
    ("<prefijo> 001", "<prefijo> 002", ...) para identificarlas.
    """
    tenant = db.get(Tenant, user.tenant_id)
    limit = _tenant_limit(tenant)
    used = _used_links(db, user.tenant_id)
    count = min(int(data.count), max(limit - used, 0))
    if count <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"No quedan enlaces disponibles (límite {limit}, usados {used}).",
        )

    prefix = (data.label_prefix or "").strip()
    expires_at = (
        datetime.utcnow() + timedelta(days=int(data.expires_in_days))
        if data.expires_in_days is not None
        else None
    )

    links = []
    for i in range(count):
        number = used + i + 1
        label = f"{prefix} {number:03d}".strip() if prefix else f"Enlace {number:03d}"
        link = CalculatorLink(
            tenant_id=user.tenant_id,
            token=_generate_token(db),
            label=label[:120],
            status="available",
            created_by=user.id,
            expires_at=expires_at,
        )
        db.add(link)
        links.append(link)

    db.commit()
    for link in links:
        db.refresh(link)
    return links


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
    itbis_rate, currency = _money_config(tenant)
    return CalculatorPublicStatusOut(
        status=status,
        tenant_name=tenant.name if tenant else None,
        label=link.label,
        message=message,
        expires_at=link.expires_at,
        products=_custom_products(tenant),
        itbis_rate=itbis_rate,
        currency=currency,
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


# ===================== VISITA / SINCRONIZACIÓN CRM =====================


def _digits_only(value: str | None) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def _phone_key(phone: str | None) -> str | None:
    """Clave normalizada de teléfono: últimos 10 dígitos (o None si es muy corto)."""
    d = _digits_only(phone)
    if len(d) < 7:
        return None
    return d[-10:]


def _find_prospect_by_phone(tdb: Session, tenant_id: int, phone: str | None) -> Prospect | None:
    """Busca un prospecto cuyo teléfono coincida (ignorando formato)."""
    key = _phone_key(phone)
    if not key:
        return None
    candidates = (
        tdb.query(Prospect)
        .filter(Prospect.tenant_id == tenant_id, Prospect.phone.isnot(None))
        .all()
    )
    for p in candidates:
        if _phone_key(p.phone) == key:
            return p
    return None


def _search_prospects(tdb: Session, tenant_id: int, q: str, limit: int = 15) -> list[Prospect]:
    like = f"%{q.strip()}%"
    return (
        tdb.query(Prospect)
        .filter(Prospect.tenant_id == tenant_id)
        .filter(Prospect.full_name.ilike(like) | Prospect.phone.ilike(like))
        .order_by(Prospect.updated_at.desc())
        .limit(limit)
        .all()
    )


def _prospect_mini(p: Prospect) -> CalculatorProspectMini:
    return CalculatorProspectMini(
        id=p.id, full_name=p.full_name, phone=p.phone, stage_slug=p.stage_slug
    )


def _resolve_visit_prospect(
    tdb: Session,
    tenant_id: int,
    actor_id: int | None,
    data: CalculatorVisitIn,
    seller_label: str | None = None,
) -> tuple[Prospect, bool]:
    """Localiza el prospecto de la visita o lo crea si no existe.

    Devuelve (prospecto, creado_nuevo).
    """
    if data.prospect_id:
        p = (
            tdb.query(Prospect)
            .filter(Prospect.id == data.prospect_id, Prospect.tenant_id == tenant_id)
            .first()
        )
        if p is None:
            raise HTTPException(status_code=404, detail="Prospecto no encontrado")
        return p, False

    p = _find_prospect_by_phone(tdb, tenant_id, data.client_phone)
    if p is not None:
        return p, False

    name = (data.client_name or "").strip()
    phone = (data.client_phone or "").strip() or None
    if not name:
        name = f"Cliente {phone}" if phone else "Cliente calculadora"
    p = Prospect(
        tenant_id=tenant_id,
        full_name=name[:200],
        phone=phone,
        status="nuevo",
        commercial_status="nuevo",
        stage_slug="nuevo",
        owner_id=actor_id,
        created_by=actor_id,
        prospector_name=(seller_label or "")[:120] or None,
    )
    tdb.add(p)
    tdb.flush()
    tdb.add(
        ProspectHistory(
            tenant_id=tenant_id,
            prospect_id=p.id,
            user_id=actor_id,
            action="PROSPECTO_CREADO",
            detail=f"Prospecto '{p.full_name}' creado desde la calculadora",
        )
    )
    return p, True


def _register_visit(
    tdb: Session,
    tenant_id: int,
    actor_id: int | None,
    data: CalculatorVisitIn,
    *,
    seller_label: str,
    link_id: int | None = None,
    device_id: str | None = None,
    user_id: int | None = None,
) -> CalculatorVisitOut:
    """Registra el resultado de una visita en el CRM del cliente.

    - ``compra``: marca el prospecto como cliente convertido (etapa "cliente").
    - ``reagendado``: crea una cita en el calendario y programa el seguimiento.
    En ambos casos queda una actividad de visita y una entrada en el historial.
    """
    prospect, created = _resolve_visit_prospect(tdb, tenant_id, actor_id, data, seller_label)
    now = datetime.utcnow()
    note = (data.note or "").strip() or None
    total_txt = (
        f" · cotización {data.quote_total:,.2f}" if data.quote_total else ""
    )

    tdb.add(
        ProspectActivity(
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            kind="visita",
            done_at=now,
            observation=note,
            result=data.result,
            status="realizada",
            user_id=actor_id,
            created_by=actor_id,
        )
    )

    # Evento para el Reporte Mensual: atribuye la visita al vendedor/enlace.
    tdb.add(
        VisitEvent(
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            seller_label=seller_label[:160],
            link_id=link_id,
            device_id=(device_id or "").strip()[:128] or None,
            user_id=user_id,
            result=data.result,
            quote_total=float(data.quote_total) if data.quote_total else None,
            note=note,
        )
    )

    appointment_id = None
    if data.result == "compra":
        prospect.status = "cliente_convertido"
        prospect.commercial_status = "cliente_convertido"
        prospect.stage_slug = "cliente"
        prospect.converted_at = now
        prospect.converted_by = actor_id
        prospect.close_probability = 100
        if data.quote_total:
            prospect.setup_value = float(data.quote_total)
        action = "VISITA_COMPRA"
        detail = f"El cliente compró durante la visita{total_txt}"
    else:
        if data.reschedule_at is None:
            raise HTTPException(
                status_code=400, detail="Indica la fecha y hora para reagendar"
            )
        start = data.reschedule_at
        if start.tzinfo is not None:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        end = start + timedelta(hours=1)
        appt = Appointment(
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            start_at=start,
            end_at=end,
            user_id=actor_id,
            address=prospect.address,
            phone=prospect.phone,
            observation=note or "Visita reagendada desde la calculadora",
            status="programada",
            created_by=actor_id,
        )
        tdb.add(appt)
        tdb.flush()
        appointment_id = appt.id
        prospect.next_followup_at = start
        if prospect.stage_slug not in ("cliente", "no_interesado"):
            prospect.stage_slug = "cita_programada"
        action = "VISITA_REAGENDADA"
        detail = f"Visita reagendada para {start.strftime('%d/%m/%Y %H:%M')}"

    prospect.summary = detail + "."
    tdb.add(
        ProspectHistory(
            tenant_id=tenant_id,
            prospect_id=prospect.id,
            user_id=actor_id,
            action=action,
            detail=detail,
        )
    )
    tdb.commit()
    return CalculatorVisitOut(
        prospect_id=prospect.id,
        prospect_name=prospect.full_name,
        result=data.result,
        appointment_id=appointment_id,
        created_prospect=created,
    )


# ---- Autenticados (panel interno) ----


@admin_router.get("/prospects", response_model=list[CalculatorProspectMini])
def search_calculator_prospects(
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=15, ge=1, le=30),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Busca prospectos por nombre o teléfono para vincularlos a la visita."""
    return [_prospect_mini(p) for p in _search_prospects(db, user.tenant_id, q, limit)]


@admin_router.post("/visit", response_model=CalculatorVisitOut)
def register_calculator_visit(
    data: CalculatorVisitIn,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Registra desde la calculadora si el cliente compró o se reagendó."""
    return _register_visit(
        db,
        user.tenant_id,
        user.id,
        data,
        seller_label=user.username,
        user_id=user.id,
    )


# ---- Públicos (enlace + dispositivo autorizado) ----


def _public_device_link(db: Session, token: str, device_id: str | None) -> tuple[CalculatorLink, Tenant]:
    """Valida token + dispositivo autorizado para los endpoints de visita."""
    link = db.query(CalculatorLink).filter(CalculatorLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Enlace de calculadora no encontrado")
    tenant = db.get(Tenant, link.tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=403, detail="El cliente de este enlace está desactivado.")
    if "calculator" not in modules_from_raw(tenant.modules):
        raise HTTPException(status_code=403, detail="La calculadora no está habilitada para este cliente.")
    if link.status == "revoked":
        raise HTTPException(status_code=403, detail="Este enlace fue revocado por el administrador.")
    if _is_expired(link):
        raise HTTPException(status_code=403, detail="Este enlace venció. Pide al administrador uno nuevo.")
    if link.status != "active" or not device_id or link.device_id != device_id.strip():
        raise HTTPException(
            status_code=403,
            detail="Este enlace no tiene un dispositivo autorizado activo.",
        )
    return link, tenant


@public_router.get("/{token}/prospects", response_model=list[CalculatorProspectMini])
def public_search_prospects(
    token: str,
    q: str = Query(min_length=2, max_length=120),
    device_id: str = Query(min_length=8, max_length=128),
    db: Session = Depends(get_db),
):
    """Búsqueda de prospectos desde un enlace público (dispositivo autorizado)."""
    _link, tenant = _public_device_link(db, token, device_id)
    tdb = get_tenant_session(tenant.id)
    try:
        return [_prospect_mini(p) for p in _search_prospects(tdb, tenant.id, q)]
    finally:
        tdb.close()


@public_router.post("/{token}/visit", response_model=CalculatorVisitOut)
def public_register_visit(
    token: str,
    data: CalculatorVisitIn,
    db: Session = Depends(get_db),
):
    """Registra la visita desde el enlace público (dispositivo autorizado)."""
    link, tenant = _public_device_link(db, token, data.device_id)
    tdb = get_tenant_session(tenant.id)
    try:
        seller_label = (link.label or "").strip() or f"Enlace #{link.id}"
        return _register_visit(
            tdb,
            tenant.id,
            link.created_by,
            data,
            seller_label=seller_label,
            link_id=link.id,
            device_id=data.device_id,
        )
    finally:
        tdb.close()
