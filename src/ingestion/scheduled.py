"""Comprobación programada: python -m src.ingestion.scheduled --db RUTA [--url URL]
[--interval HORAS] [--accept-command TEXTO]

Una comprobación decide si toca capturar y, solo si toca, lanza una única
ingesta. La decisión y la ingesta se hacen con el bloqueo de la carpeta ya
cogido, así que una ingesta manual no puede colarse entre las dos. Nunca
crea ni modifica nada en la carpeta de datos salvo a través de la ingesta.

Cada comprobación escribe en la salida estándar líneas que empiezan por la
fecha y hora de Madrid, con su resultado.
"""

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import storage
from .__main__ import exit_code, run_ingestion, summary_lines
from .client import API_URL, DOWNLOAD_DEADLINE_S, utc_now
from .errors import (
    IngestionBusy,
    IngestionError,
    InterruptedIngestion,
    ShortResponseError,
    short_response_figures,
)
from .lock import data_dir_lock, sigterm_as_interrupt

MADRID = ZoneInfo("Europe/Madrid")
DEFAULT_INTERVAL_H = 6
MIN_INTERVAL_H, MAX_INTERVAL_H = 1, 24
MARGIN = timedelta(minutes=15)
FUTURE_TOLERANCE = timedelta(hours=1)
DEFAULT_ACCEPT_COMMAND = "python -m src.ingestion --accept-short-response"


class InvalidInterval(ValueError):
    """Intervalo de `CAPTURE_INTERVAL_HOURS` no válido."""


class _Interrupted:
    """Centinela: la base tiene un diario pendiente de una ingesta cortada."""

    def __repr__(self):
        return "INTERRUPTED"


INTERRUPTED = _Interrupted()


@dataclass(frozen=True)
class Decision:
    due: bool
    reason: str  # línea de resultado si no toca; motivo si toca
    notice: str | None = None  # línea adicional antes del resultado (D7)


def parse_interval(text: str | None) -> int:
    """Horas enteras de 1 a 24; ausente o vacío → 6. Se ignoran los espacios."""
    if text is None or not text.strip():
        return DEFAULT_INTERVAL_H
    value = text.strip()
    if re.fullmatch(r"[0-9]+", value) and MIN_INTERVAL_H <= int(value) <= MAX_INTERVAL_H:
        return int(value)
    raise InvalidInterval(
        f"CAPTURE_INTERVAL_HOURS no válido: {text!r}; se admiten horas enteras "
        f"de {MIN_INTERVAL_H} a {MAX_INTERVAL_H}"
    )


def is_due(last, now: datetime, interval_h: int) -> Decision:
    """¿Toca capturar? `last` es un `LastSnapshot`, None (sin capturas) o INTERRUPTED."""
    interval = timedelta(hours=interval_h)
    if last is INTERRUPTED:
        return Decision(True, "la última ingesta quedó a medias",
                        notice="la última ingesta quedó a medias; se lanza una nueva")
    if last is None:
        return Decision(True, "no hay capturas")
    last_at = last.downloaded_at
    instant = storage.format_instant(last_at)
    if last_at - now > FUTURE_TOLERANCE:
        return Decision(
            True,
            "la última captura tiene una fecha anómala",
            notice=f"aviso: la última captura tiene una fecha anómala ({instant}), más de 1 h "
                   "posterior a la actual; se captura igualmente",
        )
    if last_at > now:
        return Decision(False, f"no toca capturar: la última captura tiene una fecha "
                               f"posterior a la actual ({instant})")
    age = now - last_at
    if age >= interval - MARGIN:
        return Decision(True, f"última captura hace {format_age(age)}, intervalo {interval_h} h")
    return Decision(False, f"no toca capturar: última captura hace {format_age(age)} "
                           f"(intervalo {interval_h} h)")


def format_age(age: timedelta) -> str:
    minutes = int(age.total_seconds()) // 60
    return f"{minutes // 60} h {minutes % 60} min"


def madrid_time(instant: datetime) -> str:
    return instant.astimezone(MADRID).strftime("%Y-%m-%d %H:%M:%S %Z")


def run_check(
    db_path: Path,
    url: str,
    interval_text: str | None,
    clock: Callable[[], datetime],
    out: Callable[[str], None],
    accept_command: str = DEFAULT_ACCEPT_COMMAND,
    deadline_s: float = DOWNLOAD_DEADLINE_S,
) -> int:
    """Una comprobación completa. Devuelve 0 si no hay nada que corregir y 1 si hay un error."""

    def log(text: str) -> None:
        out(f"{madrid_time(clock())} · {text}")

    try:
        interval_h = parse_interval(interval_text)
    except InvalidInterval as exc:
        log(f"configuración no válida: {exc}; no se hace ninguna petición")
        return 1
    folder = db_path.parent
    if not folder.is_dir():
        log(f"error: no existe la carpeta de datos {folder}; no se hace ninguna petición")
        return 1
    try:
        with data_dir_lock(folder):
            try:
                last = storage.read_last_snapshot(db_path)
            except InterruptedIngestion:
                last = INTERRUPTED
            decision = is_due(last, clock(), interval_h)
            if not decision.due:
                log(decision.reason)
                return 0
            if decision.notice:
                log(decision.notice)
            result = run_ingestion(db_path, url, deadline_s, clock)
    except KeyboardInterrupt:
        log("ingesta interrumpida")
        return 1
    except IngestionBusy:
        log("otra ingesta en curso; no se captura")
        return 0
    except ShortResponseError as exc:
        log(
            "respuesta corta, no se ha guardado: "
            f"{short_response_figures(exc.stations, exc.reference)}. "
            f"Si es correcta, guárdala con: {accept_command}"
        )
        return exit_code(exc)
    except storage.StorageError as exc:
        log(f"error en la base de datos: {exc}; no se captura")
        return 1
    except IngestionError as exc:
        log(f"error: {exc}")
        return 1
    lines = summary_lines(result)
    log(f"captura guardada ({decision.reason})")
    for line in lines[1:]:  # la primera repite la ruta de la base
        log(line)
    return 0


def main(argv: list[str] | None = None, clock: Callable[[], datetime] = utc_now) -> int:
    args = _parse_args(argv)
    if args.now is not None:
        fixed = datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        clock = lambda: fixed  # noqa: E731
    deadline = args.deadline if args.deadline is not None else DOWNLOAD_DEADLINE_S
    with sigterm_as_interrupt():
        return run_check(
            Path(args.db),
            args.url,
            args.interval,
            clock,
            lambda line: print(line, flush=True),
            accept_command=args.accept_command,
            deadline_s=deadline,
        )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.ingestion.scheduled",
        description="Comprueba si toca capturar y, si toca, lanza una ingesta.",
    )
    parser.add_argument("--db", required=True, help="archivo de la base de datos")
    parser.add_argument("--url", default=API_URL, help="URL de la API (por defecto, la oficial)")
    parser.add_argument("--interval", default=None,
                        help=f"horas entre capturas, de 1 a 24 (por defecto, {DEFAULT_INTERVAL_H})")
    parser.add_argument("--accept-command", default=DEFAULT_ACCEPT_COMMAND,
                        help="comando que se sugiere para aceptar una respuesta corta")
    # Solo para los tests: reloj fijo (instante ISO en UTC) y plazo de descarga.
    parser.add_argument("--now", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--deadline", type=float, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
