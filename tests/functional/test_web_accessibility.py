"""Accesibilidad, controles al alcance del pulgar, toques, giro y textos sin la
palabra API (map-view, tarea 10.2)."""

import re

import pytest

from tests.web_helpers import MADRID, in_visible_zone, nearby_calls, text, wait_until

pytestmark = pytest.mark.browser

GRANT = {"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}


@pytest.fixture
def opened(open_page):
    def open_(nearby="nearby_madrid", device="iphone", geo=GRANT, health="health_ok", **kwargs):
        def mocks(web):
            web.mock("/api/fuels", "fuels_ok")
            web.mock("/api/health", health)
            web.mock("/api/stations/nearby", nearby)
        web = open_page(device=device, geo=geo, clock=False, before_goto=mocks, **kwargs)
        if geo is GRANT:
            web.page.wait_for_selector("#count:not([hidden])")
        return web
    return open_


def active_id(web):
    return web.page.evaluate("() => document.activeElement.id || document.activeElement.dataset.id")


def click_marker(web, station_id):
    """Pulsa un marcador aunque una hoja lo tape (como lo haría el usuario al verlo)."""
    web.page.evaluate(f"""() => document.querySelector('.price-marker[data-id="{station_id}"] .label')
        .dispatchEvent(new MouseEvent('click', {{bubbles: true}}))""")
    web.page.wait_for_selector("#detail:not([hidden])")


# --- Accesibilidad básica ----------------------------------------------------------

def test_select_labels(opened):
    """Escenario: Etiquetas de los selectores."""
    web = opened()
    for select, label in (("fuel", "Combustible"), ("radius", "Radio")):
        locator = web.page.locator(f'label[for="{select}"]')
        assert locator.inner_text() == label and locator.is_visible()
    assert web.page.get_by_label("Combustible").get_attribute("id") == "fuel"


def test_list_with_keyboard(opened):
    """Escenario: Lista con el teclado (escritorio)."""
    web = opened(device="desktop")
    for _ in range(60):
        web.page.keyboard.press("Tab")
        if active_id(web) == "1001":
            break
    assert active_id(web) == "1001"
    web.page.keyboard.press("Enter")
    web.page.wait_for_selector("#detail:not([hidden])")
    assert active_id(web) == "detail-close"


def test_sheet_button(opened):
    """Escenario: Botón de la hoja inferior (también con el teclado)."""
    web = opened()
    toggle = web.page.locator("#toggle")
    assert (toggle.inner_text(), toggle.get_attribute("aria-expanded")) == ("Ver lista", "false")
    web.page.focus("#toggle")
    web.page.keyboard.press("Enter")
    assert (toggle.inner_text(), toggle.get_attribute("aria-expanded")) == ("Ocultar lista", "true")


@pytest.mark.parametrize("device", ["iphone", "desktop"])
def test_focus_on_close_from_row(opened, device):
    """Escenario: Foco al cerrar (abierta desde la fila)."""
    web = opened(device=device)
    if device == "iphone":
        web.press("#toggle")
    web.press('.station-row[data-id="1001"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.keyboard.press("Escape")
    web.page.wait_for_selector("#detail", state="hidden")
    assert active_id(web) == "1001"


@pytest.mark.parametrize(("device", "expanded", "expected"), [
    ("desktop", False, "1001"), ("iphone", True, "1001"), ("iphone", False, "toggle")])
def test_focus_on_close_from_marker(opened, device, expanded, expected):
    """Escenario: Foco al cerrar una ficha abierta desde un marcador."""
    web = opened(device=device)
    if expanded:
        web.press("#toggle")
    click_marker(web, "1001")
    web.press("#detail-close")
    web.page.wait_for_selector("#detail", state="hidden")
    assert active_id(web) == expected


def test_focus_on_close_from_cheapest(opened):
    """Escenario: Foco al cerrar una ficha abierta desde la más barata."""
    web = opened()
    web.press("#cheapest")
    web.page.wait_for_selector("#detail:not([hidden])")
    web.press("#detail-close")
    web.page.wait_for_selector("#detail", state="hidden")
    assert active_id(web) == "cheapest"


def test_announced_notices(opened):
    """Escenario: Avisos anunciados (recuento, error y desactualizados)."""
    web = opened(health="health_stale")
    live = "#status[aria-live=polite]"
    assert web.page.locator(f"{live} #count").inner_text() == "3 gasolineras encontradas"
    assert web.page.locator(f"{live} #message").count() == 1
    web.page.wait_for_selector("#stale:not([hidden])")
    assert web.page.get_attribute("#stale", "role") == "status"


def luminance(rgb):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rgb(css):
    return tuple(int(x) for x in re.findall(r"\d+", css)[:3])


def contrast(a, b):
    la, lb = sorted((luminance(rgb(a)), luminance(rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("selected", [False, True])
def test_marker_contrast(opened, selected):
    """Escenario: Contraste de los marcadores (los cuatro colores, también resaltados)."""
    web = opened()
    colours = web.page.evaluate(f"""() => ['cheap', 'mid', 'expensive', 'single'].map(t => {{
        const box = document.createElement('div');
        box.className = 'price-marker{' selected' if selected else ''}';
        const label = document.createElement('span');
        label.className = 'label tier-' + t; label.textContent = '1,459';
        box.append(label); document.querySelector('.leaflet-marker-pane').append(box);
        const s = getComputedStyle(label); return [t, s.color, s.backgroundColor]; }})""")
    for tier, colour, background in colours:
        assert contrast(colour, background) >= 4.5, tier


# --- Controles al alcance del pulgar --------------------------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel", "iphone_landscape"])
def test_controls_in_the_lower_half(opened, device):
    """Escenarios: Controles en vertical y Controles en horizontal."""
    web = opened(device=device)
    height = web.page.evaluate("() => innerHeight")
    for selector in ("#fuel", "#radius", "#back-to-location"):
        box = web.page.locator(selector).bounding_box()
        assert box["y"] >= height / 2 and box["y"] + box["height"] <= height, selector


def touch_targets(web):
    """Tamaños de los objetivos que se ven (sin tocarlos: design.md D11)."""
    return web.page.evaluate("""() => [...document.querySelectorAll(
        'select, button, .leaflet-control-zoom a')].filter(e => {
            const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'
                && e.offsetParent !== null; })
        .map(e => [e.id || e.className || e.title, Math.round(e.getBoundingClientRect().width),
                   Math.round(e.getBoundingClientRect().height)])""")


@pytest.mark.parametrize(("device", "state"), [
    ("small", "plegada"), ("small", "desplegada"), ("small", "ficha"),
    ("desktop", "sin ficha"), ("desktop", "ficha")])
def test_touch_targets(opened, device, state):
    """Escenarios: Objetivos táctiles y Excepciones (marcadores y enlace, fuera)."""
    web = opened(device=device)
    if state == "desplegada":
        web.press("#toggle")
    elif state == "ficha":
        click_marker(web, "1001")
    targets = touch_targets(web)
    assert any(name == "detail-close" for name, _, _ in targets) == (state == "ficha")
    for name, width, height in targets:
        assert width >= 44 and height >= 44, (name, width, height)


# --- Sin depender de hover: todo con toques ------------------------------------------

def test_everything_with_taps(opened):
    """Escenario: Todo con toques (Android táctil, sin ratón)."""
    web = opened(device="pixel", geo={"kind": "deny"})
    web.page.wait_for_selector("#fuel:not([disabled])")
    web.page.wait_for_load_state("networkidle")
    point = web.page.evaluate("""() => { const m = window.__mapView.map.leaflet;
        const p = m.latLngToContainerPoint([40.4168, -3.7038]);
        const r = document.getElementById('map').getBoundingClientRect();
        return [p.x + r.left, p.y + r.top]; }""")
    web.page.touchscreen.tap(*point)
    web.page.wait_for_selector("#count:not([hidden])")
    web.page.tap("#toggle")
    web.page.wait_for_selector("#panel.expanded")
    web.page.tap('.station-row[data-id="1001"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.tap("#detail-close")
    web.page.wait_for_selector("#detail", state="hidden")
    web.page.tap("#toggle")
    web.page.locator('.price-marker[data-id="1002"] .label').tap()
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.tap("#detail-close")
    web.page.select_option("#radius", "25")
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    assert web.console_errors == []


# --- Vertical y horizontal ------------------------------------------------------------

def no_page_scroll(web):
    return web.page.evaluate("""() => document.scrollingElement.scrollHeight <= innerHeight
        && document.scrollingElement.scrollWidth <= innerWidth""")


def test_rotate_with_detail_open(opened):
    """Escenario: Girar con la ficha abierta."""
    web = opened()
    web.page.locator('.price-marker[data-id="1001"] .label').tap()
    web.page.wait_for_selector("#detail:not([hidden])")
    requests = len(web.guard.requests)
    for size in ({"width": 750, "height": 342}, {"width": 390, "height": 664}):
        web.page.set_viewport_size(size)
        web.page.wait_for_timeout(400)
        detail = web.page.locator("#detail").bounding_box()
        close = web.page.locator("#detail-close").bounding_box()
        assert detail["y"] >= 0 and detail["y"] + detail["height"] <= size["height"] + 0.5
        assert close["y"] >= detail["y"] and close["y"] + close["height"] <= size["height"] + 0.5
        assert no_page_scroll(web)
        assert in_visible_zone(web, [(40.425, -3.7038)]), size
    api = [r for r in web.guard.requests[requests:] if "/api/" in r["url"]]
    assert api == []


def test_rotate_with_list_expanded(opened):
    """Escenario: Girar con la lista desplegada."""
    web = opened(nearby="nearby_40")
    web.press("#toggle")
    web.page.set_viewport_size({"width": 750, "height": 342})
    web.page.wait_for_timeout(400)
    assert "expanded" in web.page.get_attribute("#panel", "class")
    panel = web.page.locator("#panel").bounding_box()
    assert panel["height"] <= 0.7 * 342 + 1
    assert no_page_scroll(web)
    scrolls = web.page.evaluate("""() => { const b = document.getElementById('panel-body');
        return b.scrollHeight > b.clientHeight; }""")
    assert scrolls


# --- Textos de la página sin la palabra API ------------------------------------------

STATES = {
    "resultados": dict(nearby="nearby_madrid"),
    "sin resultados": dict(nearby="nearby_empty"),
    "fuera de España": dict(nearby="outside_spain"),
    "ocupado": dict(nearby="busy_base_retry_5"),
    "sin datos": dict(nearby="no_captures"),
    "caído": dict(nearby="network_error"),
    "respuesta inesperada": dict(nearby="bad_gateway_html"),
    "desactualizados": dict(health="health_stale"),
}


@pytest.mark.parametrize("state", list(STATES))
def test_no_api_word_in_page_texts(opened, state):
    """Escenario: Recorrido por todos los estados."""
    web = opened(geo={"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}, **STATES[state])
    web.page.wait_for_timeout(300)
    if web.page.locator("#toggle").is_visible():
        web.press("#toggle")
    own = web.page.evaluate("""() => {
        const clone = document.body.cloneNode(true);
        clone.querySelectorAll('.station-row, #cheapest, #detail-body, script').forEach(e => e.remove());
        const texts = [clone.innerText || clone.textContent];
        document.querySelectorAll('[title], [aria-label]').forEach(e =>
            texts.push(e.getAttribute('title') || '', e.getAttribute('aria-label') || ''));
        return texts.join(' '); }""")
    own = re.sub(r"Detalle:.*", "", own)
    assert not re.search(r"\bapi\b", own, re.IGNORECASE), own
    assert text(web, "#message") is None or "API" not in text(web, "#message").split("Detalle:")[0]
