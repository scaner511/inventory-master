"""Citas comerciales, recordatorios, cierre de visitas y dashboard comercial.

Parte del módulo Gestión de Prospectos. Tablas de negocio (tenant_id).

Endpoints bajo /api/appointments.
"""
import json
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_tenant_db
from app.models import (
    Appointment,
    AppointmentClosure,
    AppointmentReminder,
    Notification,
    Prospect,
    ProspectActivity,
    ProspectHistory,
    SalesPipeline,
    User,
)
from app.schemas import (
    AppointmentClosureCreate,
    AppointmentClosureOut,
    AppointmentCreate,
    AppointmentOut,
    AppointmentUpdate,
    CommercialDashboardOut,
)
from app.utils.audit import record_audit

router = APIRouter(prefix="/api/appointments", tags=["appointments"])

VALID_REMINDER_MINUTES = {15, 30, 60, 120, 240, 480, 1440}


def _get_appointment(db: Session, appt_id: int, tenant_id: int) -> Appointment:
    a = (
        db.query(Appointment)
        .filter(Appointment.id == appt_id, Appointment.tenant_id == tenant_id)
        .first()
    )
    if a is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    return a


def _prospect(db: Session, prospect_id: int, tenant_id: int) -> Prospect:
    p = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id, Prospect.tenant_id == tenant_id)
        .first()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Prospecto no encontrado")
    return p


def _closure_out(c: AppointmentClosure) -> AppointmentClosureOut:
    out = AppointmentClosureOut.model_validate(c)
    for field in ("markers", "interest_products", "delivered_info"):
        raw = getattr(c, field)
        try:
            parsed = json.loads(raw) if raw else []
        except (ValueError, TypeError):
            parsed = []
        setattr(out, field, parsed if isinstance(parsed, list) else [])
    return out


def _history(db, *, prospect_id, tenant_id, user_id, action, detail=None):
    db.add(
        ProspectHistory(
            tenant_id=tenant_id, prospect_id=prospect_id, user_id=user_id,
            action=action, detail=detail,
        )
    )


def _notify(db, *, tenant_id, user_id, kind, title, body=None, entity=None, entity_id=None):
    db.add(
        Notification(
            tenant_id=tenant_id, user_id=user_id, kind=kind, title=title,
            body=body, entity=entity, entity_id=entity_id,
        )
    )


def _setup_reminders(db: Session, appt: Appointment, minutes_list: list[int], tenant_id: int) -> None:
    db.query(AppointmentReminder).filter(
        AppointmentReminder.appointment_id == appt.id,
        AppointmentReminder.tenant_id == tenant_id,
    ).delete(synchronize_session=False)
    for minutes in sorted(set(minutes_list)):
        if minutes not in VALID_REMINDER_MINUTES:
            continue
        fire_at = appt.start_at - timedelta(minutes=minutes)
        db.add(
            AppointmentReminder(
                tenant_id=tenant_id, appointment_id=appt.id,
                minutes_before=minutes, fire_at=fire_at, sent=False,
            )
        )


