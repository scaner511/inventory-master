"""Generación de PDFs (comprobantes de préstamo) con logo de empresa."""
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def generate_loan_pdf(
    seller: str,
    phone: str | None,
    items: list[tuple[str, int]],
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

    y = 680
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Vendedor:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, seller)
    y -= 28
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Telefono:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, phone or "-")
    y -= 40

    # Producto(s) prestado(s): uno o varios por préstamo.
    if len(items) == 1:
        product_name, quantity = items[0]
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Producto:")
        c.setFont("Helvetica", 11)
        c.drawString(180, y, product_name)
        y -= 28
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "Cantidad:")
        c.setFont("Helvetica", 11)
        c.drawString(180, y, str(quantity))
        y -= 40
    else:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, f"Productos ({len(items)}):")
        y -= 26
        c.setFont("Helvetica", 10.5)
        for idx, (product_name, quantity) in enumerate(items, 1):
            c.drawString(70, y, f"{idx}. {product_name}")
            c.drawString(500, y, f"x{quantity}")
            y -= 22
        y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Fecha de Entrega:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, loan_date)
    y -= 28
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Fecha de Devolucion:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(due_date))

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
