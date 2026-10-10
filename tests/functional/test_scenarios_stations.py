"""Escenarios de estaciones, de principio a fin (descarga, parser, SQLite y resumen).

Requisitos: "Datos fijos de la estación separados de los precios",
"Coordenadas inválidas" y "Actualización de estaciones existentes sin
duplicarlas".
"""

import pytest

from tests.builders import response, station
from tests.helpers import db_dump
from tests.scenario_helpers import (
    LAT,
    LON,
    assert_no_warnings,
    assert_one_warning,
    run_ingestion,
    warning_lines,
)
from tests.storage_helpers import ingest, prices_of, query, station_row

OLD = (40.416775, -3.70379)


def coords(db, station_id="4375"):
    return station_row(db, station_id)[6:]


def existing(db, **fields):
    """Estación "4375" ya guardada (captura 1) con latitud 40.416775 y longitud -3.70379."""
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"}, **fields)))


# --- Datos fijos de la estación ----------------------------------------------

def test_scenario_new_station(http_server, tmp_path, capsys):
    """Escenario: Estación nueva."""
    db = tmp_path / "p.db"
    data = response(
        station(
            "4375",
            **{
                "Rótulo": "REPSOL",
                "Dirección": "CALLE MAYOR, 1",
                "Municipio": "Madrid",
                "Provincia": "MADRID",
                LAT: "40,416775",
                LON: "-3,703790",
                "Horario": "L-D: 24H",
            },
        )
    )
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert query(db, "SELECT * FROM stations") == [
        ("4375", "REPSOL", "CALLE MAYOR, 1", "Madrid", "MADRID", "L-D: 24H", 40.416775, -3.70379)
    ]
    assert "Estaciones procesadas: 1 (1 nueva, 0 actualizadas)" in out
    assert_no_warnings(out)


def test_scenario_fixed_text_field_empty_or_missing(http_server, tmp_path, capsys):
    """Escenario: Dato fijo de texto vacío o ausente."""
    db = tmp_path / "p.db"
    data = response(
        station("5120", drop=["Horario"], **{"Rótulo": "", "Dirección": None, "Precio Gasoleo A": "1,459"})
    )
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    row = station_row(db, "5120")
    assert (row[1], row[2], row[5]) == ("", "", "")
    assert prices_of(db, "5120") == {"Gasoleo A": 1.459}
    assert_no_warnings(out)


