"""Utilidades para los tests de guardado: parsear una respuesta y guardarla."""

import sqlite3
from datetime import datetime, timezone

from src.ingestion.parser import parse_response
from src.ingestion.storage import save_snapshot
from tests.helpers import check_not_real_data

INSTANT = datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc)


def ingest(db_path, data, instant=INSTANT):
    """Parsea `data` y la guarda; devuelve (SaveResult, ParsedSnapshot)."""
    check_not_real_data(db_path)
    parsed = parse_response(data)
    return save_snapshot(parsed, db_path, instant), parsed


def query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def station_row(db_path, station_id):
    rows = query(
        db_path,
        "SELECT id, brand, address, municipality, province, schedule, latitude, longitude "
        "FROM stations WHERE id = ?",
        (station_id,),
    )
    return rows[0] if rows else None


def prices_of(db_path, station_id, snapshot_id=None):
    sql = "SELECT fuel, price FROM prices WHERE station_id = ?"
    params = [station_id]
    if snapshot_id is not None:
        sql += " AND snapshot_id = ?"
        params.append(snapshot_id)
    return dict(query(db_path, sql, params))


# Proceso que abre una transacción de escritura, modifica muchas páginas (con
# una caché mínima, para que SQLite tenga que escribir ya en el archivo y en
# el diario) y se queda esperando sin confirmar.
_HALF_WRITE = """
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("PRAGMA cache_size = 1")
conn.execute("BEGIN IMMEDIATE")
conn.execute("CREATE TABLE IF NOT EXISTS _filler (x BLOB)")
conn.executemany("INSERT INTO _filler VALUES (?)", [(b"x" * 4000,) for _ in range(500)])
conn.execute("DELETE FROM prices")
print("ready", flush=True)
time.sleep(60)
"""


def make_pending_journal(db_path):
    """Deja en `db_path` un diario pendiente, como una ingesta matada a mitad del guardado.

    La base debe existir. Mata con SIGKILL un proceso que está en mitad de una
    transacción: quedan `prices.db-journal` y páginas sin confirmar que la
    siguiente conexión en escritura deshará.
    """
    check_not_real_data(db_path)
    import os
    import signal
    import subprocess
    import sys
    from pathlib import Path

    proc = subprocess.Popen([sys.executable, "-c", _HALF_WRITE, str(db_path)],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
    finally:
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
    journal = Path(f"{db_path}-journal")
    assert journal.exists() and journal.stat().st_size > 0
