"""Requisitos «Base de datos en la carpeta ./data del host» (incluido
«Funciona igual en macOS») y «Carpeta ./data inexistente»."""

import json
import sqlite3

import pytest

from tests.docker.helpers import container_url, dir_state, docker, make_project, unique_name, IMAGE
from tests.http_server import FIXTURES
from tests.storage_helpers import ingest, query


def first_snapshot(db):
    return (
        query(db, "SELECT * FROM snapshots WHERE id = 1"),
        sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1")),
        sorted(query(db, "SELECT * FROM stations")),
    )


@pytest.fixture
def api(http_server):
    http_server.add_fixture("/api", "valid_two_stations.json")
    return http_server


def test_reuses_existing_database(project, api):
    ingest(project.db, json.loads((FIXTURES / "valid_two_stations.json").read_text()))
    before = first_snapshot(project.db)
    result = project.run_ingest(url=container_url(api, "/api"))
    assert result.returncode == 0, result.stderr
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(2,)]
    assert first_snapshot(project.db) == before
    assert sorted(p.name for p in project.data.iterdir()) == ["prices.db"]


def test_first_run_with_empty_data(project, api):
    result = project.run_ingest(url=container_url(api, "/api"))
    assert result.returncode == 0, result.stderr
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]
    assert query(project.db, "SELECT count(*) FROM stations") == [(2,)]
    assert sorted(p.name for p in project.data.iterdir()) == ["prices.db"]


def test_data_survives_container_and_image_rebuild(tmp_path, image, api):
    tag = f"{IMAGE}:test-{unique_name('rebuild')}"
    proj = make_project(tmp_path, build=True, image=tag)
    try:
        for _ in range(2):
            built = proj.compose("build", "-q", timeout=900)
            assert built.returncode == 0, built.stderr
            result = proj.run_ingest(url=container_url(api, "/api"))
            assert result.returncode == 0, result.stderr
        assert query(proj.db, "SELECT count(*) FROM snapshots") == [(2,)]
    finally:
        proj.down()
        docker("image", "rm", "-f", tag, timeout=120)


def test_unknown_schema_version(project, api):
    conn = sqlite3.connect(project.db)
    conn.execute("CREATE TABLE snapshots (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO snapshots VALUES (1)")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before = dir_state(project.data)
    result = project.run_ingest(url=container_url(api, "/api"))
    assert result.returncode != 0
    assert dir_state(project.data) == before


def test_launched_from_another_folder(project, api, tmp_path):
    other = tmp_path / "otra-carpeta"
    other.mkdir()
    result = project.run_ingest(url=container_url(api, "/api"), cwd=other)
    assert result.returncode == 0, result.stderr
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]
    assert list(other.iterdir()) == []


def test_missing_data_folder(tmp_path, image, api):
    proj = make_project(tmp_path, data=False)
    try:
        result = proj.run_ingest(url=container_url(api, "/api"))
        assert result.returncode != 0
        assert "bind source path does not exist" in result.stderr
        assert str(proj.data) in result.stderr
        assert api.total_requests() == 0
        assert not proj.data.exists()
    finally:
        proj.down()
