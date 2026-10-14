"""Una comprobación del programador dentro del contenedor.

La lanza supercronic cada hora (y `scheduler.py` al arrancar). Rechaza root
igual que el programa de arranque de la ingesta, pero sin terminar el
programador: solo escribe el motivo y no hace nada más (ni bloqueo, ni base,
ni petición). Si no, lanza la comprobación de `src.ingestion.scheduled` con
la base fijada en la carpeta montada.
"""

import os
import sys
from datetime import datetime, timezone

from entrypoint import DB_PATH, refusal
from src.ingestion.scheduled import madrid_time
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


def main(uid: int, gid: int, env: dict[str, str], run=scheduled_main, now=None) -> int:
    reason = refusal(uid, gid, [])
    if reason is not None:
        instant = now or datetime.now(timezone.utc)
        print(f"{madrid_time(instant)} · configuración no válida: {reason}; "
              "no se hace ninguna petición", flush=True)
        return 1
    return run(check_args(env))


if __name__ == "__main__":
    sys.exit(main(os.getuid(), os.getgid(), dict(os.environ)))
