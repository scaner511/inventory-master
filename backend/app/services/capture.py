"""Servicios del módulo Captación Pública de Prospectos.

Contiene la lógica reutilizable por los routers de captación:
- Sorteo ponderado de la ruleta (con respeto de stock/vigencia).
- Integración con el CRM: crea/actualiza el prospecto, deja historial,
  seguimiento y entrada de captación.
- Generación de PDF de reportes de captación.
"""
import io
import json
import random
import secrets
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import (
    CaptureCampaign,
    CaptureConfig,
    CaptureEntry,
    CaptureHistory,
    CapturePrize,
    Notification,
    Prospect,
    ProspectActivity,
    ProspectHistory,
)
from app.utils.audit import record_audit

ORIGIN = "captacion_presencial"
ORIGIN_LABEL = "Captación Presencial"


def new_session_token() -> str:
    """Token efímero (opaco) que usa la tablet para registrar sin JWT del usuario."""
    return secrets.token_urlsafe(24)


# --------------------------------------------------------------------------- #
# Configuración del módulo
# --------------------------------------------------------------------------- #
def get_or_create_config(db: Session, tenant_id: int | None) -> CaptureConfig:
    cfg = (
        db.query(CaptureConfig)
        .filter(CaptureConfig.tenant_id == tenant_id)
        .order_by(CaptureConfig.id)
        .first()
    )
    if cfg is None:
        cfg = CaptureConfig(
            tenant_id=tenant_id, duplicate_action="actualizar",
            no_prize_message="Gracias por participar",
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# --------------------------------------------------------------------------- #
# Ruleta
# --------------------------------------------------------------------------- #
def _prize_available(prize: CapturePrize, today: date) -> bool:
    if not prize.is_active:
        return False
    if prize.valid_from and today < prize.valid_from:
        return False
    if prize.valid_until and today > prize.valid_until:
        return False
    if prize.stock is not None and prize.stock <= 0:
        return False
    return True


def list_available_prizes(db: Session, tenant_id: int) -> list[CapturePrize]:
    today = date.today()
    rows = (
        db.query(CapturePrize)
        .filter(CapturePrize.tenant_id == tenant_id)
        .order_by(CapturePrize.id)
        .all()
    )
    available = [p for p in rows if _prize_available(p, today)]
    # Si ningún premio está disponible pero existe una cara "sin premio", déjala.
    if not available:
        available = [p for p in rows if p.is_no_prize]
    return available


def spin_wheel(db: Session, tenant_id: int, config: CaptureConfig | None = None) -> CapturePrize | None:
    """Sorteo ponderado. Devuelve el premio ganador (o None si no hay ruleta)."""
    prizes = list_available_prizes(db, tenant_id)
    if not prizes:
        return None
    total = sum(max(0, p.probability) for p in prizes)
    if total <= 0:
        return random.choice(prizes)
    pick = random.uniform(0, total)
    acc = 0.0
    for prize in prizes:
        acc += max(0, prize.probability)
        if pick <= acc:
            return prize
    return prizes[-1]


def wheel_segments(db: Session, tenant_id: int) -> list[dict]:
    """Segmentos que el frontend usa para dibujar la ruleta."""
    prizes = list_available_prizes(db, tenant_id)
    return [
        {
            "id": p.id,
            "label": p.name,
            "color": p.color or "#3b82f6",
            "probability": p.probability,
            "is_no_prize": p.is_no_prize,
        }
        for p in prizes
    ]


# --------------------------------------------------------------------------- #
# Duplicados
# --------------------------------------------------------------------------- #
def find_duplicate(db: Session, tenant_id: int, phone: str) -> Prospect | None:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) < 3:
        return None
    candidates = (
        db.query(Prospect)
        .filter(Prospect.tenant_id == tenant_id, Prospect.phone.isnot(None))
        .all()
    )
    for p in candidates:
        p_digits = "".join(ch for ch in (p.phone or "") if ch.isdigit())
        if p_digits and p_digits == digits:
            return p
    return None


