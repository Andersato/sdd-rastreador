"""Unitarios de la lógica de la página (`web/js/logic.js` y `web/js/api.js`).

Corren en Chromium; los de fechas (`Intl` con `Europe/Madrid`), también en
WebKit, el motor del iPhone (design.md D11).

Se cargan desde una página vacía servida con `page.route` en el origen del
servidor de prueba, así que no hace falta añadir nada a `web/`.
"""

import pytest

from tests.web_fixtures import fixture_response, fulfill_args

pytestmark = pytest.mark.browser

HARNESS = "/__unit__.html"


def serve_blank(web):
    web.page.route(web.base + HARNESS, lambda route: route.fulfill(
        status=200, body="<!doctype html><title>unit</title>", content_type="text/html"))


class Module:
    def __init__(self, web, path):
        self.web = web
        self.path = path

    def __getattr__(self, name):
        def call(*args):
            return self.web.page.evaluate(
                "async ([path, name, args]) => (await import(path))[name](...args)",
                [self.path, name, list(args)])
        return call


@pytest.fixture
def logic_in(open_page):
    def make(timezone_id="Europe/Madrid", device="desktop"):
        web = open_page(HARNESS, device=device, before_goto=serve_blank, clock=False,
                        timezone_id=timezone_id)
        return Module(web, "/js/logic.js")
    return make


@pytest.fixture
def logic(logic_in):
    return logic_in()


# --- Formato de precios y distancias -----------------------------------------

def test_prices(logic):
    """Escenario: Precios."""
    assert logic.formatPrice(1.459, "€/l") == "1,459 €/l"
    assert logic.formatPrice(1.4, "€/l") == "1,400 €/l"
    assert logic.formatPrice(12.95, "€/kg") == "12,950 €/kg"


def test_distances(logic):
    """Escenario: Distancias."""
    assert [logic.formatDistance(d) for d in (0.91, 2.05, 3.4, 0, 50)] == [
        "0,9 km", "2,1 km", "3,4 km", "0,0 km", "50,0 km"]


def test_distance_of_the_detail_example(logic):
    assert logic.formatDistance(0.04) == "0,0 km"
    assert logic.formatDistance(2.01) == "2,0 km"


# --- Coordenadas enviadas con 3 decimales --------------------------------------

def test_rounding(logic):
    """Escenario: Redondeo."""
    point = logic.searchPoint(40.416775, -3.703790)
    assert point == {"lat": 40.417, "lon": -3.704}
    assert (logic.coordParam(point["lat"]), logic.coordParam(point["lon"])) == ("40.417", "-3.704")


def test_click_on_a_world_copy(logic):
    """Escenario: Pinchar en una copia del mundo."""
    point = logic.searchPoint(40.0, 357.6)
    assert (logic.coordParam(point["lat"]), logic.coordParam(point["lon"])) == ("40.000", "-2.400")


@pytest.mark.parametrize(("lon", "expected"), [(-3.7, -3.7), (180, -180), (-180, -180),
                                               (540, -180), (-362.5, -2.5), (2.1686, 2.1686)])
def test_normalize_longitude(logic, lon, expected):
    assert logic.normalizeLon(lon) == pytest.approx(expected)


def test_barcelona_and_half_away_from_zero(logic):
    assert logic.searchPoint(41.3874, 2.1686) == {"lat": 41.387, "lon": 2.169}
    assert logic.roundCoord(-0.0004) == 0
    assert logic.coordParam(-0.0004) == "0.000"


# --- Colores por tercios ------------------------------------------------------

