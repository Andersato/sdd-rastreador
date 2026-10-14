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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import IngestionBusy, StorageError


@contextmanager
def data_dir_lock(folder: Path) -> Iterator[None]:
    """Coge el bloqueo de `folder` sin esperar; `IngestionBusy` si ya lo tiene otro."""
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError as exc:
        raise StorageError(
            f"no se ha podido crear o escribir la base de datos en {folder}: {exc}"
        ) from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise IngestionBusy(f"ya hay otra ingesta en curso sobre {folder}") from exc
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
