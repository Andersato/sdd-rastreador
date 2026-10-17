"""Escenarios de `database-backup` sobre la copia en sí (`src/backup/make.py` y
`run_backup`), sin Docker y con reloj fijo.

Requisitos: «Copia en caliente sin tocar la base», «Copia verificada antes de
darla por buena», «Una sola copia a la vez», «Nombre y rotación de las
copias» (lo que hace la copia), «Archivos ajenos y temporales en ./backups»
y «Una línea de log por copia». Otro proceso con el bloqueo se simula con un
proceso aparte que lo coge (es el mismo `flock` que usan ingesta y copia).
"""

import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pytest

import src.backup.make as make
from src.backup.make import BackupFailed, BackupPending, make_backup
from src.backup.rotation import backup_name
from src.backup.scheduled import EXIT_BUSY, EXIT_FAILED, EXIT_OK, run_backup, saved_line
from src.backup.verify import NothingToCopy
from tests.builders import response, station
from tests.helpers import REPO_ROOT, closed_port_url, run_check
from tests.storage_helpers import ingest, make_pending_journal, query

# 2026-10-17 04:43 en Madrid (CEST).
NOW = datetime(2026, 10, 17, 2, 43, tzinfo=timezone.utc)
TODAY = date(2026, 10, 17)


def clock():
    return NOW


def folder_state(folder):
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


@pytest.fixture
def dirs(tmp_path):
    data, backups = tmp_path / "data", tmp_path / "backups"
    data.mkdir()
    backups.mkdir()
    return data, backups


def seed(data, count=3, stations=2):
    db = data / "prices.db"
    body = response(*(station(f"S{i}", **{"Precio Gasoleo A": "1,459"}) for i in range(stations)))
    for n in range(count):
        ingest(db, body, instant=NOW - timedelta(hours=6 * (count - n)))
    return db


def unpack(gz, tmp_path):
    out = tmp_path / "restaurada.db"
    with gzip.open(gz) as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return out


HOLDER = """
import sys, time
from pathlib import Path
from src.ingestion.lock import data_dir_lock
with data_dir_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    time.sleep(float(sys.argv[2]))
    if len(sys.argv) > 3:
        from src.ingestion.parser import parse_response
        from src.ingestion.storage import save_snapshot
        from datetime import datetime, timezone
        import json
        data = json.loads(Path(sys.argv[4]).read_text())
        save_snapshot(parse_response(data), Path(sys.argv[3]), datetime.now(timezone.utc))
"""


@pytest.fixture
def holder():
    """Proceso que coge el bloqueo de una carpeta durante `seconds` segundos."""
    procs = []

    def start(folder, seconds=60, then_ingest=None):
        args = [sys.executable, "-c", HOLDER, str(folder), str(seconds)]
        if then_ingest:
            args += [str(then_ingest[0]), str(then_ingest[1])]
        proc = subprocess.Popen(args, cwd=REPO_ROOT, stdout=subprocess.PIPE, text=True)
        assert proc.stdout.readline().strip() == "locked"
        procs.append(proc)
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()


def log_of(capture):
    lines = []
    return lines, lines.append


# --- Copia en caliente sin tocar la base -------------------------------------

def test_copy_with_the_scheduler_running(dirs, tmp_path):
    """Escenario: Copia con el programador en marcha."""
    data, backups = dirs
    db = seed(data, count=4)
    prices = query(db, "SELECT COUNT(*) FROM prices")[0][0]
    before = folder_state(data)
    result = make_backup(db, backups, clock)
    copy = unpack(backups / "prices-2026-10-17.db.gz", tmp_path)
    assert query(copy, "SELECT COUNT(*) FROM snapshots")[0][0] == 4
    assert query(copy, "SELECT COUNT(*) FROM prices")[0][0] == prices
    assert result.snapshots == 4
    assert folder_state(data) == before
    assert sorted(os.listdir(data)) == ["prices.db"]


