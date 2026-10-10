"""Escenarios de descarga, respuestas inválidas y resultado, con la CLI real como subproceso.

Requisitos: "Descarga única de precios en JSON", "Tiempo límite de la
descarga", "Respuestas inválidas no guardan nada", "Base de datos con
estructura desconocida" y "Resultado de la ejecución".
"""

import sqlite3
from datetime import datetime, timezone

from src.ingestion.__main__ import main
from tests.builders import response, station
from tests.helpers import closed_port_url, db_dump, run_cli
from tests.http_server import HANG
from tests.storage_helpers import ingest, prices_of, query


def existing_db(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    return db


# --- Descarga única de precios en JSON ---------------------------------------

def test_scenario_normal_run(http_server, tmp_path):
    """Escenario: Ejecución normal."""
    db = tmp_path / "prices.db"
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr
    assert http_server.requests == {"/api": 1}
    assert http_server.received_headers["/api"]["Accept"] == "application/json"
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]


def test_scenario_redirect(http_server, tmp_path):
    """Escenario: Redirección."""
    db = tmp_path / "prices.db"
    http_server.add_fixture("/nueva", "valid_two_stations.json")
    url = http_server.add("/antigua", status=301, headers={"Location": http_server.url("/nueva")})
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr
    assert http_server.requests == {"/antigua": 1, "/nueva": 1}
    assert query(db, "SELECT id FROM stations ORDER BY id") == [("4375",), ("5120",)]
    assert query(db, "SELECT COUNT(*) FROM prices") == [(3,)]


def test_scenario_failure_without_retry(http_server, tmp_path):
    """Escenario: Fallo sin reintento."""
    db = existing_db(tmp_path)
    before = db_dump(db)
    url = http_server.add("/api", status=503, body=b"busy")
    result = run_cli(url, db)
    assert result.returncode != 0
    assert http_server.requests == {"/api": 1}
    assert db_dump(db) == before


# --- Tiempo límite de la descarga --------------------------------------------

def test_scenario_timeout(http_server, tmp_path):
    """Escenario: Tiempo agotado."""
    db = existing_db(tmp_path)
    before = db_dump(db)
    url = http_server.add("/api", mode=HANG)
    result = run_cli(url, db, deadline=1)
    assert result.returncode != 0
    assert "se agotó el tiempo" in result.stderr
    assert http_server.requests == {"/api": 1}
    assert db_dump(db) == before


# --- Respuestas inválidas no guardan nada ------------------------------------

def test_scenario_connection_refused(tmp_path):
    """Escenario: Fallo de conexión (el servidor rechaza la conexión)."""
    db = existing_db(tmp_path)
    before = db_dump(db)
    result = run_cli(closed_port_url(), db)
    assert result.returncode != 0
    assert "no se ha podido conectar" in result.stderr
    assert db_dump(db) == before


def test_scenario_name_not_resolved(tmp_path, capsys):
    """Escenario: Fallo de conexión (no se resuelve el nombre).

    En proceso: el bloqueo de red de conftest.py hace fallar la resolución
    antes de salir de la máquina, igual que un nombre inexistente.
    """
    db = existing_db(tmp_path)
    before = db_dump(db)
    code = main(
        ["--url", "http://gasolineras.invalid/api", "--db", str(db)],
        now=lambda: datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    assert code != 0
    assert "no se ha podido conectar" in capsys.readouterr().err
    assert db_dump(db) == before


def test_scenario_duplicated_identifier(http_server, tmp_path):
    """Escenario: Identificador duplicado (el error indica el identificador)."""
    db = existing_db(tmp_path)
    before = db_dump(db)
    url = http_server.add_fixture("/api", "ideess_duplicate.json")
    result = run_cli(url, db)
    assert result.returncode != 0
    assert "duplicado" in result.stderr and "4375" in result.stderr
    assert db_dump(db) == before


def test_scenario_duplicated_identifier_with_spaces(http_server, tmp_path):
    """Escenario: Identificador duplicado con espacios (se indica "4375", sin espacios)."""
    db = existing_db(tmp_path)
    before = db_dump(db)
    url = http_server.add_fixture("/api", "ideess_duplicate_spaces.json")
    result = run_cli(url, db)
    assert result.returncode != 0
    assert "duplicado: 4375\n" in result.stderr
    assert db_dump(db) == before


def test_scenario_write_error_in_database(http_server, tmp_path):
    """Escenario: Error de escritura en la base de datos (CLI real como subproceso)."""
    db = existing_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER fail_snapshots BEFORE INSERT ON snapshots "
        "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
    )
    conn.commit()
    conn.close()
    before = db_dump(db)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db)
    assert result.returncode != 0
    assert "fallo simulado" in result.stderr
    assert db_dump(db) == before


# --- Base de datos con estructura desconocida --------------------------------

def test_scenario_unknown_schema_version(http_server, tmp_path):
    """Escenario: Versión de estructura desconocida (CLI real como subproceso)."""
    db = existing_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before_bytes = db.read_bytes()
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db)
    assert result.returncode != 0
    assert "versión de base de datos no compatible" in result.stderr
    assert db.read_bytes() == before_bytes


# --- Resultado de la ejecución -----------------------------------------------

def test_scenario_successful_run_summary(http_server, tmp_path):
    """Escenario: Resumen de ejecución correcta.

    `valid_three_stations.json`: "4375" (ya existe) con 2 precios, y dos
    estaciones nuevas con 0 y 4 precios.
    """
    db = existing_db(tmp_path)
    url = http_server.add_fixture("/api", "valid_three_stations.json")
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr
    assert "Estaciones procesadas: 3 (2 nuevas, 1 actualizada)" in result.stdout
    assert "Precios guardados: 6" in result.stdout
    assert "Avisos: 0" in result.stdout
    assert query(db, "SELECT COUNT(*) FROM prices WHERE snapshot_id = 2") == [(6,)]


def test_scenario_successful_run_with_warnings(http_server, tmp_path):
    """Escenario: Ejecución correcta con avisos."""
    db = tmp_path / "prices.db"
    url = http_server.add_fixture("/api", "with_warnings.json")
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr
    assert "Avisos: 2" in result.stdout
    lines = [line for line in result.stdout.splitlines() if line.startswith("Aviso: ")]
    assert len(lines) == 2
    assert any("4375" in line and "Gasoleo A" in line and '"1,4a9"' in line for line in lines)
    assert any("5120" in line and "Latitud" in line and '"abc"' in line for line in lines)
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert prices_of(db, "4375") == {"Gasolina 95 E5": 1.529}
    assert prices_of(db, "5120") == {"Gasoleo A": 1.479}


def test_scenario_failed_run_report(http_server, tmp_path):
    """Escenario: Informe de ejecución fallida."""
    url = http_server.add("/api", status=503, body=b"busy")
    result = run_cli(url, tmp_path / "prices.db")
    assert result.returncode != 0
    assert "la descarga ha fallado con HTTP 503" in result.stderr
    assert result.stdout == ""