def test_scenario_fixed_text_field_as_number(http_server, tmp_path, capsys):
    """Escenario: Dato fijo de texto que llega como número."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(http_server, db, response(station("5120", **{"Rótulo": 123})), capsys)
    assert code == 0
    assert station_row(db, "5120")[1] == "123"
    assert query(db, "SELECT typeof(brand) FROM stations") == [("text",)]
    assert_no_warnings(out)


def test_scenario_texts_with_spaces(http_server, tmp_path, capsys):
    """Escenario: Textos con espacios (se guardan tal cual, decisión del usuario)."""
    db = tmp_path / "p.db"
    code, _, _ = run_ingestion(http_server, db, response(station("5120", **{"Rótulo": " GALP "})), capsys)
    assert code == 0
    assert station_row(db, "5120")[1] == " GALP "


def test_scenario_identifier_with_spaces(http_server, tmp_path, capsys):
    """Escenario: Identificador con espacios."""
    db = tmp_path / "p.db"
    existing(db)
    code, out, _ = run_ingestion(
        http_server,
        db,
        response(station(" 4375 ", **{"Rótulo": "CEPSA", "Precio Gasoleo A": "1,459"})),
        capsys,
    )
    assert code == 0
    assert query(db, "SELECT id FROM stations") == [("4375",)]
    assert station_row(db, "4375")[1] == "CEPSA"
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert query(db, "SELECT DISTINCT station_id FROM prices") == [("4375",)]
    assert "Estaciones procesadas: 1 (0 nuevas, 1 actualizada)" in out


# --- Coordenadas inválidas en estación nueva ---------------------------------

NEW_STATION_CASES = [
    # (escenario, campos, claves quitadas, textos que deben aparecer en el aviso)
    ("Latitud con formato inválido en estación nueva", {LAT: "abc", LON: "-3,703790"}, (), (LAT, '"abc"')),
    ("Latitud fuera de rango en estación nueva", {LAT: "123,000000", LON: "-3,703790"}, (), (LAT, '"123,000000"')),
    ("Longitud con formato inválido en estación nueva", {LAT: "40,416775", LON: "-3,70x790"}, (), (LON, '"-3,70x790"')),
    ("Longitud fuera de rango en estación nueva", {LAT: "40,416775", LON: "-190,000000"}, (), (LON, '"-190,000000"')),
    ("Coordenada vacía en estación nueva", {LAT: "", LON: "-3,703790"}, (), (LAT,)),
    ("Coordenada ausente en estación nueva", {LAT: "40,416775"}, (LON,), (LON, "(ausente)")),
    ("Coordenada null en estación nueva", {LAT: None, LON: "-3,703790"}, (), (LAT,)),
    ("Coordenada que no es texto en estación nueva", {LAT: 40.416775, LON: "-3,703790"}, (), (LAT,)),
]


@pytest.mark.parametrize(
    "fields, drop, warning_parts",
    [case[1:] for case in NEW_STATION_CASES],
    ids=[case[0] for case in NEW_STATION_CASES],
)
def test_scenario_invalid_coordinate_on_new_station(http_server, tmp_path, capsys, fields, drop, warning_parts):
    """Escenarios de "Coordenadas inválidas" en estación nueva (uno por id)."""
    db = tmp_path / "p.db"
    data = response(station("4375", drop=drop, **{"Precio Gasoleo A": "1,459"}, **fields))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert coords(db) == (None, None)
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert_one_warning(out, "4375", *warning_parts)


def test_scenario_both_coordinates_invalid(http_server, tmp_path, capsys):
    """Escenario: Las dos coordenadas inválidas."""
    db = tmp_path / "p.db"
    data = response(station("4375", drop=[LON], **{LAT: "abc", "Precio Gasoleo A": "1,459"}))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert coords(db) == (None, None)
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459}
    assert "Avisos: 2" in out
    lat_line, lon_line = warning_lines(out)
    assert "4375" in lat_line and LAT in lat_line and '"abc"' in lat_line
    assert "4375" in lon_line and LON in lon_line and "(ausente)" in lon_line


def test_scenario_range_limits(http_server, tmp_path, capsys):
    """Escenario: Extremos del rango."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("9001", **{LAT: "-90,000000", LON: "180,000000"})), capsys
    )
    assert code == 0
    assert coords(db, "9001") == (-90.0, 180.0)
    assert_no_warnings(out)