def test_ingestion_in_progress_that_ends_soon(dirs, tmp_path, holder):
    """Escenario: Ingesta en curso que termina pronto: la copia espera y lleva la
    captura nueva."""
    data, backups = dirs
    db = seed(data, count=2)
    body = tmp_path / "body.json"
    body.write_text(__import__("json").dumps(response(station("S0", **{"Precio Gasoleo A": "1,5"}),
                                                      station("S1", **{"Precio Gasoleo A": "1,5"}))))
    proc = holder(data, seconds=1, then_ingest=(db, body))
    result = make_backup(db, backups, clock, wait_s=20)
    proc.wait()
    assert result.snapshots == 3


def test_ingestion_that_does_not_end_leaves_the_copy_pending(dirs, tmp_path, holder):
    """Escenario: Ingesta en curso que no termina (plazo reducido)."""
    data, backups = dirs
    db = seed(data)
    (backups / "prices-2026-10-16.db.gz").write_bytes(b"anterior")
    before_data, before_backups = folder_state(data), folder_state(backups)
    holder(data)
    marker = tmp_path / "backup-pending"
    lines, out = log_of(None)
    start = time.monotonic()
    code = run_backup(db, backups, clock, out, marker=marker, wait_s=1.5)
    assert 1.0 < time.monotonic() - start < 5
    assert code == EXIT_BUSY
    assert lines == ["2026-10-17 04:43:00 CEST · copia pendiente: otra ingesta o copia en curso; "
                     "se reintenta en la próxima comprobación horaria"]
    assert marker.read_text() == "2026-10-17"
    assert folder_state(data) == before_data and folder_state(backups) == before_backups


def test_pending_journal_leaves_the_copy_pending_without_touching_data(dirs, tmp_path):
    """Escenario: Ingesta anterior a medias."""
    data, backups = dirs
    db = seed(data)
    make_pending_journal(db)
    before = folder_state(data)
    marker = tmp_path / "backup-pending"
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out, marker=marker) == EXIT_BUSY
    assert "copia pendiente: la última ingesta quedó a medias" in lines[0]
    assert folder_state(data) == before  # prices.db y prices.db-journal intactos
    assert os.listdir(backups) == []
    assert marker.exists()


def test_hourly_check_during_the_dump_is_rejected(dirs, http_server, holder):
    """Escenario: Comprobación horaria durante el volcado."""
    data, backups = dirs
    db = seed(data, count=1)
    holder(data)  # el volcado tiene el bloqueo de ./data
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_check(url, db, "2026-10-17T12:17:00Z")
    assert result.stdout.strip().endswith("otra ingesta o copia en curso; no se captura")
    assert http_server.requests == {}


def test_hourly_check_during_verification_or_compression_captures(dirs, http_server, holder):
    """Escenarios: Comprobación horaria durante la verificación o la compresión e
    Ingesta durante la verificación de otra copia: solo está cogido el bloqueo
    de ./backups, que la ingesta no usa."""
    data, backups = dirs
    db = seed(data, count=1)
    holder(backups)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_check(url, db, "2026-10-17T12:17:00Z")
    assert "captura guardada" in result.stdout, result.stdout + result.stderr
    assert http_server.requests == {"/api": 1}


# --- Copia verificada antes de darla por buena --------------------------------

def test_correct_copy_decompresses_with_gunzip(dirs, tmp_path):
    """Escenario: Copia correcta (se descomprime con `gunzip`)."""
    data, backups = dirs
    db = seed(data, count=28)
    make_backup(db, backups, clock)
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(backups / "prices-2026-10-17.db.gz", work)
    subprocess.run(["gunzip", str(work / "prices-2026-10-17.db.gz")], check=True)
    copy = work / "prices-2026-10-17.db"
    assert query(copy, "PRAGMA integrity_check") == [("ok",)]
    assert query(copy, "SELECT COUNT(*) FROM snapshots")[0][0] == 28
    assert sorted(os.listdir(backups)) == ["prices-2026-10-17.db.gz"]


