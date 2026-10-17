"""«Salud del servicio», «Intervalo no válido en la salud», «Lista de
combustibles», «Catálogo de combustibles» y «Combustible obligatorio por su
identificador», por HTTP (prices-api)."""

import sqlite3
from datetime import timedelta

import pytest

from src.ingestion.storage import SCHEMA
from tests.api_helpers import (
    CAPTURE_AT,
    assert_error,
    basic_db,
    hold_lock,
    make_client,
    priced,
    save,
)
from tests.storage_helpers import make_pending_journal


@pytest.fixture
def db(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    return folder / "prices.db"


# --- salud --------------------------------------------------------------------

def test_health_ok(db):
    """Escenario: Todo correcto."""
    basic_db(db)
    body = make_client(db).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"
    assert body["data"] == {"stale_after_hours": 13, "unexposed_fuels": []}


def test_health_old_capture(db):
    """Escenario: Captura antigua."""
    basic_db(db)
    client = make_client(db, now=CAPTURE_AT + timedelta(hours=13, seconds=23))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "desactualizada"


def test_health_other_interval(db):
    """Escenario: Otro intervalo."""
    basic_db(db)
    client = make_client(db, now=CAPTURE_AT + timedelta(hours=24, minutes=30), interval_text="12")
    body = client.get("/api/health").json()
    assert (body["status"], body["data"]["stale_after_hours"]) == ("ok", 25)


def test_health_unexposed_fuel(db):
    """Escenario: Combustible fuera del catálogo."""
    save(db, priced("1", {"Gasoleo A": "1,459", "Metanol": "1,200"}),
         priced("2", {"Metanol": "1,250"}))
    body = make_client(db).get("/api/health").json()
    assert body["data"]["unexposed_fuels"] == [{"name": "Metanol", "stations": 2}]
    assert body["status"] == "ok"


def test_health_invalid_interval(db):
    """Escenario: Intervalo imposible."""
    basic_db(db)
    client = make_client(db, interval_text="25")
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configuracion_no_valida"
    assert body["data"]["stale_after_hours"] is None
    assert "'25'" in body["data"]["message"]
    assert "horas enteras de 1 a 24" in body["data"]["message"]
    assert body["capture"]["downloaded_at"] == "2026-10-16T07:26:37Z"
    assert client.get("/api/fuels").status_code == 200


def test_health_invalid_interval_without_database(db):
    """Escenario: Intervalo no válido y sin base."""
    body = assert_error(make_client(db, interval_text="25").get("/api/health"), 503, "sin_base")
    assert body["status"] == "error"


def schema_only(db):
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    conn.close()


@pytest.mark.parametrize(("prepare", "code"), [
    (lambda db: None, "sin_base"),
    (schema_only, "sin_capturas"),
    (lambda db: db.write_text("hola"), "base_ilegible"),
])
def test_health_errors_have_status_error(db, prepare, code):
    """Escenario: Errores de la salud."""
    prepare(db)
    body = assert_error(make_client(db).get("/api/health"), 503, code)
    assert body["status"] == "error"


def test_health_error_when_busy(db):
    """Escenario: Errores de la salud (base ocupada)."""
    basic_db(db)
    with hold_lock(db, 4):
        response = make_client(db).get("/api/health")
    body = assert_error(response, 503, "base_ocupada")
    assert body["status"] == "error"
    assert response.headers["retry-after"] == "5"


def test_health_error_with_pending_journal(db):
    basic_db(db)
    make_pending_journal(db)
    body = assert_error(make_client(db).get("/api/health"), 503, "recogida_a_medias")
    assert body["status"] == "error"


# --- errores de la base por HTTP -------------------------------------------------

def test_no_database_by_http(db):
    """Escenario: Sin base de datos."""
    body = assert_error(make_client(db).get("/api/stations/4375"), 503, "sin_base")
    assert body["error"]["message"] == "todavía no hay base de datos: lanza la primera recogida"
    assert "status" not in body
    assert not db.exists()


def test_first_capture_with_the_api_running(db):
    """Escenario: Primera captura con la API en marcha."""
    client = make_client(db)
    assert_error(client.get("/api/fuels"), 503, "sin_base")
    basic_db(db)
    assert client.get("/api/fuels").status_code == 200


def test_unknown_version_by_http(db):
    """Escenario: Estructura desconocida."""
    basic_db(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 2")
    conn.close()
    assert_error(make_client(db).get("/api/fuels"), 503, "base_no_compatible")


# --- combustibles ---------------------------------------------------------------

def test_fuels_with_test_data(db):
    """Escenario: Datos de prueba."""
    save(db,
         priced("1", {"Gasoleo A": "1,459", "Gasolina 95 E5": "1,529", "Hidrogeno": "9,900"}),
         priced("2", {"Gasoleo A": "1,469", "Gasolina 95 E5": "1,539", "Adblue": "0,999"}),
         priced("3", {"Gasoleo A": "1,479"}))
    body = make_client(db).get("/api/fuels").json()
    items = body["data"]
    assert len(items) == 21
    assert items[0] == {"name": "Gasoleo A", "slug": "gasoleo-a", "unit": "€/l",
                        "kind": "combustible", "stations": 3}
    assert [(i["slug"], i["stations"]) for i in items[1:4]] == [
        ("gasolina-95-e5", 2), ("adblue", 1), ("hidrogeno", 1)]
    assert items[2]["kind"] == "aditivo"
    assert items[3]["unit"] == "€/kg"
    rest = items[4:]
    assert len(rest) == 17 and all(i["stations"] == 0 for i in rest)
    assert [i["slug"] for i in rest] == sorted(i["slug"] for i in rest)


def test_fuels_without_source_date(db):
    """Escenario: Captura sin fecha de la fuente."""
    save(db, priced("1", {"Gasoleo A": "1,459"}),
         instant=CAPTURE_AT.replace(month=11, day=2, hour=5, minute=17, second=3),
         drop=("Fecha",))
    body = make_client(db).get("/api/fuels").json()
    assert body["capture"] == {"downloaded_at": "2026-11-02T05:17:03Z", "source_date": None}


def test_unexposed_fuel_not_in_a_station(db):
    """Escenario: Combustible fuera del catálogo en una estación."""
    save(db, priced("4375", {"Gasoleo A": "1,459", "Metanol": "1,200"}))
    prices = make_client(db).get("/api/stations/4375").json()["data"]["prices"]
    assert [p["slug"] for p in prices] == ["gasoleo-a"]


@pytest.mark.parametrize("value", ["Gasoleo%20A", "GASOLEO-A", "metanol", "diesel"])
def test_unknown_fuel_identifier(db, value):
    """Escenarios: Nombre en lugar del identificador; Combustible fuera del catálogo."""
    basic_db(db)
    body = assert_error(make_client(db).get(f"/api/provinces/prices?fuel={value}"), 422,
                        "combustible_desconocido")
    assert "/api/fuels" in body["error"]["message"]


@pytest.mark.parametrize("path", ["/api/stations/nearby?lat=40.4168&lon=-3.7038",
                                  "/api/provinces/prices"])
def test_missing_fuel(db, path):
    """Escenario: Falta el combustible."""
    basic_db(db)
    body = assert_error(make_client(db).get(path), 422, "parametro_no_valido")
    assert "fuel" in body["error"]["message"]
    assert "/api/fuels" in body["error"]["message"]


def test_adblue_is_accepted_as_fuel(db):
    """Escenario: AdBlue (se admite como `fuel`)."""
    save(db, priced("1", {"Adblue": "0,999"}, lat=40.4168, lon=-3.7038))
    client = make_client(db)
    assert client.get("/api/provinces/prices?fuel=adblue").status_code == 200
    nearby = client.get("/api/stations/nearby?lat=40.4168&lon=-3.7038&fuel=adblue").json()
    assert nearby["data"]["total"] == 1
