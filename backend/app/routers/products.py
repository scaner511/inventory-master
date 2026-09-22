"""Rutas CRUD de productos (inventario)."""
import io
import unicodedata

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import Product, ProductStockLocation, User
from app.schemas import ProductCreate, ProductOut, ProductUpdate
from app.utils import locations as loc_utils

router = APIRouter(prefix="/api/products", tags=["products"])


def _fold(text: str | None) -> str:
    """Minúsculas y sin acentos para búsquedas tolerantes."""
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def _matches_terms(values: list[str], terms: list[str]) -> bool:
    """True si cada término está presente en al menos uno de los valores.

    Permite buscar por nombre sin importar el orden de las palabras:
    "tapa presion" encuentra "TAPA OLLA DE PRESION" aunque falte "olla".
    """
    folded = [_fold(v) for v in values]
    return all(any(t in f for f in folded) for t in terms)


def _get_threshold(db: Session, tenant_id: int | None = None) -> int:
    from app.deps import get_or_create_settings

    return get_or_create_settings(db, tenant_id).low_stock_threshold or 5


def _to_out(db: Session, p: Product, threshold: int) -> ProductOut:
    out = ProductOut.model_validate(p)
    if p.stock <= 0:
        out.status = "NO_DISPONIBLE"
    elif p.stock <= threshold:
        out.status = "STOCK_BAJO"
    else:
        out.status = "DISPONIBLE"
    rows = loc_utils.rows_for(db, p)
    if rows:
        out.locations = [{"location": r.location, "quantity": r.quantity} for r in rows]
        out.location = " | ".join(f"{r.location} = {r.quantity}" for r in rows)
    else:
        # Datos antiguos sin desglose: se muestran las columnas legacy
        out.location = " | ".join(l for l in (p.location1, p.location2, p.location3) if l and l.strip()) or "Sin asignar"
    return out


