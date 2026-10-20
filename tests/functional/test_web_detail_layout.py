"""Ficha completa mobile first y su accesibilidad (add-station-detail, spec
`station-detail`, requisitos «Ficha completa mobile first» y «Accesibilidad de
la ficha completa»). Respuestas fijas; dispositivos de design.md D11.
"""

import re

import pytest

from tests.fixtures.web.make_web_fixtures import detail, nearby, price, station
from tests.functional.test_web_accessibility import no_page_scroll
from tests.functional.test_web_detail import (
    LOADED, LOADING, UNREACHABLE, close, open_station, opened, prices, schedule,  # noqa: F401
    status, wait_status)
from tests.functional.test_web_map import CSS, WEB, rules
from tests.functional.test_web_search import attributions_visible_and_uncovered
from tests.web_helpers import UA_LINUX_CHROME, in_visible_zone

pytestmark = pytest.mark.browser

AT_4375 = (40.416775, -3.70379)
FULL = "station_4375_full"
LONG = nearby([station("4375", 1.459, 0.04, brand="R" * 80, lat=AT_4375[0], lon=AT_4375[1])])
LONG_SCHEDULE = detail("4375", "X" * 200, [price("gasoleo-a", 1.459)])


def box(web, selector):
    return web.page.locator(selector).bounding_box()


def fully_in_window(web, selector):
    b = box(web, selector)
    width, height = web.page.evaluate("() => [innerWidth, innerHeight]")
    return b["x"] >= 0 and b["y"] >= 0 and b["x"] + b["width"] <= width + 0.5 \
        and b["y"] + b["height"] <= height + 0.5


def no_horizontal_scroll(web):
    return web.page.evaluate("""() => document.scrollingElement.scrollWidth <= innerWidth
        && document.getElementById('detail-body').scrollWidth
           <= document.getElementById('detail-body').clientWidth""")


def no_popup(web):
    return web.page.locator(".leaflet-popup").count() == 0


def loaded(web, sid="4375"):
    open_station(web, sid)
    wait_status(web, LOADED)
    web.page.wait_for_timeout(150)  # reencuadre tras el frame del estado (D10)


# --- Ficha completa mobile first ------------------------------------------------

def test_full_detail_on_iphone(opened):
    """Escenario: Ficha completa en un iPhone (cuatro tramos y cinco precios)."""
    web = opened(details={"4375": FULL})
    loaded(web)
    height = web.page.evaluate("() => innerHeight")
    assert box(web, "#detail")["height"] <= 0.7 * height + 1
    assert web.page.evaluate("""() => { const b = document.getElementById('detail-body');
        return b.scrollHeight > b.clientHeight && getComputedStyle(b).overflowY === 'auto'; }""")
    for selector in ("#detail-directions", "#detail-close"):
        assert fully_in_window(web, selector), selector
        assert box(web, selector)["y"] >= height / 2, selector
    assert no_popup(web)
    assert in_visible_zone(web, [AT_4375])


def test_full_detail_in_landscape(opened):
    """Escenario: En horizontal (750×342)."""
    web = opened(details={"4375": FULL}, device="iphone_landscape")
    loaded(web)
    assert box(web, "#detail")["height"] <= 0.7 * 342 + 1
    for selector in ("#detail-directions", "#detail-close"):
        assert fully_in_window(web, selector), selector
    assert no_page_scroll(web)
    attributions_visible_and_uncovered(web)
    assert in_visible_zone(web, [AT_4375])


def test_full_detail_on_small_phone(opened):
    """Escenario: Teléfono pequeño (320×568, rótulo de 80 caracteres)."""
    web = opened(LONG, details={"4375": FULL}, device="small", user_agent=UA_LINUX_CHROME)
    loaded(web)
    assert no_horizontal_scroll(web)
    rows = web.page.locator("#detail-prices li")
    assert rows.count() == 5
    body = box(web, "#detail-body")
    for index in range(rows.count()):
        row = rows.nth(index)
        row.scroll_into_view_if_needed()
        price_box = row.locator(".fuel-price").bounding_box()
        assert price_box["x"] >= body["x"] - 0.5
        assert price_box["x"] + price_box["width"] <= body["x"] + body["width"] + 0.5
    for selector in ("#detail-directions", "#detail-close"):
        assert fully_in_window(web, selector), selector
    attributions_visible_and_uncovered(web)


