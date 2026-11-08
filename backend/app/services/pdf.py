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


def generate_temporary_storage_pdf(
    data: dict,
    logo_path: str | None = None,
    company_name: str = "MC'CEA INVENTORY",
) -> io.BytesIO:
    """Comprobante de recepción de mercancía en depósito temporal.

    `data` incluye: number, short_code, entry_date, deadline_date, party_name,
    party_company, party_phone, party_email, reference_document, location_name,
    note, status, y items = [{product_name, quantity, returned_qty, pending}].
    Si la recepción ya tiene salida, agrega el bloque de devolución/retiro.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    if logo_path and Path(logo_path).exists():
        try:
            c.drawImage(logo_path, 50, 720, width=130, height=80, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 15)
    c.drawString(200, 755, "RECEPCION DE MERCANCIA")
    c.setFont("Helvetica", 10)
    c.drawString(200, 740, "Deposito temporal de mercancia de terceros")

    y = 710
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "No. Recepcion:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("number", "-")))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(380, y, "Codigo:")
    c.setFont("Helvetica", 11)
    c.drawString(450, y, str(data.get("short_code", "-")))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Estado:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("status", "-")))

    y -= 34
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Tercero / Vendedor:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("party_name", "-")))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Empresa:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("party_company") or "-"))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Telefono:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("party_phone") or "-"))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Correo:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("party_email") or "-"))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Doc. Referencia:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("reference_document") or "-"))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Ubicacion:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("location_name") or "-"))
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Fecha Entrada:")
    c.setFont("Helvetica", 11)
    c.drawString(180, y, str(data.get("entry_date", "-")))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(380, y, "Fecha Limite:")
    c.setFont("Helvetica", 11)
    c.drawString(450, y, str(data.get("deadline_date", "-")))

    y -= 34
    c.line(50, y, 550, y)
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "PRODUCTOS")
    y -= 22
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "#")
    c.drawString(90, y, "Producto")
    c.drawString(420, y, "Cant.")
    c.drawString(480, y, "Pend.")
    y -= 16
    c.setFont("Helvetica", 10)
    items = data.get("items") or []
    for idx, it in enumerate(items, 1):
        if y < 120:
            c.showPage()
            y = 750
            c.setFont("Helvetica", 10)
        name = str(it.get("product_name", ""))
        if len(name) > 55:
            name = name[:52] + "..."
        c.drawString(60, y, str(idx))
        c.drawString(90, y, name)
        c.drawString(420, y, str(it.get("quantity", 0)))
        c.drawString(480, y, str(it.get("pending", it.get("quantity", 0))))
        y -= 18

    total_units = sum(int(it.get("quantity", 0)) for it in items)
    y -= 6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(90, y, "TOTAL DE UNIDADES:")
    c.drawString(420, y, str(total_units))
    y -= 30

    if data.get("exit_type"):
        c.line(50, y, 550, y)
        y -= 20
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, f"SALIDA ({str(data.get('exit_type')).upper()})")
        y -= 22
        c.setFont("Helvetica", 10)
        c.drawString(60, y, f"Fecha: {data.get('exit_date') or '-'}")
        y -= 18
        c.drawString(60, y, f"Responsable: {data.get('exit_responsible') or '-'}")
        y -= 18
        c.drawString(60, y, f"Documento: {data.get('exit_document') or '-'}")
        y -= 18
        c.drawString(60, y, f"Observaciones: {data.get('exit_note') or '-'}")
        y -= 30

    if data.get("note"):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Observaciones:")
        y -= 18
        c.setFont("Helvetica", 10)
        note = str(data.get("note"))
        c.drawString(60, y, note[:95])
        y -= 40

    if y > 130:
        c.line(50, y, 220, y)
        c.line(320, y, 500, y)
        c.setFont("Helvetica", 10)
        c.drawString(70, y - 15, "Firma de quien entrega")
        c.drawString(340, y - 15, "Firma de quien recibe")

    c.setFont("Helvetica", 9)
    c.drawString(
        50,
        50,
        "Mercancia de terceros en deposito temporal - NO es propiedad de "
        f"{company_name} - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
    )

    c.save()
    buffer.seek(0)
    return buffer