TIER_CASES = [
    ("Seis precios distintos", [1.400, 1.410, 1.420, 1.430, 1.440, 1.450],
     ["cheap", "cheap", "mid", "mid", "expensive", "expensive"]),
    ("Una gasolinera extrema", [1.400, 1.410, 1.420, 1.430, 1.440, 1.450, 2.500],
     ["cheap", "cheap", "cheap", "mid", "expensive", "expensive", "expensive"]),
    ("Empates en Madrid", [1.299, 1.399, 1.459, 1.459], ["cheap", "cheap", "expensive", "expensive"]),
    ("Empate que ocupa el centro", [1.400, 1.500, 1.500, 1.500, 1.600],
     ["cheap", "mid", "mid", "mid", "expensive"]),
    ("Mayoría en el precio mínimo", [1.400, 1.400, 1.400, 1.400, 1.500],
     ["cheap", "cheap", "cheap", "cheap", "expensive"]),
    ("Mayoría en el precio máximo", [1.400, 1.500, 1.500, 1.500, 1.500],
     ["cheap", "expensive", "expensive", "expensive", "expensive"]),
    ("Dos gasolineras", [1.399, 1.459], ["cheap", "expensive"]),
    ("Todas al mismo precio", [1.459, 1.459, 1.459], ["single", "single", "single"]),
    ("Una sola gasolinera", [1.399], ["single"]),
]


@pytest.mark.parametrize(("name", "prices", "expected"), TIER_CASES, ids=[c[0] for c in TIER_CASES])
def test_tiers(logic, name, prices, expected):
    """Escenarios de «Colores por tercios»."""
    assert logic.tiers(prices) == expected


@pytest.mark.parametrize(("name", "prices", "expected"), TIER_CASES, ids=[c[0] for c in TIER_CASES])
def test_tiers_do_not_depend_on_order(logic, name, prices, expected):
    order = list(reversed(range(len(prices))))
    order = order[1::2] + order[0::2]
    shuffled = [prices[i] for i in order]
    assert logic.tiers(shuffled) == [expected[i] for i in order]


def test_tiers_without_rounding_errors(logic):
    # 1.1 + 0.3 no es exactamente 1.4 en binario; las milésimas sí lo son.
    assert logic.tiers([1.4, 1.1 + 0.3, 1.5]) == ["cheap", "cheap", "expensive"]


# --- Captura en hora de Madrid -----------------------------------------------

ENGINES = pytest.mark.parametrize("device", ["desktop", "iphone"], ids=["chromium", "webkit"])


@ENGINES
def test_summer_time_from_new_york(logic_in, device):
    """Escenario: Horario de verano."""
    logic = logic_in("America/New_York", device)
    assert logic.captureText({"downloaded_at": "2026-10-16T07:26:37Z"}) == (
        "Precios de la captura del 16/10/2026 a las 09:26 (hora de Madrid)")


@ENGINES
def test_winter_time_from_utc(logic_in, device):
    """Escenario: Horario de invierno."""
    logic = logic_in("UTC", device)
    assert logic.captureText({"downloaded_at": "2026-11-02T05:17:03Z"}) == (
        "Precios de la captura del 02/11/2026 a las 06:17 (hora de Madrid)")


@pytest.mark.parametrize("capture", [{"downloaded_at": "ayer"}, None, {},
                                     {"downloaded_at": "2026-10-16 07:26:37"},
                                     {"downloaded_at": "2026-13-40T07:26:37Z"}])
@ENGINES
def test_date_that_cannot_be_understood(logic_in, device, capture):
    """Escenario: Fecha que no se entiende."""
    assert logic_in(device=device).captureText(capture) == "Fecha de la captura desconocida"


@ENGINES
def test_stale_text(logic_in, device):
    assert logic_in(device=device).staleText({"downloaded_at": "2026-10-16T07:26:37Z"}) == (
        "Los precios pueden no estar al día: la última captura es del 16/10/2026 "
        "a las 09:26 (hora de Madrid)")


# --- Retry-After --------------------------------------------------------------

@pytest.mark.parametrize(("value", "seconds"), [
    ("5", 5), ("12", 12), ("60", 60), (" 7 ", 7), (None, 5), ("0", 5), ("abc", 5),
    ("3600", 5), ("61", 5), ("Wed, 21 Oct 2026 07:28:00 GMT", 5), ("-3", 5), ("2.5", 5)])
