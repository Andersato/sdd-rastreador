"""Utilidades de los tests funcionales de la web (map-view)."""

import time

from tests.api_helpers import priced, save

NEARBY = "/api/stations/nearby"
MADRID = (40.416775, -3.703790)
BARCELONA = (41.3874, 2.1686)
SPAIN_CORNERS = [(35.9, -9.4), (43.9, 4.4), (35.9, 4.4), (43.9, -9.4)]
CLICK_HINT = "Pincha en el mapa para elegir dónde buscar"
SEARCHING = "Buscando tu ubicación…"

# Agentes de usuario fijos para los tests de «Cómo llegar» (add-station-detail, D11):
# sin ellos, el Chromium de Playwright en un Mac dice «Macintosh».
UA_LINUX_CHROME = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/156.0.0.0 Safari/537.36")
UA_MAC_SAFARI = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) Version/26.0 Safari/605.1.15")
# iPadOS se presenta como un Mac: «Macintosh» y sin «iPad».
UA_IPADOS = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1")


def seed_madrid(db):
    """Las estaciones del escenario «Búsqueda en Madrid» de prices-api, más dos
    de Barcelona."""
    save(db,
         priced("1001", {"Gasoleo A": "1,459"}, 40.4250, -3.7038),
         priced("1002", {"Gasoleo A": "1,459"}, 40.4168, -3.6800),
         priced("1003", {"Gasoleo A": "1,399"}, 40.4400, -3.7300, **{"Rótulo": "CEPSA"}),
         priced("1004", {"Gasoleo A": "1,299"}, 40.4630, -3.7038, **{"Rótulo": "BP"}),
         priced("1005", {"Gasolina 95 E5": "1,529"}, 40.416775, -3.703790),
         priced("1006", {"Gasoleo A": "1,199"}, 0.0, 0.0),
         priced("8001", {"Gasoleo A": "1,419"}, 41.3900, 2.1700, **{"Rótulo": "PLENOIL"}),
         priced("8002", {"Gasoleo A": "1,439"}, 41.3800, 2.1600, **{"Rótulo": "BONAREA"}))


def wait_until(web, condition, timeout=10.0, step_ms=50):
    """Espera a que se cumpla `condition`, dejando trabajar a Playwright entre
    comprobaciones (con `time.sleep` no se procesarían sus eventos)."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("no se cumplió la condición a tiempo")
        web.page.wait_for_timeout(step_ms)


def nearby_calls(web):
    return web.guard.api_calls(NEARBY)


def click_map(web, lat, lon):
    """Pincha en el mapa en (lat, lon), como lo traduce Leaflet un toque o clic."""
    web.page.evaluate("""([lat, lon]) => { const m = window.__mapView.map.leaflet;
        m.fire('click', {latlng: L.latLng(lat, lon)}); }""", [lat, lon])


def text(web, selector):
    locator = web.page.locator(selector)
    return locator.inner_text() if locator.is_visible() else None


def visible_zone(web):
    """(arriba, abajo) en píxeles de la ventana de la zona visible del mapa."""
    return web.page.evaluate("""() => {
        const attribution = document.querySelector('.leaflet-control-attribution').getBoundingClientRect();
        const detail = document.getElementById('detail');
        const sheet = detail.hidden ? document.getElementById('panel') : detail;
        const desktop = matchMedia('(min-width: 1024px)').matches;
        return [attribution.bottom, desktop ? innerHeight : sheet.getBoundingClientRect().top]; }""")


def in_visible_zone(web, points):
    """Todos los `points` (lat, lon) caen dentro de la zona visible del mapa."""
    top, bottom = visible_zone(web)
    positions = web.page.evaluate("""(points) => { const m = window.__mapView.map.leaflet;
        const box = document.getElementById('map').getBoundingClientRect();
        return points.map(([lat, lon]) => { const p = m.latLngToContainerPoint([lat, lon]);
            return [p.x + box.left, p.y + box.top]; }); }""", [list(p) for p in points])
    width = web.page.evaluate("() => innerWidth")
    return all(top - 1 <= y <= bottom + 1 and -1 <= x <= width + 1 for x, y in positions)


def circle_in_view(web):
    """El círculo del radio se ve entero (spec: zona visible del mapa)."""
    bounds = web.page.evaluate("""() => { const m = window.__mapView.map.leaflet; let c = null;
        m.eachLayer(l => { if (l instanceof L.Circle) c = l; });
        if (!c) return null; const b = c.getBounds();
        return [[b.getSouth(), b.getWest()], [b.getNorth(), b.getEast()]]; }""")
    if bounds is None:
        return False
    (south, west), (north, east) = bounds
    return in_visible_zone(web, [(south, west), (north, east), (south, east), (north, west)])


def has_circle(web):
    return web.page.evaluate("""() => { let n = 0;
        window.__mapView.map.leaflet.eachLayer(l => { if (l instanceof L.Circle) n += 1; });
        return n > 0; }""")


def station_markers(web):
    return web.page.locator(".price-marker").count()


def point_and_circle(web):
    """Centros (lat, lon) del marcador del punto y del círculo del radio (o None)."""
    return web.page.evaluate("""() => { let point = null, circle = null;
        window.__mapView.map.leaflet.eachLayer(l => {
            if (l instanceof L.Circle) { const c = l.getLatLng(); circle = [c.lat, c.lng]; }
            else if (l instanceof L.CircleMarker) { const c = l.getLatLng(); point = [c.lat, c.lng]; }
        });
        return {point, circle}; }""")
