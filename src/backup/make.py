"""Una copia de seguridad de la base en la máquina que recoge (D2–D5).

1. Coge el bloqueo de la carpeta de copias (nunca dos copias a la vez) y
   borra los temporales de una copia cortada: con ese bloqueo cogido, no
   puede haber otra en curso.
2. Coge el bloqueo de la carpeta de la base (el de la ingesta) solo para el
   volcado, hecho con la API de backup de SQLite desde una conexión de solo
   lectura: no crea ni modifica nada en la carpeta de la base.
3. Ya sin ese bloqueo: `integrity_check`, compresión, comprobación de lo
   comprimido y publicación atómica con el nombre del día; después, rotación.

Los dos bloqueos comparten un único plazo (10 minutos por defecto). Ante
cualquier error o interrupción se borran los temporales; las copias
anteriores no se tocan.
"""

import gzip
import os
import re
import shutil
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from src.ingestion.errors import IngestionBusy, StorageError
from src.ingestion.lock import data_dir_lock
from src.ingestion.scheduled import MADRID
from src.ingestion.storage import SCHEMA_VERSION, SQLITE_READONLY_ROLLBACK

from .rotation import backup_name, classify, rotate
from .verify import CHUNK, NothingToCopy, VerificationError, gzip_digest, inspect_db, sha256_of

WAIT_S = 10 * 60
BACKUP_PAGES = 4096  # páginas por paso del volcado: entre pasos se atienden las señales
TEMP_RE = re.compile(r"\.(prices-\d{4}-\d{2}-\d{2}\.\d+\.(db|gz)\.tmp|verify-.*\.tmp)(-journal)?")
BUSY = "otra ingesta o copia en curso"
INTERRUPTED = "la última ingesta quedó a medias"


class BackupPending(Exception):
    """No se ha podido hacer ahora, pero se puede reintentar hoy (bloqueo o diario)."""


class BackupFailed(Exception):
    """La copia ha fallado (base ilegible, verificación, disco…)."""


class AlreadyDone(Exception):
    """Ya hay una copia de hoy posterior a la marca de pendiente."""


@dataclass
class BackupResult:
    name: str
    size: int
    snapshots: int
    removed: list[str] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def madrid_date(instant: datetime) -> date:
    return instant.astimezone(MADRID).date()


def make_backup(
    db_path: Path,
    backups_dir: Path,
    clock: Callable[[], datetime],
    wait_s: float = WAIT_S,
    skip_if_newer_than: float | None = None,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> BackupResult:
    db_path, backups_dir = Path(db_path), Path(backups_dir)
    if not backups_dir.is_dir():
        raise BackupFailed(f"no existe la carpeta de copias {backups_dir}")
    deadline = monotonic() + wait_s
    try:
        with data_dir_lock(backups_dir, deadline=deadline, sleep=sleep, monotonic=monotonic):
            today = madrid_date(clock())
            final = backups_dir / backup_name(today)
            if skip_if_newer_than is not None and final.exists() \
                    and final.stat().st_mtime > skip_if_newer_than:
                raise AlreadyDone(final.name)
            cleaned = _clean_temporaries(backups_dir)
            result = _backup_locked(db_path, backups_dir, final, deadline, sleep, monotonic)
            result.cleaned = cleaned
            result.removed, future = rotate(backups_dir, today)
            result.warnings += [f"fecha futura en {name} (no cuenta para la rotación)"
                                for name in future]
            return result
    except IngestionBusy as exc:
        raise BackupPending(BUSY) from exc
    except StorageError as exc:
        raise BackupFailed(str(exc)) from exc


def _clean_temporaries(backups_dir: Path) -> list[str]:
    cleaned = []
    for path in sorted(backups_dir.iterdir()):
        if path.is_file() and TEMP_RE.fullmatch(path.name):
            path.unlink()
            cleaned.append(path.name)
    return cleaned


def _backup_locked(db_path, backups_dir, final, deadline, sleep, monotonic) -> BackupResult:
    stem = f".{final.name.removesuffix('.db.gz')}.{os.getpid()}"
    dump = backups_dir / f"{stem}.db.tmp"
    packed = backups_dir / f"{stem}.gz.tmp"
    try:
        with data_dir_lock(db_path.parent, deadline=deadline, sleep=sleep, monotonic=monotonic):
            version = _dump(db_path, dump)
        try:
            info = inspect_db(dump)
        except VerificationError as exc:
            raise BackupFailed(f"la base no ha pasado la verificación: {exc}") from exc
        digest = sha256_of(dump)
        try:
            _compress(dump, packed)
            if gzip_digest(packed) != digest:
                raise BackupFailed("lo comprimido no coincide con la base volcada")
            os.replace(packed, final)
            _fsync_dir(backups_dir)
        except OSError as exc:
            raise BackupFailed(f"no se ha podido escribir la copia en {backups_dir}: {exc}") from exc
        except VerificationError as exc:
            raise BackupFailed(str(exc)) from exc
        warnings = []
        if version not in (0, SCHEMA_VERSION):
            warnings.append(f"versión de estructura desconocida ({version})")
        return BackupResult(final.name, final.stat().st_size, info.snapshots, warnings=warnings)
    finally:
        for leftover in (dump, dump.with_name(dump.name + "-journal"), packed):
            leftover.unlink(missing_ok=True)


def _dump(db_path: Path, dump: Path) -> int:
    """Volcado con la API de backup desde una conexión de solo lectura. Devuelve la versión."""
    if not db_path.exists():
        raise NothingToCopy("no existe la base de datos")  # abrirla la crearía
    src = dst = None
    try:
        try:
            src = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
            version = src.execute("PRAGMA user_version").fetchone()[0]
            has_table = src.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'snapshots'"
            ).fetchone()
            if not has_table:
                raise NothingToCopy("la base no tiene tabla de capturas")
            if src.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 0:
                raise NothingToCopy("la base no tiene ninguna captura")
        except sqlite3.Error as exc:
            if getattr(exc, "sqlite_errorcode", None) == SQLITE_READONLY_ROLLBACK:
                raise BackupPending(INTERRUPTED) from exc
            raise BackupFailed(f"no se ha podido leer la base {db_path}: {exc}") from exc
        try:
            dst = sqlite3.connect(dump)
            # La función de progreso es Python: entre pasos se atiende SIGTERM.
            src.backup(dst, pages=BACKUP_PAGES, progress=lambda status, remaining, total: None)
        except (sqlite3.Error, OSError) as exc:
            raise BackupFailed(f"no se ha podido escribir la copia en {dump.parent}: {exc}") from exc
        return version
    finally:
        for conn in (dst, src):
            if conn is not None:
                conn.close()


def _compress(src: Path, dst: Path) -> None:
    with open(src, "rb") as f, open(dst, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as g:
            shutil.copyfileobj(f, g, CHUNK)
        raw.flush()
        os.fsync(raw.fileno())


def _fsync_dir(folder: Path) -> None:
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def latest_backup(backups_dir: Path, today: date) -> Path | None:
    """La copia más reciente por la fecha del nombre (sin ajenas ni futuras)."""
    if not Path(backups_dir).is_dir():
        return None
    valid, _ = classify((p.name for p in Path(backups_dir).iterdir() if p.is_file()), today)
    return Path(backups_dir) / valid[max(valid)] if valid else None
