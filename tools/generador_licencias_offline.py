"""Generador de licencias offline (HMAC-SHA256) - ventana y CLI.

Ventana (sin argumentos, lo normal para el operador):
    doble clic en generador_licencias_offline.bat  o  python generador_licencias_offline.py

CLI:
    python generador_licencias_offline.py <codigo_activacion> <AAAA-MM-DD>

La ventana tiene el botón "Mi código" que autocompleta el código de
activación cuando se ejecuta en el mismo equipo donde está el programa.

La SECRET_KEY se lee de la variable de entorno LICENSE_SECRET_KEY; si no
existe se usa la constante SECRET_KEY (debe coincidir con la del programa,
backend/app/utils/offline_license.py). Solo librería estándar.
"""
import argparse
import base64
import hashlib
import hmac
import os
import socket
import subprocess
import sys
import tkinter as tk
import uuid
from datetime import date, timedelta
from tkinter import ttk

SECRET_KEY = os.environ.get("LICENSE_SECRET_KEY", "6c5ab6f076be4a57a76a81c1dfc19000a6dd493b054f91b3520dc8206919fcf8")

VERSION = "LIC"


def get_activation_code() -> str:
    """Código de activación de esta máquina (copia de offline_license.py)."""
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
    digest = hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i : i + 4] for i in range(0, 16, 4))


def generate_license(activation_code: str, expiry: str, secret: str | None = None) -> str:
    payload = f"{activation_code.strip().upper().replace(' ', '')}|{expiry.strip()}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    secret = secret or SECRET_KEY
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{VERSION}.{payload_b64}.{sig}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Licencias Offline - Inventory Master")
        self.geometry("560x330")
        self.resizable(False, False)
        self.configure(bg="#0b1220")
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 6}

        ttk.Label(
            self,
            text="Generador de licencias offline",
            font=("Segoe UI", 14, "bold"),
            foreground="#ffffff",
            background="#0b1220",
        ).pack(pady=(18, 2))

        ttk.Label(
            self,
            text="Formato: LIC.<datos>.<firma HMAC-SHA256>",
            font=("Consolas", 10),
            foreground="#94a3b8",
            background="#0b1220",
        ).pack(pady=(0, 8))

        code_frame = ttk.Frame(self)
        code_frame.pack(fill="x", **pad)
        ttk.Label(code_frame, text="Código de activación del equipo:").pack(side="left")
        ttk.Button(code_frame, text="Mi código", command=self.fill_code).pack(side="right")

        self.code_var = tk.StringVar(value="")
        ttk.Entry(self, textvariable=self.code_var, font=("Consolas", 12)).pack(fill="x", **pad)

        self.expiry_var = tk.StringVar(value=(date.today() + timedelta(days=365)).isoformat())
        expiry_frame = ttk.Frame(self)
        expiry_frame.pack(fill="x", **pad)
        ttk.Label(expiry_frame, text="Fecha de expiración (AAAA-MM-DD):").pack(side="left")

        self.result = tk.StringVar(value="")
        ttk.Entry(self, textvariable=self.result, font=("Consolas", 11), state="readonly").pack(fill="x", **pad)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **pad)

        ttk.Button(buttons, text="Generar", command=self.on_generate).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(buttons, text="Copiar", command=self.on_copy).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(buttons, text="Salir", command=self.destroy).pack(side="left", expand=True, fill="x", padx=(5, 0))

        self.status = ttk.Label(self, text="", background="#0b1220", foreground="#f59e0b")
        self.status.pack(pady=(0, 12))

    def fill_code(self):
        self.code_var.set(get_activation_code())
        self.status.config(text="Código de esta máquina cargado", foreground="#3b82f6")

    def on_generate(self):
        code = self.code_var.get().strip()
        expiry = self.expiry_var.get().strip()
        if not code:
            self.status.config(text="Pega el código de activación o usa «Mi código»", foreground="#ef4444")
            return
        try:
            exp = date.fromisoformat(expiry)
        except ValueError:
            self.status.config(text="Fecha inválida: usa formato AAAA-MM-DD", foreground="#ef4444")
            return
        if exp < date.today():
            self.status.config(text="La fecha de expiración ya pasó", foreground="#f59e0b")
        key = generate_license(code, expiry)
        self.result.set(key)
        self.status.config(text=f"Licencia generada · válida hasta {expiry}", foreground="#10b981")
        self.clipboard_clear()
        self.clipboard_append(key)

    def on_copy(self):
        key = self.result.get()
        if not key:
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        self.status.config(text="Copiada al portapapeles", foreground="#3b82f6")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        App().mainloop()
        return 0

    parser = argparse.ArgumentParser(description="Genera una clave de licencia offline (HMAC-SHA256).")
    parser.add_argument("activation_code", help="Código de activación del equipo (XXXX-XXXX-XXXX-XXXX)")
    parser.add_argument("expiry", help="Fecha de expiración en formato AAAA-MM-DD")
    parser.add_argument("--secret", help="SECRET_KEY (alternativa a LICENSE_SECRET_KEY / la hardcodeada)")
    args = parser.parse_args(argv)

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
