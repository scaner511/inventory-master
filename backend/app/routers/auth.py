"""Rutas de autenticación: login, recuperación de contraseña y sesión."""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, get_tenant_session
from app.deps import get_current_user, get_current_user_optional
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
from app.utils.platform_audit import record_platform_audit
from app.utils.security import create_access_token, decode_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_for(user: User, session_id: str) -> TokenResponse:
    token = create_access_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "tenant_id": user.tenant_id,
            "session_id": session_id,
        }
    )
    return TokenResponse(access_token=token, user=user_out(user))


def _session_window() -> timedelta:
    """Ventana de inactividad: si no hay actividad en este lapso, la sesión
    única se considera libre y se permite entrar desde otro equipo."""
    return timedelta(minutes=settings.active_session_idle_minutes)


def _session_max() -> timedelta:
    return timedelta(minutes=settings.active_session_expire_minutes)


def _session_active(user: User, now: datetime) -> bool:
    """True si la sesión única actual sigue vigente (no expirada)."""
    return bool(user.active_session and user.session_expires_at and user.session_expires_at > now)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    # Sesión única: si la sesión previa sigue vigente (con actividad reciente) se
    # bloquea el acceso desde otro equipo. Si quedó inactiva (equipo apagado,
    # pestaña cerrada, etc.), la ventana se vence y se permite reingresar.
    now = datetime.now()
    if _session_active(user, now):
        raise HTTPException(
            status_code=409,
            detail=(
                "Ya hay una sesión activa en otro equipo. Cierra sesión ahí, o "
                "espera unos minutos sin actividad para poder entrar aquí."
            ),
        )

    session_id = secrets.token_urlsafe(32)
    user.active_session = session_id
    user.session_expires_at = now + _session_window()
    user.last_login = now
    db.commit()
    return _token_for(user, session_id)


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
    payload = decode_access_token(reset_token)
    if not payload or payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Token de recuperación inválido o expirado")

    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.password_hash = hash_password(data.new_password)
    # Al restablecer la contraseña se cierra cualquier sesión activa.
    user.active_session = None
    user.session_expires_at = None
    db.commit()
    return {"message": "Contraseña restablecida correctamente."}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/logout", status_code=200)
def logout(
    token: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Cierra la sesión activa del usuario: libera el equipo para nuevos inicios.

    Acepta el usuario por cabecera ``Authorization`` o, como respaldo, un ``token``
    por query (necesario para ``navigator.sendBeacon`` al cerrar la pestaña, ya que
    no permite cabeceras personalizadas).
    """
    if user is None and token:
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            user = db.get(User, int(payload["sub"]))
    if user is None:
        return {"message": "Sesión cerrada correctamente."}
    user.active_session = None
    user.session_expires_at = None
    db.commit()
    return {"message": "Sesión cerrada correctamente."}


@router.post("/accept-terms", response_model=UserOut)
def accept_terms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra la aceptación obligatoria de Términos y Política de Privacidad.

    Idempotente: si ya aceptó, no duplica la fecha ni el evento de auditoría.
    """
    if not user.accepted_terms:
        user.accepted_terms = True
        user.accepted_terms_date = datetime.now()
        db.commit()
        detail = (
            "Aceptó los Términos y Condiciones de Uso y la Política de "
            "Privacidad de Inventory Master OS Web v2026"
        )
        if user.tenant_id is not None:
            # El historial de negocio vive en la base EXCLUSIVA del cliente.
            tdb = get_tenant_session(user.tenant_id)
            try:
                record_audit(tdb, "TERMS_ACCEPTED", user.id, detail=detail, tenant_id=user.tenant_id)
            finally:
                tdb.close()
        else:
            record_platform_audit(db, "TERMS_ACCEPTED", user.id, detail=detail)
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
