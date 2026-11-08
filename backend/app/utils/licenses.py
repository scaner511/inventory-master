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
from app.models import License, UsedLicenseKey

LICENSE_PATTERN = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")


def _base36_decode(s: str) -> int:
    return int(s, 36)


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


def activate_license(db: Session, key: str) -> dict:
    """Activa la licencia por los días codificados en la clave (o los
    configurados por defecto si la clave es de formato antiguo)."""
    key = key.strip().upper()

    if not validate_key_format(key):
        return {"ok": False, "error": "Formato de clave inválido. Debe ser: MC26-XXXX-XXXX"}

    used = db.query(UsedLicenseKey).filter(UsedLicenseKey.key_value == key).first()
    if used:
        return {"ok": False, "error": "Esta clave ya ha sido utilizada anteriormente."}

    days = decode_days(key) or settings.license_duration_days
    expires = date.today() + timedelta(days=days)

    lic = db.get(License, 1)
    if lic is None:
        lic = License(id=1)
        db.add(lic)
    lic.is_active = True
    lic.activated_at = datetime.now()
    lic.expires_at = expires
    lic.last_key = key

    db.add(UsedLicenseKey(key_value=key, used_at=datetime.now()))
    db.commit()

    return {"ok": True, "expires_at": expires.isoformat(), "days": days}
