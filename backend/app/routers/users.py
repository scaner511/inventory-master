"""Rutas de gestión de usuarios del cliente (solo su administrador).

Cada administrador solo ve y gestiona los usuarios de su propio cliente.
El Super Admin administra todos los clientes desde /api/superadmin.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_admin
from app.models import Tenant, User
from app.schemas import (
    AdminResetPassword,
    UserCreate,
    UserOut,
    UserUpdate,
    user_out,
)
from app.utils.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _tenant_users_count(db: Session, tenant_id: int) -> int:
    return (
        db.query(func.count(User.id))
        .filter(User.tenant_id == tenant_id, User.role.in_(("admin", "user")))
        .scalar()
        or 0
    )


def _ensure_quota(db: Session, tenant_id: int) -> None:
    tenant = db.get(Tenant, tenant_id)
    limit = tenant.max_users if tenant and tenant.max_users else settings.max_users_per_tenant
    if _tenant_users_count(db, tenant_id) >= limit:
        raise HTTPException(
            status_code=400,
            detail=f"El cliente ya alcanzó el máximo de {limit} usuarios",
        )


def _get_tenant_user(db: Session, user_id: int, tenant_id: int) -> User:
    user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


def _ensure_admin_remains(db: Session, user: User) -> None:
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


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    users = (
        db.query(User)
        .filter(User.tenant_id == _user.tenant_id)
        .order_by(User.username)
        .all()
    )
    return [user_out(u) for u in users]


@router.get("/terms-acceptances")
def terms_acceptances(db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    """Consulta administrativa: quién aceptó los términos y cuándo."""
    users = (
        db.query(User)
        .filter(User.tenant_id == _user.tenant_id)
        .order_by(User.username)
        .all()
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "accepted_terms": bool(u.accepted_terms),
            "accepted_terms_date": u.accepted_terms_date.isoformat() if u.accepted_terms_date else None,
        }
        for u in users
    ]


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    _ensure_quota(db, _user.tenant_id)

    password = data.password or settings.default_generic_password
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(password),
        role=data.role,
        tenant_id=_user.tenant_id,
        must_change_password=True,
        security_question=data.security_question,
        security_answer=data.security_answer,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    user = _get_tenant_user(db, user_id, _user.tenant_id)

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


@router.post("/{user_id}/reset-password", status_code=200)
def reset_user_password(
    user_id: int,
    data: AdminResetPassword,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    user = _get_tenant_user(db, user_id, _user.tenant_id)
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = True
    db.commit()
    return {"message": f"Contraseña de '{user.username}' actualizada correctamente."}


@router.delete("/{user_id}", status_code=200)
def delete_user(user_id: int, db: Session = Depends(get_db), _user: User = Depends(require_admin)):
    user = _get_tenant_user(db, user_id, _user.tenant_id)
    _ensure_admin_remains(db, user)
    db.delete(user)
    db.commit()
    return {"message": f"Usuario '{user.username}' eliminado."}
