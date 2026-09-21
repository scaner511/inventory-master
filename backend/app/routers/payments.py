"""Rutas de pagos para auto-activación de licencia (PayPal).

Flujo seguro:
  1. POST /paypal/create  — crea la orden en PayPal y guarda un registro
     temporal (status="created") con el tenant_id del usuario autenticado.
  2. El cliente paga en el popup de PayPal.
  3. POST /paypal/capture  — confirma el pago, valida el monto, extiende la
     licencia del tenant y registra el pago. Idempotente.
  4. POST /paypal/webhook  — endpoint SIN autenticación al que PayPal envía
     confirmaciones server-to-server. Confirma el pago por el servidor aunque
     el cliente cierre el navegador. (Protegido con verificación básica de
     PayPal; en producción reforzar con firma SSL).
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Payment, Tenant, User
from app.utils import paypal
from app.utils.audit import record_audit
from app.utils.licenses import extend_tenant_license, get_or_create_tenant_license

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


class CaptureRequest(BaseModel):
    order_id: str


# ─────────────────────────── helpers internos ────────────────────────────


def _tenant_price(db: Session, tenant_id: int | None) -> float:
    """Precio de la licencia del cliente (USD).

    El precio puede ser por cliente (columna tenants.price_usd) o global
    (PAYPAL_PRICE_USD). Varmoore a $55 fijos; el resto usan el global.
    """
    if tenant_id is not None:
        tenant = db.get(Tenant, tenant_id)
        if tenant is not None and tenant.price_usd is not None:
            return round(float(tenant.price_usd), 2)
    return round(settings.paypal_price_usd, 2)


def _apply_confirmed_payment(
    db: Session, order_id: str, amount: float, currency: str
) -> dict:
    """Extiende la licencia y registra el pago. Idempotente."""
    payment = (
        db.query(Payment).filter(Payment.order_id == order_id).first()
    )
    if payment is None:
        return {
            "applied": False,
            "error": "Este pago no corresponde a una solicitud registrada",
        }
    if payment.status == "completed":
        return {
            "applied": False,
            "already_applied": True,
            "expires_at": payment.expires_after.isoformat() if payment.expires_after else None,
            "days": payment.days_granted,
        }
    if payment.status not in ("created", "pending"):
        return {"applied": False, "error": f"Estado inesperado del pago ({payment.status})"}

    if abs(round(amount, 2) - _tenant_price(db, payment.tenant_id)) > 0.01:
        payment.status = "mismatch"
        db.commit()
        return {"applied": False, "error": "El monto no coincide con lo esperado"}

    tenant_id = payment.tenant_id
    days = settings.paypal_license_days
    before = get_or_create_tenant_license(db, tenant_id).expires_at
    lic = extend_tenant_license(db, tenant_id, days, key=f"PAY-{order_id}")
    after = lic.expires_at

    payment.status = "completed"
    payment.amount = round(amount, 2)
    payment.currency = currency
    payment.days_granted = days
    payment.expires_before = before
    payment.expires_after = after
    db.commit()

    record_audit(
        db,
        action="LICENCIA_PAGADA",
        user_id=None,
        tenant_id=tenant_id,
        detail=f"PayPal {order_id}: +{days} días",
    )

    return {
        "applied": True,
        "message": f"Pago confirmado. Licencia activada por {days} días",
        "expires_at": after.isoformat(),
        "days": days,
    }


# ──────────────────────── rutas autenticadas (frontend) ─────────────────


@router.get("/paypal/config")
def paypal_config(_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """Configuración del botón de PayPal (sin secretos), con el precio del cliente."""
    return {
        "enabled": settings.paypal_enabled,
        "client_id": settings.paypal_client_id if settings.paypal_enabled else "",
        "mode": settings.paypal_mode,
        "currency": "USD",
        "amount": _tenant_price(db, _user.tenant_id),
        "days": settings.paypal_license_days,
    }


@router.post("/paypal/create")
def create_paypal_order(
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea la orden de PayPal y guarda un registro para seguimiento."""
    if not settings.paypal_enabled:
        raise HTTPException(status_code=400, detail="Pago con PayPal no configurado")
    if _user.tenant_id is None:
        raise HTTPException(status_code=400, detail="Tu cuenta no tiene licencia de cliente")

    amount = _tenant_price(db, _user.tenant_id)
    reference_id = f"tenant-{_user.tenant_id}-LIC"
    result = paypal.create_order(
        amount=amount,
        reference_id=reference_id,
    )
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])

    db.add(
        Payment(
            order_id=result["id"],
            tenant_id=_user.tenant_id,
            provider="paypal",
            amount=amount,
            currency="USD",
            status="created",
        )
    )
    db.commit()

    return result


