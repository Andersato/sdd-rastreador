"""«Formato común de los errores», «Documentación interactiva», «Formato común
de las respuestas correctas» y «Parámetros antes que la base» (prices-api)."""

import pytest

import src.api.queries
from tests.api_helpers import ATTRIBUTION, assert_error, basic_db, hold_lock, make_client


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


@pytest.fixture
def client(db):
    basic_db(db)
    return make_client(db)


def test_invalid_parameter_with_decimal_comma(client):
    """Escenario: Parámetro no válido."""
    response = client.get("/api/stations/nearby?lat=40,4168&lon=-3.7038&fuel=gasoleo-a")
    body = assert_error(response, 422, "parametro_no_valido")
    assert "lat" in body["error"]["message"]
    assert "número con punto decimal" in body["error"]["message"]
    assert "40,4168" not in response.text


@pytest.mark.parametrize("path", ["/api/precios", "/"])
def test_unknown_route(client, path):
    """Escenario: Ruta inexistente."""
    assert_error(client.get(path), 404, "no_encontrado")


@pytest.mark.parametrize(("method", "path"), [("POST", "/api/fuels"),
                                              ("DELETE", "/api/stations/4375"),
                                              ("PUT", "/api/health")])
def test_method_not_allowed(client, db, method, path):
    """Escenario: Método no permitido."""
    before = db.read_bytes()
    response = client.request(method, path)
    assert_error(response, 405, "metodo_no_permitido")
    assert response.headers["allow"] == "GET"
    assert db.read_bytes() == before


def test_unexpected_error_hides_internal_details(client, monkeypatch, caplog):
    """Escenario: Error inesperado."""
    def broken(reader):
        raise RuntimeError("SELECT secreto FROM /app/data/prices.db")

    monkeypatch.setattr(src.api.queries, "fuel_counts", broken)
    response = client.get("/api/fuels")
    body = assert_error(response, 500, "error_interno")
    assert body["error"]["message"] == "error interno de la API; revisa el log del servicio"
    for internal in ("SELECT", "/app/data", "Traceback", "RuntimeError"):
        assert internal not in response.text
    assert "SELECT secreto" in caplog.text


def test_openapi_describes_exactly_the_routes(client):
    """Escenario: Documentación."""
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert set(spec["paths"]) == {"/api/health", "/api/fuels", "/api/stations/nearby",
                                  "/api/stations/{station_id}", "/api/provinces/prices"}
    assert ATTRIBUTION in spec["info"]["description"]
    params = {p["name"]: p for p in spec["paths"]["/api/stations/nearby"]["get"]["parameters"]}
    assert params["radius_km"]["schema"]["default"] == 5
    assert params["radius_km"]["schema"]["maximum"] == 50
    assert params["limit"]["schema"]["default"] == 20
    assert params["limit"]["schema"]["maximum"] == 100
    docs = client.get("/api/docs")
    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_no_documentation_at_the_root(client, path):
    """Escenario: Sin documentación en la raíz."""
    assert_error(client.get(path), 404, "no_encontrado")


def test_capture_of_origin(client):
    """Escenario: Captura de origen."""
    body = client.get("/api/fuels").json()
    assert body["attribution"] == ATTRIBUTION
    assert body["capture"] == {"downloaded_at": "2026-10-16T07:26:37Z",
                               "source_date": "2026-10-16T09:26:34+02:00"}


def test_every_data_route_has_attribution_and_capture(client):
    for path in ("/api/health", "/api/fuels", "/api/stations/4375",
                 "/api/provinces/prices?fuel=gasoleo-a",
                 "/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a"):
        body = client.get(path).json()
        assert body["attribution"] == ATTRIBUTION, path
        assert body["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z", path
        assert "data" in body, path


def test_invalid_parameter_without_database(db):
    """Escenario: Parámetro no válido sin base."""
    client = make_client(db)
    response = client.get("/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a"
                          "&radius_km=51")
    assert_error(response, 422, "parametro_no_valido")
    assert not db.exists()


def test_unknown_fuel_with_the_database_busy(client, db):
    """Escenario: Combustible desconocido con la base ocupada."""
    import time

    with hold_lock(db, 4):
        start = time.monotonic()
        response = client.get("/api/provinces/prices?fuel=diesel")
        elapsed = time.monotonic() - start
    assert_error(response, 422, "combustible_desconocido")
    assert elapsed < 0.5
