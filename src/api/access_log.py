"""Una línea de log por petición, sin ubicaciones exactas (design.md, D10).

`lat` y `lon` se escriben redondeados a 2 decimales (o `(no válido)`), para no
guardar dónde está quien busca. Solo se escriben los parámetros que existen
en alguna ruta; el resto se resume como `(otros: N)`, sin nombre ni valor
(podría ser una ubicación con otro nombre). Los caracteres de control se
escriben escapados (`\\n`), para que nadie pueda fabricar líneas falsas. El
log de acceso de uvicorn va desactivado: escribiría la consulta original.
"""

import math
import time
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI, Request

from src.ingestion.scheduled import madrid_time

COORDINATES = ("lat", "lon")
KNOWN_PARAMETERS = ("lat", "lon", "fuel", "radius_km", "limit")
MAX_VALUE_CHARS = 40


def printable(text: str) -> str:
    """Caracteres de control escapados: `\\n`, `\\t`, `\\x00`…"""
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in text)


def coordinate_text(value: str) -> str:
    try:
        number = float(value)
    except ValueError:
        return "(no válido)"
    if not math.isfinite(number):
        return "(no válido)"
    return f"{number:.2f}"


def parameters_text(items) -> str:
    parts = []
    others = 0
    for key, value in items:
        if key not in KNOWN_PARAMETERS:
            others += 1
            continue
        shown = coordinate_text(value) if key in COORDINATES else printable(value[:MAX_VALUE_CHARS])
        parts.append(f"{key}={shown}")
    if others:
        parts.append(f"(otros: {others})")
    return " ".join(parts)


def access_line(now: datetime, method: str, path: str, items, status: int,
                elapsed_s: float) -> str:
    params = parameters_text(items)
    path = printable(path)
    target = f"{path} {params}" if params else path
    return f"{madrid_time(now)} · {method} {target} → {status} ({elapsed_s * 1000:.0f} ms)"


def add_access_log(app: FastAPI, write: Callable[[str], None],
                   clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
    @app.middleware("http")
    async def access_log(request: Request, call_next):
        start = time.monotonic()

        def emit(status):
            write(access_line(clock(), request.method, request.url.path,
                              request.query_params.multi_items(), status,
                              time.monotonic() - start))

        try:
            response = await call_next(request)
        except Exception:
            # El manejador de Exception está por fuera de este middleware: se
            # apunta el 500 y se deja seguir para que responda y escriba la traza.
            emit(500)
            raise
        emit(response.status_code)
        return response
