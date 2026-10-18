"""Página base sin resultados (map-view, tarea 4.2): recursos y teselas,
atribuciones, licencia de Leaflet, diseño mobile first, alto de la pantalla y
zonas seguras, y hojas de estilo sin hover.

Por defecto en el iPhone 13 con WebKit; los demás dispositivos se piden con
`device=` (tests/web_fixtures.py, design.md D11)."""

import re

import pytest

from tests.helpers import REPO_ROOT
from tests.web_fixtures import TILE_URL

pytestmark = pytest.mark.browser

WEB = REPO_ROOT / "web"
# Hoja de estilos sin comentarios, para buscar en sus reglas.
CSS = re.sub(r"/\*.*?\*/", "", (WEB / "styles.css").read_text(encoding="utf-8"), flags=re.S)
MINISTRY = ("Ministerio de Industria, Comercio y Turismo - Precios de carburantes "
            "en estaciones de servicio")
DENY = {"kind": "deny"}


def settle(web):
    """Espera a que el mapa termine de pedir teselas."""
    web.page.wait_for_load_state("networkidle")
    web.page.wait_for_timeout(300)


def box(web, selector):
    return web.page.locator(selector).bounding_box()


# --- Sin recursos de terceros salvo las teselas --------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel", "desktop"])
def test_only_own_origin_and_tiles(open_page, device):
    web = open_page(device=device, geo=DENY, clock=False)
    settle(web)
    for request in web.guard.requests:
        url = request["url"]
        assert url.startswith(web.base + "/") or TILE_URL.match(url), url
    assert web.guard.tiles, "el mapa no pidió teselas"


def test_leaflet_license_and_single_copy():
    """Escenario: Licencia de Leaflet."""
    folder = WEB / "vendor" / "leaflet"
    assert "BSD 2-Clause License" in (folder / "LICENSE").read_text()
    version = (folder / "VERSION").read_text()
    assert "Leaflet 1.9.4" in version and "sha512-" in version
    copies = [p for p in WEB.rglob("*leaflet*.js")]
    assert copies == [folder / "leaflet.js"]
    html = (WEB / "index.html").read_text()
    assert html.count('<script src="vendor/leaflet/leaflet.js"></script>') == 1
    assert "unpkg" not in html and "cdn" not in html.lower()


# --- Teselas de OpenStreetMap ---------------------------------------------------

def test_maximum_zoom(open_page):
    """Escenario: Zoom máximo."""
    web = open_page(geo=DENY, clock=False)
    settle(web)
    zoom = web.page.evaluate("""() => { const m = window.__mapView.map.leaflet;
        m.setView([40.4168, -3.7038], 25, {animate: false}); return m.getZoom(); }""")
    assert zoom == 19
    settle(web)
    assert max(int(TILE_URL.match(t["url"]).group(1)) for t in web.guard.tiles) <= 19


def test_only_what_is_seen(open_page):
    """Escenario: Solo lo que se ve (1280×800, sin ubicación)."""
    web = open_page(device="desktop", geo=DENY, clock=False)
    settle(web)
    zooms = {TILE_URL.match(t["url"]).group(1) for t in web.guard.tiles}
    assert len(zooms) == 1, zooms
    assert 0 < len(web.guard.tiles) <= 40


@pytest.mark.parametrize("device", ["iphone", "desktop"])
def test_tile_referer(open_page, device):
    """Escenario: Referer de las teselas."""
    web = open_page(device=device, geo=DENY, clock=False)
    settle(web)
    assert web.guard.tiles
    for tile in web.guard.tiles:
        assert tile["headers"].get("referer") == web.base + "/"
    policy = web.page.evaluate(
        "() => document.querySelector('meta[name=referrer]')?.content || ''")
    assert policy != "no-referrer"


def test_no_own_tile_store(open_page):
    """Escenario: Sin almacén propio de teselas."""
    web = open_page(geo=DENY, clock=False)
    settle(web)
    stores = web.page.evaluate("""async () => ({
        workers: navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0,
        caches: window.caches ? (await caches.keys()).length : 0 })""")
    assert stores == {"workers": 0, "caches": 0}


# --- Atribuciones visibles --------------------------------------------------------

def attribution_box(web):
    return web.page.locator(".leaflet-control-attribution")


def test_attributions_with_api_down(open_page):
    """Escenario: Atribuciones con la API caída."""
    def down(web):
        web.mock("/api/fuels", "network_error")
        web.mock("/api/health", "network_error")
    web = open_page(geo=DENY, before_goto=down, clock=False)
    web.page.wait_for_selector("#message:not([hidden])")
    text = attribution_box(web).inner_text()
    assert MINISTRY in text and "© OpenStreetMap contributors" in text
    link = web.page.locator(".leaflet-control-attribution a", has_text="OpenStreetMap contributors")
    assert link.get_attribute("href") == "https://www.openstreetmap.org/copyright"
    assert attribution_box(web).is_visible()


