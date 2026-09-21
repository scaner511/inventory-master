"""Inventory Master OS Web - Aplicación principal FastAPI."""
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

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
    payments,
    products,
    reports,
    settings as settings_router,
    superadmin,
    users,
)
from app.utils.security import decode_access_token, hash_password
from app.utils import offline_license


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


def _migrate_tenant_max_users(db: Session) -> None:
    """Agrega la columna max_users a la tabla tenants (limite por proveedor)."""
    if "max_users" not in _table_columns("tenants"):
        db.execute(text("ALTER TABLE tenants ADD COLUMN max_users INTEGER"))
    db.commit()


def _migrate_tenant_price(db: Session) -> None:
    """Agrega la columna price_usd a tenants (precio de licencia por cliente).

    NULL = usar el precio global PAYPAL_PRICE_USD (p. ej. 75 USD); con valor,
    ese cliente paga su propio monto (p. ej. Varmoore a 55 USD).
    """
    if "price_usd" not in _table_columns("tenants"):
        db.execute(text("ALTER TABLE tenants ADD COLUMN price_usd NUMERIC(12, 2)"))
    db.commit()


def _migrate_accept_terms(db: Session) -> None:
    """Agrega las columnas de aceptación de términos a la tabla users."""
    cols = _table_columns("users")
    if "accepted_terms" not in cols:
        default = "0" if engine.dialect.name == "sqlite" else "FALSE"
        db.execute(text(f"ALTER TABLE users ADD COLUMN accepted_terms BOOLEAN NOT NULL DEFAULT {default}"))
    if "accepted_terms_date" not in cols:
        db.execute(text("ALTER TABLE users ADD COLUMN accepted_terms_date TIMESTAMP"))
    db.commit()


def _migrate_drive_per_tenant(db: Session) -> None:
    """Convierte drive_connection a conexión por proveedor (columna tenant_id)."""
    if "drive_connection" not in _table_names():
        return
    if "tenant_id" not in _table_columns("drive_connection"):
        db.execute(text("ALTER TABLE drive_connection ADD COLUMN tenant_id INTEGER"))
        db.commit()
    # La antigua conexión única (id=1) era del Super Admin global (tenant NULL);
    # ya queda así con tenant_id NULL, no requiere migración adicional.
    if engine.dialect.name == "postgresql":
        db.execute(
            text("ALTER TABLE drive_connection DROP CONSTRAINT IF EXISTS ck_drive_connection_single_row")
        )
        db.commit()
    elif engine.dialect.name == "sqlite":
        # SQLite no admite DROP CONSTRAINT; comprobamos si la restricción sigue
        # y, de existir, la quitamos reconstruyendo la tabla.
        row = db.execute(
            text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='drive_connection'"
            )
        ).fetchone()
        if row and row[0] and "ck_drive_connection_single_row" in row[0]:
            _rebuild_drive_connection_sqlite(db)


def _rebuild_drive_connection_sqlite(db: Session) -> None:
    """Reconstruye drive_connection sin la restricción de una sola fila (SQLite)."""
    db.execute(text("CREATE TABLE drive_connection_new ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "tenant_id INTEGER, "
                    "email VARCHAR(255), "
                    "refresh_token TEXT, "
                    "folder_id TEXT, "
                    "folder_name VARCHAR(255), "
                    "connected_at DATETIME, "
                    "UNIQUE (tenant_id))"))
    db.execute(text("INSERT INTO drive_connection_new (id, tenant_id, email, refresh_token, "
                    "folder_id, folder_name, connected_at) "
                    "SELECT id, tenant_id, email, refresh_token, folder_id, folder_name, "
                    "connected_at FROM drive_connection"))
    db.execute(text("DROP TABLE drive_connection"))
    db.execute(text("ALTER TABLE drive_connection_new RENAME TO drive_connection"))
    db.commit()


def _table_columns(table: str) -> set[str]:
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    except Exception:
        return set()


def _table_names() -> set[str]:
    try:
        return {t for t in inspect(engine).get_table_names()}
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


