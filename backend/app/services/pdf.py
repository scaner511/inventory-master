"""Generación de PDFs (comprobantes de préstamo) con logo de empresa."""
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def generate_loan_pdf(
    seller: str,
    phone: str | None,
    product_name: str,
    quantity: int,
    loan_date: str,
    due_date: str,
    logo_path: str | None = None,
    company_name: str = "MC'CEA INVENTORY",
) -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Logo
    if logo_path and Path(logo_path).exists():
        try:
            c.drawImage(logo_path, 50, 720, width=130, height=80, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 18)
    c.drawString(200, 750, "COMPROBANTE DE PRESTAMO")

    c.setFont("Helvetica", 12)
    y = 680
    datos = [
        ("Vendedor:", seller),
        ("Telefono:", phone or "-"),
        ("Producto:", product_name),
        ("Cantidad:", str(quantity)),
        ("Fecha de Entrega:", loan_date),
        ("Fecha de Devolucion:", str(due_date)),
    ]
    for label, value in datos:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, label)
        c.setFont("Helvetica", 11)
        c.drawString(180, y, value)
        y -= 28

    y -= 20
    c.line(50, y, 550, y)
    y -= 30
    c.setFont("Helvetica", 11)
    c.drawString(50, y, "La mercancia fue entregada en buen estado.")
    y -= 40

    c.line(50, y, 220, y)
    c.line(320, y, 500, y)
    c.setFont("Helvetica", 10)
    c.drawString(70, y - 15, "Firma del Vendedor")
    c.drawString(340, y - 15, "Firma de Despacho / Administrador")

    c.setFont("Helvetica", 9)
    c.drawString(50, 50, f"Generado por {company_name} - {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    c.save()
    buffer.seek(0)
    return buffer
