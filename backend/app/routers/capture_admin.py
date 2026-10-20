"""Router administrativo + jornada + dashboard del módulo Captación Pública.

Endpoints bajo /api/capture (requieren JWT de usuario del tenant):
- Campañas (CRUD), Premios (CRUD), Configuración.
- Jornadas: iniciar / finalizar / listar.
- Dashboard, estadísticas y reportes (PDF/Excel/CSV), auditoría.
"""
import io
from datetime import date, datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.deps import get_current_user, get_tenant_db, require_admin
from app.models import (
    CaptureCampaign,
    CaptureConfig,
    CaptureEntry,
    CaptureHistory,
    CapturePrize,
    Prospect,
    PublicCaptureSession,
    Setting,
    User,
)
from app.schemas import (
    CaptureCampaignCreate,
    CaptureCampaignOut,
    CaptureCampaignUpdate,
    CaptureCaptureHistoryOut,
    CaptureConfigOut,
    CaptureConfigUpdate,
    CaptureDashboardOut,
    CaptureEntryOut,
    CapturePrizeCreate,
    CapturePrizeOut,
    CapturePrizeUpdate,
    CaptureSessionCreate,
    CaptureSessionOut,
    CaptureSessionStartOut,
)
from app.services import capture as services

router = APIRouter(prefix="/api/capture", tags=["capture"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MEDIA = "text/csv"


def _client_ip(request: Request) -> str | None:
    if request.client:
        return request.client.host
    return None


def _user_display(user: User) -> str:
    """Nombre para mostrar del usuario (no hay full_name; usamos username)."""
    return user.username


def _platform_user_name(user_id: int) -> str | None:
    """Nombre del usuario según la base de PLATAFORMA (users vive ahí, no en el negocio)."""
    from app.database import SessionLocal

    pdb = SessionLocal()
    try:
        u = pdb.get(User, user_id)
        if u is None:
            return None
        return u.username
    finally:
        pdb.close()


def _campaign_or_404(db: Session, campaign_id: int, tenant_id: int) -> CaptureCampaign:
    c = (
        db.query(CaptureCampaign)
        .filter(CaptureCampaign.id == campaign_id, CaptureCampaign.tenant_id == tenant_id)
        .first()
    )
    if c is None:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    return c


def _prize_or_404(db: Session, prize_id: int, tenant_id: int) -> CapturePrize:
    p = (
        db.query(CapturePrize)
        .filter(CapturePrize.id == prize_id, CapturePrize.tenant_id == tenant_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Premio no encontrado")
    return p


# --------------------------------------------------------------------------- #
# Campañas
# --------------------------------------------------------------------------- #
@router.get("/campaigns", response_model=list[CaptureCampaignOut])
def list_campaigns(
    status: str | None = Query(default=None),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    q = db.query(CaptureCampaign).filter(CaptureCampaign.tenant_id == user.tenant_id)
    if status:
        q = q.filter(CaptureCampaign.status == status)
    return q.order_by(CaptureCampaign.created_at.desc()).all()


@router.post("/campaigns", response_model=CaptureCampaignOut, status_code=201)
def create_campaign(
    data: CaptureCampaignCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    obj = CaptureCampaign(
        tenant_id=user.tenant_id, created_by=user.id,
        **data.model_dump(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="CAMPAÑA_CREADA",
        detail=obj.name, user_id=user.id, user_name=_user_display(user),
    )
    db.commit()
    return obj


@router.put("/campaigns/{campaign_id}", response_model=CaptureCampaignOut)
def update_campaign(
    campaign_id: int,
    data: CaptureCampaignUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    obj = _campaign_or_404(db, campaign_id, user.tenant_id)
    before = obj.status
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    detail = obj.name
    if before != obj.status:
        detail = f"{obj.name}: estado {before} -> {obj.status}"
    services.capture_history(
        db, tenant_id=user.tenant_id, action="CAMPAÑA_MODIFICADA",
        detail=detail, user_id=user.id, user_name=_user_display(user),
    )
    db.commit()
    return obj


@router.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    obj = _campaign_or_404(db, campaign_id, user.tenant_id)
    name = obj.name
    db.delete(obj)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="CAMPAÑA_ELIMINADA",
        detail=name, user_id=user.id, user_name=_user_display(user),
    )
    db.commit()


# --------------------------------------------------------------------------- #
# Premios de la ruleta
# --------------------------------------------------------------------------- #
@router.get("/prizes", response_model=list[CapturePrizeOut])
def list_prizes(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(CapturePrize)
        .filter(CapturePrize.tenant_id == user.tenant_id)
        .order_by(CapturePrize.id)
        .all()
    )


@router.post("/prizes", response_model=CapturePrizeOut, status_code=201)
def create_prize(
    data: CapturePrizeCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    obj = CapturePrize(tenant_id=user.tenant_id, created_by=user.id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="PREMIO_CREADO",
        detail=obj.name, user_id=user.id, user_name=_user_display(user),
    )
    db.commit()
    return obj


@router.put("/prizes/{prize_id}", response_model=CapturePrizeOut)
def update_prize(
    prize_id: int,
    data: CapturePrizeUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    obj = _prize_or_404(db, prize_id, user.tenant_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="PREMIO_MODIFICADO",
        detail=obj.name, user_id=user.id, user_name=_user_display(user),
    )
    db.commit()
    return obj


@router.delete("/prizes/{prize_id}", status_code=204)
def delete_prize(
    prize_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    obj = _prize_or_404(db, prize_id, user.tenant_id)
    name = obj.name
    db.delete(obj)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="PREMIO_ELIMINADO",
        detail=name, user_id=user.id, user_name=_user_display(user),
    )
    db.commit()


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
@router.get("/config", response_model=CaptureConfigOut)
def get_config(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    cfg = services.get_or_create_config(db, user.tenant_id)
    return cfg


@router.put("/config", response_model=CaptureConfigOut)
def update_config(
    data: CaptureConfigUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    cfg = services.get_or_create_config(db, user.tenant_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="CONFIGURACION_MODIFICADA",
        detail=f"Duplicados: {cfg.duplicate_action}", user_id=user.id, user_name=_user_display(user),
    )
    db.commit()
    return cfg


# --------------------------------------------------------------------------- #
# Jornadas de captación
# --------------------------------------------------------------------------- #
@router.get("/sessions", response_model=list[CaptureSessionOut])
def list_sessions(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(PublicCaptureSession)
        .filter(PublicCaptureSession.tenant_id == user.tenant_id)
        .order_by(PublicCaptureSession.started_at.desc())
        .all()
    )


@router.post("/sessions", response_model=CaptureSessionStartOut, status_code=201)
def start_session(
    data: CaptureSessionCreate,
    request: Request,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    vendor_id = data.user_id or user.id
    # Nombre de vendedor: manual (si se escribió), el del usuario elegido desde
    # la plataforma, o el del usuario autenticado.
    if data.vendor_name and data.vendor_name.strip():
        vendor_name = data.vendor_name.strip()
    elif vendor_id == user.id:
        vendor_name = _user_display(user)
    else:
        vendor_name = _platform_user_name(vendor_id) or _user_display(user)
    campaign = None
    if data.campaign_id:
        campaign = _campaign_or_404(db, data.campaign_id, user.tenant_id)

    token = services.new_session_token()
    session = PublicCaptureSession(
        tenant_id=user.tenant_id, user_id=vendor_id, user_name=vendor_name,
        campaign_id=campaign.id if campaign else None,
        campaign_name=campaign.name if campaign else None,
        location=data.location, observations=data.observations,
        status="abierta", session_token=token, created_by=user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="JORNADA_INICIADA",
        detail=f"Vendedor: {vendor_name or ''} · Campaña: {campaign.name if campaign else 'N/A'}",
        session_id=session.id, user_id=user.id, user_name=_user_display(user),
        ip=_client_ip(request),
    )
    db.commit()
    return {"session": session, "session_token": token}


@router.post("/sessions/{session_id}/close", response_model=CaptureSessionOut)
def close_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    session = (
        db.query(PublicCaptureSession)
        .filter(
            PublicCaptureSession.id == session_id,
            PublicCaptureSession.tenant_id == user.tenant_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    session.status = "cerrada"
    session.closed_at = datetime.utcnow()
    session.session_token = None
    db.commit()
    db.refresh(session)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="JORNADA_FINALIZADA",
        detail=session.campaign_name, session_id=session.id,
        user_id=user.id, user_name=_user_display(user), ip=_client_ip(request),
    )
    db.commit()
    return session


@router.post("/sessions/{session_id}/reopen", response_model=CaptureSessionOut)
def reopen_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Reabre una jornada cerrada reanudándola con su configuración original.

    Al reabrir, la tablet del vendedor vuelve a funcionar con la MISMA jornada
    (misma campaña, ubicación y nombre de vendedor), sin necesidad de configurar
    nada de nuevo.
    """
    session = (
        db.query(PublicCaptureSession)
        .filter(
            PublicCaptureSession.id == session_id,
            PublicCaptureSession.tenant_id == user.tenant_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    session.status = "abierta"
    session.closed_at = None
    db.commit()
    db.refresh(session)
    services.capture_history(
        db, tenant_id=user.tenant_id, action="JORNADA_REABIERTA",
        detail=session.campaign_name, session_id=session.id,
        user_id=user.id, user_name=_user_display(user), ip=_client_ip(request),
    )
    db.commit()
    return session


# --------------------------------------------------------------------------- #
# Participaciones / auditoría
# --------------------------------------------------------------------------- #
@router.get("/entries", response_model=list[CaptureEntryOut])
def list_entries(
    session_id: int | None = Query(default=None),
    campaign_id: int | None = Query(default=None),
    vendor_id: int | None = Query(default=None),
    entry_date: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    q = db.query(CaptureEntry).filter(CaptureEntry.tenant_id == user.tenant_id)
    if session_id:
        q = q.filter(CaptureEntry.session_id == session_id)
    if campaign_id:
        q = q.filter(CaptureEntry.campaign_id == campaign_id)
    if vendor_id:
        q = q.filter(CaptureEntry.vendor_id == vendor_id)
    if entry_date:
        q = q.filter(CaptureEntry.entry_date == entry_date)
    return q.order_by(CaptureEntry.created_at.desc()).limit(limit).all()


@router.get("/history", response_model=list[CaptureCaptureHistoryOut])
def list_history(
    session_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    q = db.query(CaptureHistory).filter(CaptureHistory.tenant_id == user.tenant_id)
    if session_id:
        q = q.filter(CaptureHistory.session_id == session_id)
    return q.order_by(CaptureHistory.created_at.desc()).limit(limit).all()


# --------------------------------------------------------------------------- #
# Dashboard / estadísticas
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_model=CaptureDashboardOut)
def dashboard(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    tenant_id = user.tenant_id
    today = date.today()
    month_start = today.replace(day=1)
    entries = (
        db.query(CaptureEntry)
        .filter(CaptureEntry.tenant_id == tenant_id)
        .all()
    )
    captured_today = sum(1 for e in entries if e.entry_date == today)
    captured_month = sum(1 for e in entries if e.entry_date >= month_start)
    prizes_given = sum(1 for e in entries if e.prize_name)
    sessions_count = (
        db.query(PublicCaptureSession)
        .filter(PublicCaptureSession.tenant_id == tenant_id)
        .count()
    )

    prospect_ids = {e.prospect_id for e in entries if e.prospect_id}
    converted = 0
    if prospect_ids:
        converted = (
            db.query(Prospect.id)
            .filter(
                Prospect.tenant_id == tenant_id,
                Prospect.id.in_(prospect_ids),
                Prospect.converted_at.isnot(None),
            )
            .count()
        )
    conversion_rate = round(converted / len(prospect_ids) * 100, 1) if prospect_ids else 0.0

    def _group(key) -> dict[str, int]:
        acc: dict[str, int] = {}
        for e in entries:
            k = key(e) or "Sin dato"
            acc[k] = acc.get(k, 0) + 1
        return acc

    by_campaign = [{"name": k, "value": v} for k, v in _group(lambda e: e.campaign_name).items()]
    by_vendor = [{"name": k, "value": v} for k, v in _group(lambda e: e.vendor_name).items()]
    by_prize = [{"name": k, "value": v} for k, v in _group(lambda e: e.prize_name).items()]

    by_day_map: dict[str, int] = {}
    start = today - timedelta(days=days - 1)
    for e in entries:
        if e.entry_date and e.entry_date >= start:
            k = e.entry_date.isoformat()
            by_day_map[k] = by_day_map.get(k, 0) + 1
    by_day = [{"date": k, "value": by_day_map[k]} for k in sorted(by_day_map)]

    top_campaigns = sorted(by_campaign, key=lambda x: x["value"], reverse=True)[:5]
    top_vendors = sorted(by_vendor, key=lambda x: x["value"], reverse=True)[:5]

    return CaptureDashboardOut(
        captured_today=captured_today,
        captured_month=captured_month,
        total_entries=len(entries),
        prizes_given=prizes_given,
        sessions_count=sessions_count,
        converted=converted,
        conversion_rate=conversion_rate,
        by_campaign=by_campaign,
        by_vendor=by_vendor,
        by_day=by_day,
        by_prize=by_prize,
        top_campaigns=top_campaigns,
        top_vendors=top_vendors,
    )


# --------------------------------------------------------------------------- #
# Reportes
# --------------------------------------------------------------------------- #
def _entries_rows(db: Session, tenant_id: int) -> list[CaptureEntry]:
    return (
        db.query(CaptureEntry)
        .filter(CaptureEntry.tenant_id == tenant_id)
        .order_by(CaptureEntry.created_at.desc())
        .all()
    )


@router.get("/export/excel")
def export_excel(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    rows = _entries_rows(db, user.tenant_id)
    data = [
        {
            "Fecha": e.entry_date.isoformat() if e.entry_date else "",
            "Hora": e.created_at.strftime("%H:%M") if e.created_at else "",
            "Prospecto": e.prospect_name or "",
            "Teléfono": e.phone or "",
            "Premio": e.prize_name or "Sin premio",
            "Campaña": e.campaign_name or "",
            "Vendedor": e.vendor_name or "",
            "Ubicación": e.location or "",
            "Origen": services.ORIGIN_LABEL,
            "Duplicado": e.duplicate_action or "",
        }
        for e in rows
    ]
    columns = [
        "Fecha", "Hora", "Prospecto", "Teléfono", "Premio", "Campaña",
        "Vendedor", "Ubicación", "Origen", "Duplicado",
    ]
    df = pd.DataFrame(data, columns=columns)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    filename = f"Captaciones_{date.today().strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        buffer, media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/csv")
def export_csv(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    rows = _entries_rows(db, user.tenant_id)
    data = [
        {
            "Fecha": e.entry_date.isoformat() if e.entry_date else "",
            "Hora": e.created_at.strftime("%H:%M") if e.created_at else "",
            "Prospecto": e.prospect_name or "",
            "Teléfono": e.phone or "",
            "Premio": e.prize_name or "Sin premio",
            "Campaña": e.campaign_name or "",
            "Vendedor": e.vendor_name or "",
            "Ubicación": e.location or "",
            "Origen": services.ORIGIN_LABEL,
            "Duplicado": e.duplicate_action or "",
        }
        for e in rows
    ]
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
    buffer.seek(0)
    filename = f"Captaciones_{date.today().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        buffer, media_type=CSV_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/pdf")
def export_pdf(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    rows = _entries_rows(db, user.tenant_id)
    setting = (
        db.query(Setting).filter(Setting.tenant_id == user.tenant_id).order_by(Setting.id).first()
    )
    logo = setting.logo_path if setting else None
    company = setting.company_name if setting else "Mi Empresa"
    table = [
        [
            e.entry_date.isoformat() if e.entry_date else "",
            (e.prospect_name or "")[:24],
            e.phone or "",
            (e.prize_name or "Sin premio")[:18],
            (e.campaign_name or "")[:18],
            (e.vendor_name or "")[:18],
        ]
        for e in rows
    ]
    buffer = services.generate_capture_pdf(
        "REPORTE DE CAPTACIÓN PÚBLICA",
        ["Fecha", "Prospecto", "Teléfono", "Premio", "Campaña", "Vendedor"],
        table, logo_path=logo, company_name=company,
        summary=[f"Total de captaciones: {len(rows)}"],
    )
    filename = f"Captaciones_{date.today().strftime('%Y-%m-%d')}.pdf"
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
