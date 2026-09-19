"""Backups automáticos de PostgreSQL (pg_dump) con respaldo Excel.

Si pg_dump no está disponible, se genera un respaldo Excel de todas las
tablas usando SQLAlchemy + pandas, que funciona en cualquier entorno.
"""
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import DateTime, inspect, text

from app.config import settings

# Tablas que no se incluyen en los respaldos Excel (tokens/credenciales).
EXCLUDED_TABLES = {"drive_connection"}

# Tablas que NO se respaldan por proveedor (son globales del sistema).
_GLOBAL_TABLES = {"settings", "licenses", "used_license_keys"}


def _pg_dump_available() -> bool:
    return shutil.which("pg_dump") is not None


def run_pg_dump(db_url: str, dest: Path) -> bool:
    """Ejecuta pg_dump. Devuelve True si tuvo éxito."""
    try:
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-privileges", db_url, "-f", str(dest)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode == 0 and dest.stat().st_size > 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _excel_backup(db, dest: Path) -> None:
    """Respaldo completo en Excel de todas las tablas (fallback universal)."""
    inspector = inspect(db.bind)
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        for table in inspector.get_table_names():
            if table in EXCLUDED_TABLES:
                continue  # datos sensibles que no deben copiarse a los respaldos
            df = pd.read_sql_table(table, db.bind)
            sheet = table[:31].replace("$", "_")
            df.to_excel(writer, sheet_name=sheet, index=False)


def _df_for_tenant(db, table: str, tenant_id: int | None) -> pd.DataFrame:
    """Devuelve el DataFrame de una tabla, filtrado a un proveedor.

    - Tablas globales del sistema (settings/licenses/used_license_keys): se
      incluyen completas (son compartidas por todos los proveedores).
    - Tablas con tenant_id (products, loans, users, audit_logs): SOLO las filas
      de ese proveedor.
    - Super Admin (tenant_id None): respaldo completo.
    """
    cols = {c["name"] for c in inspect(db.bind).get_columns(table)}
    if table in _GLOBAL_TABLES:
        return pd.read_sql_table(table, db.bind)
    if tenant_id is not None and "tenant_id" in cols:
        return pd.read_sql(
            text(f"SELECT * FROM {table} WHERE tenant_id = :t"),
            db.bind, params={"t": tenant_id},
        )
    return pd.read_sql_table(table, db.bind)


def create_tenant_backup(db, tenant_id: int | None, tenant_prefix: str = "") -> tuple[Path, str]:
    """Crea un backup del proveedor (solo sus datos) en Excel.

    Retorna (ruta, tipo='excel'). El nombre incluye un prefijo del proveedor
    para distinguir los backups de cada uno cuando se comparte carpeta.
    """
    folder = settings.backup_path
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"backup_{tenant_prefix or 'global'}_{stamp}.xlsx"
    dest = folder / name
    inspector = inspect(db.bind)
    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        for table in inspector.get_table_names():
            if table in EXCLUDED_TABLES:
                continue
            df = _df_for_tenant(db, table, tenant_id)
            sheet = table[:31].replace("$", "_")
            df.to_excel(writer, sheet_name=sheet, index=False)
    return dest, "excel"


def create_backup(db) -> tuple[Path, str]:
    """Crea un backup. Retorna (ruta, tipo) donde tipo es 'postgres' o 'excel'."""
    folder = settings.backup_path
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if _pg_dump_available():
        dest = folder / f"inventario_backup_{stamp}.sql"
        if run_pg_dump(settings.database_url, dest):
            return dest, "postgres"

    dest = folder / f"inventario_backup_{stamp}.xlsx"
    _excel_backup(db, dest)
    return dest, "excel"


def cleanup_old_backups() -> int:
    """Elimina backups más antiguos que la retención configurada. Devuelve cuántos borró."""
    folder = settings.backup_path
    retention = settings.backup_retention_days
    deleted = 0
    for f in _backup_files(folder):
        try:
            age_days = (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).days
            if age_days > retention:
                f.unlink(missing_ok=True)
                deleted += 1
        except OSError:
            continue
    return deleted


