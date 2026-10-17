"""Una línea de log por petición, sin ubicaciones exactas (design.md, D10).

`lat` y `lon` se escriben redondeados a 2 decimales (o `(no válido)`), para no
guardar dónde está quien busca. El log de acceso de uvicorn va desactivado:
escribiría la consulta original.
"""

import math
import time
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import FastAPI, Request

from src.ingestion.scheduled import madrid_time

COORDINATES = ("lat", "lon")
MAX_VALUE_CHARS = 40


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
    for key, value in items:
        shown = coordinate_text(value) if key in COORDINATES else value[:MAX_VALUE_CHARS]
        parts.append(f"{key[:MAX_VALUE_CHARS]}={shown}")
    return " ".join(parts)


def access_line(now: datetime, method: str, path: str, items, status: int,
                elapsed_s: float) -> str:
    params = parameters_text(items)
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
