"""Escenarios de «Respuesta con demasiadas pocas estaciones», «Aceptar a mano una
respuesta corta» y «Formato de las cifras en los mensajes», con la CLI real.

Las respuestas de miles de estaciones se generan al vuelo (no se guardan en
`tests/fixtures/`). La base de referencia de 12.000 estaciones se crea una vez
por módulo y se copia en cada test.
"""

import json
import shutil
import sqlite3
from datetime import datetime, timezone

import pytest

from src.ingestion import storage
from tests.builders import response, station
from tests.helpers import db_dump, run_cli
from tests.storage_helpers import ingest, make_pending_journal, query

EXIT_SHORT_RESPONSE = 4
SEED_INSTANT = datetime(2026, 10, 12, 8, 17, 40, tzinfo=timezone.utc)


def stations_with_price(n, empty=0, prefix="E"):
    """`n` estaciones con un precio válido más `empty` sin ningún precio."""
    with_price = [station(f"{prefix}{i}", **{"Precio Gasoleo A": "1,459"}) for i in range(n)]
    without = [station(f"{prefix}V{i}", **{"Precio Gasoleo A": ""}) for i in range(empty)]
    return response(*with_price, *without)


def serve(http_server, data, path="/api"):
    return http_server.add(path, body=json.dumps(data))


@pytest.fixture(scope="module")
def seed_12000(tmp_path_factory):
    db = tmp_path_factory.mktemp("seed") / "prices.db"
    ingest(db, stations_with_price(12_000), instant=SEED_INSTANT)
    return db


@pytest.fixture
def db_12000(seed_12000, tmp_path):
    db = tmp_path / "prices.db"
    shutil.copy(seed_12000, db)
    return db


def db_with(tmp_path, data):
    db = tmp_path / "prices.db"
    ingest(db, data, instant=SEED_INSTANT)
    return db


def snapshots(db):
    return query(db, "SELECT COUNT(*) FROM snapshots")[0][0]


# --- Respuesta con demasiadas pocas estaciones --------------------------------

def test_scenario_short_response(http_server, db_12000):
    """Escenario: Respuesta corta."""
    before = db_dump(db_12000)
    result = run_cli(serve(http_server, stations_with_price(9_000)), db_12000)
    assert result.returncode == EXIT_SHORT_RESPONSE
    assert result.stderr.strip() == (
        "Error: respuesta sospechosamente corta: 9.000 estaciones con precio frente a "
        "12.000 de la última captura (75,0 %); no se ha guardado. "
        "Si es correcta, guárdala con --accept-short-response"
    )
    assert http_server.requests == {"/api": 1}
    assert db_dump(db_12000) == before


def test_scenario_exactly_80_percent(http_server, db_12000):
    """Escenario: Justo el 80 %."""
    result = run_cli(serve(http_server, stations_with_price(9_600)), db_12000)
    assert result.returncode == 0, result.stderr
    assert snapshots(db_12000) == 2


def test_scenario_one_station_below_80_percent(http_server, db_12000):
    """Escenario: Una estación por debajo del 80 %."""
    before = db_dump(db_12000)
    result = run_cli(serve(http_server, stations_with_price(9_599)), db_12000)
    assert result.returncode == EXIT_SHORT_RESPONSE
    assert "(79,9 %)" in result.stderr
    assert db_dump(db_12000) == before


def test_scenario_more_stations_than_last_time(http_server, db_12000):
    """Escenario: Más estaciones que la última vez."""
    result = run_cli(serve(http_server, stations_with_price(12_150)), db_12000)
    assert result.returncode == 0, result.stderr
    assert snapshots(db_12000) == 2


def test_scenario_stations_without_price_do_not_count(http_server, tmp_path):
    """Escenario: Estaciones sin precio no cuentan."""
    db = db_with(tmp_path, stations_with_price(10))
    before = db_dump(db)
    result = run_cli(serve(http_server, stations_with_price(7, empty=3)), db)
    assert result.returncode == EXIT_SHORT_RESPONSE
    assert "7 estaciones con precio frente a 10 de la última captura (70,0 %)" in result.stderr
    assert db_dump(db) == before


@pytest.mark.parametrize("existing", [False, True], ids=["sin-base", "base-sin-capturas"])
def test_scenario_first_capture(http_server, tmp_path, existing):
    """Escenario: Primera captura (base inexistente, o existente sin capturas)."""
    db = tmp_path / "prices.db"
    if existing:
        conn = sqlite3.connect(db)
        for statement in storage.SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {storage.SCHEMA_VERSION}")
        conn.commit()
        conn.close()
    result = run_cli(serve(http_server, stations_with_price(2)), db)
    assert result.returncode == 0, result.stderr
    assert snapshots(db) == 1


