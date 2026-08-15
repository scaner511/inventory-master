"""Inventory Master OS Web - Aplicación principal FastAPI."""
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app import models
from app.config import BASE_DIR, settings
from app.database import Base, SessionLocal, engine
from app.deps import require_valid_license
from app.routers import (
    audit,
    auth,
    backup,
    dashboard,
    license as license_router,
    loans,
    products,
    reports,
    settings as settings_router,
    superadmin,
    users,
)
from app.utils.security import hash_password


def _migrate(db: Session) -> None:
    """Migraciones ligeras para bases existentes sin borrar datos."""
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("users")}
    except Exception:
        return
    if "must_change_password" not in columns:
        default = "1" if engine.dialect.name == "sqlite" else "TRUE"
        db.execute(text(f"ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT {default}"))
        # El admin que ya existía no se ve forzado a cambiar su contraseña.
        db.execute(text("UPDATE users SET must_change_password = 0 WHERE username = :u"), {"u": settings.admin_username})
        db.commit()


def _table_columns(table: str) -> set[str]:
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    except Exception:
        return set()


TENANT_TABLES = ("users", "products", "loans", "audit_logs")


def _migrate_tenant_columns(db: Session) -> None:
    """Agrega la columna tenant_id a las tablas que aún no la tienen."""
    for table in TENANT_TABLES:
        if "tenant_id" not in _table_columns(table):
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER"))
    db.commit()


def _migrate_roles(db: Session) -> None:
    """Rol 'operador' pasa a llamarse 'user' (superadmin | admin | user)."""
    db.execute(text("UPDATE users SET role = 'user' WHERE role = 'operador'"))
    db.commit()


def _get_or_create_first_tenant(db: Session) -> models.Tenant:
    tenant = db.query(models.Tenant).order_by(models.Tenant.id).first()
    if tenant is None:
        tenant = models.Tenant(name=settings.default_tenant_name)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return tenant


def _backfill_tenant(db: Session, tenant_id: int) -> None:
    """Asigna el tenant principal a los datos existentes (los superadmins no)."""
    for table in TENANT_TABLES:
        db.execute(
            text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
            {"tid": tenant_id},
        )
    db.commit()


def _migrate_products_unique(db: Session) -> None:
    """Reemplaza el UNIQUE global de code por un UNIQUE compuesto (tenant_id, code).

    PostgreSQL: DROP del índice UNIQUE ix_products_code (o constraint) + ADD.
    SQLite: reconstruye la tabla (no se pueden quitar índices UNIQUE existentes).
    """
    dialect = engine.dialect.name
    if dialect == "postgresql":
        has_constraint = db.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = 'products_code_key'")
        ).first()
        if has_constraint:
            db.execute(text("ALTER TABLE products DROP CONSTRAINT products_code_key"))
        has_unique_idx = db.execute(
            text(
                "SELECT 1 FROM pg_indexes "
                "WHERE indexname = 'ix_products_code' AND indexdef ILIKE '%UNIQUE%'"
            )
        ).first()
        if has_unique_idx:
            db.execute(text("DROP INDEX IF EXISTS ix_products_code"))
        has_composite = db.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = 'uq_products_tenant_code'")
        ).first()
        if not has_composite:
            db.execute(
                text("ALTER TABLE products ADD CONSTRAINT uq_products_tenant_code UNIQUE (tenant_id, code)")
            )
        db.commit()
    elif dialect == "sqlite":
        row = db.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'ix_products_code'")
        ).first()
        current_idx = (row[0] if row else "") or ""
        if "UNIQUE" not in current_idx.upper():
            return  # ya es un índice normal (migración ya aplicada)
        db.execute(
            text(
                """
                CREATE TABLE products_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    tenant_id INTEGER,
                    code VARCHAR(50),
                    name VARCHAR(255),
                    stock INTEGER,
                    purchase_price NUMERIC(12, 2),
                    sale_price NUMERIC(12, 2),
                    location1 VARCHAR(255),
                    location2 VARCHAR(255),
                    location3 VARCHAR(255),
                    created_at DATETIME,
                    updated_at DATETIME,
                    UNIQUE (tenant_id, code)
                )
                """
            )
        )
        db.execute(
            text(
                """
                INSERT INTO products_new
                    (id, tenant_id, code, name, stock, purchase_price, sale_price,
                     location1, location2, location3, created_at, updated_at)
                SELECT id, tenant_id, code, name, stock, purchase_price, sale_price,
                       location1, location2, location3, created_at, updated_at
                FROM products
                """
            )
        )
        db.execute(text("DROP TABLE products"))
        db.execute(text("ALTER TABLE products_new RENAME TO products"))
        db.execute(text("CREATE INDEX ix_products_name ON products (name)"))
        db.execute(text("CREATE INDEX ix_products_code ON products (code)"))
        db.commit()


