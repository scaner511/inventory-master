"""Panel de Super Admin: clientes (tenants) y gestión global de usuarios.

Solo el Super Admin (role=superadmin) puede acceder a estas rutas.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_superadmin
from app.models import AuditLog, Loan, Product, Tenant, User
from app.schemas import (
    AdminResetPassword,
    TenantCreate,
    TenantOut,
    TenantUpdate,
    TenantUserCreate,
    UserOut,
    UserUpdate,
    user_out,
)
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
        result.append(out)
    return result


@router.post("/tenants", response_model=TenantOut, status_code=201)
def create_tenant(data: TenantCreate, db: Session = Depends(get_db)):
    if db.query(Tenant).filter(Tenant.name == data.name).first():
        raise HTTPException(status_code=400, detail="Ya existe un cliente con ese nombre")
    if db.query(User).filter(User.username == data.admin_username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario del administrador ya existe")

    tenant = Tenant(name=data.name, max_users=data.max_users)
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
        )
    )
    db.commit()

    out = TenantOut.model_validate(tenant)
    out.users_count = _tenant_users_count(db, tenant.id)
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
    return out


@router.delete("/tenants/{tenant_id}", status_code=200)
def delete_tenant(tenant_id: int, db: Session = Depends(get_db)):
    tenant = _get_tenant(db, tenant_id)
    db.query(Loan).filter(Loan.tenant_id == tenant_id).delete()
    db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).delete()
    db.query(Product).filter(Product.tenant_id == tenant_id).delete()
    db.query(User).filter(User.tenant_id == tenant_id).delete()
    db.delete(tenant)
    db.commit()
    return {"message": f"Cliente '{tenant.name}' eliminado correctamente."}


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
    _get_tenant(db, tenant_id)
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


@router.delete("/users/{user_id}", status_code=200)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="No se puede eliminar a un Super Admin")
    _ensure_admin_remains(db, user)
    db.delete(user)
    db.commit()
    return {"message": f"Usuario '{user.username}' eliminado."}
