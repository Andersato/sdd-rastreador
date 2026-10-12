"""Requisito «Argumentos adicionales del comando»."""

import pytest

from tests.docker.helpers import container_url, dir_state
from tests.storage_helpers import query


def test_url_argument(project, http_server):
    http_server.add_fixture("/otra", "valid_two_stations.json")
    result = project.run_ingest(url=container_url(http_server, "/otra"))
    assert result.returncode == 0, result.stderr
    assert http_server.total_requests() == 1
    assert http_server.count("/otra") == 1
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]


def test_help(project, http_server):
    http_server.add_fixture("/api", "valid_two_stations.json")
    result = project.run_ingest("--help", url=container_url(http_server, "/api"))
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout and "--url" in result.stdout
    assert http_server.total_requests() == 0
    assert dir_state(project.data) == {}


@pytest.mark.parametrize("args", [("--db", "/tmp/otra.db"), ("--db=/tmp/otra.db",)])
def test_db_cannot_be_changed(project, http_server, args):
    http_server.add_fixture("/api", "valid_two_stations.json")
    result = project.run_ingest(*args, url=container_url(http_server, "/api"))
    assert result.returncode != 0
    assert "la base de datos no se puede cambiar en el contenedor" in result.stderr
    assert http_server.total_requests() == 0
    assert dir_state(project.data) == {}
