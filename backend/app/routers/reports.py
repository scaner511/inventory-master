"""Reportes: Excel diario y comprobante PDF de préstamo."""
import io
from datetime import date, datetime, time, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal as PlatformSessionLocal
from app.deps import get_current_user, get_or_create_settings, get_tenant_db
from app.models import Loan, User
from app.services.pdf import generate_loan_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _excel_response(df: pd.DataFrame, filename: str) -> StreamingResponse:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily")
def daily_report(db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    """Inventario completo + movimientos del día en un solo Excel."""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    day_start = datetime.combine(today, time.min)          # hoy 00:00
    day_end = day_start + timedelta(days=1)                # mañana 00:00

    df_inventory = pd.read_sql(
        text(
            """
            SELECT code AS Codigo, name AS Nombre, stock AS Stock,
                   purchase_price AS Compra, sale_price AS Venta,
                   location1 AS Ubicacion1, location2 AS Ubicacion2, location3 AS Ubicacion3
            FROM products
            WHERE tenant_id = :tid
            ORDER BY name
            """
        ),
        db.bind,
        params={"tid": user.tenant_id},
    )

    # Se filtran los movimientos por rango (>= inicio del día y < inicio del
    # siguiente) en vez de DATE(): así la consulta sirve igual en SQLite y en
    # PostgreSQL, donde comparar una columna date con un parámetro de texto
    # rompe porque no existe el operador date = character varying.
    # IMPORTANTE: se usa text(...) para que SQLAlchemy bindee :tid/:start/:end;
    # pasar SQL crudo a pandas con params rompe en PostgreSQL (sintaxis ':').
    # El nombre de usuario se resuelve desde la plataforma (los usuarios de
    # negocio no comparten base con el cliente).
    df_movements = pd.read_sql(
        text(
            """
            SELECT a.timestamp AS Fecha, a.user_id, a.action AS Accion,
                   a.product_name AS Producto, a.quantity AS Cantidad
            FROM audit_logs a
            WHERE a.tenant_id = :tid AND a.timestamp >= :start AND a.timestamp < :end
            ORDER BY a.timestamp DESC
            """
        ),
        db.bind,
        params={"tid": user.tenant_id, "start": day_start, "end": day_end},
    )
    if not df_movements.empty:
        pldb = PlatformSessionLocal()
        try:
            ids = df_movements["user_id"].dropna().astype(int).tolist()
            names = {}
            if ids:
                rows = pldb.query(User.id, User.username).filter(User.id.in_(ids)).all()
                names = {r[0]: r[1] for r in rows}
        finally:
            pldb.close()
        df_movements["Usuario"] = df_movements["user_id"].map(names).fillna("Sistema")
        df_movements = df_movements.drop(columns=["user_id"])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_inventory.to_excel(writer, sheet_name="Inventario_Actual", index=False)
        df_movements.to_excel(writer, sheet_name="Movimientos_Hoy", index=False)
    buffer.seek(0)

    filename = f"Reporte_Diario_{today_str}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/loan-ticket/{loan_id}")
def loan_ticket(loan_id: int, db: Session = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.tenant_id == user.tenant_id)
        .first()
    )
    if not loan:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    setting = get_or_create_settings(db, user.tenant_id)
    pdf_buffer = generate_loan_pdf(
        seller=loan.seller,
        phone=loan.phone,
        items=[(item.product_name, item.quantity) for item in loan.items],
        loan_date=loan.loan_date.strftime("%d/%m/%Y %H:%M"),
        due_date=loan.due_date.strftime("%d/%m/%Y"),
        logo_path=setting.logo_path,
        company_name=setting.company_name or "MC'CEA INVENTORY",
    )

    filename = f"Ticket_{loan.seller.replace(' ', '_')}_{loan.id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Reporte mensual de ventas por vendedor (calculadora + citas)
# --------------------------------------------------------------------------- #
import re as _re

from app.models import AppointmentClosure, Prospect, VisitEvent


def _sales_period(period: str, anchor: date) -> tuple[datetime, datetime]:
    """Rango [start, end) según el período elegido."""
    if period == "day":
        start_d, end_d = anchor, anchor + timedelta(days=1)
    elif period == "week":
        start_d = anchor - timedelta(days=anchor.weekday())  # lunes
        end_d = start_d + timedelta(days=7)
    elif period == "year":
        start_d = anchor.replace(month=1, day=1)
        end_d = start_d.replace(year=start_d.year + 1)
    else:  # month
        start_d = anchor.replace(day=1)
        if start_d.month == 12:
            end_d = start_d.replace(year=start_d.year + 1, month=1)
        else:
            end_d = start_d.replace(month=start_d.month + 1)
    return (
        datetime.combine(start_d, time.min),
        datetime.combine(end_d, time.min),
    )


def _seller_section(label: str) -> str:
    """Sección del vendedor = etiqueta sin el número final.

    'Vendedor 001' -> 'Vendedor', 'Norte-015' -> 'Norte', 'mmoore' -> 'mmoore'.
    """
    section = _re.sub(r"[\s\-_.#]*\d+\s*$", "", label).strip()
    return section or label.strip() or "General"


