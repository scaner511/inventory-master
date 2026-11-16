"""Operaciones con el stock por almacén (slots globales del sistema).

El sistema tiene exactamente 3 almacenes globales por cliente (configurables en
settings: warehouse1_name, warehouse2_name, warehouse3_name). Cada producto
tiene una fila en ``product_stock_locations`` por cada almacén (slot 1/2/3).

Invariante central: ``products.stock`` es SIEMPRE la suma de las cantidades de
las 3 filas de ubicación del producto.
"""
from sqlalchemy.orm import Session

from app.deps import get_or_create_settings
from app.models import Product, ProductStockLocation


SLOT_COUNT = 3


def slot_names(db: Session) -> list[str]:
    """Devuelve los 3 nombres de almacenes del cliente (con defaults)."""
    setting = get_or_create_settings(db)
    names = [
        (setting.warehouse1_name or "").strip() or "Almacén Principal",
        (setting.warehouse2_name or "").strip() or "Vehículo",
        (setting.warehouse3_name or "").strip() or "Almacén Secundario",
    ]
    return names


def rows_for(session: Session, product: Product) -> list[ProductStockLocation]:
    return (
        session.query(ProductStockLocation)
        .filter_by(product_id=product.id, tenant_id=product.tenant_id)
        .order_by(ProductStockLocation.id)
        .all()
    )


def sync_location_names(session: Session, product: Product) -> None:
    """Renombra las filas de ubicación si el admin cambió los nombres de los
    almacenes. Mantiene las cantidades. Crea las que falten."""
    names = slot_names(session)
    rows = rows_for(session, product)
    # Indexar filas existentes por posición (orden de creación).
    # Si hay menos de 3 filas, completar.
    # Estrategia: emparejar por posición ordinal.
    for i, name in enumerate(names):
        if i < len(rows):
            if rows[i].location != name:
                rows[i].location = name
        else:
            session.add(
                ProductStockLocation(
                    tenant_id=product.tenant_id,
                    product_id=product.id,
                    location=name,
                    quantity=0,
                )
            )
    session.flush()


def ensure_seed(session: Session, product: Product) -> None:
    """Garantiza que el producto tenga las 3 filas de almacén.

    - Si no tiene ninguna: crea las 3 con el stock total en el slot 1.
    - Si tiene menos de 3: completa hasta 3 con cantidad 0.
    - Si tiene más (legacy): no borra, pero se sincronizan los nombres.
    """
    session.flush()
    rows = rows_for(session, product)
    if not rows:
        names = slot_names(session)
        session.add(
            ProductStockLocation(
                tenant_id=product.tenant_id,
                product_id=product.id,
                location=names[0],
                quantity=product.stock or 0,
            )
        )
        for name in names[1:]:
            session.add(
                ProductStockLocation(
                    tenant_id=product.tenant_id,
                    product_id=product.id,
                    location=name,
                    quantity=0,
                )
            )
        session.flush()
        return
    # Completar si faltan slots.
    names = slot_names(session)
    if len(rows) < SLOT_COUNT:
        for i in range(len(rows), SLOT_COUNT):
            session.add(
                ProductStockLocation(
                    tenant_id=product.tenant_id,
                    product_id=product.id,
                    location=names[i],
                    quantity=0,
                )
            )
        session.flush()
    # Sincronizar nombres (por si el admin renombró).
    rows = rows_for(session, product)
    for i, name in enumerate(names):
        if i < len(rows) and rows[i].location != name:
            rows[i].location = name
    session.flush()


def reconcile_stock(session: Session, product: Product) -> None:
    """Ajusta la primera fila para que la suma coincida con products.stock."""
    session.flush()
    rows = rows_for(session, product)
    if not rows:
        ensure_seed(session, product)
        session.flush()
        rows = rows_for(session, product)
        if not rows:
            return
    total = sum(r.quantity for r in rows)
    if total != product.stock:
        rows[0].quantity = max(rows[0].quantity + (product.stock - total), 0)


