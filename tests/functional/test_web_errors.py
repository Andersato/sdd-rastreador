"""Errores y «Reintentar» (map-view, tareas 9.2 y 9.3), con las respuestas
fijas de tests/fixtures/web/. En el iPhone (WebKit) salvo que se diga otra
cosa."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.web_helpers import (BARCELONA, MADRID, SPAIN_CORNERS, click_map, has_circle,
                               in_visible_zone, nearby_calls, station_markers, text, wait_until)

pytestmark = pytest.mark.browser

GRANT = {"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}
DENY = {"kind": "deny"}
PENDING = {"kind": "pending"}
KEY = "precios-gasolineras.preferencias"
BUSY = "El servidor está ocupado; inténtalo en unos segundos"
UNEXPECTED = "El servidor ha dado una respuesta inesperada"
SERVER_ERROR = "El servidor ha dado un error. Inténtalo más tarde."
UNREACHABLE = ("No se puede conectar con el servidor. Comprueba que está en marcha y que el "
               "túnel está abierto.")
OUTSIDE = "Ese punto está fuera de España. Pincha en el mapa un punto de España."
MINISTRY = ("Ministerio de Industria, Comercio y Turismo - Precios de carburantes "
            "en estaciones de servicio")


def params(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def prefs(**values):
    return f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(json.dumps(values))})"


@pytest.fixture
def opened(open_page):
    """Abre la web con respuestas fijas; devuelve la página y sus mocks."""
    def open_(*, fuels=("fuels_ok",), nearby=("nearby_madrid",), health=("health_ok",),
              geo=GRANT, clock=True, init_scripts=(), device="iphone"):
        mocks = {}

        def setup(web):
            mocks["fuels"] = web.mock("/api/fuels", *fuels)
            mocks["health"] = web.mock("/api/health", *health)
            mocks["nearby"] = web.mock("/api/stations/nearby", *nearby)
        web = open_page(device=device, geo=geo, clock=clock, before_goto=setup,
                        init_scripts=init_scripts)
        web.mocks = mocks
        return web
    return open_


def wait_message(web, expected=None):
    web.page.wait_for_selector("#message:not([hidden])")
    if expected is not None:
        wait_until(web, lambda: text(web, "#message") == expected)


def retry_state(web):
    retry = web.page.locator("#retry")
    return retry.is_visible(), retry.is_disabled() if retry.is_visible() else None


def no_results(web):
    return (station_markers(web) == 0 and web.page.locator(".station-row").count() == 0
            and text(web, "#count") is None)


# --- API o base ocupadas -------------------------------------------------------

def test_busy_database_with_retry_after(opened):
    """Escenario: Base ocupada con Retry-After (5 s, margen de 0,5 s)."""
    web = opened(nearby=("busy_base_retry_5",))
    wait_message(web, BUSY)
    assert retry_state(web) == (True, True)
    web.page.clock.run_for(4500)
    assert retry_state(web) == (True, True)
    web.page.clock.run_for(1000)
    assert retry_state(web) == (True, False)
    assert len(nearby_calls(web)) == 1


def test_retry(opened):
    """Escenario: Reintentar (una sola petición con los mismos parámetros)."""
    web = opened(nearby=("busy_base_retry_5", "nearby_madrid"))
    wait_message(web, BUSY)
    web.page.clock.run_for(5500)
    web.press("#retry")
    web.page.wait_for_selector("#count:not([hidden])")
    calls = nearby_calls(web)
    assert len(calls) == 2 and params(calls[0]) == params(calls[1])
    assert station_markers(web) == 3


def test_busy_api_with_another_retry_after(opened):
    """Escenario: API ocupada con otro Retry-After (12 s en /api/fuels)."""
    web = opened(fuels=("busy_api_retry_12",))
    wait_message(web, BUSY)
    web.page.clock.run_for(11500)
    assert retry_state(web) == (True, True)
    web.page.clock.run_for(1000)
    assert retry_state(web) == (True, False)


@pytest.mark.parametrize("name", ["long_query", "busy_base_no_retry", "busy_base_retry_0",
                                  "busy_base_retry_abc", "busy_base_retry_3600",
                                  "busy_base_retry_date"])
def test_odd_retry_after_waits_5_seconds(opened, name):
    """Escenarios: Consulta demasiado larga y Retry-After raro (5 s)."""
    web = opened(nearby=(name,))
    wait_message(web, BUSY)
    web.page.clock.run_for(4500)
    assert retry_state(web) == (True, True)
    web.page.clock.run_for(1000)
    assert retry_state(web) == (True, False)


# --- Sin datos en la base ---------------------------------------------------------

def test_database_without_captures(opened):
    """Escenario: Base sin capturas."""
    web = opened(fuels=("no_captures",))
    wait_message(web, "No hay datos disponibles. Detalle: todavía no hay capturas guardadas")
    assert retry_state(web) == (True, False)


def test_503_without_message(opened):
    """Escenario: 503 sin mensaje."""
    web = opened(fuels=("no_data_unknown_code",))
    wait_message(web, "No hay datos disponibles.")
    assert retry_state(web) == (True, False)


def test_error_message_with_markup(opened):
    """Escenario: Mensaje de error con etiquetas."""
    web = opened(fuels=("no_captures_markup",))
    wait_message(web, "No hay datos disponibles. Detalle: <b>sin datos</b>")
    assert web.page.locator("#message b").count() == 0


# --- Sin gasolineras en el radio -------------------------------------------------------

def test_no_results_at_10_km(opened):
    """Escenario: Sin resultados a 10 km (Hidrogeno)."""
    web = opened(nearby=("nearby_empty",), init_scripts=[prefs(fuel="hidrogeno")])
    wait_message(web, "No hay gasolineras con Hidrogeno a menos de 10 km. Prueba con un radio mayor.")
    assert has_circle(web) and station_markers(web) == 0
    assert not web.page.locator("#retry").is_visible()


def test_no_results_at_50_km(opened):
    """Escenario: Sin resultados a 50 km."""
    web = opened(nearby=("nearby_empty_50",), init_scripts=[prefs(fuel="hidrogeno", radius=50)])
    wait_message(web, "No hay gasolineras con Hidrogeno a menos de 50 km.")


# --- Punto fuera de España ------------------------------------------------------------

def test_click_on_rabat(opened):
    """Escenario: Pinchar en Rabat."""
    web = opened(geo=DENY, clock=False, nearby=("outside_spain", "nearby_madrid"))
    web.page.wait_for_selector("#fuel:not([disabled])")
    click_map(web, 34.0209, -6.8416)
    wait_message(web, OUTSIDE)
    assert not has_circle(web) and web.page.locator(".search-point").count() == 0
    assert no_results(web)
    click_map(web, *MADRID)
    web.page.wait_for_selector("#count:not([hidden])")
    assert station_markers(web) == 3


def test_location_in_london(opened):
    """Escenario: Ubicación en Londres."""
    web = opened(geo={"kind": "grant", "lat": 51.5074, "lon": -0.1278}, clock=False,
                 nearby=("outside_spain",))
    wait_message(web, OUTSIDE)
    web.page.wait_for_timeout(300)
    assert in_visible_zone(web, SPAIN_CORNERS)
    assert not web.page.locator("#back-to-location").is_visible()


def test_point_in_portugal_inside_the_zone(opened):
    """Escenario: Punto de Portugal dentro de la zona de la Península."""
    web = opened(geo=DENY, clock=False, nearby=("nearby_empty_gasoleo",))
    web.page.wait_for_selector("#fuel:not([disabled])")
    click_map(web, 38.7223, -9.1393)
    wait_message(web, "No hay gasolineras con Gasoleo A a menos de 10 km. Prueba con un radio mayor.")


# --- API caída o respuesta inesperada ---------------------------------------------------

def test_api_down_on_open(opened):
    """Escenario: API caída al abrir."""
    web = opened(fuels=("network_error",), health=("network_error",), clock=False)
    wait_message(web, UNREACHABLE)
    assert retry_state(web) == (True, False)
    attribution = web.page.locator(".leaflet-control-attribution")
    assert attribution.is_visible() and MINISTRY in attribution.inner_text()
    assert web.page.locator("#map").is_visible()


def test_api_that_does_not_answer(opened):
    """Escenario: API que no contesta (15 s, margen de 1 s)."""
    web = opened(nearby=(None,))
    wait_until(web, lambda: len(nearby_calls(web)) == 1)
    web.page.clock.run_for(14000)
    assert text(web, "#message") is None
    web.page.clock.run_for(2000)
    wait_message(web, UNREACHABLE)
    assert retry_state(web) == (True, False)


@pytest.mark.parametrize(("where", "name"), [("nearby", "bad_gateway_html"),
                                             ("fuels", "proxy_503_html")])
def test_response_that_is_not_json(opened, where, name):
    """Escenarios: Respuesta que no es JSON y 503 que no es JSON."""
    web = opened(**{where: (name,)}, clock=False)
    wait_message(web, UNEXPECTED)
    assert "nginx" not in web.page.locator("body").inner_text()
    assert "No hay datos disponibles" not in web.page.locator("body").inner_text()


@pytest.mark.parametrize("name", ["internal_error", "unknown_fuel", "not_found_404", "method_405",
                                  "too_many_429"])
def test_other_api_errors(opened, name):
    """Escenarios: Error interno y Otros errores de la API."""
    web = opened(nearby=(name,), clock=False)
    wait_message(web, SERVER_ERROR)
    assert retry_state(web) == (True, False)
    body = web.page.locator("body").inner_text()
    for detail in ("error_interno", "combustible_desconocido", "no_encontrado",
                   "metodo_no_permitido", "mensaje del servidor", "revisa el log"):
        assert detail not in body


def test_retry_after_unknown_fuel(opened):
    """Escenario: Reintentar tras combustible desconocido."""
    web = opened(nearby=("unknown_fuel", "nearby_madrid"), clock=False)
    wait_message(web, SERVER_ERROR)
    fuels_before = len(web.mocks["fuels"].calls)
    web.press("#retry")
    web.page.wait_for_selector("#count:not([hidden])")
    assert len(web.mocks["fuels"].calls) == fuels_before + 1
    assert len(nearby_calls(web)) == 2
    assert params(nearby_calls(web)[-1])["fuel"] == "gasoleo-a"


# --- Tarea 9.3: lo que depende de errores y de «Reintentar» --------------------------

def test_back_to_late_location_outside_spain(opened):
    """Escenario: Volver a una ubicación tardía fuera de España (y el foco)."""
    web = opened(geo=PENDING, clock=False, nearby=("nearby_barcelona", "outside_spain"))
    web.page.wait_for_selector("#fuel:not([disabled])")
    click_map(web, *BARCELONA)
    web.page.wait_for_selector("#count:not([hidden])")
    web.geo.grant(51.5074, -0.1278)
    web.page.wait_for_selector("#back-to-location:not([hidden])")
    web.page.focus("#back-to-location")
    web.page.keyboard.press("Enter")
    wait_message(web, OUTSIDE)
    web.page.wait_for_timeout(300)
    assert in_visible_zone(web, SPAIN_CORNERS)
    assert not has_circle(web) and no_results(web)
    assert not web.page.locator("#back-to-location").is_visible()
    assert web.page.evaluate("() => document.activeElement.id") == "status"


def test_click_outside_spain_while_waiting(opened):
    """Escenario: Pinchar fuera de España mientras se espera."""
    web = opened(geo=PENDING, clock=False, nearby=("outside_spain",))
    web.page.wait_for_selector("#fuel:not([disabled])")
    click_map(web, 34.0209, -6.8416)
    wait_message(web, OUTSIDE)
    web.geo.grant(*MADRID)
    web.page.wait_for_selector("#back-to-location:not([hidden])")
    web.page.wait_for_timeout(300)
    assert len(nearby_calls(web)) == 1
    assert text(web, "#message") == OUTSIDE


def test_click_with_failed_fuels(opened):
    """Escenario: Pinchar con los combustibles fallidos."""
    web = opened(geo=DENY, clock=False, fuels=("network_error", "fuels_ok"),
                 nearby=("nearby_barcelona",))
    wait_message(web, UNREACHABLE)
    click_map(web, *BARCELONA)
    web.page.wait_for_timeout(300)
    assert web.page.evaluate("() => window.__mapView.state.point") == {"lat": 41.387, "lon": 2.169}
    assert nearby_calls(web) == []
    web.press("#retry")
    web.page.wait_for_selector("#count:not([hidden])")
    assert len(web.mocks["fuels"].calls) == 2
    assert len(nearby_calls(web)) == 1
    assert (params(nearby_calls(web)[0])["lat"], params(nearby_calls(web)[0])["lon"]) == (
        "41.387", "2.169")


def test_retry_after_failed_fuels(opened):
    """Escenario: Reintentar tras fallar los combustibles (ubicación concedida)."""
    web = opened(clock=False, fuels=("network_error", "fuels_ok"))
    wait_message(web, UNREACHABLE)
    assert nearby_calls(web) == []
    web.press("#retry")
    web.page.wait_for_selector("#count:not([hidden])")
    assert len(web.mocks["fuels"].calls) == 2
    assert len(nearby_calls(web)) == 1
    assert params(nearby_calls(web)[0])["lat"] == "40.417"


def test_no_fuel_with_stations(opened):
    """Escenario: Ningún combustible con estaciones («Reintentar» pide /api/fuels)."""
    web = opened(clock=False, fuels=("fuels_all_zero", "fuels_ok"))
    wait_message(web, "No hay precios en la última captura")
    assert nearby_calls(web) == []
    web.press("#retry")
    web.page.wait_for_selector("#count:not([hidden])")
    assert len(web.mocks["fuels"].calls) == 2


@pytest.mark.parametrize("name", ["fuels_not_list", "fuels_no_valid_items"])
def test_fuel_list_that_cannot_be_used(opened, name):
    """Escenario: Lista de combustibles que no se puede usar."""
    web = opened(clock=False, fuels=(name,))
    wait_message(web, UNEXPECTED)
    assert retry_state(web) == (True, False)
    web.page.wait_for_timeout(300)
    assert nearby_calls(web) == []


@pytest.mark.parametrize("name", ["nearby_all_discarded", "nearby_no_stations",
                                  "nearby_342_all_discarded"])
def test_nothing_that_can_be_shown(opened, name):
    """Escenarios: Todas descartadas, Respuesta incompleta y Ninguna se puede mostrar."""
    web = opened(clock=False, nearby=("nearby_madrid", name))
    web.page.wait_for_selector("#count:not([hidden])")
    web.page.select_option("#radius", "25")
    wait_message(web, UNEXPECTED)
    assert retry_state(web) == (True, False)
    assert no_results(web)
    for notice in ("#more", "#discarded"):
        assert web.page.locator(notice).text_content() == ""


@pytest.mark.parametrize("name", ["nearby_empty", "nearby_all_discarded", "busy_base_retry_5"])
def test_no_count(opened, name):
    """Escenario: Sin recuento (total 0, todas descartadas o 503)."""
    web = opened(clock=False, nearby=("nearby_madrid", name))
    web.page.wait_for_selector("#count:not([hidden])")
    web.page.select_option("#radius", "25")
    wait_message(web)
    assert text(web, "#count") is None


@pytest.mark.parametrize(("first", "notice"), [("nearby_two_discarded", "#discarded"),
                                               ("nearby_342", "#more")])
def test_notices_disappear_after_an_error(opened, first, notice):
    """Los avisos de descartadas y de «Hay N gasolineras…» desaparecen tras un error."""
    web = opened(clock=False, nearby=(first, "busy_base_retry_5"))
    web.page.wait_for_selector("#count:not([hidden])")
    assert web.page.locator(notice).text_content()
    web.page.select_option("#radius", "25")
    wait_message(web, BUSY)
    assert web.page.locator(notice).text_content() == ""


def test_folds_when_an_error_leaves_no_list(opened):
    """Escenarios: Sin lista que mostrar y Se pliega al quedarse sin lista (con un error)."""
    web = opened(clock=False, nearby=("nearby_madrid", "internal_error", "nearby_madrid"))
    web.page.wait_for_selector("#count:not([hidden])")
    web.press("#toggle")
    web.page.wait_for_selector("#panel.expanded")
    web.page.select_option("#radius", "25")
    wait_message(web, SERVER_ERROR)
    assert "expanded" not in web.page.get_attribute("#panel", "class")
    assert not web.page.locator("#toggle").is_visible()
    assert not web.page.locator("#cheapest").is_visible()
    assert web.page.locator("#message").is_visible()
    web.press("#retry")
    web.page.wait_for_selector("#count:not([hidden])")
    assert "expanded" not in web.page.get_attribute("#panel", "class")
    assert text(web, "#toggle") == "Ver lista"


def test_no_list_without_point(opened):
    """Escenario: Sin lista que mostrar (sin punto elegido)."""
    web = opened(geo=DENY, clock=False)
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert not web.page.locator("#toggle").is_visible()
    assert not web.page.locator("#cheapest").is_visible()
