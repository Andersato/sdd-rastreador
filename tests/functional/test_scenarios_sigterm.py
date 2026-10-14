"""Escenarios de «Señal de parada tratada como Ctrl+C», con la CLI real.

Para mandar la señal durante el guardado se espera a que aparezca el diario
(base existente) o el temporal (primera captura), que solo existen mientras
se está guardando.
"""

import json
import os
import signal
import time

from tests.builders import response, station
from tests.helpers import db_dump, start_cli
from tests.http_server import HANG
from tests.storage_helpers import ingest, query

BIG = 20_000


def big_response():
    return response(*(station(f"B{i}", **{"Precio Gasoleo A": "1,459", "Precio Gasoleo B": "1,299"})
                      for i in range(BIG)))


def wait_for(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "no se ha llegado a la fase esperada"
        time.sleep(0.005)


def saving(folder):
    return any(p.name.endswith("-journal") or ".tmp-" in p.name for p in folder.iterdir())


def files(folder):
    return sorted(p.name for p in folder.iterdir())


def test_scenario_sigterm_during_save(http_server, tmp_path):
    """Escenario: Señal de parada durante el guardado."""
    db = tmp_path / "prices.db"
    ingest(db, big_response())
    first = sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1"))
    url = http_server.add("/api", body=json.dumps(big_response()))
    proc = start_cli(url, db)
    try:
        wait_for(lambda: saving(tmp_path) or proc.poll() is not None)
        os.kill(proc.pid, signal.SIGTERM)
        _, err = proc.communicate(timeout=30)
    finally:
        proc.kill()
    assert files(tmp_path) == ["prices.db"]
    snapshots = query(db, "SELECT COUNT(*) FROM snapshots")[0][0]
    if snapshots == 1:
        assert proc.returncode != 0
        assert "Error: ingesta interrumpida" in err
    else:  # la señal llegó justo después del COMMIT
        assert snapshots == 2
        assert query(db, "SELECT COUNT(*) FROM prices WHERE snapshot_id = 2") == [(2 * BIG,)]
    assert sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1")) == first


def test_scenario_sigterm_during_first_capture(http_server, tmp_path):
    """Escenario: Señal de parada durante la primera captura."""
    db = tmp_path / "prices.db"
    url = http_server.add("/api", body=json.dumps(big_response()))
    proc = start_cli(url, db)
    try:
        wait_for(lambda: saving(tmp_path) or proc.poll() is not None)
        os.kill(proc.pid, signal.SIGTERM)
        proc.communicate(timeout=30)
    finally:
        proc.kill()
    if files(tmp_path) == []:
        assert proc.returncode != 0
    else:
        assert files(tmp_path) == ["prices.db"]
        assert query(db, "SELECT COUNT(*) FROM prices") == [(2 * BIG,)]


def test_scenario_sigterm_during_download(http_server, tmp_path):
    """Escenario: Señal de parada durante la descarga."""
    db = tmp_path / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"})))
    before = db_dump(db)
    url = http_server.add("/api", mode=HANG)
    proc = start_cli(url, db, deadline=60)
    try:
        wait_for(lambda: http_server.count("/api") == 1, timeout=10)
        start = time.monotonic()
        os.kill(proc.pid, signal.SIGTERM)
        _, err = proc.communicate(timeout=10)
        assert time.monotonic() - start < 2
    finally:
        proc.kill()
    assert proc.returncode != 0
    assert "Error: ingesta interrumpida" in err
    assert http_server.count("/api") == 1
    assert db_dump(db) == before
    assert files(tmp_path) == ["prices.db"]
