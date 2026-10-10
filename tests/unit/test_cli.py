"""Requisito "Resultado de la ejecución" y errores a nivel de CLI (en proceso)."""

import sqlite3
from datetime import datetime, timezone

import pytest

from src.ingestion import storage
from src.ingestion.__main__ import main
from tests.builders import response, station
from tests.helpers import db_dump
from tests.http_server import HANG
from tests.storage_helpers import ingest

FIXED = datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc)


def run(url, db, **kwargs):
    return main(["--url", url, "--db", str(db)], now=lambda: FIXED, **kwargs)


def test_successful_summary(http_server, tmp_path, capsys):
    db = tmp_path / "p.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    url = http_server.add_fixture("/api", "valid_three_stations.json")
    assert run(url, db) == 0
    out = capsys.readouterr().out
    assert "Estaciones procesadas: 3 (2 nuevas, 1 actualizada)" in out
    assert "Precios guardados: 6" in out
    assert "Avisos: 0" in out


def test_successful_run_with_warnings(http_server, tmp_path, capsys):
    url = http_server.add_fixture("/api", "with_warnings.json")
    assert run(url, tmp_path / "p.db") == 0
    out = capsys.readouterr().out
    assert "Avisos: 2" in out
    assert 'Aviso: estación 4375, Gasoleo A: valor "1,4a9" no válido' in out
    assert 'Aviso: estación 5120, Latitud: valor "abc" no válido' in out


def test_failed_run_report(http_server, tmp_path, capsys):
    url = http_server.add("/api", status=503, body=b"busy")
    assert run(url, tmp_path / "p.db") != 0
    assert "la descarga ha fallado con HTTP 503" in capsys.readouterr().err


def test_timeout_report(http_server, tmp_path, capsys):
    url = http_server.add("/api", mode=HANG)
    assert run(url, tmp_path / "p.db", deadline_s=0.5) != 0
    assert "se agotó el tiempo de descarga" in capsys.readouterr().err


def test_write_error_on_existing_database(http_server, tmp_path, capsys):
    db = tmp_path / "p.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER fail_prices BEFORE INSERT ON prices "
        "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
    )
    conn.commit()
    conn.close()
    before = db_dump(db)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    assert run(url, db) != 0
    assert "fallo simulado" in capsys.readouterr().err
    assert db_dump(db) == before


def test_write_error_on_first_run(http_server, tmp_path, monkeypatch, capsys):
    def failing_insert(conn, snapshot_id, prices):
        raise sqlite3.OperationalError("disco lleno (simulado)")

    monkeypatch.setattr(storage, "_insert_prices", failing_insert)
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    assert run(url, tmp_path / "data" / "p.db") != 0
    assert "disco lleno" in capsys.readouterr().err
    assert not (tmp_path / "data" / "p.db").exists()
    assert list((tmp_path / "data").iterdir()) == []


def test_unknown_schema_version(http_server, tmp_path, capsys):
    db = tmp_path / "p.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before = db_dump(db)
    before_bytes = db.read_bytes()
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    assert run(url, db) != 0
    assert "versión de base de datos no compatible: 7" in capsys.readouterr().err
    assert db_dump(db) == before
    assert db.read_bytes() == before_bytes


def test_deadline_option_is_hidden(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--deadline" not in out
    assert "--db" in out and "--url" in out


def test_pathological_json_reports_error_without_traceback(http_server, tmp_path, capsys):
    url = http_server.add("/api", body=b"1" * 5000)
    assert run(url, tmp_path / "p.db") == 1
    err = capsys.readouterr().err
    assert err.startswith("Error: la respuesta de la API no es JSON válido")
    assert "Traceback" not in err


def test_malformed_url_reports_error_without_traceback(tmp_path, capsys):
    assert run("sin-esquema", tmp_path / "p.db") == 1
    assert capsys.readouterr().err.startswith("Error: URL no válida")


def test_warning_values_quoted_only_when_text(http_server, tmp_path, capsys):
    data = response(
        station("4375", **{"Latitud": None, "Longitud (WGS84)": 40.5}),
        station("5120", **{"Latitud": "null"}),
        station("6200", drop=["Latitud"]),
    )
    import json

    url = http_server.add("/api", body=json.dumps(data).encode())
    assert run(url, tmp_path / "p.db") == 0
    out = capsys.readouterr().out
    assert "Aviso: estación 4375, Latitud: valor null no válido" in out
    assert "Aviso: estación 4375, Longitud (WGS84): valor 40.5 no válido" in out
    assert 'Aviso: estación 5120, Latitud: valor "null" no válido' in out
    assert "Aviso: estación 6200, Latitud: valor (ausente) no válido" in out
