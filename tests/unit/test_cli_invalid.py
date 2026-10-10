"""Requisito "Respuestas inválidas no guardan nada": todos los casos por la CLI.

Cada caso se prueba con una base existente (debe quedar idéntica) y sin base
(no debe crearse ningún archivo).
"""

from datetime import datetime, timezone

import pytest

from src.ingestion.__main__ import main
from tests.builders import response, station
from tests.helpers import closed_port_url, db_dump
from tests.http_server import HANG, TRUNCATED_CLOSE, TRUNCATED_LENGTH
from tests.storage_helpers import ingest

FIXED = datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc)

FIXTURE_CASES = [
    "empty.json", "not_json.xml", "not_json.html", "root_list.json", "root_string.json",
    "resultado_error.json", "resultado_missing.json", "lista_missing.json", "lista_empty.json",
    "lista_object.json", "lista_string.json", "station_not_object.json", "ideess_missing.json",
    "ideess_empty.json", "ideess_spaces.json", "ideess_number.json", "ideess_null.json",
    "ideess_duplicate.json", "ideess_duplicate_spaces.json",
]
SERVER_CASES = {
    "http-500": dict(status=500, body=b"error"),
    "http-503": dict(status=503, body=b"busy"),
    "http-204": dict(status=204, body=b""),
    "http-206": dict(status=206, fixture="valid_two_stations.json"),
    "truncated-length": dict(fixture="valid_two_stations.json", mode=TRUNCATED_LENGTH),
    "truncated-close": dict(fixture="valid_two_stations.json", mode=TRUNCATED_CLOSE),
    "timeout": dict(mode=HANG),
}
CASES = [f"fixture:{name}" for name in FIXTURE_CASES] + [f"server:{name}" for name in SERVER_CASES] + ["refused"]


def url_for(case, server):
    kind, _, name = case.partition(":")
    if kind == "fixture":
        return server.add_fixture("/api", name)
    if kind == "server":
        spec = dict(SERVER_CASES[name])
        fixture = spec.pop("fixture", None)
        if fixture:
            return server.add_fixture("/api", fixture, **spec)
        return server.add("/api", **spec)
    return closed_port_url()


def run(url, db):
    return main(["--url", url, "--db", str(db)], now=lambda: FIXED, deadline_s=0.5)


@pytest.mark.parametrize("case", CASES)
def test_existing_database_unchanged(case, http_server, tmp_path, capsys):
    db = tmp_path / "p.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    before = db_dump(db)
    assert run(url_for(case, http_server), db) != 0
    assert capsys.readouterr().err.startswith("Error: ")
    assert db_dump(db) == before


@pytest.mark.parametrize("case", CASES)
def test_no_database_created(case, http_server, tmp_path):
    db = tmp_path / "data" / "p.db"
    assert run(url_for(case, http_server), db) != 0
    assert db_dump(db) == "no existe"
    assert not (tmp_path / "data").exists()
