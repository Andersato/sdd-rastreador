"""Escenarios de "Captura con fecha y hora" y "Primera ejecución", de principio a fin."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.builders import response, station
from tests.helpers import run_cli
from tests.scenario_helpers import assert_no_warnings, assert_one_warning, run_ingestion
from tests.storage_helpers import prices_of, query

MADRID_SUMMER = timezone(timedelta(hours=2))


def two_stations(fecha="10/10/2026 19:05:23", drop=(), price="1,459"):
    return response(
        station("4375", **{"Precio Gasoleo A": price, "Precio Gasolina 95 E5": "1,529"}),
        station("5120", **{"Precio Gasoleo A": "1,479"}),
        fecha=fecha,
        drop=drop,
    )


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 10, 19, 5, 30, tzinfo=MADRID_SUMMER),
        datetime(2026, 10, 10, 13, 5, 30, tzinfo=timezone(timedelta(hours=-4))),
    ],
    ids=["reloj-utc", "reloj-madrid", "reloj-nueva-york"],
)
def test_scenario_snapshot_record(http_server, tmp_path, capsys, now):
    """Escenario: Registro de la captura (el mismo instante expresado en varias zonas)."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(http_server, db, two_stations(), capsys, now=now)
    assert code == 0
    [(snapshot_id, downloaded_at, source_date)] = query(db, "SELECT id, downloaded_at, source_date FROM snapshots")
    assert downloaded_at == "2026-10-10T17:05:30Z"
    assert source_date == "2026-10-10T19:05:23"
    assert query(db, "SELECT DISTINCT snapshot_id FROM prices") == [(snapshot_id,)]
    assert query(db, "SELECT COUNT(*) FROM prices") == [(3,)]
    assert_no_warnings(out)


def test_scenario_snapshot_record_in_other_machine_timezone(http_server, tmp_path):
    """Escenario: Registro de la captura, con la CLI real en una máquina con otra zona horaria."""
    db = tmp_path / "p.db"
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    before = datetime.now(timezone.utc).replace(microsecond=0)
    result = run_cli(url, db, env={"TZ": "Asia/Tokyo"})
    after = datetime.now(timezone.utc)
    assert result.returncode == 0, result.stderr
    [(snapshot_id, downloaded_at, source_date)] = query(db, "SELECT id, downloaded_at, source_date FROM snapshots")
    instant = datetime.strptime(downloaded_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert before <= instant <= after
    assert source_date == "2026-10-10T19:05:23"
    assert query(db, "SELECT DISTINCT snapshot_id FROM prices") == [(snapshot_id,)]


def test_scenario_two_runs_with_same_api_fecha(http_server, tmp_path, capsys):
    """Escenario: Dos ejecuciones con la misma Fecha de la API."""
    db = tmp_path / "p.db"
    fecha = "10/10/2026 07:50:12"
    first = datetime(2026, 10, 10, 8, 0, tzinfo=MADRID_SUMMER)
    second = datetime(2026, 10, 10, 8, 5, tzinfo=MADRID_SUMMER)
    assert run_ingestion(http_server, db, two_stations(fecha=fecha), capsys, now=first)[0] == 0
    first_prices = query(db, "SELECT * FROM prices WHERE snapshot_id = 1")
    assert run_ingestion(http_server, db, two_stations(fecha=fecha, price="1,469"), capsys, now=second)[0] == 0
    assert query(db, "SELECT id, downloaded_at, source_date FROM snapshots ORDER BY id") == [
        (1, "2026-10-10T06:00:00Z", "2026-10-10T07:50:12"),
        (2, "2026-10-10T06:05:00Z", "2026-10-10T07:50:12"),
    ]
    assert query(db, "SELECT * FROM prices WHERE snapshot_id = 1") == first_prices
    assert prices_of(db, "4375", snapshot_id=2)["Gasoleo A"] == 1.469


def test_scenario_fecha_with_single_digits(http_server, tmp_path, capsys):
    """Escenario: Fecha con números de un dígito."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(http_server, db, two_stations(fecha="1/2/2026 9:05:23"), capsys)
    assert code == 0
    assert query(db, "SELECT source_date FROM snapshots") == [("2026-02-01T09:05:23",)]
    assert_no_warnings(out)


@pytest.mark.parametrize(
    "fecha, drop",
    [
        (None, ("Fecha",)),
        (None, ()),
        ("2026-10-10 19:05", ()),
        ("31/02/2026 10:00:00", ()),
    ],
    ids=["ausente", "null", "otro-formato", "fecha-imposible"],
)
def test_scenario_api_fecha_missing_or_other_format(http_server, tmp_path, capsys, fecha, drop):
    """Escenario: Fecha de la API ausente o con otro formato."""
    db = tmp_path / "p.db"
    code, out, _ = run_ingestion(http_server, db, two_stations(fecha=fecha, drop=drop), capsys)
    assert code == 0
    assert query(db, "SELECT downloaded_at, source_date FROM snapshots") == [("2026-10-10T17:05:30Z", None)]
    assert query(db, "SELECT COUNT(*) FROM prices") == [(3,)]
    assert_one_warning(out, "Fecha")


def test_scenario_database_does_not_exist(http_server, tmp_path):
    """Escenario: Base de datos inexistente (CLI real como subproceso)."""
    db = tmp_path / "nueva" / "prices.db"
    assert not db.parent.exists()
    url = http_server.add_fixture("/api", "valid_two_stations.json")
    result = run_cli(url, db)
    assert result.returncode == 0, result.stderr
    assert query(db, "SELECT id FROM stations ORDER BY id") == [("4375",), ("5120",)]
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(1,)]
    assert prices_of(db, "4375") == {"Gasoleo A": 1.459, "Gasolina 95 E5": 1.529}
    assert prices_of(db, "5120") == {"Gasoleo A": 1.479}
    assert query(db, "PRAGMA user_version") == [(1,)]
    assert sorted(p.name for p in db.parent.iterdir()) == ["prices.db"]
