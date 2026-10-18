"""Aplicación FastAPI de la API de precios (`prices-api`, design.md D1 y D4).

Toda respuesta lleva la atribución obligatoria al Ministerio. Las de datos
dicen además de qué captura salen. Los errores, también los que genera
FastAPI, tienen el formato común `{"attribution", "error": {code, message}}`.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import geo, queries, web
from .access_log import add_access_log
from .catalog import BY_NAME, BY_SLUG, CATALOG, Fuel
from .db import Capture, read_snapshot
from .errors import ApiError, unknown_fuel
from .formatting import average, clean_text, round_half_up, source_date_text, utc_text
from .health import ERROR, health_state

ATTRIBUTION = ("Ministerio de Industria, Comercio y Turismo - Precios de carburantes "
               "en estaciones de servicio")
DEFAULT_WEB_DIR = Path(__file__).resolve().parents[2] / "web"
DEFAULT_RADIUS_KM = 5
MAX_RADIUS_KM = 50
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

# Mensaje fijo por parámetro: nunca incluye el valor recibido (puede ser una
# ubicación exacta).
PARAMETER_MESSAGES = {
    "lat": "lat debe ser un número con punto decimal entre -90 y 90",
    "lon": "lon debe ser un número con punto decimal entre -180 y 180",
    "radius_km": f"radius_km debe ser un número mayor que 0; el radio máximo es {MAX_RADIUS_KM} km",
    "limit": f"limit no válido: el límite es un entero de 1 a {MAX_LIMIT}",
    "fuel": "falta fuel: indica el identificador de un combustible de /api/fuels",
}

log = logging.getLogger("src.api")


def error_response(error: ApiError, **extra) -> JSONResponse:
    content = {"attribution": ATTRIBUTION, **extra,
               "error": {"code": error.code, "message": error.message}}
    return JSONResponse(content, status_code=error.status, headers=error.headers)


def capture_dict(capture: Capture) -> dict:
    return {"downloaded_at": utc_text(capture.downloaded_at),
            "source_date": source_date_text(capture.source_date, capture.downloaded_at)}


def success(capture: Capture, data, **extra) -> dict:
    return {"attribution": ATTRIBUTION, **extra, "capture": capture_dict(capture), "data": data}


def find_fuel(slug: str) -> Fuel:
    fuel = BY_SLUG.get(slug)
    if fuel is None:
        raise unknown_fuel(slug)
    return fuel


def coordinates(latitude, longitude) -> tuple[float | None, float | None]:
    """Coordenadas de una estación, o (None, None) si no caen en España."""
    if geo.in_spain(latitude, longitude):
        return latitude, longitude
    return None, None


def station_fields(row) -> dict:
    station_id, brand, address, municipality, province, schedule, latitude, longitude = row
    latitude, longitude = coordinates(latitude, longitude)
    return {"id": station_id, "brand": clean_text(brand), "address": clean_text(address),
            "municipality": clean_text(municipality), "province": clean_text(province),
            "schedule": clean_text(schedule), "latitude": latitude, "longitude": longitude}


def create_app(db_path: Path, *, interval_text: str | None = None,
               clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
               read_options: dict | None = None,
               log_line: Callable[[str], None] | None = None,
               web_dir: Path | None = DEFAULT_WEB_DIR) -> FastAPI:
    """Aplicación sobre `db_path`. `log_line` recibe la línea de cada petición
    (por defecto, a la salida estándar); `read_options` solo lo usan los tests.
    `web_dir` es la carpeta de la página web que se sirve en `/` (map-view);
    con `None`, o si no existe, no se sirve nada fuera de `/api/`."""
    read_options = read_options or {}
    app = FastAPI(
        title="Precios de Gasolineras",
        version="1",
        description=("API de solo lectura sobre el histórico de precios de las gasolineras "
                     f"de España. Fuente de los datos: {ATTRIBUTION}."),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    add_access_log(app, log_line or (lambda line: print(line, flush=True)))

    def snapshot():
        return read_snapshot(db_path, **read_options)

    @app.exception_handler(ApiError)
    def api_error(request: Request, exc: ApiError):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    def validation_error(request: Request, exc: RequestValidationError):
        name = next((str(err["loc"][-1]) for err in exc.errors() if err.get("loc")), "")
        message = PARAMETER_MESSAGES.get(name, f"parámetro no válido: {name}")
        return error_response(ApiError(422, "parametro_no_valido", message))

    @app.exception_handler(StarletteHTTPException)
    def http_error(request: Request, exc: StarletteHTTPException):
        # Las cabeceras de la excepción se conservan: en los errores de la web
        # incluyen las de D3 (CSP, nosniff…); en los de la API no hay ninguna.
        headers = dict(exc.headers or {})
        if exc.status_code == 404:
            return error_response(ApiError(404, "no_encontrado",
                                           f"no existe la ruta {request.url.path}", headers))
        if exc.status_code == 405:
            # La web admite GET y HEAD (StaticFiles ya lo indica en `Allow`);
            # las rutas de la API, solo GET.
            headers.setdefault("Allow", "GET")
            message = (web.METHOD_MESSAGE if "HEAD" in headers["Allow"]
                       else "la API es de solo lectura: solo se admite GET")
            return error_response(ApiError(405, "metodo_no_permitido", message, headers))
        return error_response(ApiError(exc.status_code, "error_http", str(exc.detail)))

    @app.exception_handler(Exception)
    def unexpected_error(request: Request, exc: Exception):
        log.error("error no previsto en %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(ApiError(500, "error_interno",
                                       "error interno de la API; revisa el log del servicio"))

    @app.get("/api/health", summary="Salud del servicio")
    def health():
        """Estado (`ok`, `desactualizada`, `configuracion_no_valida` o `error`) y última captura."""
        try:
            with snapshot() as reader:
                capture = reader.capture
                counts = queries.fuel_counts(reader)
        except ApiError as exc:
            return error_response(exc, status=ERROR)
        state = health_state(capture.downloaded_at, clock(), interval_text)
        unexposed = [{"name": name, "stations": n}
                     for name, n in sorted(counts.items()) if name not in BY_NAME]
        data = {"stale_after_hours": state.stale_after_hours, "unexposed_fuels": unexposed}
        if state.message:
            data["message"] = state.message
        return success(capture, data, status=state.status)

    @app.get("/api/fuels", summary="Combustibles y estaciones que los venden")
    def fuels():
        """Los 21 combustibles del catálogo con las estaciones que los venden en la última captura."""
        with snapshot() as reader:
            capture = reader.capture
            counts = queries.fuel_counts(reader)
        items = [{**fuel.as_dict(), "stations": counts.get(fuel.name, 0)} for fuel in CATALOG]
        items.sort(key=lambda item: (-item["stations"], item["slug"]))
        return success(capture, items)

    @app.get("/api/stations/nearby", summary="Gasolineras cercanas")
    def nearby(
        lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False,
                                    description="Latitud del punto de búsqueda (punto decimal)")],
        lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False,
                                    description="Longitud del punto de búsqueda (punto decimal)")],
        fuel: Annotated[str, Query(description="Identificador del combustible (ver /api/fuels)")],
        radius_km: Annotated[float, Query(gt=0, le=MAX_RADIUS_KM, allow_inf_nan=False,
                                          description="Radio en km, en línea recta")] = DEFAULT_RADIUS_KM,
        limit: Annotated[int, Query(ge=1, le=MAX_LIMIT,
                                    description="Número máximo de estaciones")] = DEFAULT_LIMIT,
    ):
        """Estaciones con ese combustible dentro del radio, por precio, distancia e identificador."""
        chosen = find_fuel(fuel)
        if not geo.in_spain(lat, lon):
            raise ApiError(422, "fuera_de_espana",
                           "el punto de búsqueda está fuera de las zonas de España")
        with snapshot() as reader:
            capture = reader.capture
            rows = queries.fuel_prices(reader, chosen.name)
        found = []
        for row in rows:
            fields, price = station_fields(row[:8]), row[8]
            if fields["latitude"] is None:
                continue
            distance = geo.distance_km(lat, lon, fields["latitude"], fields["longitude"])
            if distance <= radius_km:
                found.append((price, distance, fields["id"], fields))
        found.sort(key=lambda item: item[:3])
        stations = [{**{k: v for k, v in fields.items() if k != "schedule"}, "price": price,
                     "unit": chosen.unit, "distance_km": round_half_up(distance, 2)}
                    for price, distance, _, fields in found[:limit]]
        return success(capture, {"fuel": chosen.as_dict(), "center": {"lat": lat, "lon": lon},
                                 "radius_km": radius_km, "limit": limit, "total": len(found),
                                 "stations": stations})

    @app.get("/api/stations/{station_id}", summary="Ficha de una estación")
    def station(station_id: str):
        """Datos de la estación y sus precios de la última captura."""
        with snapshot() as reader:
            capture = reader.capture
            row = queries.station(reader, station_id)
            prices = queries.station_prices(reader, station_id) if row else []
        if row is None:
            raise ApiError(404, "estacion_no_encontrada", f"no existe la estación {station_id!r}")
        items = [{**BY_NAME[name].as_dict(), "price": price}
                 for name, price in prices if name in BY_NAME]
        items.sort(key=lambda item: item["slug"])
        return success(capture, {**station_fields(row), "prices": items})

    @app.get("/api/provinces/prices", summary="Precio medio por provincia")
    def provinces(
        fuel: Annotated[str, Query(description="Identificador del combustible (ver /api/fuels)")],
    ):
        """Media, mínimo, máximo y estaciones de cada provincia en la última captura."""
        chosen = find_fuel(fuel)
        with snapshot() as reader:
            capture = reader.capture
            rows = queries.fuel_prices(reader, chosen.name)
        groups: dict[str, list[float]] = {}
        for row in rows:
            province = clean_text(row[4])
            if province is not None:
                groups.setdefault(province, []).append(row[8])
        items = [{"province": name, "average": average(prices), "min": min(prices),
                  "max": max(prices), "stations": len(prices)}
                 for name, prices in groups.items()]
        items.sort(key=lambda item: (item["average"], item["province"]))
        return success(capture, {"fuel": chosen.as_dict(), "provinces": items})

    # Después de todas las rutas: la web solo atiende lo que no es de /api/.
    if web_dir is not None and Path(web_dir).is_dir():
        app.mount("/", web.WebFiles(directory=Path(web_dir), api_routes=list(app.router.routes)),
                  name="web")

    return app
