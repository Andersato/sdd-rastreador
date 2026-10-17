"""Escenarios de `database-backup` y `price-ingestion` que necesitan el flujo
completo de una comprobación del programador (captura y copia en la misma
comprobación) o dos procesos reales a la vez, sin Docker.

- La comprobación es la de `container/check.py` (`main`) con las rutas del
  contenedor sustituidas por carpetas temporales; la captura la hace la
  comprobación real (`python -m src.ingestion.scheduled`) contra el servidor
  local, con reloj fijo.
- La copia es la real (`run_backup` / `make_backup`).
- Para que una copia "esté volcando" o "esté comprimiendo" se ralentiza ese
  paso dentro de un proceso aparte; el bloqueo es el `flock` real.
"""

import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import src.backup.make as make
from src.backup.make import make_backup
from src.backup.rotation import backup_name
from src.backup.scheduled import EXIT_BUSY, EXIT_OK, run_backup
from src.backup.verify import verify_gz
from tests.builders import response, station
from tests.functional.test_scenarios_backup import folder_state, holder  # noqa: F401
from tests.helpers import REPO_ROOT, run_check, run_cli
from tests.storage_helpers import ingest, make_pending_journal, query

MADRID = ZoneInfo("Europe/Madrid")
CONTAINER = REPO_ROOT / "container"
BUSY_MESSAGE = "ya hay otra ingesta o copia en curso"


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(instant):
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


BODY = response(station("S0", **{"Precio Gasoleo A": "1,459"}),
                station("S1", **{"Precio Gasoleo A": "1,459"}))


def seed_at(db, *instants):
    for instant in instants:
        ingest(db, BODY, instant=instant)


def snapshots_in(gz, work):
    out = work / f"copia-{time.monotonic_ns()}.db"
    with gzip.open(gz) as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return query(out, "SELECT COUNT(*) FROM snapshots")[0][0]


@pytest.fixture
def dirs(tmp_path):
    data, backups, tmp = tmp_path / "data", tmp_path / "backups", tmp_path / "tmp"
    for folder in (data, backups, tmp):
        folder.mkdir()
    return data, backups, tmp / "backup-pending"


