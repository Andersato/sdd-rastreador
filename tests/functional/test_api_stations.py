"""«Gasolineras cercanas», «Límites de la búsqueda de cercanas», «Ficha de una
estación», «Coordenadas fuera de España» y «Limpieza de textos al responder»,
por HTTP (prices-api)."""

import pytest

from tests.api_helpers import assert_error, make_client, priced, save
from tests.helpers import db_dump

SEARCH = "/api/stations/nearby?lat=40.416775&lon=-3.703790&fuel=gasoleo-a"


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


@pytest.fixture
def madrid(db):
    """Las estaciones del escenario «Búsqueda en Madrid»."""
    save(db,
         priced("1001", {"Gasoleo A": "1,459"}, 40.4250, -3.7038),
         priced("1002", {"Gasoleo A": "1,459"}, 40.4168, -3.6800),
         priced("1003", {"Gasoleo A": "1,399"}, 40.4400, -3.7300, **{"Rótulo": "GALP"}),
         priced("1004", {"Gasoleo A": "1,299"}, 40.4630, -3.7038),
         priced("1005", {"Gasolina 95 E5": "1,529"}, 40.416775, -3.703790),
         priced("1006", {"Gasoleo A": "1,199"}, 0.0, 0.0))
    return make_client(db)


def ids(body):
    return [s["id"] for s in body["data"]["stations"]]


# --- cercanas -------------------------------------------------------------------

def test_search_in_madrid(madrid):
    """Escenario: Búsqueda en Madrid."""
    body = madrid.get(SEARCH).json()
    assert ids(body) == ["1003", "1001", "1002"]
    assert [(s["price"], s["distance_km"]) for s in body["data"]["stations"]] == [
        (1.399, 3.4), (1.459, 0.91), (1.459, 2.01)]


def test_shape_of_the_response(madrid):
    """Escenario: Forma de la respuesta."""
    data = madrid.get(SEARCH).json()["data"]
    assert data["fuel"] == {"name": "Gasoleo A", "slug": "gasoleo-a", "unit": "€/l",
                            "kind": "combustible"}
    assert data["center"] == {"lat": 40.416775, "lon": -3.70379}
    assert (data["radius_km"], data["limit"], data["total"]) == (5, 20, 3)
    assert data["stations"][0] == {
        "id": "1003", "brand": "GALP", "address": "CALLE MAYOR, 1", "municipality": "Madrid",
        "province": "MADRID", "latitude": 40.44, "longitude": -3.73, "price": 1.399,
        "unit": "€/l", "distance_km": 3.4}


def test_bigger_radius(madrid):
    """Escenario: Radio mayor."""
    body = madrid.get(SEARCH + "&radius_km=10").json()
    assert ids(body) == ["1004", "1003", "1001", "1002"]
    assert body["data"]["stations"][0]["distance_km"] == 5.14


def test_same_price_and_distances_that_round_the_same(db):
    """Escenario: Mismo precio y distancias que se redondean igual."""
    # Al norte del punto: 2.0140 km ("3001") y 2.0111 km ("3002"); las dos 2.01.
    save(db, priced("3001", {"Gasoleo A": "1,459"}, 40.434887, -3.70379),
         priced("3002", {"Gasoleo A": "1,459"}, 40.434861, -3.70379))
    stations = make_client(db).get(SEARCH).json()["data"]["stations"]
    assert [s["id"] for s in stations] == ["3002", "3001"]
    assert [s["distance_km"] for s in stations] == [2.01, 2.01]


def test_limit_of_results(db):
    """Escenario: Límite de resultados."""
    save(db, *(priced(f"{2000 + i}", {"Gasoleo A": f"1,{400 + i}"}, 40.4168 + i / 10000, -3.7038)
               for i in range(30)))
    data = make_client(db).get(SEARCH).json()["data"]
    assert data["total"] == 30
    assert [s["id"] for s in data["stations"]] == [f"{2000 + i}" for i in range(20)]


def test_no_results(madrid):
    """Escenario: Sin resultados."""
    response = madrid.get("/api/stations/nearby?lat=28.1235&lon=-15.4363&fuel=gasoleo-a")
    assert response.status_code == 200
    assert (response.json()["data"]["total"], ids(response.json())) == (0, [])


def test_station_just_outside_a_zone(db):
    """Escenario: Estación justo fuera de una zona."""
    save(db, priced("2001", {"Gasoleo A": "1,459"}, 42.0, -9.45),
         priced("2002", {"Gasoleo A": "1,459"}, 42.0, -9.30))
    body = make_client(db).get(
        "/api/stations/nearby?lat=42.0&lon=-9.35&fuel=gasoleo-a&radius_km=10").json()
    assert ids(body) == ["2002"]
    assert body["data"]["stations"][0]["distance_km"] == 4.13


# --- límites --------------------------------------------------------------------

