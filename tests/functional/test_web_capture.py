"""«Captura de los precios en hora de Madrid» y «Aviso de datos
desactualizados» (map-view, tarea 8.2), en el iPhone (WebKit)."""

import pytest

from tests.web_helpers import MADRID, text, wait_until

pytestmark = pytest.mark.browser

GRANT = {"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}
STALE = ("Los precios pueden no estar al día: la última captura es del 16/10/2026 a las 09:26 "
         "(hora de Madrid)")


def open_with(open_page, nearby="nearby_madrid", health="health_ok", **kwargs):
    def mocks(web):
        web.mock("/api/fuels", "fuels_ok")
        web.mock("/api/health", health)
        web.mock("/api/stations/nearby", nearby)
    web = open_page(geo=GRANT, clock=False, before_goto=mocks, **kwargs)
    web.page.wait_for_selector("#count:not([hidden])")
    web.press("#toggle")
    return web


def test_summer_time_from_new_york(open_page):
    """Escenario: Horario de verano."""
    web = open_with(open_page, timezone_id="America/New_York")
    assert text(web, "#capture") == "Precios de la captura del 16/10/2026 a las 09:26 (hora de Madrid)"


def test_winter_time_from_utc(open_page):
    """Escenario: Horario de invierno."""
    web = open_with(open_page, nearby="nearby_winter", timezone_id="UTC")
    assert text(web, "#capture") == "Precios de la captura del 02/11/2026 a las 06:17 (hora de Madrid)"


@pytest.mark.parametrize("nearby", ["nearby_bad_capture", "nearby_no_capture"])
def test_date_that_cannot_be_understood(open_page, nearby):
    """Escenario: Fecha que no se entiende."""
    web = open_with(open_page, nearby=nearby)
    assert text(web, "#capture") == "Fecha de la captura desconocida"
    assert web.page.locator(".station-row").count() == 1


def test_stale_data(open_page):
    """Escenario: Datos desactualizados."""
    web = open_with(open_page, health="health_stale")
    wait_until(web, lambda: text(web, "#stale") == STALE)
    assert web.page.get_attribute("#stale", "role") == "status"
    assert web.page.locator(".station-row").count() == 3


@pytest.mark.parametrize("health", ["health_ok", "health_invalid_config"])
def test_data_up_to_date(open_page, health):
    """Escenario: Datos al día."""
    web = open_with(open_page, health=health)
    web.page.wait_for_timeout(300)
    assert text(web, "#stale") is None


@pytest.mark.parametrize("health", ["health_busy", None])
def test_health_that_fails(open_page, health):
    """Escenario: Salud que falla (503 o sin respuesta), sin repetir la petición."""
    web = open_with(open_page, health=health)
    web.page.wait_for_timeout(500)
    assert text(web, "#stale") is None
    assert web.page.locator(".station-row").count() == 3
    calls = [r for r in web.guard.requests if r["url"].endswith("/api/health")]
    assert len(calls) == 1
