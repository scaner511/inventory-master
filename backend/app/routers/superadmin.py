"""Panel de Super Admin: clientes (tenants) y gestión global de usuarios.

Solo el Super Admin (role=superadmin) puede acceder a estas rutas.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_superadmin
from app.models import (
    AuditLog,
    DriveConnection,
    Loan,
    LoanItem,
    Product,
    ProductStockLocation,
    Setting,
    Tenant,
    User,
)
from app.schemas import (
    AdminResetPassword,
    SubscriptionRenew,
    TenantCreate,
    TenantOut,
    TenantReset,
    TenantUpdate,
    TenantUserCreate,
    UserOut,
    UserUpdate,
    user_out,
)
from app.utils.audit import record_audit
from app.utils.security import hash_password

router = APIRouter(
    prefix="/api/superadmin",
    tags=["superadmin"],
    dependencies=[Depends(require_superadmin)],
)


def _tenant_users_count(db: Session, tenant_id: int) -> int:
    return (
        db.query(func.count(User.id))
        .filter(User.tenant_id == tenant_id, User.role.in_(("admin", "user")))
        .scalar()
        or 0
    )


def _tenant_max_users(tenant: Tenant) -> int:
    """Límite de usuarios efectivo: el del cliente o, si no lo definió el
    Super Admin, el valor global."""
    return tenant.max_users or settings.max_users_per_tenant


def _ensure_user_quota(db: Session, tenant_id: int) -> None:
    tenant = db.get(Tenant, tenant_id)
    limit = _tenant_max_users(tenant)
    if _tenant_users_count(db, tenant_id) >= limit:
        raise HTTPException(
            status_code=400,
            detail=f"El cliente ya alcanzó el máximo de {limit} usuarios",
        )


def _get_tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return tenant


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _subscription_days_left(tenant: Tenant) -> int | None:
    if tenant.subscription_expires_at is None:
        return None
    return (tenant.subscription_expires_at - date.today()).days


def _renew_tenant(db: Session, tenant: Tenant, days: int, actor: User) -> date:
    """Renueva la licencia del cliente y la hereda a todos sus usuarios.

    Base: el vencimiento actual si aún no venció; si ya venció, se cuenta
    desde hoy. Devuelve la nueva fecha de vencimiento.
    """
    today = date.today()
    base = tenant.subscription_expires_at or today
    if base < today:
        base = today
    expire = base + timedelta(days=days)
    tenant.subscription_expires_at = expire
    db.query(User).filter(User.tenant_id == tenant.id).update(
        {"subscription_expires_at": expire}, synchronize_session=False
    )
    record_audit(
        db,
        "SUBSCRIPTION_RENEWED",
        actor.id,
        tenant_id=tenant.id,
        detail=(
            f"Licencia de '{tenant.name}' renovada {days} días "
            f"(vence el {expire.isoformat()})"
        ),
    )
    return expire


def _ensure_admin_remains(db: Session, user: User) -> None:
    """Evita dejar a un cliente sin ningún administrador."""
    if user.role != "admin" or user.tenant_id is None:
        return
    others = (
        db.query(func.count(User.id))
        .filter(
            User.tenant_id == user.tenant_id,
            User.role == "admin",
            User.id != user.id,
            User.is_active.is_(True),
        )
        .scalar()
        or 0
    )
    if others == 0:
        raise HTTPException(
            status_code=400,
            detail="No se puede dejar al cliente sin ningún administrador",
        )


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db)):
    tenants = db.query(Tenant).order_by(Tenant.name).all()
    result = []
    for t in tenants:
        out = TenantOut.model_validate(t)
        out.users_count = _tenant_users_count(db, t.id)
        out.subscription_days_left = _subscription_days_left(t)
        result.append(out)
    return result


@router.post("/tenants", response_model=TenantOut, status_code=201)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)):
    if db.query(Tenant).filter(Tenant.name == data.name).first():
        raise HTTPException(status_code=400, detail="Ya existe un cliente con ese nombre")
    if db.query(User).filter(User.username == data.admin_username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario del administrador ya existe")

    start = date.today() + timedelta(days=settings.subscription_days)
    tenant = Tenant(name=data.name, max_users=data.max_users, subscription_expires_at=start)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    password = data.admin_password or settings.default_generic_password
    db.add(
        User(
            username=data.admin_username,
            email=data.admin_email,
            password_hash=hash_password(password),
            role="admin",
            tenant_id=tenant.id,
            must_change_password=True,
            subscription_expires_at=start,
        )
    )
    db.commit()

    out = TenantOut.model_validate(tenant)
    out.users_count = _tenant_users_count(db, tenant.id)
    out.subscription_days_left = _subscription_days_left(tenant)
    return out


@router.put("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, data: TenantUpdate, db: Session = Depends(get_db)):
    tenant = _get_tenant(db, tenant_id)
    if data.name is not None:
        if data.name != tenant.name and db.query(Tenant).filter(Tenant.name == data.name).first():
            raise HTTPException(status_code=400, detail="Ya existe un cliente con ese nombre")
        tenant.name = data.name
    if data.is_active is not None:
        tenant.is_active = data.is_active
    if data.clear_max_users:
        # Volver al límite global (NULL).
        if tenant.max_users and _tenant_users_count(db, tenant_id) > settings.max_users_per_tenant:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede quitar el límite: el cliente tiene {_tenant_users_count(db, tenant_id)} usuarios y el global es {settings.max_users_per_tenant}",
            )
        tenant.max_users = None
    elif data.max_users is not None:
        if _tenant_users_count(db, tenant_id) > data.max_users:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede fijar {data.max_users} usuarios: el cliente ya tiene {_tenant_users_count(db, tenant_id)}",
            )
        tenant.max_users = data.max_users
    db.commit()
    db.refresh(tenant)

    out = TenantOut.model_validate(tenant)
    out.users_count = _tenant_users_count(db, tenant.id)
    out.subscription_days_left = _subscription_days_left(tenant)
    return out


@router.delete("/tenants/{tenant_id}", status_code=200)
def delete_tenant(tenant_id: int, db: Session = Depends(get_db)):
    tenant = _get_tenant(db, tenant_id)
    loan_ids = db.query(Loan.id).filter(Loan.tenant_id == tenant_id)
    db.query(LoanItem).filter(LoanItem.loan_id.in_(loan_ids)).delete(synchronize_session=False)
    db.query(ProductStockLocation).filter(ProductStockLocation.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Loan).filter(Loan.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Product).filter(Product.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(DriveConnection).filter(DriveConnection.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Setting).filter(Setting.tenant_id == tenant_id).delete(synchronize_session=False)
    db.delete(tenant)
    db.commit()
    return {"message": f"Cliente '{tenant.name}' eliminado correctamente."}


@router.post("/tenants/{tenant_id}/reset", status_code=200)
def reset_tenant(tenant_id: int, data: TenantReset, db: Session = Depends(get_db)):
    """Restablece un cliente a 'estado de fábrica': borra productos, préstamos
    e historial, deja un único administrador con la contraseña genérica y
    obliga a cambiarla en el primer inicio de sesión (como al crear el cliente).
    """
    tenant = _get_tenant(db, tenant_id)

    # Administrador que se conserva: el indicado o el de menor ID (primero creado).
    preserve = None
    if data.preserve_user_id:
        preserve = _get_user(db, data.preserve_user_id)
        if preserve.tenant_id != tenant_id or preserve.role != "admin":
            raise HTTPException(
                status_code=400,
                detail="El usuario indicado debe ser un administrador de este cliente",
            )
    else:
        preserve = (
            db.query(User)
            .filter(User.tenant_id == tenant_id, User.role == "admin")
            .order_by(User.id)
            .first()
        )
        if preserve is None:
            raise HTTPException(
                status_code=400,
                detail="El cliente no tiene un administrador para conservar",
            )

    # Limpiar todos los datos operativos del cliente.
    loan_ids = db.query(Loan.id).filter(Loan.tenant_id == tenant_id)
    db.query(LoanItem).filter(LoanItem.loan_id.in_(loan_ids)).delete(synchronize_session=False)
    db.query(ProductStockLocation).filter(ProductStockLocation.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Loan).filter(Loan.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Product).filter(Product.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(DriveConnection).filter(DriveConnection.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(Setting).filter(Setting.tenant_id == tenant_id).delete(synchronize_session=False)
    db.query(User).filter(User.tenant_id == tenant_id, User.id != preserve.id).delete(synchronize_session=False)

    # Dejar el administrador como recién creado.
    preserve.password_hash = hash_password(settings.default_generic_password)
    preserve.must_change_password = True
    preserve.accepted_terms = False
    preserve.accepted_terms_date = None
    preserve.is_active = True
    preserve.active_session = None
    preserve.session_expires_at = None
    # El administrador conservado hereda la vigencia del cliente.
    if tenant.subscription_expires_at is not None:
        preserve.subscription_expires_at = tenant.subscription_expires_at

    tenant.is_active = True
    db.commit()
    return {
        "message": (
            f"Cliente '{tenant.name}' restablecido a estado de fábrica. "
            f"Solo queda el administrador '{preserve.username}' con la contraseña genérica."
        ),
        "admin_username": preserve.username,
        "password": settings.default_generic_password,
    }


@router.get("/tenants/{tenant_id}/users", response_model=list[UserOut])
def list_tenant_users(tenant_id: int, db: Session = Depends(get_db)):
    _get_tenant(db, tenant_id)
    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)
        .order_by(User.username)
        .all()
    )
    return [user_out(u) for u in users]


@router.post("/tenants/{tenant_id}/users", response_model=UserOut, status_code=201)
def create_tenant_user(tenant_id: int, data: TenantUserCreate, db: Session = Depends(get_db)):
    tenant = _get_tenant(db, tenant_id)
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    _ensure_user_quota(db, tenant_id)

    password = data.password or settings.default_generic_password
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(password),
        role=data.role,
        tenant_id=tenant_id,
        must_change_password=True,
        security_question=data.security_question,
        security_answer=data.security_answer,
        # El nuevo usuario comparte la vigencia del cliente.
        subscription_expires_at=tenant.subscription_expires_at
        or (date.today() + timedelta(days=settings.subscription_days)),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.role, User.username).all()
    return [user_out(u) for u in users]


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="No se puede modificar a un Super Admin")

    updates = data.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] != user.role:
        _ensure_admin_remains(db, user)
    if updates.get("is_active") is False:
        _ensure_admin_remains(db, user)

    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.post("/users/{user_id}/reset-password", status_code=200)
def reset_password(user_id: int, data: AdminResetPassword, db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="El Super Admin cambia su contraseña desde su cuenta")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = True
    db.commit()
    return {"message": f"Contraseña de '{user.username}' actualizada correctamente."}


@router.post("/tenants/{tenant_id}/renew", status_code=200)
def renew_tenant_subscription(
    tenant_id: int,
    data: SubscriptionRenew,
    db: Session = Depends(get_db),
    me: User = Depends(require_superadmin),
):
    """Renueva la licencia del cliente (por días) y la hereda a sus usuarios.

    Visible solo para el Super Admin. Si la licencia está vigente se suman los
    días al vencimiento actual; si ya venció, se cuenta desde hoy.
    """
    tenant = _get_tenant(db, tenant_id)
    expire = _renew_tenant(db, tenant, data.days, me)
    return {
        "message": f"Licencia de '{tenant.name}' renovada por {data.days} días.",
        "expires_at": expire.isoformat(),
        "days_left": (expire - date.today()).days,
    }


@router.post("/users/{user_id}/renew", status_code=200)
def renew_subscription(
    user_id: int,
    data: SubscriptionRenew,
    db: Session = Depends(get_db),
    me: User = Depends(require_superadmin),
):
    """Renueva la licencia del cliente al que pertenece el usuario.

    La licencia es del CLIENTE, no del usuario: renovar a cualquiera de sus
    usuarios renueva todo el cliente. El Super Admin queda exento.
    """
    user = _get_user(db, user_id)
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="El Super Admin no tiene suscripción")

    if user.tenant_id is None:
        raise HTTPException(status_code=400, detail="El usuario no pertenece a ningún cliente")

    tenant = _get_tenant(db, user.tenant_id)
    expire = _renew_tenant(db, tenant, data.days, me)
    return {
        "message": f"Licencia de '{tenant.name}' renovada por {data.days} días.",
        "expires_at": expire.isoformat(),
        "days_left": (expire - date.today()).days,
    }


@router.delete("/users/{user_id}", status_code=200)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="No se puede eliminar a un Super Admin")
    _ensure_admin_remains(db, user)
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update({"user_id": None}, synchronize_session=False)
    db.query(Loan).filter(Loan.created_by == user_id).update({"created_by": None}, synchronize_session=False)
    db.delete(user)
    db.commit()
    return {"message": f"Usuario '{user.username}' eliminado."}
