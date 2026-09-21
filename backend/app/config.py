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

    # Super Admin global: crea clientes (tenants) y administra todo el sistema.
    # Si no se configuran variables de entorno, se usan estos valores de desarrollo.
    superadmin_username: str = "superadmin"
    superadmin_password: str = "SuperAdmin123!"
    superadmin_email: str = "superadmin@mccea.local"

    # Multi-cliente
    default_tenant_name: str = "Cliente Principal"
    max_users_per_tenant: int = 4

    # Backups
    backup_dir: str = str(BASE_DIR / "backups")
    backup_hour: str = "03:00"
    backup_retention_days: int = 30

    # Google Drive (respaldos en la nube, opcional)
    google_drive_folder_id: str = ""
    google_service_account_json: str = ""
    google_service_account_file: str = ""
    google_drive_auto_upload: bool = False

    # Google Drive OAuth ("Conectar con Google Drive", opcional)
    # Cliente OAuth creado UNA vez en Google Cloud Console por el desarrollador.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # URL pública de esta API (ej. https://mi-api.onrender.com). Si se define,
    # la URL de retorno de OAuth se construye con ella; si no, se deduce del request.
    public_base_url: str = ""
    # Origen del panel (ej. https://mi-panel.vercel.app). Opcional: si se deja
    # vacío, el retorno tras conectar Google Drive deduce el origen del Referer
    # capturado al iniciar el flujo y lo viaja firmado dentro del estado.
    frontend_origin: str = ""

    # Uploads (logo)
    uploads_dir: str = str(BASE_DIR / "uploads" / "logos")

    # Licencia
    license_prefix: str = "MC26"
    license_duration_days: int = 30

    # Umbral de stock bajo por defecto
    low_stock_threshold: int = 5

    # Contraseña genérica para usuarios nuevos (se pide cambiarla al primer login)
    default_generic_password: str = "Cambiar123!"

    # PayPal (auto-activación de la licencia al pagar, opcional)
    # Modo: "sandbox" para probar sin dinero real | "live" para producción.
    # Las credenciales se crean en https://developer.paypal.com (Apps & Credentials).
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_mode: str = "sandbox"
    # Días de licencia que se otorgan automáticamente al confirmar el pago.
    paypal_license_days: int = 30
    # Monto en USD que se cobra por la activación/renovación. Es el precio
    # GLOBAL: algún cliente puede tener un precio propio (tenants.price_usd).
    paypal_price_usd: float = 75.0
    # ID del webhook configurado en PayPal (opcional pero recomendado: confirma
    # el pago por el servidor aunque el cliente cierre el navegador).
    paypal_webhook_id: str = ""

    # Umbral de stock bajo por defecto
    low_stock_threshold: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def paypal_api_base(self) -> str:
        return (
            "https://api-m.sandbox.paypal.com"
            if self.paypal_mode.lower() == "sandbox"
            else "https://api-m.paypal.com"
        )

    @property
    def paypal_web_base(self) -> str:
        return (
            "https://www.sandbox.paypal.com"
            if self.paypal_mode.lower() == "sandbox"
            else "https://www.paypal.com"
        )

    @property
    def paypal_enabled(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

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
