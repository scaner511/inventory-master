"""Gestión de Prospectos (CRM comercial interno).

Módulo independiente del inventario y del CRM de cartera externo. Gestiona el
ciclo comercial del prospecto: ficha, seguimientos, notas, historial, embudo y
conversión a cliente. Todas las tablas son de negocio (tenant_id).

Endpoints bajo /api/prospects.
"""
import base64
import io
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.deps import get_current_user, get_tenant_db, require_admin
from app.models import (
    PROSPECT_STATUSES,
    Notification,
    Prospect,
    ProspectActivity,
    ProspectFile,
    ProspectHistory,
    ProspectNote,
    ProspectSignature,
    SalesPipeline,
    User,
)
from app.schemas import (
    ConvertProspectIn,
    OpportunitySummary,
    PipelineStageOut,
    ProspectActivityCreate,
    ProspectActivityOut,
    ProspectActivityUpdate,
    ProspectCreate,
    ProspectFileOut,
    ProspectHistoryOut,
    ProspectMove,
    ProspectNoteCreate,
    ProspectNoteOut,
    ProspectOut,
    ProspectSignatureCreate,
    ProspectSignatureOut,
    ProspectUpdate,
)
from app.utils.audit import record_audit

router = APIRouter(prefix="/api/prospects", tags=["prospects"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ALLOWED_FILE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

# Etapas por defecto del embudo (se siembran por cliente la primera vez).
DEFAULT_STAGES = [
    ("nuevo", "Nuevo Prospecto", "#3b82f6", False, False, False),
    ("contactado", "Contactado", "#6366f1", False, False, False),
    ("interesado", "Interesado", "#8b5cf6", False, False, False),
    ("cita_programada", "Cita Programada", "#0ea5e9", False, False, False),
    ("visitado", "Visitado", "#14b8a6", False, False, False),
    ("propuesta_enviada", "Propuesta Enviada", "#f59e0b", False, False, False),
    ("negociacion", "Negociación", "#f97316", False, False, False),
    ("cliente", "Cliente", "#22c55e", True, True, False),
    ("no_interesado", "No Interesado", "#ef4444", True, False, True),
]

STATUS_LABELS = {
    "nuevo": "Nuevo",
    "contactado": "Contactado",
    "interesado": "Interesado",
    "pendiente_cita": "Pendiente de cita",
    "visitado": "Visitado",
    "cliente_potencial": "Cliente potencial",
    "cliente_convertido": "Cliente convertido",
    "no_interesado": "No interesado",
}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _ensure_pipeline(db: Session, tenant_id: int) -> None:
    exists = db.query(SalesPipeline.id).filter(SalesPipeline.tenant_id == tenant_id).first()
    if exists:
        return
    for pos, (slug, name, color, terminal, won, lost) in enumerate(DEFAULT_STAGES):
        db.add(
            SalesPipeline(
                tenant_id=tenant_id,
                slug=slug,
                name=name,
                position=pos,
                color=color,
                is_terminal=terminal,
                is_won=won,
                is_lost=lost,
            )
        )
    db.commit()


def _history(
    db: Session, *, prospect_id: int, tenant_id: int, user_id: int | None, action: str, detail: str | None = None
) -> None:
    db.add(
        ProspectHistory(
            tenant_id=tenant_id,
            prospect_id=prospect_id,
            user_id=user_id,
            action=action,
            detail=detail,
        )
    )


def _notify(
    db: Session, *, tenant_id: int, user_id: int | None, kind: str, title: str, body: str | None = None,
    entity: str | None = None, entity_id: int | None = None,
) -> None:
    db.add(
        Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            entity=entity,
            entity_id=entity_id,
        )
    )


def _get_prospect(db: Session, prospect_id: int, tenant_id: int) -> Prospect:
    p = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id, Prospect.tenant_id == tenant_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Prospecto no encontrado")
    return p


def _to_out(p: Prospect) -> ProspectOut:
    out = ProspectOut.model_validate(p)
    out.opportunity_value = p.opportunity_value
    out.weighted_value = p.weighted_value
    return out


def _products_to_json(items: list[str] | None) -> str | None:
    if not items:
        return None
    import json

    return json.dumps(items)


def _products_from_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    import json

    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


# --------------------------------------------------------------------------- #
# Pipeline / embudo
# --------------------------------------------------------------------------- #
@router.get("/pipeline", response_model=list[PipelineStageOut])
def list_pipeline(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    _ensure_pipeline(db, user.tenant_id)
    return (
        db.query(SalesPipeline)
        .filter(SalesPipeline.tenant_id == user.tenant_id)
        .order_by(SalesPipeline.position, SalesPipeline.id)
        .all()
    )


@router.get("/board")
def kanban_board(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    """Prospectos agrupados por etapa para el tablero Kanban."""
    _ensure_pipeline(db, user.tenant_id)
    stages = (
        db.query(SalesPipeline)
        .filter(SalesPipeline.tenant_id == user.tenant_id)
        .order_by(SalesPipeline.position, SalesPipeline.id)
        .all()
    )
    prospects = (
        db.query(Prospect)
        .filter(Prospect.tenant_id == user.tenant_id)
        .order_by(Prospect.updated_at.desc())
        .all()
    )
    grouped: dict[str, list] = {s.slug: [] for s in stages}
    for p in prospects:
        grouped.setdefault(p.stage_slug or "nuevo", []).append(_to_out(p).model_dump(mode="json"))
    return {
        "stages": [PipelineStageOut.model_validate(s).model_dump(mode="json") for s in stages],
        "columns": grouped,
    }


@router.get("/opportunity-summary", response_model=OpportunitySummary)
def opportunity_summary(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    _ensure_pipeline(db, user.tenant_id)
    prospects = db.query(Prospect).filter(Prospect.tenant_id == user.tenant_id).all()
    total = sum(p.opportunity_value for p in prospects)
    weighted = sum(p.weighted_value for p in prospects)
    by_stage: dict[str, float] = {}
    for p in prospects:
        by_stage[p.stage_slug or "nuevo"] = by_stage.get(p.stage_slug or "nuevo", 0) + p.opportunity_value
    by_status: dict[str, int] = {}
    for p in prospects:
        by_status[p.status] = by_status.get(p.status, 0) + 1
    return OpportunitySummary(
        total_value=total,
        weighted_value=weighted,
        pipeline_by_stage=[{"stage": k, "value": v} for k, v in by_stage.items()],
        by_status=[{"status": k, "count": v} for k, v in by_status.items()],
    )


# --------------------------------------------------------------------------- #
# Prospectos
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[ProspectOut])
def list_prospects(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    stage: str | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    rating: int | None = Query(default=None, ge=1, le=5),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Prospect).filter(Prospect.tenant_id == user.tenant_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Prospect.full_name.ilike(like)
            | Prospect.phone.ilike(like)
            | Prospect.address.ilike(like)
        )
    if status_filter:
        query = query.filter(Prospect.status == status_filter)
    if stage:
        query = query.filter(Prospect.stage_slug == stage)
    if owner_id:
        query = query.filter(Prospect.owner_id == owner_id)
    if rating:
        query = query.filter(Prospect.rating == rating)
    rows = query.order_by(Prospect.updated_at.desc()).all()
    return [_to_out(p) for p in rows]


@router.post("", response_model=ProspectOut, status_code=201)
def create_prospect(
    data: ProspectCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _ensure_pipeline(db, user.tenant_id)
    status = data.status or "nuevo"
    if status not in PROSPECT_STATUSES:
        raise HTTPException(status_code=400, detail="Estado de prospecto inválido")
    p = Prospect(
        tenant_id=user.tenant_id,
        full_name=data.full_name.strip(),
        phone=(data.phone or "").strip() or None,
        address=(data.address or "").strip() or None,
        marital_status=(data.marital_status or "").strip() or None,
        occupation=(data.occupation or "").strip() or None,
        knows_brand=data.knows_brand,
        notes=(data.notes or "").strip() or None,
        status=status,
        commercial_status=data.commercial_status or "nuevo",
        rating=data.rating,
        stage_slug=data.stage_slug or "nuevo",
        owner_id=data.owner_id or user.id,
        created_by=user.id,
        has_budget=data.has_budget,
        is_decision_maker=data.is_decision_maker,
        close_probability=data.close_probability,
        monthly_value=data.monthly_value,
        setup_value=data.setup_value,
        interested_products=_products_to_json(data.interested_products),
        lost_reason=data.lost_reason,
        lost_reason_detail=data.lost_reason_detail,
        summary=data.summary,
        next_followup_at=data.next_followup_at,
    )
    db.add(p)
    db.flush()
    _history(
        db,
        prospect_id=p.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="PROSPECTO_CREADO",
        detail=f"Prospecto '{p.full_name}' creado",
    )
    record_audit(
        db, action="PROSPECTO", user_id=user.id, tenant_id=user.tenant_id,
        detail=f"Prospecto '{p.full_name}' creado",
    )
    # Envío automático de la ficha al responsable asignado.
    if p.owner_id:
        _notify(
            db, tenant_id=user.tenant_id, user_id=p.owner_id, kind="FICHA_ASIGNADA",
            title="Nueva ficha de prospecto asignada",
            body=f"{p.full_name}{(' · ' + p.phone) if p.phone else ''}",
            entity="prospect", entity_id=p.id,
        )
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.get("/{prospect_id}", response_model=ProspectOut)
def get_prospect(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    return _to_out(_get_prospect(db, prospect_id, user.tenant_id))


@router.put("/{prospect_id}", response_model=ProspectOut)
def update_prospect(
    prospect_id: int,
    data: ProspectUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    p = _get_prospect(db, prospect_id, user.tenant_id)
    updates = data.model_dump(exclude_unset=True)

    if "status" in updates and updates["status"] and updates["status"] not in PROSPECT_STATUSES:
        raise HTTPException(status_code=400, detail="Estado de prospecto inválido")

    changed = []
    for field in (
        "full_name", "phone", "address", "marital_status", "occupation", "knows_brand", "notes",
        "status", "commercial_status", "rating", "stage_slug", "owner_id",
        "has_budget", "is_decision_maker", "close_probability", "monthly_value",
        "setup_value", "lost_reason", "lost_reason_detail", "summary", "next_followup_at",
    ):
        if field in updates:
            val = updates[field]
            if isinstance(val, str):
                val = val.strip() or None
            setattr(p, field, val)
            changed.append(field)
    if "interested_products" in updates:
        p.interested_products = _products_to_json(updates["interested_products"])
        changed.append("interested_products")

    # Envío automático de la ficha al nuevo responsable si cambió.
    if "owner_id" in updates and p.owner_id and p.owner_id != user.id:
        _notify(
            db, tenant_id=user.tenant_id, user_id=p.owner_id, kind="FICHA_ASIGNADA",
            title="Ficha de prospecto reasignada",
            body=f"{p.full_name}{(' · ' + p.phone) if p.phone else ''}",
            entity="prospect", entity_id=p.id,
        )

    _history(
        db,
        prospect_id=p.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="PROSPECTO_EDITADO",
        detail=f"Campos actualizados: {', '.join(changed)}" if changed else "Edición sin cambios",
    )
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.post("/{prospect_id}/move", response_model=ProspectOut)
def move_prospect(
    prospect_id: int,
    data: ProspectMove,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Mueve el prospecto de etapa (drag & drop del Kanban)."""
    p = _get_prospect(db, prospect_id, user.tenant_id)
    stage = (
        db.query(SalesPipeline)
        .filter(SalesPipeline.tenant_id == user.tenant_id, SalesPipeline.slug == data.stage_slug)
        .first()
    )
    if stage is None:
        raise HTTPException(status_code=404, detail="Etapa no encontrada")
    old = p.stage_slug
    p.stage_slug = stage.slug
    if stage.is_won:
        p.status = "cliente_convertido"
        p.commercial_status = "cliente_convertido"
    elif stage.is_lost:
        p.status = "no_interesado"
        p.commercial_status = "no_interesado"
    _history(
        db,
        prospect_id=p.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="ETAPA_CAMBIADA",
        detail=f"Etapa de '{old}' a '{stage.slug}'",
    )
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.post("/{prospect_id}/convert", response_model=ProspectOut)
def convert_prospect(
    prospect_id: int,
    data: ConvertProspectIn,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Convierte el prospecto en cliente."""
    p = _get_prospect(db, prospect_id, user.tenant_id)
    if p.converted_at:
        raise HTTPException(status_code=400, detail="El prospecto ya fue convertido")
    p.status = "cliente_convertido"
    p.commercial_status = "cliente_convertido"
    p.stage_slug = "cliente"
    p.converted_at = datetime.utcnow()
    p.converted_by = user.id
    _history(
        db,
        prospect_id=p.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="CLIENTE_CONVERTIDO",
        detail=data.note or f"Prospecto '{p.full_name}' convertido en cliente",
    )
    _notify(
        db, tenant_id=user.tenant_id, user_id=p.owner_id, kind="CONVERSION",
        title="Prospecto convertido en cliente",
        body=f"{p.full_name} se convirtió en cliente.", entity="prospect", entity_id=p.id,
    )
    record_audit(
        db, action="PROSPECTO_CONVERTIDO", user_id=user.id, tenant_id=user.tenant_id,
        detail=f"Prospecto '{p.full_name}' convertido en cliente",
    )
    db.commit()
    db.refresh(p)
    return _to_out(p)


@router.delete("/{prospect_id}", status_code=204)
def delete_prospect(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    p = _get_prospect(db, prospect_id, user.tenant_id)
    name = p.full_name
    db.delete(p)
    record_audit(
        db, action="PROSPECTO_ELIMINADO", user_id=user.id, tenant_id=user.tenant_id,
        detail=f"Prospecto '{name}' eliminado",
    )
    db.commit()
    return None


# --------------------------------------------------------------------------- #
# Notas
# --------------------------------------------------------------------------- #
@router.get("/{prospect_id}/notes", response_model=list[ProspectNoteOut])
def list_notes(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    return (
        db.query(ProspectNote)
        .filter(ProspectNote.tenant_id == user.tenant_id, ProspectNote.prospect_id == prospect_id)
        .order_by(ProspectNote.created_at.desc())
        .all()
    )


@router.post("/{prospect_id}/notes", response_model=ProspectNoteOut, status_code=201)
def add_note(
    prospect_id: int,
    data: ProspectNoteCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    note = ProspectNote(
        tenant_id=user.tenant_id,
        prospect_id=prospect_id,
        text=data.text.strip(),
        created_by=user.id,
    )
    db.add(note)
    _history(
        db, prospect_id=prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="NOTA_AGREGADA", detail=data.text.strip()[:200],
    )
    db.commit()
    db.refresh(note)
    return note


# --------------------------------------------------------------------------- #
# Seguimientos (actividades)
# --------------------------------------------------------------------------- #
@router.get("/{prospect_id}/activities", response_model=list[ProspectActivityOut])
def list_activities(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    return (
        db.query(ProspectActivity)
        .filter(
            ProspectActivity.tenant_id == user.tenant_id,
            ProspectActivity.prospect_id == prospect_id,
        )
        .order_by(ProspectActivity.created_at.desc())
        .all()
    )


@router.post("/{prospect_id}/activities", response_model=ProspectActivityOut, status_code=201)
def add_activity(
    prospect_id: int,
    data: ProspectActivityCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    p = _get_prospect(db, prospect_id, user.tenant_id)
    act = ProspectActivity(
        tenant_id=user.tenant_id,
        prospect_id=prospect_id,
        kind=data.kind,
        scheduled_at=data.scheduled_at,
        done_at=data.done_at,
        observation=(data.observation or "").strip() or None,
        result=(data.result or "").strip() or None,
        status=data.status,
        user_id=data.user_id or user.id,
        created_by=user.id,
    )
    db.add(act)
    if data.scheduled_at and data.status == "pendiente":
        p.next_followup_at = data.scheduled_at
    _history(
        db, prospect_id=prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="SEGUIMIENTO",
        detail=f"{data.kind} ({data.status}): {(data.result or data.observation or '')[:150]}",
    )
    db.commit()
    db.refresh(act)
    return act


@router.put("/activities/{activity_id}", response_model=ProspectActivityOut)
def update_activity(
    activity_id: int,
    data: ProspectActivityUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    act = (
        db.query(ProspectActivity)
        .filter(
            ProspectActivity.id == activity_id,
            ProspectActivity.tenant_id == user.tenant_id,
        )
        .first()
    )
    if act is None:
        raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    updates = data.model_dump(exclude_unset=True)
    for field in ("kind", "scheduled_at", "done_at", "observation", "result", "status", "user_id"):
        if field in updates:
            setattr(act, field, updates[field])
    if act.status == "realizada" and act.done_at is None:
        act.done_at = datetime.utcnow()
    _history(
        db, prospect_id=act.prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="SEGUIMIENTO_EDITADO", detail=f"Seguimiento #{act.id} actualizado",
    )
    db.commit()
    db.refresh(act)
    return act


# --------------------------------------------------------------------------- #
# Historial
# --------------------------------------------------------------------------- #
@router.get("/{prospect_id}/history", response_model=list[ProspectHistoryOut])
def list_history(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    return (
        db.query(ProspectHistory)
        .filter(
            ProspectHistory.tenant_id == user.tenant_id,
            ProspectHistory.prospect_id == prospect_id,
        )
        .order_by(ProspectHistory.timestamp.desc())
        .all()
    )


# --------------------------------------------------------------------------- #
# Evidencias (adjuntos)
# --------------------------------------------------------------------------- #
@router.get("/{prospect_id}/files", response_model=list[ProspectFileOut])
def list_files(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    return (
        db.query(ProspectFile)
        .filter(ProspectFile.tenant_id == user.tenant_id, ProspectFile.prospect_id == prospect_id)
        .order_by(ProspectFile.created_at.desc())
        .all()
    )


@router.post("/{prospect_id}/files", response_model=ProspectFileOut, status_code=201)
def upload_file(
    prospect_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_FILE_EXT:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")

    dest_dir = app_settings.prospect_files_path / str(user.tenant_id) / str(prospect_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    dest = dest_dir / stored
    size = 0
    with dest.open("wb") as buffer:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                buffer.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="El archivo supera el límite de 10 MB")
            buffer.write(chunk)

    rec = ProspectFile(
        tenant_id=user.tenant_id,
        prospect_id=prospect_id,
        filename=(file.filename or stored)[:255],
        path=str(dest),
        content_type=file.content_type,
        size=size,
        created_by=user.id,
    )
    db.add(rec)
    _history(
        db, prospect_id=prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="EVIDENCIA_AGREGADA", detail=rec.filename,
    )
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/files/{file_id}/download")
def download_file(
    file_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    rec = (
        db.query(ProspectFile)
        .filter(ProspectFile.id == file_id, ProspectFile.tenant_id == user.tenant_id)
        .first()
    )
    if rec is None or not Path(rec.path).exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(rec.path, filename=rec.filename, media_type=rec.content_type or "application/octet-stream")


@router.delete("/files/{file_id}", status_code=204)
def delete_file(
    file_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    rec = (
        db.query(ProspectFile)
        .filter(ProspectFile.id == file_id, ProspectFile.tenant_id == user.tenant_id)
        .first()
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    Path(rec.path).unlink(missing_ok=True)
    _history(
        db, prospect_id=rec.prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="EVIDENCIA_ELIMINADA", detail=rec.filename,
    )
    db.delete(rec)
    db.commit()
    return None


# --------------------------------------------------------------------------- #
# Firma digital
# --------------------------------------------------------------------------- #
def _decode_signature(image_data: str) -> bytes:
    """Acepta data URL (data:image/png;base64,...) o base64 crudo."""
    raw = image_data.split(",", 1)[1] if "," in image_data else image_data
    try:
        return base64.b64decode(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Firma inválida (no se pudo decodificar)")


@router.get("/{prospect_id}/signatures", response_model=list[ProspectSignatureOut])
def list_signatures(
    prospect_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    return (
        db.query(ProspectSignature)
        .filter(ProspectSignature.tenant_id == user.tenant_id, ProspectSignature.prospect_id == prospect_id)
        .order_by(ProspectSignature.created_at.desc())
        .all()
    )


@router.post("/{prospect_id}/signatures", response_model=ProspectSignatureOut, status_code=201)
def save_signature(
    prospect_id: int,
    data: ProspectSignatureCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_prospect(db, prospect_id, user.tenant_id)
    blob = _decode_signature(data.image_data)
    if len(blob) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="La firma es demasiado grande")

    dest_dir = app_settings.prospect_files_path / str(user.tenant_id) / str(prospect_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"firma_{data.role}_{uuid.uuid4().hex}.png"
    dest.write_bytes(blob)

    rec = ProspectSignature(
        tenant_id=user.tenant_id, prospect_id=prospect_id,
        role=data.role, path=str(dest), created_by=user.id,
    )
    db.add(rec)
    _history(
        db, prospect_id=prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="FIRMA_GUARDADA", detail=f"Firma del {data.role}",
    )
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/signatures/{signature_id}/image")
def get_signature_image(
    signature_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    rec = (
        db.query(ProspectSignature)
        .filter(ProspectSignature.id == signature_id, ProspectSignature.tenant_id == user.tenant_id)
        .first()
    )
    if rec is None or not Path(rec.path).exists():
        raise HTTPException(status_code=404, detail="Firma no encontrada")
    return FileResponse(rec.path, media_type="image/png")


# --------------------------------------------------------------------------- #
# Exportación
# --------------------------------------------------------------------------- #
@router.get("/export/excel")
def export_excel(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Prospect)
        .filter(Prospect.tenant_id == user.tenant_id)
        .order_by(Prospect.full_name)
        .all()
    )
    data = []
    for p in rows:
        data.append(
            {
                "Nombre": p.full_name,
                "Teléfono": p.phone or "",
                "Dirección": p.address or "",
                "Estado civil": p.marital_status or "",
                "Ocupación": p.occupation or "",
                "Conoce marca": "Sí" if p.knows_brand else ("No" if p.knows_brand is False else ""),
                "Estado": STATUS_LABELS.get(p.status, p.status),
                "Calificación": p.rating,
                "Etapa": p.stage_slug,
                "Probabilidad %": p.close_probability,
                "Valor potencial": round(p.opportunity_value, 2),
                "Valor ponderado": round(p.weighted_value, 2),
                "Notas": p.notes or "",
                "Creado": p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
            }
        )
    columns = [
        "Nombre", "Teléfono", "Dirección", "Estado civil", "Ocupación", "Conoce marca", "Estado",
        "Calificación", "Etapa", "Probabilidad %", "Valor potencial", "Valor ponderado",
        "Notas", "Creado",
    ]
    df = pd.DataFrame(data, columns=columns)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    filename = f"Prospectos_{date.today().strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
