"""Verificación de bases y copias (`src/backup/verify.py`, D4)."""

import gzip
import shutil
import sqlite3

import pytest

from src.backup.verify import NothingToCopy, VerificationError, gzip_digest, inspect_db, sha256_of, verify_gz
from tests.builders import response, station
from tests.storage_helpers import ingest


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "prices.db"
    ingest(path, response(station("S1", **{"Precio Gasoleo A": "1,459"})))
    return path


def compress(src, dst):
    with open(src, "rb") as f, gzip.open(dst, "wb") as g:
        shutil.copyfileobj(f, g)
    return dst


def test_healthy_copy(db, tmp_path):
    gz = compress(db, tmp_path / "prices-2026-10-17.db.gz")
    assert verify_gz(gz, tmp_path).snapshots == 1
    assert gzip_digest(gz) == sha256_of(db)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["prices-2026-10-17.db.gz", "prices.db"]


def test_truncated_gzip(db, tmp_path):
    gz = compress(db, tmp_path / "prices-2026-10-17.db.gz")
    data = gz.read_bytes()
    gz.write_bytes(data[: len(data) // 2])
    with pytest.raises(VerificationError, match="no se descomprime bien"):
        verify_gz(gz, tmp_path)
    with pytest.raises(VerificationError):
        gzip_digest(gz)


def test_text_instead_of_gzip(tmp_path):
    gz = tmp_path / "prices-2026-10-17.db.gz"
    gz.write_text("hola")
    with pytest.raises(VerificationError):
        verify_gz(gz, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["prices-2026-10-17.db.gz"]


def test_text_instead_of_database(tmp_path):
    path = tmp_path / "prices.db"
    path.write_text("hola")
    with pytest.raises(VerificationError, match="no se ha podido leer la base"):
        inspect_db(path)


def test_database_without_snapshots(tmp_path):
    path = tmp_path / "prices.db"
    sqlite3.connect(path).close()
    with pytest.raises(NothingToCopy):
        inspect_db(path)
    gz = compress(path, tmp_path / "prices-2026-10-17.db.gz")
    with pytest.raises(VerificationError, match="tabla de capturas"):
        verify_gz(gz, tmp_path)


def test_corrupted_database_fails_integrity(db, tmp_path):
    """Base dañada: se estropean todas las páginas salvo la primera (cabecera y
    esquema), así que falla `integrity_check` o la lectura ("malformed")."""
    page = sqlite3.connect(db).execute("PRAGMA page_size").fetchone()[0]
    data = bytearray(db.read_bytes())
    assert len(data) > page
    data[page:] = b"\xff" * (len(data) - page)
    db.write_bytes(bytes(data))
    with pytest.raises(VerificationError):
        inspect_db(db)


def test_unknown_version_is_reported_not_rejected(db):
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 7")
    conn.close()
    info = inspect_db(db)
    assert (info.version, info.snapshots) == (7, 1)


def test_integrity_check_can_be_interrupted(db, monkeypatch):
    """Revisión: SIGTERM durante `integrity_check` (llega como KeyboardInterrupt en
    la función de progreso) interrumpe la verificación en vez de esperar."""
    import src.backup.verify as verify

    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(verify, "_progress", interrupted)
    monkeypatch.setattr(verify, "PROGRESS_STEPS", 1)
    with pytest.raises(KeyboardInterrupt):
        inspect_db(db)
