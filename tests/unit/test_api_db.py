"""Acceso a la base de la API (prices-api, D2 y D3).

Requisitos «Base inexistente, vacía o ilegible», «Base abierta solo para
leer y sin crear archivos», «Base ocupada por una recogida», «La API no
impide guardar capturas» y «Datos siempre de capturas terminadas».
Los formatos HTTP de estos errores se prueban en los tests de la API.
"""

import shutil
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from src.api.db import read_snapshot
from src.api.errors import ApiError
from src.ingestion.storage import SCHEMA
from tests.api_helpers import CAPTURE_AT, basic_db, hold_lock, priced, save
from tests.helpers import db_dump
from tests.storage_helpers import make_pending_journal

UTC = timezone.utc


def folder_state(folder):
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns, p.read_bytes())
            for p in sorted(folder.iterdir())}


def read_capture(db, **kwargs):
    with read_snapshot(db, **kwargs) as reader:
        return reader.capture


def error_of(db, **kwargs) -> ApiError:
    with pytest.raises(ApiError) as exc:
        read_capture(db, **kwargs)
    assert exc.value.status == 503
    return exc.value


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


# --- base inexistente, vacía o ilegible ----------------------------------------

def test_no_database_is_not_created(db):
    """Escenario: Sin base de datos."""
    error = error_of(db)
    assert error.code == "sin_base"
    assert error.message == "todavía no hay base de datos: lanza la primera recogida"
    assert list(db.parent.iterdir()) == []


def test_schema_without_snapshots(db):
    """Escenario: Base sin capturas (versión 1 vacía)."""
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    conn.close()
    before = folder_state(db.parent)
    error = error_of(db)
    assert error.code == "sin_capturas"
    assert "aún no tiene capturas" in error.message
    assert folder_state(db.parent) == before


def test_empty_file(db):
    """Escenario: Base sin capturas (archivo de 0 bytes, versión 0)."""
    db.write_bytes(b"")
    assert error_of(db).code == "sin_capturas"
    assert db.read_bytes() == b""
    assert [p.name for p in db.parent.iterdir()] == ["prices.db"]


def test_file_that_is_not_a_database(db):
    """Escenario: Archivo que no es una base."""
    db.write_text("hola")
    error = error_of(db)
    assert (error.code, error.message) == ("base_ilegible", "no se ha podido leer la base de datos")
    assert db.read_text() == "hola"


