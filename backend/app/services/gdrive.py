"""Subida de respaldos a Google Drive (opcional). Dos modos:

1) OAuth "Conectar con Google Drive" (recomendado):
   El Super Admin hace clic en el botón del panel, Google pide permiso y
   listo. La app crea/usa su propia carpeta "Inventory Master Backups" en
   el Drive del usuario. Requiere que el desarrollador configure una sola
   vez un Cliente OAuth:
     GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET

2) Cuenta de servicio (avanzado):
     GOOGLE_DRIVE_FOLDER_ID + GOOGLE_SERVICE_ACCOUNT_JSON (o *_FILE)

Común:
     GOOGLE_DRIVE_AUTO_UPLOAD=true  sube automáticamente cada backup.

Prioridad: si hay conexión OAuth activa se usa esa; si no, cuenta de servicio.
Las librerías de Google se importan de forma diferida: el resto del programa
funciona igual aunque no estén instaladas ni configuradas.
"""
import base64
import hashlib
import hmac
import io
import json
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_NAME = "Inventory Master Backups"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REVOKE_URI = "https://oauth2.googleapis.com/revoke"
USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"

STATE_MAX_AGE_SECONDS = 600


# ==========================================================================
# Utilidades comunes
# ==========================================================================

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign(data: str) -> str:
    mac = hmac.new(settings.secret_key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).digest()
    return _b64url(mac)


def make_state(return_path: str = "/admin", frontend_origin: str = "", tenant_id: str = "") -> str:
    """Estado firmado (CSRF) para el flujo OAuth: ts.nonce.tenant.ruta.origen.firma.

    El origen del panel y el tenant del proveedor viajan dentro del estado
    firmado porque el callback llega desde Google y no permite confiar en sus
    cabeceras.
    """
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(12)
    payload = ".".join(
        [
            ts,
            nonce,
            _b64url(tenant_id.encode("utf-8")),
            _b64url(return_path.encode("utf-8")),
            _b64url(frontend_origin.encode("utf-8")),
        ]
    )
    return f"{payload}.{_sign(payload)}"


def verify_state(state: str) -> tuple[str, str, str] | None:
    """Devuelve (ruta_retorno, origen_frontend, tenant_id) si es válido/reciente; si no, None."""
    try:
        ts, nonce, tenant_b64, return_b64, origin_b64, sig = state.split(".")
        payload = f"{ts}.{nonce}.{tenant_b64}.{return_b64}.{origin_b64}"
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        if int(time.time()) - int(ts) > STATE_MAX_AGE_SECONDS:
            return None

        def _dec(b64: str) -> str:
            pad = "=" * (-len(b64) % 4)
            return base64.urlsafe_b64decode(b64 + pad).decode("utf-8")

        tenant_id = _dec(tenant_b64)
        return_path = _dec(return_b64)
        origin = _dec(origin_b64)
        return return_path, origin, tenant_id
    except Exception:
        return None


