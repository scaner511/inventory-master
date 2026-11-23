"""Reportes: Excel diario y comprobante PDF de préstamo."""
import io
from datetime import date, datetime, time, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal as PlatformSessionLocal
from app.deps import get_current_user, get_or_create_settings, get_tenant_db
from app.models import CalculatorLink, Loan, User
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


def _build_sales_report(
    db: Session,
    tenant_id: int,
    period: str,
    on_date: str | None,
    commission_pct: float,
    viewer_id: int | None = None,
    viewer_role: str | None = None,
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
    prospect_rows = (
        db.query(Prospect.id, Prospect.full_name, Prospect.owner_id)
        .filter(Prospect.tenant_id == tenant_id)
        .all()
    )
    prospect_names = {pid: name for pid, name, _owner in prospect_rows}
    prospect_owners = {pid: owner for pid, _name, owner in prospect_rows}

    # Mapa identidad-del-vendedor -> sección, resuelto en la plataforma:
    # los enlaces públicos y los usuarios pueden tener un nombre real
    # (seller_name) que no sigue el patrón "Prefijo 001" de la etiqueta.
    section_map: dict[str, str] = {}
    pldb = PlatformSessionLocal()
    try:
        links = (
            pldb.query(CalculatorLink)
            .filter(CalculatorLink.tenant_id == tenant_id)
            .all()
        )
        for link in links:
            section = _seller_section(link.label or link.seller_name or "") or "General"
            for key in (link.label, link.seller_name):
                if key and key.strip():
                    section_map[key.strip()] = section
        users = pldb.query(User).filter(User.tenant_id == tenant_id).all()
        for u in users:
            section = _seller_section(u.username or "") or "General"
            for key in (u.username, u.seller_name):
                if key and key.strip():
                    section_map[key.strip()] = section
    finally:
        pldb.close()

    sellers: dict[str, dict] = {}

    def entry(label: str) -> dict:
        label = (label or "").strip() or "Sin vendedor"
        if label not in sellers:
            sellers[label] = {
                "seller": label,
                "section": section_map.get(label) or _seller_section(label),
                "prospects_captured": 0,
                "captured_list": [],
                "presentations": 0,
                "presentation_list": [],
                "clients_closed": 0,
                "closed_list": [],
                "sales_total": 0.0,
                "pending_sales_total": 0.0,
                "sales_list": [],
            }
        return sellers[label]

    # 1) Visitas de la calculadora (enlaces públicos + panel interno).
    events = (
        db.query(VisitEvent)
        .filter(
            VisitEvent.tenant_id == tenant_id,
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
        # Las ventas registradas por cierre de cita (source='cita') ya cuentan
        # como presentación en el bucle de cierres; no se duplican.
        if e.source != "cita":
            s["presentations"] += 1
            s["presentation_list"].append({"date": day, "source": "calculadora", "detail": e.result})
        if e.result == "compra":
            total = float(e.quote_total or 0)
            s["clients_closed"] += 1
            s["closed_list"].append({"name": pname, "date": day, "total": total})
            can_approve = (
                viewer_role in ("admin", "superadmin")
                or (viewer_id is not None and viewer_id in {e.user_id, prospect_owners.get(e.prospect_id)})
            )
            item = {
                "event_id": e.id,
                "name": pname,
                "date": day,
                "total": total,
                "approved": bool(e.approved),
                "source": e.source or "calculadora",
                "can_approve": bool(can_approve),
            }
            s["sales_list"].append(item)
            # Solo las ventas aprobadas cuentan para comisión.
            if e.approved:
                s["sales_total"] += total
            else:
                s["pending_sales_total"] += total

    # 2) Prospectos captados en el período (atribuidos por prospector_name).
    captured = (
        db.query(Prospect)
        .filter(
            Prospect.tenant_id == tenant_id,
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
            AppointmentClosure.tenant_id == tenant_id,
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
                pldb.query(User.id, User.username, User.seller_name)
                .filter(User.id.in_(closure_user_ids))
                .all()
            )
            user_names = {uid: (sname or uname) for uid, uname, sname in rows}
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


    # ITBIS configurado por el cliente (por defecto 18%).
    settings_obj = get_or_create_settings(db, tenant_id)
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
            "pending_sales_total": sum(s["pending_sales_total"] for s in rows),
            "sales_base": base_total,
            "commission": base_total * commission_pct / 100,
            "presentations": sum(s["presentations"] for s in rows),
            "clients_closed": sum(s["clients_closed"] for s in rows),
            "prospects_captured": sum(s["prospects_captured"] for s in rows),
            "sellers_count": len(rows),
        },
    }

@router.get("/sales")
def sales_report(
    period: str = "month",
    on_date: str | None = None,
    commission_pct: float = 10,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Reporte de ventas por vendedor para el período elegido."""
    return _build_sales_report(
        db, user.tenant_id, period, on_date, commission_pct,
        viewer_id=user.id, viewer_role=user.role,
    )


def _render_sales_pdf(data: dict) -> bytes:
    """Renderiza el reporte de ventas a PDF con reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    W, _H = letter
    left, right = 40, W - 40

    def new_page():
        c.showPage()
        c.setFont("Helvetica", 8)
        c.drawRightString(right, 20, "Inventory Master OS - Reporte de Ventas")

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, 750, "Reporte Mensual de Ventas")
    c.setFont("Helvetica", 10)
    c.drawString(left, 732, f"Periodo: {data['period']}  |  {data['from']} a {data['to']}")
    c.drawString(
        left, 716,
        f"Comision: {data['commission_pct']}%  |  ITBIS: {data['itbis_rate']}%",
    )

    t = data["totals"]
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, 690, "TOTALES")
    c.setFont("Helvetica", 10)
    y = 672
    rows = [
        ("Ventas aprobadas", f"RD$ {t['sales_total']:,.2f}"),
        ("Ventas pendientes", f"RD$ {t['pending_sales_total']:,.2f}"),
        ("Base sin ITBIS", f"RD$ {t['sales_base']:,.2f}"),
        ("Comision", f"RD$ {t['commission']:,.2f}"),
        ("Clientes cerrados", str(t["clients_closed"])),
        ("Presentaciones", str(t["presentations"])),
        ("Prospectos captados", str(t["prospects_captured"])),
        ("Vendedores", str(t["sellers_count"])),
    ]
    for label, val in rows:
        c.drawString(left + 10, y, label)
        c.drawString(left + 220, y, val)
        y -= 16

    y -= 10
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "POR VENDEDOR")
    y -= 18
    c.setFont("Helvetica-Bold", 8)
    headers = ["Vendedor", "Seccion", "Clientes", "Prospectos", "Presentaciones", "Ventas", "Comision"]
    xs = [left, left + 130, left + 190, left + 240, left + 300, left + 360, left + 440]
    for x, h in zip(xs, headers):
        c.drawString(x, y, h)
    y -= 6
    c.line(left, y + 4, right, y + 4)
    y -= 12
    c.setFont("Helvetica", 8)

    sections: dict[str, list] = {}
    for s in data["sellers"]:
        sections.setdefault(s["section"], []).append(s)

    for section in sorted(sections):
        if y < 70:
            new_page()
            y = 770
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left, y, section.upper())
        y -= 14
        for s in sections[section]:
            if y < 60:
                new_page()
                y = 770
            base = s["sales_total"] / (1 + (data["itbis_rate"] or 18) / 100)
            comm = base * data["commission_pct"] / 100
            vals = [
                s["seller"][:24],
                "",
                str(s["clients_closed"]),
                str(s["prospects_captured"]),
                str(s["presentations"]),
                f"{s['sales_total']:,.2f}",
                f"{comm:,.2f}",
            ]
            for x, v in zip(xs, vals):
                c.drawString(x, y, v)
            y -= 13
        y -= 6

    c.showPage()
    c.save()
    return buf.getvalue()


