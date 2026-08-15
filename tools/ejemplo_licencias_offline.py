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

    days = 30
    out = subprocess.run(
        [sys.executable, GENERADOR, code, "--days", str(days)],
        capture_output=True,
        text=True,
        check=True,
    )
    key = out.stdout.strip().splitlines()[-1]
    print(f"2) Licencia generada por la herramienta ({days} días):", key)

    result = validate_license(key, activation_code=code)
    print("3) Validación correcta ->", result)
    assert result["valid"] is True, result

    _, _, sig = key.split(".")
    sig_list = list(sig)
    sig_list[10] = "A" if sig_list[10] != "A" else "B"
    tampered = f"LIC.{key.split('.')[1]}.{''.join(sig_list)}"
    print("   Clave alterada   ->", validate_license(tampered, activation_code=code))
    print("   Otra máquina     ->", validate_license(key, activation_code="FFFF-FFFF-FFFF-FFFF"))

    expired_key = subprocess.run(
        [sys.executable, GENERADOR, code, "--days", "1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().splitlines()[-1]
    print("   Licencia vencida ->", validate_license(expired_key, activation_code=code, today=date.today() + timedelta(days=2)))

    print("\nEjemplo completado: licencia válida activa 30 días.")


if __name__ == "__main__":
    main()
