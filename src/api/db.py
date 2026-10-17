"""Acceso a la base en solo lectura (design.md, D2 y D3).

Cada petición abre una conexión nueva con `mode=ro`, toma el bloqueo
compartido con su primera lectura y hace todas sus lecturas en una sola
transacción, así salen de la misma captura. Nunca `immutable` ni `nolock`
(ignorarían los bloqueos y podrían leer una captura a medias) ni pragmas que
escriban.

Mientras alguien lee, la ingesta no puede terminar de guardar (espera hasta
5 s). Por eso las lecturas de una petición tienen un plazo de 2 s desde que
se obtiene el bloqueo; la espera previa por base ocupada no cuenta.

Las peticiones leen de una en una dentro del proceso (candado `_GATE`). En
Unix, SQLite lleva los bloqueos de lectura por proceso: con lecturas
solapadas en varios hilos, el proceso no suelta nunca el suyo y una lectura
nueva no mira si la ingesta espera para guardar, así que la ingesta se
quedaría sin turno (design.md, D2).
"""

import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.ingestion.storage import SCHEMA_VERSION, SQLITE_READONLY_ROLLBACK

from .errors import ApiError, unavailable
from .formatting import parse_utc

BUSY_TIMEOUT_S = 2.0
READ_LIMIT_S = 2.0
GATE_TIMEOUT_S = 2.0
RETRY_AFTER_S = 5
PROGRESS_STEPS = 1000

SQLITE_BUSY = 5
SQLITE_LOCKED = 6
SQLITE_NOTADB = 26
SQLITE_INTERRUPT = 9

_GATE = threading.Lock()


def no_database() -> ApiError:
    return unavailable("sin_base", "todavía no hay base de datos: lanza la primera recogida")


def no_snapshots() -> ApiError:
    return unavailable("sin_capturas", "la base de datos aún no tiene capturas")


def unreadable() -> ApiError:
    return unavailable("base_ilegible", "no se ha podido leer la base de datos")


def busy() -> ApiError:
    return unavailable(
        "base_ocupada",
        "la base de datos está ocupada guardando una captura; inténtalo de nuevo en unos segundos",
        {"Retry-After": str(RETRY_AFTER_S)},
    )


def interrupted_ingestion() -> ApiError:
    return unavailable(
        "recogida_a_medias",
        "una recogida quedó a medias; se arreglará en la siguiente recogida de la máquina "
        "que recoge",
    )


def api_busy() -> ApiError:
    return unavailable(
        "api_ocupada",
        "la API está atendiendo demasiadas consultas; inténtalo de nuevo en unos segundos",
        {"Retry-After": str(RETRY_AFTER_S)},
    )


def too_long() -> ApiError:
    return unavailable(
        "consulta_demasiado_larga",
        "la consulta ha tardado demasiado y se ha cortado para no impedir guardar capturas; "
        "inténtalo de nuevo",
    )


def incompatible(version: int) -> ApiError:
    return unavailable(
        "base_no_compatible",
        f"la estructura de la base de datos (versión {version}) no es la que conoce la API "
        f"(versión {SCHEMA_VERSION})",
    )


@dataclass(frozen=True)
class Capture:
    id: int
    downloaded_at: datetime
    source_date: str | None


class Reader:
    """Conexión con la transacción de lectura abierta y la última captura."""

    def __init__(self, conn: sqlite3.Connection, capture: Capture, deadline: float,
                 monotonic=time.monotonic):
        self._conn = conn
        self.capture = capture
        self._deadline = deadline
        self._monotonic = monotonic

    def check(self) -> None:
        """Comprobación del plazo entre sentencias."""
        if self._monotonic() > self._deadline:
            raise too_long()

    def all(self, sql: str, params=()) -> list[tuple]:
        self.check()
        rows = _fetch(self._conn, sql, params)
        self.check()
        return rows


def _fetch(conn: sqlite3.Connection, sql: str, params=()) -> list[tuple]:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        translated = translate(exc)
        if isinstance(translated, ApiError):
            raise translated from exc
        raise


def translate(exc: sqlite3.Error) -> ApiError | sqlite3.Error:
    """Error de SQLite → ApiError; uno no previsto se deja tal cual (500)."""
    code = getattr(exc, "sqlite_errorcode", None)
    if code == SQLITE_READONLY_ROLLBACK:
        return interrupted_ingestion()
    primary = code & 0xFF if code is not None else None
    if primary in (SQLITE_BUSY, SQLITE_LOCKED):
        return busy()
    if primary == SQLITE_INTERRUPT:
        return too_long()
    if primary == SQLITE_NOTADB:
        return unreadable()
    return exc


@contextmanager
def read_snapshot(db_path: Path, *, busy_timeout_s: float = BUSY_TIMEOUT_S,
                  read_limit_s: float = READ_LIMIT_S, gate: threading.Lock = _GATE,
                  gate_timeout_s: float = GATE_TIMEOUT_S,
                  monotonic=time.monotonic) -> Iterator[Reader]:
    """Abre la base para leer la última captura; ApiError si no se puede."""
    db_path = Path(db_path)
    if not db_path.exists():
        # Con mode=ro tampoco se crearía, pero así el mensaje es el de «sin base».
        raise no_database()
    if not gate.acquire(timeout=gate_timeout_s):
        raise api_busy()
    try:
        with _read(db_path, busy_timeout_s, read_limit_s, monotonic) as reader:
            yield reader
    finally:
        gate.release()


@contextmanager
def _read(db_path: Path, busy_timeout_s: float, read_limit_s: float,
          monotonic) -> Iterator[Reader]:
    try:
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True,
                               timeout=busy_timeout_s, isolation_level=None)
    except sqlite3.Error as exc:
        raise _opening_error(exc) from exc
    try:
        try:
            conn.execute("BEGIN")
            # Primera lectura: toma el bloqueo compartido (aquí se espera si la
            # ingesta está guardando) y lee la cabecera.
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as exc:
            raise _opening_error(exc) from exc
        deadline = monotonic() + read_limit_s
        conn.set_progress_handler(lambda: 1 if monotonic() > deadline else 0, PROGRESS_STEPS)
        if version == 0:
            raise no_snapshots()
        if version != SCHEMA_VERSION:
            raise incompatible(version)
        rows = _fetch(conn,
                      "SELECT id, downloaded_at, source_date FROM snapshots ORDER BY id DESC LIMIT 1")
        if not rows:
            raise no_snapshots()
        snapshot_id, downloaded_at, source_date = rows[0]
        capture = Capture(snapshot_id, parse_utc(downloaded_at), source_date)
        yield Reader(conn, capture, deadline, monotonic)
    finally:
        _close(conn)


def _opening_error(exc: sqlite3.Error) -> ApiError:
    translated = translate(exc)
    return translated if isinstance(translated, ApiError) else unreadable()


def _close(conn: sqlite3.Connection) -> None:
    conn.set_progress_handler(None, 0)
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass  # tras una interrupción SQLite puede haberla cerrado ya
    conn.close()  # libera el bloqueo en cualquier caso