def _http_post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_json(url: str, access_token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ==========================================================================
# Modo OAuth ("Conectar con Google Drive")
# ==========================================================================

def oauth_configured() -> bool:
    """True si hay Cliente OAuth configurado (puede ofrecerse el botón Conectar)."""
    return bool(settings.google_oauth_client_id.strip()) and bool(settings.google_oauth_client_secret.strip())


def get_connection(db: Session, tenant_id: int | None):
    from app.models import DriveConnection

    conn = (
        db.query(DriveConnection)
        .filter(DriveConnection.tenant_id == tenant_id)
        .first()
    )
    if conn is not None and conn.refresh_token:
        return conn
    return None


def build_auth_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.google_oauth_client_id.strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URI}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Canjea el código de autorización por tokens. Lanza error si falla."""
    return _http_post_form(
        TOKEN_URI,
        {
            "code": code,
            "client_id": settings.google_oauth_client_id.strip(),
            "client_secret": settings.google_oauth_client_secret.strip(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )


def fetch_user_email(access_token: str) -> str | None:
    try:
        info = _http_get_json(USERINFO_URI, access_token)
        return info.get("email")
    except Exception:
        return None


def save_connection(db: Session, tenant_id: int | None, refresh_token: str, email: str | None) -> None:
    from app.models import DriveConnection

    conn = (
        db.query(DriveConnection)
        .filter(DriveConnection.tenant_id == tenant_id)
        .first()
    )
    if conn is None:
        conn = DriveConnection(tenant_id=tenant_id)
        db.add(conn)
    conn.refresh_token = refresh_token
    conn.email = email
    conn.connected_at = datetime.now()
    db.commit()


def disconnect(db: Session, tenant_id: int | None) -> bool:
    """Revoca el token en Google y borra la conexión del proveedor."""
    from app.models import DriveConnection

    conn = (
        db.query(DriveConnection)
        .filter(DriveConnection.tenant_id == tenant_id)
        .first()
    )
    if conn is None or not conn.refresh_token:
        return False
    try:
        _http_post_form(REVOKE_URI, {"token": conn.refresh_token})
    except Exception:
        pass  # aunque Google falle, la conexión local se elimina igualmente
    db.delete(conn)
    db.commit()
    return True


def _oauth_credentials(conn):
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise RuntimeError(
            "Faltan las librerías de Google. Instala requirements.txt actualizado."
        ) from e
    return Credentials(
        token=None,
        refresh_token=conn.refresh_token,
        token_uri=TOKEN_URI,
        client_id=settings.google_oauth_client_id.strip(),
        client_secret=settings.google_oauth_client_secret.strip(),
        scopes=SCOPES,
    )


def _ensure_folder(svc, conn) -> tuple[str, str]:
    """Devuelve (folder_id, folder_name); crea la carpeta si no existe o fue borrada."""
    if conn.folder_id:
        try:
            folder = svc.files().get(fileId=conn.folder_id, fields="id,name").execute()
            return folder["id"], folder.get("name") or FOLDER_NAME
        except Exception:
            pass  # borrada o sin acceso: crear una nueva
    meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
    folder = svc.files().create(body=meta, fields="id,name").execute()
    return folder["id"], folder["name"]


# ==========================================================================
# Modo cuenta de servicio (alternativa avanzada)
# ==========================================================================

def _credentials_json() -> str | None:
    raw = (settings.google_service_account_json or "").strip()
    if raw:
        return raw
    file_path = (settings.google_service_account_file or "").strip()
    if file_path:
        p = Path(file_path)
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


def is_service_account_configured() -> bool:
    return bool((settings.google_drive_folder_id or "").strip()) and _credentials_json() is not None


def _get_service_account_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "Faltan las librerías de Google. Instala requirements.txt actualizado "
            "(google-api-python-client)."
        ) from e

    info = json.loads(_credentials_json())
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def test_service_account_connection() -> dict:
    folder_id = (settings.google_drive_folder_id or "").strip()
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID no está configurado.")
    if _credentials_json() is None:
        raise RuntimeError("No hay credenciales de cuenta de servicio (GOOGLE_SERVICE_ACCOUNT_JSON o FILE).")
    svc = _get_service_account_service()
    folder = svc.files().get(fileId=folder_id, fields="id,name,mimeType").execute()
    if folder.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("El ID configurado no corresponde a una carpeta de Drive.")
    return {"folder_id": folder.get("id"), "folder_name": folder.get("name")}


# ==========================================================================
# API unificada
# ==========================================================================

def active_mode(db: Session, tenant_id: int | None) -> str | None:
    """'oauth' | 'service_account' | None según lo que esté listo para usarse."""
    if oauth_configured() and get_connection(db, tenant_id) is not None:
        return "oauth"
    if is_service_account_configured():
        return "service_account"
    return None


def status_info(db: Session, tenant_id: int | None) -> dict:
    mode = active_mode(db, tenant_id)
    conn = get_connection(db, tenant_id) if mode == "oauth" else None
    return {
        "configured": mode is not None,
        "mode": mode,
        "email": conn.email if conn else None,
        "folder_name": conn.folder_name if conn else None,
        "folder_id": (
            conn.folder_id if conn else ((settings.google_drive_folder_id or "").strip() or None)
        ),
        "auto_upload": bool(settings.google_drive_auto_upload),
        "oauth_available": oauth_configured(),
    }


def test_connection(db: Session, tenant_id: int | None) -> dict:
    """Comprueba la conexión activa. Devuelve info descriptiva o lanza error."""
    mode = active_mode(db, tenant_id)
    if mode == "oauth":
        conn = get_connection(db, tenant_id)
        svc = _build_service_from_oauth(conn)
        folder_id, folder_name = _ensure_folder(svc, conn)
        db.commit()  # persistir carpeta si se acaba de crear
        return {
            "mode": "oauth",
            "message": f"Conectado a Drive de {conn.email} · carpeta '{folder_name}'.",
            "folder_name": folder_name,
            "folder_id": folder_id,
        }
    if mode == "service_account":
        info = test_service_account_connection()
        return {
            "mode": "service_account",
            "message": f"Conexión correcta con la carpeta '{info['folder_name']}'.",
            **info,
        }
    raise RuntimeError(
        "Google Drive no está configurado: conecta tu cuenta desde el panel o define las variables de entorno."
    )


def _build_service_from_oauth(conn):
    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError(
            "Faltan las librerías de Google. Instala requirements.txt actualizado."
        ) from e
    return build("drive", "v3", credentials=_oauth_credentials(conn), cache_discovery=False)


def upload_file(path: Path, db: Session, tenant_id: int | None) -> dict:
    """Sube un archivo al Drive configurado (OAuth o cuenta de servicio)."""
    mode = active_mode(db, tenant_id)
    if mode == "oauth":
        from googleapiclient.http import MediaFileUpload

        conn = get_connection(db, tenant_id)
        svc = _build_service_from_oauth(conn)
        folder_id, folder_name = _ensure_folder(svc, conn)
        media = MediaFileUpload(str(path), resumable=True)
        file = (
            svc.files()
            .create(
                body={"name": path.name, "parents": [folder_id]},
                media_body=media,
                fields="id,name",
            )
            .execute()
        )
        if conn.folder_id != folder_id or conn.folder_name != folder_name:
            conn.folder_id = folder_id
            conn.folder_name = folder_name
            db.commit()
        return {"id": file.get("id"), "name": file.get("name") or path.name, "mode": "oauth"}

    if mode == "service_account":
        from googleapiclient.http import MediaFileUpload

        svc = _get_service_account_service()
        media = MediaFileUpload(str(path), resumable=True)
        file = (
            svc.files()
            .create(body={"name": path.name}, media_body=media, fields="id,name")
            .execute()
        )
        return {"id": file.get("id"), "name": file.get("name") or path.name, "mode": "service_account"}

    raise RuntimeError(
        "Google Drive no está configurado: conecta tu cuenta desde el panel o define las variables de entorno."
    )


def _drive_service(db: Session, tenant_id: int | None):
    """Servicio de Drive según el modo activo (OAuth o cuenta de servicio)."""
    mode = active_mode(db, tenant_id)
    if mode == "oauth":
        return _build_service_from_oauth(get_connection(db, tenant_id))
    if mode == "service_account":
        return _get_service_account_service()
    raise RuntimeError(
        "Google Drive no está configurado: conecta tu cuenta desde el panel o define las variables de entorno."
    )


def list_backups(db: Session, tenant_id: int | None) -> dict:
    """Lista los respaldos del proveedor guardados en la carpeta de Drive.

    Devuelve {"mode": ..., "files": [...]} con los más recientes primero.
    """
    svc = _drive_service(db, tenant_id)
    mode = active_mode(db, tenant_id)

    folder_id = ""
    if mode == "oauth":
        conn = get_connection(db, tenant_id)
        folder_id = (conn.folder_id or "").strip() if conn else ""
    else:
        folder_id = (settings.google_drive_folder_id or "").strip()
    if not folder_id:
        # La carpeta aún no se ha creado: nunca se subió nada.
        return {"mode": mode, "files": []}

    query = f"'{folder_id}' in parents and trashed = false and name contains 'inventario_backup_'"
    result = (
        svc.files()
        .list(
            q=query,
            orderBy="createdTime desc",
            pageSize=50,
            fields="files(id,name,size,modifiedTime,mimeType)",
        )
        .execute()
    )
    files = []
    for f in result.get("files", []):
        size = f.get("size")
        files.append(
            {
                "id": f["id"],
                "name": f.get("name") or "",
                "size_kb": round(int(size) / 1024, 1) if size else None,
                "modified": f.get("modifiedTime"),
                "kind": "postgres" if (f.get("name") or "").endswith(".sql") else "excel",
            }
        )
    return {"mode": mode, "files": files}


def download_file_bytes(db: Session, file_id: str, tenant_id: int | None) -> tuple[str, bytes]:
    """Descarga un archivo por id desde el Drive configurado. Devuelve (nombre, bytes)."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as e:
        raise RuntimeError("Faltan las librerías de Google. Instala requirements.txt actualizado.") from e

    svc = _drive_service(db, tenant_id)
    meta = svc.files().get(fileId=file_id, fields="id,name").execute()
    name = meta.get("name") or "backup"
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, svc.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return name, buffer.getvalue()
