"""Consultas SQL de cada ruta, sobre la última captura de un `Reader` abierto.

Solo leen: la transformación (limpieza, distancias, orden, redondeos) se hace
en `app.py` después de cerrar la transacción.
"""

from .db import Reader

STATION_COLUMNS = "s.id, s.brand, s.address, s.municipality, s.province, s.schedule, " \
                  "s.latitude, s.longitude"


def fuel_counts(reader: Reader) -> dict[str, int]:
    """Estaciones que venden cada combustible en la última captura."""
    rows = reader.all("SELECT fuel, COUNT(*) FROM prices WHERE snapshot_id = ? GROUP BY fuel",
                      (reader.capture.id,))
    return dict(rows)


def fuel_prices(reader: Reader, fuel_name: str) -> list[tuple]:
    """(datos de la estación…, precio) de quien vende `fuel_name` en la última captura."""
    return reader.all(
        f"SELECT {STATION_COLUMNS}, p.price FROM prices p "
        "JOIN stations s ON s.id = p.station_id "
        "WHERE p.snapshot_id = ? AND p.fuel = ?",
        (reader.capture.id, fuel_name),
    )


def station(reader: Reader, station_id: str) -> tuple | None:
    rows = reader.all(f"SELECT {STATION_COLUMNS} FROM stations s WHERE s.id = ?", (station_id,))
    return rows[0] if rows else None


def station_prices(reader: Reader, station_id: str) -> list[tuple]:
    return reader.all("SELECT fuel, price FROM prices WHERE snapshot_id = ? AND station_id = ?",
                      (reader.capture.id, station_id))
