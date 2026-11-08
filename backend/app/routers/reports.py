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