def corrupt_index(db):
    """Base que no pasa `integrity_check` pero cuyas capturas se pueden contar: un
    índice que apunta a la raíz de otra tabla."""
    conn = sqlite3.connect(db)
    conn.execute("CREATE INDEX idx_fuel ON prices(fuel)")
    conn.commit()
    root = conn.execute("SELECT rootpage FROM sqlite_master WHERE name = 'stations'").fetchone()[0]
    conn.execute("PRAGMA writable_schema = ON")
    conn.execute("UPDATE sqlite_master SET rootpage = ? WHERE name = 'idx_fuel'", (root,))
    conn.commit()
    conn.close()
    try:
        assert query(db, "PRAGMA integrity_check") != [("ok",)]
    except sqlite3.DatabaseError:
        pass  # "malformed": también es una base que no pasa la verificación
    assert query(db, "SELECT COUNT(*) FROM snapshots")[0][0] > 0  # se pueden contar


def test_damaged_database(dirs):
    """Escenario: Base dañada."""
    data, backups = dirs
    db = seed(data)
    corrupt_index(db)
    (backups / "prices-2026-10-16.db.gz").write_bytes(b"anterior")
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert "error en la copia: la base no ha pasado la verificación" in lines[0]
    assert folder_state(backups) == {"prices-2026-10-16.db.gz": b"anterior"}


@pytest.mark.parametrize("create", [False, True], ids=["inexistente", "sin-capturas"])
def test_missing_or_empty_database(dirs, create):
    """Escenario: Base inexistente o sin capturas."""
    data, backups = dirs
    db = data / "prices.db"
    if create:
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE snapshots (id INTEGER PRIMARY KEY)")
        conn.close()
    before = folder_state(data)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert "copia no hecha: nada que copiar" in lines[0]
    assert folder_state(data) == before
    assert os.listdir(backups) == []


def test_unreadable_database(dirs):
    """Escenario: Base ilegible."""
    data, backups = dirs
    db = data / "prices.db"
    db.write_text("hola")
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert "no se ha podido leer la base" in lines[0]
    assert db.read_text() == "hola"
    assert os.listdir(backups) == []


def test_unknown_schema_version_is_copied_with_a_warning(dirs):
    """Escenario: Versión de estructura desconocida."""
    data, backups = dirs
    db = seed(data, count=28)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 7")
    conn.close()
    before = folder_state(data)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_OK
    assert "28 capturas" in lines[0]
    assert "aviso: versión de estructura desconocida (7)" in lines[0]
    assert folder_state(data) == before


def test_unknown_version_without_snapshots_table(dirs):
    """Escenario: Versión desconocida sin tabla de capturas."""
    data, backups = dirs
    db = data / "prices.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE otra (x)")
    conn.execute("PRAGMA user_version = 7")
    conn.close()
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert "nada que copiar" in lines[0]


def test_disk_full(dirs, monkeypatch):
    """Escenario: Disco lleno (error simulado al comprimir)."""
    data, backups = dirs
    db = seed(data)
    (backups / "prices-2026-10-16.db.gz").write_bytes(b"anterior")

    def full(src, dst):
        dst.write_bytes(b"medio")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(make, "_compress", full)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert "No space left on device" in lines[0]
    assert folder_state(backups) == {"prices-2026-10-16.db.gz": b"anterior"}


def test_interrupted_copy_leaves_nothing(dirs, monkeypatch):
    """Escenario: Copia interrumpida (SIGTERM llega como KeyboardInterrupt)."""
    data, backups = dirs
    db = seed(data)
    before = folder_state(data)

    def interrupted(src, dst):
        dst.write_bytes(b"medio")
        raise KeyboardInterrupt

    monkeypatch.setattr(make, "_compress", interrupted)
    with pytest.raises(KeyboardInterrupt):
        make_backup(db, backups, clock)
    assert os.listdir(backups) == []
    assert folder_state(data) == before


# --- Una sola copia a la vez --------------------------------------------------

def test_second_copy_waits_for_the_first(dirs, holder):
    """Escenario: Copia a mano a la vez que la diaria (la primera tiene ./backups)."""
    data, backups = dirs
    db = seed(data)
    proc = holder(backups, seconds=1)
    start = time.monotonic()
    make_backup(db, backups, clock, wait_s=20)
    assert time.monotonic() - start > 0.5
    proc.wait()
    assert sorted(os.listdir(backups)) == ["prices-2026-10-17.db.gz"]


