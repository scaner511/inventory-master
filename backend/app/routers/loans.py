"""Rutas de préstamos: registro, devolución, prórroga y consulta."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Loan, Product, User
from app.schemas import LoanCreate, LoanOut, LoanReturn, LoanUpdate
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
    """True si el vendedor tiene mercancía vencida y sin devolver."""
    today = date.today()
    return (
        db.query(Loan)
        .filter(
            Loan.seller == seller,
            Loan.tenant_id == tenant_id,
            Loan.quantity > Loan.returned_qty,
            Loan.due_date < today,
        )
        .count()
        > 0
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Loan).filter(Loan.tenant_id == user.tenant_id)
    if q:
        like = f"%{q}%"
        query = query.filter(Loan.seller.ilike(like) | Loan.product_name.ilike(like))

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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = _get_product(db, data.product_id, user.tenant_id)
    if not product:
        raise HTTPException(status_code=404, detail="El código de producto no existe")

    if product.stock < data.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Stock insuficiente. Solo hay {product.stock} unidades de '{product.name}'.",
        )

    if _seller_blocked(db, data.seller, user.tenant_id):
        raise HTTPException(
            status_code=400,
            detail=f"El vendedor {data.seller} tiene mercancía VENCIDA sin devolver. No se pueden realizar préstamos.",
        )

    # Descontar stock
    product.stock -= data.quantity

    loan = Loan(
        seller=data.seller,
        phone=data.phone,
        tenant_id=user.tenant_id,
        product_id=product.id,
        product_name=product.name,
        quantity=data.quantity,
        due_date=data.due_date,
        note=data.note,
        created_by=user.id,
    )
    db.add(loan)
    record_audit(
        db,
        action="PRESTAMO",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Préstamo de {data.quantity} unidades a {data.seller}",
        product_name=product.name,
        quantity=data.quantity,
    )
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.put("/{loan_id}", response_model=LoanOut)
def update_loan(
    loan_id: int,
    data: LoanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Edita los datos de un préstamo (vendedor, teléfono, producto, cantidad, fecha o nota).

    Si cambia el producto o la cantidad, el stock se ajusta automáticamente.
    Solo se permite cambiar producto/cantidad cuando aún no hay devoluciones.
    """
    loan = _get_loan(db, loan_id, user.tenant_id)

    updates = data.model_dump(exclude_unset=True)

    if "product_id" in updates or "quantity" in updates:
        if loan.returned_qty > 0:
            raise HTTPException(
                status_code=400,
                detail="No se puede cambiar el producto o la cantidad porque el préstamo ya tiene devoluciones",
            )

    new_product_id = updates.get("product_id", loan.product_id)
    new_quantity = updates.get("quantity", loan.quantity)

    old_product = _get_product(db, loan.product_id, user.tenant_id) if loan.product_id else None
    new_product = _get_product(db, new_product_id, user.tenant_id) if new_product_id is not None else None
    if new_product_id is not None and new_product is None:
        raise HTTPException(status_code=404, detail="El producto seleccionado no existe")

    if "seller" in updates and updates["seller"] != loan.seller:
        if _seller_blocked(db, updates["seller"], user.tenant_id):
            raise HTTPException(
                status_code=400,
                detail=f"El vendedor {updates['seller']} tiene mercancía VENCIDA sin devolver.",
            )

    # Ajuste de stock
    if new_product_id == loan.product_id and old_product:
        delta = new_quantity - loan.quantity
        if delta > 0 and old_product.stock < delta:
            raise HTTPException(
                status_code=400,
                detail=f"Stock insuficiente de '{old_product.name}'. Solo hay {old_product.stock} unidades.",
            )
        old_product.stock -= delta
    elif new_product_id != loan.product_id:
        if old_product:
            old_product.stock += loan.quantity
        if new_product is not None:
            if new_product.stock < new_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente de '{new_product.name}'. Solo hay {new_product.stock} unidades.",
                )
            new_product.stock -= new_quantity

    for field in ("seller", "phone", "due_date", "note"):
        if field in updates:
            setattr(loan, field, updates[field])
    if new_product is not None:
        loan.product_name = new_product.name
    if "product_id" in updates:
        loan.product_id = new_product_id
    if "quantity" in updates:
        loan.quantity = new_quantity

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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    loan = _get_loan(db, loan_id, user.tenant_id)

    if loan.completed:
        raise HTTPException(status_code=400, detail="Este préstamo ya está completamente devuelto")

    new_total = loan.returned_qty + data.returned_qty
    if new_total > loan.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"No se pueden devolver {data.returned_qty} unidades. Pendiente por devolver: {loan.pending}.",
        )

    loan.returned_qty = new_total

    # Devolver mercancía al stock
    product = _get_product(db, loan.product_id, user.tenant_id)
    if product:
        product.stock += data.returned_qty

    record_audit(
        db,
        action="DEVOLUCION",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Devolución de {data.returned_qty} unidades de {loan.product_name}",
        product_name=loan.product_name,
        quantity=data.returned_qty,
    )
    db.commit()
    db.refresh(loan)
    return _to_out(loan)


@router.post("/{loan_id}/extend", response_model=LoanOut)
def extend_loan(
    loan_id: int,
    days: int = Query(ge=1, le=365),
    db: Session = Depends(get_db),
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