@pytest.fixture
def check(monkeypatch, dirs):
    """`container/check.py` con las rutas del contenedor en carpetas temporales."""
    monkeypatch.syspath_prepend(str(CONTAINER))
    spec = importlib.util.spec_from_file_location("container_check_flow", CONTAINER / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data, backups, marker = dirs
    monkeypatch.setattr(module, "DB_PATH", str(data / "prices.db"))
    monkeypatch.setattr(module, "BACKUPS_DIR", str(backups))
    monkeypatch.setattr(module, "MARKER", str(marker))
    return module


ENABLED = {"COLLECTION_ENABLED": "true"}


def hourly_check(check, url, db, now, startup=False):
    """Una comprobación de `check.py`: la captura real contra `url` y, después,
    la copia de arranque o el reintento, todo con el reloj en `now`."""

    def run(args):
        assert f"--db={db}" in args
        result = run_check(url, db, iso(now))
        print(result.stdout, end="", flush=True)
        return result.returncode

    return check.main(501, 20, ENABLED, run=run, now=now, startup=startup)


# --- Copia al arrancar si la última es antigua ---------------------------------

def test_startup_with_capture_due_ingests_first_then_copies(check, dirs, http_server, capsys,
                                                           tmp_path):
    """Escenario: Arranque con captura pendiente: toca capturar y la última copia
    tiene 30 horas; primero la ingesta y después la copia, que incluye la captura
    nueva."""
    data, backups, _ = dirs
    now = utc("2026-10-17T09:00:00Z")
    db = data / "prices.db"
    seed_at(db, now - timedelta(hours=13), now - timedelta(hours=7))
    old = backups / backup_name((now - timedelta(days=1)).astimezone(MADRID).date())
    old.write_bytes(b"anterior")
    os.utime(old, ((now - timedelta(hours=30)).timestamp(),) * 2)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    hourly_check(check, url, db, now, startup=True)
    out = capsys.readouterr().out
    assert http_server.requests == {"/api": 1}
    assert out.index("captura guardada") < out.index("copia guardada: prices-2026-10-17.db.gz")
    assert "3 capturas, integridad correcta" in out
    assert snapshots_in(backups / "prices-2026-10-17.db.gz", tmp_path) == 3


# --- Copia en caliente: copia pendiente y reintentos ---------------------------

def test_pending_copy_and_capture_due_in_the_same_check(check, dirs, http_server, holder,
                                                        capsys, tmp_path):
    """Escenarios: Ingesta en curso que no termina (la copia de las 05:17) y Orden
    en una comprobación con copia pendiente: la copia del 2026-10-17 quedó
    pendiente a las 04:43 por el bloqueo y a las 05:17 también toca capturar:
    primero la ingesta y después la copia, que incluye la captura nueva."""
    data, backups, marker = dirs
    db = data / "prices.db"
    at_0443 = utc("2026-10-17T02:43:00Z")
    seed_at(db, at_0443 - timedelta(hours=12), at_0443 - timedelta(hours=7))
    before = folder_state(data)
    proc = holder(data)
    lines = []
    assert run_backup(db, backups, lambda: at_0443, lines.append, marker=marker,
                      wait_s=1) == EXIT_BUSY
    assert os.listdir(backups) == [] and folder_state(data) == before
    proc.kill()
    proc.wait()
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    hourly_check(check, url, db, utc("2026-10-17T03:17:00Z"))
    out = capsys.readouterr().out
    assert out.index("captura guardada") < out.index("copia guardada: prices-2026-10-17.db.gz")
    assert snapshots_in(backups / "prices-2026-10-17.db.gz", tmp_path) == 3
    assert not marker.exists()
    # Las siguientes comprobaciones de ese día ya no intentan copiar.
    hourly_check(check, url, db, utc("2026-10-17T04:17:00Z"))
    assert "copia" not in capsys.readouterr().out
    assert sorted(os.listdir(backups)) == ["prices-2026-10-17.db.gz"]


def test_interrupted_ingestion_is_resolved_and_copied_in_the_same_check(check, dirs, http_server,
                                                                       capsys, tmp_path):
    """Escenario: Ingesta anterior a medias: a las 04:43 hay un `prices.db-journal`;
    no se copia y queda pendiente; a las 05:17 toca capturar por la ingesta a
    medias (la última captura completa es de hace 1 h), la ingesta resuelve el
    diario y justo después, en esa misma comprobación, se hace la copia."""
    data, backups, marker = dirs
    db = data / "prices.db"
    seed_at(db, utc("2026-10-16T14:17:00Z"), utc("2026-10-16T20:17:00Z"),
            utc("2026-10-17T02:17:00Z"))
    make_pending_journal(db)
    before = folder_state(data)
    assert "prices.db-journal" in before
    lines = []
    assert run_backup(db, backups, lambda: utc("2026-10-17T02:43:00Z"), lines.append,
                      marker=marker) == EXIT_BUSY
    assert "copia pendiente: la última ingesta quedó a medias" in lines[0]
    assert folder_state(data) == before and os.listdir(backups) == []
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    hourly_check(check, url, db, utc("2026-10-17T03:17:00Z"))
    out = capsys.readouterr().out
    assert http_server.requests == {"/api": 1}
    assert out.index("captura guardada") < out.index("copia guardada: prices-2026-10-17.db.gz")
    assert sorted(os.listdir(data)) == ["prices.db"]
    assert query(db, "SELECT COUNT(*) FROM snapshots")[0][0] == 4
    assert snapshots_in(backups / "prices-2026-10-17.db.gz", tmp_path) == 4
    assert not marker.exists()


def test_interrupted_ingestion_not_resolved_retries_at_the_next_check(check, dirs, http_server,
                                                                     capsys):
    """Escenario: Ingesta a medias que no se resuelve: la ingesta de las 05:17 falla
    con HTTP 503 antes de guardar; la copia sigue pendiente, no se crea ninguna y
    se vuelve a intentar a las 06:17."""
    data, backups, marker = dirs
    db = data / "prices.db"
    seed_at(db, utc("2026-10-16T20:17:00Z"), utc("2026-10-17T02:17:00Z"))
    make_pending_journal(db)
    assert run_backup(db, backups, lambda: utc("2026-10-17T02:43:00Z"), [].append,
                      marker=marker) == EXIT_BUSY
    failing = http_server.add("/fail", status=503)
    hourly_check(check, failing, db, utc("2026-10-17T03:17:00Z"))
    out = capsys.readouterr().out
    assert http_server.count("/fail") == 1
    assert "copia pendiente: la última ingesta quedó a medias" in out
    assert os.listdir(backups) == [] and marker.exists()
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    hourly_check(check, url, db, utc("2026-10-17T04:17:00Z"))
    out = capsys.readouterr().out
    assert "copia guardada: prices-2026-10-17.db.gz" in out
    assert not marker.exists()


# --- La ingesta frente a una copia en curso ------------------------------------

SLOW_STEP = """
import sys, time
from datetime import datetime, timezone
from pathlib import Path
import src.backup.make as make
from src.backup.scheduled import run_backup

step, seconds = sys.argv[3], float(sys.argv[4])
original = getattr(make, step)

def slow(*args):
    print(step, flush=True)
    time.sleep(seconds)
    return original(*args)

setattr(make, step, slow)
clock = lambda: datetime(2026, 10, 17, 2, 43, tzinfo=timezone.utc)
code = run_backup(Path(sys.argv[1]), Path(sys.argv[2]), clock, print, wait_s=60)
sys.exit(code)
"""


@pytest.fixture
def slow_copy():
    """Copia real en un proceso aparte, con el paso `step` de `make.py` ralentizado."""
    procs = []

    def start(db, backups, step, seconds, wait_for_step=True):
        proc = subprocess.Popen([sys.executable, "-c", SLOW_STEP, str(db), str(backups), step,
                                 str(seconds)], cwd=REPO_ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        procs.append(proc)
        if wait_for_step:
            assert proc.stdout.readline().strip() == step
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()


def test_ingestion_during_a_copy_dump_is_rejected(dirs, http_server, slow_copy):
    """Escenario (price-ingestion): Ingesta durante una copia: con la copia
    volcando la base (tiene el bloqueo de ./data), la ingesta termina en menos de
    2 s con código distinto de 0 y "ya hay otra ingesta o copia en curso", sin
    pedir nada, y la copia termina con normalidad."""
    data, backups, _ = dirs
    db = data / "prices.db"
    seed_at(db, utc("2026-10-17T01:00:00Z"))
    copy = slow_copy(db, backups, "_dump", 4)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    start = time.monotonic()
    result = run_cli(url, db)
    assert time.monotonic() - start < 2 + 1  # + arranque del intérprete
    assert result.returncode != 0
    assert BUSY_MESSAGE in result.stderr
    assert http_server.requests == {}
    out, err = copy.communicate(timeout=60)
    assert copy.returncode == 0, out + err
    assert "copia guardada: prices-2026-10-17.db.gz" in out


def test_hourly_check_during_the_dump_retries_at_the_next_check(dirs, http_server, slow_copy):
    """Escenario: Comprobación horaria durante el volcado (con una copia real):
    deja "otra ingesta o copia en curso" sin ninguna petición, y en la
    siguiente comprobación vuelve a tocar y captura."""
    data, backups, _ = dirs
    db = data / "prices.db"
    seed_at(db, utc("2026-10-17T04:00:00Z"))
    copy = slow_copy(db, backups, "_dump", 4)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    busy = run_check(url, db, "2026-10-17T10:17:00Z")
    assert busy.stdout.strip().endswith("otra ingesta o copia en curso; no se captura")
    assert http_server.requests == {}
    copy.communicate(timeout=60)
    assert copy.returncode == 0
    after = run_check(url, db, "2026-10-17T11:17:00Z")
    assert "captura guardada" in after.stdout, after.stdout + after.stderr
    assert http_server.requests == {"/api": 1}


def test_hourly_check_during_compression_captures_and_copy_keeps_dumped_state(
        dirs, http_server, slow_copy, tmp_path):
    """Escenarios: Comprobación horaria durante la verificación o la compresión e
    Ingesta durante la verificación de otra copia: la ingesta se hace con
    normalidad y la copia termina con las capturas que había al volcar."""
    data, backups, _ = dirs
    db = data / "prices.db"
    seed_at(db, utc("2026-10-17T01:00:00Z"), utc("2026-10-17T04:00:00Z"))
    copy = slow_copy(db, backups, "_compress", 4)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    start = time.monotonic()
    result = run_check(url, db, "2026-10-17T10:17:00Z")
    assert time.monotonic() - start < 4, "la ingesta ha esperado a la copia"
    assert "captura guardada" in result.stdout, result.stdout + result.stderr
    assert query(db, "SELECT COUNT(*) FROM snapshots")[0][0] == 3
    out, err = copy.communicate(timeout=60)
    assert copy.returncode == 0, out + err
    assert snapshots_in(backups / "prices-2026-10-17.db.gz", tmp_path) == 2


# --- Una sola copia a la vez ----------------------------------------------------

def test_two_copies_at_the_same_time_run_one_after_the_other(dirs, slow_copy, tmp_path):
    """Escenario: Copia a mano a la vez que la diaria: cada una tarda (aquí) unos
    2 s; la segunda empieza cuando termina la primera, las dos terminan bien y
    queda un único archivo del día, verificado."""
    data, backups, _ = dirs
    db = data / "prices.db"
    seed_at(db, utc("2026-10-17T01:00:00Z"))
    start = time.monotonic()
    first = slow_copy(db, backups, "_compress", 2)
    second = slow_copy(db, backups, "_compress", 2, wait_for_step=False)
    outputs = [proc.communicate(timeout=60) for proc in (first, second)]
    elapsed = time.monotonic() - start
    assert [first.returncode, second.returncode] == [0, 0], outputs
    assert elapsed >= 4 - 0.5, "las dos copias se han solapado"
    assert sorted(os.listdir(backups)) == ["prices-2026-10-17.db.gz"]
    assert verify_gz(backups / "prices-2026-10-17.db.gz", tmp_path).snapshots == 1


# --- Cambios de hora --------------------------------------------------------------

@pytest.mark.parametrize("day", ["2026-10-25", "2027-03-28"])
def test_0443_exists_once_on_dst_change_days(day):
    """Escenario: Cambios de hora (lógica con reloj inyectado): las 04:43 de
    Madrid existen y son un único instante los días del cambio de hora (que
    ocurre entre las 02:00 y las 03:00), así que la línea `43 4 * * *` del
    crontab dispara exactamente una vez y la copia lleva la fecha de ese día."""
    local = datetime.fromisoformat(f"{day}T04:43:00").replace(tzinfo=MADRID)
    instants = {local.replace(fold=fold).astimezone(timezone.utc) for fold in (0, 1)}
    assert len(instants) == 1  # ni ambigua (dos veces) ni inexistente
    (instant,) = instants
    assert instant.astimezone(MADRID).strftime("%H:%M") == "04:43"
    assert backup_name(make.madrid_date(instant)) == f"prices-{day}.db.gz"
    # Ninguna otra hora de ese día cae a las 04:43 de Madrid.
    start = datetime.fromisoformat(f"{day}T00:00:00").replace(tzinfo=MADRID)
    minutes = [start.astimezone(timezone.utc) + timedelta(minutes=m) for m in range(25 * 60)]
    hits = [m for m in minutes if m.astimezone(MADRID).strftime("%Y-%m-%d %H:%M")
            == f"{day} 04:43"]
    assert hits == [instant]
