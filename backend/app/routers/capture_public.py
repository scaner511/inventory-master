"""Router público de captación (tablet durante la jornada).

Endpoints bajo /api/capture/public (autenticados con el token FIJO del
vendedor, NO con el JWT del usuario). El token se envía en el header
``X-Capture-Token`` y resuelve el vendedor + su cliente (tenant).

Diseño "link fijo por vendedor": el administrador genera una vez el enlace del
vendedor (``users.capture_token``). Ese enlace no cambia entre jornadas: al
abrirse se REUTILIZA la jornada abierta del vendedor o se CREA una nueva de
forma automática (sin botón "INICIAR JORNADA" en el celular).
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_tenant_session
from app.models import CaptureCampaign, CapturePrize, PublicCaptureSession, Setting, User
from app.schemas import (
    CaptureCampaignOut,
    CaptureDuplicateCheckIn,
    CaptureDuplicateCheckOut,
    CapturePublicInfoOut,
    CaptureRegisterIn,
    CaptureRegisterOut,
    CaptureSpinOut,
)
from app.services import capture as services

router = APIRouter(prefix="/api/capture/public", tags=["capture-public"])


def _resolve_session(
    x_capture_token: str | None = Header(default=None, alias="X-Capture-Token"),
    token: str | None = None,
):
    """Resuelve (vendedor, jornada) a partir del token FIJO de la tablet.

    El enlace es único por vendedor. La tablet SOLO funciona mientras la última
    jornada de ese vendedor esté ABIERTA: el administrador la inicia y la cierra
    desde el panel. Si está cerrada (o el vendedor no tiene jornada), se niega el
    acceso (403) hasta que el administrador la reabra; al reabrir se reanuda la
    MISMA jornada con su configuración original (sin reconfigurar).

    Devuelve un generador que entrega (tenant_db, session). El tenant_db se
    cierra al finalizar la petición.
    """
    # El token puede venir en el header (llamadas API normales) o como query
    # `?token=` (p. ej. al cargar el logo en un <img>, que no envía headers).
    capture_token = x_capture_token or token
    if not capture_token:
        raise HTTPException(status_code=401, detail="Token de captación requerido")

    # 1) El token pertenece a un usuario/vendedor (tabla de plataforma).
    pdb: Session = SessionLocal()
    try:
        vendor = pdb.query(User).filter(User.capture_token == capture_token).first()
        if vendor is None or not vendor.is_active:
            raise HTTPException(status_code=401, detail="Enlace de captación inválido")
        tenant_id = vendor.tenant_id
        vendor_id = vendor.id
        vendor_name = vendor.username
    finally:
        pdb.close()

    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Enlace de captación inválido")

    # 2) Resuelve la jornada MÁS RECIENTE del vendedor. No se crea sola: eso lo
    #    hace el administrador al iniciar la jornada. Si la última está cerrada,
    #    la tablet no tiene acceso.
    tdb = get_tenant_session(tenant_id)
    try:
        session = (
            tdb.query(PublicCaptureSession)
            .filter(
                PublicCaptureSession.tenant_id == tenant_id,
                PublicCaptureSession.user_id == vendor_id,
            )
            .order_by(PublicCaptureSession.started_at.desc())
            .first()
        )
        if session is None:
            raise HTTPException(
                status_code=403,
                detail="Aún no hay una jornada de captación. Pídele a tu administrador que la inicie.",
            )
        if session.status != "abierta":
            raise HTTPException(
                status_code=403,
                detail="La jornada de captación está cerrada. Pídele a tu administrador que la reabra.",
            )
        if not session.user_name:
            session.user_name = vendor_name
            tdb.commit()
            tdb.refresh(session)
        yield tdb, session
    finally:
        tdb.close()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _company_info(db: Session, tenant_id: int) -> dict:
    """Nombre y logo del cliente para mostrarlos en la tablet del sorteo."""
    setting = (
        db.query(Setting).filter(Setting.tenant_id == tenant_id).order_by(Setting.id).first()
    )
    if not setting:
        return {"company_name": None, "logo_url": None}
    return {
        "company_name": setting.company_name,
        "logo_url": "/api/capture/public/logo" if setting.logo_path else None,
    }


@router.get("/session", response_model=CapturePublicInfoOut)
def public_session(ctx=Depends(_resolve_session)):
    db, session = ctx
    campaign = None
    if session.campaign_id:
        campaign = (
            db.query(CaptureCampaign).filter(CaptureCampaign.id == session.campaign_id).first()
        )
    cfg = services.get_or_create_config(db, session.tenant_id)
    return CapturePublicInfoOut(
        session=session,
        campaign=campaign,
        vendor_name=session.user_name,
        location=session.location,
        duplicate_action=cfg.duplicate_action,
        no_prize_message=cfg.no_prize_message,
        segments=services.wheel_segments(db, session.tenant_id),
        **_company_info(db, session.tenant_id),
    )


@router.get("/logo")
def public_logo(ctx=Depends(_resolve_session)):
    """Sirve el logo del cliente para la tablet (autenticado con el token fijo)."""
    db, session = ctx
    setting = (
        db.query(Setting).filter(Setting.tenant_id == session.tenant_id).order_by(Setting.id).first()
    )
    if not setting or not setting.logo_path or not Path(setting.logo_path).exists():
        raise HTTPException(status_code=404, detail="No hay logo configurado")
    return FileResponse(setting.logo_path)


@router.get("/campaigns", response_model=list[CaptureCampaignOut])
def public_campaigns(ctx=Depends(_resolve_session)):
    """Campañas activas disponibles para que el vendedor elija."""
    db, _session = ctx
    return (
        db.query(CaptureCampaign)
        .filter(
            CaptureCampaign.tenant_id == _session.tenant_id,
            CaptureCampaign.status == "activa",
        )
        .order_by(CaptureCampaign.name)
        .all()
    )


@router.post("/campaign", response_model=CapturePublicInfoOut)
def public_select_campaign(
    payload: dict,
    ctx=Depends(_resolve_session),
):
    """El vendedor elige/actualiza la campaña activa de su jornada."""
    db, session = ctx
    campaign_id = payload.get("campaign_id")
    campaign = None
    if campaign_id:
        campaign = (
            db.query(CaptureCampaign)
            .filter(
                CaptureCampaign.id == int(campaign_id),
                CaptureCampaign.tenant_id == session.tenant_id,
            )
            .first()
        )
        if campaign is None:
            raise HTTPException(status_code=404, detail="Campaña no encontrada")
    session.campaign_id = campaign.id if campaign else None
    session.campaign_name = campaign.name if campaign else None
    db.commit()
    db.refresh(session)
    cfg = services.get_or_create_config(db, session.tenant_id)
    return CapturePublicInfoOut(
        session=session,
        campaign=campaign,
        vendor_name=session.user_name,
        location=session.location,
        duplicate_action=cfg.duplicate_action,
        no_prize_message=cfg.no_prize_message,
        segments=services.wheel_segments(db, session.tenant_id),
        **_company_info(db, session.tenant_id),
    )


@router.post("/spin", response_model=CaptureSpinOut)
def public_spin(ctx=Depends(_resolve_session)):
    db, session = ctx
    cfg = services.get_or_create_config(db, session.tenant_id)
    segments = services.wheel_segments(db, session.tenant_id)
    prize = services.spin_wheel(db, session.tenant_id, cfg)
    if prize is None:
        return CaptureSpinOut(
            prize={"name": cfg.no_prize_message, "is_no_prize": True},
            segments=segments,
            wheel_index=0,
        )
    idx = next((i for i, s in enumerate(segments) if s["id"] == prize.id), 0)
    return CaptureSpinOut(
        prize={"id": prize.id, "name": prize.name, "color": prize.color,
               "is_no_prize": prize.is_no_prize},
        segments=segments,
        wheel_index=idx,
    )


@router.post("/check-duplicate", response_model=CaptureDuplicateCheckOut)
def public_check_duplicate(
    data: CaptureDuplicateCheckIn,
    ctx=Depends(_resolve_session),
):
    db, session = ctx
    cfg = services.get_or_create_config(db, session.tenant_id)
    existing = services.find_duplicate(db, session.tenant_id, data.phone)
    return CaptureDuplicateCheckOut(
        exists=existing is not None,
        prospect_id=existing.id if existing else None,
        prospect_name=existing.full_name if existing else None,
        action=cfg.duplicate_action,
    )


@router.post("/register", response_model=CaptureRegisterOut, status_code=201)
def public_register(
    data: CaptureRegisterIn,
    request: Request,
    ctx=Depends(_resolve_session),
):
    db, session = ctx
    campaign = None
    if session.campaign_id:
        campaign = (
            db.query(CaptureCampaign).filter(CaptureCampaign.id == session.campaign_id).first()
        )
    prize = None
    if data.prize_id:
        prize = db.query(CapturePrize).filter(CapturePrize.id == data.prize_id).first()

    # Si hay duplicado y la config bloquea, se rechaza salvo elección explícita.
    if data.duplicate_choice == "bloquear":
        raise HTTPException(
            status_code=409,
            detail="Este prospecto ya se encuentra registrado.",
        )

    result = services.register_prospect(
        db, tenant_id=session.tenant_id, data=data, session=session,
        campaign=campaign, prize=prize, vendor_id=session.user_id,
        vendor_name=session.user_name, ip=_client_ip(request),
        duplicate_choice=data.duplicate_choice,
    )
    return CaptureRegisterOut(**result)