def test_long_schedule_on_small_phone(opened):
    """Escenario: Horario largo en el móvil (200 caracteres sin espacios)."""
    web = opened(details={"4375": LONG_SCHEDULE}, device="small", user_agent=UA_LINUX_CHROME)
    loaded(web)
    assert no_horizontal_scroll(web)
    line = web.page.locator("#detail-schedule li").first
    line_height = line.evaluate("e => parseFloat(getComputedStyle(e).lineHeight)")
    assert box(web, "#detail-schedule li")["height"] > 2 * line_height
    for selector in ("#detail-directions", "#detail-close"):
        assert fully_in_window(web, selector), selector


def test_full_detail_on_android(opened):
    """Escenario: Android (toques)."""
    web = opened(details={"4375": "station_4375"}, device="pixel")
    loaded(web)
    assert schedule(web) == ["L-D: 24H"] and len(prices(web)) == 2
    web.page.tap("#detail-close")
    web.page.wait_for_selector("#detail", state="hidden")


def test_full_detail_on_desktop(opened):
    """Escenario: Escritorio (panel lateral, encima de la lista)."""
    web = opened(details={"4375": FULL}, device="desktop", user_agent=UA_LINUX_CHROME)
    loaded(web)
    detail_box = box(web, "#detail")
    panel_box = box(web, "#panel")
    assert detail_box["x"] < 1 and detail_box["width"] <= 400
    assert detail_box["y"] + detail_box["height"] <= panel_box["y"] + 0.5
    assert detail_box["height"] <= 0.7 * 800 + 1
    for selector in ("#detail-directions", "#detail-close"):
        assert fully_in_window(web, selector), selector
    assert no_popup(web)


@pytest.mark.parametrize("device", ["small", "desktop"])
def test_detail_touch_targets(opened, device):
    """Escenario: Objetivos táctiles («Cómo llegar», «Cerrar» y «Reintentar»)."""
    web = opened(details={"4375": "network_error"}, device=device, user_agent=UA_LINUX_CHROME)
    open_station(web, "4375")
    wait_status(web, UNREACHABLE)
    for selector in ("#detail-directions", "#detail-close", "#detail-retry"):
        b = box(web, selector)
        assert b["width"] >= 44 and b["height"] >= 44, (selector, b)


def test_rotate_with_detail_loaded(opened):
    """Escenario: Girar con el detalle cargado."""
    web = opened(details={"4375": FULL})
    loaded(web)
    requests = len(web.guard.requests)
    for size in ({"width": 750, "height": 342}, {"width": 390, "height": 664}):
        web.page.set_viewport_size(size)
        web.page.wait_for_timeout(400)
        assert web.page.locator("#detail-info").is_visible()
        assert len(prices(web)) == 5
        for selector in ("#detail-directions", "#detail-close"):
            assert fully_in_window(web, selector), (size, selector)
    assert [r for r in web.guard.requests[requests:] if "/api/" in r["url"]] == []


def test_safe_areas():
    """Escenario: Zonas seguras (la fila de acciones va dentro del relleno de la ficha)."""
    detail_rules = rules(CSS, ".detail")
    for inset in ("bottom", "left", "right"):
        assert f"env(safe-area-inset-{inset})" in detail_rules, inset
    html = (WEB / "index.html").read_text(encoding="utf-8")
    section = html[html.index('<section id="detail"'):html.index("</section>", html.index(
        '<section id="detail"'))]
    assert 'class="detail-actions"' in section and 'id="detail-directions"' in section
    assert not re.search(r"\d(\.\d+)?vh\b", CSS)


# --- Accesibilidad de la ficha completa -----------------------------------------

def record_status(web):
    web.page.evaluate("""() => { window.__status = [];
        const s = document.getElementById('detail-status');
        new MutationObserver(() => window.__status.push(s.textContent))
            .observe(s, {childList: true, characterData: true, subtree: true}); }""")


def open_with_keyboard(web, sid):
    web.page.locator(f'.station-row[data-id="{sid}"]').focus()
    web.page.keyboard.press("Enter")
    web.page.wait_for_selector("#detail:not([hidden])")


def active_id(web):
    return web.page.evaluate("() => document.activeElement.id")


def test_status_announced_and_focus_stays(opened):
    """Escenario: Llega el detalle (foco en «Cerrar», estado corto anunciado)."""
    web = opened(details={"4375": "station_4375"}, hold={"4375"}, device="desktop",
                 user_agent=UA_LINUX_CHROME)
    open_with_keyboard(web, "4375")
    wait_status(web, LOADING)
    assert active_id(web) == "detail-close"
    zone = web.page.locator("#detail-status")
    assert zone.get_attribute("role") == "status" and zone.get_attribute("aria-live") == "polite"
    web.details["4375"].release()
    wait_status(web, LOADED)
    assert active_id(web) == "detail-close"
    assert zone.locator("li").count() == 0 and status(web) == LOADED
    assert web.page.locator("#detail-status #detail-schedule, #detail-status #detail-prices"
                            ).count() == 0


