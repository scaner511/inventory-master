"""Configuración central de la aplicación.

Los valores se leen desde variables de entorno (archivo .env si existe).
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    # Base de datos
    database_url: str = "postgresql+psycopg2://inventario:inventario_secreto@localhost:5432/inventario_db"

    # Seguridad
    secret_key: str = "cambia-esta-clave-secreta-por-una-aleatoria"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # App
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # CORS adicional: expresión regular de orígenes (p. ej. cualquier dominio de Vercel).
    # Los dominios personalizados se agregan como orígenes exactos en CORS_ORIGINS.
    cors_origin_regex: str = r"https://.*\.vercel\.app"
    admin_username: str = "admin"
    admin_password: str = "admin1234"
    admin_email: str = "admin@mccea.local"

    # Super Admin global: crea proveedores (tenants) y administra todo el sistema.
    # Si no se configuran variables de entorno, se usan estos valores de desarrollo.
    superadmin_username: str = "superadmin"
    superadmin_password: str = "SuperAdmin123!"
    superadmin_email: str = "superadmin@mccea.local"

    # Multi-proveedor
    default_tenant_name: str = "Proveedor Principal"
    max_users_per_tenant: int = 4

    # Backups
    backup_dir: str = str(BASE_DIR / "backups")
    backup_hour: str = "03:00"
    backup_retention_days: int = 30

    # Uploads (logo)
    uploads_dir: str = str(BASE_DIR / "uploads" / "logos")

    # Licencia
    license_prefix: str = "MC26"
    license_duration_days: int = 30

    # Umbral de stock bajo por defecto
    low_stock_threshold: int = 5

    # Contraseña genérica para usuarios nuevos (se pide cambiarla al primer login)
    default_generic_password: str = "Cambiar123!"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def backup_path(self) -> Path:
        p = Path(self.backup_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def uploads_path(self) -> Path:
        p = Path(self.uploads_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
