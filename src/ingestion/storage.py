"""Guardado de una captura en SQLite: todo o nada.

El esquema, la captura, las estaciones y los precios se escriben en una única
transacción. Una base nueva se escribe en un archivo temporal que solo se
renombra al nombre definitivo tras el COMMIT. Nunca se borran capturas ni
precios, ni se toca un archivo que ya existía si algo falla.
"""

import os
import secrets
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import InterruptedIngestion, ShortResponseError, StorageError
from .models import ParsedSnapshot, PriceRecord

# Raíz del repo (src/ingestion/storage.py → ../..): la base por defecto no
# depende de la carpeta desde la que se lance el programa.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "prices.db"

SCHEMA_VERSION = 1
MIN_SQLITE_VERSION = (3, 24, 0)  # necesario para INSERT ... ON CONFLICT
INSTANT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SQLITE_READONLY_ROLLBACK = 776  # código extendido de SQLite

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    id            TEXT PRIMARY KEY,
    brand         TEXT NOT NULL,
    address       TEXT NOT NULL,
    municipality  TEXT NOT NULL,
    province      TEXT NOT NULL,
    schedule      TEXT NOT NULL,
    latitude      REAL,
    longitude     REAL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    downloaded_at  TEXT NOT NULL,
    source_date    TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    snapshot_id  INTEGER NOT NULL REFERENCES snapshots(id),
    station_id   TEXT    NOT NULL REFERENCES stations(id),
    fuel         TEXT    NOT NULL,
    price        REAL    NOT NULL CHECK (price > 0),
    PRIMARY KEY (snapshot_id, station_id, fuel)
);
"""

UPSERT_STATION = """
INSERT INTO stations (id, brand, address, municipality, province, schedule, latitude, longitude)
VALUES (:id, :brand, :address, :municipality, :province, :schedule, :latitude, :longitude)
ON CONFLICT(id) DO UPDATE SET
    brand = excluded.brand,
    address = excluded.address,
    municipality = excluded.municipality,
    province = excluded.province,
    schedule = excluded.schedule,
    latitude = COALESCE(excluded.latitude, stations.latitude),
    longitude = COALESCE(excluded.longitude, stations.longitude)
