"""Generador CLI de licencias offline (HMAC-SHA256).

Pegas el código de activación del equipo (lo muestra el programa con
get_activation_code) y una fecha de expiración YYYY-MM-DD, y obtienes la clave.

Uso:
    python generador_licencias_offline.py <codigo_activacion> <AAAA-MM-DD>
    python generador_licencias_offline.py AB12-CD34-EF56-7890 2027-12-31

La SECRET_KEY se lee de la variable de entorno LICENSE_SECRET_KEY; si no existe
se usa la constante SECRET_KEY (debe coincidir con la del módulo del programa
backend/app/utils/offline_license.py). Solo librería estándar.
"""
import argparse
import base64
import hashlib
import hmac
import os
import subprocess
import sys
from datetime import date

SECRET_KEY = os.environ.get("LICENSE_SECRET_KEY", "6c5ab6f076be4a57a76a81c1dfc19000a6dd493b054f91b3520dc8206919fcf8")

VERSION = "LIC"


def generate_license(activation_code: str, expiry: str, secret: str | None = None) -> str:
    payload = f"{activation_code.strip().upper().replace(' ', '')}|{expiry.strip()}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    secret = secret or SECRET_KEY
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{VERSION}.{payload_b64}.{sig}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera una clave de licencia offline (HMAC-SHA256).")
    parser.add_argument("activation_code", help="Código de activación del equipo (XXXX-XXXX-XXXX-XXXX)")
    parser.add_argument("expiry", help="Fecha de expiración en formato AAAA-MM-DD")
    parser.add_argument("--secret", help="SECRET_KEY (alternativa a LICENSE_SECRET_KEY / la hardcodeada)")
    args = parser.parse_args()

    try:
        exp = date.fromisoformat(args.expiry)
    except ValueError:
        print("Error: la fecha debe tener formato AAAA-MM-DD.", file=sys.stderr)
        return 1
    if exp < date.today():
        print("Aviso: la fecha de expiración ya pasó (la licencia nacería vencida).", file=sys.stderr)

    key = generate_license(args.activation_code, args.expiry, args.secret)
    print(key)

    if sys.platform == "win32":
        try:
            subprocess.run(["clip"], input=key.encode("utf-8"), check=True)
            print("(copiada al portapapeles)", file=sys.stderr)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
