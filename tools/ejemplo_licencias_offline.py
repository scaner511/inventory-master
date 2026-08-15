"""Ejemplo completo del sistema de licencias offline.

Flujo real:
  1. El programa (esta máquina) obtiene su código de activación.
  2. El operador genera la clave con el generador independiente (CLI).
  3. El programa valida la clave (firma + código + expiración).

Ejecutar:  python ejemplo_licencias_offline.py
"""
import os
import subprocess
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.utils.offline_license import get_activation_code, validate_license  # noqa: E402

GENERADOR = os.path.join(ROOT, "tools", "generador_licencias_offline.py")


def main() -> None:
    code = get_activation_code()
    print("1) Código de activación de esta máquina:", code)

    expiry = (date.today() + timedelta(days=365)).isoformat()
    out = subprocess.run(
        [sys.executable, GENERADOR, code, expiry],
        capture_output=True,
        text=True,
        check=True,
    )
    key = out.stdout.strip().splitlines()[-1]
    print("2) Licencia generada por la herramienta:", key)

    result = validate_license(key, activation_code=code)
    print("3) Validación correcta ->", result)
    assert result["valid"] is True, result

    tampered = key[:-1] + ("A" if key[-1] != "A" else "B")
    print("   Clave alterada   ->", validate_license(tampered, activation_code=code))
    print("   Otra máquina     ->", validate_license(key, activation_code="FFFF-FFFF-FFFF-FFFF"))

    expired_key = subprocess.run(
        [sys.executable, GENERADOR, code, (date.today() - timedelta(days=1)).isoformat()],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().splitlines()[-1]
    print("   Licencia vencida ->", validate_license(expired_key, activation_code=code))

    print("\nEjemplo completado: licencia válida activa 365 días.")


if __name__ == "__main__":
    main()
