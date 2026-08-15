"""Rutas de gestión de usuarios (solo administradores)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_admin
from app.models import User
from app.schemas import (
    AdminResetPassword,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.utils.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")

    # Contraseña genérica si el admin no indicó una; en todos los casos el
    # usuario deberá cambiarla en su primer inicio de sesión.
    password = data.password or settings.default_generic_password

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(password),
        role=data.role,
        must_change_password=True,
        security_question=data.security_question,
        security_answer=data.security_answer,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.username == "admin" and data.is_active is False:
        raise HTTPException(status_code=400, detail="No se puede desactivar al administrador principal")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=200)
def reset_user_password(
    user_id: int,
    data: AdminResetPassword,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.password_hash = hash_password(data.new_password)
    user.must_change_password = True
    db.commit()
    return {"message": f"Contraseña de '{user.username}' actualizada correctamente."}


@router.delete("/{user_id}", status_code=200)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar al administrador principal")

    db.delete(user)
    db.commit()
    return {"message": f"Usuario '{user.username}' eliminado."}
