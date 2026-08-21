"""Rutas de autenticación: login, recuperación de contraseña y sesión."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    user_out,
)
from app.utils.audit import record_audit
from app.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_for(user: User) -> TokenResponse:
    token = create_access_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "tenant_id": user.tenant_id,
        }
    )
    return TokenResponse(access_token=token, user=user_out(user))


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    user.last_login = datetime.now()
    db.commit()
    return _token_for(user)


@router.post("/forgot-password", status_code=200)
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Valida la pregunta de seguridad y entrega un token para restablecer la contraseña."""
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not user.security_question or not user.security_answer:
        raise HTTPException(status_code=400, detail="Este usuario no tiene configurada una pregunta de seguridad")

    if user.security_answer.lower() != data.answer.strip().lower():
        raise HTTPException(status_code=400, detail="Respuesta de seguridad incorrecta")

    reset_token = create_access_token({"sub": str(user.id), "purpose": "password_reset"}, expires_minutes=15)
    return {"reset_token": reset_token, "message": "Respuesta correcta. Puedes restablecer tu contraseña."}


@router.post("/reset-password", status_code=200)
def reset_password(
    reset_token: str,
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Restablece la contraseña usando el token de recuperación."""
    from app.utils.security import decode_access_token

    payload = decode_access_token(reset_token)
    if not payload or payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Token de recuperación inválido o expirado")

    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Contraseña restablecida correctamente."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/accept-terms", response_model=UserOut)
def accept_terms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra la aceptación obligatoria de Términos y Política de Privacidad.

    Idempotente: si ya aceptó, no duplica la fecha ni el evento de auditoría.
    """
    if not user.accepted_terms:
        user.accepted_terms = True
        user.accepted_terms_date = datetime.now()
        db.commit()
        record_audit(
            db,
            "TERMS_ACCEPTED",
            user.id,
            detail=(
                "Aceptó los Términos y Condiciones de Uso y la Política de "
                "Privacidad de Inventory Master OS Web v2026"
            ),
            tenant_id=user.tenant_id,
        )
    return user_out(user)


@router.post("/change-password", status_code=200)
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    db.commit()
    return {"message": "Contraseña actualizada correctamente."}
