"""Gestión de procesos de la ingesta: bloqueo y señal de parada.

Bloqueo para que no haya dos ingestas a la vez sobre la misma base.

Se bloquea la carpeta de la base con `flock`, no un archivo: no se crea
nada en la carpeta, no interfiere con los bloqueos propios de SQLite y vale
también en la primera ejecución, cuando `prices.db` aún no existe. El
sistema lo libera solo al cerrar el descriptor o al morir el proceso
(también con `kill -9`). Cubre procesos del mismo sistema operativo: dos
contenedores que comparten `./data`, o dos procesos en el Mac, pero no un
proceso del Mac junto a uno de un contenedor.
"""

import fcntl
import os
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import IngestionBusy, StorageError


RETRY_S = 1.0


@contextmanager
def data_dir_lock(folder: Path, wait_s: float = 0, *, deadline: float | None = None,
                  sleep=time.sleep, monotonic=time.monotonic) -> Iterator[None]:
    """Coge el bloqueo de `folder`; `IngestionBusy` si ya lo tiene otro.

    Sin `wait_s` ni `deadline` no espera (la ingesta). La copia de seguridad
    espera reintentando cada segundo hasta `wait_s` segundos, o hasta el
    instante `deadline` de `monotonic()`, que comparten sus dos bloqueos.
    """
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError as exc:
        raise StorageError(
            f"no se ha podido crear o escribir la base de datos en {folder}: {exc}"
        ) from exc
    if deadline is None:
        deadline = monotonic() + wait_s
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise IngestionBusy(
                        f"ya hay otra ingesta o copia en curso sobre {folder}"
                    ) from exc
                sleep(min(RETRY_S, remaining))
        yield
    finally:
        os.close(fd)


@contextmanager
def sigterm_as_interrupt() -> Iterator[None]:
    """Trata SIGTERM (`docker stop`, parada del programador) igual que Ctrl+C.

    Por defecto Python termina con SIGTERM sin ejecutar ningún `finally` ni
    `except`, y quedarían un diario pendiente o un temporal. Así llega como
    `KeyboardInterrupt`: el guardado hace ROLLBACK y borra su temporal. Al
    salir se restaura el manejador anterior.
    """

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