def test_scenario_last_capture_without_prices(http_server, tmp_path):
    """Escenario: Última captura sin ninguna estación con precio."""
    db = db_with(tmp_path, stations_with_price(0, empty=3))
    result = run_cli(serve(http_server, stations_with_price(2)), db)
    assert result.returncode == 0, result.stderr
    assert snapshots(db) == 2


def test_scenario_ingestion_after_interrupted_save(http_server, tmp_path):
    """Escenario: Ingesta tras un guardado interrumpido."""
    db = db_with(tmp_path, stations_with_price(10))
    first = sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1"))
    make_pending_journal(db)
    result = run_cli(serve(http_server, stations_with_price(10)), db)
    assert result.returncode == 0, result.stderr
    assert snapshots(db) == 2
    assert sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1")) == first
    assert query(db, "SELECT COUNT(*) FROM prices WHERE snapshot_id = 2") == [(10,)]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["prices.db"]


def test_scenario_rejected_response_does_not_change_reference(http_server, db_12000):
    """Escenario: Una respuesta rechazada no cambia la referencia."""
    url = serve(http_server, stations_with_price(9_000))
    assert run_cli(url, db_12000).returncode == EXIT_SHORT_RESPONSE
    result = run_cli(serve(http_server, stations_with_price(9_500), "/api2"), db_12000)
    assert result.returncode == EXIT_SHORT_RESPONSE
    assert "frente a 12.000 de la última captura (79,1 %)" in result.stderr
    assert snapshots(db_12000) == 1


# --- Aceptar a mano una respuesta corta ---------------------------------------

ACCEPTED_9000 = (
    "Aviso: respuesta corta aceptada con --accept-short-response: 9.000 estaciones con "
    "precio frente a 12.000 de la última captura (75,0 %)"
)


def test_scenario_manual_acceptance_and_new_reference(http_server, db_12000):
    """Escenarios: Aceptación manual y La nueva captura pasa a ser la referencia."""
    url = serve(http_server, stations_with_price(9_000))
    result = run_cli(url, db_12000, "--accept-short-response")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert "Avisos: 1" in lines
    assert ACCEPTED_9000 in lines
    assert snapshots(db_12000) == 2

    result = run_cli(serve(http_server, stations_with_price(8_800), "/api2"), db_12000)
    assert result.returncode == 0, result.stderr  # 8.800 / 9.000 = 97,7 %
    assert snapshots(db_12000) == 3


def test_scenario_option_with_response_that_is_not_short(http_server, db_12000):
    """Escenario: Opción con una respuesta que no es corta."""
    url = serve(http_server, stations_with_price(11_900))
    result = run_cli(url, db_12000, "--accept-short-response")
    assert result.returncode == 0, result.stderr
    assert "Avisos: 0" in result.stdout.splitlines()
    assert "respuesta corta" not in result.stdout


def test_scenario_option_without_previous_captures(http_server, tmp_path):
    """Escenario: Opción sin capturas anteriores."""
    db = tmp_path / "prices.db"
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db, "--accept-short-response")
    assert result.returncode == 0, result.stderr
    assert "respuesta corta" not in result.stdout
    assert snapshots(db) == 1


# --- Formato de las cifras en los mensajes ------------------------------------

def test_scenario_small_figures(http_server, tmp_path):
    """Escenario: Cifras pequeñas."""
    db = db_with(tmp_path, stations_with_price(10))
    result = run_cli(serve(http_server, stations_with_price(7)), db)
    assert "7 estaciones con precio frente a 10 de la última captura (70,0 %)" in result.stderr


# --- Orden de la comprobación de versión y de la referencia (D4) -------------

def test_unknown_version_without_prices_table(http_server, tmp_path):
    db = tmp_path / "prices.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE snapshots (id INTEGER PRIMARY KEY, downloaded_at TEXT)")
    conn.execute("INSERT INTO snapshots VALUES (1, '2026-10-12T08:17:40Z')")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before = db_dump(db)
    result = run_cli(serve(http_server, stations_with_price(2)), db)
    assert result.returncode == 1
    assert "versión de base de datos no compatible: 7" in result.stderr
    assert db_dump(db) == before


def test_existing_database_without_tables_is_saved_without_comparing(http_server, tmp_path):
    db = tmp_path / "prices.db"
    sqlite3.connect(db).close()
    result = run_cli(serve(http_server, stations_with_price(2)), db)
    assert result.returncode == 0, result.stderr
    assert snapshots(db) == 1
