"""Verificación de bases y de copias comprimidas (D4). Lo usan el VPS y el Mac.

Una copia es buena si se descomprime entera, da `ok` en
`PRAGMA integrity_check` y tiene al menos una captura.
"""

import gzip
import hashlib
import os
import shutil
import sqlite3
import zlib
from dataclasses import dataclass
from pathlib import Path

CHUNK = 1024 * 1024
PROGRESS_STEPS = 10_000  # instrucciones de SQLite entre llamadas a la función de progreso


def _progress() -> int:
    """Función de Python durante `integrity_check`: entre llamadas se atiende SIGTERM.

    Si la señal llega aquí (como KeyboardInterrupt), SQLite aborta la consulta
    con "interrupted" y `inspect_db` vuelve a lanzar la interrupción.
    """
    return 0


class VerificationError(Exception):
    """La base o la copia no ha pasado la verificación."""


class NothingToCopy(Exception):
    """La base no tiene tabla de capturas o no tiene ninguna captura."""


@dataclass(frozen=True)
class DbInfo:
    snapshots: int
    version: int


def inspect_db(path: Path) -> DbInfo:
    """Integridad, número de capturas y versión de estructura, en solo lectura."""
    conn = None
    try:
        conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        conn.set_progress_handler(_progress, PROGRESS_STEPS)
        result = conn.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            detail = "; ".join(str(row[0]) for row in result[:3])
            raise VerificationError(f"no ha pasado PRAGMA integrity_check: {detail}")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'snapshots'"
        ).fetchone()
        if not has_table:
            raise NothingToCopy("la base no tiene tabla de capturas")
        snapshots = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    except sqlite3.OperationalError as exc:
        if str(exc) == "interrupted":  # la función de progreso recibió la señal
            raise KeyboardInterrupt from exc
        raise VerificationError(f"no se ha podido leer la base: {exc}") from exc
    except sqlite3.Error as exc:
        raise VerificationError(f"no se ha podido leer la base: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()
    if snapshots == 0:
        raise NothingToCopy("la base no tiene ninguna captura")
    return DbInfo(snapshots=snapshots, version=version)


def sha256_of(path: Path, opener=open) -> str:
    digest = hashlib.sha256()
    with opener(path, "rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_digest(gz_path: Path) -> str:
    """SHA-256 de lo descomprimido; `VerificationError` si el gzip está mal."""
    try:
        return sha256_of(gz_path, opener=gzip.open)
    except (OSError, EOFError, zlib.error) as exc:
        raise VerificationError(f"el archivo comprimido no se descomprime bien: {exc}") from exc


def verify_gz(gz_path: Path, work_dir: Path) -> DbInfo:
    """Descomprime `gz_path` en un temporal de `work_dir`, lo verifica y lo borra."""
    tmp = Path(work_dir) / f".verify-{Path(gz_path).name}.{os.getpid()}.tmp"
    try:
        try:
            with gzip.open(gz_path, "rb") as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
        except (EOFError, zlib.error, gzip.BadGzipFile) as exc:
            raise VerificationError(f"el archivo comprimido no se descomprime bien: {exc}") from exc
        try:
            return inspect_db(tmp)
        except NothingToCopy as exc:
            raise VerificationError(str(exc)) from exc
    finally:
        for leftover in (tmp, tmp.with_name(tmp.name + "-journal")):
            leftover.unlink(missing_ok=True)
