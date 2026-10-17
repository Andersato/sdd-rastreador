"""«Precio medio por provincia» y «Redondeo y orden de las provincias», y
«Muchas consultas no cambian ./data» (prices-api)."""

import sqlite3

import pytest

from tests.api_helpers import folder_state, assert_error, make_client, priced, save

PATH = "/api/provinces/prices?fuel=gasoleo-a"


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


def province(body, name):
    return next(p for p in body["data"]["provinces"] if p["province"] == name)


def test_madrid_average(db):
    """Escenario: Media de Madrid."""
    save(db, *(priced(i, {"Gasoleo A": p}) for i, p in
               [("1001", "1,459"), ("1002", "1,459"), ("1003", "1,399"), ("1004", "1,299")]))
    body = make_client(db).get(PATH).json()
    assert body["data"]["fuel"]["unit"] == "€/l"
    assert province(body, "MADRID") == {"province": "MADRID", "average": 1.404, "min": 1.299,
                                        "max": 1.459, "stations": 4}


def test_same_name_with_spaces(db):
    """Escenario: Mismo nombre con espacios."""
    save(db, priced("1001", {"Gasoleo A": "1,459"}, Provincia="MADRID"),
         priced("1002", {"Gasoleo A": "1,459"}, Provincia="MADRID "))
    provinces = make_client(db).get(PATH).json()["data"]["provinces"]
    assert [(p["province"], p["stations"]) for p in provinces] == [("MADRID", 2)]


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_province(db, value):
    """Escenario: Provincia vacía."""
    save(db, priced("1001", {"Gasoleo A": "1,459"}),
         priced("1007", {"Gasoleo A": "1,299"}, Provincia=value))
    provinces = make_client(db).get(PATH).json()["data"]["provinces"]
    assert provinces == [{"province": "MADRID", "average": 1.459, "min": 1.459, "max": 1.459,
                          "stations": 1}]


def test_province_without_that_fuel(db):
    """Escenario: Provincia sin ese combustible."""
    save(db, priced("1", {"Hidrogeno": "9,900"}, Provincia="MADRID"),
         priced("2", {"Gasoleo A": "1,459"}, Provincia="SORIA"))
    body = make_client(db).get("/api/provinces/prices?fuel=hidrogeno").json()
    assert [p["province"] for p in body["data"]["provinces"]] == ["MADRID"]
    assert body["data"]["fuel"]["unit"] == "€/kg"


def test_station_without_coordinates_counts(db):
    """Escenario: Estación sin coordenadas en la media por provincia."""
    save(db, priced("11988", {"Gasoleo A": "1,499"}, 0.0, 0.0, Provincia="BARCELONA"))
    body = make_client(db).get(PATH).json()
    assert province(body, "BARCELONA")["stations"] == 1


def test_average_with_half(db):
    """Escenario: Media con mitad."""
    save(db, priced("1", {"Gasoleo A": "1,404"}, Provincia="LUGO"),
         priced("2", {"Gasoleo A": "1,405"}, Provincia="LUGO"))
    assert province(make_client(db).get(PATH).json(), "LUGO")["average"] == 1.405


def test_tie_on_average(db):
    """Escenario: Empate de media."""
    save(db, priced("1", {"Gasoleo A": "1,450"}, Provincia="ÁVILA"),
         priced("2", {"Gasoleo A": "1,450"}, Provincia="ZAMORA"),
         priced("3", {"Gasoleo A": "1,449"}, Provincia="CORUÑA (A)"))
    provinces = make_client(db).get(PATH).json()["data"]["provinces"]
    assert [p["province"] for p in provinces] == ["CORUÑA (A)", "ZAMORA", "ÁVILA"]


def test_missing_fuel(db):
    """Escenario: Falta el combustible."""
    save(db, priced("1", {"Gasoleo A": "1,459"}))
    assert_error(make_client(db).get("/api/provinces/prices"), 422, "parametro_no_valido")


def test_many_requests_do_not_change_data(db):
    """Escenario: Muchas consultas no cambian ./data (100 peticiones a todas las rutas)."""
    from datetime import timedelta

    from tests.api_helpers import CAPTURE_AT

    stations = [priced("4375", {"Gasoleo A": "1,459", "Gasolina 95 E5": "1,529"}),
                priced("1003", {"Gasoleo A": "1,399"}, 40.44, -3.73, Provincia="TOLEDO")]
    for n in range(8):
        save(db, *stations, instant=CAPTURE_AT - timedelta(hours=6 * (7 - n)))
    before = folder_state(db.parent)
    client = make_client(db)
    paths = ["/api/health", "/api/fuels", "/api/stations/4375", "/api/stations/99999",
             "/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=gasoleo-a&radius_km=50",
             PATH, "/api/provinces/prices?fuel=metanol", "/api/openapi.json", "/api/precios",
             "/api/stations/nearby?lat=nan&lon=-3.7&fuel=gasoleo-a"]
    for i in range(100):
        assert client.get(paths[i % len(paths)]).status_code < 500
    assert folder_state(db.parent) == before
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        conn.close()
