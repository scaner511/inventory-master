"""Rutas de préstamos: registro, devolución, prórroga y consulta."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_tenant_db
from app.models import Loan, LoanItem, Product, User
from app.schemas import LoanCreate, LoanOut, LoanReturn, LoanUpdate
from app.utils import locations as loc_utils
from app.utils.audit import record_audit

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _to_out(loan: Loan) -> LoanOut:
    out = LoanOut.model_validate(loan)
    if loan.completed:
        out.status = "COMPLETADO"
    elif loan.overdue:
        out.status = "VENCIDO"
    elif loan.due_date == date.today():
        out.status = "VENCE_HOY"
    else:
        out.status = "ACTIVO"
    return out


def _seller_blocked(db: Session, seller: str, tenant_id: int) -> bool:
    """True si el vendedor tiene mercancía vencida y sin devolver (cualquier ítem)."""
    today = date.today()
    return (
        db.query(Loan.id)
        .join(LoanItem)
        .filter(
            Loan.seller == seller,
            Loan.tenant_id == tenant_id,
            LoanItem.quantity > LoanItem.returned_qty,
            Loan.due_date < today,
        )
        .first()
        is not None
    )


def _get_loan(db: Session, loan_id: int, tenant_id: int) -> Loan:
    loan = (
        db.query(Loan)
        .filter(Loan.id == loan_id, Loan.tenant_id == tenant_id)
        .first()
    )
    if loan is None:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    return loan


def _get_product(db: Session, product_id: int, tenant_id: int) -> Product | None:
    return (
        db.query(Product)
        .filter(Product.id == product_id, Product.tenant_id == tenant_id)
        .first()
    )


@router.get("", response_model=list[LoanOut])
def list_loans(
    q: str | None = Query(default=None, description="Filtro por vendedor o producto"),
    status_filter: str | None = Query(default=None, alias="status"),
    date_filter: date | None = Query(default=None, alias="date", description="Filtro por fecha del préstamo (YYYY-MM-DD)"),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Loan).filter(Loan.tenant_id == user.tenant_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            Loan.seller.ilike(like) | Loan.items.any(LoanItem.product_name.ilike(like))
        )
    if date_filter:
        query = query.filter(Loan.loan_date >= date_filter, Loan.loan_date < date_filter + timedelta(days=1))

    loans = query.order_by(Loan.id.desc()).all()

    if status_filter:
        filtered = []
        for loan in loans:
            out = _to_out(loan)
            if out.status == status_filter:
                filtered.append(loan)
        loans = filtered

    return [_to_out(l) for l in loans]


@router.post("", response_model=LoanOut, status_code=201)
def create_loan(
    data: LoanCreate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    if _seller_blocked(db, data.seller, user.tenant_id):
        raise HTTPException(
            status_code=400,
            detail=f"El vendedor {data.seller} tiene mercancía VENCIDA sin devolver. No se pueden realizar préstamos.",
        )

    if not data.items:
        raise HTTPException(status_code=400, detail="Indica al menos un producto")

    # Validar TODO antes de tocar stock: si algo falla, no se descuenta nada.
    validated = []
    for item in data.items:
        product = _get_product(db, item.product_id, user.tenant_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"El producto con id {item.product_id} no existe")

        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente. Solo hay {product.stock} unidades de '{product.name}'.",
            )

        # Ubicación de salida: si el producto tiene ubicaciones y se indicó una,
        # se descuenta de esa fila concreta.
        location_out = (item.location_out or "").strip() or None
        if location_out:
            rows = loc_utils.rows_for(db, product)
            if rows:
                try:
                    loc_utils.subtract_from(db, product, location_out, item.quantity)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc))
            # Sin filas registradas: se acepta la ubicación indicada para historial,
            # pero no hay stock por ubicación que descontar.

        product.stock -= item.quantity
        validated.append((product, item.quantity, location_out))

    total_qty = sum(v[1] for v in validated)
    loan = Loan(
        seller=data.seller,
        phone=data.phone,
        tenant_id=user.tenant_id,
        due_date=data.due_date,
        note=data.note,
        created_by=user.id,
    )
    db.add(loan)

    for product, qty, location_out in validated:
        loan.items.append(
            LoanItem(
                product_id=product.id,
                product_name=product.name,
                quantity=qty,
                location_out=location_out,
            )
        )

    # Instantánea legacy (primer ítem + total) por compatibilidad.
    first = validated[0]
    loan.product_id = first[0].id
    loan.product_name = first[0].name
    loan.quantity = total_qty
    loan.location_out = first[2]

    def _plural(items, qty):
        return (
            f"{len(items)} productos ({qty} unidades)"
            if len(items) > 1
            else f"1 producto ({qty} unidades)"
        )

    record_audit(
        db,
        action="PRESTAMO",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Préstamo de {_plural(data.items, total_qty)} a {data.seller}",
        product_name=first[0].name,
        quantity=total_qty,
    )
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.put("/{loan_id}", response_model=LoanOut)
def update_loan(
    loan_id: int,
    data: LoanUpdate,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    """Edita un préstamo (cabecera y/o lista de ítems).

    Si cambian los ítems, el stock y las ubicaciones se ajustan automáticamente.
    Solo se permite cambiar productos/cantidades cuando aún no hay devoluciones.
    """
    loan = _get_loan(db, loan_id, user.tenant_id)

    updates = data.model_dump(exclude_unset=True)
    items_update: list[dict] | None = updates.pop("items", None)

    if items_update is not None:
        if any(item.returned_qty > 0 for item in loan.items):
            # Con devoluciones ya registradas NO se toca stock ni productos:
            # solo se admite cambiar la ubicación de salida de los ítems actuales.
            current = {item.id: item for item in loan.items}
            for spec in items_update:
                item_id = spec.get("id")
                item = current.get(item_id)
                if item is None:
                    raise HTTPException(
                        status_code=400,
                        detail="No se puede agregar ni quitar productos porque el préstamo ya tiene devoluciones",
                    )
                if spec["product_id"] != item.product_id or spec["quantity"] != item.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail="No se puede cambiar el producto o la cantidad porque el préstamo ya tiene devoluciones",
                    )
            for spec in items_update:
                item = current[spec["id"]]
                item.location_out = (spec.get("location_out") or "").strip() or None
            db.flush()
        else:
            if not items_update:
                raise HTTPException(status_code=400, detail="El préstamo debe tener al menos un producto")

            # Devolver al stock lo que estaba prestado (equivalente a anular)...
            for item in list(loan.items):
                product = _get_product(db, item.product_id, user.tenant_id)
                if product:
                    product.stock += item.quantity
                    if item.location_out and loc_utils.rows_for(db, product):
                        loc_utils.adjust_quantity(db, product, item.location_out, item.quantity)
            loan.items.clear()
            db.flush()

            # ...y prestar de nuevo la lista corregida.
            for spec in items_update:
                product = _get_product(db, spec["product_id"], user.tenant_id)
                if not product:
                    raise HTTPException(status_code=404, detail=f"El producto con id {spec['product_id']} no existe")

                qty = spec["quantity"]
                if product.stock < qty:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Stock insuficiente. Solo hay {product.stock} unidades de '{product.name}'.",
                    )

                location_out = (spec.get("location_out") or "").strip() or None
                if location_out:
                    rows = loc_utils.rows_for(db, product)
                    if rows:
                        try:
                            loc_utils.subtract_from(db, product, location_out, qty)
                        except ValueError as exc:
                            raise HTTPException(status_code=400, detail=str(exc))

                product.stock -= qty
                loan.items.append(
                    LoanItem(
                        product_id=product.id,
                        product_name=product.name,
                        quantity=qty,
                        location_out=location_out,
                    )
                )

    old_seller = loan.seller
    for field in ("seller", "phone", "due_date", "note"):
        if field in updates:
            setattr(loan, field, updates[field])

    if "seller" in updates and updates["seller"] != old_seller:
        if _seller_blocked(db, updates["seller"], user.tenant_id):
            raise HTTPException(
                status_code=400,
                detail=f"El vendedor {updates['seller']} tiene mercancía VENCIDA sin devolver.",
            )

    # Mantener la instantánea legacy consistente con los ítems.
    db.flush()
    if loan.items:
        loan.product_id = loan.items[0].product_id
        loan.product_name = loan.items[0].product_name
        loan.quantity = sum(item.quantity for item in loan.items)
        loan.returned_qty = sum(item.returned_qty for item in loan.items)
        loan.location_out = loan.items[0].location_out

    record_audit(
        db,
        action="EDICION",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Préstamo #{loan.id} editado",
        product_name=loan.product_name,
    )
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.post("/{loan_id}/return", response_model=LoanOut)
def return_loan(
    loan_id: int,
    data: LoanReturn,
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    loan = _get_loan(db, loan_id, user.tenant_id)

    item = next((i for i in loan.items if i.id == data.item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Ítem del préstamo no encontrado")

    if item.completed:
        raise HTTPException(status_code=400, detail="Este ítem ya está completamente devuelto")

    new_total = item.returned_qty + data.returned_qty
    if new_total > item.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"No se pueden devolver {data.returned_qty} unidades de '{item.product_name}'. Pendiente por devolver: {item.pending}.",
        )

    item.returned_qty = new_total

    # Devolver mercancía al stock: a la ubicación elegida (o la de salida).
    product = _get_product(db, item.product_id, user.tenant_id)
    if product:
        product.stock += data.returned_qty
        dest = (data.location_in or "").strip() or item.location_out or None
        if dest and loc_utils.rows_for(db, product):
            loc_utils.adjust_quantity(db, product, dest, data.returned_qty)
        elif dest and not loc_utils.rows_for(db, product):
            # Producto sin desglose: conservar la ubicación en el préstamo
            # para referencia (el stock total ya se actualizó arriba).
            pass

    # Sincronizar la instantánea legacy del préstamo.
    loan.returned_qty = sum(i.returned_qty for i in loan.items)

    record_audit(
        db,
        action="DEVOLUCION",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Devolución de {data.returned_qty} unidades de {item.product_name}"
               + (f" a '{dest}'" if dest else ""),
        product_name=item.product_name,
        quantity=data.returned_qty,
    )
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.post("/{loan_id}/extend", response_model=LoanOut)
def extend_loan(
    loan_id: int,
    days: int = Query(ge=1, le=365),
    db: Session = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
):
    loan = _get_loan(db, loan_id, user.tenant_id)

    if loan.completed:
        raise HTTPException(status_code=400, detail="No se puede prorrogar un préstamo completado")

    loan.due_date = loan.due_date + timedelta(days=days)
    record_audit(
        db,
        action="PRORROGA",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Prórroga de {days} días al préstamo #{loan.id}",
        product_name=loan.product_name,
    )
    db.commit()
    db.refresh(loan)
    return _to_out(loan)
