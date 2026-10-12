"""Requisito «Lanzamiento único con el código de salida de la ingesta»."""

import json

from tests.docker.helpers import (
    CLOSED_PORT_URL,
    UNRESOLVABLE_URL,
    container_exists,
    container_url,
    dir_state,
)
from tests.http_server import FIXTURES
from tests.storage_helpers import ingest, query


def seed(project):
    """Base del proyecto temporal con 1 captura."""
    data = json.loads((FIXTURES / "valid_two_stations.json").read_text())
    ingest(project.db, data)


def test_successful_run(project, http_server):
    http_server.add_fixture("/api", "valid_two_stations.json")
    result = project.run_ingest(url=container_url(http_server, "/api"))
    assert result.returncode == 0, result.stderr
    assert "Captura guardada en /app/data/prices.db" in result.stdout
    assert "Estaciones procesadas: 2" in result.stdout
    assert "Precios guardados:" in result.stdout
    assert "Avisos: 0" in result.stdout
    assert http_server.count("/api") == 1
    assert http_server.total_requests() == 1
    assert not container_exists(result.container_name)
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]


def test_successful_run_with_warnings(project, http_server):
    http_server.add_fixture("/api", "with_warnings.json")
    result = project.run_ingest(url=container_url(http_server, "/api"))
    assert result.returncode == 0, result.stderr
    assert "Aviso:" in result.stdout
    assert "1,4a9" in result.stdout
    # La captura se guarda pese a los avisos.
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]
    assert query(project.db, "SELECT count(*) FROM stations") == [(2,)]
    assert query(project.db, "SELECT count(*) FROM prices") != [(0,)]


def test_api_down(project, http_server):
    seed(project)
    before = dir_state(project.data)
    http_server.add("/api", status=503, body=b"Service Unavailable")
    result = project.run_ingest(url=container_url(http_server, "/api"))
    # Mismo código que la ingesta, que termina con 1 cuando falla la descarga.
    assert result.returncode == 1
    assert "503" in result.stderr
    assert http_server.count("/api") == 1
    assert not container_exists(result.container_name)
    assert dir_state(project.data) == before


def test_no_connection(project):
    seed(project)
    before = dir_state(project.data)
    for url in (CLOSED_PORT_URL, UNRESOLVABLE_URL):
        result = project.run_ingest(url=url)
        assert result.returncode == 1, result.stdout
        assert dir_state(project.data) == before


def test_invalid_response(project, http_server):
    http_server.add_fixture("/api", "lista_empty.json")
    result = project.run_ingest(url=container_url(http_server, "/api"))
    assert result.returncode == 1
    assert dir_state(project.data) == {}