def test_retry_after(logic, value, seconds):
    """Escenario: Retry-After raro (y los válidos)."""
    assert logic.retryAfterSeconds(value) == seconds


# --- Validación de respuestas ----------------------------------------------------

def test_invalid_fuel_items(logic):
    """Escenario: Elementos no válidos."""
    data = [{"name": "Sin slug", "unit": "€/l", "stations": 5},
            {"name": "Gasoleo A", "slug": "gasoleo-a", "unit": "€/l", "stations": 3},
            {"name": "Sin unidad", "slug": "sin-unidad", "unit": None, "stations": 2},
            {"name": "Texto", "slug": "texto", "unit": "€/l", "stations": "4"},
            {"name": "Cero", "slug": "cero", "unit": "€/l", "stations": 0},
            None, "x"]
    result = logic.validFuels(data)
    assert [f["slug"] for f in result["offered"]] == ["gasoleo-a"]
    assert [f["slug"] for f in result["all"]] == ["gasoleo-a", "cero"]


@pytest.mark.parametrize("data", [{"fuels": []}, "x", None, 3])
def test_fuels_that_are_not_a_list(logic, data):
    """Escenario: Lista de combustibles que no se puede usar."""
    assert logic.validFuels(data) is None


def test_stations_with_unusable_data(logic):
    """Escenario: Estación con datos que no sirven."""
    stations = [{"id": "1001", "price": "1,459", "latitude": 40.4, "longitude": -3.7},
                {"id": "1002", "price": 1.459, "latitude": 40.4, "longitude": -3.68},
                {"id": "1003", "price": 1.399, "latitude": None, "longitude": -3.73},
                None]
    result = logic.validStations(stations)
    assert [s["id"] for s in result["shown"]] == ["1002"]
    assert result["discarded"] == 3
    assert logic.validStations("x") is None


# --- Textos ----------------------------------------------------------------------

def test_texts(logic):
    assert logic.stationsCountText(1) == "1 gasolinera encontrada"
    assert logic.stationsCountText(3) == "3 gasolineras encontradas"
    assert logic.discardedText(1) == "1 gasolinera no se muestra por datos incompletos."
    assert logic.discardedText(2) == "2 gasolineras no se muestran por datos incompletos."
    assert logic.moreText(342, 100, 25) == (
        "Hay 342 gasolineras en este radio; se han pedido las 100 más baratas. "
        "Reduce el radio para ver menos y más cercanas.")
    assert logic.moreText(130, 100, 5) == (
        "Hay 130 gasolineras en este radio; se han pedido las 100 más baratas.")
    assert logic.emptyText("Hidrogeno", 10) == (
        "No hay gasolineras con Hidrogeno a menos de 10 km. Prueba con un radio mayor.")
    assert logic.emptyText("Hidrogeno", 50) == "No hay gasolineras con Hidrogeno a menos de 50 km."


# --- api.js: clasificación, tiempo límite y búsquedas (tarea 4.3) ---------------


CLASSIFY_CASES = [
    ("nearby_madrid", "ok"), ("fuels_ok", "ok"), ("health_stale", "ok"),
    ("busy_base_retry_5", "busy"), ("busy_api_retry_12", "busy"), ("long_query", "busy"),
    ("busy_base_no_retry", "busy"), ("no_captures", "no_data"), ("no_data_unknown_code", "no_data"),
    ("proxy_503_html", "unexpected"), ("bad_gateway_html", "unexpected"),
    ("internal_error", "server_error"), ("outside_spain", "outside_spain"),
    ("unknown_fuel", "unknown_fuel"), ("not_found_404", "server_error"),
    ("method_405", "server_error"), ("too_many_429", "server_error"),
    ("health_busy", "busy"),
]


