"""Genera las respuestas fijas de la API para los tests de la web (add-map-view y
add-station-detail).

Son respuestas de nuestra propia API (`prices-api`) escritas a mano a partir
de la spec, no del Ministerio. Cada archivo tiene la forma
`{"status", "headers", "body"}` o, para respuestas que no son JSON,
`{"status", "headers", "body_text"}`.

Se vuelven a generar con: .venv/bin/python tests/fixtures/web/make_web_fixtures.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
ATTRIBUTION = ("Ministerio de Industria, Comercio y Turismo - Precios de carburantes "
               "en estaciones de servicio")
CAPTURE = {"downloaded_at": "2026-10-16T07:26:37Z", "source_date": "2026-10-16T09:26:34+02:00"}
GASOLEO_A = {"name": "Gasoleo A", "slug": "gasoleo-a", "unit": "€/l", "kind": "combustible"}
HIDROGENO = {"name": "Hidrogeno", "slug": "hidrogeno", "unit": "€/kg", "kind": "combustible"}

# (nombre, slug, unidad, tipo), como el catálogo de src/api/catalog.py.
CATALOG = [
    ("Adblue", "adblue", "€/l", "aditivo"),
    ("Biodiesel", "biodiesel", "€/l", "combustible"),
    ("Bioetanol", "bioetanol", "€/l", "combustible"),
    ("Biogas Natural Comprimido", "biogas-natural-comprimido", "€/kg", "combustible"),
    ("Biogas Natural Licuado", "biogas-natural-licuado", "€/kg", "combustible"),
    ("Diésel Renovable", "diesel-renovable", "€/l", "combustible"),
    ("Gas Natural Comprimido", "gas-natural-comprimido", "€/kg", "combustible"),
    ("Gas Natural Licuado", "gas-natural-licuado", "€/kg", "combustible"),
    ("Gases licuados del petróleo", "gases-licuados-del-petroleo", "€/l", "combustible"),
    ("Gasoleo A", "gasoleo-a", "€/l", "combustible"),
    ("Gasoleo B", "gasoleo-b", "€/l", "combustible"),
    ("Gasoleo Premium", "gasoleo-premium", "€/l", "combustible"),
    ("Gasolina 95 E10", "gasolina-95-e10", "€/l", "combustible"),
    ("Gasolina 95 E25", "gasolina-95-e25", "€/l", "combustible"),
    ("Gasolina 95 E5", "gasolina-95-e5", "€/l", "combustible"),
    ("Gasolina 95 E5 Premium", "gasolina-95-e5-premium", "€/l", "combustible"),
    ("Gasolina 95 E85", "gasolina-95-e85", "€/l", "combustible"),
    ("Gasolina 98 E10", "gasolina-98-e10", "€/l", "combustible"),
    ("Gasolina 98 E5", "gasolina-98-e5", "€/l", "combustible"),
    ("Gasolina Renovable", "gasolina-renovable", "€/l", "combustible"),
    ("Hidrogeno", "hidrogeno", "€/kg", "combustible"),
]


def ok(data, capture=CAPTURE, **extra):
    body = {"attribution": ATTRIBUTION, **extra, "data": data}
    if capture is not None:
        body["capture"] = capture
    return {"status": 200, "headers": {}, "body": body}


def error(http_status, code, message="mensaje del servidor", headers=None, **extra):
    err = {"code": code}
    if message is not None:
        err["message"] = message
    return {"status": http_status, "headers": headers or {},
            "body": {"attribution": ATTRIBUTION, **extra, "error": err}}


def html(status):
    return {"status": status, "headers": {},
            "body_text": "<!doctype html><html><body><h1>Bad Gateway</h1>"
                         "<p>nginx proxy</p></body></html>"}


def fuels(counts: dict):
    items = [{"name": n, "slug": s, "unit": u, "kind": k, "stations": counts.get(s, 0)}
             for n, s, u, k in CATALOG]
    items.sort(key=lambda i: (-i["stations"], i["slug"]))
    return ok(items)


def station(sid, price, distance, brand="REPSOL", lat=40.42, lon=-3.70, unit="€/l", **fields):
    return {"id": sid, "brand": brand, "address": "CALLE MAYOR, 1", "municipality": "Madrid",
            "province": "MADRID", "latitude": lat, "longitude": lon, "price": price,
            "unit": unit, "distance_km": distance, **fields}


def nearby(stations, total=None, radius=10, fuel=GASOLEO_A, capture=CAPTURE,
           center=(40.417, -3.704)):
    data = {"fuel": fuel, "center": {"lat": center[0], "lon": center[1]}, "radius_km": radius,
            "limit": 100, "total": len(stations) if total is None else total,
            "stations": stations}
    return ok(data, capture=capture)


def many(n, start_price=1.300, step=0.001):
    """`n` estaciones válidas por precio creciente alrededor de Madrid."""
    return [station(f"{2000 + i}", round(start_price + i * step, 3), round(0.5 + i * 0.2, 2),
                    brand=f"GASOLINERA {i + 1}", lat=40.40 + (i % 10) * 0.01,
                    lon=-3.75 + (i // 10) * 0.01)
            for i in range(n)]


NEWER_CAPTURE = {"downloaded_at": "2026-10-16T08:26:40Z",
                 "source_date": "2026-10-16T10:26:36+02:00"}


def price(slug, value):
    """Un precio de la ficha de una estación, con su nombre y unidad del catálogo."""
    name, _, unit, kind = next(c for c in CATALOG if c[1] == slug)
    return {"slug": slug, "name": name, "unit": unit, "kind": kind, "price": value}


def detail(sid, schedule, prices, brand="REPSOL", lat=40.416775, lon=-3.70379,
           capture=CAPTURE):
    """Respuesta de `GET /api/stations/{id}` (spec prices-api, «Ficha de una estación»)."""
    return ok({"id": sid, "brand": brand, "address": "CALLE MAYOR, 1", "municipality": "Madrid",
               "province": "MADRID", "schedule": schedule, "latitude": lat, "longitude": lon,
               "prices": prices}, capture=capture)


def build() -> dict:
    files = {}
    # --- 503 ocupada -------------------------------------------------------
    busy = "la base de datos está ocupada guardando una captura; inténtalo de nuevo en unos segundos"
    for name, value in [("5", "5"), ("0", "0"), ("abc", "abc"), ("3600", "3600"),
                        ("date", "Wed, 21 Oct 2026 07:28:00 GMT")]:
        files[f"busy_base_retry_{name}"] = error(503, "base_ocupada", busy, {"Retry-After": value})
    files["busy_base_no_retry"] = error(503, "base_ocupada", busy)
    api_busy = "la API está atendiendo demasiadas consultas; inténtalo de nuevo en unos segundos"
    files["busy_api_retry_5"] = error(503, "api_ocupada", api_busy, {"Retry-After": "5"})
    files["busy_api_retry_12"] = error(503, "api_ocupada", api_busy, {"Retry-After": "12"})
    files["long_query"] = error(503, "consulta_demasiado_larga", "la consulta ha tardado demasiado")
    # --- 503 sin datos -----------------------------------------------------
    files["no_captures"] = error(503, "sin_capturas", "todavía no hay capturas guardadas")
    files["no_captures_markup"] = error(503, "sin_capturas", "<b>sin datos</b>")
    files["no_data_unknown_code"] = error(503, "codigo_raro", None)
    files["proxy_503_html"] = html(503)
    # --- otros errores -----------------------------------------------------
    files["bad_gateway_html"] = html(502)
    files["internal_error"] = error(500, "error_interno",
                                    "error interno de la API; revisa el log del servicio")
    files["outside_spain"] = error(422, "fuera_de_espana",
                                   "el punto de búsqueda está fuera de las zonas de España")
    files["unknown_fuel"] = error(422, "combustible_desconocido",
                                  "combustible desconocido: 'gasoleo-a'")
    files["not_found_404"] = error(404, "no_encontrado", "no existe la ruta /api/x")
    files["method_405"] = error(405, "metodo_no_permitido", "solo se admite GET", {"Allow": "GET"})
    files["too_many_429"] = error(429, "demasiadas_peticiones", "demasiadas peticiones")
    # --- /api/fuels --------------------------------------------------------
    files["fuels_ok"] = fuels({"gasoleo-a": 3, "gasolina-95-e5": 2, "adblue": 1, "hidrogeno": 1})
    files["fuels_hidrogeno_zero"] = fuels({"gasoleo-a": 3, "gasolina-95-e5": 2, "adblue": 1})
    files["fuels_all_zero"] = fuels({})
    files["fuels_not_list"] = ok({"fuels": "no es una lista"})
    files["fuels_invalid_items"] = ok([
        {"name": "Sin slug", "unit": "€/l", "kind": "combustible", "stations": 5},
        {"name": "Gasoleo A", "slug": "gasoleo-a", "unit": "€/l", "kind": "combustible",
         "stations": 3},
        {"name": "Sin unidad", "slug": "sin-unidad", "unit": None, "kind": "combustible",
         "stations": 2},
        {"name": "Recuento en texto", "slug": "recuento-texto", "unit": "€/l",
         "kind": "combustible", "stations": "4"},
    ])
    files["fuels_no_valid_items"] = ok([{"name": "Sin slug", "unit": "€/l", "stations": 5}])
    # --- cercanas ----------------------------------------------------------
    files["nearby_madrid"] = nearby([
        station("1003", 1.399, 3.4, brand="CEPSA", lat=40.44, lon=-3.73),
        station("1001", 1.459, 0.91, lat=40.425, lon=-3.7038),
        station("1002", 1.459, 2.01, brand=None, lat=40.4168, lon=-3.68),
    ], radius=5)
    files["nearby_legend"] = nearby([
        station("1004", 1.299, 5.14, brand="BP", lat=40.463, lon=-3.7038),
        station("1003", 1.399, 3.4, brand="CEPSA", lat=40.44, lon=-3.73),
        station("1001", 1.459, 0.91, lat=40.425, lon=-3.7038),
        station("1002", 1.459, 2.01, brand="GALP", lat=40.4168, lon=-3.68),
    ])
    files["nearby_same_price"] = nearby([
        station("1001", 1.459, 0.91, lat=40.425, lon=-3.7038),
        station("1002", 1.459, 2.01, brand="GALP", lat=40.4168, lon=-3.68),
        station("1003", 1.459, 3.4, brand="CEPSA", lat=40.44, lon=-3.73),
    ])
    files["nearby_one"] = nearby([station("1003", 1.399, 3.4, brand="CEPSA", lat=40.44,
                                          lon=-3.73)])
    files["nearby_detail"] = nearby([
        station("4375", 1.459, 0.04, lat=40.416775, lon=-3.70379),
        station("5120", 1.499, 1.2, brand=None, address=None, municipality=None,
                lat=40.43, lon=-3.68),
    ])
    files["nearby_barcelona"] = nearby([
        station("8001", 1.419, 0.6, brand="PLENOIL", lat=41.39, lon=2.17, municipality="Barcelona",
                province="BARCELONA"),
        station("8002", 1.439, 1.1, brand="BONAREA", lat=41.38, lon=2.16, municipality="Barcelona",
                province="BARCELONA"),
    ], center=(41.387, 2.169))
    files["nearby_hidrogeno"] = nearby([
        station("9001", 12.95, 4.2, brand="HYDRO", lat=40.45, lon=-3.69, unit="€/kg"),
    ], fuel=HIDROGENO)
    files["nearby_invalid_stations"] = nearby([
        station("1001", "1,459", 0.91, lat=40.425, lon=-3.7038),
        station("1002", 1.459, 2.01, brand="GALP", lat=40.4168, lon=-3.68),
        station("1003", 1.399, 3.4, brand="CEPSA", lat=None, lon=-3.73),
    ])
    files["nearby_one_discarded"] = nearby([
        station("1003", 1.399, 3.4, brand="CEPSA", lat=40.44, lon=-3.73),
        station("1001", 1.459, 0.91, lat=None, lon=None),
        station("1002", 1.459, 2.01, brand="GALP", lat=40.4168, lon=-3.68),
    ])
    files["nearby_two_discarded"] = nearby([
        station("1001", 1.399, 0.5), station("1002", None, 0.7), station("1003", 1.419, 0.9),
        station("1004", None, 1.1), station("1005", 1.439, 1.3)])
    files["nearby_all_discarded"] = nearby([station("1001", None, 0.5),
                                            station("1002", None, 0.7)])
    files["nearby_342"] = nearby(many(100), total=342, radius=25)
    two_bad = many(100)
    two_bad[10]["latitude"] = None
    two_bad[20]["longitude"] = None
    files["nearby_342_two_discarded"] = nearby(two_bad, total=342, radius=25)
    all_bad = many(100)
    for s in all_bad:
        s["price"] = None
    files["nearby_342_all_discarded"] = nearby(all_bad, total=342, radius=25)
    files["nearby_130_5km"] = nearby(many(100), total=130, radius=5)
    files["nearby_40"] = nearby(many(40))
    files["nearby_long_brand"] = nearby([station("1001", 1.459, 0.91, brand="X" * 80)])
    files["nearby_markup_brand"] = nearby([station("1001", 1.459, 0.91,
                                                   brand="<img src=x onerror=alert(1)>")])
    files["nearby_empty"] = nearby([], fuel=HIDROGENO)
    files["nearby_empty_50"] = nearby([], fuel=HIDROGENO, radius=50)
    files["nearby_empty_gasoleo"] = nearby([], center=(38.722, -9.139))
    files["nearby_no_stations"] = ok({"fuel": GASOLEO_A, "center": {"lat": 40.417, "lon": -3.704},
                                      "radius_km": 10, "limit": 100, "total": 3})
    files["nearby_winter"] = nearby([station("1001", 1.459, 0.91)],
                                    capture={"downloaded_at": "2026-11-02T05:17:03Z",
                                             "source_date": None})
    files["nearby_bad_capture"] = nearby([station("1001", 1.459, 0.91)],
                                         capture={"downloaded_at": "ayer", "source_date": None})
    files["nearby_no_capture"] = nearby([station("1001", 1.459, 0.91)], capture=None)
    # --- /api/health -------------------------------------------------------
    health = {"stale_after_hours": 13, "unexposed_fuels": []}
    files["health_ok"] = ok(health, status="ok")
    files["health_stale"] = ok(health, status="desactualizada")
    files["health_invalid_config"] = ok({**health, "stale_after_hours": None,
                                         "message": "intervalo no válido"},
                                        status="configuracion_no_valida")
    files["health_busy"] = error(503, "api_ocupada", api_busy, {"Retry-After": "5"},
                                 status="error")
    # --- ficha de una estación (add-station-detail) ------------------------
    files["station_4375"] = detail("4375", "L-D: 24H",
                                   [price("gasoleo-a", 1.459), price("gasolina-95-e5", 1.529)])
    files["station_4375_newer"] = detail(
        "4375", "L-D: 24H", [price("gasoleo-a", 1.479), price("gasolina-95-e5", 1.529)],
        capture=NEWER_CAPTURE)
    files["station_4375_full"] = detail(
        "4375", "L-J: 06:00-22:30; V: 06:00-23:00; S: 06:45-23:00; D: 07:45-22:30",
        [price("adblue", 0.899), price("gasoleo-a", 1.459), price("gasoleo-premium", 1.559),
         price("gasolina-95-e5", 1.529), price("gasolina-98-e5", 1.689)])
    files["station_4375_empty"] = detail("4375", None, [])
    files["station_1001"] = detail("1001", "L-D: 24H", [price("gasoleo-a", 1.459)],
                                   lat=40.425, lon=-3.7038)
    files["station_1002"] = detail("1002", "L-S: 07:00-21:00", [price("gasoleo-a", 1.459)],
                                   brand="GALP", lat=40.4168, lon=-3.68)
    files["station_1003"] = detail("1003", "L-V: 06:00-22:00; S-D: 08:00-15:00",
                                   [price("gasoleo-a", 1.399)], brand="CEPSA", lat=40.44,
                                   lon=-3.73)
    files["station_not_found"] = error(404, "estacion_no_encontrada",
                                       "no existe la estación «4375»")
    return files


def main():
    for name, spec in build().items():
        (HERE / f"{name}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")


if __name__ == "__main__":
    main()
