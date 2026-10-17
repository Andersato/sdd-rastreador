"""«Log de la API limitado y sin ubicaciones exactas» (prices-api, D10).

La rotación (3 × 10 MB) es de Docker y se prueba con `docker compose config`.
"""

from datetime import datetime, timezone

import pytest

import src.api.queries
from src.api.access_log import access_line
from tests.api_helpers import basic_db, make_client


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    db = folder / "prices.db"
    basic_db(db)
    return db


@pytest.fixture
def lines():
    return []


def test_search_in_the_log(db, lines):
    """Escenario: Búsqueda en el log."""
    client = make_client(db, log_line=lines.append)
    response = client.get("/api/stations/nearby?lat=40.416775&lon=-3.703790&fuel=gasoleo-a")
    assert response.status_code == 200
    assert len(lines) == 1
    line = lines[0]
    assert "GET /api/stations/nearby" in line
    assert "lat=40.42" in line and "lon=-3.70" in line and "fuel=gasoleo-a" in line
    assert "→ 200" in line
    log = "\n".join(lines)
    assert "40.416775" not in log and "-3.703790" not in log and "-3.70379" not in log


def test_invalid_coordinates_in_the_log(db, lines):
    """Escenario: Coordenadas no válidas en el log."""
    client = make_client(db, log_line=lines.append)
    response = client.get("/api/stations/nearby?lat=40,416775&lon=-3.703790&fuel=gasoleo-a")
    assert response.status_code == 422
    line = lines[0]
    assert "40,416775" not in line and "-3.703790" not in line
    assert "lat=(no válido)" in line and "lon=-3.70" in line
    assert "→ 422" in line


def test_one_line_per_request_with_status(db, lines):
    client = make_client(db, log_line=lines.append)
    client.get("/api/fuels")
    client.get("/api/stations/99999")
    client.post("/api/fuels")
    assert [line.split("→ ")[1].split(" ")[0] for line in lines] == ["200", "404", "405"]


def test_unexpected_error_line_and_trace(db, lines, monkeypatch, caplog):
    """Una 500 apunta su línea y deja la traza en el log, no en la respuesta."""
    def broken(reader):
        raise RuntimeError("fallo interno de prueba")

    monkeypatch.setattr(src.api.queries, "fuel_counts", broken)
    response = make_client(db, log_line=lines.append).get("/api/fuels")
    assert response.status_code == 500
    assert "fallo interno de prueba" not in response.text
    assert "→ 500" in lines[0]
    assert "fallo interno de prueba" in caplog.text
    assert "Traceback" in caplog.text or any(r.exc_info for r in caplog.records)


def test_line_format_in_madrid_time():
    now = datetime(2026, 10, 16, 9, 30, 2, tzinfo=timezone.utc)
    line = access_line(now, "GET", "/api/stations/nearby",
                       [("lat", "40.416775"), ("lon", "-3.703790"), ("fuel", "gasoleo-a")],
                       200, 0.014)
    assert line == ("2026-10-16 11:30:02 CEST · GET /api/stations/nearby lat=40.42 lon=-3.70 "
                    "fuel=gasoleo-a → 200 (14 ms)")


@pytest.mark.parametrize("value", ["nan", "inf", "abc", ""])
def test_non_numeric_coordinates(value):
    line = access_line(datetime.now(timezone.utc), "GET", "/x", [("lat", value)], 422, 0)
    assert "lat=(no válido)" in line


def test_long_values_are_cut():
    line = access_line(datetime.now(timezone.utc), "GET", "/x", [("fuel", "x" * 500)], 422, 0)
    assert "fuel=" + "x" * 40 + " " in line
