"""Ubicación y punto de búsqueda (map-view, tarea 5.2): «Punto de búsqueda
desde la ubicación del navegador», «Espera de la ubicación», «Sin ubicación
del navegador», «Coordenadas enviadas con 3 decimales» y «Ubicación y punto
pinchado sin guardar». En el iPhone (WebKit) y, lo común, en el Pixel 7."""

from urllib.parse import parse_qs, urlsplit

import pytest

from tests.web_helpers import (BARCELONA, CLICK_HINT, MADRID, SEARCHING, SPAIN_CORNERS,
                               circle_in_view, click_map, in_visible_zone, nearby_calls,
                               point_and_circle, seed_madrid, text, wait_until)

pytestmark = pytest.mark.browser

GRANT = {"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}


@pytest.fixture
def seeded(web_db):
    seed_madrid(web_db)


def params(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def wait_results(web):
    web.page.wait_for_selector("#count:not([hidden])")


def wait_hint(web, expected):
    wait_until(web, lambda: text(web, "#hint") == expected)


# --- Punto de búsqueda desde la ubicación del navegador --------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_location_granted_in_madrid(open_page, seeded, device):
    """Escenario: Ubicación concedida en Madrid."""
    web = open_page(device=device, geo=GRANT, clock=False)
    wait_results(web)
    calls = nearby_calls(web)
    assert len(calls) == 1
    assert urlsplit(calls[0]).query == "lat=40.417&lon=-3.704&fuel=gasoleo-a&radius_km=10&limit=100"
    point = web.page.evaluate("() => window.__mapView.state.point")
    assert point == {"lat": 40.417, "lon": -3.704}
    # marca ese punto (redondeado) y dibuja ahí el círculo de 10 km
    assert point_and_circle(web) == {"point": [40.417, -3.704], "circle": [40.417, -3.704]}
    assert web.page.locator(".search-point").count() == 1
    assert circle_in_view(web)
    assert web.console_errors == []


def test_back_to_my_location(open_page, seeded):
    """Escenario: Volver a mi ubicación."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    click_map(web, *BARCELONA)
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    wait_results(web)
    web.press("#back-to-location")
    wait_until(web, lambda: len(nearby_calls(web)) == 3)
    assert params(nearby_calls(web)[-1])["lat"] == "40.417"
    assert params(nearby_calls(web)[-1])["lon"] == "-3.704"
    wait_results(web)
    assert web.page.evaluate("() => window.__mapView.state.point") == {"lat": 40.417, "lon": -3.704}
    assert point_and_circle(web) == {"point": [40.417, -3.704], "circle": [40.417, -3.704]}
    assert circle_in_view(web)


def test_no_location_no_button(open_page, seeded):
    """Escenario: Sin ubicación no hay botón."""
    web = open_page(geo={"kind": "deny"}, clock=False)
    wait_hint(web, CLICK_HINT)
    assert not web.page.locator("#back-to-location").is_visible()


# --- Espera de la ubicación -----------------------------------------------------------

def test_while_waiting(open_page, seeded):
    """Escenario: Mientras se espera."""
    web = open_page(clock=False)
    wait_hint(web, SEARCHING)
    web.page.wait_for_timeout(500)
    assert in_visible_zone(web, SPAIN_CORNERS)
    assert nearby_calls(web) == []


def test_click_while_waiting(open_page, seeded):
    """Escenario: Pinchar mientras se espera."""
    web = open_page()
    web.page.clock.run_for(3000)
    click_map(web, *BARCELONA)
    web.page.clock.run_for(2000)
    web.geo.grant(*MADRID)
    wait_results(web)
    web.page.wait_for_timeout(300)
    calls = nearby_calls(web)
    assert len(calls) == 1
    assert (params(calls[0])["lat"], params(calls[0])["lon"]) == ("41.387", "2.169")
    assert web.page.evaluate("() => window.__mapView.state.point") == {"lat": 41.387, "lon": 2.169}
    assert text(web, "#hint") is None
    assert web.page.locator("#back-to-location").is_visible()


# --- Sin ubicación del navegador ---------------------------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_location_denied(open_page, seeded, device):
    """Escenario: Ubicación denegada."""
    web = open_page(device=device, geo={"kind": "deny"}, clock=False)
    wait_hint(web, CLICK_HINT)
    web.page.wait_for_timeout(300)
    assert in_visible_zone(web, SPAIN_CORNERS)
    assert nearby_calls(web) == []


def test_browser_without_geolocation(open_page, seeded):
    """Escenario: Navegador sin ubicación."""
    web = open_page(geo={"kind": "none"}, clock=False)
    wait_hint(web, CLICK_HINT)
    web.page.wait_for_timeout(300)
    assert in_visible_zone(web, SPAIN_CORNERS)
    assert nearby_calls(web) == []
    assert web.console_errors == []


def test_location_that_does_not_arrive(open_page, seeded):
    """Escenario: Ubicación que no llega (10 s con un margen de 1 s)."""
    web = open_page()
    web.page.clock.run_for(9000)
    assert text(web, "#hint") == SEARCHING
    web.page.clock.run_for(2000)
    wait_hint(web, CLICK_HINT)
    assert in_visible_zone(web, SPAIN_CORNERS)
    assert nearby_calls(web) == []


def test_late_location_without_click(open_page, seeded):
    """Escenario: Ubicación tardía sin pinchar."""
    web = open_page()
    web.page.clock.run_for(11000)
    wait_hint(web, CLICK_HINT)
    web.page.clock.run_for(4000)
    web.geo.grant(*MADRID)
    wait_results(web)
    assert len(nearby_calls(web)) == 1
    assert params(nearby_calls(web)[0])["lat"] == "40.417"
    assert text(web, "#hint") is None
    assert web.page.locator("#back-to-location").is_visible()
    # igual que si hubiera llegado a tiempo: punto marcado y círculo encuadrado
    assert point_and_circle(web) == {"point": [40.417, -3.704], "circle": [40.417, -3.704]}
    assert circle_in_view(web)


def test_late_location_after_click(open_page, seeded):
    """Escenario: Ubicación tardía después de pinchar."""
    web = open_page()
    web.page.clock.run_for(11000)
    wait_hint(web, CLICK_HINT)
    click_map(web, *BARCELONA)
    wait_results(web)
    web.geo.grant(*MADRID)
    web.page.wait_for_timeout(500)
    calls = nearby_calls(web)
    assert len(calls) == 1 and params(calls[0])["lat"] == "41.387"
    assert web.page.evaluate("() => window.__mapView.state.point") == {"lat": 41.387, "lon": 2.169}
    assert web.page.locator("#back-to-location").is_visible()


# --- Coordenadas enviadas con 3 decimales -----------------------------------------

def test_rounding_in_the_request(open_page, seeded):
    """Escenario: Redondeo (petición real desde la ubicación)."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    query = params(nearby_calls(web)[0])
    assert (query["lat"], query["lon"]) == ("40.417", "-3.704")


def test_click_on_a_world_copy_in_the_request(open_page, seeded):
    """Escenario: Pinchar en una copia del mundo."""
    web = open_page(geo={"kind": "deny"}, clock=False)
    wait_hint(web, CLICK_HINT)
    click_map(web, 40.0, 357.6)
    wait_until(web, lambda: len(nearby_calls(web)) == 1)
    query = params(nearby_calls(web)[0])
    assert (query["lat"], query["lon"]) == ("40.000", "-2.400")
    web.page.wait_for_timeout(300)
    assert "parametro_no_valido" not in web.page.content()


# --- Ubicación y punto pinchado sin guardar ---------------------------------------

def test_nothing_is_stored(open_page, seeded):
    """Escenarios: Nada guardado y Solo a la propia API."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    click_map(web, *BARCELONA)
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    wait_results(web)
    stored = web.page.evaluate("""async () => {
        const all = [];
        for (const store of [localStorage, sessionStorage])
            for (let i = 0; i < store.length; i++) all.push(store.key(i), store.getItem(store.key(i)));
        all.push(document.cookie);
        const dbs = indexedDB.databases ? await indexedDB.databases() : [];
        all.push(JSON.stringify(dbs));
        all.push(location.href);
        return all.join(' '); }""")
    for fragment in ("40.41", "-3.70", "41.38", "2.16"):
        assert fragment not in stored, fragment
    for request in web.guard.requests:
        url = request["url"]
        if any(f in url for f in ("40.41", "-3.70", "41.38", "2.16")):
            assert url.startswith(web.base + "/api/stations/nearby?"), url
    for tile in web.guard.tiles:
        assert "?" not in tile["url"]
