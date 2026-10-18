"""Combustibles, radio y preferencias (map-view, tarea 6.2): «Selector de
combustible», «Selector de radio» y «Recordar la última elección».
«Cambiar a Hidrogeno» y «Almacenamiento bloqueado» van en test_web_search.py;
«Ningún combustible con estaciones» y «Lista de combustibles que no se puede
usar», en test_web_errors.py."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.web_helpers import (CLICK_HINT, MADRID, circle_in_view, click_map, has_circle,
                               nearby_calls, seed_madrid, text, wait_until)

pytestmark = pytest.mark.browser

GRANT = {"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}
DENY = {"kind": "deny"}
KEY = "precios-gasolineras.preferencias"


@pytest.fixture
def seeded(web_db):
    seed_madrid(web_db)


def params(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def options(web):
    return web.page.eval_on_selector_all("#fuel option", "els => els.map(e => e.textContent)")


def selected(web, selector):
    return web.page.eval_on_selector(selector, "e => e.value")


def store(prefs):
    return f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(json.dumps(prefs))})"


# --- Selector de combustible ---------------------------------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_fuel_options(open_page, device):
    """Escenario: Opciones del selector."""
    web = open_page(device=device, geo=DENY, clock=False,
                    before_goto=lambda w: w.mock("/api/fuels", "fuels_ok"))
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert options(web) == ["Gasoleo A (€/l)", "Gasolina 95 E5 (€/l)", "Adblue (€/l)",
                            "Hidrogeno (€/kg)"]
    assert selected(web, "#fuel") == "gasoleo-a"


def test_change_fuel_without_point(open_page, seeded):
    """Escenario: Cambiar sin punto (combustible)."""
    web = open_page(geo=DENY, clock=False)
    web.page.wait_for_selector("#fuel:not([disabled])")
    web.page.select_option("#fuel", "gasolina-95-e5")
    web.page.wait_for_timeout(500)
    assert nearby_calls(web) == []


def test_invalid_fuel_items(open_page):
    """Escenario: Elementos no válidos."""
    web = open_page(geo=DENY, clock=False,
                    before_goto=lambda w: w.mock("/api/fuels", "fuels_invalid_items"))
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert options(web) == ["Gasoleo A (€/l)"]


# --- Selector de radio -------------------------------------------------------------

def test_radius_options(open_page, seeded):
    """Escenario: Opciones del radio."""
    web = open_page(geo=DENY, clock=False)
    web.page.wait_for_selector("#fuel:not([disabled])")
    labels = web.page.eval_on_selector_all("#radius option", "els => els.map(e => e.textContent)")
    assert labels == ["5 km", "10 km", "25 km", "50 km"]
    assert selected(web, "#radius") == "10"


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_change_to_50_km(open_page, seeded, device):
    """Escenario: Cambiar a 50 km."""
    web = open_page(device=device, geo=GRANT, clock=False)
    web.page.wait_for_selector("#count:not([hidden])")
    web.page.select_option("#radius", "50")
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    assert params(nearby_calls(web)[-1])["radius_km"] == "50"
    web.page.wait_for_selector("#count:not([hidden])")
    web.page.wait_for_timeout(200)
    radius = web.page.evaluate("""() => { let r = null;
        window.__mapView.map.leaflet.eachLayer(l => { if (l instanceof L.Circle) r = l.getRadius(); });
        return r; }""")
    assert radius == 50000
    assert circle_in_view(web)


def test_change_radius_without_point(open_page, seeded):
    """Escenario: Cambiar sin punto (radio)."""
    web = open_page(geo=DENY, clock=False)
    wait_until(web, lambda: text(web, "#hint") == CLICK_HINT)
    web.page.select_option("#radius", "25")
    web.page.wait_for_timeout(500)
    assert nearby_calls(web) == [] and not has_circle(web)
    click_map(web, *MADRID)
    wait_until(web, lambda: len(nearby_calls(web)) == 1)
    assert params(nearby_calls(web)[0])["radius_km"] == "25"


# --- Recordar la última elección -------------------------------------------------------

def test_open_again(open_page, seeded):
    """Escenario: Volver a abrir."""
    web = open_page(geo=GRANT, clock=False)
    web.page.wait_for_selector("#count:not([hidden])")
    web.page.select_option("#fuel", "gasolina-95-e5")
    web.page.select_option("#radius", "25")
    web.page.wait_for_timeout(300)
    web.page.reload()
    web.page.wait_for_selector("#fuel:not([disabled])")
    wait_until(web, lambda: len(nearby_calls(web)) >= 3)
    assert selected(web, "#fuel") == "gasolina-95-e5"
    assert selected(web, "#radius") == "25"
    first = params(nearby_calls(web)[-1])
    assert (first["fuel"], first["radius_km"]) == ("gasolina-95-e5", "25")


def test_saved_fuel_no_longer_sold(open_page):
    """Escenario: Combustible guardado que ya no se vende."""
    web = open_page(geo=DENY, clock=False, init_scripts=[store({"fuel": "hidrogeno", "radius": 25})],
                    before_goto=lambda w: w.mock("/api/fuels", "fuels_hidrogeno_zero"))
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert selected(web, "#fuel") == "gasoleo-a"
    assert selected(web, "#radius") == "25"


def test_invalid_saved_values(open_page, seeded):
    """Escenario: Valores guardados no válidos."""
    web = open_page(geo=DENY, clock=False, init_scripts=[store({"fuel": "diesel", "radius": 7})])
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert (selected(web, "#fuel"), selected(web, "#radius")) == ("gasoleo-a", "10")


def test_changing_only_the_radius_keeps_the_saved_fuel(open_page, web_server):
    """Pendiente 4 (design.md D9): con `hidrogeno` guardado y sin estaciones, se
    cambia solo el radio, y al volver a abrir con Hidrogeno a la venta sale
    elegido Hidrogeno."""
    once = ("if (!sessionStorage.getItem('sembrado')) { sessionStorage.setItem('sembrado', '1'); "
            + store({"fuel": "hidrogeno"}) + "; }")
    web = open_page(geo=DENY, clock=False, init_scripts=[once],
                    before_goto=lambda w: w.mock("/api/fuels", "fuels_hidrogeno_zero"))
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert selected(web, "#fuel") == "gasoleo-a"
    web.page.select_option("#radius", "25")
    web.page.wait_for_timeout(200)
    saved = json.loads(web.page.evaluate(f"() => localStorage.getItem({json.dumps(KEY)})"))
    assert saved == {"fuel": "hidrogeno", "radius": 25}
    web.page.unroute_all()
    web.mock("/api/fuels", "fuels_ok")
    web.page.reload()
    web.page.wait_for_selector("#fuel:not([disabled])")
    assert selected(web, "#fuel") == "hidrogeno"
    assert selected(web, "#radius") == "25"
    assert web.console_errors == []