def _backup_files(folder: Path):
    """Archivos de backup locales (legados 'inventario_backup_*' y actuales 'backup_*')."""
    seen = {}
    for pat in ("inventario_backup_*", "backup_*"):
        for f in folder.glob(pat):
            if f.is_file():
                seen[f.name] = f
    return seen.values()


def list_backups() -> list[dict]:
    folder = settings.backup_path
    backups = []
    for f in _backup_files(folder):
        backups.append(
            {
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "url": f"/api/backup/download/{f.name}",
                "kind": "postgres" if f.suffix == ".sql" else "excel",
            }
        )
    backups.sort(key=lambda b: b["created"], reverse=True)
    return backups


def purge_all_but_latest() -> tuple[int, str | None]:
    """Elimina todos los backups excepto el más reciente. Devuelve (cantidad borrada, nombre conservado)."""
    backups = list_backups()
    if not backups:
        return 0, None
    kept = backups[0]["name"]
    deleted = 0
    for b in backups[1:]:
        path = settings.backup_path / b["name"]
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
    return deleted, kept


def restore_from_excel(db, buffer) -> dict:
    """Restaura la base de datos completa desde un respaldo Excel (.xlsx).

    El respaldo contiene una hoja por tabla; se vacían las tablas en orden
    (hijos primero) y se reinsertan (padres primero) preservando los ids.
    """
    import pandas as pd

    from app import models

    workbook = pd.read_excel(buffer, sheet_name=None)
    known = {
        "products": models.Product,
        "product_stock_locations": models.ProductStockLocation,
        "loans": models.Loan,
        "users": models.User,
        "settings": models.Setting,
        "licenses": models.License,
        "used_license_keys": models.UsedLicenseKey,
        "audit_logs": models.AuditLog,
    }

    # Vaciar en orden inverso de dependencias (hijos primero).
    clear_order = [
        "audit_logs",
        "loans",
        "product_stock_locations",
        "used_license_keys",
        "products",
        "users",
        "settings",
        "licenses",
    ]
    for name in clear_order:
        if name in workbook:
            db.query(known[name]).delete()
    db.commit()

    counts: dict[str, int] = {}
    insert_order = [
        "settings",
        "licenses",
        "users",
        "used_license_keys",
        "products",
        "product_stock_locations",
        "loans",
        "audit_logs",
    ]
    # Coerción de tipos: las columnas DateTime pueden venir como string
    # (p. ej. al leer el Excel devuelto por SQLite) y SQLAlchemy las rechaza.
    def _coerce(model, col, val):
        if val is None:
            return None
        try:
            ctype = model.__table__.c[col].type
            if isinstance(ctype, DateTime):
                if isinstance(val, (pd.Timestamp, datetime)):
                    return val.to_pydatetime() if isinstance(val, pd.Timestamp) else val
                return datetime.fromisoformat(str(val))
        except (KeyError, AttributeError, ValueError):
            pass
        return val

    for name in insert_order:
        if name not in workbook:
            continue
        df = workbook[name].copy()
        df.columns = [str(c) for c in df.columns]
        model = known[name]
        for _, row in df.iterrows():
            kwargs = {}
            for col in df.columns:
                val = row[col]
                if isinstance(val, float) and pd.isna(val):
                    val = None
                elif isinstance(val, pd.Timestamp):
                    val = val.to_pydatetime()
                elif hasattr(val, "item"):
                    val = val.item()
                kwargs[col] = _coerce(model, col, val)
            db.add(model(**kwargs))
        counts[name] = len(df)
    db.commit()

    # Si hay secuencias (PostgreSQL), reajustarlas para evitar conflictos de id.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text

        for table in ("products", "product_stock_locations", "loans", "users", "audit_logs"):
            db.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                )
            )
        db.commit()

    return counts