def test_loaded_without_schedule_or_prices(opened):
    """Escenario: Ficha cargada sin horario ni precios."""
    web = opened(details={"4375": "station_4375_empty"})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert web.page.locator("#detail-no-schedule").inner_text() == "Horario no disponible"
    assert web.page.locator("#detail-no-prices").inner_text() == (
        "No hay precios de esta gasolinera en la última captura")
    assert web.page.locator("#detail-status #detail-no-schedule").count() == 0


def test_reopen_loaded_detail_status(opened):
    """Escenario: Reabrir una ficha ya cargada («Ficha cargada» desde el principio)."""
    web = opened(details={"4375": "station_4375"})
    open_station(web, "4375")
    wait_status(web, LOADED)
    close(web)
    record_status(web)
    open_station(web, "4375")
    wait_status(web, LOADED)
    web.page.wait_for_timeout(100)
    assert LOADING not in web.page.evaluate("() => window.__status")
    assert len(web.details["4375"].calls) == 1


def test_error_announced(opened):
    """Escenario: Error anunciado."""
    web = opened(details={"4375": "network_error"})
    open_station(web, "4375")
    wait_status(web, UNREACHABLE)
    assert web.page.locator("[role=status][aria-live=polite]#detail-status").inner_text() == (
        UNREACHABLE)


def test_tab_order(opened):
    """Escenario: Orden con el tabulador (error con «Reintentar» activo: red caída)."""
    web = opened(details={"4375": "network_error"}, device="desktop", user_agent=UA_LINUX_CHROME)
    open_with_keyboard(web, "4375")
    wait_status(web, UNREACHABLE)
    assert active_id(web) == "detail-close"
    web.page.keyboard.press("Tab")
    assert active_id(web) == "detail-directions"
    web.page.keyboard.press("Shift+Tab")
    assert active_id(web) == "detail-close"
    web.page.keyboard.press("Shift+Tab")
    assert active_id(web) == "detail-retry"
    web.page.locator("#detail-directions").focus()
    web.page.keyboard.press("Tab")
    assert not web.page.evaluate(
        "() => document.getElementById('detail').contains(document.activeElement)")


def test_focus_after_retry(opened):
    """Escenario: Foco tras «Reintentar» (con el teclado)."""
    web = opened(details={"4375": ["network_error", "station_4375"]}, device="desktop",
                 user_agent=UA_LINUX_CHROME)
    open_with_keyboard(web, "4375")
    wait_status(web, UNREACHABLE)
    web.page.locator("#detail-retry").focus()
    web.page.keyboard.press("Enter")
    assert active_id(web) == "detail-status"
    wait_status(web, LOADED)
    assert active_id(web) == "detail-status"


@pytest.mark.parametrize(("device", "user_agent", "name"), [
    ("iphone", None, "Apple Maps"), ("pixel", None, "Google Maps"),
    ("desktop", UA_LINUX_CHROME, "OpenStreetMap")])
def test_directions_accessible_name(opened, device, user_agent, name):
    """Escenario: Nombre de «Cómo llegar»."""
    kwargs = {"user_agent": user_agent} if user_agent else {}
    web = opened(details={"4375": "station_4375"}, device=device, **kwargs)
    open_station(web, "4375")
    label = f"Cómo llegar con {name} (se abre en otra pestaña)"
    assert web.page.locator("#detail-directions").inner_text() == "Cómo llegar"
    assert web.page.get_by_role("link", name=label, exact=True).count() == 1


def test_searched_tag_is_read(opened):
    """Escenario: Destacado sin depender del color («Buscado» en el árbol de
    accesibilidad de la lista de precios)."""
    full = detail("4375", "L-D: 24H", [price("adblue", 0.899), price("gasoleo-a", 1.459),
                                       price("gasolina-95-e5", 1.529)])
    web = opened(details={"4375": full}, fuel="gasolina-95-e5")
    open_station(web, "4375")
    wait_status(web, LOADED)
    snapshot = web.page.locator("#detail-prices").aria_snapshot()
    items = [line for line in snapshot.splitlines() if line.strip().startswith("- listitem")]
    assert len(items) == 3
    assert "Gasolina 95 E5" in items[0] and "Buscado" in items[0]
    assert all("Buscado" not in item for item in items[1:])
    assert web.page.locator("#detail-prices [aria-hidden=true]").count() == 0
    assert web.page.locator("#detail-prices li").first.inner_text().endswith("Buscado")
