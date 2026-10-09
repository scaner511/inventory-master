"""Operaciones con el stock por ubicación.

Invariante central: ``products.stock`` es SIEMPRE la suma de las cantidades de
las filas de ``product_stock_locations`` del producto. Estas funciones
garantizan ese invariante en todos los flujos (creación/edición, importación,
préstamos y devoluciones).
"""

from sqlalchemy.orm import Session

from app.models import Product, ProductStockLocation


def rows_for(session: Session, product: Product) -> list[ProductStockLocation]:
    return (
        session.query(ProductStockLocation)
        .filter_by(product_id=product.id, tenant_id=product.tenant_id)
        .order_by(ProductStockLocation.id)
        .all()
    )


def to_dict_list(session: Session, product: Product) -> list[dict]:
    return [
        {"location": r.location, "quantity": r.quantity} for r in rows_for(session, product)
    ]


def ensure_seed(session: Session, product: Product) -> None:
    """Si el producto no tiene filas de ubicación, crea una con su stock total.

    Aplica a productos creados ANTES de la función o importados sin ubicaciones.
    """
    if rows_for(session, product):
        return
    name = (product.location1 or "").strip() or "Principal"
    session.add(
        ProductStockLocation(
            tenant_id=product.tenant_id,
            product_id=product.id,
            location=name,
            quantity=product.stock or 0,
        )
    )


def reconcile_stock(session: Session, product: Product) -> None:
    """Ajusta la primera fila para que la suma coincida con products.stock."""
    # La sesión usa autoflush=False: un ensure_seed previo (o una creación con
    # flush pendiente) puede tener filas sin vaciar. Si no las materializamos en
    # cascada, una consulta posterior no las vería y se intentaría crear otra
    # fila idéntica (violaría la unicidad product+location).
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


def set_locations(session: Session, product: Product, locations: list[dict]) -> int:
    """Reemplaza las filas por las dadas y recalcula products.stock = suma.

    Devuelve el stock total resultante.
    """
    session.query(ProductStockLocation).filter_by(
        product_id=product.id, tenant_id=product.tenant_id
    ).delete(synchronize_session=False)

    total = 0
    first_name = ""
    for loc in locations:
        name = (loc.get("location") or "").strip()
        qty = int(loc.get("quantity") or 0)
        # Se conservan las filas con cantidad 0 (p. ej. una ubicación agotada):
        # eliminarlas aquí borraba ubicaciones al editar un producto.
        if not name:
            continue
        if not first_name:
            first_name = name
        total += qty
        session.add(
            ProductStockLocation(
                tenant_id=product.tenant_id,
                product_id=product.id,
                location=name,
                quantity=qty,
            )
        )
    product.stock = total
    if first_name and product.location1 != first_name:
        product.location1 = first_name
    return total


def adjust_quantity(session: Session, product: Product, location: str, delta: int) -> None:
    """Suma (delta>0) o resta (delta<0) unidades a una ubicación concreta.

    Crea la fila si no existe y el delta es positivo. Nunca deja negativos.
    NO toca products.stock: el llamador es responsable de actualizarlo.
    """
    if not location:
        return
    row = (
        session.query(ProductStockLocation)
        .filter_by(product_id=product.id, tenant_id=product.tenant_id, location=location)
        .first()
    )
    if row is None:
        if delta < 0:
            return
        row = ProductStockLocation(
            tenant_id=product.tenant_id, product_id=product.id, location=location, quantity=0
        )
        session.add(row)
    row.quantity = max(row.quantity + delta, 0)


def subtract_from(session: Session, product: Product, location: str, qty: int) -> None:
    """Resta qty de la ubicación indicada. Si la fila no existe o tiene menos,
    lanza ValueError (la validación previa ya debería haberlo impedido)."""
    row = (
        session.query(ProductStockLocation)
        .filter_by(product_id=product.id, tenant_id=product.tenant_id, location=location)
        .first()
    )
    if row is None:
        raise ValueError(f"El producto no tiene stock registrado en la ubicación '{location}'")
    if row.quantity < qty:
        raise ValueError(
            f"Solo hay {row.quantity} unidades de '{product.name}' en '{location}'"
        )
    row.quantity -= qty