"""Cuándo y cómo se lanza una copia, y su línea de log (D6).

- `run_backup`: una copia (diaria, de arranque, reintento o a mano) con su
  línea de log y su código de salida.
- Marca de pendiente: un archivo con la fecha de Madrid fuera de `./data` y
  de `./backups` (en el programador, `/tmp/backup-pending`). La crean las
  copias del programador que se rinden por bloqueo o diario pendiente; la
  borra la copia correcta. La copia a mano no la usa.
- `startup_due`: regla de 26 h de la comprobación de arranque.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from src.ingestion.formatting import thousands
from src.ingestion.scheduled import madrid_time

from .make import (
    BUSY,
    AlreadyDone,
    BackupFailed,
    BackupPending,
    BackupResult,
    latest_backup,
    madrid_date,
    make_backup,
)
from .verify import NothingToCopy

EXIT_OK, EXIT_FAILED, EXIT_BUSY = 0, 1, 3
STARTUP_MAX_AGE = timedelta(hours=26)


def megabytes(size: int) -> str:
    """Tamaño en MB con un decimal y coma: 912_400_000 → "912,4 MB"."""
    tenths = round(size / 100_000)
    return f"{thousands(tenths // 10)},{tenths % 10} MB"


def saved_line(result: BackupResult) -> str:
    parts = [f"copia guardada: {result.name} ({megabytes(result.size)}, "
             f"{thousands(result.snapshots)} capturas, integridad correcta)"]
    if result.removed:
        parts.append("borradas: " + ", ".join(result.removed))
    if result.cleaned:
        parts.append("temporales borrados: " + ", ".join(result.cleaned))
    parts += [f"aviso: {warning}" for warning in result.warnings]
    return "; ".join(parts)


def run_backup(
    db_path: Path,
    backups_dir: Path,
    clock: Callable[[], datetime],
    out: Callable[[str], None],
    marker: Path | None = None,
    skip_if_newer_than: float | None = None,
    **kwargs,
) -> int:
    """Una copia con su línea de log. `marker` None = copia a mano (nunca pendiente)."""

    def log(text: str) -> None:
        out(f"{madrid_time(clock())} · {text}")

    try:
        result = make_backup(db_path, backups_dir, clock,
                             skip_if_newer_than=skip_if_newer_than, **kwargs)
    except AlreadyDone as exc:
        clear_marker(marker)
        log(f"copia pendiente ya hecha: {exc} es posterior; no se repite")
        return EXIT_OK
    except BackupPending as exc:
        if marker is None:  # a mano: nunca queda pendiente
            if str(exc) == BUSY:
                log(f"no se ha hecho la copia: ya hay {BUSY}")
                return EXIT_BUSY
            log(f"no se ha hecho la copia: {exc}")
            return EXIT_FAILED
        write_marker(marker, madrid_date(clock()))
        log(f"copia pendiente: {exc}; se reintenta en la próxima comprobación horaria")
        return EXIT_BUSY
    except NothingToCopy as exc:
        clear_marker(marker)  # otros fallos no se reintentan hasta el día siguiente
        log(f"copia no hecha: nada que copiar ({exc})")
        return EXIT_FAILED
    except BackupFailed as exc:
        clear_marker(marker)
        log(f"error en la copia: {exc}")
        return EXIT_FAILED
    clear_marker(marker)
    log(saved_line(result))
    return EXIT_OK


# --- Marca de pendiente --------------------------------------------------------

def write_marker(marker: Path, day: date) -> None:
    marker.write_text(day.isoformat())


def clear_marker(marker: Path | None) -> None:
    if marker is not None:
        marker.unlink(missing_ok=True)


def pending_since(marker: Path, today: date) -> float | None:
    """`mtime` de la marca si es de hoy; una de otro día se borra y no cuenta."""
    try:
        text = marker.read_text().strip()
        mtime = marker.stat().st_mtime
    except FileNotFoundError:
        return None
    if text != today.isoformat():
        marker.unlink(missing_ok=True)
        return None
    return mtime


def retry_pending(db_path, backups_dir, clock, out, marker: Path, **kwargs) -> int | None:
    """Reintento horario: None si no hay nada pendiente hoy."""
    since = pending_since(marker, madrid_date(clock()))
    if since is None:
        return None
    return run_backup(db_path, backups_dir, clock, out, marker=marker,
                      skip_if_newer_than=since, **kwargs)


# --- Copia de arranque ---------------------------------------------------------

def startup_due(backups_dir: Path, now: datetime) -> bool:
    """Sin copias, o la más reciente (por fecha del nombre) modificada hace más de 26 h."""
    latest = latest_backup(backups_dir, madrid_date(now))
    if latest is None:
        return True
    age = now.timestamp() - latest.stat().st_mtime
    return age > STARTUP_MAX_AGE.total_seconds()
