"""Escenarios «Recogida mientras se consulta» («La API no impide guardar
capturas») y «Muchas peticiones a la vez» («Lecturas de la base de una en
una»), de prices-api.

API real (uvicorn) en un puerto local libre sobre una base temporal y en otro
proceso, como en marcha; varios clientes piden cercanas sin parar y, en
medio, se guarda una captura.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from tests.api_helpers import CAPTURE_AT, priced
from tests.builders import response
from tests.helpers import REPO_ROOT, run_cli
from tests.storage_helpers import ingest, query

STATIONS = 2000
DURATION_S = 30
CLIENTS = 4
SERVER = """
import sys
from pathlib import Path
import uvicorn
from src.api.app import create_app
app = create_app(Path(sys.argv[1]), log_line=lambda line: None)
uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
"""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def madrid_response():
    return response(*(priced(f"{10000 + i}", {"Gasoleo A": f"1,{400 + i % 500:03d}"},
                             40.30 + (i % 50) * 0.005, -3.80 + (i // 50) * 0.005)
                      for i in range(STATIONS)))


class Api:
    """La API en otro proceso, con uvicorn, sobre `db`."""

    def __init__(self, db):
        self.port = free_port()
        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
        self.process = subprocess.Popen([sys.executable, "-c", SERVER, str(db), str(self.port)],
                                        cwd=REPO_ROOT, env=env, stderr=subprocess.PIPE, text=True)
        self.base = f"http://127.0.0.1:{self.port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                get(self.base + "/api/health")
                return
            except OSError:
                assert time.monotonic() < deadline, "la API no arranca"
                time.sleep(0.2)

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=30)


def run_clients(url, clients, duration_s, during):
    """`clients` hilos piden `url` sin parar; a un tercio del tiempo se llama a
    `during()`. Devuelve (resultados, lo que devuelve `during`, instante final)."""
    results = []
    lock = threading.Lock()
    stop_at = time.monotonic() + duration_s

    def client():
        while time.monotonic() < stop_at:
            started = time.monotonic()
            status, body = get(url)
            with lock:
                results.append((started, status, body))

    threads = [threading.Thread(target=client) for _ in range(clients)]
    for thread in threads:
        thread.start()
    time.sleep(duration_s / 3)
    outcome = during()
    done_at = time.monotonic()
    for thread in threads:
        thread.join()
    return results, outcome, done_at


def test_eight_clients_do_not_delay_saving(tmp_path):
    """Escenario: Muchas peticiones a la vez (8 clientes, radio 50 km, 2.000 estaciones)."""
    from src.ingestion.parser import parse_response
    from src.ingestion.storage import save_snapshot

    db = tmp_path / "data" / "prices.db"
    db.parent.mkdir()
    data = madrid_response()
    ingest(db, data, instant=CAPTURE_AT)
    parsed = parse_response(data)
    api = Api(db)
    url = api.base + "/api/stations/nearby?lat=40.40&lon=-3.70&fuel=gasoleo-a&radius_km=50"

    def save():
        started = time.monotonic()
        save_snapshot(parsed, db, CAPTURE_AT.replace(hour=13))
        return time.monotonic() - started

    try:
        results, elapsed, _ = run_clients(url, 8, 12, save)
    finally:
        api.stop()
    assert elapsed < 1.0
    assert {status for _, status, _ in results} == {200}


def test_ingestion_saves_while_clients_read(tmp_path, http_server):
    """Escenario: Recogida mientras se consulta (4 clientes, 30 s, ingesta real)."""
    db = tmp_path / "data" / "prices.db"
    db.parent.mkdir()
    data = madrid_response()
    ingest(db, data, instant=CAPTURE_AT)
    http_server.add("/api", body=json.dumps(data).encode())

    api = Api(db)
    url = api.base + "/api/stations/nearby?lat=40.40&lon=-3.70&fuel=gasoleo-a&radius_km=50&limit=100"
    try:
        results, ingestion, saved_at = run_clients(
            url, CLIENTS, DURATION_S, lambda: run_cli(http_server.url("/api"), db, timeout=60))
    finally:
        api.stop()

    assert ingestion.returncode == 0, ingestion.stdout + ingestion.stderr
    assert query(db, "SELECT count(*) FROM snapshots") == [(2,)]
    new_capture = query(db, "SELECT downloaded_at FROM snapshots ORDER BY id DESC LIMIT 1")[0][0]
    assert len(results) > 50
    for _, status, body in results:
        assert status == 200 or body["error"]["code"] == "base_ocupada", body
    after = [body for started, status, body in results if started > saved_at and status == 200]
    assert after, "no hubo respuestas después de guardar"
    assert all(body["capture"]["downloaded_at"] == new_capture for body in after)
    assert all(body["data"]["total"] > 0 for body in after)