def _migrate_license_machine_code(db: Session) -> None:
    """Agrega columnas machine_code y last_key ampliado a la tabla licenses."""
    cols = _table_columns("licenses")
    if "machine_code" not in cols:
        db.execute(text("ALTER TABLE licenses ADD COLUMN machine_code VARCHAR(19)"))
    if "last_key" in cols:
        # Ampliar last_key a 500 caracteres para soportar claves offline (LIC....)
        if engine.dialect.name == "sqlite":
            row = db.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='licenses'")
            ).first()
            if row and "VARCHAR(20)" in (row[0] or ""):
                db.execute(
                    text(
                        """
                        CREATE TABLE licenses_new (
                            id INTEGER NOT NULL PRIMARY KEY,
                            is_active BOOLEAN NOT NULL DEFAULT 0,
                            activated_at TIMESTAMP,
                            expires_at DATE,
                            last_key VARCHAR(500),
                            machine_code VARCHAR(19)
                        );
                        INSERT INTO licenses_new (id, is_active, activated_at, expires_at, last_key, machine_code)
                        SELECT id, is_active, activated_at, expires_at, last_key, machine_code FROM licenses;
                        DROP TABLE licenses;
                        ALTER TABLE licenses_new RENAME TO licenses;
                        """
                    )
                )
        else:
            db.execute(text("ALTER TABLE licenses ALTER COLUMN last_key TYPE VARCHAR(500)"))
    db.commit()


def _migrate_loan_location_out(db: Session) -> None:
    """Agrega la columna location_out a la tabla loans (stock por ubicación)."""
    if "location_out" not in _table_columns("loans"):
        db.execute(text("ALTER TABLE loans ADD COLUMN location_out VARCHAR(255)"))
        db.commit()


def _migrate_product_stock_locations(db: Session) -> None:
    """Siembra/valida el stock por ubicación de los productos.

    - Productos sin filas de ubicación (creados antes del cambio): se crea una
      fila ("Principal" o su location1) con su stock total.
    - Productos con filas: se reconcilia products.stock = suma(filas).
    """
    from app.utils import locations as loc_utils

    products = db.query(models.Product).all()
    for p in products:
        loc_utils.ensure_seed(db, p)
        loc_utils.reconcile_stock(db, p)
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
    """Asigna el tenant principal a los datos existentes (los superadmins no).

    IMPORTANTE: debe correrse ANTES de _ensure_superadmin. Si se corre después,
    el superadmin (tenant_id=NULL) quedaría asignado al tenant principal y ya no
    sería un usuario global.
    """
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


def _migrate_tenant_licenses(db: Session) -> None:
    """Crea una licencia POR CLIENTE (tenant_licenses) para los existentes.

    Los clientes actuales heredan el estado de la licencia global histórica
    (tabla licenses, fila 1) para que nada cambie para ellos: solo se extiende
    la de quien paga. Los nuevos clientes crean su fila al registrarse.
    """
    lic = db.get(models.License, 1)
    for tenant in db.query(models.Tenant).all():
        exists = (
            db.query(models.TenantLicense)
            .filter(models.TenantLicense.tenant_id == tenant.id)
            .first()
        )
        if exists is None:
            db.add(
                models.TenantLicense(
                    tenant_id=tenant.id,
                    is_active=bool(lic and lic.is_active),
                    activated_at=lic.activated_at if lic else None,
                    expires_at=lic.expires_at if lic else None,
                    last_key=lic.last_key if lic else None,
                    machine_code=lic.machine_code if lic else None,
                )
            )
    db.commit()


