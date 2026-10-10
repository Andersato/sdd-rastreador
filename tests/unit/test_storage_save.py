"""Guardado de estaciones nuevas y primera ejecución."""

from tests.builders import response, station
from tests.storage_helpers import ingest, prices_of, query, station_row


def test_new_station_saved(tmp_path):
    db = tmp_path / "prices.db"
    result, _ = ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert station_row(db, "4375") == (
        "4375", "REPSOL", "CALLE MAYOR, 1", "Madrid", "MADRID", "L-D: 24H", 40.416775, -3.70379,
    )
    assert (result.new_stations, result.updated_stations, result.prices) == (1, 0, 1)


def test_station_without_any_price(tmp_path):
    db = tmp_path / "prices.db"
    result, _ = ingest(db, response(station("5120", **{"Precio Gasoleo A": ""})))
    assert station_row(db, "5120") is not None
    assert prices_of(db, "5120") == {}
    assert result.prices == 0
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]


def test_database_does_not_exist(tmp_path):
    db = tmp_path / "data" / "prices.db"
    assert not db.parent.exists()
    ingest(
        db,
        response(
            station("4375", **{"Precio Gasoleo A": "1,459"}),
            station("5120", **{"Precio Gasoleo A": "1,479", "Precio Gasolina 95 E5": "1,549"}),
        ),
    )
    assert db.exists()
    assert [row[0] for row in query(db, "SELECT id FROM stations ORDER BY id")] == ["4375", "5120"]
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert query(db, "SELECT COUNT(*) FROM prices") == [(3,)]
    assert sorted(p.name for p in db.parent.iterdir()) == ["prices.db"]
