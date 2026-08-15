"""Rutas de backups (solo administradores)."""
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_admin
from app.services import backup as backup_service
from app.utils.audit import record_audit

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(require_admin)])


@router.post("/run")
def run_backup(db: Session = Depends(get_db)):
    path, kind = backup_service.create_backup(db)
    deleted = backup_service.cleanup_old_backups()
    return {
        "message": "Backup creado correctamente.",
        "file": path.name,
        "kind": kind,
        "cleaned": deleted,
    }


@router.get("/list")
def list_backups():
    return backup_service.list_backups()


@router.post("/purge")
def purge_backups(db: Session = Depends(get_db), _user=Depends(require_admin)):
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
def restore_backup(file: UploadFile = File(...), db: Session = Depends(get_db), _user=Depends(require_admin)):
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


@router.get("/download/{name}")
def download_backup(name: str):
    path = settings.backup_path / name
    if not path.exists() or not name.startswith("inventario_backup_"):
        raise HTTPException(status_code=404, detail="Backup no encontrado")
    return FileResponse(path, filename=name)
