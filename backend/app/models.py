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
    # Módulos habilitados por el administrador (JSON serializado). NULL = todos.
    # Claves válidas: capture, calendar, temporary_storage, prospects.
    modules: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Token FIJO de captación por vendedor: enlace reutilizable de la tablet que
    # no cambia entre jornadas (NULL = aún no generado).
    capture_token: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

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


# ==============================================================================
# MÓDULO: RECEPCIÓN DE MERCANCÍA (mercancía de terceros en depósito temporal)
#
# Totalmente INDEPENDIENTE del inventario oficial. La mercancía NO es propiedad
# de la empresa, NO suma existencias y NO altera products.stock,
# product_stock_locations, préstamos ni reportes de inventario. Usa tablas
# propias; los productos se referencian por id (referencial) y, si no existen
# en el catálogo, se guarda su nombre para no tocar el inventario.
# ==============================================================================


class TemporaryStorageLocation(BaseBusiness):
    """Ubicación física del depósito temporal (catálogo independiente).

    No se mezcla con las ubicaciones del inventario tradicional
    (product_stock_locations): son espacios separados del almacén.
    """

    __tablename__ = "temporary_storage_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ts_location_tenant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TemporaryStorage(BaseBusiness):
    """Recepción: cabecera con los datos del tercero y N productos.

    `number` es el consecutivo autogenerado (REC-AAAA-NNNN).
    `short_code` es un código corto (TS-XXXXXX) único por cliente para
    búsquedas rápidas e impresión del comprobante.
    """

    __tablename__ = "temporary_storage"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_ts_tenant_number"),
        UniqueConstraint("tenant_id", "short_code", name="uq_ts_tenant_short_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    number: Mapped[str] = mapped_column(String(30), index=True)
    short_code: Mapped[str] = mapped_column(String(12), index=True)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today)
    deadline_date: Mapped[date] = mapped_column(Date)
    # Tercero que deja la mercancía (vendedor/proveedor/distribuidor).
    party_name: Mapped[str] = mapped_column(String(150), index=True)
    party_company: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    party_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    party_email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    reference_document: Mapped[str | None] = mapped_column(String(120), nullable=True)
    received_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("temporary_storage_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Estado manual/derivado:
    # recibido | almacenado | devuelto | retirado
    status: Mapped[str] = mapped_column(String(20), default="recibido", index=True)
    # Datos de salida (cuando la mercancía se devuelve o se retira).
    exit_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # devuelto | retirado
    exit_responsible: Mapped[str | None] = mapped_column(String(150), nullable=True)
    exit_document: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exit_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    items: Mapped[list["TemporaryStorageItem"]] = relationship(
        back_populates="storage",
        cascade="all, delete-orphan",
        order_by="TemporaryStorageItem.id",
    )
    location: Mapped["TemporaryStorageLocation | None"] = relationship()

    @property
    def days_left(self) -> int:
        return (self.deadline_date - date.today()).days

    @property
    def is_out(self) -> bool:
        return self.status in ("devuelto", "retirado")

    @property
    def computed_status(self) -> str:
        """Estado visual: conserva el manual (recibido/almacenado) mientras no
        haya salida y agrega el vencimiento calculado en la fecha límite."""
        if self.is_out:
            return self.status
        if self.deadline_date < date.today():
            return "vencido"
        if self.days_left <= 7:
            return "proximo_vencer"
        return self.status

    @property
    def total_units(self) -> int:
        return sum(item.quantity for item in self.items)


class TemporaryStorageItem(BaseBusiness):
    """Producto dentro de una recepción.

    `product_id` es referencial (apunta al catálogo si el producto existía).
    `product_name`/`barcode` son una instantánea para no depender del catálogo
    y permitir productos temporales que no existen en el inventario.
    """

    __tablename__ = "temporary_storage_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    storage_id: Mapped[int] = mapped_column(
        ForeignKey("temporary_storage.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), index=True)
    barcode: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    storage: Mapped["TemporaryStorage"] = relationship(back_populates="items")

    @property
    def pending(self) -> int:
        return max(self.quantity - self.returned_qty, 0)

    @property
    def completed(self) -> bool:
        return self.returned_qty >= self.quantity


class TemporaryStorageHistory(BaseBusiness):
    """Trazabilidad completa del módulo (recepción, edición, cambio de
    ubicación, cambio de fecha límite, devolución/retiro).

    Tabla propia e independiente de audit_logs del inventario.
    """

    __tablename__ = "temporary_storage_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    storage_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ==============================================================================
# MÓDULO: GESTIÓN DE PROSPECTOS (CRM comercial interno)
#
# Independiente del inventario y del CRM de cartera externo. Gestiona el ciclo
# comercial de un prospecto: contacto -> citas -> seguimiento -> cierre -> cliente.
# Todas las tablas son de NEGOCIO (BaseBusiness) con tenant_id.
# ==============================================================================

# Estados del prospecto (los del spec de la ficha).
PROSPECT_STATUSES = (
    "nuevo",
    "contactado",
    "interesado",
    "pendiente_cita",
    "visitado",
    "cliente_potencial",
    "cliente_convertido",
    "no_interesado",
)

# Estados comerciales del cierre (actualización automática del prospecto).
PROSPECT_COMMERCIAL_STATUSES = (
    "nuevo",
    "contactado",
    "interesado",
    "calificado",
    "en_negociacion",
    "propuesta_enviada",
    "pendiente_respuesta",
    "cliente_convertido",
    "no_interesado",
)

PROSPECT_STATUS_LABELS = {
    "nuevo": "Nuevo",
    "contactado": "Contactado",
    "interesado": "Interesado",
    "pendiente_cita": "Pendiente de cita",
    "visitado": "Visitado",
    "cliente_potencial": "Cliente potencial",
    "cliente_convertido": "Cliente convertido",
    "no_interesado": "No interesado",
}


class SalesPipeline(BaseBusiness):
    """Etapa del embudo/kanban (configurable por cliente)."""

    __tablename__ = "sales_pipeline"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_pipeline_tenant_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Prospect(BaseBusiness):
    """Ficha completa del prospecto."""

    __tablename__ = "prospects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    knows_brand: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Notas rápidas de la ficha (máx. 500); el historial detallado va en prospect_notes.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="nuevo", index=True)
    commercial_status: Mapped[str] = mapped_column(String(30), default="nuevo", index=True)
    # Calificación 1..5 (estrellas).
    rating: Mapped[int] = mapped_column(Integer, default=3)
    stage_slug: Mapped[str] = mapped_column(String(40), default="nuevo", index=True)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Evaluación comercial de la oportunidad.
    has_budget: Mapped[str | None] = mapped_column(String(20), nullable=True)  # si|no|desconocido
    is_decision_maker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    close_probability: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    # Valor de oportunidad.
    monthly_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    setup_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    # Interés / cierre.
    interested_products: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON ["inventario",...]
    lost_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lost_reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Conversión.
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    converted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    notes_rel: Mapped[list["ProspectNote"]] = relationship(
        back_populates="prospect", cascade="all, delete-orphan"
    )
    activities: Mapped[list["ProspectActivity"]] = relationship(
        back_populates="prospect", cascade="all, delete-orphan"
    )

    @property
    def opportunity_value(self) -> float:
        return float(self.monthly_value or 0) + float(self.setup_value or 0)

    @property
    def weighted_value(self) -> float:
        return self.opportunity_value * (self.close_probability or 0) / 100.0


class ProspectNote(BaseBusiness):
    """Nota con fecha/usuario (historial de notas del prospecto)."""

    __tablename__ = "prospect_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(500))
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    prospect: Mapped["Prospect"] = relationship(back_populates="notes_rel")


class ProspectActivity(BaseBusiness):
    """Seguimiento (llamada, WhatsApp, correo, visita, videollamada, otro)."""

    __tablename__ = "prospect_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), index=True)  # llamada|whatsapp|correo|visita|videollamada|otro
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente|realizada|cancelada
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    prospect: Mapped["Prospect"] = relationship(back_populates="activities")


class ProspectHistory(BaseBusiness):
    """Línea de tiempo cronológica del prospecto."""

    __tablename__ = "prospect_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProspectFile(BaseBusiness):
    """Evidencia/adjunto del prospecto (imágenes, PDF, documentos)."""

    __tablename__ = "prospect_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProspectSignature(BaseBusiness):
    """Firma digital (cliente / representante) guardada como imagen."""

    __tablename__ = "prospect_signatures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # cliente|representante
    path: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Appointment(BaseBusiness):
    """Cita comercial del prospecto."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="programada", index=True)
    # programada|confirmada|en_proceso|completada|cancelada|reagendada
    reminder_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 15..1440
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    reminders: Mapped[list["AppointmentReminder"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )


class AppointmentReminder(BaseBusiness):
    """Recordatorio programado de una cita (una fila por tiempo configurado)."""

    __tablename__ = "appointment_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    minutes_before: Mapped[int] = mapped_column(Integer)  # 15,30,60,120,240,480,1440
    fire_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    appointment: Mapped["Appointment"] = relationship(back_populates="reminders")


class AppointmentClosure(BaseBusiness):
    """Formulario obligatorio de cierre de visita."""

    __tablename__ = "appointment_closures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), index=True
    )
    prospect_id: Mapped[int] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    visit_date: Mapped[date] = mapped_column(Date)
    arrival_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    departure_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    total_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(40))
    result_detail: Mapped[str] = mapped_column(String(1000))
    markers: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON lista
    interest_level: Mapped[int] = mapped_column(Integer, default=3)
    demo_done: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest_products: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON lista
    delivered_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON lista
    commercial_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Evaluación comercial del prospecto durante la visita.
    has_budget: Mapped[str | None] = mapped_column(String(20), nullable=True)  # si|no|desconocido
    is_decision_maker: Mapped[str | None] = mapped_column(String(30), nullable=True)
    close_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0..100
    # Valor de oportunidad detectado en la visita.
    monthly_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    setup_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Motivos de no compra (cuando aplica).
    lost_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lost_reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(BaseBusiness):
    """Notificación interna genérica (campana) para los usuarios del cliente."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Referencias opcionales para navegar al origen.
    entity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# =====================================================================
# CAPTACIÓN PÚBLICA DE PROSPECTOS (jornadas, campañas, ruleta, premios)
# =====================================================================

# Orígenes de captación admitidos.
CAPTURE_ORIGINS = ("captacion_presencial",)
CAPTURE_ORIGIN_LABELS = {"captacion_presencial": "Captación Presencial"}

# Estados de una jornada de captación.
CAPTURE_SESSION_STATUSES = ("abierta", "cerrada")
# Estados de una campaña.
CAPTURE_CAMPAIGN_STATUSES = ("borrador", "activa", "pausada", "finalizada")
# Acciones (configurables) cuando el teléfono ya existe.
DUPLICATE_ACTIONS = ("actualizar", "nueva_interaccion", "bloquear")


class CaptureCampaign(BaseBusiness):
    """Campaña comercial (evento, promoción, ruta) a la que se asocian captaciones."""

    __tablename__ = "capture_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # borrador|activa|pausada|finalizada
    status: Mapped[str] = mapped_column(String(20), default="activa", index=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CapturePrize(BaseBusiness):
    """Premio de la ruleta promocional (probabilidad, color, stock, vigencia)."""

    __tablename__ = "capture_prizes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Peso relativo para el sorteo ponderado (no hace falta que sume 100).
    probability: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # stock disponible; None = ilimitado.
    stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # fechas de vigencia opcionales.
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # "sin premio" (cara de cortesía, no descuenta stock ni cuenta como entregado).
    is_no_prize: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PublicCaptureSession(BaseBusiness):
    """Jornada de captación abierta por un vendedor durante un evento."""

    __tablename__ = "public_capture_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # vendedor responsable de la jornada (usuario del tenant).
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    campaign_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    location: Mapped[str | None] = mapped_column(String(180), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    # abierta|cerrada
    status: Mapped[str] = mapped_column(String(20), default="abierta", index=True)
    # token efímero que usa la tablet para registrar sin exponer el JWT del usuario.
    session_token: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CaptureEntry(BaseBusiness):
    """Participación: un prospecto captado en una jornada, con su premio obtenido."""

    __tablename__ = "capture_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    campaign_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    prize_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prize_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    vendor_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # prospecto creado/actualizado por esta participación.
    prospect_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prospect_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(180), nullable=True)
    origin: Mapped[str] = mapped_column(String(40), default="captacion_presencial")
    # cómo se resolvió un posible duplicado: nuevo|actualizado|nueva_interaccion
    duplicate_action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CaptureHistory(BaseBusiness):
    """Bitácora del módulo de captación (inicio/fin de jornada, premios, cambios)."""

    __tablename__ = "capture_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CaptureConfig(BaseBusiness):
    """Configuración administrable del módulo (comportamiento global del cliente)."""

    __tablename__ = "capture_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Acción ante teléfono duplicado: actualizar|nueva_interaccion|bloquear
    duplicate_action: Mapped[str] = mapped_column(String(30), default="actualizar")
    # Premio por defecto cuando la ruleta no tiene premios disponibles.
    no_prize_message: Mapped[str] = mapped_column(String(180), default="Gracias por participar")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )