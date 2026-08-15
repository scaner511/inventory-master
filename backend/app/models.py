"""Modelos ORM de la base de datos."""
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

from app.database import Base


class Tenant(Base):
    """Proveedor (tenant). Aísla inventario, productos y movimientos."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    products: Mapped[list["Product"]] = relationship(back_populates="tenant")
    loans: Mapped[list["Loan"]] = relationship(back_populates="tenant")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="tenant")


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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant | None"] = relationship(back_populates="users")
    loans_created: Mapped[list["Loan"]] = relationship(back_populates="creator")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_products_tenant_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    purchase_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sale_price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    location1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="products")


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    seller: Mapped[str] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)
    loan_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date] = mapped_column(Date)
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="loans")
    creator: Mapped["User"] = relationship(back_populates="loans_created")

    @property
    def pending(self) -> int:
        return max(self.quantity - self.returned_qty, 0)

    @property
    def completed(self) -> bool:
        return self.returned_qty >= self.quantity

    @property
    def overdue(self) -> bool:
        return not self.completed and self.due_date < date.today()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="audit_logs")


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_settings_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)


class License(Base):
    __tablename__ = "licenses"
    __table_args__ = (CheckConstraint("id = 1", name="ck_license_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_key: Mapped[str | None] = mapped_column(String(20), nullable=True)


class UsedLicenseKey(Base):
    __tablename__ = "used_license_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_value: Mapped[str] = mapped_column(String(20), unique=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
