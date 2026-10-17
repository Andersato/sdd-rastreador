"""Copia de seguridad dentro del contenedor: `backup.py --daily` o `--manual`.

- `--daily`: la lanza supercronic a las 04:43. Si se rinde por una ingesta u
  otra copia en curso, o por una ingesta a medias, deja la marca de
  pendiente (`/tmp/backup-pending`) para los reintentos horarios.
- `--manual`: `docker compose run --rm backup`. Nunca queda pendiente.

Antes comprueba, en este orden: usuario root, grupo root, valor de
`COLLECTION_ENABLED` y desactivada (el intervalo no cuenta: solo afecta a la
captura). Códigos de salida: 0 copia correcta, 1 error, 2 configuración no
válida o (con `--manual`) copias desactivadas, 3 otra ingesta o copia en
curso, 130 interrumpida. Con `--daily` y las copias desactivadas termina con
0: no es un error (supercronic registraría uno cada día en el Mac).
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from entrypoint import DB_PATH, refusal
from settings import InvalidSetting, parse_enabled
from src.backup.scheduled import run_backup
from src.ingestion.lock import sigterm_as_interrupt
from src.ingestion.scheduled import madrid_time

BACKUPS_DIR = "/app/backups"
MARKER = "/tmp/backup-pending"
EXIT_REFUSED = 2
EXIT_INTERRUPTED = 130
DISABLED = "copias desactivadas en esta máquina; se activan con COLLECTION_ENABLED=true en .env"


def backup_blocker(uid: int, gid: int, env: dict[str, str]) -> str | None:
    """Línea de log si no se puede copiar, o None. Orden de D8, sin el intervalo."""
    reason = refusal(uid, gid, [])
    if reason is None:
        try:
            if not parse_enabled(env.get("COLLECTION_ENABLED")):
                return DISABLED
        except InvalidSetting as exc:
            reason = str(exc)
    if reason is not None:
        return f"configuración no válida: {reason}; no se hace la copia"
    return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def main(uid: int, gid: int, env: dict[str, str], argv: list[str], run=run_backup,
         clock=utc_now) -> int:
    args = _parse_args(argv)
    blocker = backup_blocker(uid, gid, env)
    if blocker is not None:
        print(f"{madrid_time(clock())} · {blocker}", flush=True)
        return 0 if args.daily and blocker == DISABLED else EXIT_REFUSED
    marker = Path(MARKER) if args.daily else None
    try:
        with sigterm_as_interrupt():
            extra = {} if args.wait is None else {"wait_s": args.wait}
            return run(Path(DB_PATH), Path(BACKUPS_DIR), clock,
                       lambda line: print(line, flush=True), marker=marker, **extra)
    except KeyboardInterrupt:
        print(f"{madrid_time(clock())} · copia interrumpida", flush=True)
        return EXIT_INTERRUPTED


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="backup.py",
                                     description="Copia de seguridad de ./data/prices.db.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--daily", action="store_true", help="copia diaria (supercronic)")
    mode.add_argument("--manual", action="store_true", help="copia a mano")
    parser.add_argument("--wait", type=float, default=None,
                        help="segundos de espera por otra ingesta o copia (solo para pruebas; "
                             "por defecto, 600)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main(os.getuid(), os.getgid(), dict(os.environ), sys.argv[1:]))
