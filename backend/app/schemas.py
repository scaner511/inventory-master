"""Esquemas Pydantic (validación de entrada/salida de la API)."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator


def _utc_iso(dt: datetime | None) -> str | None:
    """Serializa datetimes naive (guardados en UTC) con sufijo Z.

    El frontend envía las citas en UTC; sin la 'Z' el navegador las
    interpretaría como hora local y desplazaría las citas.
    """
    if dt is None:
        return None
    return dt.isoformat() + "Z" if dt.tzinfo is None else dt.isoformat()


# Módulos que un administrador puede habilitar/deshabilitar por usuario.
ALLOWED_MODULES = ("capture", "calendar", "temporary_storage", "prospects")


def modules_from_raw(raw: str | None) -> list[str]:
    """Convierte el valor almacenado (JSON o separado por comas) en lista."""
    import json

    if not raw:
        return list(ALLOWED_MODULES)
    raw = raw.strip()
    if raw.startswith("["):
        try:
            values = json.loads(raw)
            return [str(v) for v in values if str(v) in ALLOWED_MODULES]
        except Exception:
            return list(ALLOWED_MODULES)
    return [v for v in (p.strip() for p in raw.split(",")) if v in ALLOWED_MODULES]


def modules_to_raw(values: list[str] | None) -> str | None:
    """Serializa la lista de módulos para guardarla en la columna."""
    import json

    if values is None:
        return None
    clean = [v for v in values if v in ALLOWED_MODULES]
    return json.dumps(clean)

# ===================== AUTH =====================


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int | None = None
    tenant_name: str | None = None
    username: str
    email: str | None = None
    role: str
    is_active: bool
    must_change_password: bool = False
    accepted_terms: bool = False
    accepted_terms_date: datetime | None = None
    created_at: datetime
    last_login: datetime | None = None
    # Suscripción: vigencia del usuario y días restantes (solo los clientes;
    # el Super Admin va a None).
    subscription_expires_at: date | None = None
    subscription_days_left: int | None = None
    # Módulos habilitados para este usuario (lista). Admin/superadmin = todos.
    modules: list[str] = Field(default_factory=list)
    # Enlace fijo de captación (solo se incluye en el listado de usuarios).
    capture_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def user_out(user) -> UserOut:
    """Construye UserOut rellenando el nombre del tenant si existe."""
    out = UserOut.model_validate(user)
    out.modules = list(ALLOWED_MODULES) if user.role in ("admin", "superadmin") else modules_from_raw(user.modules)
    if user.tenant_id is not None:
        tenant = getattr(user, "tenant", None)
        out.tenant_name = tenant.name if tenant is not None else None
    if user.subscription_expires_at is not None:
        out.subscription_days_left = (user.subscription_expires_at - date.today()).days
    return out


class ForgotPasswordRequest(BaseModel):
    username: str
    answer: str


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ===================== USERS =====================


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")
    security_question: str | None = None
    security_answer: str | None = None
    # Módulos habilitados (solo aplica a rol "user"). None = todos.
    modules: list[str] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None
    # Módulos habilitados (solo aplica a rol "user"). None = no modificar.
    modules: list[str] | None = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class AdminResetPassword(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class SubscriptionRenew(BaseModel):
    """Extiende la suscripción de un usuario N días (lo registra el Super Admin
    cuando el cliente paga)."""
    days: int = Field(default=30, ge=1, le=3650)


# ===================== TENANTS (multi-proveedor) =====================


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    admin_username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    admin_password: str | None = Field(default=None, min_length=6, max_length=128)
    admin_email: EmailStr | None = None
    # Límite de usuarios de este proveedor (lo define el Super Admin). Si es
    # NULL, se usa MAX_USERS_PER_TENANT (global). Debe ser >= 1 porque el
    # administrador siempre ocupa uno.
    max_users: int | None = Field(default=None, ge=1)

    @field_validator("admin_email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    max_users: int | None = Field(default=None, ge=1)
    # Para poder "limpiar" el límite de un proveedor (volver al global).
    clear_max_users: bool | None = None


class TenantReset(BaseModel):
    """Petición para restablecer un cliente a estado de fábrica.

    Si preserve_user_id es None, se conserva el administrador de menor ID
    (el primero creado)."""
    preserve_user_id: int | None = None


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    max_users: int | None = None
    is_active: bool
    created_at: datetime
    # Licencia del cliente (visible solo para el Super Admin).
    subscription_expires_at: date | None = None
    subscription_days_left: int | None = None
    users_count: int = 0


class TenantUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")
    security_question: str | None = None
    security_answer: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


# ===================== PRODUCTS =====================


class LocationEntry(BaseModel):
    """Cantidad disponible de un producto en una ubicación concreta."""

    location: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=0)


class ProductBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    stock: int = Field(default=0, ge=0)
    purchase_price: float = Field(default=0, ge=0)
    sale_price: float = Field(default=0, ge=0)
    location1: str | None = None
    location2: str | None = None
    location3: str | None = None
    # Estado físico: "buen_estado" | "incompleto" | "usado"
    condition: str = Field(default="buen_estado", max_length=30)
    # Desglose por ubicación (con cantidades). Si se envía, el stock total se
    # recalcula como la suma de estas filas.
    locations: list[LocationEntry] = []


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    stock: int | None = Field(default=None, ge=0)
    purchase_price: float | None = Field(default=None, ge=0)
    sale_price: float | None = Field(default=None, ge=0)
    location1: str | None = None
    location2: str | None = None
    location3: str | None = None
    condition: str | None = Field(default=None, max_length=30)
    locations: list[LocationEntry] | None = None


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    # Estado calculado para la UI
    status: str | None = None
    location: str | None = None


# ===================== LOANS =====================


class LoanItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)
    # Ubicación de dónde sale este ítem (stock por ubicación).
    location_out: str | None = None


class LoanCreate(BaseModel):
    seller: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    items: list[LoanItemCreate] = Field(min_length=1)
    due_date: date
    note: str | None = None


class LoanItemUpdate(BaseModel):
    id: int | None = None
    product_id: int
    quantity: int = Field(ge=1)
    location_out: str | None = None


class LoanReturn(BaseModel):
    item_id: int
    returned_qty: int = Field(gt=0)
    # Ubicación donde se guarda lo devuelto. Si se omite, vuelve a la misma
    # ubicación de la que salió al prestarse.
    location_in: str | None = None


class LoanUpdate(BaseModel):
    seller: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = None
    due_date: date | None = None
    note: str | None = None
    items: list[LoanItemUpdate] | None = None


class LoanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = None
    product_name: str
    quantity: int
    returned_qty: int
    location_out: str | None = None
    pending: int
    completed: bool


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller: str
    phone: str | None = None
    items: list[LoanItemOut] = []
    loan_date: datetime
    due_date: date
    note: str | None = None
    pending: int
    completed: bool
    overdue: bool
    status: str | None = None


# ===================== DASHBOARD =====================


class DashboardOut(BaseModel):
    total_products: int
    total_units: int
    active_loans: int
    overdue_loans: int
    low_stock_products: int
    capital_invested: float
    potential_income: float
    low_stock_list: list[ProductOut] = []
    overdue_loans_list: list[LoanOut] = []
    top_products: list[dict] = []
    recent_loans: list[LoanOut] = []
    loans_last_7_days: list[dict] = []
    # Stock total agrupado por ubicación (feature stock por ubicación).
    stock_by_location: list[dict] = []


# ===================== RECEPCIÓN DE MERCANCÍA (depósito temporal) =====================


class TsLocationBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    is_active: bool = True


class TsLocationCreate(TsLocationBase):
    pass


class TsLocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    is_active: bool | None = None


class TsLocationOut(TsLocationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class TsItemCreate(BaseModel):
    product_id: int | None = None
    product_name: str = Field(min_length=1, max_length=255)
    barcode: str | None = None
    quantity: int = Field(default=1, ge=1)
    note: str | None = None


class TsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = None
    product_name: str
    barcode: str | None = None
    quantity: int
    returned_qty: int
    note: str | None = None
    pending: int = 0
    completed: bool = False


class TsCreate(BaseModel):
    entry_date: date | None = None
    deadline_date: date
    party_name: str = Field(min_length=1, max_length=150)
    party_company: str | None = None
    party_phone: str | None = None
    party_email: str | None = None
    reference_document: str | None = None
    location_id: int | None = None
    note: str | None = None
    items: list[TsItemCreate] = Field(min_length=1)


class TsUpdate(BaseModel):
    entry_date: date | None = None
    deadline_date: date | None = None
    party_name: str | None = Field(default=None, min_length=1, max_length=150)
    party_company: str | None = None
    party_phone: str | None = None
    party_email: str | None = None
    reference_document: str | None = None
    location_id: int | None = None
    note: str | None = None
    status: str | None = Field(default=None, pattern="^(recibido|almacenado)$")
    items: list[TsItemCreate] | None = None


class TsExit(BaseModel):
    """Salida de la mercancía (flujo único: devuelto o retirado)."""

    exit_type: str = Field(pattern="^(devuelto|retirado)$")
    responsible: str | None = None
    document: str | None = None
    note: str | None = None


class TsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    short_code: str
    entry_date: date
    deadline_date: date
    party_name: str
    party_company: str | None = None
    party_phone: str | None = None
    party_email: str | None = None
    reference_document: str | None = None
    received_by: int | None = None
    location_id: int | None = None
    location_name: str | None = None
    note: str | None = None
    status: str
    exit_date: datetime | None = None
    exit_type: str | None = None
    exit_responsible: str | None = None
    exit_document: str | None = None
    exit_note: str | None = None
    items: list[TsItemOut] = []
    days_left: int = 0
    computed_status: str = "recibido"
    total_units: int = 0


class TsHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    storage_id: int | None = None
    timestamp: datetime
    user_id: int | None = None
    action: str
    detail: str | None = None


class TsDashboardOut(BaseModel):
    active_receptions: int
    stored_products: int
    stored_units: int
    expiring_soon: int
    expired: int
    returned_this_month: int
    by_party: list[dict] = []
    by_location: list[dict] = []


# ===================== GESTIÓN DE PROSPECTOS =====================


class PipelineStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    position: int
    color: str | None = None
    is_terminal: bool = False
    is_won: bool = False
    is_lost: bool = False


class ProspectNoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ProspectNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    created_by: int | None = None
    created_at: datetime


class ProspectActivityCreate(BaseModel):
    kind: str = Field(pattern="^(llamada|whatsapp|correo|visita|videollamada|otro)$")
    scheduled_at: datetime | None = None
    done_at: datetime | None = None
    observation: str | None = None
    result: str | None = None
    status: str = Field(default="pendiente", pattern="^(pendiente|realizada|cancelada)$")
    user_id: int | None = None


class ProspectActivityUpdate(BaseModel):
    kind: str | None = Field(default=None, pattern="^(llamada|whatsapp|correo|visita|videollamada|otro)$")
    scheduled_at: datetime | None = None
    done_at: datetime | None = None
    observation: str | None = None
    result: str | None = None
    status: str | None = Field(default=None, pattern="^(pendiente|realizada|cancelada)$")
    user_id: int | None = None


class ProspectActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prospect_id: int
    kind: str
    scheduled_at: datetime | None = None
    done_at: datetime | None = None
    observation: str | None = None
    result: str | None = None
    status: str
    user_id: int | None = None
    created_at: datetime


class ProspectHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    user_id: int | None = None
    action: str
    detail: str | None = None


class ProspectBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    marital_status: str | None = Field(default=None, max_length=30)
    knows_brand: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    status: str | None = None
    commercial_status: str | None = None
    rating: int = Field(default=3, ge=1, le=5)
    stage_slug: str | None = None
    owner_id: int | None = None
    has_budget: str | None = Field(default=None, pattern="^(si|no|desconocido)$")
    is_decision_maker: str | None = Field(default=None, pattern="^(si|no|debe_consultar)$")
    close_probability: int = Field(default=0, ge=0, le=100)
    monthly_value: float = 0
    setup_value: float = 0
    interested_products: list[str] = []
    lost_reason: str | None = None
    lost_reason_detail: str | None = None
    summary: str | None = None
    next_followup_at: datetime | None = None


class ProspectCreate(ProspectBase):
    pass


class ProspectUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    marital_status: str | None = Field(default=None, max_length=30)
    knows_brand: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    status: str | None = None
    commercial_status: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    stage_slug: str | None = None
    owner_id: int | None = None
    has_budget: str | None = Field(default=None, pattern="^(si|no|desconocido)$")
    is_decision_maker: str | None = Field(default=None, pattern="^(si|no|debe_consultar)$")
    close_probability: int | None = Field(default=None, ge=0, le=100)
    monthly_value: float | None = None
    setup_value: float | None = None
    interested_products: list[str] | None = None
    lost_reason: str | None = None
    lost_reason_detail: str | None = None
    summary: str | None = None
    next_followup_at: datetime | None = None


class ProspectOut(ProspectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int | None = None
    created_by: int | None = None
    converted_at: datetime | None = None
    converted_by: int | None = None
    created_at: datetime
    updated_at: datetime
    opportunity_value: float = 0
    weighted_value: float = 0


class ProspectMove(BaseModel):
    stage_slug: str = Field(min_length=1, max_length=40)
    position: int | None = None


class ConvertProspectIn(BaseModel):
    note: str | None = None


class OpportunitySummary(BaseModel):
    total_value: float
    weighted_value: float
    pipeline_by_stage: list[dict] = []
    by_status: list[dict] = []


# ===================== CITAS, RECORDATORIOS Y NOTIFICACIONES =====================

APPOINTMENT_STATUSES = "programada|confirmada|en_proceso|completada|cancelada|reagendada"


class AppointmentReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    minutes_before: int
    fire_at: datetime
    sent: bool
    sent_at: datetime | None = None

    @field_serializer("fire_at", "sent_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class AppointmentCreate(BaseModel):
    prospect_id: int
    start_at: datetime
    end_at: datetime | None = None
    user_id: int | None = None
    address: str | None = None
    phone: str | None = None
    observation: str | None = None
    status: str | None = Field(default=None, pattern=f"^({APPOINTMENT_STATUSES})$")
    reminder_minutes: list[int] = []
    reminder_minutes_single: int | None = Field(default=None, ge=1, le=1440)


class AppointmentUpdate(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    user_id: int | None = None
    address: str | None = None
    phone: str | None = None
    observation: str | None = None
    status: str | None = Field(default=None, pattern=f"^({APPOINTMENT_STATUSES})$")
    reminder_minutes: list[int] | None = None
    reschedule: bool = False


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prospect_id: int
    prospect_name: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    user_id: int | None = None
    address: str | None = None
    phone: str | None = None
    observation: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("start_at", "end_at", "created_at", "updated_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str | None = None
    entity: str | None = None
    entity_id: int | None = None
    read: bool
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


# ===================== CIERRE DE VISITAS =====================


class AppointmentClosureCreate(BaseModel):
    visit_date: date | None = None
    arrival_time: str | None = Field(default=None, max_length=8)
    departure_time: str | None = Field(default=None, max_length=8)
    result: str = Field(min_length=1, max_length=40)
    result_detail: str = Field(min_length=1, max_length=1000)
    markers: list[str] = []
    interest_level: int = Field(default=3, ge=1, le=5)
    demo_done: bool = False
    demo_description: str | None = None
    interest_products: list[str] = []
    delivered_info: list[str] = []
    commercial_status: str | None = None
    next_followup_at: datetime | None = None
    next_followup_kind: str | None = Field(default=None, pattern="^(llamada|whatsapp|correo|visita|videollamada|otro)$")
    next_followup_observation: str | None = None
    convert: bool = False
    # Evaluación comercial.
    has_budget: str | None = Field(default=None, pattern="^(si|no|desconocido)$")
    is_decision_maker: str | None = Field(default=None, pattern="^(si|no|debe_consultar)$")
    close_probability: int | None = Field(default=None, ge=0, le=100)
    # Valor de oportunidad.
    monthly_value: float | None = None
    setup_value: float | None = None
    # Motivos de no compra.
    lost_reason: str | None = Field(default=None, max_length=40)
    lost_reason_detail: str | None = None


class AppointmentClosureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_id: int
    prospect_id: int
    visit_date: date
    arrival_time: str | None = None
    departure_time: str | None = None
    total_minutes: int | None = None
    user_id: int | None = None
    result: str
    result_detail: str
    markers: list[str] = []
    interest_level: int
    demo_done: bool
    demo_description: str | None = None
    interest_products: list[str] = []
    delivered_info: list[str] = []
    commercial_status: str | None = None
    has_budget: str | None = None
    is_decision_maker: str | None = None
    close_probability: int | None = None
    monthly_value: float | None = None
    setup_value: float | None = None
    lost_reason: str | None = None
    lost_reason_detail: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


# ===================== EVIDENCIAS Y FIRMAS =====================


class ProspectFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prospect_id: int
    filename: str
    content_type: str | None = None
    size: int | None = None
    created_by: int | None = None
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class ProspectSignatureCreate(BaseModel):
    role: str = Field(pattern="^(cliente|representante)$")
    # Imagen de la firma en base64 data URL (data:image/png;base64,...).
    image_data: str = Field(min_length=20)


class ProspectSignatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prospect_id: int
    role: str
    created_by: int | None = None
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class CommercialDashboardOut(BaseModel):
    total_prospects: int
    converted: int
    conversion_rate: float
    active_pipeline_value: float
    weighted_value: float
    appointments_today: int
    appointments_week: int
    pending_followups: int
    by_status: list[dict] = []
    by_stage: list[dict] = []
    by_month: list[dict] = []
    top_products: list[dict] = []
    lost_reasons: list[dict] = []


# ===================== CAPTACIÓN PÚBLICA DE PROSPECTOS =====================


class CaptureCampaignBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = Field(default="activa", pattern="^(borrador|activa|pausada|finalizada)$")
    observations: str | None = None


class CaptureCampaignCreate(CaptureCampaignBase):
    pass


class CaptureCampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = Field(default=None, pattern="^(borrador|activa|pausada|finalizada)$")
    observations: str | None = None


class CaptureCampaignOut(CaptureCampaignBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class CapturePrizeBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    probability: int = Field(default=1, ge=0, le=10000)
    is_active: bool = True
    stock: int | None = Field(default=None, ge=0)
    valid_from: date | None = None
    valid_until: date | None = None
    is_no_prize: bool = False


class CapturePrizeCreate(CapturePrizeBase):
    pass


class CapturePrizeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(default=None, max_length=20)
    probability: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None
    stock: int | None = Field(default=None, ge=0)
    valid_from: date | None = None
    valid_until: date | None = None
    is_no_prize: bool | None = None


class CapturePrizeOut(CapturePrizeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class CaptureConfigOut(BaseModel):
    duplicate_action: str
    no_prize_message: str


class CaptureConfigUpdate(BaseModel):
    duplicate_action: str | None = Field(
        default=None, pattern="^(actualizar|nueva_interaccion|bloquear)$"
    )
    no_prize_message: str | None = Field(default=None, max_length=180)


class CaptureSessionCreate(BaseModel):
    user_id: int | None = None
    vendor_name: str | None = Field(default=None, max_length=80)
    campaign_id: int | None = None
    location: str | None = Field(default=None, max_length=180)
    observations: str | None = None


class CaptureSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    user_name: str | None = None
    campaign_id: int | None = None
    campaign_name: str | None = None
    location: str | None = None
    observations: str | None = None
    status: str
    started_at: datetime
    closed_at: datetime | None = None

    @field_serializer("started_at", "closed_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class CaptureSessionStartOut(BaseModel):
    """Respuesta al iniciar jornada: incluye el token efímero para la tablet."""

    session: CaptureSessionOut
    session_token: str


class CapturePrizeWon(BaseModel):
    id: int | None = None
    name: str
    color: str | None = None
    is_no_prize: bool = False


class CaptureSpinOut(BaseModel):
    """Resultado del giro de ruleta (público)."""

    prize: CapturePrizeWon
    segments: list[dict] = []
    wheel_index: int = 0


class CapturePublicInfoOut(BaseModel):
    """Datos que ve la tablet al abrir la pantalla de captación."""

    session: CaptureSessionOut
    campaign: CaptureCampaignOut | None = None
    vendor_name: str | None = None
    location: str | None = None
    duplicate_action: str
    no_prize_message: str


class CaptureDuplicateCheckIn(BaseModel):
    phone: str = Field(min_length=3, max_length=40)


class CaptureDuplicateCheckOut(BaseModel):
    exists: bool
    prospect_id: int | None = None
    prospect_name: str | None = None
    action: str  # acción que aplicará el sistema según config


class CaptureRegisterIn(BaseModel):
    """Registro del participante desde la tablet."""

    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=3, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    marital_status: str | None = Field(default=None, max_length=30)
    knows_brand: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    prize_id: int | None = None
    # Para duplicados: "actualizar" | "nueva_interaccion" (según elija la tablet).
    duplicate_choice: str | None = Field(
        default=None, pattern="^(actualizar|nueva_interaccion|bloquear)$"
    )


class CaptureRegisterOut(BaseModel):
    prospect_id: int
    prospect_name: str
    created: bool
    duplicate_action: str | None = None
    prize_name: str | None = None


class CaptureEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None = None
    campaign_id: int | None = None
    campaign_name: str | None = None
    prize_name: str | None = None
    vendor_id: int | None = None
    vendor_name: str | None = None
    prospect_id: int | None = None
    prospect_name: str | None = None
    phone: str | None = None
    location: str | None = None
    origin: str
    duplicate_action: str | None = None
    entry_date: date
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class CaptureCaptureHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int | None = None
    action: str
    detail: str | None = None
    user_id: int | None = None
    user_name: str | None = None
    ip_address: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, dt: datetime | None) -> str | None:
        return _utc_iso(dt)


class CaptureDashboardOut(BaseModel):
    captured_today: int
    captured_month: int
    total_entries: int
    prizes_given: int
    sessions_count: int
    converted: int
    conversion_rate: float
    by_campaign: list[dict] = []
    by_vendor: list[dict] = []
    by_day: list[dict] = []
    by_prize: list[dict] = []
    top_campaigns: list[dict] = []
    top_vendors: list[dict] = []
