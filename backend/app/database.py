"""Motores y sesiones SQLAlchemy de la plataforma y de cada cliente.

Arquitectura multi-base:

- **Plataforma** (`UNA` base): cuentas, licencias y conexiones Drive de todos
  los clientes. Es la base configurada en DATABASE_URL. No contiene datos de
  negocio (inventario, préstamos, reportes).
- **Negocio** (`UNA POR cliente`): el inventario, préstamos, ubicaciones,
  auditoría y ajustes de UN CLIENTE. Cada tenant tiene su propia base física
  (`tenants.database_name`). El Super Admin no puede obtener sesión de negocio
  (su `tenant_id` es NULL), así que le es imposible leer o mezclar los datos.

Si no hay PostgreSQL disponible en desarrollo, la plataforma cae a SQLite
local y cada tenant recibe un archivo SQLite propio en el mismo directorio.
"""
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BASE_DIR, settings

USING_SQLITE = False


def _resolve_database_url() -> str:
    global USING_SQLITE

    db_url = settings.database_url
    env_file = BASE_DIR / ".env"

    # Render expone DATABASE_URL con el esquema `postgres://`, pero SQLAlchemy
    # necesita `postgresql+psycopg2://`. Se normaliza automáticamente.
    if db_url.startswith("postgres://"):
        db_url = "postgresql+psycopg2://" + db_url[len("postgres://"):]
    elif db_url.startswith("postgresql://"):
        db_url = "postgresql+psycopg2://" + db_url[len("postgresql://"):]

    # En Render (producción) SIEMPRE se debe usar PostgreSQL. El disco del plan
    # Free es EFÍMERO: si la app cae a SQLite ahí, la licencia, los usuarios y
    # los datos se borran en cada reinicio/redeploy. Si falta DATABASE_URL o la
    # base no responde, fallamos con un error visible en lugar de usar SQLite.
    is_render = __import__("os").environ.get("RENDER") == "true"
    if is_render and "DATABASE_URL" not in __import__("os").environ:
        raise RuntimeError(
            "No se definió DATABASE_URL en Render. Conecta la base de datos "
            "PostgreSQL al Web Service (Dashboard → servicio → Connect) o define "
            "la variable DATABASE_URL en Environment. Sin PostgreSQL, el sistema "
            "perdería la licencia y los datos en cada reinicio."
        )

    # Fallback a SQLite SOLO en desarrollo (fuera de Render) y solo si el usuario
    # no configuró PostgreSQL explícitamente (sin .env ni DATABASE_URL).
    using_default = "DATABASE_URL" not in __import__("os").environ and not env_file.exists()
    if db_url.startswith("postgresql") and using_default:
        probe = create_engine(db_url, connect_args={"connect_timeout": 3})
        try:
            with probe.connect() as conn:
                conn.execute(text("SELECT 1"))
            probe.dispose()
            return db_url
        except Exception as exc:
            probe.dispose()
            sqlite_path = Path(BASE_DIR) / "inventario_dev.db"
            USING_SQLITE = True
            print("=" * 60)
            print("[AVISO] PostgreSQL no disponible, usando SQLite local.")
            print(f"        Detalle: {exc}")
            print("        Modo solo para DESARROLLO. Para red local usa")
            print("        PostgreSQL (ver README.md / docs/deployment.md).")
            print("=" * 60)
            return f"sqlite:///{sqlite_path}"

    # El usuario configuró su propia base (PostgreSQL u otra)
    if db_url.startswith("sqlite"):
        USING_SQLITE = True
    return db_url


DATABASE_URL = _resolve_database_url()