@router.post("/paypal/capture")
def capture_paypal_order(
    data: CaptureRequest,
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirma el pago tras el popup y extiende la licencia del cliente."""
    if not settings.paypal_enabled:
        raise HTTPException(status_code=400, detail="Pago con PayPal no configurado")
    if _user.tenant_id is None:
        raise HTTPException(status_code=400, detail="Tu cuenta no tiene licencia de cliente")

    order_id = data.order_id.strip()

    # Idempotencia rápida: si ya está completed, devolver el resultado.
    existing = (
        db.query(Payment).filter(Payment.order_id == order_id).first()
    )
    if existing is not None and existing.status == "completed":
        return {
            "message": "Este pago ya fue aplicado a la licencia",
            "already_applied": True,
            "expires_at": existing.expires_after.isoformat() if existing.expires_after else None,
            "days": existing.days_granted,
        }

    # Capturar en PayPal
    capture = paypal.capture_order(order_id)
    if capture.get("ok") is not True:
        if capture.get("status") == "PENDING":
            # Guardar el intento pendiente para que el webhook lo resuelva.
            if existing is None:
                db.add(
                    Payment(
                        order_id=order_id,
                        tenant_id=_user.tenant_id,
                        provider="paypal",
                        amount=_tenant_price(db, _user.tenant_id),
                        currency="USD",
                        status="pending",
                    )
                )
            else:
                existing.status = "pending"
            db.commit()
            raise HTTPException(
                status_code=202,
                detail="El pago está pendiente de confirmación. La licencia se activará automáticamente.",
            )
        raise HTTPException(status_code=502, detail=capture.get("error", "El pago no pudo confirmarse"))

    result = _apply_confirmed_payment(
        db, order_id, capture.get("amount", 0), capture.get("currency", "USD")
    )
    if not result["applied"] and not result.get("already_applied"):
        raise HTTPException(status_code=500, detail=result.get("error", "No se pudo aplicar el pago"))

    return result


# ──────────────────────── webhook (sin autenticación) ────────────────────


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    """Endpoint al que PayPal notifica pagos capturados (server-to-server).

    Si el cliente cierra el navegador tras pagar, el popup no regresa y
    ``/capture`` no se ejecuta. PayPal envía aquí la confirmación para que
    la licencia se active de todas formas.
    """
    if not settings.paypal_enabled:
        raise HTTPException(status_code=400, detail="Pago con PayPal no configurado")

    body = await request.body()
    headers = dict(request.headers)

    if not paypal.verify_webhook(headers, body):
        raise HTTPException(status_code=400, detail="Webhook inválido")

    order_id = paypal.webhook_extract_order(body)
    if not order_id:
        return {"status": "ignored"}

    # Buscar la orden; si no fue registrada por nuestro sistema, ignorar.
    payment = (
        db.query(Payment).filter(Payment.order_id == order_id).first()
    )
    if payment is None:
        return {"status": "ignored"}

    if payment.status == "completed":
        return {"status": "already_processed"}

    # El webhook ya indica que el pago está capturado; procesar directamente
    # sin volver a llamar a PayPal.
    days = settings.paypal_license_days
    before = get_or_create_tenant_license(db, payment.tenant_id).expires_at
    lic = extend_tenant_license(db, payment.tenant_id, days, key=f"PAY-{order_id}")
    after = lic.expires_at

    payment.status = "completed"
    payment.days_granted = days
    payment.expires_before = before
    payment.expires_after = after
    db.commit()

    record_audit(
        db,
        action="LICENCIA_PAGADA",
        user_id=None,
        tenant_id=payment.tenant_id,
        detail=f"PayPal webhook {order_id}: +{days} días",
    )

    return {"status": "applied"}