# --------------------------------------------------------------------------- #
# Historial / auditoría de captación
# --------------------------------------------------------------------------- #
def capture_history(
    db: Session, *, tenant_id: int, action: str, detail: str | None = None,
    session_id: int | None = None, entry_id: int | None = None,
    user_id: int | None = None, user_name: str | None = None, ip: str | None = None,
) -> None:
    db.add(
        CaptureHistory(
            tenant_id=tenant_id, session_id=session_id, entry_id=entry_id,
            action=action, detail=detail, user_id=user_id, user_name=user_name,
            ip_address=ip,
        )
    )


# --------------------------------------------------------------------------- #
# Integración con el CRM (prospectos)
# --------------------------------------------------------------------------- #
def _prospect_history(db, *, prospect_id, tenant_id, user_id, action, detail=None) -> None:
    db.add(
        ProspectHistory(
            tenant_id=tenant_id, prospect_id=prospect_id, user_id=user_id,
            action=action, detail=detail,
        )
    )


def register_prospect(
    db: Session, *,
    tenant_id: int,
    data,  # CaptureRegisterIn
    session,  # PublicCaptureSession | None
    campaign: CaptureCampaign | None,
    prize: CapturePrize | None,
    vendor_id: int | None,
    vendor_name: str | None,
    ip: str | None = None,
    duplicate_choice: str | None = None,
) -> dict:
    """Crea/actualiza el prospecto y registra la participación de captación.

    Devuelve un dict con: prospect_id, prospect_name, created, duplicate_action, prize_name.
    """
    name = data.full_name.strip()
    phone = data.phone.strip()
    existing = find_duplicate(db, tenant_id, phone)

    created = True
    duplicate_action: str | None = None
    prospect: Prospect

    if existing is not None:
        choice = duplicate_choice or "actualizar"
        duplicate_action = choice
        prospect = existing
        if choice == "actualizar":
            # Refresca datos con lo nuevo (no borra lo que venga vacío).
            prospect.full_name = name or prospect.full_name
            if data.address:
                prospect.address = data.address.strip()
            if data.marital_status:
                prospect.marital_status = data.marital_status.strip()
            if data.knows_brand is not None:
                prospect.knows_brand = data.knows_brand
            _prospect_history(
                db, prospect_id=prospect.id, tenant_id=tenant_id, user_id=vendor_id,
                action="CAPTACION_ACTUALIZADA",
                detail=f"Datos actualizados en jornada de captación ({ORIGIN_LABEL})",
            )
        else:  # nueva_interaccion: solo deja rastro, no toca la ficha.
            _prospect_history(
                db, prospect_id=prospect.id, tenant_id=tenant_id, user_id=vendor_id,
                action="CAPTACION_INTERACCION",
                detail=f"Nueva interacción en jornada de captación ({ORIGIN_LABEL})",
            )
    else:
        notes = (data.notes or "").strip() or None
        trailer = f"[Captado en {ORIGIN_LABEL}"
        if campaign:
            trailer += f" · Campaña: {campaign.name}"
        if prize and not prize.is_no_prize:
            trailer += f" · Premio: {prize.name}"
        trailer += "]"
        notes = f"{notes}\n{trailer}" if notes else trailer
        if len(notes) > 500:
            notes = notes[:497] + "..."

        prospect = Prospect(
            tenant_id=tenant_id,
            full_name=name,
            phone=phone,
            address=(data.address or "").strip() or None,
            marital_status=(data.marital_status or "").strip() or None,
            knows_brand=data.knows_brand,
            notes=notes,
            status="nuevo",
            commercial_status="nuevo",
            stage_slug="nuevo",
            owner_id=vendor_id,
            created_by=vendor_id,
            close_probability=0,
        )
        db.add(prospect)
        db.flush()
        _prospect_history(
            db, prospect_id=prospect.id, tenant_id=tenant_id, user_id=vendor_id,
            action="CAPTADO_EN_JORNADA",
            detail=f"Prospecto captado desde jornada presencial ({ORIGIN_LABEL})",
        )

    # Seguimiento automático (actividad) en ambos casos.
    obs = f"Prospecto captado desde jornada presencial ({ORIGIN_LABEL})."
    if campaign:
        obs += f" Campaña: {campaign.name}."
    if prize:
        obs += f" Premio: {prize.name}."
    db.add(
        ProspectActivity(
            tenant_id=tenant_id, prospect_id=prospect.id, kind="otro",
            observation=obs, result="Captación presencial", status="pendiente",
            user_id=vendor_id, created_by=vendor_id,
        )
    )
    _prospect_history(
        db, prospect_id=prospect.id, tenant_id=tenant_id, user_id=vendor_id,
        action="SEGUIMIENTO",
        detail="Seguimiento automático: prospecto captado en jornada presencial.",
    )

    # Notificación al vendedor responsable.
    db.add(
        Notification(
            tenant_id=tenant_id, user_id=vendor_id, kind="PROSPECTO_CAPTADO",
            title="Prospecto captado en jornada",
            body=f"{prospect.full_name}" + (f" · {prize.name}" if prize else ""),
            entity="prospect", entity_id=prospect.id,
        )
    )

    # Consumir stock del premio.
    if prize and not prize.is_no_prize and prize.stock is not None:
        prize.stock = max(0, prize.stock - 1)

    # Entrada de captación (participación).
    entry = CaptureEntry(
        tenant_id=tenant_id,
        session_id=session.id if session else None,
        campaign_id=campaign.id if campaign else None,
        campaign_name=campaign.name if campaign else None,
        prize_id=prize.id if prize else None,
        prize_name=prize.name if prize else None,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        prospect_id=prospect.id,
        prospect_name=prospect.full_name,
        phone=phone,
        location=session.location if session else None,
        origin=ORIGIN,
        duplicate_action=duplicate_action,
        entry_date=date.today(),
        created_by=vendor_id,
    )
    db.add(entry)
    db.flush()

    capture_history(
        db, tenant_id=tenant_id, action="PROSPECTO_REGISTRADO",
        detail=f"{prospect.full_name} · {prize.name if prize else 'sin premio'}",
        session_id=session.id if session else None, entry_id=entry.id,
        user_id=vendor_id, user_name=vendor_name, ip=ip,
    )
    record_audit(
        db, action="CAPTACION_PROSPECTO", user_id=vendor_id, tenant_id=tenant_id,
        detail=f"Prospecto '{prospect.full_name}' captado ({ORIGIN_LABEL})",
    )
    db.commit()
    db.refresh(entry)

    return {
        "prospect_id": prospect.id,
        "prospect_name": prospect.full_name,
        "created": created,
        "duplicate_action": duplicate_action,
        "prize_name": prize.name if prize else None,
    }


