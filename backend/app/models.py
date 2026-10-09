"""Modelos ORM de la base de datos.

La aplicación usa UNA base de datos por cliente (empresa):

- **Base (plataforma)**: datos de cuentas y licencias. Tablas: tenants, users,
  licenses, used_license_keys, drive_connection, platform_audit_logs. La
  gestiona el Super Admin (solo cuentas y licencias, sin datos de negocio).
- **BaseBusiness (negocio)**: datos operativos de UN cliente: products,
  product_stock_locations, loans, loan_items, audit_logs, settings. Hay una
  base por cada tenant (su `database_name`), físicamente separada, sin cruce
  posible con otros clientes (ni el Super Admin puede leer su contenido).
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, BaseBusiness

# ==============================================================================
# PLATAFORMA (una sola base global de cuentas y licencias)
# ==============================================================================


class Tenant(Base):
    """Cliente (tenant). Cada cliente tiene SU PROPIA base de datos de negocio.

    La plataforma solo guarda la cuenta, su licencia y el identificador único
    de su base de datos (`database_name`). Nunca guarda datos de inventario.
    """

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # Nombre (único) de la base de datos de negocio de ESTE cliente.
    # Ej: "im_varmoore". Solo el runtime la usa; el Super Admin no lee su contenido.
    database_name: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    # Límite de usuarios permitidos para este cliente (NULL = global).
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Licencia del cliente (30 días renovables). Fuente de verdad: los usuarios
    # del cliente heredan este vencimiento. Solo el Super Admin la ve.
    subscription_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # superadmin no tiene tenant_id (NULL); admin/user siempre pertenecen a uno.
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user")  # superadmin | admin | user
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    security_question: Mapped[str | None] = mapped_column(String(255), nullable=True)
    security_answer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Aceptación obligatoria de Términos y Condiciones / Política de Privacidad
    accepted_terms: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_terms_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Suscripción: vigencia del usuario (heredada de su cliente). Al vencer sin
    # renovar, se bloquea el acceso hasta que el Super Admin registre el pago.
    subscription_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Sesión única: sólo un equipo puede tener la sesión activa a la vez.
    active_session: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant | None"] = relationship(back_populates="users")


class License(Base):
    __tablename__ = "licenses"
    __table_args__ = (CheckConstraint("id = 1", name="ck_license_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    machine_code: Mapped[str | None] = mapped_column(String(19), nullable=True)


class UsedLicenseKey(Base):
    __tablename__ = "used_license_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_value: Mapped[str] = mapped_column(String(20), unique=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DriveConnection(Base):
    """Conexión OAuth de Google Drive por proveedor (tenant).

    Cada proveedor vincula su propia cuenta de Google de su administrador y
    respalda ahí SOLO sus propios datos. Hay una fila por tenant y NO se
    incluye en los respaldos Excel (no se propaga el refresh_token).
    """

    __tablename__ = "drive_connection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Proveedor al que pertenece esta conexión. NULL = global (superadmin).
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id"), nullable=True, unique=True, index=True
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PlatformAuditLog(Base):
    """Registro de eventos de PLATAFORMA (cuentas y licencias).

    Es independiente del historial de negocio (AuditLog, que vive en la base
    de cada cliente): aquí solo se registran acciones del Super Admin como
    crear/renovar/eliminar clientes y renovar licencias.
    """

    __tablename__ = "platform_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ==============================================================================
# NEGOCIO (UNA base de datos por cliente; tenant_id conserva el id del cliente
# para compatibilidad, pero NO es una clave foránea: la base no contiene la
# tabla tenants ni users, así que es imposible cruzar datos entre clientes).
# ==============================================================================


class Product(BaseBusiness):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_products_tenant_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    purchase_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sale_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    location1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Estado físico: "buen_estado" | "incompleto" | "usado"
    condition: Mapped[str] = mapped_column(String(30), default="buen_estado")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductStockLocation(BaseBusiness):
    """Cantidad de unidades de un producto en una ubicación concreta.

    El stock total del producto (products.stock) es SIEMPRE la suma de las
    cantidades de sus filas de ubicación.
    """

    __tablename__ = "product_stock_locations"
    __table_args__ = (
        UniqueConstraint("product_id", "location", name="uq_psl_product_location"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    location: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=0)


class Loan(BaseBusiness):
    """Préstamo: cabecera con datos del vendedor + N ítems (1+ productos).

    Las columnas legacy product_id/product_name/quantity/returned_qty/
    location_out se conservan como instantánea del primer ítem por
    compatibilidad.
    """

    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    seller: Mapped[str] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # --- Columnas legacy (ver docstring del modelo) ---
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)
    location_out: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # --------------------------------------------------
    loan_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date] = mapped_column(Date)
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Solo el id del usuario que lo creó (referencial; la tabla users vive en
    # la base de la plataforma, no en la del cliente).
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["LoanItem"]] = relationship(
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="LoanItem.id",
    )

    @property
    def pending(self) -> int:
        return sum(item.pending for item in self.items)

    @property
    def completed(self) -> bool:
        return bool(self.items) and all(item.completed for item in self.items)

    @property
    def overdue(self) -> bool:
        return not self.completed and self.due_date < date.today()


class LoanItem(BaseBusiness):
    """Ítem de un préstamo: un producto con su cantidad y devoluciones."""

    __tablename__ = "loan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)
    # Ubicación de dónde salió este ítem (feature stock por ubicación).
    location_out: Mapped[str | None] = mapped_column(String(255), nullable=True)

    loan: Mapped["Loan"] = relationship(back_populates="items")

    @property
    def pending(self) -> int:
        return max(self.quantity - self.returned_qty, 0)

    @property
    def completed(self) -> bool:
        return self.returned_qty >= self.quantity


class AuditLog(BaseBusiness):
    """Historial de movimientos de UN cliente (vive en su base de datos)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # Id del usuario de la plataforma que realizó la acción (referencial).
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Setting(BaseBusiness):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)