@router.get("/sales")
def sales_report(
    period: str = "month",
    on_date: str | None = None,
    commission_pct: float = 10,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Reporte de ventas por vendedor para el período elegido.

    Fuentes: visitas de la calculadora (visit_events), prospectos captados
    (prospector_name) y cierres de citas (appointment_closures). Las ventas
    aprobadas son las compras marcadas en la calculadora con su total.
    """
    if period not in ("day", "week", "month", "year"):
        raise HTTPException(status_code=400, detail="Período inválido")
    try:
        anchor = date.fromisoformat(on_date) if on_date else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida")
    if commission_pct < 0 or commission_pct > 100:
        raise HTTPException(status_code=400, detail="Comisión inválida")

    start, end = _sales_period(period, anchor)

    # Nombres de prospectos para los detalles.
    prospect_names = {
        p.id: p.full_name
        for p in db.query(Prospect.id, Prospect.full_name)
        .filter(Prospect.tenant_id == user.tenant_id)
        .all()
    }

    sellers: dict[str, dict] = {}

    def entry(label: str) -> dict:
        label = (label or "").strip() or "Sin vendedor"
        if label not in sellers:
            sellers[label] = {
                "seller": label,
                "section": _seller_section(label),
                "prospects_captured": 0,
                "captured_list": [],
                "presentations": 0,
                "presentation_list": [],
                "clients_closed": 0,
                "closed_list": [],
                "sales_total": 0.0,
                "sales_list": [],
            }
        return sellers[label]

    # 1) Visitas de la calculadora (enlaces públicos + panel interno).
    events = (
        db.query(VisitEvent)
        .filter(
            VisitEvent.tenant_id == user.tenant_id,
            VisitEvent.created_at >= start,
            VisitEvent.created_at < end,
        )
        .order_by(VisitEvent.created_at)
        .all()
    )
    for e in events:
        s = entry(e.seller_label)
        day = e.created_at.strftime("%Y-%m-%d") if e.created_at else None
        pname = prospect_names.get(e.prospect_id, "Cliente")
        s["presentations"] += 1
        s["presentation_list"].append({"date": day, "source": "calculadora", "detail": e.result})
        if e.result == "compra":
            total = float(e.quote_total or 0)
            s["clients_closed"] += 1
            s["closed_list"].append({"name": pname, "date": day, "total": total})
            s["sales_total"] += total
            s["sales_list"].append({"name": pname, "date": day, "total": total})

    # 2) Prospectos captados en el período (atribuidos por prospector_name).
    captured = (
        db.query(Prospect)
        .filter(
            Prospect.tenant_id == user.tenant_id,
            Prospect.created_at >= start,
            Prospect.created_at < end,
            Prospect.prospector_name.isnot(None),
            Prospect.prospector_name != "",
        )
        .order_by(Prospect.created_at)
        .all()
    )
    for p in captured:
        s = entry(p.prospector_name)
        s["prospects_captured"] += 1
        s["captured_list"].append(
            {"name": p.full_name, "date": p.created_at.strftime("%Y-%m-%d") if p.created_at else None}
        )

    # 3) Cierres de citas del módulo de citas (presentaciones por usuario).
    closures = (
        db.query(AppointmentClosure)
        .filter(
            AppointmentClosure.tenant_id == user.tenant_id,
            AppointmentClosure.visit_date >= start.date(),
            AppointmentClosure.visit_date < end.date(),
        )
        .all()
    )
    closure_user_ids = {c.user_id for c in closures if c.user_id}
    user_names: dict[int, str] = {}
    if closure_user_ids:
        pldb = PlatformSessionLocal()
        try:
            rows = (
                pldb.query(User.id, User.username)
                .filter(User.id.in_(closure_user_ids))
                .all()
            )
            user_names = {uid: uname for uid, uname in rows}
        finally:
            pldb.close()
    for c in closures:
        label = user_names.get(c.user_id) or (f"Usuario #{c.user_id}" if c.user_id else "Sin vendedor")
        s = entry(label)
        s["presentations"] += 1
        pname = prospect_names.get(c.prospect_id, "Cliente")
        s["presentation_list"].append(
            {
                "date": c.visit_date.isoformat() if c.visit_date else None,
                "source": "cita",
                "detail": c.result,
                "name": pname,
            }
        )
        if c.result == "venta_realizada":
            total = float(c.monthly_value or 0) + float(c.setup_value or 0)
            s["clients_closed"] += 1
            s["closed_list"].append(
                {"name": pname, "date": c.visit_date.isoformat() if c.visit_date else None, "total": total}
            )
            s["sales_total"] += total
            s["sales_list"].append(
                {"name": pname, "date": c.visit_date.isoformat() if c.visit_date else None, "total": total}
            )

    # ITBIS configurado por el cliente (por defecto 18%).
    settings_obj = get_or_create_settings(db, user.tenant_id)
    itbis_rate = float(settings_obj.itbis_rate or 18)

    rows = sorted(sellers.values(), key=lambda s: (-s["sales_total"], s["seller"]))
    grand_total = sum(s["sales_total"] for s in rows)
    base_total = grand_total / (1 + itbis_rate / 100) if grand_total else 0.0

    return {
        "period": period,
        "from": start.date().isoformat(),
        "to": (end.date() - timedelta(days=1)).isoformat(),
        "commission_pct": commission_pct,
        "itbis_rate": itbis_rate,
        "sellers": rows,
        "totals": {
            "sales_total": grand_total,
            "sales_base": base_total,
            "commission": base_total * commission_pct / 100,
            "presentations": sum(s["presentations"] for s in rows),
            "clients_closed": sum(s["clients_closed"] for s in rows),
            "prospects_captured": sum(s["prospects_captured"] for s in rows),
        },
    }
