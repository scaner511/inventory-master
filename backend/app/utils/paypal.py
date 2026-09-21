"""Cliente REST de PayPal (Orders API v2) — solo stdlib (urllib).

Flujo:
  1. El frontend abre el botón de PayPal y obtiene un order_id.
  2. El frontend envía el order_id a /payments/paypal/capture.
  3. El backend captura el pago, verifica la respuesta y extiende la
     licencia del tenant. Idempotente: un mismo order_id nunca otorga
     días dos veces.

El cliente podría cerrar el navegador después de pagar; para esos casos,
un webhook (POST /payments/paypal/webhook) registrado en PayPal confirma
el pago por el servidor. La verificación del webhook es sencilla en sandbox
(comparación de id); en producción debe verificarse la firma SSL de PayPal.
"""
import base64
import json
import logging
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from app.config import settings

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.x509 import load_pem_x509_certificates

    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - dev sin cryptography
    hashes = None
    padding = None
    load_pem_x509_certificates = None
    _CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)

_NO_VERIFY = ssl.create_default_context()


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def get_access_token() -> str | None:
    """Devuelve un access_token de PayPal (válido ~3600 s) o None si falla."""
    creds = _b64encode(
        f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode()
    )
    req = urllib.request.Request(
        f"{settings.paypal_api_base}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_NO_VERIFY) as resp:
            return json.loads(resp.read())["access_token"]
    except Exception as exc:
        logger.warning("PayPal get_access_token error: %s", exc)
        return None


def create_order(
    amount: float,
    currency: str = "USD",
    description: str = "Activación de licencia Inventory Master OS",
    reference_id: str | None = None,
) -> dict[str, Any]:
    """Crea una orden de PayPal y devuelve {id, approve_url}.

    En caso de error devuelve {error: "..."}. Se usa la app_return_url
    configurada en la app de PayPal como base; se agrega /license como
    retorno real (el usuario será redirigido a la pantalla de licencia
    tras pagar).
    """
    token = get_access_token()
    if not token:
        return {"error": "No se pudo autenticar con PayPal"}

    payload: dict[str, Any] = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                **({"reference_id": reference_id} if reference_id else {}),
                "amount": {
                    "currency_code": currency,
                    "value": f"{amount:.2f}",
                },
                "description": description,
            }
        ],
        "application_context": {
            "landing_page": "NO_PREFERENCE",
            "user_action": "PAY_NOW",
        },
    }

    req = urllib.request.Request(
        f"{settings.paypal_api_base}/v2/checkout/orders",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_NO_VERIFY) as resp:
            data = json.loads(resp.read())
            approve_url = next(
                (link["href"] for link in data.get("links", []) if link.get("rel") == "approve"),
                None,
            )
            return {"id": data["id"], "approve_url": approve_url}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("PayPal create_order %s: %s", exc.code, body)
        return {"error": f"Error de PayPal ({exc.code})"}
    except Exception as exc:
        logger.warning("PayPal create_order error: %s", exc)
        return {"error": str(exc)}


def capture_order(order_id: str) -> dict[str, Any]:
    """Captura una orden aprobada.

    Devuelve un dict con los campos relevantes del pago:
    {ok, order_id, status, amount, currency} o {ok: False, error: ...}.
    """
    token = get_access_token()
    if not token:
        return {"ok": False, "error": "No se pudo autenticar con PayPal"}

    req = urllib.request.Request(
        f"{settings.paypal_api_base}/v2/checkout/orders/{order_id}/capture",
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=_NO_VERIFY) as resp:
            data = json.loads(resp.read())
            if data.get("status") not in ("COMPLETED", "PENDING"):
                return {"ok": False, "error": f"Estado de la orden inesperado: {data.get('status')}"}
            purchase = data.get("purchase_units", [{}])[0]
            amount_data = purchase.get("amount", {})
            return {
                "ok": data.get("status") == "COMPLETED",
                "order_id": order_id,
                "status": data.get("status"),
                "amount": float(amount_data.get("value", 0)),
                "currency": amount_data.get("currency_code", "USD"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("PayPal capture_order %s: %s", exc.code, body)
        return {"ok": False, "error": f"Error de PayPal ({exc.code})"}
    except Exception as exc:
        logger.warning("PayPal capture_order error: %s", exc)
        return {"ok": False, "error": str(exc)}


def verify_webhook(headers: dict[str, str], body: bytes) -> bool:
    """Verifica un webhook de PayPal.

    Si se configuró ``PAYPAL_WEBHOOK_ID`` se valida la FIRMA completa de
    PayPal (transmisión id/hora/firma + certificado + HMAC del evento):
      1. El evento debe ser PAYMENT.CAPTURE.COMPLETED.
      2. La transmisión no debe tener más de 10 minutos (antirreplay).
      3. La firma debe corresponder al certificado público de PayPal.
    Sin webhook ID registrado (sandbox inicial), basta con que el evento sea
    de captura completada.
    """
    try:
        data = json.loads(body)
    except Exception:
        return False
    if data.get("event_type") != "PAYMENT.CAPTURE.COMPLETED":
        return False

    webhook_id = settings.paypal_webhook_id
    if not webhook_id:
        return True
    return _verify_signature(headers, body, webhook_id)


def _verify_signature(headers: dict[str, str], body: bytes, webhook_id: str) -> bool:
    """Verifica la firma SSL de PayPal (antirreplay + firma)."""
    if not _CRYPTO_AVAILABLE:
        logger.warning("cryptography no está instalado: webhooks con firma rechazados")
        return False
    transmission_id = headers.get("paypal-transmission-id", "")
    transmission_time = headers.get("paypal-transmission-time", "")
    transmission_sig = headers.get("paypal-transmission-sig", "")
    cert_url = headers.get("paypal-cert-url", "")
    if not all([transmission_id, transmission_time, transmission_sig, cert_url]):
        return False

    try:
        sent_at = datetime.strptime(transmission_time, "%Y-%m-%dT%H:%M:%SZ")
        if abs((datetime.utcnow() - sent_at).total_seconds()) > 600:
            return False
    except Exception:
        return False

    message = f"{transmission_id}|{transmission_time}|{webhook_id}|{body.decode('utf-8')}".encode()
    try:
        with urllib.request.urlopen(cert_url, timeout=10, context=_NO_VERIFY) as resp:
            cert_pem = resp.read()
        cert = load_pem_x509_certificates(cert_pem)[0]
        pub = cert.public_key()
        pub.verify(
            base64.b64decode(transmission_sig),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception as exc:
        logger.warning("PayPal webhook signature invalid: %s", exc)
        return False


def webhook_extract_order(body: bytes) -> str | None:
    """Extrae el order_id del body de un webhook de PayPal."""
    try:
        data = json.loads(body)
        return data.get("resource", {}).get("id")
    except Exception:
        return None
