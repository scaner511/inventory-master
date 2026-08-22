"""Rutas de backups (solo Super Admin)."""
import io
import urllib.parse

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    Response,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_superadmin
from app.models import User
from app.services import backup as backup_service
from app.services import gdrive
from app.utils.audit import record_audit
from app.utils.security import decode_access_token

router = APIRouter(prefix="/api/backup", tags=["backup"])

# Rutas del flujo OAuth: las llama Google desde el navegador (sin JWT ni sesión),
# así que viven en un router aparte sin las dependencias globales de licencia y
# rol. Se protegen por sí mismas (token firmado en /start, estado firmado en
# /callback).
oauth_router = APIRouter(prefix="/api/backup/drive/oauth", tags=["backup"])


@router.post("/run", dependencies=[Depends(require_superadmin)])
def run_backup(db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    path, kind = backup_service.create_backup(db)
    deleted = backup_service.cleanup_old_backups()
    drive_result = None
    if settings.google_drive_auto_upload and gdrive.active_mode(db):
        try:
            info = gdrive.upload_file(path, db)
            drive_result = {"uploaded": True, **info}
            record_audit(db, "BACKUP", _user.id, detail=f"Backup '{path.name}' subido a Google Drive")
        except Exception as e:
            drive_result = {"uploaded": False, "error": str(e)}
    return {
        "message": "Backup creado correctamente.",
        "file": path.name,
        "kind": kind,
        "cleaned": deleted,
        "drive": drive_result,
    }


@router.get("/list", dependencies=[Depends(require_superadmin)])
def list_backups():
    return backup_service.list_backups()


@router.post("/purge", dependencies=[Depends(require_superadmin)])
def purge_backups(db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    """Borra todas las bases de datos de respaldo excepto la última generada."""
    deleted, kept = backup_service.purge_all_but_latest()
    record_audit(db, "BACKUP", _user.id, detail=f"Purga de backups: {deleted} eliminado(s), conservado '{kept}'")
    if deleted == 0:
        return {"message": "No había backups que borrar.", "deleted": 0}
    return {
        "message": f"{deleted} backup(s) eliminado(s). Se conservó el más reciente.",
        "deleted": deleted,
        "kept": kept,
    }


@router.post("/restore")
def restore_backup(file: UploadFile = File(...), db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    """Restaura la base de datos a partir de un respaldo Excel (.xlsx).

    Reemplaza por completo los datos actuales por los del respaldo
    (productos, préstamos, usuarios, historial, etc.).
    """
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext != "xlsx":
        raise HTTPException(status_code=400, detail="Solo se aceptan respaldos .xlsx generados por el sistema")

    content = file.file.read()
    try:
        counts = backup_service.restore_from_excel(db, io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo restaurar el respaldo: {e}")

    record_audit(db, "RESTAURACION", _user.id, detail=f"Base de datos restaurada desde {file.filename}")
    summary = ", ".join(f"{name}: {count}" for name, count in counts.items())
    return {"message": f"Base de datos restaurada correctamente ({summary}).", "tables": counts}


@router.get("/download/{name}", dependencies=[Depends(require_superadmin)])
def download_backup(name: str):
    path = settings.backup_path / name
    if not path.exists() or not name.startswith("inventario_backup_"):
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    return FileResponse(path, filename=name)


# ================= Google Drive =================


def _redirect_uri(request: Request) -> str:
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}/api/backup/drive/oauth/callback"


def _safe_return_path(raw: str | None) -> str:
    """Valida la ruta interna de retorno del navegador (evita open redirect)."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/admin"


def _frontend_origin(request: Request) -> str:
    """Origen del panel (scheme://host) desde donde se inició la conexión.

    La navegación a /start es cross-origin, así que el navegador manda el
    Referer reducido al origen; es la forma fiable de saber a qué frontend
    volver tras autenticar. FRONTEND_ORIGIN (si existe) tiene prioridad.
    """
    explicit = (settings.frontend_origin or "").strip().rstrip("/")
    if explicit.startswith(("http://", "https://")):
        return explicit
    parts = urllib.parse.urlsplit(request.headers.get("referer", ""))
    if parts.scheme in ("http", "https") and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return ""


@router.get("/drive/status", dependencies=[Depends(require_superadmin)])
def drive_status(db: Session = Depends(get_db)):
    return gdrive.status_info(db)


@router.post("/drive/test", dependencies=[Depends(require_superadmin)])
def drive_test(db: Session = Depends(get_db)):
    """Comprueba la conexión activa (OAuth o cuenta de servicio)."""
    try:
        info = gdrive.test_connection(db)
        return {"ok": True, **info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/drive/upload/{name}")
def drive_upload(name: str, db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    """Sube una copia local concreta a Google Drive."""
    path = settings.backup_path / name
    if not path.exists() or not name.startswith("inventario_backup_"):
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    try:
        info = gdrive.upload_file(path, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo subir a Drive: {e}")
    record_audit(db, "BACKUP", _user.id, detail=f"Backup '{name}' subido a Google Drive")
    return {"message": f"'{name}' subido a Google Drive correctamente.", "file": name, **info}


@oauth_router.get("/start")
def oauth_start(request: Request, token: str = "", return_path: str | None = None, db: Session = Depends(get_db)):
    """Inicia el flujo 'Conectar con Google Drive'.

    Se navega desde el navegador (sin cabecera Authorization), por eso el JWT
    viaja como parámetro y se valida manualmente.
    """
    payload = decode_access_token(token)
    user = db.get(User, int(payload["sub"])) if payload and payload.get("sub") else None
    if user is None or not user.is_active or user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Acceso restringido al Super Admin")

    if not gdrive.oauth_configured():
        raise HTTPException(
            status_code=400,
            detail="El servidor no tiene GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET configurados.",
        )

    safe_return = _safe_return_path(return_path)
    state = gdrive.make_state(safe_return, _frontend_origin(request))
    url = gdrive.build_auth_url(_redirect_uri(request), state)
    return RedirectResponse(url)


@oauth_router.get("/callback")
def oauth_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    """Recibe la respuesta de Google, guarda la conexión y vuelve al panel."""
    verified = gdrive.verify_state(state) if state else None
    return_path = verified[0] if verified else None
    state_origin = (verified[1] if verified else "").rstrip("/")

    def _back(ok: bool, msg: str = ""):
        # El origen del panel se capturó en /start y viaja firmado en el estado;
        # este request viene de Google, así que sus cabeceras no se tienen en cuenta.
        target_origin = state_origin
        if not target_origin:
            detail = "Conexión con Google Drive completada." if ok else f"No se completó la conexión: {msg}"
            return HTMLResponse(
                f"<h2>{detail}</h2><p>Vuelve al panel y recarga la página para ver el estado.</p>"
            )
        ret = return_path or "/admin"
        sep = "&" if "?" in ret else "?"
        flag = "ok" if ok else f"error:{urllib.parse.quote(msg)}"
        return RedirectResponse(f"{target_origin}{ret}{sep}drive={flag}")

    if error:
        return _back(False, "autorizacion_cancelada")
    if not code or return_path is None:
        return _back(False, "estado_invalido")

    try:
        tokens = gdrive.exchange_code(code, _redirect_uri(request))
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Google no devolvió un refresh_token; reintenta la conexión.")
        email = gdrive.fetch_user_email(tokens.get("access_token", ""))
        gdrive.save_connection(db, refresh_token, email)
        record_audit(db, "BACKUP", None, detail=f"Google Drive conectado ({email or 'sin email'})")
    except Exception as e:
        return _back(False, str(e)[:120])

    return _back(True)


@router.post("/drive/oauth/disconnect", dependencies=[Depends(require_superadmin)])
def oauth_disconnect(db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    had = gdrive.disconnect(db)
    if not had:
        return {"message": "No había conexión de Google Drive.", "disconnected": False}
    record_audit(db, "BACKUP", _user.id, detail="Google Drive desconectado")
    return {"message": "Google Drive desconectado correctamente.", "disconnected": True}


@router.get("/drive/list")
def drive_list(db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    """Lista los respaldos guardados en la carpeta de Google Drive."""
    try:
        return gdrive.list_backups(db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/drive/download/{file_id}")
def drive_download(file_id: str, db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    """Descarga a tu equipo un respaldo concreto desde Google Drive."""
    try:
        name, content = gdrive.download_file_bytes(db, file_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo descargar de Drive: {e}")
    if not name.startswith("inventario_backup_"):
        raise HTTPException(status_code=400, detail="El archivo no es un respaldo del sistema")
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if name.endswith(".xlsx")
        else "application/octet-stream"
    )
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/drive/restore/{file_id}")
def drive_restore(file_id: str, db: Session = Depends(get_db), _user=Depends(require_superadmin)):
    """Restaura la base de datos directamente desde una copia en Google Drive.

    Descarga el respaldo Excel desde Drive y reemplaza TODOS los datos
    actuales por los del respaldo, sin pasar por el equipo local.
    """
    try:
        name, content = gdrive.download_file_bytes(db, file_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo descargar de Drive: {e}")
    if not name.startswith("inventario_backup_") or not name.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden restaurar respaldos Excel (.xlsx) generados por el sistema",
        )
    try:
        counts = backup_service.restore_from_excel(db, io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo restaurar el respaldo: {e}")

    record_audit(db, "RESTAURACION", _user.id, detail=f"Base de datos restaurada desde Google Drive ({name})")
    summary = ", ".join(f"{n}: {c}" for n, c in counts.items())
    return {
        "message": f"Base de datos restaurada correctamente ({summary}).",
        "tables": counts,
        "file": name,
    }
