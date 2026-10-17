"""Una comprobación del programador dentro del contenedor.

La lanza supercronic cada hora (y `scheduler.py` al arrancar). Antes de
capturar comprueba, en este orden: usuario root, grupo root, intervalo y
`COLLECTION_ENABLED` (valor no válido, y después desactivada). El primer
fallo deja una línea en el log y no se hace nada más (ni bloqueo, ni base,
ni petición), sin terminar el programador. Si no, lanza la comprobación de
`src.ingestion.scheduled` con la base fijada en la carpeta montada.

Después de la decisión de captura (haya capturado o no), y si la
configuración permite copiar (como `backup.py`, sin mirar el intervalo):
- con `--startup` (la de arranque), hace una copia si no hay ninguna o la
  más reciente tiene más de 26 h;
- si no, reintenta la copia de hoy si quedó pendiente (`/tmp/backup-pending`).
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from backup import BACKUPS_DIR, MARKER, backup_blocker
from entrypoint import DB_PATH, refusal
from settings import ENABLE_HINT, InvalidSetting, parse_enabled
from src.backup.scheduled import retry_pending, run_backup, startup_due
from src.ingestion.lock import sigterm_as_interrupt
from src.ingestion.scheduled import InvalidInterval, madrid_time, parse_interval
from src.ingestion.scheduled import main as scheduled_main

ACCEPT_COMMAND = "docker compose run --rm ingest --accept-short-response"


def check_args(env: dict[str, str]) -> list[str]:
    # Con `=`: un valor que empiece por `-` no se confunde con una opción.
    args = [f"--db={DB_PATH}", f"--accept-command={ACCEPT_COMMAND}"]
    if env.get("INGEST_API_URL"):
        args.append(f"--url={env['INGEST_API_URL']}")
    if "CAPTURE_INTERVAL_HOURS" in env:
        args.append(f"--interval={env['CAPTURE_INTERVAL_HOURS']}")
    return args


def capture_blocker(uid: int, gid: int, env: dict[str, str]) -> tuple[str, int] | None:
    """(línea, código) si no se puede capturar, o None. Orden de D8."""
    reason = refusal(uid, gid, [])
    if reason is None:
        try:
            parse_interval(env.get("CAPTURE_INTERVAL_HOURS"))
        except InvalidInterval as exc:
            reason = str(exc)
    if reason is None:
        try:
            enabled = parse_enabled(env.get("COLLECTION_ENABLED"))
        except InvalidSetting as exc:
            reason = str(exc)
        else:
            if not enabled:
                return f"recogida desactivada en esta máquina; {ENABLE_HINT}", 0
    if reason is not None:
        return f"configuración no válida: {reason}; no se hace ninguna petición", 1
    return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def backup_after_check(uid, gid, env, startup, clock, copy=run_backup, retry=retry_pending,
                       due=startup_due) -> int | None:
    """Copia de arranque o reintento de una pendiente; None si no toca ninguna."""
    if backup_blocker(uid, gid, env) is not None:
        return None  # la línea de la captura ya dice por qué
    db, backups, out = Path(DB_PATH), Path(BACKUPS_DIR), (lambda line: print(line, flush=True))
    try:
        with sigterm_as_interrupt():
            if startup:
                if due(backups, clock()):
                    return copy(db, backups, clock, out, marker=Path(MARKER))
                return None
            return retry(db, backups, clock, out, Path(MARKER))
    except KeyboardInterrupt:
        print(f"{madrid_time(clock())} · copia interrumpida", flush=True)
        return 130


def main(uid: int, gid: int, env: dict[str, str], run=scheduled_main, now=None,
         startup=False, after=backup_after_check) -> int:
    clock = (lambda: now) if now is not None else utc_now
    blocker = capture_blocker(uid, gid, env)
    if blocker is not None:
        line, code = blocker
        print(f"{madrid_time(clock())} · {line}", flush=True)
    else:
        code = run(check_args(env))
    after(uid, gid, env, startup, clock)
    return code


if __name__ == "__main__":
    startup = sys.argv[1:] == ["--startup"]
    sys.exit(main(os.getuid(), os.getgid(), dict(os.environ), startup=startup))
