"""Lógica del sistema de licencias mensuales (MC26-XXXX-XXXX, 30 días)."""
import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import License, UsedLicenseKey

LICENSE_PATTERN = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")


def validate_key_format(key: str) -> bool:
    key = key.strip().upper()
    if not key.startswith(settings.license_prefix):
        return False
    return bool(LICENSE_PATTERN.match(key))


def generate_new_key(seed: str = "") -> str:
    """Genera una clave MC26-XXXX-XXXX a partir de un seed (para el admin)."""
    import hashlib

    raw = f"{settings.license_prefix}{seed}{datetime.now().timestamp()}"
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()
    return f"{settings.license_prefix}-{digest[:4]}-{digest[4:8]}"


def activate_license(db: Session, key: str) -> dict:
    """Activa la licencia por 30 días. Retorna info de resultado."""
    key = key.strip().upper()

    if not validate_key_format(key):
        return {"ok": False, "error": "Formato de clave inválido. Debe ser: MC26-XXXX-XXXX"}

    used = db.query(UsedLicenseKey).filter(UsedLicenseKey.key_value == key).first()
    if used:
        return {"ok": False, "error": "Esta clave ya ha sido utilizada anteriormente."}

    expires = date.today() + timedelta(days=settings.license_duration_days)

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

    return {"ok": True, "expires_at": expires.isoformat()}