def slot_quantities(session: Session, product: Product) -> list[int]:
    """Devuelve [q1, q2, q3] para el producto (rellena con 0 si faltan)."""
    ensure_seed(session, product)
    rows = rows_for(session, product)
    out = [0, 0, 0]
    for i in range(min(len(rows), SLOT_COUNT)):
        out[i] = rows[i].quantity or 0
    return out


def set_slot_quantities(session: Session, product: Product, quantities: list[int]) -> int:
    """Asigna las cantidades a los 3 slots y recalcula products.stock = suma.

    Devuelve el stock total resultante.
    """
    names = slot_names(session)
    ensure_seed(session, product)
    rows = rows_for(session, product)
    total = 0
    for i in range(SLOT_COUNT):
        q = int(quantities[i] if i < len(quantities) else 0)
        if q < 0:
            q = 0
        if i < len(rows):
            rows[i].location = names[i]
            rows[i].quantity = q
        else:
            session.add(
                ProductStockLocation(
                    tenant_id=product.tenant_id,
                    product_id=product.id,
                    location=names[i],
                    quantity=q,
                )
            )
        total += q
    product.stock = total
    if rows and rows[0].location:
        product.location1 = rows[0].location
    return total


def adjust_quantity(session: Session, product: Product, slot: int, delta: int) -> None:
    """Suma (delta>0) o resta (delta<0) unidades a un slot (1/2/3)."""
    if slot < 1 or slot > SLOT_COUNT:
        return
    ensure_seed(session, product)
    rows = rows_for(session, product)
    if slot - 1 >= len(rows):
        return
    row = rows[slot - 1]
    row.quantity = max((row.quantity or 0) + delta, 0)


def slot_index_for_name(session: Session, name: str | None) -> int | None:
    """Devuelve el slot (1-3) que corresponde al nombre de un almacén.

    Comparación case-insensitive. Devuelve None si no coincide con
    ninguno de los 3 almacenes globales del cliente.
    """
    if not name:
        return None
    target = name.strip().lower()
    for i, n in enumerate(slot_names(session)):
        if n.strip().lower() == target:
            return i + 1
    return None


def set_locations(session: Session, product: Product, locations: list[dict]) -> int:
    """Reemplaza la distribución por almacenes y recalcula products.stock.

    Los nombres de ubicación se mapean a los 3 slots globales por nombre
    (case-insensitive). Las ubicaciones que no coinciden con ningún almacén
    registrado se acumulan en el primer slot para no perder stock.
    Devuelve el stock total resultante.
    """
    ensure_seed(session, product)
    names = [n.strip().lower() for n in slot_names(session)]
    slot_qty = [0, 0, 0]
    first_name = ""
    for loc in locations:
        name = (loc.get("location") or "").strip()
        qty = int(loc.get("quantity") or 0)
        if not name:
            continue
        if not first_name:
            first_name = name
        folded = name.lower()
        idx = names.index(folded) if folded in names else 0
        slot_qty[idx] += qty
    set_slot_quantities(session, product, slot_qty)
    if first_name and product.location1 != first_name:
        product.location1 = first_name
    return product.stock or 0


def subtract_from_slot(session: Session, product: Product, slot: int, qty: int) -> None:
    rows = rows_for(session, product)
    if slot - 1 >= len(rows):
        raise ValueError("Slot inválido")
    row = rows[slot - 1]
    if (row.quantity or 0) < qty:
        raise ValueError(
            f"Solo hay {row.quantity} unidades de '{product.name}' en el almacén origen"
        )
    row.quantity -= qty


def to_dict_list(session: Session, product: Product) -> list[dict]:
    names = slot_names(session)
    qs = slot_quantities(session, product)
    return [{"location": names[i], "quantity": qs[i]} for i in range(SLOT_COUNT)]