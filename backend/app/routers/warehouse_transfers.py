"""Transferencias de stock entre almacenes globales del sistema."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_tenant_db, require_privileged
from app.models import Product, User, WarehouseTransfer, WarehouseTransferItem
from app.utils.audit import record_audit
from app.utils.locations import (
    SLOT_COUNT,
    ensure_seed,
    slot_names,
    subtract_from_slot,
)

router = APIRouter(prefix="/api/warehouse-transfers", tags=["warehouse-transfers"])


class TransferItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)


class TransferIn(BaseModel):
    from_slot: int = Field(ge=1, le=SLOT_COUNT)
    to_slot: int = Field(ge=1, le=SLOT_COUNT)
    note: str | None = None
    items: list[TransferItemIn]


class TransferItemOut(BaseModel):
    id: int
    product_id: int | None = None
    product_name: str
    product_code: str | None = None
    quantity: int


class TransferOut(BaseModel):
    id: int
    from_slot: int
    to_slot: int
    from_name: str
    to_name: str
    transfer_date: datetime
    note: str | None = None
    created_by: int | None = None
    items: list[TransferItemOut] = []


@router.post("", response_model=TransferOut)
def create_transfer(
    data: TransferIn,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(require_privileged),
):
    if data.from_slot == data.to_slot:
        raise HTTPException(status_code=400, detail="El almacén de origen y destino no pueden ser el mismo")
    if not data.items:
        raise HTTPException(status_code=400, detail="Debe incluir al menos un producto")

    names = slot_names(db)
    from_name = names[data.from_slot - 1]
    to_name = names[data.to_slot - 1]

    # Validar todos los items primero.
    products = []
    for it in data.items:
        p = db.query(Product).filter(Product.id == it.product_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail=f"Producto {it.product_id} no encontrado")
        ensure_seed(db, p)
        # Verificar stock disponible en origen.
        from app.utils.locations import rows_for

        rows = rows_for(db, p)
        if data.from_slot - 1 >= len(rows):
            raise HTTPException(status_code=400, detail=f"Slot inválido para {p.name}")
        avail = rows[data.from_slot - 1].quantity or 0
        if it.quantity > avail:
            raise HTTPException(
                status_code=400,
                detail=f"Solo hay {avail} unidades de '{p.name}' en {from_name}",
            )
        products.append((p, it.quantity))

    # Crear cabecera.
    transfer = WarehouseTransfer(
        tenant_id=user.tenant_id,
        from_slot=data.from_slot,
        to_slot=data.to_slot,
        from_name=from_name,
        to_name=to_name,
        created_by=user.id,
        note=data.note,
    )
    db.add(transfer)
    db.flush()

    for p, qty in products:
        item = WarehouseTransferItem(
            transfer_id=transfer.id,
            product_id=p.id,
            product_name=p.name,
            product_code=p.code,
            quantity=qty,
        )
        db.add(item)
        # Mover stock.
        subtract_from_slot(db, p, data.from_slot, qty)
        # Sumar en destino.
        from app.utils.locations import adjust_quantity

        adjust_quantity(db, p, data.to_slot, qty)
        # products.stock no cambia (suma constante), pero sincronizamos.
        from app.utils.locations import reconcile_stock

        reconcile_stock(db, p)
        record_audit(
            db,
            action="TRANSFERENCIA_ALMACEN",
            user_id=user.id,
            detail=f"Transferencia de {qty} u. de '{p.name}' ({p.code}) de '{from_name}' a '{to_name}'",
            product_name=p.name,
            quantity=qty,
            tenant_id=user.tenant_id,
        )

    db.commit()
    db.refresh(transfer)
    return _to_out(transfer)


def _to_out(t: WarehouseTransfer) -> TransferOut:
    return TransferOut(
        id=t.id,
        from_slot=t.from_slot,
        to_slot=t.to_slot,
        from_name=t.from_name,
        to_name=t.to_name,
        transfer_date=t.transfer_date,
        note=t.note,
        created_by=t.created_by,
        items=[
            TransferItemOut(
                id=i.id,
                product_id=i.product_id,
                product_name=i.product_name,
                product_code=i.product_code,
                quantity=i.quantity,
            )
            for i in t.items
        ],
    )


@router.get("", response_model=list[TransferOut])
def list_transfers(
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
):
    rows = (
        db.query(WarehouseTransfer)
        .order_by(WarehouseTransfer.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_out(t) for t in rows]