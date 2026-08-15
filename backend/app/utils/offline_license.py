"""Sistema de licencias offline basado en la máquina (HMAC-SHA256).

Flujo:
1. get_activation_code()  ->  código de activación único del equipo (XXXX-XXXX-XXXX-XXXX)
                              derivado de la MAC + MachineGuid (Windows) / machine-id
                              (Linux) + hostname.
2. El operador genera la clave con tools/generador_licencias_offline.py:
                              LIC.<payload_base64url>.<firma_hmac_base64url>
                              donde payload = "<código_activación>|<AAAA-MM-DD>".
3. validate_license()  ->  verifica firma, que el código corresponda a esta máquina
                              y que la fecha no haya expirado.

La SECRET_KEY se lee de la variable de entorno LICENSE_SECRET_KEY y, si no existe,
usa la constante SECRET_KEY de aquí. El generador independiente
(tools/generador_licencias_offline.py) debe usar la MISMA SECRET_KEY.
Solo librería estándar.
"""
import base64
import hashlib
import hmac
import os
import socket
import sys
import uuid
from datetime import date

SECRET_KEY = os.environ.get("LICENSE_SECRET_KEY", "6c5ab6f076be4a57a76a81c1dfc19000a6dd493b054f91b3520dc8206919fcf8")

VERSION = "LIC"


def _hardware_ids() -> list[str]:
    ids: list[str] = []
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                ids.append("guid=" + winreg.QueryValueEx(k, "MachineGuid")[0].strip().lower())
        except Exception:
            pass
    else:
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(path, encoding="utf-8") as fh:
                    ids.append("machine-id=" + fh.read().strip().lower())
            except Exception:
                pass
    ids.append("mac=" + f"{uuid.getnode():012x}")
    ids.append("host=" + socket.gethostname().strip().lower())
    return ids


def get_activation_code() -> str:
    """Código de activación único de esta máquina (XXXX-XXXX-XXXX-XXXX)."""
    raw = "|".join(_hardware_ids())
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i : i + 4] for i in range(0, 16, 4))


def _build_payload(activation_code: str, expiry: str) -> str:
    code = activation_code.strip().upper().replace(" ", "")
    return f"{code}|{expiry.strip()}"


def _sign(payload: str, secret: str | None = None) -> str:
    secret = secret or SECRET_KEY
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_license(activation_code: str, expiry: str, secret: str | None = None) -> str:
    """Genera la clave de licencia: LIC.<payload_b64>.<firma_b64>."""
    payload = _build_payload(activation_code, expiry)
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{VERSION}.{payload_b64}.{_sign(payload, secret)}"


def _b64decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def validate_license(
    license_key: str,
    secret: str | None = None,
    activation_code: str | None = None,
    today: date | None = None,
) -> dict:
    """Valida la licencia: formato, firma, código de máquina y expiración.

    Devuelve {"valid": True, "expires_at": ..., "days_left": ...} o
    {"valid": False, "reason": "formato_invalido" | "firma_invalida" |
     "codigo_no_coincide" | "expirada"}.
    """
    secret = secret or SECRET_KEY
    try:
        version, payload_b64, sig_b64 = license_key.strip().split(".")
        if version != VERSION:
            raise ValueError("version")
        payload = _b64decode(payload_b64).decode("utf-8")
        code, expiry = payload.split("|")
        expiry_date = date.fromisoformat(expiry)
        actual_sig = _b64decode(sig_b64)
    except Exception:
        return {"valid": False, "reason": "formato_invalido"}

    expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, actual_sig):
        return {"valid": False, "reason": "firma_invalida"}

    if activation_code is not None:
        expected_code = activation_code.strip().upper().replace(" ", "")
        if code != expected_code:
            return {"valid": False, "reason": "codigo_no_coincide"}

    ref = today or date.today()
    if expiry_date < ref:
        return {"valid": False, "reason": "expirada", "expires_at": expiry}
    return {"valid": True, "expires_at": expiry, "days_left": (expiry_date - ref).days}
