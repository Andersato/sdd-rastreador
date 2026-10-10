"""Utilidades para los tests de guardado: parsear una respuesta y guardarla."""

import sqlite3
from datetime import datetime, timezone

from src.ingestion.parser import parse_response
from src.ingestion.storage import save_snapshot

INSTANT = datetime(2026, 10, 10, 17, 5, 30, tzinfo=timezone.utc)


def ingest(db_path, data, instant=INSTANT):
    """Parsea `data` y la guarda; devuelve (SaveResult, ParsedSnapshot)."""
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
