"""Utilidades de los tests de la API: bases de prueba y bloqueos desde otro proceso.

Las bases se crean siempre en carpetas temporales con la ingesta real
(`tests/storage_helpers.ingest`), salvo lo que la ingesta no puede producir
(otra versión del esquema), que se prepara con SQL.
"""

import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from tests.builders import response, station
from tests.helpers import check_not_real_data
from tests.storage_helpers import ingest

UTC = timezone.utc
# Última captura de las bases de prueba: 2026-10-16T07:26:37Z (09:26:34 en Madrid).
CAPTURE_AT = datetime(2026, 10, 16, 7, 26, 37, tzinfo=UTC)
CAPTURE_FECHA = "16/10/2026 09:26:34"
ATTRIBUTION = ("Ministerio de Industria, Comercio y Turismo - Precios de carburantes "
               "en estaciones de servicio")


def coords(lat: float, lon: float) -> dict:
    """Coordenadas con el formato de la API (coma decimal)."""
    return {"Latitud": f"{lat}".replace(".", ","), "Longitud (WGS84)": f"{lon}".replace(".", ",")}


def priced(ideess, prices: dict, lat=None, lon=None, **fields):
    """Estación con precios `{"Gasoleo A": "1,459"}` y, si se dan, coordenadas."""
    data = {f"Precio {fuel}": value for fuel, value in prices.items()}
    if lat is not None:
        data.update(coords(lat, lon))
    return station(ideess, **fields, **data)


def save(db_path, *stations, instant=CAPTURE_AT, fecha=CAPTURE_FECHA, drop=()):
    """Guarda una captura con la ingesta real; acepta respuestas cortas."""
    check_not_real_data(db_path)
    from src.ingestion.parser import parse_response
    from src.ingestion.storage import save_snapshot

    parsed = parse_response(response(*stations, fecha=fecha, drop=drop))
    return save_snapshot(parsed, Path(db_path), instant, accept_short=True)


def basic_db(db_path, instant=CAPTURE_AT):
    """Base con una captura: "4375" con Gasoleo A y Gasolina 95 E5."""
    ingest(db_path, response(station("4375", **{"Precio Gasoleo A": "1,459",
                                                 "Precio Gasolina 95 E5": "1,529"}),
                             fecha=CAPTURE_FECHA), instant=instant)


# Proceso que toma un bloqueo y lo mantiene `segundos`. En modo de diario
# `delete`, BEGIN EXCLUSIVE impide leer; BEGIN IMMEDIATE (reservado) no.
_HOLD = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN " + sys.argv[2])
print("ready", flush=True)
time.sleep(float(sys.argv[3]))
conn.execute("ROLLBACK")
conn.close()
"""


@contextmanager
def hold_lock(db_path, seconds: float, mode: str = "EXCLUSIVE"):
    """Mantiene un bloqueo de SQLite desde otro proceso durante `seconds`."""
    check_not_real_data(db_path)
    proc = subprocess.Popen([sys.executable, "-c", _HOLD, str(db_path), mode, str(seconds)],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
        yield proc
    finally:
        proc.kill()
        proc.wait()


NOW = datetime(2026, 10, 16, 10, 0, 0, tzinfo=UTC)


def make_client(db_path, *, now=NOW, interval_text=None, read_options=None, log_line=None):
    """Cliente HTTP de pruebas (TestClient, con httpx) sobre la API de `db_path`.

    Las excepciones no previstas se responden como 500, igual que en marcha.
    """
    from fastapi.testclient import TestClient

    from src.api.app import create_app

    check_not_real_data(db_path)
    app = create_app(Path(db_path), interval_text=interval_text, clock=lambda: now,
                     read_options=read_options, log_line=log_line or (lambda line: None))
    return TestClient(app, raise_server_exceptions=False)


def assert_error(response, status, code):
    """Formato común de los errores: atribución y `error` con código y mensaje."""
    assert response.status_code == status, response.text
    body = response.json()
    assert body["attribution"] == ATTRIBUTION
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body