def test_daily_gives_up_when_the_first_copy_takes_too_long(dirs, tmp_path, holder):
    """Escenario: La primera copia no termina a tiempo (plazo reducido)."""
    data, backups = dirs
    db = seed(data)
    holder(backups)
    marker = tmp_path / "backup-pending"
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out, marker=marker, wait_s=1) == EXIT_BUSY
    assert "copia pendiente: otra ingesta o copia en curso" in lines[0]
    assert marker.exists()


def test_manual_copy_gives_up_waiting_for_another_copy(dirs, holder):
    """Escenario: Copia a mano que espera demasiado a otra copia."""
    data, backups = dirs
    db = seed(data)
    holder(backups)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out, wait_s=1) == EXIT_BUSY
    assert lines[0].endswith("no se ha hecho la copia: ya hay otra ingesta o copia en curso")
    assert os.listdir(backups) == []


def test_wait_counts_in_total_for_both_locks(dirs, holder):
    """Escenario: Espera total: primero otra copia y después una ingesta."""
    data, backups = dirs
    db = seed(data)
    holder(backups, seconds=1)
    holder(data)
    start = time.monotonic()
    with pytest.raises(BackupPending):
        make_backup(db, backups, clock, wait_s=2.5)
    assert 2.0 < time.monotonic() - start < 4.5


# --- Nombre y rotación (lo que hace la copia) ----------------------------------

def test_second_copy_same_day_replaces_the_first(dirs, tmp_path):
    """Escenario: Segunda copia el mismo día."""
    data, backups = dirs
    db = seed(data, count=28)
    make_backup(db, backups, clock)
    ingest(db, response(station("S0", **{"Precio Gasoleo A": "1,5"}),
                        station("S1", **{"Precio Gasoleo A": "1,5"})), instant=NOW)
    make_backup(db, backups, clock)
    assert sorted(os.listdir(backups)) == ["prices-2026-10-17.db.gz"]
    copy = unpack(backups / "prices-2026-10-17.db.gz", tmp_path)
    assert query(copy, "SELECT COUNT(*) FROM snapshots")[0][0] == 29


def test_second_copy_same_day_that_fails_keeps_the_first(dirs):
    """Escenario: Segunda copia del mismo día que falla."""
    data, backups = dirs
    db = seed(data)
    make_backup(db, backups, clock)
    first = (backups / "prices-2026-10-17.db.gz").read_bytes()
    corrupt_index(db)
    with pytest.raises(BackupFailed):
        make_backup(db, backups, clock)
    assert (backups / "prices-2026-10-17.db.gz").read_bytes() == first


def test_failed_copy_does_not_remove_copies(dirs):
    """Escenario: Una copia fallida no borra copias (habría que rotar 12)."""
    data, backups = dirs
    db = seed(data)
    for n in range(1, 13):
        (backups / backup_name(TODAY - timedelta(days=7 * n))).write_bytes(b"x")
    before = folder_state(backups)
    corrupt_index(db)
    with pytest.raises(BackupFailed):
        make_backup(db, backups, clock)
    assert folder_state(backups) == before


def test_copy_rotates_after_success(dirs):
    data, backups = dirs
    db = seed(data)
    for n in range(1, 20):
        (backups / backup_name(TODAY - timedelta(days=n))).write_bytes(b"x")
    result = make_backup(db, backups, clock)
    # Del 28/09 al 17/10: 7 diarias (11-17/10) y una semanal (4/10, única semana
    # completa sin diarias); el resto se borra.
    kept = sorted(n for n in os.listdir(backups) if n.endswith(".db.gz"))
    assert kept == sorted([backup_name(date(2026, 10, 4))]
                          + [backup_name(date(2026, 10, d)) for d in range(11, 18)])
    assert len(result.removed) == 12


