"""CLI de la ingesta: python -m src.ingestion [--db RUTA] [--url URL]
[--accept-short-response]

Descarga una vez los precios de la API del Ministerio, los normaliza y los
guarda como una captura. Código de salida 0 si se guarda (aunque haya avisos),
3 si ya hay otra ingesta o copia en curso sobre la misma carpeta, 4 si la respuesta
es sospechosamente corta y 1 si falla por otro motivo (en todos esos casos no
se guarda nada). Con Ctrl+C o SIGTERM se interrumpe sin dejar nada a medias
(código 130).
"""

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import storage
from .client import API_URL, DOWNLOAD_DEADLINE_S, fetch_prices, utc_now
from .errors import IngestionBusy, IngestionError, ShortResponseError, StorageError, short_response_figures
from .lock import data_dir_lock, sigterm_as_interrupt
from .models import IngestionWarning
from .parser import parse_response

EXIT_ERROR = 1
EXIT_BUSY = 3
EXIT_SHORT_RESPONSE = 4
EXIT_INTERRUPTED = 130  # el mismo que daba Ctrl+C sin capturar


@dataclass(frozen=True)
class IngestionResult:
    db_path: Path
    saved: storage.SaveResult
    warnings: list[IngestionWarning]
    notices: list[str]  # avisos que no son de un dato (respuesta corta aceptada)


def main(
    argv: list[str] | None = None,
    now: Callable[[], datetime] = utc_now,
    deadline_s: float = DOWNLOAD_DEADLINE_S,
) -> int:
    args = _parse_args(argv)
    # Se lee en cada llamada (no al importar) para que los tests puedan cambiarla.
    db_path = Path(args.db) if args.db is not None else storage.DEFAULT_DB_PATH
    deadline = args.deadline if args.deadline is not None else deadline_s

    created = []
    try:
        with sigterm_as_interrupt():
            created = prepare_folder(db_path)
            with data_dir_lock(db_path.parent):
                result = run_ingestion(db_path, args.url, deadline, now, args.accept_short_response)
    except KeyboardInterrupt:
        remove_empty_folders(created)
        print("Error: ingesta interrumpida", file=sys.stderr)
        return EXIT_INTERRUPTED
    except IngestionError as exc:
        # Como antes del bloqueo: la carpeta solo la creaba el guardado. Si se
        # falla antes de guardar, no queda; si falla el guardado, sí.
        if not isinstance(exc, StorageError):
            remove_empty_folders(created)
        print(f"Error: {exc}", file=sys.stderr)
        return exit_code(exc)

    for line in summary_lines(result):
        print(line)
    return 0


def prepare_folder(db_path: Path) -> list[Path]:
    """Crea la carpeta de la base si no existe (hace falta para bloquearla).

    Devuelve las carpetas creadas, de la más profunda a la más alta, para
    poder quitarlas si la ingesta falla: una ingesta fallida no deja nada.
    """
    missing = [folder for folder in [db_path.parent, *db_path.parent.parents] if not folder.exists()]
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        remove_empty_folders(missing)
        raise StorageError(f"no se ha podido crear la carpeta {db_path.parent}: {exc}") from exc
    return missing


def remove_empty_folders(folders: list[Path]) -> None:
    for folder in folders:
        try:
            folder.rmdir()  # solo si sigue vacía
        except OSError:
            return


def run_ingestion(
    db_path: Path,
    url: str,
    deadline_s: float,
    now: Callable[[], datetime],
    accept_short: bool = False,
) -> IngestionResult:
    """Descarga, parsea y guarda una captura.

    No coge el bloqueo de la carpeta: el llamante MUST tenerlo cogido
    (`data_dir_lock`) durante toda la llamada.
    """
    data, downloaded_at = fetch_prices(url, deadline_s=deadline_s, now=now)
    snapshot = parse_response(data)
    saved = storage.save_snapshot(snapshot, db_path, downloaded_at, accept_short)
    notices = []
    if saved.short_response is not None:
        short = saved.short_response
        notices.append(
            "respuesta corta aceptada con --accept-short-response: "
            + short_response_figures(short.stations, short.reference)
        )
    return IngestionResult(db_path, saved, snapshot.warnings, notices)


def exit_code(exc: IngestionError) -> int:
    if isinstance(exc, IngestionBusy):
        return EXIT_BUSY
    if isinstance(exc, ShortResponseError):
        return EXIT_SHORT_RESPONSE
    return EXIT_ERROR


def summary_lines(result: IngestionResult) -> list[str]:
    saved = result.saved
    processed = saved.new_stations + saved.updated_stations
    lines = [
        f"Captura guardada en {result.db_path}",
        f"Estaciones procesadas: {processed} "
        f"({_count(saved.new_stations, 'nueva')}, "
        f"{_count(saved.updated_stations, 'actualizada')})",
        f"Precios guardados: {saved.prices}",
        f"Avisos: {len(result.warnings) + len(result.notices)}",
    ]
    lines += [format_warning(warning) for warning in result.warnings]
    lines += [f"Aviso: {notice}" for notice in result.notices]
    return lines


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
    parser.add_argument(
        "--accept-short-response",
        action="store_true",
        help="guarda la captura aunque traiga menos del 80 %% de las estaciones de la última",
    )
    # Solo para los tests: reduce el plazo total de descarga en el subproceso.
    parser.add_argument("--deadline", type=float, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
