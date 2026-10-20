"""Router público de captación (tablet durante la jornada).

Endpoints bajo /api/capture/public (autenticados con el token de jornada,
NO con el JWT del usuario). El token se envía en el header
``X-Capture-Token`` y resuelve la jornada + su cliente (tenant).
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_tenant_session
from app.models import CaptureCampaign, CapturePrize, PublicCaptureSession, User
from app.schemas import (
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
):
    """Resuelve la jornada a partir del token efímero de la tablet.

    Devuelve (platform_db, tenant_db, session). El tenant_db se cierra al final.
    """
    if not x_capture_token:
        raise HTTPException(status_code=401, detail="Token de jornada requerido")

    pdb: Session = SessionLocal()
    try:
        session = (
            pdb.query(PublicCaptureSession)
            .filter(
                PublicCaptureSession.session_token == x_capture_token,
                PublicCaptureSession.status == "abierta",
            )
            .first()
        )
        if session is None:
            raise HTTPException(status_code=401, detail="Token de jornada inválido o expirado")
        tenant_id = session.tenant_id
    finally:
        pdb.close()

    tdb = get_tenant_session(tenant_id)
    try:
        yield tdb, session
    finally:
        tdb.close()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/session", response_model=CapturePublicInfoOut)
def public_session(
    ctx=Depends(_resolve_session),
):
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
