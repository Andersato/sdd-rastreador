"""Escenarios «Interrupción durante la descarga» e «Interrupción durante el
guardado» del requisito «Lanzamiento único…».

Antes de mirar la base se recupera siempre el diario pendiente (`recover`),
como haría la siguiente ingesta: `docker stop` mata la ingesta sin ROLLBACK.
"""

import json
import shutil
import time
from contextlib import contextmanager

import pytest

from tests.builders import response, station
from tests.docker.helpers import container_exists, container_url, docker, recover, unique_name
from tests.http_server import FIXTURES, HANG
from tests.storage_helpers import ingest, query

BIG_STATIONS = 20_000
FUELS = ("Gasoleo A", "Gasoleo B", "Gasolina 95 E5", "Gasolina 98 E5",
         "Gases licuados del petróleo", "Gasoleo Premium")
JOURNAL_TIMEOUT_S = 60
SIGINT_DELAYS_S = (0.0, 0.3, 0.8, 1.5)


def price_text(i, j):
    return f"1,{(i * 7 + j * 13) % 900 + 100:03d}"


@pytest.fixture(scope="module")
def big_response():
    """Respuesta de 20 000 estaciones, cada una con 6 precios, y los precios esperados."""
    stations = [
        station(f"B{i}", **{f"Precio {fuel}": price_text(i, j) for j, fuel in enumerate(FUELS)})
        for i in range(BIG_STATIONS)
    ]
    expected = sorted(
        (f"B{i}", fuel, float(price_text(i, j).replace(",", ".")))
        for i in range(BIG_STATIONS)
        for j, fuel in enumerate(FUELS)
    )
    return json.dumps(response(*stations)).encode("utf-8"), expected


@pytest.fixture
def seeded(tmp_path):
    """Base con 1 captura (la «primera»), para copiarla antes de cada repetición."""
    db = tmp_path / "seed.db"
    ingest(db, json.loads((FIXTURES / "valid_two_stations.json").read_text()))
    return db


def first_capture(db):
    return (
        query(db, "SELECT * FROM snapshots WHERE id = 1"),
        sorted(query(db, "SELECT * FROM prices WHERE snapshot_id = 1")),
    )


def reset_data(project, seeded):
    shutil.rmtree(project.data)
    project.data.mkdir()
    shutil.copy2(seeded, project.db)


def wait_for(predicate, timeout, interval=0.002):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@contextmanager
def launched(project, url, name):
    """Ingesta en segundo plano; si el test falla a medias, no deja nada en marcha."""
    proc = project.start_ingest(url=url, container_name=name)
    try:
        yield proc
    finally:
        if proc.returncode is None:
            docker("rm", "-f", name, timeout=60)
            proc.kill()
            proc.communicate(timeout=60)


def wait_exit(proc, timeout):
    # communicate (no wait) para que una salida grande no bloquee la tubería.
    proc.communicate(timeout=timeout)
    return proc.returncode


def check_one_or_two_complete_captures(project, seed_state, expected):
    recover(project.db)
    assert first_capture(project.db) == seed_state
    snapshots = query(project.db, "SELECT id FROM snapshots ORDER BY id")
    assert snapshots in ([(1,)], [(1,), (2,)])
    if snapshots == [(1,), (2,)]:
        saved = sorted(query(project.db,
                             "SELECT station_id, fuel, price FROM prices WHERE snapshot_id = 2"))
        assert saved == expected
    return len(snapshots)


@pytest.mark.parametrize("signal", ["stop", "INT"])
def test_interrupted_during_download(project, http_server, seeded, signal):
    reset_data(project, seeded)
    seed_state = first_capture(project.db)
    http_server.add("/api", mode=HANG)
    name = unique_name()
    with launched(project, container_url(http_server, "/api"), name) as proc:
        assert wait_for(lambda: http_server.count("/api") == 1, timeout=60)
        if signal == "stop":
            docker("stop", name, timeout=60)
        else:
            docker("kill", "--signal", "INT", name, timeout=60)
        assert wait_exit(proc, 120) != 0
    assert not container_exists(name)
    recover(project.db)
    assert query(project.db, "SELECT count(*) FROM snapshots") == [(1,)]
    assert first_capture(project.db) == seed_state


def test_stop_during_save(project, http_server, seeded, big_response):
    """`docker stop` en cuanto aparece el diario: el corte cae en el guardado."""
    body, expected = big_response
    cut_inside_transaction = 0
    for attempt in range(3):
        reset_data(project, seeded)
        seed_state = first_capture(project.db)
        path = f"/api{attempt}"
        http_server.add(path, body=body)
        journal = project.data / "prices.db-journal"
        name = unique_name()
        with launched(project, container_url(http_server, path), name) as proc:
            assert http_server.sent(path).wait(timeout=120), "el servidor no envió la respuesta"
            assert wait_for(journal.exists, timeout=JOURNAL_TIMEOUT_S), (
                "el diario no apareció: la ingesta no llegó a guardar"
            )
            docker("stop", name, timeout=60)
            wait_exit(proc, 120)
        assert not container_exists(name)
        if journal.exists():
            # Muerta dentro de la transacción: solo puede quedar la primera.
            cut_inside_transaction += 1
            assert proc.returncode != 0
            assert check_one_or_two_complete_captures(project, seed_state, expected) == 1
        else:
            # El guardado terminó antes del corte: una o dos completas.
            check_one_or_two_complete_captures(project, seed_state, expected)
        if cut_inside_transaction:
            break
    assert cut_inside_transaction, "ningún docker stop cayó dentro de la transacción"


def test_sigint_during_save(project, http_server, seeded, big_response):
    """Ctrl+C a varios intervalos tras enviar la respuesta: nunca una captura a medias."""
    body, expected = big_response
    for i, delay in enumerate(SIGINT_DELAYS_S):
        reset_data(project, seeded)
        seed_state = first_capture(project.db)
        path = f"/api{i}"
        http_server.add(path, body=body)
        name = unique_name()
        with launched(project, container_url(http_server, path), name) as proc:
            assert http_server.sent(path).wait(timeout=120), "el servidor no envió la respuesta"
            time.sleep(delay)
            docker("kill", "--signal", "INT", name, timeout=60)
            wait_exit(proc, 180)
        assert not container_exists(name)
        captures = check_one_or_two_complete_captures(project, seed_state, expected)
        if proc.returncode == 0:
            # La señal llegó cuando la ingesta ya había terminado.
            assert captures == 2