def _to_out(db: Session, a: Appointment) -> AppointmentOut:
    out = AppointmentOut.model_validate(a)
    p = db.query(Prospect.full_name).filter(Prospect.id == a.prospect_id).first()
    out.prospect_name = p[0] if p else None
    return out


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        hh, mm = value.split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Citas
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Appointment).filter(Appointment.tenant_id == user.tenant_id)
    if date_from:
        query = query.filter(Appointment.start_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(Appointment.start_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if user_id:
        query = query.filter(Appointment.user_id == user_id)
    if status_filter:
        query = query.filter(Appointment.status == status_filter)
    rows = query.order_by(Appointment.start_at).all()
    return [_to_out(db, a) for a in rows]


@router.post("", response_model=AppointmentOut, status_code=201)
def create_appointment(
    data: AppointmentCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    p = _prospect(db, data.prospect_id, user.tenant_id)
    appt = Appointment(
        tenant_id=user.tenant_id,
        prospect_id=p.id,
        start_at=data.start_at,
        end_at=data.end_at,
        user_id=data.user_id or user.id,
        address=(data.address or p.address or "").strip() or None,
        phone=(data.phone or p.phone or "").strip() or None,
        observation=(data.observation or "").strip() or None,
        status=data.status or "programada",
        created_by=user.id,
    )
    db.add(appt)
    db.flush()

    minutes = list(data.reminder_minutes or [])
    if data.reminder_minutes_single:
        minutes.append(data.reminder_minutes_single)
    _setup_reminders(db, appt, minutes, user.tenant_id)

    _history(
        db, prospect_id=p.id, tenant_id=user.tenant_id, user_id=user.id,
        action="CITA_PROGRAMADA",
        detail=f"Cita el {appt.start_at.strftime('%d/%m/%Y %H:%M')}",
    )
    _notify(
        db, tenant_id=user.tenant_id, user_id=appt.user_id, kind="CITA_ASIGNADA",
        title="Nueva cita asignada",
        body=f"{p.full_name} · {appt.start_at.strftime('%d/%m/%Y %H:%M')}",
        entity="appointment", entity_id=appt.id,
    )
    db.commit()
    db.refresh(appt)
    return _to_out(db, appt)


@router.put("/{appt_id}", response_model=AppointmentOut)
def update_appointment(
    appt_id: int,
    data: AppointmentUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    appt = _get_appointment(db, appt_id, user.tenant_id)
    updates = data.model_dump(exclude_unset=True)
    reminder_updates = updates.pop("reminder_minutes", None)
    reschedule = updates.pop("reschedule", False)

    old_start = appt.start_at
    for field in ("start_at", "end_at", "user_id", "address", "phone", "observation", "status"):
        if field in updates and updates[field] is not None:
            setattr(appt, field, updates[field])

    if reschedule and appt.start_at != old_start:
        appt.status = "reagendada"

    if reminder_updates is not None or (reschedule and appt.start_at != old_start):
        current = [r.minutes_before for r in appt.reminders]
        _setup_reminders(db, appt, reminder_updates if reminder_updates is not None else current, user.tenant_id)

    if appt.start_at != old_start:
        _history(
            db, prospect_id=appt.prospect_id, tenant_id=user.tenant_id, user_id=user.id,
            action="CITA_REAGENDADA",
            detail=f"De {old_start.strftime('%d/%m/%Y %H:%M')} a {appt.start_at.strftime('%d/%m/%Y %H:%M')}",
        )
        _notify(
            db, tenant_id=user.tenant_id, user_id=appt.user_id, kind="CITA_REAGENDADA",
            title="Cita reagendada",
            body=f"Nueva fecha: {appt.start_at.strftime('%d/%m/%Y %H:%M')}",
            entity="appointment", entity_id=appt.id,
        )
    else:
        _history(
            db, prospect_id=appt.prospect_id, tenant_id=user.tenant_id, user_id=user.id,
            action="CITA_EDITADA", detail=f"Cita #{appt.id} actualizada",
        )
    db.commit()
    db.refresh(appt)
    return _to_out(db, appt)


@router.delete("/{appt_id}", status_code=204)
def delete_appointment(
    appt_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    appt = _get_appointment(db, appt_id, user.tenant_id)
    _history(
        db, prospect_id=appt.prospect_id, tenant_id=user.tenant_id, user_id=user.id,
        action="CITA_CANCELADA", detail=f"Cita #{appt.id} cancelada",
    )
    _notify(
        db, tenant_id=user.tenant_id, user_id=appt.user_id, kind="CITA_CANCELADA",
        title="Cita cancelada", body=f"Cita #{appt.id} cancelada",
        entity="appointment", entity_id=appt.id,
    )
    db.delete(appt)
    db.commit()
    return None


@router.get("/{appt_id}/reminders", response_model=list[dict])
def list_reminders(
    appt_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_appointment(db, appt_id, user.tenant_id)
    rows = (
        db.query(AppointmentReminder)
        .filter(
            AppointmentReminder.appointment_id == appt_id,
            AppointmentReminder.tenant_id == user.tenant_id,
        )
        .order_by(AppointmentReminder.fire_at)
        .all()
    )
    return [
        {
            "id": r.id,
            "minutes_before": r.minutes_before,
            "fire_at": r.fire_at.isoformat(),
            "sent": r.sent,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Cierre de visitas
# --------------------------------------------------------------------------- #
@router.post("/{appt_id}/closure", response_model=AppointmentClosureOut, status_code=201)
def close_appointment(
    appt_id: int,
    data: AppointmentClosureCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Formulario obligatorio de cierre de visita."""
    appt = _get_appointment(db, appt_id, user.tenant_id)

    existing = (
        db.query(AppointmentClosure)
        .filter(
            AppointmentClosure.appointment_id == appt_id,
            AppointmentClosure.tenant_id == user.tenant_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Esta visita ya tiene un cierre registrado")

    # Tiempo total de visita.
    total_minutes = None
    arrival = _parse_time(data.arrival_time)
    departure = _parse_time(data.departure_time)
    if arrival and departure:
        start_dt = datetime.combine(date.today(), arrival)
        end_dt = datetime.combine(date.today(), departure)
        total_minutes = int((end_dt - start_dt).total_seconds() // 60)
        if total_minutes < 0:
            total_minutes += 24 * 60

    closure = AppointmentClosure(
        tenant_id=user.tenant_id,
        appointment_id=appt.id,
        prospect_id=appt.prospect_id,
        visit_date=data.visit_date or appt.start_at.date(),
        arrival_time=data.arrival_time,
        departure_time=data.departure_time,
        total_minutes=total_minutes,
        user_id=user.id,
        result=data.result,
        result_detail=data.result_detail.strip(),
        markers=json.dumps(data.markers) if data.markers else None,
        interest_level=data.interest_level,
        demo_done=data.demo_done,
        demo_description=(data.demo_description or "").strip() or None,
        interest_products=json.dumps(data.interest_products) if data.interest_products else None,
        delivered_info=json.dumps(data.delivered_info) if data.delivered_info else None,
        commercial_status=data.commercial_status,
        created_by=user.id,
    )
    db.add(closure)

    # Actualizar la cita.
    appt.status = "completada"

    # Actualizar el prospecto según el resultado.
    p = _prospect(db, appt.prospect_id, user.tenant_id)
    p.rating = data.interest_level
    if data.interest_products:
        p.interested_products = json.dumps(data.interest_products)
    if data.commercial_status:
        p.commercial_status = data.commercial_status

    if data.result == "venta_realizada":
        p.status = "cliente_convertido"
        p.commercial_status = "cliente_convertido"
        p.stage_slug = "cliente"
        p.converted_at = datetime.utcnow()
        p.converted_by = user.id
        p.close_probability = 100
    elif data.result == "no_interesado":
        p.status = "no_interesado"
        p.commercial_status = "no_interesado"
        p.stage_slug = "no_interesado"
    elif data.result in ("interesado", "requiere_seguimiento", "pendiente_decision"):
        if p.status in ("nuevo", "contactado", "pendiente_cita"):
            p.status = "visitado"
        p.stage_slug = "visitado"
    elif data.result in ("solicito_propuesta", "solicito_demostracion"):
        p.stage_slug = "propuesta_enviada"
        p.commercial_status = "propuesta_enviada"

    # Próximo seguimiento.
    if data.next_followup_at:
        p.next_followup_at = data.next_followup_at
        db.add(
            ProspectActivity(
                tenant_id=user.tenant_id, prospect_id=p.id,
                kind=data.next_followup_kind or "llamada",
                scheduled_at=data.next_followup_at,
                observation=data.next_followup_observation,
                status="pendiente", user_id=user.id, created_by=user.id,
            )
        )

    # Resumen automático.
    summary_bits = [f"El prospecto {p.full_name}"]
    if data.demo_done:
        summary_bits.append("recibió demostración")
    summary_bits.append(f"resultado de la visita: {data.result.replace('_', ' ')}")
    if data.next_followup_at:
        summary_bits.append(f"seguimiento programado para {data.next_followup_at.strftime('%d/%m/%Y')}")
    p.summary = ". ".join(summary_bits) + "."

    _history(
        db, prospect_id=p.id, tenant_id=user.tenant_id, user_id=user.id,
        action="CIERRE_VISITA",
        detail=f"Resultado: {data.result} ({total_minutes} min)" if total_minutes else f"Resultado: {data.result}",
    )
    if p.converted_at:
        _notify(
            db, tenant_id=user.tenant_id, user_id=p.owner_id, kind="CONVERSION",
            title="Prospecto convertido en cliente",
            body=f"{p.full_name} cerró venta en la visita.", entity="prospect", entity_id=p.id,
        )
        record_audit(
            db, action="PROSPECTO_CONVERTIDO", user_id=user.id, tenant_id=user.tenant_id,
            detail=f"Prospecto '{p.full_name}' convertido en cliente (cierre de visita)",
        )
    if data.convert and not p.converted_at:
        p.status = "cliente_convertido"
        p.commercial_status = "cliente_convertido"
        p.stage_slug = "cliente"
        p.converted_at = datetime.utcnow()
        p.converted_by = user.id

    db.commit()
    db.refresh(closure)
    return _closure_out(closure)


@router.get("/{appt_id}/closure", response_model=AppointmentClosureOut)
def get_closure(
    appt_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_appointment(db, appt_id, user.tenant_id)
    closure = (
        db.query(AppointmentClosure)
        .filter(
            AppointmentClosure.appointment_id == appt_id,
            AppointmentClosure.tenant_id == user.tenant_id,
        )
        .first()
    )
    if closure is None:
        raise HTTPException(status_code=404, detail="La visita no tiene cierre registrado")
    return _closure_out(closure)


# --------------------------------------------------------------------------- #
# Dashboard comercial
# --------------------------------------------------------------------------- #
@router.get("/dashboard/commercial", response_model=CommercialDashboardOut)
def commercial_dashboard(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    today = date.today()
    prospects = db.query(Prospect).filter(Prospect.tenant_id == user.tenant_id).all()
    total = len(prospects)
    converted = sum(1 for p in prospects if p.converted_at)
    active = [p for p in prospects if not p.converted_at and p.status != "no_interesado"]

    active_value = sum(p.opportunity_value for p in active)
    weighted_value = sum(p.weighted_value for p in active)

    appts_today = (
        db.query(Appointment.id)
        .filter(
            Appointment.tenant_id == user.tenant_id,
            Appointment.start_at >= datetime.combine(today, time.min),
            Appointment.start_at < datetime.combine(today + timedelta(days=1), time.min),
        )
        .count()
    )
    week_end = today + timedelta(days=7)
    appts_week = (
        db.query(Appointment.id)
        .filter(
            Appointment.tenant_id == user.tenant_id,
            Appointment.start_at >= datetime.combine(today, time.min),
            Appointment.start_at < datetime.combine(week_end, time.min),
        )
        .count()
    )
    pending_followups = (
        db.query(ProspectActivity.id)
        .filter(
            ProspectActivity.tenant_id == user.tenant_id,
            ProspectActivity.status == "pendiente",
        )
        .count()
    )

    by_status: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    by_month: dict[str, int] = {}
    top_products: dict[str, int] = {}
    lost_reasons: dict[str, int] = {}

    for p in prospects:
        by_status[p.status] = by_status.get(p.status, 0) + 1
        by_stage[p.stage_slug or "nuevo"] = by_stage.get(p.stage_slug or "nuevo", 0) + 1
        if p.created_at:
            key = p.created_at.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0) + 1
        if p.lost_reason:
            lost_reasons[p.lost_reason] = lost_reasons.get(p.lost_reason, 0) + 1
        try:
            prods = json.loads(p.interested_products) if p.interested_products else []
        except (ValueError, TypeError):
            prods = []
        for prod in prods if isinstance(prods, list) else []:
            top_products[prod] = top_products.get(prod, 0) + 1

    return CommercialDashboardOut(
        total_prospects=total,
        converted=converted,
        conversion_rate=round((converted / total * 100) if total else 0, 1),
        active_pipeline_value=active_value,
        weighted_value=weighted_value,
        appointments_today=appts_today,
        appointments_week=appts_week,
        pending_followups=pending_followups,
        by_status=[{"status": k, "count": v} for k, v in by_status.items()],
        by_stage=[{"stage": k, "count": v} for k, v in by_stage.items()],
        by_month=sorted([{"month": k, "count": v} for k, v in by_month.items()]),
        top_products=sorted(
            [{"product": k, "count": v} for k, v in top_products.items()],
            key=lambda x: x["count"], reverse=True,
        ),
        lost_reasons=sorted(
            [{"reason": k, "count": v} for k, v in lost_reasons.items()],
            key=lambda x: x["count"], reverse=True,
        ),
    )
