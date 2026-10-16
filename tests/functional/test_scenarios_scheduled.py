"""Escenarios de `scheduled-collection` que no necesitan Docker: la comprobación
(`python -m src.ingestion.scheduled`) con reloj fijo contra el servidor local.

Requisitos: «Cuándo toca capturar», «Un fallo de la ingesta no detiene el
programador» (parte de la comprobación), «La comprobación no modifica
./data», «Zona horaria de Madrid» y «Una línea de log por comprobación».
"""

import json
import shutil
import sqlite3
from datetime import datetime, timezone

import pytest

from tests.builders import response, station
from tests.functional.test_scenarios_lock import slow_fixture, wait_for_request
from tests.functional.test_scenarios_short_response import stations_with_price
from tests.helpers import closed_port_url, db_dump, run_check, start_cli
from tests.storage_helpers import ingest, make_pending_journal, query

ACCEPT = "docker compose run --rm ingest --accept-short-response"


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def data_dir(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


def seeded(tmp_path, instant, data=None):
    db = data_dir(tmp_path) / "prices.db"
    ingest(db, data or stations_with_price(10), instant=at(instant))
    return db


def check(http_server, db, now, path="/api", body=None, fixture=None, status=200,
          interval_arg=None, **kwargs):
    extra = () if interval_arg is None else (f"--interval={interval_arg}",)
    if fixture is not None:
        url = http_server.add_fixture(path, fixture)
    elif body is not None:
        url = http_server.add(path, body=json.dumps(body), status=status)
    else:
        url = http_server.add(path, status=status, body=b"busy")
    return run_check(url, db, now, "--accept-command", ACCEPT, *extra, **kwargs)


def lines(result):
    return result.stdout.splitlines()


def snapshots(db):
    return query(db, "SELECT COUNT(*) FROM snapshots")[0][0]


def files(folder):
    return sorted(p.name for p in folder.iterdir())


# --- Una línea de log por comprobación ---------------------------------------

def test_scenario_capture_saved_line(http_server, tmp_path):
    """Escenario: Captura guardada (resumen y avisos)."""
    db = data_dir(tmp_path) / "prices.db"
    result = check(http_server, db, "2026-10-12T12:17:00Z", fixture="with_warnings.json")
    assert result.returncode == 0, result.stdout + result.stderr
    out = lines(result)
    assert out[0].startswith("2026-10-12 14:17:00 CEST · captura guardada (no hay capturas)")
    assert any(line.endswith("Avisos: 2") for line in out)
    assert sum(" · Aviso: " in line for line in out) == 2
    assert all(line.startswith("2026-10-12 14:17:00 CEST · ") for line in out)
    assert http_server.requests == {"/api": 1}


def test_scenario_not_due_line(http_server, tmp_path):
    """Escenario: No toca (última captura de hace 2 h 10 min)."""
    db = seeded(tmp_path, "2026-10-12T10:07:00Z")
    before = db_dump(db)
    result = check(http_server, db, "2026-10-12T12:17:00Z", fixture="valid_two_stations.json")
    assert result.returncode == 0
    assert lines(result) == [
        "2026-10-12 14:17:00 CEST · no toca capturar: última captura hace 2 h 10 min (intervalo 6 h)"
    ]
    assert http_server.requests == {}
    assert db_dump(db) == before


@pytest.fixture(scope="module")
def seed_12000(tmp_path_factory):
    db = tmp_path_factory.mktemp("seed") / "prices.db"
    ingest(db, stations_with_price(12_000), instant=at("2026-10-12T02:17:00Z"))
    return db


def test_scenario_short_response_line(http_server, tmp_path, seed_12000):
    """Escenario: Respuesta corta (cifras, porcentaje y comando para aceptarla)."""
    db = data_dir(tmp_path) / "prices.db"
    shutil.copy(seed_12000, db)
    before = db_dump(db)
    result = check(http_server, db, "2026-10-12T12:17:00Z", body=stations_with_price(9_000))
    assert lines(result) == [
        "2026-10-12 14:17:00 CEST · respuesta corta, no se ha guardado: 9.000 estaciones con "
        "precio frente a 12.000 de la última captura (75,0 %). Si es correcta, guárdala con: "
        f"{ACCEPT}"
    ]
    assert db_dump(db) == before


def test_scenario_error_line(tmp_path):
    """Escenario: Error (no se puede conectar con la API)."""
    db = data_dir(tmp_path) / "prices.db"
    result = run_check(closed_port_url(), db, "2026-10-12T12:17:00Z")
    assert result.returncode != 0
    assert lines(result)[0].startswith("2026-10-12 14:17:00 CEST · error: ")
    assert "no se ha podido conectar con la API" in result.stdout


def test_invalid_interval_line(http_server, tmp_path):
    """Escenario: Intervalo no válido (la comprobación no pide nada)."""
    db = data_dir(tmp_path) / "prices.db"
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_check(url, db, "2026-10-12T12:17:00Z", "--interval", "seis")
    assert result.returncode != 0
    assert lines(result) == [
        "2026-10-12 14:17:00 CEST · configuración no válida: CAPTURE_INTERVAL_HOURS no válido: "
        "'seis'; se admiten horas enteras de 1 a 24; no se hace ninguna petición"
    ]
    assert http_server.requests == {}
    assert files(db.parent) == []


def test_missing_data_folder_is_not_created(http_server, tmp_path):
    db = tmp_path / "data" / "prices.db"
    result = check(http_server, db, "2026-10-12T12:17:00Z", fixture="valid_two_stations.json")
    assert result.returncode != 0
    assert "no existe la carpeta de datos" in result.stdout
    assert not (tmp_path / "data").exists()
    assert http_server.requests == {}


# --- Cuándo toca capturar -----------------------------------------------------

def test_scenario_manual_capture_during_check(http_server, tmp_path):
    """Escenario: Captura manual durante la comprobación."""
    # Referencia de 2 estaciones, como la respuesta de la ingesta manual.
    db = seeded(tmp_path, "2026-10-12T05:17:00Z", stations_with_price(2))  # hace 7 h
    manual = start_cli(slow_fixture(http_server, "/manual", 2), db)
    try:
        wait_for_request(http_server, "/manual")
        result = check(http_server, db, "2026-10-12T12:17:00Z", fixture="valid_two_stations.json")
        assert lines(result) == ["2026-10-12 14:17:00 CEST · otra ingesta en curso; no se captura"]
        assert http_server.count("/api") == 0
        manual.communicate(timeout=30)
        assert manual.returncode == 0
    finally:
        manual.kill()
    # La siguiente comprobación ya no toca: la captura manual es reciente.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = check(http_server, db, now, path="/api2", fixture="valid_two_stations.json")
    assert "no toca capturar" in result.stdout
    assert http_server.count("/api2") == 0


def test_scenario_pending_journal(http_server, tmp_path):
    """Escenario: Diario pendiente de una ingesta cortada."""
    db = seeded(tmp_path, "2026-10-12T11:17:00Z")  # hace 1 h
    first = sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1"))
    make_pending_journal(db)
    result = check(http_server, db, "2026-10-12T12:17:00Z", body=stations_with_price(10))
    assert result.returncode == 0, result.stdout
    out = lines(result)
    assert out[0] == ("2026-10-12 14:17:00 CEST · la última ingesta quedó a medias; "
                      "se lanza una nueva")
    assert out[1].startswith("2026-10-12 14:17:00 CEST · captura guardada")
    assert snapshots(db) == 2
    assert sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1")) == first
    assert files(db.parent) == ["prices.db"]


def test_scenario_capture_far_in_the_future(http_server, tmp_path):
    """Escenario: Última captura muy en el futuro (aviso y captura)."""
    db = seeded(tmp_path, "2030-01-01T00:00:00Z")
    result = check(http_server, db, "2026-10-12T12:17:00Z", body=stations_with_price(10))
    out = lines(result)
    assert "fecha anómala (2030-01-01T00:00:00Z)" in out[0]
    assert "captura guardada" in out[1]
    assert snapshots(db) == 2


# --- Un fallo de la ingesta no detiene el programador ------------------------

def test_scenario_api_down_then_retry(http_server, tmp_path):
    """Escenario: API caída (y la siguiente comprobación vuelve a pedir)."""
    db = seeded(tmp_path, "2026-10-12T01:17:00Z")
    before = db_dump(db)
    result = check(http_server, db, "2026-10-12T08:17:00Z", status=503)
    assert "error: la descarga ha fallado con HTTP 503" in result.stdout
    assert db_dump(db) == before
    result = check(http_server, db, "2026-10-12T09:17:00Z", status=503)
    assert http_server.requests == {"/api": 2}


def test_scenario_several_failures_one_request_per_check(http_server, tmp_path):
    """Escenario: Varios fallos seguidos (una petición por comprobación)."""
    db = seeded(tmp_path, "2026-10-12T01:17:00Z")
    for hour in ("08", "09", "10", "11"):
        check(http_server, db, f"2026-10-12T{hour}:17:00Z", status=503)
    assert http_server.requests == {"/api": 4}


def test_scenario_retry_after_short_response(http_server, tmp_path):
    """Escenario: Reintento tras una respuesta corta."""
    db = seeded(tmp_path, "2026-10-12T01:17:00Z")
    result = check(http_server, db, "2026-10-12T08:17:00Z", body=stations_with_price(7))
    assert "respuesta corta" in result.stdout
    result = check(http_server, db, "2026-10-12T09:17:00Z", path="/api2", body=stations_with_price(10))
    assert "captura guardada" in result.stdout
    assert http_server.requests == {"/api": 1, "/api2": 1}
    assert snapshots(db) == 2


# --- La comprobación no modifica ./data --------------------------------------

def test_scenario_empty_data_after_503(http_server, tmp_path):
    """Escenario: Comprobación con la base inexistente y sin poder capturar."""
    db = data_dir(tmp_path) / "prices.db"
    check(http_server, db, "2026-10-12T12:17:00Z", status=503)
    assert files(db.parent) == []


def test_scenario_only_prices_db_remains(http_server, tmp_path):
    """Escenario: Solo queda prices.db (no toca, falla y guarda)."""
    db = seeded(tmp_path, "2026-10-12T10:17:00Z")
    check(http_server, db, "2026-10-12T12:17:00Z", path="/a", body=stations_with_price(10))
    assert files(db.parent) == ["prices.db"]
    check(http_server, db, "2026-10-12T17:17:00Z", path="/b", status=503)
    assert files(db.parent) == ["prices.db"]
    check(http_server, db, "2026-10-12T18:17:00Z", path="/c", body=stations_with_price(10))
    assert files(db.parent) == ["prices.db"]
    assert snapshots(db) == 2


def test_scenario_unknown_schema_version(http_server, tmp_path):
    """Escenario: Base de datos con versión de estructura desconocida."""
    db = data_dir(tmp_path) / "prices.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before = db.read_bytes()
    result = check(http_server, db, "2026-10-12T12:17:00Z", fixture="valid_two_stations.json")
    assert "versión de base de datos no compatible: 7" in result.stdout
    assert http_server.requests == {}
    assert db.read_bytes() == before
    assert files(db.parent) == ["prices.db"]


def test_scenario_file_that_is_not_a_database(http_server, tmp_path):
    """Escenario: Archivo que no es una base de datos."""
    db = data_dir(tmp_path) / "prices.db"
    db.write_text("hola")
    result = check(http_server, db, "2026-10-12T12:17:00Z", fixture="valid_two_stations.json")
    assert "no se ha podido leer la base de datos" in result.stdout
    assert http_server.requests == {}
    assert db.read_text() == "hola"
    assert files(db.parent) == ["prices.db"]


# --- Zona horaria de Madrid ---------------------------------------------------

@pytest.mark.parametrize(("now", "madrid"), [
    ("2026-07-15T12:17:00Z", "2026-07-15 14:17:00 CEST"),
    ("2026-12-15T13:17:00Z", "2026-12-15 14:17:00 CET"),
])
def test_scenario_summer_and_winter_time(http_server, tmp_path, now, madrid):
    """Escenarios: Horario de verano y Horario de invierno."""
    db = data_dir(tmp_path) / "prices.db"
    result = check(http_server, db, now, body=stations_with_price(2))
    assert lines(result)[0].startswith(f"{madrid} · captura guardada")
    assert query(db, "SELECT downloaded_at FROM snapshots") == [(now,)]


def test_scenario_october_time_change(http_server, tmp_path):
    """Escenario: Cambio de hora de octubre (la segunda 02:17 no toca)."""
    db = data_dir(tmp_path) / "prices.db"
    first = check(http_server, db, "2026-10-25T00:17:00Z", path="/a", body=stations_with_price(2))
    assert lines(first)[0].startswith("2026-10-25 02:17:00 CEST · captura guardada")
    second = check(http_server, db, "2026-10-25T01:17:00Z", path="/b", body=stations_with_price(2))
    assert lines(second)[0].startswith("2026-10-25 02:17:00 CET · no toca capturar")
    assert snapshots(db) == 1
    assert http_server.requests == {"/a": 1}


def test_scenario_march_time_change(http_server, tmp_path):
    """Escenario: Cambio de hora de marzo (lógica con reloj inyectado)."""
    db = data_dir(tmp_path) / "prices.db"
    for i, (now, madrid) in enumerate([
        ("2027-03-27T23:17:00Z", "2027-03-28 00:17:00 CET"),
        ("2027-03-28T00:17:00Z", "2027-03-28 01:17:00 CET"),
        ("2027-03-28T01:17:00Z", "2027-03-28 03:17:00 CEST"),
        ("2027-03-28T02:17:00Z", "2027-03-28 04:17:00 CEST"),
    ]):
        result = check(http_server, db, now, path=f"/p{i}", body=stations_with_price(2))
        assert lines(result)[0].startswith(f"{madrid} · ")
    assert snapshots(db) == 1
    assert http_server.total_requests() == 1


# --- Intervalo configurable y recuperación ------------------------------------

@pytest.mark.parametrize("interval", [" 6 ", "06"])
def test_scenario_accepted_interval_forms(http_server, tmp_path, interval):
    """Escenario: Formas admitidas (` 6 ` y `06` valen 6 horas): con la última
    captura de hace 5 h no toca y con la de hace 5 h 45 min sí."""
    db = seeded(tmp_path, "2026-10-12T07:17:00Z")
    result = check(http_server, db, "2026-10-12T12:17:00Z", path="/a",
                   fixture="valid_two_stations.json", interval_arg=interval)
    assert lines(result) == [
        "2026-10-12 14:17:00 CEST · no toca capturar: última captura hace 5 h 0 min (intervalo 6 h)"
    ]
    result = check(http_server, db, "2026-10-12T13:02:00Z", path="/b",
                   body=stations_with_price(10), interval_arg=interval)
    assert lines(result)[0].startswith("2026-10-12 15:02:00 CEST · captura guardada "
                                       "(última captura hace 5 h 45 min, intervalo 6 h)")
    assert http_server.requests == {"/b": 1}


def test_scenario_recovery_after_restart(http_server, tmp_path):
    """Escenario: Recuperación tras un reinicio: última captura a las 02:17 de
    Madrid y comprobación de arranque a las 11:05 → captura sin esperar a las 11:17."""
    db = seeded(tmp_path, "2026-10-12T00:17:00Z")
    result = check(http_server, db, "2026-10-12T09:05:00Z", body=stations_with_price(10))
    assert result.returncode == 0, result.stdout + result.stderr
    assert lines(result)[0].startswith("2026-10-12 11:05:00 CEST · captura guardada "
                                       "(última captura hace 8 h 48 min, intervalo 6 h)")
    assert snapshots(db) == 2
    assert http_server.requests == {"/api": 1}
