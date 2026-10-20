"""Accesibilidad, controles al alcance del pulgar, toques, giro y textos sin la
palabra API (map-view, tarea 10.2)."""

import re

import pytest

from tests.fixtures.web.make_web_fixtures import NEWER_CAPTURE
from tests.fixtures.web.make_web_fixtures import detail as detail_fixture
from tests.fixtures.web.make_web_fixtures import price as detail_price
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
    # lo mismo que al pulsarla: fila y marcador resaltados, marcador a la vista y su ficha
    selected = web.page.eval_on_selector_all(".station-row.selected, .price-marker.selected",
                                             "els => els.map(e => e.dataset.id)")
    assert selected == ["1001", "1001"]
    assert in_visible_zone(web, [(40.425, -3.7038)])
    assert "REPSOL" in web.page.locator("#detail-body").inner_text()


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
    """Tamaños de los objetivos que se ven (sin tocarlos: design.md D11), también
    los enlaces de acción como «Cómo llegar» (add-station-detail, tarea 0.1)."""
    return web.page.evaluate("""() => [...document.querySelectorAll(
        'select, button, .leaflet-control-zoom a, a.detail-directions')].filter(e => {
            const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden'
                && e.offsetParent !== null; })
        .map(e => [e.id || e.className || e.title, Math.round(e.getBoundingClientRect().width),
                   Math.round(e.getBoundingClientRect().height)])""")


@pytest.mark.parametrize(("device", "state"), [
    ("small", "plegada"), ("small", "desplegada"), ("small", "ficha"),
    ("desktop", "sin ficha"), ("desktop", "ficha")])
def test_touch_targets(opened, device, state):
    """Escenarios: Objetivos táctiles y Excepciones (marcadores y enlace, fuera). Con
    la ficha, también «Cómo llegar» y el «Reintentar» del detalle (aquí el detalle
    da error: el servidor de prueba no tiene base)."""
    web = opened(device=device)
    if state == "desplegada":
        web.press("#toggle")
    elif state == "ficha":
        click_marker(web, "1001")
        web.page.wait_for_selector("#detail-retry:not([hidden])")
    targets = touch_targets(web)
    names = {name for name, _, _ in targets}
    for name in ("detail-close", "detail-directions", "detail-retry"):
        assert (name in names) == (state == "ficha"), name
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
    # Con add-station-detail la ficha pide su detalle: se espera a que llegue
    # antes de contar (autorizado en su tarea 0.1).
    web.page.wait_for_function(
        "() => document.getElementById('detail-status').textContent !== ''"
        " && document.getElementById('detail-status').textContent !== 'Cargando horario…'")
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

# Estados de la ficha completa (add-station-detail, escenario «Textos sin la
# palabra API»): se abre la ficha de "1001" con esta respuesta del detalle.
_DETAIL = detail_fixture("1001", "L-D: 24H", [detail_price("gasoleo-a", 1.459)])
DETAIL_STATES = {
    "ficha cargando": None,
    "ficha correcta": _DETAIL,
    "ficha sin horario": detail_fixture("1001", None, [detail_price("gasoleo-a", 1.459)]),
    "ficha sin precios": detail_fixture("1001", "L-D: 24H", []),
    "ficha captura más reciente": detail_fixture("1001", "L-D: 24H",
                                                 [detail_price("gasoleo-a", 1.459)],
                                                 capture=NEWER_CAPTURE),
    "ficha ocupada": "busy_base_retry_5",
    "ficha consulta larga": "long_query",
    "ficha sin datos": "no_captures",
    "ficha caída": "network_error",
    "ficha no JSON": "bad_gateway_html",
    "ficha 503 no JSON": "proxy_503_html",
    "ficha no encontrada": "station_not_found",
    "ficha error interno": "internal_error",
}


@pytest.mark.parametrize("state", list(STATES) + list(DETAIL_STATES))
def test_no_api_word_in_page_texts(opened, state):
    """Escenario: Recorrido por todos los estados (también los de la ficha
    completa; cambia con add-station-detail, autorizado en su tarea 0.1)."""
    on_detail = state in DETAIL_STATES
    web = opened(geo={"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]},
                 **({} if on_detail else STATES[state]))
    if on_detail:
        web.mock("/api/stations/1001", DETAIL_STATES[state])
        web.page.locator('.price-marker[data-id="1001"] .label').tap()
        web.page.wait_for_selector("#detail:not([hidden])")
    web.page.wait_for_timeout(300)
    if web.page.locator("#toggle").is_visible():
        web.press("#toggle")
    # Fuera solo lo que llega del servidor: filas, datos de la búsqueda en la
    # ficha, tramos del horario y nombres y precios de los combustibles.
    own = web.page.evaluate("""() => {
        const clone = document.body.cloneNode(true);
        clone.querySelectorAll('.station-row, #cheapest, #detail-head, #detail-schedule li, '
            + '#detail-prices .fuel-name, #detail-prices .fuel-price, script')
            .forEach(e => e.remove());
        const texts = [clone.innerText || clone.textContent];
        document.querySelectorAll('[title], [aria-label]').forEach(e =>
            texts.push(e.getAttribute('title') || '', e.getAttribute('aria-label') || ''));
        return texts.join(' '); }""")
    own = re.sub(r"Detalle:.*", "", own)
    assert not re.search(r"\bapi\b", own, re.IGNORECASE), own
    assert text(web, "#message") is None or "API" not in text(web, "#message").split("Detalle:")[0]


# --- Refuerzos de la revisión de cobertura -------------------------------------------

@pytest.mark.parametrize(("nearby", "expected"), [
    ("internal_error", "El servidor ha dado un error. Inténtalo más tarde."),
    ("busy_base_retry_5", "El servidor está ocupado; inténtalo en unos segundos"),
])
def test_error_is_announced(opened, nearby, expected):
    """Escenario: Avisos anunciados (un error): el mensaje está en la zona que
    anuncian los lectores de pantalla."""
    web = opened(nearby=nearby, geo={"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]})
    web.page.wait_for_selector("#message:not([hidden])")
    announced = web.page.locator("[aria-live=polite] #message, [role=status] #message, "
                                 "[role=alert] #message")
    assert announced.count() == 1
    assert announced.inner_text() == expected


@pytest.mark.parametrize("device", ["small", "desktop"])
def test_touch_target_of_retry(opened, device):
    """Escenario: Objetivos táctiles («Reintentar», que solo se ve con un error)."""
    web = opened(nearby="internal_error", device=device,
                 geo={"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]})
    web.page.wait_for_selector("#retry:not([hidden])")
    targets = touch_targets(web)
    assert any(name == "retry" for name, _, _ in targets)
    for name, width, height in targets:
        assert width >= 44 and height >= 44, (name, width, height)


@pytest.mark.parametrize("device", ["small", "desktop"])
def test_every_marker_has_a_measured_row(opened, device):
    """Escenario: Excepciones: cada gasolinera de un marcador tiene su fila en la
    lista, y la fila mide al menos 44×44 px."""
    web = opened(nearby="nearby_40", device=device)
    if device == "small":
        web.press("#toggle")
        web.page.wait_for_selector("#panel.expanded")
    markers = web.page.eval_on_selector_all(".price-marker", "els => els.map(e => e.dataset.id)")
    rows = web.page.eval_on_selector_all(".station-row", """els => els.map(e => {
        const r = e.getBoundingClientRect(); return [e.dataset.id, r.width, r.height]; })""")
    assert len(markers) == 40 and sorted(markers) == sorted(r[0] for r in rows)
    for station_id, width, height in rows:
        assert width >= 44 and height >= 44, (station_id, width, height)