@router.get("", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(default=None, description="Filtro por código o nombre"),
    low_stock_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    threshold = _get_threshold(db, user.tenant_id)
    query = db.query(Product).filter(Product.tenant_id == user.tenant_id)

    terms: list[str] = []
    if q:
        terms = [t for t in _fold(q).split() if t]

    products = query.order_by(Product.name).all()
    if terms:
        products = [p for p in products if _matches_terms([p.name, p.code], terms)]
    if low_stock_only:
        products = [p for p in products if p.stock <= threshold]
    return [_to_out(db, p, threshold) for p in products]


def _normalize_header(h) -> str:
    """Minúsculas, sin acentos y sin espacios para comparar cabeceras."""
    import unicodedata

    h = str(h).lower()
    h = "".join(c for c in unicodedata.normalize("NFD", h) if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in h if ch.isalnum())


HEADER_ALIASES = {
    # código
    "codigo": "code", "code": "code", "id": "code", "sku": "code",
    "clave": "code", "referencia": "code",
    # nombre
    "nombre": "name", "name": "name", "producto": "name", "articulo": "name",
    "descripcion": "name", "descripciondelproducto": "name",
    # stock
    "stock": "stock", "cantidad": "stock", "existencia": "stock",
    "existencias": "stock", "unidades": "stock", "cant": "stock",
    # precio de compra
    "compra": "compra", "preciocompra": "compra", "preciodecompra": "compra",
    "costocompra": "compra", "costo": "compra", "costounitario": "compra",
    # precio de venta
    "venta": "venta", "precioventa": "venta", "preciodeventa": "venta",
    "preciopublico": "venta", "precio": "venta",
    # ubicaciones
    "ubicacion1": "ubicacion1", "ubicacion": "ubicacion1",
    "ubicacionprincipal": "ubicacion1", "ubicacion2": "ubicacion2",
    "ubicacion3": "ubicacion3",
}

POSITIONAL_FIELDS = ["code", "name", "stock", "compra", "venta", "ubicacion1", "ubicacion2", "ubicacion3"]


def _map_columns(df):
    """Resuelve qué columna corresponde a cada campo.

    1) Por cabecera (acepta variantes: "Código", "Precio de Compra", ...).
    2) Por posición si no se reconocen las cabeceras (0=código, 1=nombre,
       2=stock, ...), igual que hacía la versión de escritorio.
    """
    mapping = {}
    for i, col in enumerate(df.columns):
        field = HEADER_ALIASES.get(_normalize_header(col))
        if field and field not in mapping:
            mapping[field] = i

    if {"code", "name", "stock"}.issubset(mapping):
        return mapping

    if df.shape[1] >= 3:
        return {POSITIONAL_FIELDS[i]: i for i in range(min(len(POSITIONAL_FIELDS), df.shape[1]))}

    raise HTTPException(
        status_code=400,
        detail="El archivo debe tener columnas: codigo, nombre, stock "
               "(y opcionalmente compra, venta, ubicacion1, ubicacion2, ubicacion3). "
               "Si tu archivo no tiene encabezados, el orden debe ser: "
               "codigo, nombre, stock, compra, venta, ubicacion1, ubicacion2, ubicacion3.",
    )


def _val(row, mapping, field, default=""):
    idx = mapping.get(field)
    if idx is None:
        return default
    value = row.iloc[idx]
    return default if pd.isna(value) else value


@router.post("/import", status_code=201)
def import_products(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Carga masiva de productos desde CSV o Excel.

    Acepta columnas con cualquier nombre reconocible (Código, Codigo, Nombre,
    Stock, Cantidad, Precio de Compra, Venta, Ubicación 1...). Si no se
    reconocen los encabezados, se mapean por posición:
    codigo, nombre, stock, compra, venta, ubicacion1, ubicacion2, ubicacion3.
    """
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ("csv", "xlsx", "xls"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos .csv, .xlsx o .xls")

    content = file.file.read()
    try:
        if ext == "csv":
            df = None
            for sep in (";", ","):
                try:
                    df = pd.read_csv(io.BytesIO(content), sep=sep, decimal=",", encoding="latin-1")
                    if len(df.columns) >= 2:
                        break
                except Exception:
                    continue
            if df is None or len(df.columns) < 2:
                raise HTTPException(status_code=400, detail="No se pudo leer el archivo CSV (se probaron ';' y ',').")
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {e}")

    # Si la primera fila no parece una cabecera reconocible, asumimos que el
    # archivo no tiene encabezados y re-leemos con header=None (mapeo por posición).
    if not any(_normalize_header(c) in HEADER_ALIASES for c in df.columns):
        try:
            if ext == "csv":
                df = None
                for sep in (";", ","):
                    try:
                        df = pd.read_csv(io.BytesIO(content), sep=sep, decimal=",", encoding="latin-1", header=None)
                        if df.shape[1] >= 2:
                            break
                    except Exception:
                        continue
                df.columns = [f"col{i}" for i in range(df.shape[1])]
            else:
                df = pd.read_excel(io.BytesIO(content), header=None)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {e}")

    df = df.dropna(how="all")
    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo está vacío o no contiene datos.")

    mapping = _map_columns(df)

    def col(field, default=""):
        return pd.Series([_val(row, mapping, field, default) for _, row in df.iterrows()])

    codes = [str(c).strip() for c in col("code")]
    names = [str(n).strip() for n in col("name")]
    stocks = pd.to_numeric(col("stock", 0), errors="coerce").fillna(0).clip(lower=0).astype(int)
    compras = pd.to_numeric(col("compra", 0), errors="coerce").fillna(0)
    ventas = pd.to_numeric(col("venta", 0), errors="coerce").fillna(0)
    ubi1 = [str(u).strip() for u in col("ubicacion1")]
    ubi2 = [str(u).strip() for u in col("ubicacion2")]
    ubi3 = [str(u).strip() for u in col("ubicacion3")]

    # --- Procesamiento robusto ---
    # La sesión usa autoflush=False, por lo que las consultas NO ven los
    # productos pendientes de la misma carga. Para evitar que dos filas con el
    # mismo código (p. ej. "-") rompan la restricción UNIQUE, se deduplican los
    # códigos (gana la última fila) y a las filas sin código válido se les
    # asigna uno automático (AUTO1, AUTO2, ...).
    seen: dict = {}
    skipped = 0
    auto = 0
    for i in range(len(df)):
        name = names[i]
        if not name:
            skipped += 1
            continue
        code = codes[i]
        if not code or code.lower() in ("nan", "none", "-", "s/c", "n/a", "sincodigo"):
            auto += 1
            code = f"AUTO{auto}"
        payload = {
            "code": code,
            "name": name,
            "stock": int(stocks.iloc[i]),
            "purchase_price": float(compras.iloc[i]),
            "sale_price": float(ventas.iloc[i]),
            "location1": ubi1[i] or None,
            "location2": ubi2[i] or None,
            "location3": ubi3[i] or None,
        }
        seen[code] = payload

    created, updated = 0, 0
    for code, payload in seen.items():
        product = (
            db.query(Product)
            .filter(Product.code == code, Product.tenant_id == user.tenant_id)
            .first()
        )
        if product:
            for field, value in payload.items():
                setattr(product, field, value)
            # Mantener el invariante stock = suma(filas). Si ya hay filas de
            # ubicación, la diferencia del import se absorbe en la primera.
            loc_utils.reconcile_stock(db, product)
            updated += 1
        else:
            product = Product(tenant_id=user.tenant_id, **payload)
            db.add(product)
            created += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="No se pudieron guardar los productos: hay códigos repetidos o datos inválidos. "
                   "Revisa que cada fila tenga un código único y un nombre.",
        ) from exc

    # Sembrar filas de ubicación para los productos recién creados (una fila
    # con el stock total asignado a su ubicación principal).
    for product in db.query(Product).filter(Product.tenant_id == user.tenant_id).all():
        loc_utils.ensure_seed(db, product)
    db.commit()

    message = f"Carga completada: {created} nuevos, {updated} actualizados"
    if auto:
        message += f", {auto} con código asignado automáticamente"
    if skipped:
        message += f", {skipped} fila(s) omitida(s) por falta de nombre"
    return {"message": message, "created": created, "updated": updated, "autogenerated": auto, "skipped": skipped}

@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.tenant_id == user.tenant_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    threshold = _get_threshold(db, user.tenant_id)
    return _to_out(db, product, threshold)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if (
        db.query(Product)
        .filter(Product.code == data.code, Product.tenant_id == user.tenant_id)
        .first()
    ):
        raise HTTPException(status_code=400, detail=f"Ya existe un producto con el código '{data.code}'")

    payload = data.model_dump(exclude={"locations"})
    product = Product(tenant_id=user.tenant_id, **payload)
    db.add(product)
    db.flush()

    if data.locations:
        loc_utils.set_locations(db, product, [l.model_dump() for l in data.locations])
    else:
        # Falla hacia el comportamiento antiguo: todo el stock en una sola fila
        loc_utils.ensure_seed(db, product)

    db.commit()
    db.refresh(product)
    return _to_out(db, product, 5)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.tenant_id == user.tenant_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    updates = data.model_dump(exclude_unset=True)
    if "code" in updates and updates["code"] != product.code:
        if (
            db.query(Product)
            .filter(Product.code == updates["code"], Product.tenant_id == user.tenant_id)
            .first()
        ):
            raise HTTPException(status_code=400, detail=f"Ya existe un producto con el código '{updates['code']}'")

    for field, value in updates.items():
        setattr(product, field, value)
    db.flush()

    if data.locations is not None:
        loc_utils.set_locations(db, product, [l.model_dump() for l in data.locations])
    else:
        loc_utils.ensure_seed(db, product)

    db.commit()
    db.refresh(product)
    return _to_out(db, product, 5)


@router.delete("/all", status_code=200)
def delete_all_products(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Elimina TODOS los productos del cliente (solo administrador).

    Exige confirmación implícita: no hay copia de seguridad, así que primero
    se verifica que no haya préstamos activos con mercancía pendiente.
    """
    from app.models import Loan
    from app.utils.audit import record_audit

    active = (
        db.query(Loan)
        .filter(
            Loan.tenant_id == user.tenant_id,
            Loan.quantity > Loan.returned_qty,
        )
        .count()
    )
    if active:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Hay {active} préstamo(s) con mercancía pendiente por devolver. "
                "Primero cierra esos préstamos o cambia los productos antes de borrar el inventario."
            ),
        )

    deleted = (
        db.query(ProductStockLocation)
        .filter(ProductStockLocation.tenant_id == user.tenant_id)
        .delete(synchronize_session=False)
    )
    count = (
        db.query(Product)
        .filter(Product.tenant_id == user.tenant_id)
        .delete(synchronize_session=False)
    )
    record_audit(
        db,
        action="ELIMINACION_MASIVA",
        user_id=user.id,
        tenant_id=user.tenant_id,
        detail=f"Inventario vaciado: {count} producto(s) eliminados",
    )
    db.commit()
    return {"message": f"Se eliminaron {count} producto(s).", "deleted": count, "stock_rows": deleted}


@router.delete("/{product_id}", status_code=200)
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.tenant_id == user.tenant_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    from app.models import Loan

    active = (
        db.query(Loan)
        .filter(
            Loan.product_id == product_id,
            Loan.tenant_id == user.tenant_id,
            Loan.quantity > Loan.returned_qty,
        )
        .count()
    )
    if active:
        raise HTTPException(
            status_code=400,
            detail=f"El producto '{product.name}' tiene {active} préstamo(s) activo(s). Devuelva la mercancía antes de eliminarlo.",
        )

    db.query(ProductStockLocation).filter(
        ProductStockLocation.product_id == product_id,
        ProductStockLocation.tenant_id == user.tenant_id,
    ).delete(synchronize_session=False)
    db.delete(product)
    db.commit()
    return {"message": "Producto eliminado correctamente."}
