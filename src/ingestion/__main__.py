"""CLI de la ingesta: python -m src.ingestion [--db RUTA] [--url URL]

Descarga una vez los precios de la API del Ministerio, los normaliza y los
guarda como una captura. Código de salida 0 si se guarda (aunque haya avisos),
1 si falla (en ese caso no se guarda nada).
"""

import argparse
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import storage
from .client import API_URL, DOWNLOAD_DEADLINE_S, fetch_prices, utc_now
from .errors import IngestionError
from .models import IngestionWarning
from .parser import parse_response


def main(
    argv: list[str] | None = None,
    now: Callable[[], datetime] = utc_now,
    deadline_s: float = DOWNLOAD_DEADLINE_S,
) -> int:
    args = _parse_args(argv)
    # Se lee en cada llamada (no al importar) para que los tests puedan cambiarla.
    db_path = Path(args.db) if args.db is not None else storage.DEFAULT_DB_PATH
    deadline = args.deadline if args.deadline is not None else deadline_s

    try:
        data, downloaded_at = fetch_prices(args.url, deadline_s=deadline, now=now)
        snapshot = parse_response(data)
        result = storage.save_snapshot(snapshot, db_path, downloaded_at)
    except IngestionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    processed = result.new_stations + result.updated_stations
    print(f"Captura guardada en {db_path}")
    print(
        f"Estaciones procesadas: {processed} "
        f"({_count(result.new_stations, 'nueva')}, "
        f"{_count(result.updated_stations, 'actualizada')})"
    )
    print(f"Precios guardados: {result.prices}")
    print(f"Avisos: {len(snapshot.warnings)}")
    for warning in snapshot.warnings:
        print(format_warning(warning))
    return 0


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def format_warning(warning: IngestionWarning) -> str:
    value = f'"{warning.value}"' if warning.value_is_text else warning.value
    where = f"estación {warning.station_id}, " if warning.station_id is not None else ""
    return f"Aviso: {where}{warning.field}: valor {value} no válido ({warning.reason})"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.ingestion",
        description="Descarga los precios de las gasolineras y los guarda como una captura.",
    )
    parser.add_argument("--url", default=API_URL, help="URL de la API (por defecto, la oficial)")
    parser.add_argument(
        "--db",
        default=None,
        help=f"archivo de la base de datos (por defecto, {storage.DEFAULT_DB_PATH})",
    )
    # Solo para los tests: reduce el plazo total de descarga en el subproceso.
    parser.add_argument("--deadline", type=float, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
