"""Escenarios de «Cómo llegar» (add-station-detail, spec `station-detail`):
enlace según el dispositivo y sin la ubicación de quien busca. Nunca se abre
ninguna aplicación de mapas: las pulsaciones se interceptan y se cancelan
(design.md D11).
"""

import re

import pytest

from tests.fixtures.web.make_web_fixtures import nearby, station
from tests.functional.test_web_detail import (
    BUSY, LOADING, UNREACHABLE, close, open_station, opened, wait_status)  # noqa: F401
from tests.web_helpers import UA_IPADOS, UA_LINUX_CHROME, UA_MAC_SAFARI

pytestmark = pytest.mark.browser

APPLE_1003 = "https://maps.apple.com/?daddr=40.44,-3.73"
GOOGLE_1003 = "https://www.google.com/maps/dir/?api=1&destination=40.44,-3.73"
OSM_1003 = "https://www.openstreetmap.org/directions?route=%3B40.44%2C-3.73"
APPLE_4375 = "https://maps.apple.com/?daddr=40.416775,-3.70379"
BOTH = nearby([station("1003", 1.399, 3.4, brand="CEPSA", lat=40.44, lon=-3.73),
               station("4375", 1.459, 0.04, lat=40.416775, lon=-3.70379)])


def link(web):
    return web.page.locator("#detail-directions")


def href(web):
    return link(web).get_attribute("href")


# --- Enlace «Cómo llegar» según el dispositivo ------------------------------------

@pytest.mark.parametrize(("device", "user_agent", "expected"), [
    ("iphone", None, APPLE_1003),
    ("iphone_landscape", None, APPLE_1003),
    ("desktop", UA_MAC_SAFARI, APPLE_1003),
    ("desktop", UA_IPADOS, APPLE_1003),
    ("pixel", None, GOOGLE_1003),
    ("small", UA_LINUX_CHROME, OSM_1003),
    ("desktop", UA_LINUX_CHROME, OSM_1003),
], ids=["iphone", "iphone-horizontal", "mac", "ipados", "android", "otros-320", "otros-escritorio"])
def test_directions_by_device(opened, device, user_agent, expected):
    """Escenarios: iPhone, Mac, iPad que se presenta como Mac, Android y Otros
    dispositivos."""
    kwargs = {"user_agent": user_agent} if user_agent else {}
    web = opened("nearby_one", details={"1003": "station_1003"}, device=device, **kwargs)
    open_station(web, "1003")
    assert href(web) == expected
    assert link(web).inner_text() == "Cómo llegar"


def test_many_decimals(opened):
    """Escenario: Coordenadas con muchos decimales."""
    web = opened(details={"4375": "station_4375"})
    open_station(web, "4375")
    assert href(web) == APPLE_4375


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_new_tab_and_no_keys(opened, device):
    """Escenario: Otra pestaña y sin claves."""
    web = opened("nearby_madrid", details={"1003": "station_1003"}, device=device)
    open_station(web, "1003")
    assert link(web).evaluate("a => a.tagName") == "A"
    assert link(web).get_attribute("target") == "_blank"
    assert link(web).get_attribute("rel") == "noopener noreferrer"
    assert not re.search(r"key|token|account|client|sig|auth", href(web), re.IGNORECASE)


@pytest.mark.parametrize("state", ["cargando", "fallido"])
def test_available_while_detail_loads_or_fails(opened, state):
    """Escenario: Disponible aunque falle el detalle."""
    spec = "station_1003" if state == "cargando" else "network_error"
    web = opened("nearby_madrid", details={"1003": spec}, hold={"1003"} if state == "cargando"
                 else ())
    open_station(web, "1003")
    wait_status(web, LOADING if state == "cargando" else UNREACHABLE)
    assert link(web).is_visible()
    assert href(web) == APPLE_1003


def test_link_changes_with_detail(opened):
    """Escenario: El enlace cambia con la ficha."""
    web = opened(BOTH, details={"1003": "station_1003", "4375": "station_4375"})
    open_station(web, "1003")
    assert href(web) == APPLE_1003
    open_station(web, "4375")
    assert href(web) == APPLE_4375


# --- «Cómo llegar» sin la ubicación de quien busca ---------------------------------

def test_without_browser_location(opened):
    """Escenario: Sin la ubicación."""
    web = opened("nearby_madrid", details={"1003": "station_1003"})
    open_station(web, "1003")
    url = href(web)
    assert "40.44,-3.73" in url
    for leak in ("40.41", "-3.70", "40.417", "-3.704"):
        assert leak not in url


def test_without_clicked_point(opened):
    """Escenario: Sin el punto pinchado."""
    from tests.web_helpers import BARCELONA, click_map

    web = opened("nearby_barcelona", details={"8001": "station_1001"},
                 geo={"kind": "deny"})
    web.page.wait_for_selector("#fuel:not([disabled])")
    click_map(web, *BARCELONA)
    web.page.wait_for_selector("#count:not([hidden])")
    open_station(web, "8001")
    url = href(web)
    assert "41.39,2.17" in url
    for leak in ("41.387", "41.38", "2.169", "2.16"):
        assert leak not in url


def press_directions(web):
    """Pulsa «Cómo llegar» y espera la pestaña nueva (navegación interceptada)."""
    with web.page.context.expect_page(timeout=5_000) as popup:
        web.press("#detail-directions")
    return popup.value


def test_press_directions_on_iphone_attributes(opened):
    """Escenario: Pulsar «Cómo llegar», plan B en el iPhone (nota del escenario).

    El iPhone emulado en WebKit no abre ninguna pestaña nueva al tocar ni al
    hacer clic en un enlace `target="_blank"` (comprobado al implementar), así
    que aquí se comprueban solo los atributos del enlace; la pulsación con la
    misma dirección de Apple Maps se prueba en escritorio con agente de Mac.
    """
    web = opened("nearby_one", details={"1003": "station_1003"})
    open_station(web, "1003")
    assert href(web) == APPLE_1003
    assert link(web).get_attribute("target") == "_blank"
    assert link(web).get_attribute("rel") == "noopener noreferrer"


def test_press_directions(opened):
    """Escenario: Pulsar «Cómo llegar» (escritorio en Chromium con agente de Safari en
    Mac, misma dirección de Apple Maps; navegación interceptada y cancelada)."""
    web = opened("nearby_one", details={"1003": "station_1003"}, device="desktop",
                 user_agent=UA_MAC_SAFARI)
    seen = web.intercept_directions()
    open_station(web, "1003")
    url_before = web.page.url
    press_directions(web)
    web.page.wait_for_timeout(200)
    assert [s["url"] for s in seen] == [APPLE_1003]
    assert "referer" not in seen[0]["headers"]
    assert web.page.url == url_before
    assert web.page.locator("#detail").is_visible()
    assert not web.guard.blocked


def test_no_requests_until_pressed(opened):
    """Escenario: Sin peticiones hasta pulsar."""
    web = opened(BOTH, details={"1003": "station_1003", "4375": "station_4375"})
    for sid in ("1003", "4375", "1003"):
        open_station(web, sid)
        close(web)
    hosts = ("maps.apple.com", "www.google.com", "www.openstreetmap.org")
    assert not [r["url"] for r in web.guard.requests if any(h in r["url"] for h in hosts)]
    assert not web.guard.blocked
