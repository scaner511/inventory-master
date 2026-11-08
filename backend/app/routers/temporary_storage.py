"""Recepción de mercancía: depósito temporal de mercancía de terceros.

Módulo INDEPENDIENTE del inventario oficial. Nunca modifica products.stock ni
product_stock_locations: solo registra, ubica, alerta, retira y audita
mercancía que no es propiedad de la empresa.

Endpoints bajo /api/temporary-storage.
"""
import io
import random
import string
from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal as PlatformSessionLocal
from app.deps import get_current_user, get_or_create_settings, get_tenant_db, require_admin
from app.models import (
    TemporaryStorage,
    TemporaryStorageHistory,
    TemporaryStorageItem,
    TemporaryStorageLocation,
    User,
)
from app.schemas import (
    TsCreate,
    TsDashboardOut,
    TsExit,
    TsHistoryOut,
    TsItemOut,
    TsLocationCreate,
    TsLocationOut,
    TsLocationUpdate,
    TsOut,
    TsUpdate,
)
from app.services.pdf import generate_temporary_storage_pdf

router = APIRouter(prefix="/api/temporary-storage", tags=["temporary-storage"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

EXIT_TYPE_LABEL = {"devuelto": "Devuelto", "retirado": "Retirado"}
STATUS_LABEL = {
    "recibido": "Recibido",
    "almacenado": "Almacenado",
    "proximo_vencer": "Próximo a vencer",
    "vencido": "Vencido",
    "devuelto": "Devuelto",
    "retirado": "Retirado",
}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _record_history(
    db: Session,
    *,
    storage_id: int | None,
    tenant_id: int | None,
    user_id: int | None,
    action: str,
    detail: str | None = None,
) -> None:
    db.add(
        TemporaryStorageHistory(
            tenant_id=tenant_id,
            storage_id=storage_id,
            user_id=user_id,
            action=action,
            detail=detail,
        )
    )


def _username(user_id: int | None) -> str:
    if not user_id:
        return "Sistema"
    pldb = PlatformSessionLocal()
    try:
        u = pldb.get(User, int(user_id))
        return u.username if u else "Sistema"
    finally:
        pldb.close()


def _next_number(db: Session, tenant_id: int, year: int) -> str:
    """Consecutivo REC-AAAA-NNNN por cliente y año."""
    prefix = f"REC-{year}-"
    rows = (
        db.query(TemporaryStorage.number)
        .filter(
            TemporaryStorage.tenant_id == tenant_id,
            TemporaryStorage.number.like(f"{prefix}%"),
        )
        .all()
    )
    max_seq = 0
    for (num,) in rows:
        try:
            max_seq = max(max_seq, int(str(num).rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return f"{prefix}{max_seq + 1:04d}"


def _unique_short_code(db: Session, tenant_id: int) -> str:
    for _ in range(20):
        code = "TS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = (
            db.query(TemporaryStorage.id)
            .filter(
                TemporaryStorage.tenant_id == tenant_id,
                TemporaryStorage.short_code == code,
            )
            .first()
        )
        if not exists:
            return code
    return "TS-" + datetime.utcnow().strftime("%H%M%S")


def _get_storage(db: Session, storage_id: int, tenant_id: int) -> TemporaryStorage:
    storage = (
        db.query(TemporaryStorage)
        .filter(TemporaryStorage.id == storage_id, TemporaryStorage.tenant_id == tenant_id)
        .first()
    )
    if storage is None:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    return storage


def _to_out(storage: TemporaryStorage) -> TsOut:
    out = TsOut.model_validate(storage)
    out.location_name = storage.location.name if storage.location else None
    out.days_left = storage.days_left
    out.computed_status = storage.computed_status
    out.total_units = storage.total_units
    out.items = [
        TsItemOut(
            id=it.id,
            product_id=it.product_id,
            product_name=it.product_name,
            barcode=it.barcode,
            description=it.description,
            pallets=it.pallets or 0,
            quantity=it.quantity,
            returned_qty=it.returned_qty,
            note=it.note,
            pending=it.pending,
            completed=it.completed,
        )
        for it in storage.items
    ]
    return out


def _check_exit_state(storage: TemporaryStorage) -> None:
    if storage.is_out:
        raise HTTPException(status_code=400, detail="La mercancía ya tiene una salida registrada")


def _export_response(df: pd.DataFrame, filename: str) -> StreamingResponse:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Ubicaciones temporales
# --------------------------------------------------------------------------- #
@router.get("/locations", response_model=list[TsLocationOut])
def list_locations(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    return (
        db.query(TemporaryStorageLocation)
        .filter(TemporaryStorageLocation.tenant_id == user.tenant_id)
        .order_by(TemporaryStorageLocation.name)
        .all()
    )


@router.post("/locations", response_model=TsLocationOut, status_code=201)
def create_location(
    data: TsLocationCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    name = data.name.strip()
    dup = (
        db.query(TemporaryStorageLocation)
        .filter(
            TemporaryStorageLocation.tenant_id == user.tenant_id,
            TemporaryStorageLocation.name == name,
        )
        .first()
    )
    if dup:
        raise HTTPException(status_code=400, detail=f"La ubicación '{name}' ya existe")
    loc = TemporaryStorageLocation(
        tenant_id=user.tenant_id,
        name=name,
        description=data.description,
        is_active=data.is_active,
    )
    db.add(loc)
    _record_history(
        db,
        storage_id=None,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="UBICACION_CREADA",
        detail=f"Ubicación temporal '{name}' creada",
    )
    db.commit()
    db.refresh(loc)
    return loc


@router.put("/locations/{location_id}", response_model=TsLocationOut)
def update_location(
    location_id: int,
    data: TsLocationUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    loc = (
        db.query(TemporaryStorageLocation)
        .filter(
            TemporaryStorageLocation.id == location_id,
            TemporaryStorageLocation.tenant_id == user.tenant_id,
        )
        .first()
    )
    if loc is None:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    updates = data.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"]:
        new_name = updates["name"].strip()
        dup = (
            db.query(TemporaryStorageLocation)
            .filter(
                TemporaryStorageLocation.tenant_id == user.tenant_id,
                TemporaryStorageLocation.name == new_name,
                TemporaryStorageLocation.id != location_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=400, detail=f"La ubicación '{new_name}' ya existe")
        loc.name = new_name
    for field in ("description", "is_active"):
        if field in updates:
            setattr(loc, field, updates[field])

    _record_history(
        db,
        storage_id=None,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="UBICACION_EDITADA",
        detail=f"Ubicación temporal '{loc.name}' editada",
    )
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(
    location_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    loc = (
        db.query(TemporaryStorageLocation)
        .filter(
            TemporaryStorageLocation.id == location_id,
            TemporaryStorageLocation.tenant_id == user.tenant_id,
        )
        .first()
    )
    if loc is None:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    in_use = (
        db.query(TemporaryStorage.id)
        .filter(
            TemporaryStorage.tenant_id == user.tenant_id,
            TemporaryStorage.location_id == location_id,
            TemporaryStorage.status.in_(["recibido", "almacenado"]),
        )
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar: la ubicación tiene recepciones activas",
        )

    name = loc.name
    db.delete(loc)
    _record_history(
        db,
        storage_id=None,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="UBICACION_ELIMINADA",
        detail=f"Ubicación temporal '{name}' eliminada",
    )
    db.commit()
    return None


# --------------------------------------------------------------------------- #
# Recepciones
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[TsOut])
def list_storage(
    q: str | None = Query(default=None, description="Búsqueda global"),
    status_filter: str | None = Query(default=None, alias="status"),
    party: str | None = Query(default=None, description="Filtra por nombre/empresa del tercero"),
    location_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    query = db.query(TemporaryStorage).filter(TemporaryStorage.tenant_id == user.tenant_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            TemporaryStorage.number.ilike(like)
            | TemporaryStorage.short_code.ilike(like)
            | TemporaryStorage.party_name.ilike(like)
            | TemporaryStorage.party_company.ilike(like)
            | TemporaryStorage.reference_document.ilike(like)
            | TemporaryStorage.items.any(TemporaryStorageItem.product_name.ilike(like))
            | TemporaryStorage.items.any(TemporaryStorageItem.barcode.ilike(like))
        )
    if party:
        like = f"%{party}%"
        query = query.filter(
            TemporaryStorage.party_name.ilike(like) | TemporaryStorage.party_company.ilike(like)
        )
    if location_id:
        query = query.filter(TemporaryStorage.location_id == location_id)
    if date_from:
        query = query.filter(TemporaryStorage.entry_date >= date_from)
    if date_to:
        query = query.filter(TemporaryStorage.entry_date <= date_to)

    rows = query.order_by(TemporaryStorage.id.desc()).all()

    if status_filter:
        rows = [r for r in rows if r.computed_status == status_filter]

    return [_to_out(r) for r in rows]


@router.get("/dashboard", response_model=TsDashboardOut)
def dashboard(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(TemporaryStorage)
        .filter(TemporaryStorage.tenant_id == user.tenant_id)
        .all()
    )
    active = [r for r in rows if not r.is_out]
    expiring = [r for r in active if 0 <= r.days_left <= 7]
    expired = [r for r in active if r.deadline_date < date.today()]
    month_start = date.today().replace(day=1)
    returned_this_month = [
        r
        for r in rows
        if r.is_out and r.exit_date and r.exit_date.date() >= month_start
    ]

    by_party: dict[str, int] = {}
    for r in active:
        by_party[r.party_name] = by_party.get(r.party_name, 0) + 1

    by_location: dict[str, int] = {}
    for r in active:
        key = r.location.name if r.location else "Sin ubicación"
        by_location[key] = by_location.get(key, 0) + 1

    return TsDashboardOut(
        active_receptions=len(active),
        stored_products=sum(len(r.items) for r in active),
        stored_units=sum(r.total_units for r in active),
        expiring_soon=len(expiring),
        expired=len(expired),
        returned_this_month=len(returned_this_month),
        by_party=sorted(
            [{"party": k, "count": v} for k, v in by_party.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10],
        by_location=[{"location": k, "count": v} for k, v in by_location.items()],
    )


@router.post("", response_model=TsOut, status_code=201)
def create_storage(
    data: TsCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Agrega al menos un producto")

    if data.deadline_date < (data.entry_date or date.today()):
        raise HTTPException(
            status_code=400,
            detail="La fecha límite no puede ser anterior a la fecha de entrada",
        )

    if data.location_id is not None:
        loc = (
            db.query(TemporaryStorageLocation)
            .filter(
                TemporaryStorageLocation.id == data.location_id,
                TemporaryStorageLocation.tenant_id == user.tenant_id,
            )
            .first()
        )
        if loc is None:
            raise HTTPException(status_code=404, detail="La ubicación indicada no existe")

    entry = data.entry_date or date.today()
    number = _next_number(db, user.tenant_id, entry.year)
    storage = TemporaryStorage(
        tenant_id=user.tenant_id,
        number=number,
        short_code=_unique_short_code(db, user.tenant_id),
        entry_date=entry,
        deadline_date=data.deadline_date,
        party_name=data.party_name.strip(),
        party_company=(data.party_company or "").strip() or None,
        party_phone=(data.party_phone or "").strip() or None,
        party_email=(data.party_email or "").strip() or None,
        reference_document=(data.reference_document or "").strip() or None,
        received_by=user.id,
        location_id=data.location_id,
        note=(data.note or "").strip() or None,
        status="recibido",
        created_by=user.id,
    )
    for it in data.items:
        storage.items.append(
            TemporaryStorageItem(
                tenant_id=user.tenant_id,
                product_id=it.product_id,
                product_name=it.product_name.strip(),
                barcode=(it.barcode or "").strip() or None,
                description=(it.description or "").strip() or None,
                pallets=it.pallets or 0,
                quantity=it.quantity,
                note=(it.note or "").strip() or None,
            )
        )

    db.add(storage)
    db.flush()
    total_units = sum(i.quantity for i in storage.items)
    _record_history(
        db,
        storage_id=storage.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="RECEPCION",
        detail=(
            f"Recepción {number} de {len(data.items)} producto(s) / {total_units} unidad(es) "
            f"de {storage.party_name}. Vence el {storage.deadline_date}"
        ),
    )
    db.commit()
    db.refresh(storage)
    return _to_out(storage)


@router.get("/{storage_id}", response_model=TsOut)
def get_storage(
    storage_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    return _to_out(_get_storage(db, storage_id, user.tenant_id))


@router.put("/{storage_id}", response_model=TsOut)
def update_storage(
    storage_id: int,
    data: TsUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    storage = _get_storage(db, storage_id, user.tenant_id)
    _check_exit_state(storage)

    updates = data.model_dump(exclude_unset=True)
    items_update = updates.pop("items", None)

    if "deadline_date" in updates and updates["deadline_date"] is not None:
        if updates["deadline_date"] < storage.entry_date:
            raise HTTPException(
                status_code=400,
                detail="La fecha límite no puede ser anterior a la fecha de entrada",
            )

    if "location_id" in updates and updates["location_id"] is not None:
        loc = (
            db.query(TemporaryStorageLocation)
            .filter(
                TemporaryStorageLocation.id == updates["location_id"],
                TemporaryStorageLocation.tenant_id == user.tenant_id,
            )
            .first()
        )
        if loc is None:
            raise HTTPException(status_code=404, detail="La ubicación indicada no existe")

    if items_update is not None:
        if any(it.returned_qty > 0 for it in storage.items):
            raise HTTPException(
                status_code=400,
                detail="No se pueden modificar productos: la mercancía ya tiene salidas registradas",
            )
        if not items_update:
            raise HTTPException(status_code=400, detail="La recepción debe tener al menos un producto")
        storage.items.clear()
        db.flush()
        for it in items_update:
            storage.items.append(
                TemporaryStorageItem(
                    tenant_id=user.tenant_id,
                    product_id=it["product_id"],
                    product_name=it["product_name"].strip(),
                    barcode=(it.get("barcode") or "").strip() or None,
                    description=(it.get("description") or "").strip() or None,
                    pallets=it.get("pallets") or 0,
                    quantity=it["quantity"],
                    note=(it.get("note") or "").strip() or None,
                )
            )

    changed = []
    for field in (
        "entry_date",
        "deadline_date",
        "party_name",
        "party_company",
        "party_phone",
        "party_email",
        "reference_document",
        "location_id",
        "note",
        "status",
    ):
        if field in updates and updates[field] is not None:
            setattr(storage, field, updates[field])
            changed.append(field)

    _record_history(
        db,
        storage_id=storage.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="EDICION",
        detail=(
            f"Recepción {storage.number} editada"
            + (f" (campos: {', '.join(changed)})" if changed else "")
            + (" e items actualizados" if items_update is not None else "")
        ),
    )
    db.commit()
    db.refresh(storage)
    return _to_out(storage)


@router.post("/{storage_id}/exit", response_model=TsOut)
def exit_storage(
    storage_id: int,
    data: TsExit,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Salida de la mercancía (flujo único): devuelto o retirado."""
    storage = _get_storage(db, storage_id, user.tenant_id)
    _check_exit_state(storage)

    storage.status = data.exit_type
    storage.exit_type = data.exit_type
    storage.exit_date = datetime.utcnow()
    storage.exit_responsible = (data.responsible or "").strip() or None
    storage.exit_document = (data.document or "").strip() or None
    storage.exit_note = (data.note or "").strip() or None
    storage.exit_by = user.id

    label = EXIT_TYPE_LABEL.get(data.exit_type, data.exit_type)
    _record_history(
        db,
        storage_id=storage.id,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="SALIDA",
        detail=(
            f"{label} de la recepción {storage.number} "
            f"({storage.total_units} unidad(es) de {storage.party_name})"
        ),
    )
    db.commit()
    db.refresh(storage)
    return _to_out(storage)


@router.delete("/{storage_id}", status_code=204)
def delete_storage(
    storage_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_admin),
):
    storage = _get_storage(db, storage_id, user.tenant_id)
    number = storage.number
    db.delete(storage)
    _record_history(
        db,
        storage_id=None,
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="ELIMINACION",
        detail=f"Recepción {number} eliminada",
    )
    db.commit()
    return None


# --------------------------------------------------------------------------- #
# Historial y documentos
# --------------------------------------------------------------------------- #
@router.get("/{storage_id}/history", response_model=list[TsHistoryOut])
def storage_history(
    storage_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    _get_storage(db, storage_id, user.tenant_id)
    return (
        db.query(TemporaryStorageHistory)
        .filter(
            TemporaryStorageHistory.tenant_id == user.tenant_id,
            TemporaryStorageHistory.storage_id == storage_id,
        )
        .order_by(TemporaryStorageHistory.timestamp.desc())
        .all()
    )


@router.get("/{storage_id}/ticket")
def storage_ticket(
    storage_id: int,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    storage = _get_storage(db, storage_id, user.tenant_id)
    setting = get_or_create_settings(db, user.tenant_id)
    data = {
        "number": storage.number,
        "short_code": storage.short_code,
        "entry_date": storage.entry_date.strftime("%d/%m/%Y"),
        "deadline_date": storage.deadline_date.strftime("%d/%m/%Y"),
        "party_name": storage.party_name,
        "party_company": storage.party_company,
        "party_phone": storage.party_phone,
        "party_email": storage.party_email,
        "reference_document": storage.reference_document,
        "location_name": storage.location.name if storage.location else None,
        "note": storage.note,
        "status": STATUS_LABEL.get(storage.computed_status, storage.status),
        "exit_type": storage.exit_type,
        "exit_date": storage.exit_date.strftime("%d/%m/%Y %H:%M") if storage.exit_date else None,
        "exit_responsible": storage.exit_responsible,
        "exit_document": storage.exit_document,
        "exit_note": storage.exit_note,
        "items": [
            {
                "product_name": it.product_name,
                "quantity": it.quantity,
                "returned_qty": it.returned_qty,
                "pending": it.pending,
            }
            for it in storage.items
        ],
    }
    pdf_buffer = generate_temporary_storage_pdf(
        data,
        logo_path=setting.logo_path,
        company_name=setting.company_name or "MC'CEA INVENTORY",
    )
    filename = f"Recepcion_{storage.number}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/excel")
def export_excel(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(TemporaryStorage)
        .filter(TemporaryStorage.tenant_id == user.tenant_id)
        .order_by(TemporaryStorage.id.desc())
        .all()
    )
    if status_filter:
        rows = [r for r in rows if r.computed_status == status_filter]

    data = []
    for r in rows:
        for it in r.items:
            data.append(
                {
                    "No. Recepcion": r.number,
                    "Codigo": r.short_code,
                    "Fecha Entrada": r.entry_date.strftime("%Y-%m-%d"),
                    "Fecha Limite": r.deadline_date.strftime("%Y-%m-%d"),
                    "Dias Restantes": r.days_left,
                    "Estado": STATUS_LABEL.get(r.computed_status, r.status),
                    "Tercero": r.party_name,
                    "Empresa": r.party_company or "",
                    "Telefono": r.party_phone or "",
                    "Correo": r.party_email or "",
                    "Doc. Referencia": r.reference_document or "",
                    "Ubicacion": r.location.name if r.location else "",
                    "Producto": it.product_name,
                    "Codigo Barras": it.barcode or "",
                    "Cantidad": it.quantity,
                    "Devuelto": it.returned_qty,
                    "Pendiente": it.pending,
                    "Nota": it.note or "",
                    "Tipo Salida": EXIT_TYPE_LABEL.get(r.exit_type or "", ""),
                    "Fecha Salida": r.exit_date.strftime("%Y-%m-%d %H:%M") if r.exit_date else "",
                }
            )

    columns = [
        "No. Recepcion", "Codigo", "Fecha Entrada", "Fecha Limite", "Dias Restantes",
        "Estado", "Tercero", "Empresa", "Telefono", "Correo", "Doc. Referencia",
        "Ubicacion", "Producto", "Codigo Barras", "Cantidad", "Devuelto", "Pendiente",
        "Nota", "Tipo Salida", "Fecha Salida",
    ]
    df = pd.DataFrame(data, columns=columns)
    filename = f"Recepcion_Mercancia_{date.today().strftime('%Y-%m-%d')}.xlsx"
    return _export_response(df, filename)


@router.get("/export/csv")
def export_csv(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.query(TemporaryStorage)
        .filter(TemporaryStorage.tenant_id == user.tenant_id)
        .order_by(TemporaryStorage.id.desc())
        .all()
    )
    data = []
    for r in rows:
        data.append(
            {
                "No. Recepcion": r.number,
                "Codigo": r.short_code,
                "Fecha Entrada": r.entry_date.strftime("%Y-%m-%d"),
                "Fecha Limite": r.deadline_date.strftime("%Y-%m-%d"),
                "Dias Restantes": r.days_left,
                "Estado": STATUS_LABEL.get(r.computed_status, r.status),
                "Tercero": r.party_name,
                "Empresa": r.party_company or "",
                "Telefono": r.party_phone or "",
                "Correo": r.party_email or "",
                "Doc. Referencia": r.reference_document or "",
                "Ubicacion": r.location.name if r.location else "",
                "Total Unidades": r.total_units,
                "Tipo Salida": EXIT_TYPE_LABEL.get(r.exit_type or "", ""),
                "Fecha Salida": r.exit_date.strftime("%Y-%m-%d %H:%M") if r.exit_date else "",
            }
        )
    columns = [
        "No. Recepcion", "Codigo", "Fecha Entrada", "Fecha Limite", "Dias Restantes",
        "Estado", "Tercero", "Empresa", "Telefono", "Correo", "Doc. Referencia",
        "Ubicacion", "Total Unidades", "Tipo Salida", "Fecha Salida",
    ]
    df = pd.DataFrame(data, columns=columns)
    buffer = io.BytesIO()
    buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
    buffer.seek(0)
    filename = f"Recepcion_Mercancia_{date.today().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
