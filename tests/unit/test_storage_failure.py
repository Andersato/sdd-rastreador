"""Errores de escritura: la base queda exactamente igual o no se crea."""

import os
import sqlite3

import pytest

from src.ingestion import storage
from src.ingestion.errors import StorageError
from tests.builders import response, station
from tests.helpers import db_dump
from tests.storage_helpers import ingest


def test_write_error_on_existing_database(tmp_path):
    db = tmp_path / "prices.db"
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TRIGGER fail_prices BEFORE INSERT ON prices "
        "BEGIN SELECT RAISE(ABORT, 'fallo simulado'); END"
    )
    conn.commit()
    conn.close()
    before = db_dump(db)
    with pytest.raises(StorageError, match="fallo simulado"):
        ingest(db, response(station("4375", **{"Rótulo": "CEPSA", "Precio Gasoleo A": "1,469"}),
                            station("5120", **{"Precio Gasoleo A": "1,479"})))
    assert db_dump(db) == before


def test_write_error_on_first_run_leaves_no_file(tmp_path, monkeypatch):
    def failing_insert(conn, snapshot_id, prices):
        raise sqlite3.OperationalError("disco lleno (simulado)")

    monkeypatch.setattr(storage, "_insert_prices", failing_insert)
    db = tmp_path / "prices.db"
    with pytest.raises(StorageError, match="disco lleno"):
        ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert list(tmp_path.iterdir()) == []


def test_file_that_is_not_sqlite_is_left_intact(tmp_path):
    db = tmp_path / "notes.db"
    content = b"esto no es una base de datos SQLite, solo texto\n" * 10
    db.write_bytes(content)
    with pytest.raises(StorageError):
        ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert db.read_bytes() == content
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notes.db"]


def test_orphan_temporary_from_previous_run_is_not_reused(tmp_path):
    # Mismo nombre que generaba la versión anterior (con el PID): el caso real
    # de un temporal huérfano que coincide con el de esta ejecución.
    db = tmp_path / "prices.db"
    orphan = tmp_path / f"prices.db.tmp-{os.getpid()}"
    orphan.write_bytes(b"restos de una ejecucion cortada")
    ingest(db, response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert db_dump(db)["stations"][0][0] == "4375"
    assert orphan.read_bytes() == b"restos de una ejecucion cortada"


def test_temporary_name_collision_never_reuses_existing_file(tmp_path, monkeypatch):
    orphan = tmp_path / "prices.db.tmp-fixed"
    orphan.write_bytes(b"no tocar")
    monkeypatch.setattr(storage.secrets, "token_hex", lambda n: "fixed")
    with pytest.raises(StorageError):
        ingest(tmp_path / "prices.db", response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert orphan.read_bytes() == b"no tocar"
    assert not (tmp_path / "prices.db").exists()


def test_rename_failure_removes_temporary(tmp_path, monkeypatch):
    def failing_replace(src, dst):
        raise OSError("renombrado imposible (simulado)")

    monkeypatch.setattr(storage.os, "replace", failing_replace)
    with pytest.raises(StorageError, match="renombrado imposible"):
        ingest(tmp_path / "prices.db", response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert list(tmp_path.iterdir()) == []


def test_folder_cannot_be_created(tmp_path):
    blocker = tmp_path / "data"
    blocker.write_text("un archivo donde debería ir la carpeta")
    with pytest.raises(StorageError, match="no se ha podido crear la carpeta"):
        ingest(blocker / "prices.db", response(station("4375", **{"Precio Gasoleo A": "1,459"})))
    assert blocker.read_text() == "un archivo donde debería ir la carpeta"