def test_unknown_schema_version(db):
    """Escenario: Estructura desconocida."""
    basic_db(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 2")
    conn.close()
    before = db_dump(db)
    error = error_of(db)
    assert error.code == "base_no_compatible"
    assert "(versión 2)" in error.message and "(versión 1)" in error.message
    assert db_dump(db) == before


def test_interrupted_ingestion(db):
    """Escenario: Recogida que quedó a medias."""
    basic_db(db)
    make_pending_journal(db)
    journal = db.with_name("prices.db-journal")
    before = (db.read_bytes(), journal.read_bytes())
    error = error_of(db)
    assert error.code == "recogida_a_medias"
    assert "quedó a medias" in error.message
    assert "siguiente recogida de la máquina que recoge" in error.message
    assert (db.read_bytes(), journal.read_bytes()) == before


# --- lectura ------------------------------------------------------------------

def test_reading_creates_no_files_and_keeps_journal_mode(db):
    basic_db(db)
    before = folder_state(db.parent)
    for _ in range(20):
        assert read_capture(db).downloaded_at == CAPTURE_AT
    assert folder_state(db.parent) == before
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    conn.close()


def test_same_source_date_uses_the_last_saved(db):
    """Escenario: Misma Fecha de la API."""
    first = datetime(2026, 10, 16, 7, 26, 37, tzinfo=UTC)
    second = datetime(2026, 10, 16, 7, 31, 2, tzinfo=UTC)
    stations = [priced("4375", {"Gasoleo A": "1,459"})]
    save(db, *stations, instant=first)
    save(db, *stations, instant=second)
    capture = read_capture(db)
    assert capture.downloaded_at == second
    assert capture.source_date == "2026-10-16T09:26:34"


def test_first_capture_with_the_api_running(db):
    """Escenario: Primera captura con la API en marcha (cada lectura mira la base)."""
    assert error_of(db).code == "sin_base"
    basic_db(db)
    assert read_capture(db).downloaded_at == CAPTURE_AT


def test_restored_database_is_seen_on_the_next_read(db, tmp_path):
    """Escenario: Base restaurada desde una copia."""
    basic_db(db)
    assert read_capture(db).downloaded_at == CAPTURE_AT
    restored = tmp_path / "restaurada.db"
    later = CAPTURE_AT + timedelta(days=1)
    for hours in range(12):
        save(restored, priced("4375", {"Gasoleo A": "1,459"}),
             instant=later + timedelta(hours=6 * hours))
    db.rename(db.with_name("prices.db.apartada"))
    shutil.copy2(restored, db)
    assert read_capture(db).downloaded_at == later + timedelta(hours=66)


# --- bloqueos -----------------------------------------------------------------

def test_long_exclusive_lock_gives_busy_after_two_seconds(db):
    """Escenario: Guardado más largo que la espera."""
    basic_db(db)
    with hold_lock(db, 4):
        start = time.monotonic()
        error = error_of(db)
        elapsed = time.monotonic() - start
    assert error.code == "base_ocupada"
    assert error.message == ("la base de datos está ocupada guardando una captura; "
                             "inténtalo de nuevo en unos segundos")
    assert error.headers == {"Retry-After": "5"}
    assert 1.5 <= elapsed <= 2.5


def test_short_exclusive_lock_waits_and_reads(db):
    """Escenario: Guardado corto."""
    basic_db(db)
    with hold_lock(db, 0.5):
        start = time.monotonic()
        capture = read_capture(db)
        elapsed = time.monotonic() - start
    assert capture.downloaded_at == CAPTURE_AT
    assert elapsed <= 1.0


def test_reserved_lock_does_not_block_reads(db):
    """Escenario: Recogida preparando la captura (BEGIN IMMEDIATE sin guardar)."""
    basic_db(db)
    with hold_lock(db, 4, mode="IMMEDIATE"):
        start = time.monotonic()
        capture = read_capture(db)
        elapsed = time.monotonic() - start
    assert capture.downloaded_at == CAPTURE_AT
    assert elapsed < 0.5


def test_capture_being_saved_is_never_read_half(db):
    """Escenario: Captura guardándose (con el bloqueo exclusivo: 200 anterior o 503)."""
    basic_db(db)
    results = []
    with hold_lock(db, 1.5):
        for _ in range(3):
            try:
                results.append(read_capture(db, busy_timeout_s=0.2).downloaded_at)
            except ApiError as exc:
                results.append(exc.code)
    assert set(results) <= {CAPTURE_AT, "base_ocupada"}
    assert "base_ocupada" in results


# --- límite de lectura ----------------------------------------------------------

SLOW_SQL = ("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
            "SELECT count(*) FROM (SELECT i FROM n LIMIT 100000000)")


def test_slow_reading_is_cut_and_releases_the_lock(db):
    """Escenario: Consulta cortada."""
    basic_db(db)
    start = time.monotonic()
    with pytest.raises(ApiError) as exc:
        with read_snapshot(db, read_limit_s=0.2) as reader:
            reader.all(SLOW_SQL)
    assert time.monotonic() - start < 1.5
    assert exc.value.status == 503
    assert exc.value.code == "consulta_demasiado_larga"
    # La base queda libre: otro proceso toma el bloqueo exclusivo sin esperar.
    conn = sqlite3.connect(db, timeout=0, isolation_level=None)
    conn.execute("BEGIN EXCLUSIVE")
    conn.execute("ROLLBACK")
    conn.close()


def test_time_between_statements_also_counts(db):
    basic_db(db)
    now = [0.0]
    with pytest.raises(ApiError) as exc:
        with read_snapshot(db, read_limit_s=2.0, monotonic=lambda: now[0]) as reader:
            now[0] = 2.5
            reader.all("SELECT 1")
    assert exc.value.code == "consulta_demasiado_larga"


def test_busy_wait_does_not_count_in_the_read_limit(db):
    """La espera por base ocupada (D2) va aparte del plazo de lectura (D3)."""
    basic_db(db)
    with hold_lock(db, 0.8):
        with read_snapshot(db, read_limit_s=0.5) as reader:
            assert reader.all("SELECT count(*) FROM prices") == [(2,)]


# --- lecturas de una en una (candado del proceso, D2) ---------------------------

def test_turn_that_does_not_come(db, monkeypatch):
    """Escenario: Turno que no llega (sin abrir la base)."""
    import threading

    import src.api.db as api_db

    basic_db(db)
    gate = threading.Lock()
    gate.acquire()  # otra petición tiene el turno
    opened = []
    monkeypatch.setattr(api_db.sqlite3, "connect", lambda *a, **k: opened.append(a))
    start = time.monotonic()
    with pytest.raises(ApiError) as exc:
        read_capture(db, gate=gate)
    elapsed = time.monotonic() - start
    assert (exc.value.status, exc.value.code) == (503, "api_ocupada")
    assert exc.value.message == ("la API está atendiendo demasiadas consultas; "
                                 "inténtalo de nuevo en unos segundos")
    assert exc.value.headers == {"Retry-After": "5"}
    assert 1.5 <= elapsed <= 2.5
    assert opened == []


def test_turn_is_released_after_errors_and_reads(db):
    import threading

    gate = threading.Lock()
    with pytest.raises(ApiError):
        read_capture(db, gate=gate)  # sin base: ni siquiera coge el turno
    basic_db(db)
    read_capture(db, gate=gate)
    with pytest.raises(ApiError):
        with read_snapshot(db, gate=gate, read_limit_s=0.1) as reader:
            reader.all(SLOW_SQL)
    assert not gate.locked()


def test_gate_wait_does_not_count_in_the_read_limit(db):
    import threading

    basic_db(db)
    gate = threading.Lock()
    gate.acquire()
    threading.Timer(0.8, gate.release).start()
    with read_snapshot(db, gate=gate, read_limit_s=0.5) as reader:
        assert reader.all("SELECT count(*) FROM prices") == [(2,)]
