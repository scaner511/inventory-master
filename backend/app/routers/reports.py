"""Reportes: Excel diario y comprobante PDF de préstamo."""
import io
from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_or_create_settings
from app.models import Loan
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
def daily_report(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    """Inventario completo + movimientos del día en un solo Excel."""
    today_str = date.today().strftime("%Y-%m-%d")

    df_inventory = pd.read_sql_query(
        """
        SELECT code AS Codigo, name AS Nombre, stock AS Stock,
               purchase_price AS Compra, sale_price AS Venta,
               location1 AS Ubicacion1, location2 AS Ubicacion2, location3 AS Ubicacion3
        FROM products ORDER BY name
        """,
        db.bind,
    )

    df_movements = pd.read_sql_query(
        """
        SELECT a.timestamp AS Fecha, COALESCE(u.username, 'Sistema') AS Usuario,
               a.action AS Accion, a.product_name AS Producto, a.quantity AS Cantidad
        FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id
        WHERE DATE(a.timestamp) = :day
        ORDER BY a.timestamp DESC
        """,
        db.bind,
        params={"day": today_str},
    )

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
def loan_ticket(loan_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    loan = db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    setting = get_or_create_settings(db)
    pdf_buffer = generate_loan_pdf(
        seller=loan.seller,
        phone=loan.phone,
        product_name=loan.product_name,
        quantity=loan.quantity,
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