def test_attributions_on_small_phone(open_page):
    """Escenario: Atribuciones en el móvil (320×568, hoja plegada)."""
    web = open_page(device="small", geo=DENY, clock=False)
    settle(web)
    attribution = box(web, ".leaflet-control-attribution")
    zoom = box(web, ".leaflet-control-zoom")
    panel = box(web, "#panel")
    assert attribution["x"] >= 0 and attribution["x"] + attribution["width"] <= 320
    assert attribution["y"] >= 0
    assert attribution["y"] + attribution["height"] <= zoom["y"]  # no tapa el zoom
    assert attribution["y"] + attribution["height"] <= panel["y"]  # la hoja no la tapa
    assert MINISTRY in attribution_box(web).inner_text()


# --- Diseño mobile first -----------------------------------------------------------

def media_queries(css):
    return re.findall(r"@media\s*\(([^)]*)\)", css)


def test_stylesheets_are_mobile_first():
    """Escenario: Hojas de estilo (solo min-width)."""
    queries = media_queries(CSS)
    widths = [q for q in queries if "width" in q]
    assert widths and all(q.replace(" ", "").startswith("min-width") for q in widths), widths
    assert "max-width" not in "".join(queries)


@pytest.mark.parametrize(("device", "viewport", "layout"), [
    ("iphone", None, "fixed"),
    ("iphone_landscape", None, "fixed"),
    ("pixel", {"width": 820, "height": 1180}, "fixed"),
    ("small", None, "fixed"),
    ("desktop", None, "static"),
])
def test_layout_by_window_size(open_page, device, viewport, layout):
    """Diseño de móvil por debajo de 1024 px y de escritorio desde 1024 px."""
    web = open_page(device=device, viewport=viewport, geo=DENY, clock=False)
    settle(web)
    assert web.page.evaluate("() => getComputedStyle(document.getElementById('panel')).position") == layout
    width = web.page.evaluate("() => innerWidth")
    assert web.page.evaluate("() => document.documentElement.scrollWidth") <= width


# --- Alto de la pantalla y zonas seguras -------------------------------------------

def test_meta_viewport():
    """Escenario: Meta viewport."""
    html = (WEB / "index.html").read_text()
    metas = re.findall(r'<meta name="viewport" content="([^"]*)">', html)
    assert metas == ["width=device-width, initial-scale=1, viewport-fit=cover"]
    assert "maximum-scale" not in html and "user-scalable" not in html


def rules(css, selector):
    """Declaraciones de las reglas cuyo selector contiene `selector` (CSS sencillo)."""
    found = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in selectors.split(",")]:
            found.append(body)
    return " ".join(found)


def test_heights():
    """Escenario: Alturas."""
    assert not re.search(r"\d(\.\d+)?vh\b", CSS)
    assert "100vh" not in CSS
    assert "height: 100dvh" in rules(CSS, "body")
    assert "height: 100dvh" in rules(CSS, ".map")
    sheet = rules(CSS, ".panel")
    assert "max-height: 70dvh" in sheet and "max-height: 70dvh" in rules(CSS, ".detail")


def test_safe_areas():
    """Escenario: Zonas seguras."""
    for selector in (".panel", ".detail"):
        sheet = rules(CSS, selector)
        for side in ("bottom", "left", "right"):
            assert f"env(safe-area-inset-{side})" in sheet, (selector, side)
    corner = rules(CSS, ".leaflet-top.leaflet-left")
    assert "margin-top: env(safe-area-inset-top)" in corner
    assert "margin-left: env(safe-area-inset-left)" in corner


def test_in_the_safari_engine(open_page):
    """Escenario: En el motor de Safari (iPhone 13 en WebKit)."""
    web = open_page(device="iphone", geo=DENY, clock=False)
    settle(web)
    result = web.page.evaluate("""() => ({
        dvh: CSS.supports('height', '100dvh'),
        env: CSS.supports('padding', 'env(safe-area-inset-bottom)'),
        inner: innerHeight,
        body: document.body.getBoundingClientRect().height,
        map: document.getElementById('map').getBoundingClientRect().height,
        panelBottom: document.getElementById('panel').getBoundingClientRect().bottom })""")
    assert result["dvh"] and result["env"]
    assert result["inner"] == 664
    assert result["body"] == result["map"] == result["inner"]
    assert result["panelBottom"] == pytest.approx(result["inner"], abs=0.5)
    assert web.console_errors == []


# --- Sin depender de hover ---------------------------------------------------------

def test_no_hover_outside_hover_media():
    """Escenario: Hojas de estilo sin hover."""
    outside = re.sub(r"@media\s*\(hover:\s*hover\)\s*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", CSS)
    assert ":hover" not in outside
