"""Escenarios de «Una sola ingesta a la vez por base de datos», con la CLI real."""

import os
import signal
import time

from tests.helpers import run_cli, start_cli
from tests.http_server import FIXTURES, HANG, SLOW
from tests.storage_helpers import query

EXIT_BUSY = 3
BUSY_MESSAGE = "ya hay otra ingesta o copia en curso"


def wait_for_request(server, path, timeout=10):
    deadline = time.monotonic() + timeout
    while server.count(path) == 0:
        assert time.monotonic() < deadline, f"no ha llegado ninguna petición a {path}"
        time.sleep(0.05)


def slow_fixture(server, path, seconds):
    """Respuesta válida de 2 estaciones que tarda unos `seconds` en enviarse."""
    size = (FIXTURES / "valid_two_stations.json").stat().st_size
    return server.add_fixture(path, "valid_two_stations.json", mode=SLOW, delay=seconds / size)


def test_scenario_second_ingestion_while_another_downloads(http_server, tmp_path):
    """Escenario: Segunda ingesta mientras otra descarga."""
    db = tmp_path / "a" / "prices.db"
    db.parent.mkdir()
    url = slow_fixture(http_server, "/api", 3)
    first = start_cli(url, db)
    try:
        wait_for_request(http_server, "/api")
        start = time.monotonic()
        second = run_cli(url, db)
        assert time.monotonic() - start < 2 + 1  # + arranque del intérprete
        assert second.returncode == EXIT_BUSY
        assert BUSY_MESSAGE in second.stderr
        assert http_server.count("/api") == 1
        out, err = first.communicate(timeout=30)
        assert first.returncode == 0, err
    finally:
        first.kill()
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]


def test_scenario_different_folders(http_server, tmp_path):
    """Escenario: Carpetas distintas."""
    a, b = tmp_path / "a" / "prices.db", tmp_path / "b" / "prices.db"
    hang = http_server.add("/hang", mode=HANG)
    first = start_cli(hang, a, deadline=10)
    try:
        wait_for_request(http_server, "/hang")
        url = http_server.add_fixture("/api", "valid_two_stations.json")
        result = run_cli(url, b)
        assert result.returncode == 0, result.stderr
    finally:
        first.kill()
        first.wait()


def test_scenario_previous_ingestion_killed(http_server, tmp_path):
    """Escenario: Ingesta anterior muerta a la fuerza."""
    db = tmp_path / "a" / "prices.db"
    hang = http_server.add("/hang", mode=HANG)
    first = start_cli(hang, db, deadline=30)
    wait_for_request(http_server, "/hang")
    os.kill(first.pid, signal.SIGKILL)
    first.wait()
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr


def test_scenario_lock_leaves_no_files(http_server, tmp_path):
    """Escenario: El bloqueo no deja archivos (ingesta correcta y fallida)."""
    db = tmp_path / "a" / "prices.db"
    ok = http_server.add_fixture("/api", "valid_two_stations.json")
    assert run_cli(ok, db).returncode == 0
    assert [p.name for p in db.parent.iterdir()] == ["prices.db"]
    failing = http_server.add("/fail", status=503)
    assert run_cli(failing, db).returncode != 0
    assert [p.name for p in db.parent.iterdir()] == ["prices.db"]


def test_scenario_first_run_with_missing_database(http_server, tmp_path):
    """Escenario: Primera ejecución con base inexistente."""
    folder = tmp_path / "a"
    folder.mkdir()
    db = folder / "prices.db"
    url = slow_fixture(http_server, "/api", 1)
    procs = [start_cli(url, db), start_cli(url, db)]
    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=30)
        results.append((proc.returncode, err))
    assert sorted(code for code, _ in results) == [0, EXIT_BUSY]
    assert any(BUSY_MESSAGE in err for code, err in results if code == EXIT_BUSY)
    assert http_server.count("/api") == 1
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