@router.get("/sales/pdf")
def sales_report_pdf(
    period: str = "month",
    on_date: str | None = None,
    commission_pct: float = 10,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Exporta el reporte de ventas a PDF."""
    data = _build_sales_report(
        db, user.tenant_id, period, on_date, commission_pct,
        viewer_id=user.id, viewer_role=user.role,
    )
    pdf = _render_sales_pdf(data)
    filename = f"reporte-ventas-{period}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/sales-events/{event_id}/approval")
def set_sale_approval(
    event_id: int,
    payload: dict,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Aprueba o revoca una venta para comisión.

    Solo el administrador o el usuario encargado de la venta (quien la
    registró o el responsable del prospecto) puede aprobarla.
    """
    event = (
        db.query(VisitEvent)
        .filter(
            VisitEvent.id == event_id,
            VisitEvent.tenant_id == user.tenant_id,
            VisitEvent.result == "compra",
        )
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    prospect = (
        db.query(Prospect)
        .filter(Prospect.id == event.prospect_id, Prospect.tenant_id == user.tenant_id)
        .first()
    )
    allowed = (
        user.role in ("admin", "superadmin")
        or user.id == event.user_id
        or (prospect is not None and user.id == prospect.owner_id)
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Solo el usuario encargado o un administrador puede aprobar ventas",
        )
    approved = bool(payload.get("approved"))
    event.approved = approved
    event.approved_by = user.id if approved else None
    event.approved_at = datetime.utcnow() if approved else None
    db.commit()
    return {"id": event.id, "approved": event.approved}

