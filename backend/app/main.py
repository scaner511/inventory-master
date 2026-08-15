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


def init_db() -> None:
    """Crea tablas y datos por defecto si no existen."""
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        _migrate(db)
        # Usuario administrador inicial
        if not db.query(models.User).filter(models.User.username == settings.admin_username).first():
            db.add(
                models.User(
                    username=settings.admin_username,
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    role="admin",
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
