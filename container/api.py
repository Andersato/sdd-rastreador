"""Programa de arranque del servicio `api` (design.md, D1 y D11).

Comprueba que no se ejecuta como root antes de cargar FastAPI o uvicorn: con
usuario o grupo 0 no se llega a escuchar ni a abrir la base. Docker la
reintenta con esperas cada vez más largas (a diferencia del programador, no
se queda en marcha: nunca hay un servidor web ejecutándose como root).

Uvicorn escucha en 0.0.0.0 dentro del contenedor para que Docker pueda
reenviar el puerto; `docker-compose.yml` solo lo publica en 127.0.0.1 del host.
"""

import os
import sys

DB_PATH = "/app/data/prices.db"
HOST = "0.0.0.0"
PORT = 8000
EXIT_REFUSED = 2


def refusal(uid: int, gid: int) -> str | None:
    """Motivo para no lanzar la API, o None si se puede lanzar."""
    if uid == 0:
        return "no se permite ejecutar la API como root (usuario 0); revisa HOST_UID en .env"
    if gid == 0:
        return "no se permite ejecutar la API con el grupo root (grupo 0); revisa HOST_GID en .env"
    return None


def serve(env) -> None:
    from pathlib import Path

    import uvicorn

    from src.api.app import create_app

    app = create_app(Path(DB_PATH), interval_text=env.get("CAPTURE_INTERVAL_HOURS"))
    print(f"API en marcha: puerto {PORT} del contenedor; base {DB_PATH} en solo lectura",
          flush=True)
    uvicorn.run(app, host=HOST, port=PORT, access_log=False, timeout_graceful_shutdown=5)


def main(uid: int, gid: int, env, serve=serve) -> int:
    reason = refusal(uid, gid)
    if reason is not None:
        print(f"Error: {reason}", file=sys.stderr, flush=True)
        return EXIT_REFUSED
    serve(env)
    return 0


if __name__ == "__main__":
    sys.exit(main(os.getuid(), os.getgid(), os.environ))