def test_failed_write_in_backups_does_not_stop_the_next_check(dirs, http_server):
    """Escenario: Una copia fallida no para el programador (fallo de escritura
    inyectado: `./backups` sin permiso de escritura)."""
    data, backups = dirs
    db = seed(data, count=1)
    backups.chmod(0o555)
    try:
        lines, out = log_of(None)
        assert run_backup(db, backups, clock, out) == EXIT_FAILED
        assert "error en la copia: no se ha podido escribir la copia" in lines[0]
    finally:
        backups.chmod(0o755)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_check(url, db, "2026-10-17T03:17:00Z")
    assert result.returncode == 0 and "captura guardada" in result.stdout


# --- Archivos ajenos y temporales en ./backups ---------------------------------

def test_temporaries_of_a_cut_copy_are_removed_and_logged(dirs):
    """Escenario: Temporales de una copia cortada."""
    data, backups = dirs
    db = seed(data)
    (backups / ".prices-2026-10-16.4242.db.tmp").write_bytes(b"medio")
    (backups / ".prices-2026-10-16.4242.gz.tmp").write_bytes(b"medio")
    (backups / "notas.txt").write_text("mío")
    (backups / "prices-2026-10-16.db.gz").write_bytes(b"anterior")
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_OK
    assert ("temporales borrados: .prices-2026-10-16.4242.db.tmp, "
            ".prices-2026-10-16.4242.gz.tmp") in lines[0]
    assert sorted(os.listdir(backups)) == ["notas.txt", "prices-2026-10-16.db.gz",
                                           "prices-2026-10-17.db.gz"]


def test_future_dated_name_is_warned_in_the_log(dirs):
    """Escenario: Fecha futura en el nombre."""
    data, backups = dirs
    db = seed(data)
    (backups / "prices-2030-01-01.db.gz").write_bytes(b"x")
    for n in range(1, 13):
        (backups / backup_name(TODAY - timedelta(days=n))).write_bytes(b"x")
    lines, out = log_of(None)
    run_backup(db, backups, clock, out)
    assert "aviso: fecha futura en prices-2030-01-01.db.gz" in lines[0]
    assert (backups / "prices-2030-01-01.db.gz").exists()
    for n in range(0, 7):
        assert (backups / backup_name(TODAY - timedelta(days=n))).exists()


# --- Una línea de log por copia ------------------------------------------------

def test_saved_line_format():
    """Escenario: Copia guardada."""
    from src.backup.make import BackupResult

    result = BackupResult("prices-2026-10-17.db.gz", 912_400_000, 1204,
                          removed=["prices-2026-10-09.db.gz"])
    line = f"2026-10-17 04:43:00 CEST · {saved_line(result)}"
    assert line == ("2026-10-17 04:43:00 CEST · copia guardada: prices-2026-10-17.db.gz "
                    "(912,4 MB, 1.204 capturas, integridad correcta); "
                    "borradas: prices-2026-10-09.db.gz")


def test_error_line_shows_time_and_reason(dirs):
    """Escenario: Error (no se puede escribir en ./backups)."""
    data, backups = dirs
    db = seed(data)
    shutil.rmtree(backups)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert lines[0].startswith("2026-10-17 04:43:00 CEST · error en la copia: ")
    assert str(backups) in lines[0]


# --- Errores de disco como línea de log (revisión) ----------------------------

def test_temporary_cleanup_error_is_a_log_line(dirs, monkeypatch):
    data, backups = dirs
    db = seed(data)

    def broken(folder):
        raise PermissionError(13, "Permission denied", str(folder))

    monkeypatch.setattr(make, "_clean_temporaries", broken)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_FAILED
    assert lines[0].startswith("2026-10-17 04:43:00 CEST · error en la copia: no se han podido "
                               "borrar los temporales")


def test_rotation_error_keeps_the_saved_copy_and_says_so(dirs, monkeypatch):
    data, backups = dirs
    db = seed(data)

    def broken(folder, today):
        raise PermissionError(13, "Permission denied", "prices-2026-10-01.db.gz")

    monkeypatch.setattr(make, "rotate", broken)
    lines, out = log_of(None)
    assert run_backup(db, backups, clock, out) == EXIT_OK
    assert "copia guardada: prices-2026-10-17.db.gz" in lines[0]
    assert "aviso: error en la rotación" in lines[0]
    assert (backups / "prices-2026-10-17.db.gz").exists()
