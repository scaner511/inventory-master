"""Lógica del sistema de licencias (MC26-XXXX-XXXX) con duración configurable.

La duración en días va codificada en la propia clave (segundo grupo: K + 3
caracteres base36), de modo que cada clave puede tener su propia vigencia.
Las claves las genera el generador independiente (tools/generador_contrasenas.py),
fuera de la aplicación, para que ningún usuario del sistema pueda emitir su
propia licencia. Aquí solo se valida y activa.
Las claves generadas por versiones anteriores (sin duración) siguen siendo
válidas y usan la duración por defecto (LICENSE_DURATION_DAYS).
"""
import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import License, TenantLicense, UsedLicenseKey

LICENSE_PATTERN = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")


def _base36_decode(s: str) -> int:
    return int(s, 36)


def global_machine_code(db: Session) -> str:
    """Código de activación de la máquina del servidor (uno solo, global).

    Se calcula UNA vez y se guarda en la fila global para no cambiar entre
    reinicios (p. ej. Render). Todos los tenants comparten este código, ya
    que el despliegue es un solo servidor.
    """
    from app.utils import offline_license

    lic = db.get(License, 1)
    if lic is None:
        lic = License(id=1)
        db.add(lic)
    if not lic.machine_code:
        lic.machine_code = offline_license.get_activation_code()
        db.commit()
    return lic.machine_code


def get_or_create_tenant_license(db: Session, tenant_id: int) -> TenantLicense:
    row = (
        db.query(TenantLicense)
        .filter(TenantLicense.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        row = TenantLicense(tenant_id=tenant_id, machine_code=global_machine_code(db))
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def extend_tenant_license(
    db: Session, tenant_id: int, days: int, key: str | None = None
) -> TenantLicense:
    """Extiende la licencia del cliente `days` días desde HOY (o desde su
    vencimiento actual si aún no vence: las renovaciones suman días)."""
    row = get_or_create_tenant_license(db, tenant_id)
    today = date.today()
    base = row.expires_at if row.expires_at and row.expires_at > today else today
    row.expires_at = base + timedelta(days=days)
    row.is_active = True
    row.activated_at = datetime.now()
    if key:
        row.last_key = key
    db.commit()
    db.refresh(row)
    return row


def decode_days(key: str) -> int | None:
    """Extrae la duración en días de una clave nueva (MC26-Kxxx-XXXX).

    Las claves antiguas (segundo grupo hexadecimal) no traen duración y
    devuelven None. La "K" es un marcador que no puede aparecer en el
    segundo grupo de una clave antigua (solo usa [0-9A-F]).
    """
    parts = key.split("-")
    if len(parts) == 3 and len(parts[1]) == 4 and parts[1].startswith("K"):
        try:
            return _base36_decode(parts[1][1:])
        except ValueError:
            return None
    return None


def validate_key_format(key: str) -> bool:
    key = key.strip().upper()
    if not key.startswith(settings.license_prefix):
        return False
    return bool(LICENSE_PATTERN.match(key))


def activate_license(
    db: Session, key: str, tenant_id: int | None = None
) -> dict:
    """Activa/renueva la licencia por los días codificados en la clave.

    Si se indica ``tenant_id``, activa SOLO la licencia de ese cliente;
    si no (operador sin tenant), activa la fila global histórica.
    """
    key = key.strip().upper()

    if not validate_key_format(key):
        return {"ok": False, "error": "Formato de clave inválido. Debe ser: MC26-XXXX-XXXX"}

    used = db.query(UsedLicenseKey).filter(UsedLicenseKey.key_value == key).first()
    if used:
        return {"ok": False, "error": "Esta clave ya ha sido utilizada anteriormente."}

    days = decode_days(key) or settings.license_duration_days
    expires = date.today() + timedelta(days=days)

    if tenant_id is not None:
        row = get_or_create_tenant_license(db, tenant_id)
    else:
        row = db.get(License, 1)
        if row is None:
            row = License(id=1)
            db.add(row)
    row.is_active = True
    row.activated_at = datetime.now()
    row.expires_at = expires
    row.last_key = key

    db.add(UsedLicenseKey(key_value=key, used_at=datetime.now()))
    db.commit()

    return {"ok": True, "expires_at": expires.isoformat(), "days": days}
