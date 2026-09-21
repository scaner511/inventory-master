"""Esquemas Pydantic (validación de entrada/salida de la API)."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def user_out(user) -> UserOut:
    """Construye UserOut rellenando el nombre del tenant si existe."""
    out = UserOut.model_validate(user)
    if user.tenant_id is not None:
        tenant = getattr(user, "tenant", None)
        out.tenant_name = tenant.name if tenant is not None else None
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

    @field_validator("email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None

    @field_validator("email", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v


class AdminResetPassword(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


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
    # Precio mensual USD de la licencia de este proveedor (opcional). Si es
    # NULL, se usa PAYPAL_PRICE_USD (global).
    price_usd: float | None = Field(default=None, ge=0)

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
    price_usd: float | None = Field(default=None, ge=0)
    # Vuelve el precio al global (PAYPAL_PRICE_USD).
    clear_price_usd: bool | None = None


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    max_users: int | None = None
    price_usd: float | None = None
    is_active: bool
    created_at: datetime
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


class LoanCreate(BaseModel):
    seller: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    product_id: int
    quantity: int = Field(ge=1)
    due_date: date
    note: str | None = None
    # Ubicación de dónde sale la mercancía (stock por ubicación).
    location_out: str | None = None


class LoanReturn(BaseModel):
    returned_qty: int = Field(gt=0)
    # Ubicación donde se guarda lo devuelto. Si se omite, vuelve a la misma
    # ubicación de la que salió al prestarse.
    location_in: str | None = None


class LoanUpdate(BaseModel):
    seller: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = None
    product_id: int | None = None
    quantity: int | None = Field(default=None, ge=1)
    due_date: date | None = None
    note: str | None = None
    location_out: str | None = None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller: str
    phone: str | None = None
    product_id: int | None = None
    product_name: str
    quantity: int
    returned_qty: int
    loan_date: datetime
    due_date: date
    note: str | None = None
    location_out: str | None = None
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
