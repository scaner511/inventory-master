"""Motor de base de datos y sesiones SQLAlchemy.

Si no hay un archivo .env y PostgreSQL no está disponible, la aplicación
cae automáticamente a SQLite local para poder probar en desarrollo sin
instalar nada. Para el despliegue en red se usa PostgreSQL (configurado
en el archivo .env).
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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
    is_render = os.environ.get("RENDER") == "true"
    if is_render and "DATABASE_URL" not in os.environ:
        raise RuntimeError(
            "No se definió DATABASE_URL en Render. Conecta la base de datos "
            "PostgreSQL al Web Service (Dashboard → servicio → Connect) o define "
            "la variable DATABASE_URL en Environment. Sin PostgreSQL, el sistema "
            "perdería la licencia y los datos en cada reinicio."
        )

    # Fallback a SQLite SOLO en desarrollo (fuera de Render) y solo si el usuario
    # no configuró PostgreSQL explícitamente (sin .env ni DATABASE_URL).
    using_default = "DATABASE_URL" not in os.environ and not env_file.exists()
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

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
