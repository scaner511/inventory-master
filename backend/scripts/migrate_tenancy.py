"""Migra la base PLATAFORMA a la arquitectura de UNA BASE DE NEGOCIO POR CLIENTE.

Qué hace, por cada cliente (tenant) existente en la plataforma:

1. Le asigna un `database_name` (slug de su nombre; si ya lo tiene, lo respeta).
2. Crea su base de datos física (PostgreSQL) y su esquema de negocio.
3. Copia SUS datos de negocio desde la base plataforma a su base propia,
   preservando los ids originales (products, product_stock_locations, loans,
   loan_items, audit_logs, settings).
4. Reajusta las secuencias de PostgreSQL de la base destino.

Al final, con `--drop-source`, elimina las tablas de negocio de la base
plataforma (deja solo tenants/users/licenses/drive_connection/
platform_audit_logs). Haga un respaldo pg_dump ANTES de usar `--drop-source`.

Uso (dentro del contenedor de la API o con el entorno del backend):

    # 1) Respaldo previo de la base plataforma
    pg_dump "$DATABASE_URL" > inventario_db_$(date +%Y%m%d).sql

    # 2) Copiar los datos a la base de cada cliente (sin borrar nada aún)
    python -m scripts.migrate_tenancy

    # 3) Verificar que cada cliente ve sus datos y recién entonces:
    python -m scripts.migrate_tenancy --drop-source

Requiere que el usuario de PostgreSQL pueda crear bases:

    ALTER USER inventario CREATEDB;

El script es idempotente: un cliente que ya tenga filas en su base de negocio
se omite (use --force para volver a copiarlo, lo que vacía su base primero).
"""
import argparse
import sys

from sqlalchemy import inspect, select, text

from app.database import (
    BaseBusiness,
    USING_SQLITE,
    create_tenant_database,
    engine,
    get_tenant_engine,
    SessionLocal,
    slugify,
)
from app.models import (
    AuditLog,
    Loan,
    LoanItem,
    Product,
    ProductStockLocation,
    Setting,
    Tenant,
)


# Orden de copia: respeta las claves foráneas dentro de la base del cliente
# (primero los productos, luego lo que los referencia).
BUSINESS_MODELS = [Product, ProductStockLocation, Loan, LoanItem, AuditLog, Setting]


def _source_columns(conn, table_name: str) -> set[str]:
    insp = inspect(conn)
    if not insp.has_table(table_name):
        return set()
    return {c["name"] for c in insp.get_columns(table_name)}


def _copy_model(model, tenant_id: int, src_conn, dest_engine, force: bool) -> int:
    table = model.__table__
    model_cols = [c.name for c in table.columns]
    src_cols = _source_columns(src_conn, table.name)
    if not src_cols:
        return 0

    use_cols = [c for c in model_cols if c in src_cols]
    columns = [table.c[name] for name in use_cols]
    stmt = select(*columns)
    if "tenant_id" in src_cols:
        stmt = stmt.where(table.c.tenant_id == tenant_id)
    elif "loan_id" in src_cols and "tenant_id" in _source_columns(src_conn, "loans"):
        # Tablas hijas (loan_items) sin tenant_id: se filtran por su préstamo.
        stmt = stmt.where(
            table.c.loan_id.in_(
                select(Loan.__table__.c.id).where(Loan.__table__.c.tenant_id == tenant_id)
            )
        )
    elif "product_id" in src_cols and "tenant_id" in _source_columns(src_conn, "products"):
        # Otras tablas hijas: se filtran por su producto.
        stmt = stmt.where(
            table.c.product_id.in_(
                select(Product.__table__.c.id).where(Product.__table__.c.tenant_id == tenant_id)
            )
        )
    else:
        print(f"  [AVISO] {table.name}: sin forma de filtrar por cliente; se omite.")
        return 0

    rows = src_conn.execute(stmt).mappings().all()
    if not rows:
        return 0

    with dest_engine.begin() as dest_conn:
        if force:
            dest_conn.execute(table.delete())
        dest_conn.execute(table.insert(), [dict(r) for r in rows])
    return len(rows)


def _reset_pk_sequences(dest_engine) -> None:
    if USING_SQLITE:
        return
    with dest_engine.begin() as conn:
        for table in BaseBusiness.metadata.sorted_tables:
            if "id" not in table.columns:
                continue
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table.name}
            ).scalar()
            if not seq:
                continue
            conn.execute(
                text(
                    f'SELECT setval(\'{seq}\', COALESCE((SELECT MAX(id) FROM {table.name}), 1), '
                    f'(SELECT COUNT(*) FROM {table.name}) > 0)'
                )
            )


def migrate(force: bool = False) -> None:
    pldb = SessionLocal()
    try:
        tenants = pldb.query(Tenant).order_by(Tenant.id).all()
        if not tenants:
            print("No hay clientes en la plataforma. Nada que migrar.")
            return

        with engine.connect() as src_conn:
            for tenant in tenants:
                if not tenant.database_name:
                    base = slugify(tenant.name) or f"im_tenant_{tenant.id}"
                    name, n = base, 1
                    existing = {t.database_name for t in tenants}
                    while name in existing:
                        n += 1
                        name = f"{base}_{n}"
                    tenant.database_name = name
                    pldb.commit()
                print(f"\nCliente #{tenant.id} '{tenant.name}' -> base '{tenant.database_name}'")

                create_tenant_database(tenant, with_schema=True)
                dest_engine = get_tenant_engine(tenant)

                already = 0
                with dest_engine.connect() as dc:
                    if inspect(dc).has_table("products"):
                        already = dc.execute(text("SELECT COUNT(*) FROM products")).scalar() or 0
                if already and not force:
                    print(f"  Ya tiene {already} producto(s); se omite (use --force para recopiar).")
                    continue
                if already and force:
                    print("  --force: vaciando la base del cliente antes de copiar...")

                total = 0
                for model in BUSINESS_MODELS:
                    n = _copy_model(model, tenant.id, src_conn, dest_engine, force)
                    total += n
                    print(f"  {model.__tablename__}: {n} fila(s)")
                _reset_pk_sequences(dest_engine)
                print(f"  TOTAL copiado: {total} fila(s)")
    finally:
        pldb.close()


def drop_source() -> None:
    """Elimina las tablas de negocio de la base plataforma."""
    insp = inspect(engine)
    present = [t.name for t in BaseBusiness.metadata.sorted_tables if insp.has_table(t.name)]
    if not present:
        print("La base plataforma ya no contiene tablas de negocio.")
        return
    print("Eliminando de la plataforma: " + ", ".join(present))
    BaseBusiness.metadata.drop_all(bind=engine)
    print("Hecho. La plataforma conserva solo las tablas de cuentas y licencias.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Recopia aunque el cliente ya tenga datos (vacía su base).")
    parser.add_argument("--drop-source", action="store_true", help="Elimina las tablas de negocio de la plataforma al final.")
    args = parser.parse_args()
    migrate(force=args.force)
    if args.drop_source:
        drop_source()
    else:
        print(
            "\nCopia terminada. Verifique cada cliente y luego ejecute:\n"
            "    python -m scripts.migrate_tenancy --drop-source"
        )


if __name__ == "__main__":
    sys.exit(main())
