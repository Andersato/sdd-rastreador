"""Programa de arranque de la imagen de la ingesta.

Antes de lanzar `python -m src.ingestion` comprueba que no se ejecuta como
root y que no se intenta cambiar la base de datos, que está fijada a la
carpeta montada. Después sustituye este proceso por el de la ingesta, de modo
que su código de salida, su ayuda y sus errores son exactamente los suyos.
"""

import os
import sys

APP_DIR = "/app"
DB_PATH = "/app/data/prices.db"
EXIT_REFUSED = 2


def refusal(uid: int, gid: int, args: list[str]) -> str | None:
    """Motivo para no lanzar la ingesta, o None si se puede lanzar."""
    if uid == 0:
        return "no se permite ejecutar la ingesta como root (usuario 0); revisa HOST_UID en .env"
    if gid == 0:
        return "no se permite ejecutar la ingesta con el grupo root (grupo 0); revisa HOST_GID en .env"
    if any(arg == "--db" or arg.startswith("--db=") for arg in args):
        return (
            "la base de datos no se puede cambiar en el contenedor: "
            f"siempre es {DB_PATH} (./data/prices.db del host)"
        )
    return None


def ingestion_command(args: list[str]) -> list[str]:
    return [sys.executable, "-m", "src.ingestion", "--db", DB_PATH, *args]


def main(uid: int, gid: int, args: list[str], execv=os.execv, chdir=os.chdir) -> int:
    reason = refusal(uid, gid, args)
    if reason is not None:
        print(f"Error: {reason}", file=sys.stderr)
        return EXIT_REFUSED
    chdir(APP_DIR)
    command = ingestion_command(args)
    execv(command[0], command)
    return 0  # solo se llega aquí si `execv` se sustituye en los tests


if __name__ == "__main__":
    sys.exit(main(os.getuid(), os.getgid(), sys.argv[1:]))