@pytest.fixture
def api(open_page):
    web = open_page(HARNESS, device="desktop", before_goto=serve_blank, clock=False)
    return web


def run_request(web, path):
    return web.page.evaluate("async (p) => (await import('/js/api.js')).request(p)", path)


@pytest.mark.parametrize(("name", "kind"), CLASSIFY_CASES, ids=[c[0] for c in CLASSIFY_CASES])
def test_classification_of_fixed_responses(api, name, kind):
    api.page.route(api.base + "/api/x", lambda route: route.fulfill(**fulfill_args(fixture_response(name))))
    result = run_request(api, "/api/x")
    assert result["kind"] == kind


@pytest.mark.parametrize(("name", "seconds"), [
    ("busy_base_retry_5", 5), ("busy_api_retry_12", 12), ("busy_base_no_retry", 5),
    ("busy_base_retry_0", 5), ("busy_base_retry_abc", 5), ("busy_base_retry_3600", 5),
    ("busy_base_retry_date", 5), ("long_query", 5)])
def test_busy_seconds(api, name, seconds):
    api.page.route(api.base + "/api/x", lambda route: route.fulfill(**fulfill_args(fixture_response(name))))
    assert run_request(api, "/api/x") == {"kind": "busy", "seconds": seconds}


def test_no_data_message(api):
    api.page.route(api.base + "/api/x", lambda route: route.fulfill(**fulfill_args(fixture_response("no_captures"))))
    assert run_request(api, "/api/x") == {"kind": "no_data", "message": "todavía no hay capturas guardadas"}


def test_network_failure_is_unreachable(api):
    api.page.route(api.base + "/api/x", lambda route: route.abort("connectionrefused"))
    assert run_request(api, "/api/x") == {"kind": "unreachable"}


def test_real_server_response(api):
    """La base de prueba no existe: el servidor real responde 503 sin_base."""
    result = run_request(api, "/api/fuels")
    assert result["kind"] == "no_data"


def test_timeout_after_15_seconds(open_page):
    web = open_page(HARNESS, device="desktop", before_goto=serve_blank, clock=True)
    web.page.route(web.base + "/api/x", lambda route: None)  # no contesta nunca
    web.page.evaluate("""() => { window.__r = null;
        import('/js/api.js').then(m => m.request('/api/x')).then(r => { window.__r = r; }); }""")
    web.page.wait_for_function("() => true")
    web.page.clock.run_for(14_000)
    assert web.page.evaluate("() => window.__r") is None
    web.page.clock.run_for(1_500)
    web.page.wait_for_function("() => window.__r !== null")
    assert web.page.evaluate("() => window.__r") == {"kind": "unreachable"}


def test_nearby_path(api):
    path = api.page.evaluate("""async () => (await import('/js/api.js')).nearbyPath(
        {lat: 40.417, lon: -3.704, fuel: 'gasoleo-a', radius: 10})""")
    assert path == "/api/stations/nearby?lat=40.417&lon=-3.704&fuel=gasoleo-a&radius_km=10&limit=100"


def test_new_search_aborts_and_discards_previous(api):
    held = []
    api.page.route(api.base + "/api/slow", lambda route: held.append(route))
    api.page.route(api.base + "/api/fast",
                   lambda route: route.fulfill(**fulfill_args(fixture_response("nearby_barcelona"))))
    api.page.evaluate("""async () => {
        const m = await import('/js/api.js');
        const s = m.createSearcher();
        window.__first = s.run('/api/slow');
        window.__second = await s.run('/api/fast');
        window.__firstResult = await window.__first;
    }""")
    second = api.page.evaluate("() => window.__second")
    first = api.page.evaluate("() => window.__firstResult")
    assert second["kind"] == "ok"
    assert second["body"]["data"]["stations"][0]["id"] == "8001"
    assert first == {"kind": "stale"}
    for route in held:
        try:
            route.abort()
        except Exception:
            pass