@pytest.mark.parametrize(("query", "text"), [
    ("&radius_km=51", "el radio máximo es 50 km"),
    ("&radius_km=0", "radius_km"),
    ("&radius_km=-3", "radius_km"),
    ("&limit=0", "el límite es un entero de 1 a 100"),
    ("&limit=101", "el límite es un entero de 1 a 100"),
    ("&limit=2.5", "el límite es un entero de 1 a 100"),
])
def test_out_of_range_parameters(madrid, query, text):
    """Escenarios: Radio demasiado grande, Radio cero o negativo, Límite fuera de rango."""
    body = assert_error(madrid.get(SEARCH + query), 422, "parametro_no_valido")
    assert text in body["error"]["message"]


@pytest.mark.parametrize(("query", "name"), [
    ("lat=91&lon=-3.7", "lat"), ("lat=40.4&lon=200", "lon"),
    ("lat=nan&lon=-3.7", "lat"), ("lat=inf&lon=-3.7", "lat"), ("lat=40.4&lon=-inf", "lon"),
])
def test_impossible_coordinates(madrid, query, name):
    """Escenario: Coordenadas imposibles."""
    body = assert_error(madrid.get(f"/api/stations/nearby?{query}&fuel=gasoleo-a"), 422,
                        "parametro_no_valido")
    assert body["error"]["message"].startswith(name)


def test_point_outside_spain(madrid):
    """Escenario: Punto fuera de España."""
    assert_error(madrid.get("/api/stations/nearby?lat=48.8566&lon=2.3522&fuel=gasoleo-a"), 422,
                 "fuera_de_espana")


def test_point_in_portugal_inside_the_rectangle(madrid):
    """Escenario: Punto en Portugal dentro del rectángulo."""
    response = madrid.get("/api/stations/nearby?lat=38.7223&lon=-9.1393&fuel=gasoleo-a")
    assert response.status_code == 200
    assert response.json()["data"]["stations"] == []


# --- ficha ----------------------------------------------------------------------

def test_station_with_prices(db):
    """Escenario: Estación con precios."""
    save(db, priced("4375", {"Gasolina 95 E5": "1,529", "Gasoleo A": "1,459"}))
    data = make_client(db).get("/api/stations/4375").json()["data"]
    assert {k: v for k, v in data.items() if k != "prices"} == {
        "id": "4375", "brand": "REPSOL", "address": "CALLE MAYOR, 1", "municipality": "Madrid",
        "province": "MADRID", "schedule": "L-D: 24H", "latitude": 40.416775,
        "longitude": -3.70379}
    assert data["prices"] == [
        {"slug": "gasoleo-a", "name": "Gasoleo A", "unit": "€/l", "kind": "combustible",
         "price": 1.459},
        {"slug": "gasolina-95-e5", "name": "Gasolina 95 E5", "unit": "€/l",
         "kind": "combustible", "price": 1.529}]


def test_station_without_prices_in_the_last_capture(db):
    """Escenario: Estación sin precios en la última captura."""
    from datetime import timedelta

    from tests.api_helpers import CAPTURE_AT

    save(db, priced("5120", {"Gasoleo A": "1,459"}), priced("4375", {"Gasoleo A": "1,469"}),
         instant=CAPTURE_AT - timedelta(hours=6))
    save(db, priced("4375", {"Gasoleo A": "1,479"}))
    response = make_client(db).get("/api/stations/5120")
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["id"], data["prices"]) == ("5120", [])


def test_unknown_station(db):
    """Escenario: Estación inexistente."""
    save(db, priced("4375", {"Gasoleo A": "1,459"}))
    body = assert_error(make_client(db).get("/api/stations/99999"), 404, "estacion_no_encontrada")
    assert "99999" in body["error"]["message"]


@pytest.mark.parametrize(("ideess", "lat", "lon"), [("11988", 0.0, 0.0),
                                                   ("16268", -8.659472, 42.037472)])
def test_coordinates_outside_spain_are_null(db, ideess, lat, lon):
    """Escenarios: Coordenadas (0, 0); Latitud y longitud intercambiadas."""
    save(db, priced(ideess, {"Gasoleo A": "1,499"}, lat, lon))
    before = db_dump(db)
    data = make_client(db).get(f"/api/stations/{ideess}").json()["data"]
    assert (data["latitude"], data["longitude"]) == (None, None)
    assert db_dump(db) == before


def test_station_in_the_canary_islands(db):
    """Escenario: Estación de Canarias."""
    save(db, priced("7001", {"Gasoleo A": "1,299"}, 28.1235, -15.4363))
    data = make_client(db).get("/api/stations/7001").json()["data"]
    assert (data["latitude"], data["longitude"]) == (28.1235, -15.4363)


# --- limpieza de textos -----------------------------------------------------------

def test_texts_are_trimmed_in_the_response_only(db):
    """Escenarios: Texto con espacios; Tabuladores y espacios interiores; Texto vacío."""
    save(db, priced("5120", {"Gasoleo A": "1,459"}, **{
        "Rótulo": " GALP ", "Dirección": "\tCALLE  MAYOR, 1 ", "Horario": "   "}))
    data = make_client(db).get("/api/stations/5120").json()["data"]
    assert (data["brand"], data["address"], data["schedule"]) == ("GALP", "CALLE  MAYOR, 1", None)
    from tests.storage_helpers import station_row
    assert station_row(db, "5120")[1] == " GALP "
