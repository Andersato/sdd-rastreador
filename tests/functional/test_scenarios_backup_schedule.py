"""Escenarios de `database-backup` sobre cuándo se copia (D6): regla de 26 h de la
comprobación de arranque y reintentos de una copia pendiente con la marca.

La marca va en una carpeta aparte (en el programador, `/tmp/backup-pending`):
nunca en `./data` ni en `./backups`.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from src.backup.rotation import backup_name
from src.backup.scheduled import EXIT_BUSY, EXIT_OK, retry_pending, run_backup, startup_due
from tests.functional.test_scenarios_backup import corrupt_index, folder_state, holder, seed  # noqa: F401
from tests.storage_helpers import ingest, make_pending_journal

MADRID_0443 = datetime(2026, 10, 16, 2, 43, tzinfo=timezone.utc)  # 2026-10-16 04:43 CEST


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@pytest.fixture
def dirs(tmp_path):
    data, backups, tmp = tmp_path / "data", tmp_path / "backups", tmp_path / "tmp"
    for folder in (data, backups, tmp):
        folder.mkdir()
    return data, backups, tmp / "backup-pending"


def copy_made_at(backups, instant):
    """Copia del día de `instant` con `mtime` = `instant`."""
    day = instant.astimezone(timezone(timedelta(hours=2))).date()
    path = backups / backup_name(day)
    path.write_bytes(b"x")
    os.utime(path, (instant.timestamp(), instant.timestamp()))
    return path


# --- Copia al arrancar si la última es antigua --------------------------------

def test_server_off_for_more_than_a_day(dirs):
    """Escenario: Servidor apagado más de un día (51 h 17 min)."""
    _, backups, _ = dirs
    copy_made_at(backups, MADRID_0443)
    assert startup_due(backups, at("2026-10-18T06:00:00Z"))  # 08:00 de Madrid


def test_off_only_at_backup_time(dirs):
    """Escenario: Apagado solo a la hora de la copia (24 h 17 min)."""
    _, backups, _ = dirs
    copy_made_at(backups, MADRID_0443)
    assert not startup_due(backups, at("2026-10-17T03:00:00Z"))  # 05:00 de Madrid


def test_exactly_on_the_limit(dirs):
    """Escenario: Justo en el límite (26 h exactas)."""
    _, backups, _ = dirs
    copy_made_at(backups, MADRID_0443)
    assert not startup_due(backups, MADRID_0443 + timedelta(hours=26))
    assert startup_due(backups, MADRID_0443 + timedelta(hours=26, seconds=1))


def test_without_copies(dirs):
    """Escenario: Sin copias (los archivos ajenos no cuentan)."""
    _, backups, _ = dirs
    (backups / "notas.txt").write_text("x")
    assert startup_due(backups, MADRID_0443)


def test_most_recent_by_name_date_not_by_file_date(dirs):
    _, backups, _ = dirs
    old = copy_made_at(backups, MADRID_0443 - timedelta(days=3))
    recent = copy_made_at(backups, MADRID_0443)
    os.utime(old, (time.time(), time.time()))  # la vieja, tocada ahora
    assert recent.name > old.name
    assert not startup_due(backups, MADRID_0443 + timedelta(hours=2))


# --- Reintentos de una copia pendiente -----------------------------------------

def clock_at(text):
    instant = at(text)
    return lambda: instant


def test_retries_during_the_day_until_the_lock_is_free(dirs, holder):
    """Escenarios: Ingesta en curso que no termina y Reintentos durante el día."""
    data, backups, marker = dirs
    db = seed(data)
    proc = holder(data)
    out = []
    assert run_backup(db, backups, clock_at("2026-10-17T02:43:00Z"), out.append,
                      marker=marker, wait_s=1) == EXIT_BUSY
    assert marker.read_text() == "2026-10-17"
    assert retry_pending(db, backups, clock_at("2026-10-17T03:17:00Z"), out.append,
                         marker, wait_s=1) == EXIT_BUSY  # 05:17, sigue ocupado
    proc.kill()
    proc.wait()
    assert retry_pending(db, backups, clock_at("2026-10-17T04:17:00Z"), out.append,
                         marker, wait_s=1) == EXIT_OK  # 06:17
    assert (backups / "prices-2026-10-17.db.gz").exists()
    assert not marker.exists()
    assert retry_pending(db, backups, clock_at("2026-10-17T05:17:00Z"), out.append,
                         marker) is None  # las siguientes de ese día ya no copian
    assert sorted(os.listdir(backups)) == ["prices-2026-10-17.db.gz"]


def test_pending_until_the_end_of_the_day(dirs):
    """Escenario: Pendiente hasta el final del día."""
    data, backups, marker = dirs
    db = seed(data)
    marker.write_text("2026-10-17")
    out = []
    # 00:17 del 2026-10-18 en Madrid
    assert retry_pending(db, backups, clock_at("2026-10-17T22:17:00Z"), out.append, marker) is None
    assert not marker.exists()
    assert os.listdir(backups) == []


def test_other_failures_are_not_retried(dirs):
    """Escenario: Otros fallos no se reintentan."""
    data, backups, marker = dirs
    db = seed(data)
    corrupt_index(db)
    out = []
    assert run_backup(db, backups, clock_at("2026-10-17T02:43:00Z"), out.append,
                      marker=marker) != EXIT_OK
    assert not marker.exists()
    assert retry_pending(db, backups, clock_at("2026-10-17T03:17:00Z"), out.append, marker) is None


def test_interrupted_ingestion_not_resolved_stays_pending(dirs):
    """Escenario: Ingesta a medias que no se resuelve (la de las 05:17 falla y
    el diario sigue ahí)."""
    data, backups, marker = dirs
    db = seed(data)
    make_pending_journal(db)
    out = []
    assert run_backup(db, backups, clock_at("2026-10-17T02:43:00Z"), out.append,
                      marker=marker) == EXIT_BUSY
    assert retry_pending(db, backups, clock_at("2026-10-17T03:17:00Z"), out.append,
                         marker) == EXIT_BUSY
    assert marker.exists() and os.listdir(backups) == []
    assert "la última ingesta quedó a medias" in out[-1]


def test_manual_copy_after_the_marker_skips_the_retry(dirs):
    """D6: una copia de hoy posterior a la marca (a mano) hace innecesario el reintento."""
    data, backups, marker = dirs
    db = seed(data)
    marker.write_text("2026-10-17")
    past = time.time() - 60
    os.utime(marker, (past, past))
    run_backup(db, backups, clock_at("2026-10-17T03:00:00Z"), [].append)  # a mano
    before = folder_state(backups)
    out = []
    assert retry_pending(db, backups, clock_at("2026-10-17T03:17:00Z"), out.append,
                         marker) == EXIT_OK
    assert "copia pendiente ya hecha" in out[0]
    assert folder_state(backups) == before
    assert not marker.exists()


def test_marker_never_goes_to_data_or_backups(dirs, holder):
    data, backups, marker = dirs
    db = seed(data)
    holder(data)
    before = folder_state(data)
    run_backup(db, backups, clock_at("2026-10-17T02:43:00Z"), [].append, marker=marker, wait_s=1)
    assert folder_state(data) == before
    assert os.listdir(backups) == []
    assert marker.parent.name == "tmp"
