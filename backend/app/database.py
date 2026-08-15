"""Motor de base de datos y sesiones SQLAlchemy.

Si no hay un archivo .env y PostgreSQL no está disponible, la aplicación
cae automáticamente a SQLite local para poder probar en desarrollo sin
instalar nada. Para el despliegue en red se usa PostgreSQL (configurado
en el archivo .env).
"""
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings

USING_SQLITE = False


def _resolve_database_url() -> str:
    global USING_SQLITE

    db_url = settings.database_url
    env_file = BASE_DIR / ".env"

    # Solo se aplica el fallback cuando NO hay .env configurado
    # (es decir, cuando el usuario aún no eligió PostgreSQL explícitamente)
    # y el destino configurado por defecto (PostgreSQL) no responde.
    if db_url.startswith("postgresql") and not env_file.exists():
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
