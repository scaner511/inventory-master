"""Generador de claves de licencia - programa independiente.

Genera claves con el formato del sistema: MC26-XXXX-XXXX.
La duración en días (1 a 46655) va codificada en el segundo grupo de la
clave (K + 3 caracteres base36), igual que en backend/app/utils/licenses.py,
de modo que la vigencia depende de la clave y no solo de la configuración.

Se ejecuta como aplicación de escritorio (tkinter, solo librería estándar):

    python generador_contrasenas.py

O haz doble clic en generador_contrasenas.bat
"""
import hashlib
import secrets
import tkinter as tk
from datetime import datetime
from tkinter import ttk

PREFIX = "MC26"
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _base36_encode(n: int) -> str:
    if n <= 0:
        return "000"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = _B36[r] + out
    return out


def encode_days(days: int) -> str:
    n = min(max(int(days), 1), 46655)
    return _base36_encode(n).zfill(3)


def generate_key(days: int) -> str:
    d_part = encode_days(days)
    raw = f"{PREFIX}{d_part}{secrets.token_hex(8)}{datetime.now().timestamp()}"
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()
    return f"{PREFIX}-K{d_part}-{digest[:4]}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Claves de Licencia - Inventory Master")
        self.geometry("480x260")
        self.resizable(False, False)
        self.configure(bg="#0b1220")
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 6}

        ttk.Label(
            self,
            text="Generador de claves de licencia",
            font=("Segoe UI", 14, "bold"),
            foreground="#ffffff",
            background="#0b1220",
        ).pack(pady=(18, 2))

        ttk.Label(
            self,
            text="Formato: MC26-XXXX-XXXX",
            font=("Consolas", 10),
            foreground="#94a3b8",
            background="#0b1220",
        ).pack(pady=(0, 8))

        self.result = tk.StringVar(value="")
        entry = ttk.Entry(self, textvariable=self.result, font=("Consolas", 12), state="readonly")
        entry.pack(fill="x", **pad)

        days_frame = ttk.Frame(self)
        days_frame.pack(fill="x", **pad)
        ttk.Label(days_frame, text="Días de validez:").pack(side="left")
        self.days_var = tk.IntVar(value=30)
        ttk.Spinbox(
            days_frame,
            from_=1,
            to=3650,
            textvariable=self.days_var,
            width=6,
        ).pack(side="right")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **pad)

        ttk.Button(buttons, text="Generar", command=self.on_generate).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(buttons, text="Copiar", command=self.on_copy).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(buttons, text="Salir", command=self.destroy).pack(side="left", expand=True, fill="x", padx=(5, 0))

        self.status = ttk.Label(self, text="", background="#0b1220", foreground="#f59e0b")
        self.status.pack(pady=(0, 12))

    def on_generate(self):
        try:
            key = generate_key(self.days_var.get())
        except (TypeError, ValueError):
            self.status.config(text="Días inválidos", foreground="#ef4444")
            return
        self.result.set(key)
        self.status.config(
            text=f"Clave generada · válida por {self.days_var.get()} días",
            foreground="#10b981",
        )
        self.clipboard_clear()
        self.clipboard_append(key)

    def on_copy(self):
        key = self.result.get()
        if not key:
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        self.status.config(text="Copiada al portapapeles", foreground="#3b82f6")


if __name__ == "__main__":
    App().mainloop()