# --------------------------------------------------------------------------- #
# PDF de reportes de captación
# --------------------------------------------------------------------------- #
def generate_capture_pdf(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    logo_path: str | None = None,
    company_name: str = "MC'CEA INVENTORY",
    summary: list[str] | None = None,
) -> io.BytesIO:
    """PDF simple tipo tabla (paginado) para reportes de captación."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    col_count = max(1, len(headers))
    col_width = (width - 80) / col_count

    def draw_header(page: int) -> float:
        if logo_path and Path(logo_path).exists():
            try:
                c.drawImage(logo_path, 40, height - 90, width=110, height=65,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.setFont("Helvetica-Bold", 15)
        c.drawString(170, height - 55, title[:60])
        c.setFont("Helvetica", 9)
        c.drawString(170, height - 70, company_name[:60])
        c.drawRightString(width - 40, height - 55, f"Página {page}")
        y = height - 110
        c.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers):
            c.drawString(40 + i * col_width, y, str(h)[:24])
        c.line(40, y - 4, width - 40, y - 4)
        return y - 18

    page = 1
    y = draw_header(page)
    c.setFont("Helvetica", 8)

    for row in rows:
        if y < 60:
            c.showPage()
            page += 1
            y = draw_header(page)
            c.setFont("Helvetica", 8)
        for i, cell in enumerate(row):
            c.drawString(40 + i * col_width, y, str(cell)[:28])
        y -= 14

    if summary:
        y -= 10
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, "Resumen")
        c.setFont("Helvetica", 9)
        for line in summary:
            y -= 14
            c.drawString(50, y, str(line)[:90])

    c.save()
    buffer.seek(0)
    return buffer