def _ensure_tenant_indexes(db: Session) -> None:
    for table in TENANT_TABLES:
        db.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)"))
    db.commit()


def _ensure_superadmin(db: Session) -> None:
    if settings.superadmin_username == settings.admin_username:
        return  # mismo usuario: el admin principal ya es el superadmin global
    user = db.query(models.User).filter(models.User.username == settings.superadmin_username).first()
    if user is not None:
        if user.role != "superadmin":
            user.role = "superadmin"
            user.tenant_id = None
            db.commit()
        return
    db.add(
        models.User(
            username=settings.superadmin_username,
            email=settings.superadmin_email,
            password_hash=hash_password(settings.superadmin_password),
            role="superadmin",
            tenant_id=None,
            must_change_password=True,
        )
    )
    db.commit()


def init_db() -> None:
    """Crea tablas y datos por defecto si no existen."""
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        _migrate(db)
        _migrate_tenant_columns(db)
        _migrate_roles(db)

        # Proveedor principal + datos existentes
        first_tenant = _get_or_create_first_tenant(db)
        _backfill_tenant(db, first_tenant.id)
        _migrate_products_unique(db)
        _ensure_tenant_indexes(db)

        _ensure_superadmin(db)

        # Usuario administrador del proveedor principal
        if not db.query(models.User).filter(models.User.username == settings.admin_username).first():
            db.add(
                models.User(
                    username=settings.admin_username,
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    role="admin",
                    tenant_id=first_tenant.id,
                    must_change_password=False,
                )
            )

        # Fila de configuración
        if not db.get(models.Setting, 1):
            db.add(
                models.Setting(
                    id=1,
                    company_name="Mi Empresa",
                    low_stock_threshold=settings.low_stock_threshold,
                )
            )

        # Fila de licencia
        if not db.get(models.License, 1):
            db.add(models.License(id=1, is_active=False))

        db.commit()
    finally:
        db.close()


scheduler = BackgroundScheduler()


def schedule_backup_job() -> None:
    from app.services import backup as backup_service

    hour, minute = settings.backup_hour.split(":")
    scheduler.add_job(
        _run_scheduled_backup,
        trigger="cron",
        hour=int(hour),
        minute=int(minute),
        id="daily_backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if not scheduler.running:
        scheduler.start()


def _run_scheduled_backup() -> None:
    db: Session = SessionLocal()
    try:
        backup_service.create_backup(db)
        backup_service.cleanup_old_backups()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    schedule_backup_job()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Inventory Master OS Web",
    description="Sistema de inventario con préstamos y licencias",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== Rutas de la API ====
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(license_router.router)
app.include_router(settings_router.router)
app.include_router(superadmin.router)

# Rutas de negocio bloqueadas si la licencia no está activa
business_deps = [Depends(require_valid_license)]
app.include_router(products.router, dependencies=business_deps)
app.include_router(loans.router, dependencies=business_deps)
app.include_router(dashboard.router, dependencies=business_deps)
app.include_router(reports.router, dependencies=business_deps)
app.include_router(backup.router, dependencies=business_deps)
app.include_router(audit.router, dependencies=business_deps)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ==== Frontend estático (build de producción) ====
_dist = Path(BASE_DIR).parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        from fastapi.responses import FileResponse

        candidate = _dist / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        index = _dist / "index.html"
        if index.exists():
            return FileResponse(index)
        return {"detail": "Frontend no compilado"}, 404
