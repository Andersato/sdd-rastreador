"""Requisito "Actualización de estaciones existentes" y coordenadas en estaciones existentes."""

from tests.builders import response, station
from tests.storage_helpers import ingest, prices_of, query, station_row

LAT, LON = "Latitud", "Longitud (WGS84)"
OLD = (40.416775, -3.70379)


def first(db, **fields):
    result, _ = ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,399"}, **fields)))
    return result


def coords(db):
    row = station_row(db, "4375")
    return row[6], row[7]


def warnings_of(parsed):
    return [(w.station_id, w.field, w.value) for w in parsed.warnings]


def test_brand_and_schedule_change(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    result, _ = ingest(db, response(station("4375", **{"Rótulo": "CEPSA", "Horario": "L-S: 07:00-22:00", "Precio Gasoleo A": "1,409"})))
    assert query(db, "SELECT COUNT(*) FROM stations") == [(1,)]
    row = station_row(db, "4375")
    assert (row[1], row[5]) == ("CEPSA", "L-S: 07:00-22:00")
    assert prices_of(db, "4375", snapshot_id=1) == {"Gasoleo A": 1.399}
    assert (result.new_stations, result.updated_stations) == (0, 1)


def test_address_and_coordinates_change(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    ingest(db, response(station("4375", **{"Dirección": "CALLE MAYOR, 3", LAT: "40,416900", LON: "-3,703500", "Precio Gasoleo A": "1,409"})))
    row = station_row(db, "4375")
    assert row[2] == "CALLE MAYOR, 3"
    assert coords(db) == (40.4169, -3.7035)
    assert query(db, "SELECT COUNT(*) FROM stations") == [(1,)]


def test_fixed_field_arrives_empty(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    ingest(db, response(station("4375", **{"Horario": "", "Precio Gasoleo A": "1,409"})))
    assert station_row(db, "4375")[5] == ""


def test_coordinates_not_emptied_on_update(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    _, parsed = ingest(db, response(station("4375", **{"Horario": "", LAT: "", LON: "-3,703500", "Precio Gasoleo A": "1,409"})))
    assert station_row(db, "4375")[5] == ""
    assert coords(db) == OLD
    assert warnings_of(parsed) == [("4375", LAT, "")]


def test_identifier_with_spaces_updates_same_station(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    ingest(db, response(station(" 4375 ", **{"Rótulo": "CEPSA", "Precio Gasoleo A": "1,409"})))
    assert [row[0] for row in query(db, "SELECT id FROM stations")] == ["4375"]
    assert station_row(db, "4375")[1] == "CEPSA"


def test_invalid_coordinate_on_existing_station(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    _, parsed = ingest(
        db,
        response(station("4375", **{LAT: "abc", LON: "-3,703500", "Rótulo": "CEPSA", "Precio Gasoleo A": "1,459"})),
    )
    assert coords(db) == OLD
    assert station_row(db, "4375")[1] == "CEPSA"
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert warnings_of(parsed) == [("4375", LAT, "abc")]


def test_empty_coordinate_on_existing_station(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    _, parsed = ingest(db, response(station("4375", **{LAT: "40,416900", LON: "", "Precio Gasoleo A": "1,459"})))
    assert coords(db) == OLD
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert warnings_of(parsed) == [("4375", LON, "")]


def test_missing_coordinate_on_existing_station(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    _, parsed = ingest(db, response(station("4375", drop=[LAT], **{LON: "-3,703500", "Precio Gasoleo A": "1,459"})))
    assert coords(db) == OLD
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.459}
    assert warnings_of(parsed) == [("4375", LAT, "(ausente)")]


def test_invalid_coordinate_on_existing_station_without_coordinates(tmp_path):
    db = tmp_path / "p.db"
    first(db, **{LAT: ""})
    assert coords(db) == (None, None)
    _, parsed = ingest(db, response(station("4375", **{LAT: "abc", LON: "-3,703790", "Precio Gasoleo A": "1,409"})))
    assert coords(db) == (None, None)
    assert warnings_of(parsed) == [("4375", LAT, "abc")]


def test_station_that_disappears(tmp_path):
    db = tmp_path / "p.db"
    first(db)
    before_station = station_row(db, "4375")
    ingest(db, response(station("5120", **{"Precio Gasoleo A": "1,479"})))
    assert station_row(db, "4375") == before_station
    assert prices_of(db, "4375", snapshot_id=1) == {"Gasoleo A": 1.399}
    assert prices_of(db, "4375", snapshot_id=2) == {}