def _ensure_superadmin(db: Session) -> None:
    if settings.superadmin_username == settings.admin_username:
        return  # mismo usuario: el admin principal ya es el superadmin global
    user = db.query(models.User).filter(models.User.username == settings.superadmin_username).first()
    if user is not None:
        # El Super Admin es GLOBAL: nunca pertenece a un proveedor. El backfill
        # de tenants corre antes y podría haberle asignado el tenant principal.
        user.role = "superadmin"
        if user.tenant_id is not None:
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
        _migrate_license_machine_code(db)
        _migrate_accept_terms(db)
        _migrate_tenant_max_users(db)
        _migrate_tenant_price(db)
        _migrate_drive_per_tenant(db)
        _migrate_loan_location_out(db)
        _migrate_product_stock_locations(db)

        # Cliente principal + datos existentes
        first_tenant = _get_or_create_first_tenant(db)
        _backfill_tenant(db, first_tenant.id)
        _migrate_products_unique(db)
        _ensure_tenant_indexes(db)

        _ensure_superadmin(db)

        # Usuario administrador del cliente principal
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
        lic = db.get(models.License, 1)
        if lic is None:
            lic = models.License(id=1, is_active=False)
            db.add(lic)
        # Calcular y almacenar el código de activación de máquina UNA sola vez.
        # Render free cambia de instancia entre reinicios; si no se guarda en la
        # BD, el código puede cambiar y las licencias offline dejarían de
        # funcionar. Al guardarlo se usa siempre el mismo valor.
        if not lic.machine_code:
            lic.machine_code = offline_license.get_activation_code()

        db.commit()

        _migrate_tenant_licenses(db)

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
        path, _kind = backup_service.create_backup(db)
        backup_service.cleanup_old_backups()
        if settings.google_drive_auto_upload:
            from app.services import gdrive

            if gdrive.active_mode(db, None):
                try:
                    gdrive.upload_file(path, db, None)
                except Exception:
                    pass  # la copia local ya está a salvo; Drive se reintenta al día siguiente
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    schedule_backup_job()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


class TermsAcceptanceMiddleware:
    """Bloqueo global para usuarios que no han aceptado los términos legales.

    Middleware ASGI puro: cubre TODAS las rutas /api/* actuales y futuras en un
    único punto, sin depender de que cada router recuerde la dependencia. Solo
    quedan exentas las llamadas imprescindibles antes de aceptar: login,
    recuperación de cuenta, perfil, la propia aceptación, health-check,
    documentación y el flujo OAuth de Drive (que se valida por otros medios).
    """

    EXEMPT_PATHS = (
        "/api/health",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/accept-terms",
        "/api/backup/drive/oauth",
        "/docs",
        "/redoc",
        "/openapi.json",
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] != "OPTIONS":
            path = scope["path"]
            exempt = any(path == p or path.startswith(p + "/") for p in self.EXEMPT_PATHS)
            if path.startswith("/api/") and not exempt:
                # Solo se bloquea a quien está AUTENTICADO y aún no aceptó.
                # Sin token o con token inválido no se toca: el 401 lo pone la
                # dependencia de autenticación de cada ruta.
                if self._authenticated_without_terms(scope):
                    response = JSONResponse(
                        status_code=403,
                        content={
                            "detail": {
                                "code": "TERMS_NOT_ACCEPTED",
                                "message": (
                                    "Debes leer y aceptar los Términos y Condiciones "
                                    "y la Política de Privacidad para usar el sistema."
                                ),
                            }
                        },
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)

    def _authenticated_without_terms(self, scope) -> bool:
        """True solo con un token válido de un usuario activo que NO ha aceptado."""
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return False
        payload = decode_access_token(auth[len("Bearer "):].strip())
        if not payload or not payload.get("sub"):
            return False
        db: Session = SessionLocal()
        try:
            user = db.get(models.User, int(payload["sub"]))
            return user is not None and user.is_active and not user.accepted_terms
        except Exception:
            return False
        finally:
            db.close()


app = FastAPI(
    title="Inventory Master OS Web",
    description="Sistema de inventario con préstamos y licencias",
    version="2.0.0",
    lifespan=lifespan,
)

# El bloqueo por términos corre por DENTRO de CORS: registrado primero, CORS
# queda como capa más externa y los preflight OPTIONS no tocan la base de datos.
app.add_middleware(TermsAcceptanceMiddleware)

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

# Pagos (auto-activación de licencia): accesibles AUNQUE la licencia esté
# vencida, porque el cliente debe poder pagar para reactivarse.
app.include_router(payments.router)

# Rutas de negocio bloqueadas si la licencia no está activa
business_deps = [Depends(require_valid_license)]
app.include_router(products.router, dependencies=business_deps)
app.include_router(loans.router, dependencies=business_deps)
app.include_router(dashboard.router, dependencies=business_deps)
app.include_router(reports.router, dependencies=business_deps)
app.include_router(backup.router, dependencies=business_deps)
# El flujo OAuth de Drive lo inicia/retoma Google desde el navegador: sin
# bloqueo de licencia ni JWT (se valida por otros medios dentro de cada ruta).
app.include_router(backup.oauth_router)
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
