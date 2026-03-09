from pathlib import Path
import shutil
from datetime import datetime

from services.audit import log_event
from utils.database import DB_PATH

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"


def ensure_backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def create_db_backup(username: str | None = None) -> Path:
    ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"coronados_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    log_event(username, "backup_create", "backup", f"Backup: {backup_path.name}")
    return backup_path


def list_db_backups() -> list[Path]:
    ensure_backup_dir()
    return sorted(BACKUP_DIR.glob("coronados_*.db"), reverse=True)


def restore_db_backup(backup_name: str, username: str | None = None) -> tuple[bool, str]:
    ensure_backup_dir()
    backup_path = (BACKUP_DIR / backup_name).resolve()

    if backup_path.parent != BACKUP_DIR.resolve():
        return False, "Backup invalido."
    if not backup_path.exists() or backup_path.suffix.lower() != ".db":
        return False, "Backup no encontrado."

    try:
        shutil.copy2(backup_path, DB_PATH)
        log_event(username, "backup_restore", "backup", f"Backup restaurado: {backup_path.name}")
        return True, "Backup restaurado correctamente."
    except Exception as exc:
        return False, f"Error al restaurar backup: {exc}"