# ---------------------------------------------------------------------------
# Motor y sesión de la PLATAFORMA (la base configurada en DATABASE_URL).
# ---------------------------------------------------------------------------
if DATABASE_URL.startswith("sqlite"):
    # En desarrollo, cada base de negocio es un archivo dentro de una carpeta
    # derivada del nombre de la base de la plataforma (evita colisiones entre
    # entornos de prueba y agrupa los archivos de cada cliente).
    _platform_db_file = DATABASE_URL[len("sqlite:///"):]
    _base_dir = BASE_DIR
    _stem = "inventario_dev"
    if _platform_db_file:
        _p = Path(_platform_db_file)
        if _p.parent and str(_p.parent) not in ("", "."):
            _base_dir = _p.parent
        _stem = _p.stem or _stem
    _sqlite_dir = _base_dir / f"{_stem}_tenants"
    _sqlite_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base para los modelos de PLATAFORMA (cuentas y licencias)."""


class BaseBusiness(DeclarativeBase):
    """Base para los modelos de NEGOCIO de cada cliente."""


def get_db():
    """Dependencia de FastAPI: sesión de la PLATAFORMA (cuentas y licencias)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Motores por tenant (UNA base de datos de negocio por cliente).
# ---------------------------------------------------------------------------
_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _slug_re.sub("_", name.strip().lower()).strip("_")[:60]


def default_database_name(tenant_id: int) -> str:
    """Nombre por defecto de la base de datos de un cliente."""
    return f"im_tenant_{tenant_id}"


_tenant_engines: dict[int, "object"] = {}
_engines_lock = threading.Lock()


def _tenant_engine_dsn(database_name: str) -> str:
    """DSN de la base de negocio de un cliente.

    - PostgreSQL: mismo servidor/usuario que la plataforma, otra base.
    - SQLite (solo desarrollo): archivo junto a la base de la plataforma.
    """
    if DATABASE_URL.startswith("sqlite"):
        path = _sqlite_dir / f"{database_name}.db"
        return f"sqlite:///{path}"
    parts = urlparse(DATABASE_URL)
    db = parts.path.lstrip("/")
    return DATABASE_URL.replace(f"/{db}", f"/{database_name}")


def get_tenant_engine(tenant) -> "object":
    """Devuelve (y cachea) el motor de la base de negocio de un cliente."""
    database_name = tenant.database_name or default_database_name(tenant.id)
    with _engines_lock:
        if tenant.id in _tenant_engines:
            return _tenant_engines[tenant.id]
        dsn = _tenant_engine_dsn(database_name)
        if dsn.startswith("sqlite"):
            te = create_engine(dsn, pool_pre_ping=True, connect_args={"check_same_thread": False})
        else:
            te = create_engine(dsn, pool_pre_ping=True, pool_size=5, max_overflow=10)
        _tenant_engines[tenant.id] = te
        return te


def dispose_tenant_engine(tenant_id: int) -> None:
    """Cierra y elimina de la caché el motor del cliente (útil al eliminar)."""
    with _engines_lock:
        te = _tenant_engines.pop(tenant_id, None)
    if te is not None:
        te.dispose()


def get_tenant_session(tenant_id: int) -> Session:
    """Abre una sesión a la base de negocio del cliente.

    Consulta el cliente en la plataforma para obtener su `database_name`.
    """
    from app.models import Tenant  # import tardío para evitar ciclos

    pldb = SessionLocal()
    try:
        tenant = pldb.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(404, "Cliente no encontrado")
        engine_t = get_tenant_engine(tenant)
    finally:
        pldb.close()
    return sessionmaker(bind=engine_t)()  # sesión sin autocommit, se cierra por el router


def create_tenant_database(tenant, with_schema: bool = True) -> None:
    """Crea la base de datos de negocio del cliente (si no existe) y su esquema.

    Debe llamarse fuera de cualquier transacción activa (autocommit).
    """
    from sqlalchemy import inspect

    database_name = tenant.database_name or default_database_name(tenant.id)
    is_sqlite = DATABASE_URL.startswith("sqlite")

    if not is_sqlite:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": database_name}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{database_name}"'))
    te = get_tenant_engine(tenant)
    if with_schema:
        insp = inspect(te)
        if not insp.has_table("products"):
            BaseBusiness.metadata.create_all(bind=te)
    return None


def drop_tenant_database(tenant_id: int, database_name: str | None) -> None:
    """Elimina la base de datos de negocio del cliente (plataforma intacta)."""
    dispose_tenant_engine(tenant_id)
    if not database_name:
        return
    if DATABASE_URL.startswith("sqlite"):
        path = _sqlite_dir / f"{database_name}.db"
        if path.exists():
            path.unlink(missing_ok=True)
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(
            text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"),
            {"n": database_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))