def test_scenario_canary_islands_coordinates(http_server, tmp_path, capsys):
    """Escenario: Coordenadas de Canarias."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(
        http_server, db, response(station("8001", **{LAT: "28,123546", LON: "-15,436257"})), capsys
    )
    assert code == 0
    assert coords(db, "8001") == (28.123546, -15.436257)
    assert_no_warnings(out)


# --- Coordenadas inválidas en estación existente -----------------------------

def test_scenario_invalid_coordinate_on_existing_station(http_server, tmp_path, capsys):
    """Escenario: Coordenada inválida en estación existente."""
    db = tmp_path / "p.db"
    existing(db)
    data = response(
        station("4375", **{LAT: "abc", LON: "-3,703500", "Rótulo": "CEPSA", "Precio Gasoleo A": "1,459"})
    )
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert coords(db) == OLD
    assert station_row(db, "4375")[1] == "CEPSA"
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert_one_warning(out, "4375", LAT, '"abc"')


def test_scenario_empty_coordinate_on_existing_station(http_server, tmp_path, capsys):
    """Escenario: Coordenada vacía en estación existente."""
    db = tmp_path / "p.db"
    existing(db)
    data = response(station("4375", **{LAT: "40,416900", LON: "", "Precio Gasoleo A": "1,459"}))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert coords(db) == OLD
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert_one_warning(out, "4375", LON)


def test_scenario_missing_coordinate_on_existing_station(http_server, tmp_path, capsys):
    """Escenario: Coordenada ausente en estación existente."""
    db = tmp_path / "p.db"
    existing(db)
    data = response(station("4375", drop=[LAT], **{LON: "-3,703500", "Precio Gasoleo A": "1,459"}))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert coords(db) == OLD
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert_one_warning(out, "4375", LAT, "(ausente)")


def test_scenario_invalid_coordinate_on_existing_station_without_coordinates(http_server, tmp_path, capsys):
    """Escenario: Coordenada inválida en estación existente sin coordenadas."""
    db = tmp_path / "p.db"
    existing(db, **{LAT: ""})
    assert coords(db) == (None, None)
    code, out, _ = run_ingestion(
        http_server, db, response(station("4375", **{LAT: "abc", LON: "-3,703790"})), capsys
    )
    assert code == 0
    assert coords(db) == (None, None)
    assert_one_warning(out, "4375", LAT, '"abc"')


# --- Actualización de estaciones existentes ----------------------------------

def test_scenario_brand_and_schedule_change(http_server, tmp_path, capsys):
    """Escenario: Cambio de rótulo y horario."""
    db = tmp_path / "p.db"
    existing(db, **{"Rótulo": "REPSOL", "Horario": "L-D: 24H"})
    old_prices = query(db, "SELECT * FROM prices")
    data = response(station("4375", **{"Rótulo": "CEPSA", "Horario": "L-S: 07:00-22:00", "Precio Gasoleo A": "1,459"}))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert query(db, "SELECT id, brand, schedule FROM stations") == [("4375", "CEPSA", "L-S: 07:00-22:00")]
    assert query(db, "SELECT * FROM prices WHERE snapshot_id = 1") == old_prices
    assert "Estaciones procesadas: 1 (0 nuevas, 1 actualizada)" in out


def test_scenario_address_and_coordinates_change(http_server, tmp_path, capsys):
    """Escenario: Cambio de dirección y coordenadas."""
    db = tmp_path / "p.db"
    existing(db, **{"Dirección": "CALLE MAYOR, 1"})
    data = response(station("4375", **{"Dirección": "CALLE MAYOR, 3", LAT: "40,416900", LON: "-3,703500"}))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert query(db, "SELECT id, address, latitude, longitude FROM stations") == [
        ("4375", "CALLE MAYOR, 3", 40.4169, -3.7035)
    ]
    assert_no_warnings(out)


def test_scenario_fixed_field_arrives_empty(http_server, tmp_path, capsys):
    """Escenario: Dato fijo que llega vacío."""
    db = tmp_path / "p.db"
    existing(db, **{"Horario": "L-D: 24H"})
    code, out, _ = run_ingestion(http_server, db, response(station("4375", **{"Horario": ""})), capsys)
    assert code == 0
    assert station_row(db, "4375")[5] == ""
    assert_no_warnings(out)


def test_scenario_coordinates_not_emptied_on_update(http_server, tmp_path, capsys):
    """Escenario: Las coordenadas no se vacían al actualizar."""
    db = tmp_path / "p.db"
    existing(db, **{"Horario": "L-D: 24H"})
    data = response(station("4375", **{"Horario": "", LAT: "", LON: "-3,703500"}))
    code, out, _ = run_ingestion(http_server, db, data, capsys)
    assert code == 0
    assert station_row(db, "4375")[5] == ""
    assert coords(db) == OLD
    assert_one_warning(out, "4375", LAT)


def test_scenario_station_that_disappears(http_server, tmp_path, capsys):
    """Escenario: Estación que deja de aparecer."""
    db = tmp_path / "p.db"
    existing(db)
    before = db_dump(db)
    code, _, _ = run_ingestion(
        http_server, db, response(station("5120", **{"Precio Gasoleo A": "1,479"})), capsys
    )
    assert code == 0
    after = db_dump(db)
    # Todo lo que había antes sigue igual (nada borrado ni modificado)...
    assert [row for row in after["stations"] if row[0] == "4375"] == [
        row for row in before["stations"] if row[0] == "4375"
    ]
    assert set(before["prices"]) <= set(after["prices"])
    # ...y la nueva captura no tiene precios de "4375".
    assert prices_of(db, "4375", snapshot_id=2) == {}
    assert prices_of(db, "5120", snapshot_id=2) == {"Gasoleo A": 1.479}
