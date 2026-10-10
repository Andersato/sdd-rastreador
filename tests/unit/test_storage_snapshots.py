"""Requisito "Captura con fecha y hora" a nivel de guardado."""

from datetime import datetime, timedelta, timezone

from tests.builders import response, station
from tests.storage_helpers import ingest, prices_of, query

MADRID_SUMMER = timezone(timedelta(hours=2))


def test_snapshot_record(tmp_path):
    db = tmp_path / "p.db"
    instant = datetime(2026, 10, 10, 19, 5, 30, tzinfo=MADRID_SUMMER)
    result, _ = ingest(
        db,
        response(
            station("4375", **{"Precio Gasoleo A": "1,459"}),
            station("5120", **{"Precio Gasoleo A": "1,479"}),
            fecha="10/10/2026 19:05:23",
        ),
        instant=instant,
    )
    assert query(db, "SELECT id, downloaded_at, source_date FROM snapshots") == [
        (result.snapshot_id, "2026-10-10T17:05:30Z", "2026-10-10T19:05:23")
    ]
    assert query(db, "SELECT DISTINCT snapshot_id FROM prices") == [(result.snapshot_id,)]


def test_two_runs_with_same_fecha(tmp_path):
    db = tmp_path / "p.db"
    fecha = "10/10/2026 07:50:12"
    ingest(db, response(station(**{"Precio Gasoleo A": "1,459"}), fecha=fecha),
           instant=datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc))
    ingest(db, response(station(**{"Precio Gasoleo A": "1,469"}), fecha=fecha),
           instant=datetime(2026, 10, 10, 6, 5, tzinfo=timezone.utc))
    assert query(db, "SELECT id, source_date FROM snapshots ORDER BY id") == [
        (1, "2026-10-10T07:50:12"),
        (2, "2026-10-10T07:50:12"),
    ]
    assert prices_of(db, "4375", snapshot_id=1) == {"Gasoleo A": 1.459}
    assert prices_of(db, "4375", snapshot_id=2) == {"Gasoleo A": 1.469}


def test_missing_or_invalid_fecha_saves_without_source_date(tmp_path):
    db = tmp_path / "p.db"
    ingest(db, response(station(**{"Precio Gasoleo A": "1,459"}), drop=["Fecha"]))
    ingest(db, response(station(**{"Precio Gasoleo A": "1,469"}), fecha="2026-10-10 19:05"))
    assert query(db, "SELECT source_date FROM snapshots ORDER BY id") == [(None,), (None,)]
    assert query(db, "SELECT COUNT(*) FROM prices") == [(2,)]
