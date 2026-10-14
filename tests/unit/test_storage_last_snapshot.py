"""Lectura de la última captura para la comprobación: nunca crea ni modifica nada (D3)."""

import sqlite3
from datetime import datetime, timezone

import pytest

from src.ingestion import storage
from src.ingestion.errors import InterruptedIngestion, StorageError
from tests.builders import response, station
from tests.helpers import db_dump
from tests.storage_helpers import ingest, make_pending_journal


def folder_state(folder):
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def test_missing_database_is_not_created(tmp_path):
    assert storage.read_last_snapshot(tmp_path / "prices.db") is None
    assert list(tmp_path.iterdir()) == []


def test_database_without_tables(tmp_path):
    db = tmp_path / "prices.db"
    sqlite3.connect(db).close()
    before = folder_state(tmp_path)
    assert storage.read_last_snapshot(db) is None
    assert folder_state(tmp_path) == before


def test_database_without_snapshots(tmp_path):
    db = tmp_path / "prices.db"
    conn = sqlite3.connect(db)
    for statement in storage.SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)
    conn.execute(f"PRAGMA user_version = {storage.SCHEMA_VERSION}")
    conn.commit()
    conn.close()
    assert storage.read_last_snapshot(db) is None


def test_last_snapshot_is_the_one_with_highest_id(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(*(station(str(i), **{"Precio Gasoleo A": "1,459"}) for i in (1, 2))),
           instant=datetime(2026, 10, 12, 8, 17, 40, tzinfo=timezone.utc))
    # La segunda tiene un instante anterior (reloj atrasado): cuenta la de mayor id.
    ingest(db, response(station("1", **{"Precio Gasoleo A": "1,459", "Precio Gasoleo B": "1,2"}),
                        station("2", **{"Precio Gasoleo A": "1,469"}),
                        station("3", **{"Precio Gasoleo A": ""})),
           instant=datetime(2026, 10, 12, 7, 0, 0, tzinfo=timezone.utc))
    before = folder_state(tmp_path)
    last = storage.read_last_snapshot(db)
    assert last == storage.LastSnapshot(datetime(2026, 10, 12, 7, 0, 0, tzinfo=timezone.utc), 2)
    assert folder_state(tmp_path) == before


def test_unknown_schema_version(tmp_path):
    db = tmp_path / "prices.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE snapshots (id INTEGER PRIMARY KEY)")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before = folder_state(tmp_path)
    with pytest.raises(StorageError, match="versión de base de datos no compatible: 7"):
        storage.read_last_snapshot(db)
    assert folder_state(tmp_path) == before


def test_file_that_is_not_a_database(tmp_path):
    db = tmp_path / "prices.db"
    db.write_text("hola")
    with pytest.raises(StorageError, match="no se ha podido leer la base de datos"):
        storage.read_last_snapshot(db)
    assert folder_state(tmp_path) == {"prices.db": b"hola"}


def test_pending_journal_is_reported_as_interrupted(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    make_pending_journal(db)
    before = folder_state(tmp_path)
    with pytest.raises(InterruptedIngestion, match="quedó a medias"):
        storage.read_last_snapshot(db)
    assert folder_state(tmp_path) == before


def test_empty_journal_is_not_pending(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    (tmp_path / "prices.db-journal").write_bytes(b"")
    before = folder_state(tmp_path)
    last = storage.read_last_snapshot(db)
    assert last is not None and last.stations == 1
    assert folder_state(tmp_path) == before


def test_path_with_special_characters(tmp_path):
    folder = tmp_path / "datos ?#%"
    folder.mkdir()
    db = folder / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert storage.read_last_snapshot(db).stations == 1
    assert db_dump(db) != "no existe"