"""


@dataclass(frozen=True)
class LastSnapshot:
    """Última captura guardada (la de mayor `id`)."""

    downloaded_at: datetime
    stations: int  # estaciones con al menos un precio en esa captura


@dataclass(frozen=True)
class ShortResponse:
    """Respuesta con menos del 80 % de las estaciones de la última captura."""

    stations: int  # estaciones con al menos un precio en la respuesta
    reference: int  # estaciones con algún precio en la última captura


@dataclass(frozen=True)
class SaveResult:
    snapshot_id: int
    new_stations: int
    updated_stations: int
    prices: int
    # Solo si se ha guardado a sabiendas una respuesta corta (accept_short).
    short_response: ShortResponse | None = None


def format_instant(instant: datetime) -> str:
    """Instante en UTC con formato `AAAA-MM-DDTHH:MM:SSZ`."""
    if instant.tzinfo is None:
        raise ValueError("el instante de descarga debe llevar zona horaria")
    return instant.astimezone(timezone.utc).strftime(INSTANT_FORMAT)


def read_last_snapshot(db_path: Path) -> LastSnapshot | None:
    """Última captura guardada, o None si no hay. Nunca crea ni modifica nada.

    Abre en solo lectura. Una conexión así no puede deshacer un diario
    pendiente y falla con SQLITE_READONLY_ROLLBACK: entonces se lanza
    `InterruptedIngestion` (lo deshará la siguiente ingesta, que abre en
    escritura). Mirar solo si existe `prices.db-journal` no vale: puede quedar
    un diario vacío que no está pendiente.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None  # abrirla la crearía
    conn = None
    try:
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise StorageError(f"versión de base de datos no compatible: {version}")
        has_snapshots = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'snapshots'"
        ).fetchone()
        if not has_snapshots:
            return None
        return _last_snapshot(conn)
    except sqlite3.Error as exc:
        if getattr(exc, "sqlite_errorcode", None) == SQLITE_READONLY_ROLLBACK:
            raise InterruptedIngestion(
                f"la última ingesta sobre {db_path} quedó a medias"
            ) from exc
        raise StorageError(f"no se ha podido leer la base de datos {db_path}: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def _last_snapshot(conn: sqlite3.Connection) -> LastSnapshot | None:
    row = conn.execute(
        "SELECT id, downloaded_at FROM snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    snapshot_id, instant = row
    stations = conn.execute(
        "SELECT COUNT(DISTINCT station_id) FROM prices WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()[0]
    return LastSnapshot(parse_instant(instant), stations)


def parse_instant(text: str) -> datetime:
    """Inverso de `format_instant`."""
    return datetime.strptime(text, INSTANT_FORMAT).replace(tzinfo=timezone.utc)


def save_snapshot(
    snapshot: ParsedSnapshot,
    db_path: Path,
    downloaded_at: datetime,
    accept_short: bool = False,
) -> SaveResult:
    """Guarda la captura, todo o nada.

    Si la respuesta trae menos del 80 % de las estaciones de la última
    captura, lanza `ShortResponseError` sin guardar nada, salvo con
    `accept_short`, que la guarda y lo indica en `SaveResult.short_response`.
    """
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        raise StorageError(
            f"se necesita SQLite 3.24 o posterior; esta instalación tiene {sqlite3.sqlite_version}"
        )
    db_path = Path(db_path)
    instant = format_instant(downloaded_at)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError(f"no se ha podido crear la carpeta {db_path.parent}: {exc}") from exc

    if db_path.exists():
        return _save(db_path, snapshot, instant, accept_short)

    try:
        tmp_path = _create_temporary(db_path)
    except OSError as exc:
        raise StorageError(f"no se ha podido crear la base de datos {db_path}: {exc}") from exc
    try:
        result = _save(tmp_path, snapshot, instant, accept_short)
        os.replace(tmp_path, db_path)
    except OSError as exc:
        _remove_temporary(tmp_path)
        raise StorageError(f"no se ha podido crear la base de datos {db_path}: {exc}") from exc
    except BaseException:
        _remove_temporary(tmp_path)
        raise
    return result


def _save(path: Path, snapshot: ParsedSnapshot, instant: str, accept_short: bool) -> SaveResult:
    conn = None
    try:
        conn = sqlite3.connect(path, isolation_level=None)
        # Fuera de la transacción: dentro, SQLite lo ignora sin avisar.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            result = _write(conn, snapshot, instant, accept_short)
            conn.execute("COMMIT")
            return result
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    except sqlite3.Error as exc:
        raise StorageError(f"no se ha podido guardar en la base de datos {path}: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def _write(
    conn: sqlite3.Connection, snapshot: ParsedSnapshot, instant: str, accept_short: bool
) -> SaveResult:
    _ensure_schema(conn)
    # La referencia se lee aquí, con la conexión de escritura: tras el
    # BEGIN IMMEDIATE (que deshace un diario pendiente) y tras comprobar la
    # versión, y antes de insertar la captura nueva.
    short = _short_response(conn, snapshot)
    if short is not None and not accept_short:
        raise ShortResponseError(short.stations, short.reference)
    snapshot_id = conn.execute(
        "INSERT INTO snapshots (downloaded_at, source_date) VALUES (?, ?)",
        (instant, snapshot.source_date),
    ).lastrowid

    new = updated = 0
    for station in snapshot.stations:
        exists = conn.execute("SELECT 1 FROM stations WHERE id = ?", (station.id,)).fetchone()
        if exists:
            updated += 1
        else:
            new += 1
        conn.execute(UPSERT_STATION, asdict(station))

    _insert_prices(conn, snapshot_id, snapshot.prices)
    return SaveResult(snapshot_id, new, updated, len(snapshot.prices), short)


def _short_response(conn: sqlite3.Connection, snapshot: ParsedSnapshot) -> ShortResponse | None:
    """ShortResponse si la respuesta no llega al 80 % de la última captura."""
    last = _last_snapshot(conn)
    if last is None or last.stations == 0:
        return None
    stations = len({price.station_id for price in snapshot.prices})
    if is_short(stations, last.stations):
        return ShortResponse(stations, last.stations)
    return None


def is_short(stations: int, reference: int) -> bool:
    """Menos del 80 % de `reference`, con enteros (9.600 de 12.000 no lo es)."""
    return stations * 10 < reference * 8


def _ensure_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, SCHEMA_VERSION):
        raise StorageError(f"versión de base de datos no compatible: {version}")
    if version == 0:
        for statement in SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _insert_prices(conn: sqlite3.Connection, snapshot_id: int, prices: list[PriceRecord]) -> None:
    conn.executemany(
        "INSERT INTO prices (snapshot_id, station_id, fuel, price) VALUES (?, ?, ?, ?)",
        [(snapshot_id, p.station_id, p.fuel, p.price) for p in prices],
    )


def _create_temporary(db_path: Path) -> Path:
    """Crea un temporal vacío y nuevo junto a la base (nunca reutiliza uno huérfano).

    El nombre lleva un sufijo aleatorio y se crea en exclusiva (`O_EXCL`), así
    que no puede coincidir con el temporal de una ejecución anterior cortada.
    Se respetan los permisos por defecto del sistema (umask).
    """
    tmp_path = db_path.with_name(f"{db_path.name}.tmp-{secrets.token_hex(8)}")
    os.close(os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
    return tmp_path


def _remove_temporary(tmp_path: Path) -> None:
    for path in (tmp_path, tmp_path.with_name(tmp_path.name + "-journal")):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
