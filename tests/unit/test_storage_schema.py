"""Creación del esquema, versión de estructura y claves foráneas."""

import sqlite3

import pytest

from src.ingestion import storage
from src.ingestion.errors import StorageError
from tests.builders import response, station
from tests.helpers import db_dump
from tests.storage_helpers import ingest, query


def test_new_database_has_schema_and_version(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station(**{"Precio Gasoleo A": "1,459"})))
    tables = {row[0] for row in query(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"stations", "snapshots", "prices"} <= tables
    assert query(db, "PRAGMA user_version") == [(1,)]


def test_existing_database_is_not_recreated(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station(**{"Precio Gasoleo A": "1,459"})))
    ingest(db, response(station(**{"Precio Gasoleo A": "1,469"})))
    assert query(db, "SELECT COUNT(*) FROM snapshots") == [(2,)]
    assert query(db, "SELECT COUNT(*) FROM prices") == [(2,)]


def test_unknown_schema_version_is_not_touched(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station(**{"Precio Gasoleo A": "1,459"})))
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    before = db_dump(db)
    before_bytes = db.read_bytes()
    with pytest.raises(StorageError, match="versión de base de datos no compatible: 7"):
        ingest(db, response(station(**{"Precio Gasoleo A": "1,469"})))
    assert db_dump(db) == before
    assert db.read_bytes() == before_bytes


def test_foreign_keys_active_while_saving(tmp_path, monkeypatch):
    seen = []
    real_insert = storage._insert_prices

    def spy(conn, snapshot_id, prices):
        seen.append(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        real_insert(conn, snapshot_id, prices)

    monkeypatch.setattr(storage, "_insert_prices", spy)
    ingest(tmp_path / "prices.db", response(station(**{"Precio Gasoleo A": "1,459"})))
    assert seen == [1]
