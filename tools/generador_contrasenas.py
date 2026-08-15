"""Generador de contraseñas seguras - programa independiente.

Se ejecuta como aplicación de escritorio (tkinter, solo librería estándar):

    python generador_contrasenas.py

O haz doble clic en generador_contrasenas.bat
"""
import secrets
import string
import tkinter as tk
from tkinter import ttk

# Caracteres ambiguos que se pueden excluir (O/0, l/1, I, etc.)
AMBIGUOUS = "O0lI1|'\"`"


def generate(
    length: int,
    use_upper: bool,
    use_lower: bool,
    use_digits: bool,
    use_symbols: bool,
    exclude_ambiguous: bool,
) -> str:
    chars = ""
    if use_upper:
        chars += string.ascii_uppercase
    if use_lower:
        chars += string.ascii_lowercase
    if use_digits:
        chars += string.digits
    if use_symbols:
        chars += "!@#$%^&*()-_=+[]{};:,.<>?/"

    if not chars:
        raise ValueError("Selecciona al menos un tipo de carácter")

    if exclude_ambiguous:
        chars = "".join(c for c in chars if c not in AMBIGUOUS)

    return "".join(secrets.choice(chars) for _ in range(length))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Contraseñas - Inventory Master")
        self.geometry("460x380")
        self.resizable(False, False)
        self.configure(bg="#0b1220")
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 6}

        ttk.Label(
            self,
            text="Generador de contraseñas",
            font=("Segoe UI", 14, "bold"),
            foreground="#ffffff",
            background="#0b1220",
        ).pack(pady=(18, 2))

        self.result = tk.StringVar(value="")
        entry = ttk.Entry(self, textvariable=self.result, font=("Consolas", 12), state="readonly")
        entry.pack(fill="x", **pad)

        self.len_var = tk.IntVar(value=12)
        length_frame = ttk.Frame(self)
        length_frame.pack(fill="x", **pad)
        ttk.Label(length_frame, text="Longitud:").pack(side="left")
        ttk.Spinbox(
            length_frame,
            from_=6,
            to=64,
            textvariable=self.len_var,
            width=5,
        ).pack(side="right")

        opts_frame = ttk.LabelFrame(self, text=" Caracteres ")
        opts_frame.pack(fill="x", **pad)

        self.upper_var = tk.BooleanVar(value=True)
        self.lower_var = tk.BooleanVar(value=True)
        self.digits_var = tk.BooleanVar(value=True)
        self.symbols_var = tk.BooleanVar(value=False)
        self.ambig_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(opts_frame, text="Mayúsculas", variable=self.upper_var).grid(row=0, column=0, sticky="w", padx=10, pady=4)
        ttk.Checkbutton(opts_frame, text="Minúsculas", variable=self.lower_var).grid(row=0, column=1, sticky="w", padx=10)
        ttk.Checkbutton(opts_frame, text="Números", variable=self.digits_var).grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ttk.Checkbutton(opts_frame, text="Símbolos", variable=self.symbols_var).grid(row=1, column=1, sticky="w", padx=10)
        ttk.Checkbutton(
            opts_frame,
            text="Evitar ambiguos (O, 0, l, 1...)",
            variable=self.ambig_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=6)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **pad)

        ttk.Button(buttons, text="Generar", command=self.on_generate).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(buttons, text="Copiar", command=self.on_copy).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(buttons, text="Salir", command=self.destroy).pack(side="left", expand=True, fill="x", padx=(5, 0))

        self.status = ttk.Label(self, text="", background="#0b1220", foreground="#f59e0b")
        self.status.pack(pady=(0, 12))

    def on_generate(self):
        try:
            pw = generate(
                self.len_var.get(),
                self.upper_var.get(),
                self.lower_var.get(),
                self.digits_var.get(),
                self.symbols_var.get(),
                self.ambig_var.get(),
            )
        except ValueError as exc:
            self.status.config(text=str(exc), foreground="#ef4444")
            return
        self.result.set(pw)
        self.status.config(text="Contraseña generada", foreground="#10b981")
        self.clipboard_clear()
        self.clipboard_append(pw)

    def on_copy(self):
        pw = self.result.get()
        if not pw:
            return
        self.clipboard_clear()
        self.clipboard_append(pw)
        self.status.config(text="Copiada al portapapeles", foreground="#3b82f6")


if __name__ == "__main__":
    App().mainloop()
