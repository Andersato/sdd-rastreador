"""Búsqueda, lista, hoja, ficha y colores (map-view, tareas 7.2 y 7.3).

Los casos normales van contra la app real con la base de Madrid; los de datos
no válidos o de muchas estaciones, con respuestas fijas de tests/fixtures/web/.
Por defecto en el iPhone (WebKit); lo común se repite en el Pixel 7 y lo de
escritorio va a 1280×800 (Chromium)."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.web_fixtures import fixture_response, fulfill_args
from tests.web_helpers import (BARCELONA, MADRID, UA_MAC_SAFARI, circle_in_view, click_map,
                               in_visible_zone, nearby_calls, point_and_circle, seed_madrid,
                               station_markers, text, wait_until)

pytestmark = pytest.mark.browser

GRANT = {"kind": "grant", "lat": MADRID[0], "lon": MADRID[1]}
KEY = "precios-gasolineras.preferencias"


@pytest.fixture
def seeded(web_db):
    seed_madrid(web_db)


def params(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def wait_results(web):
    web.page.wait_for_selector("#count:not([hidden])")


def radius_pref(radius):
    return f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(json.dumps({'radius': radius}))})"


@pytest.fixture
def mocked(open_page):
    """Abre la web con combustibles y salud fijos y `nearby` (uno o varios
    nombres de respuestas fijas, en orden), con la ubicación en Madrid."""
    def open_(*nearby, device="iphone", radius=None, **kwargs):
        def mocks(web):
            web.mock("/api/fuels", "fuels_ok")
            web.mock("/api/health", "health_ok")
            web.mock("/api/stations/nearby", *nearby)
        scripts = [radius_pref(radius)] if radius else []
        web = open_page(device=device, geo=GRANT, clock=False, before_goto=mocks,
                        init_scripts=scripts, **kwargs)
        wait_results(web)
        return web
    return open_


def rows(web):
    return web.page.eval_on_selector_all(".station-row", "els => els.map(e => e.textContent)")


def row(web, station_id):
    return web.page.locator(f'.station-row[data-id="{station_id}"]')


def marker(web, station_id):
    return web.page.locator(f'.price-marker[data-id="{station_id}"]')


def expand(web):
    web.press("#toggle")
    web.page.wait_for_selector("#panel.expanded")


def is_selected(web, station_id):
    return ("selected" in (row(web, station_id).get_attribute("class") or "")
            and "selected" in (marker(web, station_id).get_attribute("class") or ""))


def selected_ids(web):
    return web.page.eval_on_selector_all(".station-row.selected, .price-marker.selected",
                                         "els => els.map(e => e.dataset.id)")


def detail_text(web):
    return web.page.locator("#detail").inner_text() if web.page.locator("#detail").is_visible() else None


def tap_marker(web, station_id):
    label = marker(web, station_id).locator(".label")
    if web.touch:
        label.tap()
    else:
        label.click()


# --- Peticiones a la API justas y sin respuestas viejas ----------------------------

def test_quiet_page(open_page, seeded):
    """Escenario: Página quieta (5 minutos sin peticiones)."""
    web = open_page(geo=GRANT)
    wait_results(web)
    before = len([r for r in web.guard.requests if "/api/" in r["url"]])
    web.page.clock.run_for(5 * 60 * 1000)
    web.page.wait_for_timeout(300)
    after = len([r for r in web.guard.requests if "/api/" in r["url"]])
    assert after == before


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_open_and_see_details(open_page, seeded, device):
    """Escenario: Abrir y ver la ficha (una petición de cada y una de detalle por
    ficha; cambia con add-station-detail, autorizado en su tarea 0.1)."""
    web = open_page(device=device, geo=GRANT, clock=False)
    wait_results(web)
    for station_id in ("1003", "1001", "1002"):
        tap_marker(web, station_id)
        web.page.wait_for_selector("#detail:not([hidden])")
        web.page.wait_for_function(
            "() => document.getElementById('detail-status').textContent === 'Ficha cargada'")
        web.press("#detail-close")
    calls = [urlsplit(r["url"]).path for r in web.guard.requests if "/api/" in r["url"]]
    assert sorted(calls) == ["/api/fuels", "/api/health", "/api/stations/1001",
                             "/api/stations/1002", "/api/stations/1003", "/api/stations/nearby"]


def test_two_clicks_in_a_row(open_page, seeded):
    """Escenario: Dos pinchazos seguidos (la respuesta vieja llega después)."""
    held = []

    def routes(web):
        def handle(route):
            if "lat=40.417" in route.request.url:
                held.append(route)
            else:
                route.fallback()
        web.page.route("**/api/stations/nearby*", handle)
    web = open_page(geo={"kind": "deny"}, clock=False, before_goto=routes)
    web.page.wait_for_selector("#fuel:not([disabled])")
    click_map(web, *MADRID)
    wait_until(web, lambda: len(held) == 1)
    click_map(web, *BARCELONA)
    wait_results(web)
    held[0].fulfill(**fulfill_args(fixture_response("nearby_madrid")))
    web.page.wait_for_timeout(500)
    assert sorted(web.page.eval_on_selector_all(".station-row", "e => e.map(x => x.dataset.id)")) \
        == ["8001", "8002"]
    assert station_markers(web) == 2


@pytest.mark.parametrize("trigger", ["location", "click"])
def test_search_waits_for_fuels(open_page, seeded, trigger):
    """Escenarios: Ubicación antes que los combustibles y Pinchar antes que los
    combustibles."""
    fuels = {}

    def routes(web):
        fuels["mock"] = web.mock("/api/fuels", "fuels_ok", hold=True)
    geo = GRANT if trigger == "location" else {"kind": "deny"}
    web = open_page(geo=geo, clock=False, before_goto=routes)
    wait_until(web, lambda: len(fuels["mock"].held) == 1)
    if trigger == "click":
        click_map(web, *BARCELONA)
    web.page.wait_for_timeout(500)
    assert nearby_calls(web) == []
    assert web.page.evaluate("() => window.__mapView.state.point") is not None
    fuels["mock"].release()
    wait_results(web)
    assert len(nearby_calls(web)) == 1
    assert params(nearby_calls(web)[0])["fuel"] == "gasoleo-a"


# --- Lista de gasolineras -------------------------------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_list_in_madrid(mocked, device):
    """Escenario: Lista en Madrid."""
    web = mocked("nearby_madrid", device=device)
    expand(web)
    assert rows(web) == ["CEPSA · 3,4 km · 1,399 €/l", "REPSOL · 0,9 km · 1,459 €/l",
                         "Sin rótulo · 2,0 km · 1,459 €/l"]
    assert station_markers(web) == 3
    assert web.page.locator(".search-point").count() == 1


def test_list_against_the_real_api(open_page, seeded):
    """Escenario: Encaje con la API real (estaciones "1001" a "1006", 10 km)."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    expand(web)
    ids = web.page.eval_on_selector_all(".station-row", "e => e.map(x => x.dataset.id)")
    assert ids == ["1004", "1003", "1001", "1002"]
    assert rows(web)[0] == "BP · 5,1 km · 1,299 €/l"


def test_station_with_unusable_data(mocked):
    """Escenario: Estación con datos que no sirven."""
    web = mocked("nearby_invalid_stations")
    expand(web)
    assert web.page.eval_on_selector_all(".station-row", "e => e.map(x => x.dataset.id)") == ["1002"]
    assert station_markers(web) == 1
    assert web.console_errors == []


# --- Recuento y avisos ------------------------------------------------------------

def test_three_stations(mocked):
    """Escenario: Tres gasolineras."""
    assert text(mocked("nearby_madrid"), "#count") == "3 gasolineras encontradas"


def test_one_station(mocked):
    """Escenario: Una gasolinera."""
    assert text(mocked("nearby_one"), "#count") == "1 gasolinera encontrada"


def test_one_discarded(mocked):
    """Escenario: Con una descartada."""
    web = mocked("nearby_one_discarded")
    assert text(web, "#count") == "2 gasolineras encontradas"
    expand(web)
    assert text(web, "#discarded") == "1 gasolinera no se muestra por datos incompletos."
    assert text(web, "#more") is None


def test_two_discarded(mocked):
    """Escenario: Con dos descartadas."""
    web = mocked("nearby_two_discarded")
    expand(web)
    assert text(web, "#discarded") == "2 gasolineras no se muestran por datos incompletos."


def search_again(web, radius):
    calls = len(nearby_calls(web))
    web.page.select_option("#radius", str(radius))
    wait_until(web, lambda: len(nearby_calls(web)) == calls + 1)
    web.page.wait_for_timeout(300)


@pytest.mark.parametrize("next_response", ["nearby_madrid", "nearby_empty"])
def test_discarded_notice_disappears(mocked, next_response):
    """Escenario: El aviso de descartadas desaparece (todas válidas o total 0)."""
    web = mocked("nearby_two_discarded", next_response)
    expand(web)
    assert text(web, "#discarded")
    search_again(web, 25)
    assert text(web, "#discarded") is None


def test_more_than_100_at_25_km(mocked):
    """Escenario: Más de 100 a 25 km."""
    web = mocked("nearby_342", radius=25)
    expand(web)
    assert len(rows(web)) == 100
    assert text(web, "#more") == ("Hay 342 gasolineras en este radio; se han pedido las 100 más "
                                  "baratas. Reduce el radio para ver menos y más cercanas.")


def test_more_than_100_at_5_km(mocked):
    """Escenario: Más de 100 a 5 km."""
    web = mocked("nearby_130_5km", radius=5)
    expand(web)
    assert text(web, "#more") == "Hay 130 gasolineras en este radio; se han pedido las 100 más baratas."


def test_more_with_discarded(mocked):
    """Escenario: Con estaciones descartadas."""
    web = mocked("nearby_342_two_discarded", radius=25)
    assert text(web, "#count") == "98 gasolineras encontradas"
    expand(web)
    assert text(web, "#more").startswith("Hay 342 gasolineras en este radio; se han pedido las 100")
    assert text(web, "#discarded") == "2 gasolineras no se muestran por datos incompletos."


def test_all_received_and_valid(mocked):
    """Escenario: Todas recibidas y válidas."""
    web = mocked("nearby_madrid")
    expand(web)
    assert text(web, "#more") is None


@pytest.mark.parametrize("next_response", ["nearby_madrid", "nearby_empty"])
def test_more_notice_disappears(mocked, next_response):
    """Escenario: El aviso anterior desaparece (todas recibidas o total 0)."""
    web = mocked("nearby_342", next_response, radius=25)
    expand(web)
    assert text(web, "#more")
    search_again(web, 10)
    assert text(web, "#more") is None


# --- Colores y leyenda -------------------------------------------------------------

def tiers_on_map(web):
    return web.page.eval_on_selector_all(
        ".price-marker .label", "els => els.map(e => [e.textContent, e.className.split(' ')[1]])")


def test_markers_and_legend(mocked):
    """Escenario: Marcadores y leyenda."""
    web = mocked("nearby_legend")
    assert sorted(tiers_on_map(web)) == sorted([
        ["1,299", "tier-cheap"], ["1,399", "tier-cheap"], ["1,459", "tier-expensive"],
        ["1,459", "tier-expensive"]])
    expand(web)
    legend = web.page.locator("#legend").inner_text()
    for fragment in ("Más barata", "Intermedia", "Más cara",
                     "Colores por tercios de las 4 gasolineras mostradas; el precio mínimo y el "
                     "máximo siempre en sus extremos", "De 1,299 a 1,459 €/l"):
        assert fragment in legend
    swatches = web.page.eval_on_selector_all(
        "#legend-tiers .swatch", "els => els.map(e => [e.className, getComputedStyle(e).backgroundColor,"
        " e.getBoundingClientRect().width > 0])")
    assert [c.split()[1] for c, _, _ in swatches] == ["tier-cheap", "tier-mid", "tier-expensive"]
    assert all(shown for _, _, shown in swatches)
    assert len({colour for _, colour, _ in swatches}) == 3
    labels = web.page.eval_on_selector_all(
        ".price-marker .label", "els => Object.fromEntries(els.map(e => [e.className.split(' ')[1],"
        " getComputedStyle(e).backgroundColor]))")
    for cls, colour, _ in swatches:  # el color de la leyenda es el de los marcadores
        tier = cls.split()[1]
        if tier in labels:
            assert labels[tier] == colour, tier


def test_legend_on_mobile(mocked):
    """Escenario: Leyenda en el móvil."""
    web = mocked("nearby_legend")
    assert not web.page.locator("#legend").is_visible()
    assert sorted(label for label, _ in tiers_on_map(web)) == ["1,299", "1,399", "1,459", "1,459"]
    expand(web)
    assert web.page.locator("#legend").is_visible()
    sizes = web.page.evaluate("""() => { const l = document.getElementById('legend').getBoundingClientRect();
        const b = document.getElementById('panel-body').getBoundingClientRect();
        return {legend: [l.top, l.bottom], body: [b.top, b.bottom], h: innerHeight}; }""")
    # completa: entera dentro de la parte visible de la hoja y de la ventana
    assert sizes["legend"][0] >= sizes["body"][0] - 1 and sizes["legend"][1] <= sizes["body"][1] + 1
    assert sizes["legend"][1] <= sizes["h"]
    legend = web.page.locator("#legend").inner_text()
    for fragment in ("Más barata", "Intermedia", "Más cara", "De 1,299 a 1,459 €/l"):
        assert fragment in legend


@pytest.mark.parametrize(("name", "expected"), [("nearby_same_price", "Todas a 1,459 €/l"),
                                                ("nearby_one", "Todas a 1,399 €/l")])
def test_single_price_legend(mocked, name, expected):
    """Escenarios: Todas al mismo precio y Una sola gasolinera."""
    web = mocked(name)
    assert {t for _, t in tiers_on_map(web)} == {"tier-single"}
    expand(web)
    assert text(web, "#legend-range") == expected
    assert not web.page.locator("#legend-tiers").is_visible()


# --- Hoja inferior de la lista -------------------------------------------------------

def test_folded_with_results(mocked):
    """Escenario: Plegada con resultados."""
    web = mocked("nearby_madrid")
    assert text(web, "#count") == "3 gasolineras encontradas"
    assert text(web, "#toggle") == "Ver lista"
    count_box = web.page.locator("#count").bounding_box()
    toggle_box = web.page.locator("#toggle").bounding_box()
    assert abs((count_box["y"] + count_box["height"] / 2)
               - (toggle_box["y"] + toggle_box["height"] / 2)) < 4  # misma fila
    assert text(web, "#cheapest") == "Más barata: CEPSA · 3,4 km · 1,399 €/l"
    for hidden in ("#list", "#capture", "#legend"):
        assert not web.page.locator(hidden).is_visible(), hidden


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_expand(mocked, device):
    """Escenario: Desplegar (40 gasolineras)."""
    web = mocked("nearby_40", device=device)
    expand(web)
    assert text(web, "#toggle") == "Ocultar lista"
    assert web.page.get_attribute("#toggle", "aria-expanded") == "true"
    for visible in ("#capture", "#legend", "#list"):
        assert web.page.locator(visible).is_visible(), visible
    sizes = web.page.evaluate("""() => { const p = document.getElementById('panel');
        const b = document.getElementById('panel-body');
        return {panel: p.getBoundingClientRect().height, h: innerHeight,
                scroll: b.scrollHeight, client: b.clientHeight,
                page: document.scrollingElement.scrollHeight}; }""")
    assert sizes["panel"] <= 0.7 * sizes["h"] + 1
    assert sizes["scroll"] > sizes["client"]  # la lista se desplaza dentro de la hoja
    assert sizes["page"] <= sizes["h"]
    web.page.evaluate("() => document.getElementById('panel-body').scrollTop = 400")
    assert web.page.evaluate("() => scrollY") == 0


def test_fold(mocked):
    """Escenario: Plegar."""
    web = mocked("nearby_madrid")
    expand(web)
    web.press("#toggle")
    assert text(web, "#toggle") == "Ver lista"
    assert web.page.get_attribute("#toggle", "aria-expanded") == "false"
    assert not web.page.locator("#list").is_visible()
    assert web.page.locator("#cheapest").is_visible()
    for hidden in ("#capture", "#legend", "#more", "#discarded", ".station-row"):
        assert not web.page.locator(hidden).first.is_visible(), hidden
    assert text(web, "#count") == "3 gasolineras encontradas"


def test_tap_the_cheapest(mocked):
    """Escenario: Tocar la más barata."""
    web = mocked("nearby_madrid")
    web.press("#cheapest")
    web.page.wait_for_selector("#detail:not([hidden])")
    assert "CEPSA" in detail_text(web)
    assert "selected" in marker(web, "1003").get_attribute("class")


def test_stays_expanded_between_searches(mocked):
    """Escenario: Desplegada entre búsquedas."""
    web = mocked("nearby_madrid", "nearby_legend")
    expand(web)
    search_again(web, 25)
    assert "expanded" in web.page.get_attribute("#panel", "class")
    assert rows(web)[0].startswith("BP")


def test_folds_when_left_without_list(mocked):
    """Escenario: Se pliega al quedarse sin lista (con total 0)."""
    web = mocked("nearby_madrid", "nearby_empty", "nearby_madrid")
    expand(web)
    search_again(web, 25)
    assert "expanded" not in web.page.get_attribute("#panel", "class")
    assert not web.page.locator("#toggle").is_visible()
    search_again(web, 50)
    wait_results(web)
    assert "expanded" not in web.page.get_attribute("#panel", "class")
    assert text(web, "#toggle") == "Ver lista"


# --- Panel lateral y mapa a pantalla completa --------------------------------------

def test_desktop_side_panel(mocked):
    """Escenario: Escritorio con resultados (panel lateral)."""
    web = mocked("nearby_40", device="desktop")
    panel = web.page.locator("#panel").bounding_box()
    the_map = web.page.locator("#map").bounding_box()
    assert panel["x"] + panel["width"] <= the_map["x"] + 1
    sizes = web.page.evaluate("""() => ({page: document.scrollingElement.scrollHeight, h: innerHeight,
        scroll: document.getElementById('panel').scrollHeight,
        client: document.getElementById('panel').clientHeight})""")
    assert sizes["page"] <= sizes["h"]
    assert sizes["scroll"] > sizes["client"]
    assert not web.page.locator("#toggle").is_visible()
    assert not web.page.locator("#cheapest").is_visible()
    assert web.page.locator("#list").is_visible()


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_full_screen_map(open_page, seeded, device):
    """Escenario: iPhone y Android (mapa a pantalla completa)."""
    web = open_page(device=device, geo=GRANT, clock=False)
    wait_results(web)
    web.page.wait_for_timeout(300)
    sizes = web.page.evaluate("""() => { const m = document.getElementById('map').getBoundingClientRect();
        return {map: [m.x, m.y, m.width, m.height], w: innerWidth, h: innerHeight,
                sw: document.scrollingElement.scrollWidth, sh: document.scrollingElement.scrollHeight}; }""")
    assert sizes["map"] == [0, 0, sizes["w"], sizes["h"]]
    assert sizes["sw"] <= sizes["w"] and sizes["sh"] <= sizes["h"]
    assert circle_in_view(web)


def test_small_phone(open_page, seeded):
    """Escenario: Teléfono pequeño (320×568, zona visible ≥ 40 %)."""
    web = open_page(device="small", geo=GRANT, clock=False)
    wait_results(web)
    web.page.wait_for_timeout(300)
    zone = web.page.evaluate("""() => {
        const a = document.querySelector('.leaflet-control-attribution').getBoundingClientRect();
        const p = document.getElementById('panel').getBoundingClientRect();
        const m = document.getElementById('map').getBoundingClientRect();
        return {ratio: (p.top - a.bottom) / innerHeight, sw: document.scrollingElement.scrollWidth,
                map: [m.x, m.y, m.width, m.height], size: [innerWidth, innerHeight],
                expanded: document.getElementById('panel').classList.contains('expanded')}; }""")
    assert zone["sw"] <= 320
    assert not zone["expanded"]
    assert zone["map"] == [0, 0, *zone["size"]] and zone["size"] == [320, 568]
    assert zone["ratio"] >= 0.40


def test_long_texts_on_mobile(mocked):
    """Escenario: Textos largos en el móvil (320×568)."""
    web = mocked("nearby_long_brand", device="small")
    for step in ("plegada", "desplegada"):
        if step == "desplegada":
            expand(web)
        assert web.page.evaluate("() => document.scrollingElement.scrollWidth") <= 320, step
    price = web.page.locator(".station-row .price").bounding_box()
    assert price["x"] >= 0 and price["x"] + price["width"] <= 320


# --- Lista y mapa sincronizados ------------------------------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_press_in_the_list(mocked, device):
    """Escenario: Pulsar en la lista."""
    web = mocked("nearby_madrid", device=device)
    expand(web)
    web.press('.station-row[data-id="1001"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    assert selected_ids(web) == ["1001", "1001"]
    assert in_visible_zone(web, [(40.425, -3.7038)])
    assert "REPSOL" in detail_text(web)


def test_press_a_marker_on_desktop(mocked):
    """Escenario: Pulsar un marcador en el escritorio (la lista se desplaza)."""
    web = mocked("nearby_40", device="desktop")
    last = web.page.eval_on_selector_all(".station-row", "e => e.at(-1).dataset.id")
    assert not web.page.evaluate(f"""() => {{ const r = document.querySelector('.station-row[data-id="{last}"]').getBoundingClientRect();
        const p = document.getElementById('panel').getBoundingClientRect();
        return r.top >= p.top - 1 && r.bottom <= p.bottom + 1; }}""")
    web.page.evaluate(f"""() => window.__mapView.map.leaflet.setView(
        [{40.40 + 9 * 0.01}, {-3.75 + 3 * 0.01}], 15, {{animate: false}})""")
    tap_marker(web, last)
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.wait_for_timeout(300)
    assert web.page.evaluate(f"""() => {{ const r = document.querySelector('.station-row[data-id="{last}"]').getBoundingClientRect();
        const p = document.getElementById('panel').getBoundingClientRect();
        return r.top >= p.top - 1 && r.bottom <= p.bottom + 1; }}""")
    assert is_selected(web, last)


def test_tap_a_marker_on_mobile(mocked):
    """Escenario: Tocar un marcador en el móvil."""
    web = mocked("nearby_madrid")
    tap_marker(web, "1002")
    web.page.wait_for_selector("#detail:not([hidden])")
    assert is_selected(web, "1002")
    assert row(web, "1002").get_attribute("aria-current") == "true"


def test_change_selected(mocked):
    """Escenario: Cambiar de seleccionada."""
    web = mocked("nearby_madrid")
    tap_marker(web, "1001")
    web.page.wait_for_selector("#detail:not([hidden])")
    tap_marker(web, "1002")
    wait_until(web, lambda: selected_ids(web) == ["1002", "1002"])
    assert detail_text(web).startswith("Sin rótulo")


@pytest.mark.parametrize(("action", "device"), [("click", "iphone"), ("click", "desktop"),
                                                ("fuel", "desktop"), ("radius", "desktop"),
                                                ("back", "desktop")])
def test_new_search_clears_selection(mocked, action, device):
    """Escenario: Nueva búsqueda (pinchar, combustible, radio o «Volver»). En el
    móvil, con la ficha abierta los controles quedan bajo ella: solo se puede
    pinchar en el mapa; los demás se prueban en escritorio."""
    web = mocked("nearby_madrid", device=device)
    tap_marker(web, "1001")
    web.page.wait_for_selector("#detail:not([hidden])")
    calls = len(nearby_calls(web))
    if action == "click":
        click_map(web, *BARCELONA)
    elif action == "fuel":
        web.page.select_option("#fuel", "gasolina-95-e5")
    elif action == "radius":
        web.page.select_option("#radius", "25")
    else:
        web.page.click("#back-to-location")
    wait_until(web, lambda: len(nearby_calls(web)) == calls + 1)
    wait_results(web)
    assert selected_ids(web) == []
    assert detail_text(web) is None


# --- Ficha sencilla -----------------------------------------------------------------

def test_full_detail(mocked):
    """Escenario: Ficha completa (los datos de la búsqueda se ven enseguida, antes
    de que llegue el detalle; cambia con add-station-detail, autorizado en su
    tarea 0.1)."""
    web = mocked("nearby_detail")
    detail = web.mock("/api/stations/4375", "station_4375", hold=True)
    tap_marker(web, "4375")
    web.page.wait_for_selector("#detail:not([hidden])")
    lines = web.page.locator("#detail-head").inner_text().split("\n")
    assert [line for line in lines if line] == ["REPSOL", "CALLE MAYOR, 1", "Madrid", "1,459 €/l",
                                                "0,0 km"]
    assert len(detail.calls) == 1 and detail.held  # el detalle aún no ha llegado
    detail.release()
    web.page.wait_for_selector("#detail-info:not([hidden])")
    lines = web.page.locator("#detail-head").inner_text().split("\n")
    assert [line for line in lines if line] == ["REPSOL", "CALLE MAYOR, 1", "Madrid", "1,459 €/l",
                                                "0,0 km"]


def test_detail_as_bottom_sheet_on_mobile(mocked):
    """Escenario: Ficha en una hoja inferior en el móvil."""
    web = mocked("nearby_detail")
    tap_marker(web, "4375")
    web.page.wait_for_selector("#detail:not([hidden])")
    box = web.page.locator("#detail").bounding_box()
    size = web.page.evaluate("() => [innerWidth, innerHeight]")
    assert box["x"] == 0 and box["width"] == size[0]
    assert box["y"] + box["height"] == pytest.approx(size[1], abs=0.5)
    assert not web.page.locator("#panel").is_visible()
    assert web.page.locator(".leaflet-popup").count() == 0
    assert in_visible_zone(web, [(40.416775, -3.70379)])


def test_detail_with_long_texts_in_landscape(open_page):
    """Escenario: Ficha con textos largos en horizontal (750×342)."""
    spec = fixture_response("nearby_one")
    station = spec["body"]["data"]["stations"][0]
    station["brand"] = "B" * 80
    station["address"] = "CALLE " + "LARGA " * 19
    station["address"] = station["address"][:120]

    def mocks(web):
        web.mock("/api/fuels", "fuels_ok")
        web.mock("/api/health", "health_ok")
        web.mock("/api/stations/nearby", spec)
    web = open_page(device="iphone_landscape", geo=GRANT, clock=False, before_goto=mocks)
    wait_results(web)
    tap_marker(web, "1003")
    web.page.wait_for_selector("#detail:not([hidden])")
    box = web.page.locator("#detail").bounding_box()
    height = web.page.evaluate("() => innerHeight")
    assert box["height"] <= 0.7 * height + 1
    close = web.page.locator("#detail-close").bounding_box()
    assert close["y"] >= box["y"] and close["y"] + close["height"] <= height
    assert "B" * 80 in detail_text(web).replace("\n", "")
    # Con estos textos, a 750 px de ancho la ficha casi llena su 70 % y el
    # contenido cabe; para ver que se desplaza dentro de ella, se agranda la
    # letra del contenido (como con un tamaño de texto mayor del sistema).
    assert web.page.evaluate(
        "() => getComputedStyle(document.getElementById('detail-body')).overflowY") in ("auto", "scroll")
    web.page.evaluate("() => document.getElementById('detail-body').style.setProperty('font-size', '28px')")
    web.page.wait_for_timeout(100)
    box = web.page.locator("#detail").bounding_box()
    assert box["height"] <= 0.7 * height + 1
    scroll = web.page.evaluate("""() => { const b = document.getElementById('detail-body');
        const before = b.scrollTop; b.scrollTop = 1000;
        return {scrolls: b.scrollHeight > b.clientHeight, moved: b.scrollTop > before,
                page: [scrollX, scrollY]}; }""")
    assert scroll["scrolls"] and scroll["moved"], scroll  # se desplaza dentro de la ficha
    assert scroll["page"] == [0, 0]
    close = web.page.locator("#detail-close").bounding_box()
    assert close["y"] >= box["y"] and close["y"] + close["height"] <= height + 0.5


def test_detail_in_the_side_panel_on_desktop(mocked):
    """Escenario: Ficha en el panel lateral en el escritorio."""
    web = mocked("nearby_detail", device="desktop")
    web.page.click('.station-row[data-id="4375"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    detail = web.page.locator("#detail").bounding_box()
    the_map = web.page.locator("#map").bounding_box()
    first_row = web.page.locator(".station-row").first.bounding_box()
    assert detail["x"] + detail["width"] <= the_map["x"] + 1
    assert detail["y"] + detail["height"] <= first_row["y"]
    assert web.page.locator(".leaflet-popup").count() == 0


def test_empty_data_in_detail(mocked):
    """Escenario: Datos vacíos."""
    web = mocked("nearby_detail")
    tap_marker(web, "5120")
    web.page.wait_for_selector("#detail:not([hidden])")
    body = web.page.locator("#detail-body").inner_text()
    for fragment in ("Sin rótulo", "Dirección no disponible", "Municipio no disponible"):
        assert fragment in body


@pytest.mark.parametrize("how", ["button", "escape"])
@pytest.mark.parametrize("expanded", [False, True])
def test_close_detail(mocked, how, expanded):
    """Escenarios: Cerrar con el botón y Cerrar con Escape."""
    web = mocked("nearby_madrid")
    if expanded:
        expand(web)  # la hoja desplegada tapa los marcadores: se abre desde la fila
        web.press('.station-row[data-id="1001"]')
    else:
        tap_marker(web, "1001")
    web.page.wait_for_selector("#detail:not([hidden])")
    calls = len(nearby_calls(web))
    if how == "button":
        web.press("#detail-close")
    else:
        web.page.keyboard.press("Escape")
    web.page.wait_for_selector("#detail", state="hidden")
    assert selected_ids(web) == []
    assert len(nearby_calls(web)) == calls
    assert ("expanded" in web.page.get_attribute("#panel", "class")) == expanded
    assert web.page.locator("#panel").is_visible()


# --- Textos de la API mostrados como texto ------------------------------------------

def test_brand_with_markup(mocked):
    """Escenario: Rótulo con etiquetas."""
    web = mocked("nearby_markup_brand")
    dialogs = []
    web.page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    expand(web)
    assert rows(web)[0].startswith("<img src=x onerror=alert(1)>")
    web.press('.station-row[data-id="1001"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    assert "<img src=x onerror=alert(1)>" in detail_text(web)
    assert web.page.locator("#list img, #detail img").count() == 0
    web.page.wait_for_timeout(300)
    assert dialogs == []


# --- Tarea 7.3: escenarios de los grupos 4 a 6 que necesitan la búsqueda ------------

from tests.web_fixtures import TILE_URL  # noqa: E402

MINISTRY = ("Ministerio de Industria, Comercio y Turismo - Precios de carburantes "
            "en estaciones de servicio")


def test_requests_while_using_the_page(open_page, seeded):
    """Escenario: Peticiones al usar la página (ubicación, búsqueda y la ficha de
    "1003", sin pulsar «Cómo llegar»). Con add-station-detail, la ficha pide su
    detalle al propio origen y el escenario «Pulsar «Cómo llegar»» se comprueba,
    en el iPhone, con los atributos del enlace (nota del escenario; autorizado en
    su tarea 0.1)."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    tap_marker(web, "1003")
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.wait_for_load_state("networkidle")
    for request in web.guard.requests:
        assert request["url"].startswith(web.base + "/") or TILE_URL.match(request["url"])
    directions = web.page.locator("#detail-directions")
    assert directions.get_attribute("href") == "https://maps.apple.com/?daddr=40.44,-3.73"
    assert directions.get_attribute("target") == "_blank"
    assert directions.get_attribute("rel") == "noopener noreferrer"


def test_press_directions_is_the_only_outside_request(open_page, seeded):
    """Escenario: Pulsar «Cómo llegar» (plan B de la nota: escritorio en Chromium con
    agente de Safari en Mac; la navegación se intercepta y se cancela)."""
    web = open_page(geo=GRANT, clock=False, device="desktop", user_agent=UA_MAC_SAFARI)
    wait_results(web)
    seen = web.intercept_directions()
    tap_marker(web, "1003")
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.wait_for_load_state("networkidle")
    before = len(web.guard.requests)
    with web.page.context.expect_page(timeout=5_000):
        web.page.click("#detail-directions")
    web.page.wait_for_timeout(300)
    outside = [r["url"] for r in web.guard.requests[before:]
               if not r["url"].startswith(web.base + "/") and not TILE_URL.match(r["url"])]
    assert outside == ["https://maps.apple.com/?daddr=40.44,-3.73"]
    assert [s["url"] for s in seen] == outside
    assert not [r for r in web.guard.requests[before:] if r["url"].startswith(web.base + "/")]


def attributions_visible_and_uncovered(web):
    attribution = web.page.locator(".leaflet-control-attribution")
    text_ = attribution.inner_text()
    assert MINISTRY in text_ and "© OpenStreetMap contributors" in text_
    box = attribution.bounding_box()
    width = web.page.evaluate("() => innerWidth")
    assert box["x"] >= 0 and box["x"] + box["width"] <= width and box["y"] >= 0
    for sheet in ("#panel", "#detail"):
        if web.page.locator(sheet).is_visible():
            assert box["y"] + box["height"] <= web.page.locator(sheet).bounding_box()["y"], sheet
    link = web.page.locator(".leaflet-control-attribution a")
    assert link.get_attribute("href") == "https://www.openstreetmap.org/copyright"
    # enteras, sin cortarse, y sin tapar los controles del mapa (el zoom)
    clipped = web.page.evaluate("""() => { const a = document.querySelector('.leaflet-control-attribution');
        return a.scrollWidth > a.clientWidth + 1 || a.scrollHeight > a.clientHeight + 1; }""")
    assert not clipped
    zoom = web.page.locator(".leaflet-control-zoom").bounding_box()
    assert box["y"] + box["height"] <= zoom["y"] + 0.5
    assert box["y"] + box["height"] <= web.page.evaluate("() => innerHeight")


def test_attributions_with_data(open_page, seeded):
    """Escenario: Atribuciones con datos (iPhone)."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    attributions_visible_and_uncovered(web)


@pytest.mark.parametrize("state", ["desplegada", "ficha"])
def test_attributions_on_small_phone_with_sheets(open_page, seeded, state):
    """Escenario: Atribuciones en el móvil (320×568, hoja desplegada o ficha)."""
    web = open_page(device="small", geo=GRANT, clock=False)
    wait_results(web)
    if state == "desplegada":
        expand(web)
    else:
        web.press("#cheapest")
        web.page.wait_for_selector("#detail:not([hidden])")
    attributions_visible_and_uncovered(web)


def test_click_on_barcelona(open_page, seeded):
    """Escenario: Pinchar en Barcelona."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    click_map(web, *BARCELONA)
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    query = params(nearby_calls(web)[-1])
    assert (query["lat"], query["lon"]) == ("41.387", "2.169")
    wait_until(web, lambda: sorted(web.page.eval_on_selector_all(
        ".price-marker", "e => e.map(x => x.dataset.id)")) == ["8001", "8002"])
    assert circle_in_view(web)  # con la hoja plegada
    assert point_and_circle(web) == {"point": [41.387, 2.169], "circle": [41.387, 2.169]}
    expand(web)
    assert sorted(web.page.eval_on_selector_all(".station-row", "e => e.map(x => x.dataset.id)")) \
        == ["8001", "8002"]


def test_tap_on_a_station_marker(open_page, seeded):
    """Escenario: Pinchar en un marcador de gasolinera (ficha, el punto no cambia y la
    única petición es la del detalle; cambia con add-station-detail, autorizado en
    su tarea 0.1)."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    before = len(web.guard.requests)
    point = web.page.evaluate("() => window.__mapView.state.point")
    tap_marker(web, "1001")
    web.page.wait_for_selector("#detail:not([hidden])")
    web.page.wait_for_timeout(300)
    assert web.page.evaluate("() => window.__mapView.state.point") == point
    api = [urlsplit(r["url"]).path for r in web.guard.requests[before:] if "/api/" in r["url"]]
    assert api == ["/api/stations/1001"]


@pytest.mark.parametrize("then", ["timeout", "deny"])
def test_click_and_location_never_comes(open_page, seeded, then):
    """Escenarios: Pinchar y que no llegue la ubicación / que después se deniegue."""
    web = open_page(geo={"kind": "pending"})
    web.page.wait_for_selector("#fuel:not([disabled])")
    web.page.clock.run_for(3000)
    click_map(web, *BARCELONA)
    wait_results(web)
    if then == "timeout":
        web.page.clock.run_for(8000)
    else:
        web.page.clock.run_for(2000)
        web.geo.deny()
    web.page.wait_for_timeout(300)
    assert text(web, "#hint") is None
    assert len(nearby_calls(web)) == 1
    assert not web.page.locator("#back-to-location").is_visible()
    assert web.page.evaluate("() => window.__mapView.state.point") == {"lat": 41.387, "lon": 2.169}
    assert station_markers(web) == 2
    assert text(web, "#count") == "2 gasolineras encontradas"
    assert point_and_circle(web) == {"point": [41.387, 2.169], "circle": [41.387, 2.169]}
    assert circle_in_view(web)  # el mapa no se ha movido a España entera


def test_change_to_hydrogen(open_page):
    """Escenario: Cambiar a Hidrogeno (precios en €/kg)."""
    def mocks(web):
        web.mock("/api/fuels", "fuels_ok")
        web.mock("/api/health", "health_ok")
        web.mock("/api/stations/nearby", "nearby_madrid", "nearby_hidrogeno")
    web = open_page(geo=GRANT, clock=False, before_goto=mocks)
    wait_results(web)
    web.page.select_option("#fuel", "hidrogeno")
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    assert params(nearby_calls(web)[-1])["fuel"] == "hidrogeno"
    wait_until(web, lambda: "€/kg" in (text(web, "#cheapest") or ""))
    expand(web)
    assert rows(web) == ["HYDRO · 4,2 km · 12,950 €/kg"]


BLOCKED_STORAGE = """
Object.defineProperty(window, 'localStorage', {configurable: true,
  get() { throw new DOMException('bloqueado', 'SecurityError'); }});
"""


def test_blocked_storage(open_page, seeded):
    """Escenario: Almacenamiento bloqueado (búsqueda completa con ficha)."""
    web = open_page(geo=GRANT, clock=False, init_scripts=[BLOCKED_STORAGE])
    wait_results(web)
    assert (web.page.eval_on_selector("#fuel", "e => e.value"),
            web.page.eval_on_selector("#radius", "e => e.value")) == ("gasoleo-a", "10")
    web.page.select_option("#radius", "25")
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    wait_results(web)
    web.press("#cheapest")
    web.page.wait_for_selector("#detail:not([hidden])")
    assert text(web, "#message") is None
    assert web.console_errors == []


@pytest.mark.parametrize(("device", "viewport", "layout"), [
    ("iphone_landscape", None, "fixed"),
    ("pixel", {"width": 820, "height": 1180}, "fixed"),
    ("desktop", None, "static"),
])
def test_layout_with_results(open_page, seeded, device, viewport, layout):
    """Escenarios de «Diseño mobile first» con resultados."""
    web = open_page(device=device, viewport=viewport, geo=GRANT, clock=False)
    wait_results(web)
    assert web.page.evaluate(
        "() => getComputedStyle(document.getElementById('panel')).position") == layout
    sizes = web.page.evaluate("() => [document.scrollingElement.scrollWidth, innerWidth]")
    assert sizes[0] <= sizes[1]
    if layout == "fixed":
        the_map = web.page.locator("#map").bounding_box()
        assert (the_map["width"], the_map["height"]) == tuple(
            web.page.evaluate("() => [innerWidth, innerHeight]"))


def test_page_weight(open_page, seeded):
    """Escenario: Peso al abrir (iPhone en WebKit, sin caché, ≤ 300 KB)."""
    responses = []

    def record(web):
        web.page.on("response", lambda response: responses.append(response))
    web = open_page(geo=GRANT, clock=False, before_goto=record)
    wait_results(web)
    own = [r for r in responses if r.url.startswith(web.base + "/") and "/api/" not in r.url]
    total = sum(len(r.body()) for r in own)
    assert total <= 300 * 1024, total
    kinds = {r.request.resource_type for r in own}
    assert "font" not in kinds
    images = [r.url for r in own if r.request.resource_type == "image"]
    assert images in ([], [web.base + "/favicon.ico"])


# --- Refuerzos de la revisión de cobertura -------------------------------------------

def test_without_colour(mocked):
    """Escenario: Sin color (escala de grises): cada gasolinera se identifica y
    compara por el precio escrito en su marcador y en su fila."""
    web = mocked("nearby_legend")
    web.page.evaluate("() => document.documentElement.style.setProperty('filter', 'grayscale(1)')")
    assert web.page.evaluate("() => getComputedStyle(document.documentElement).filter") == "grayscale(1)"
    expand(web)
    on_map = dict(web.page.eval_on_selector_all(
        ".price-marker", "els => els.map(e => [e.dataset.id, e.querySelector('.label').textContent])"))
    in_list = dict(web.page.eval_on_selector_all(
        ".station-row", "els => els.map(e => [e.dataset.id, e.querySelector('.price').textContent])"))
    assert set(on_map) == set(in_list) and len(on_map) == 4
    for station_id, label in on_map.items():
        assert label and in_list[station_id].startswith(label), station_id
    prices = [float(p.split()[0].replace(",", ".")) for p in in_list.values()]
    assert sorted(prices) == [1.299, 1.399, 1.459, 1.459]
    assert web.page.locator(".price-marker .label").evaluate_all(
        "els => els.every(e => e.getBoundingClientRect().width > 0)")


def test_no_list_when_there_are_no_results(mocked):
    """Escenario: Sin lista que mostrar (búsqueda sin resultados): ni «Ver lista»
    ni la más barata, y el aviso sigue en la hoja."""
    web = mocked("nearby_madrid", "nearby_empty_gasoleo")
    search_again(web, 25)
    web.page.wait_for_selector("#message:not([hidden])")
    assert not web.page.locator("#toggle").is_visible()
    assert not web.page.locator("#cheapest").is_visible()
    inside = web.page.evaluate("""() => { const m = document.getElementById('message');
        const p = document.getElementById('panel'); const a = m.getBoundingClientRect(),
        b = p.getBoundingClientRect();
        return p.contains(m) && a.top >= b.top - 1 && a.bottom <= b.bottom + 1; }""")
    assert inside


def test_no_own_tile_store_after_using_the_page(open_page, seeded):
    """Escenario: Sin almacén propio de teselas, tras buscar, abrir una ficha,
    pinchar en otro punto y hacer zoom."""
    web = open_page(geo=GRANT, clock=False)
    wait_results(web)
    tap_marker(web, "1001")
    web.page.wait_for_selector("#detail:not([hidden])")
    web.press("#detail-close")
    click_map(web, *BARCELONA)
    wait_until(web, lambda: len(nearby_calls(web)) == 2)
    web.page.evaluate("() => window.__mapView.map.leaflet.setZoom(15, {animate: false})")
    web.page.wait_for_load_state("networkidle")
    assert web.guard.tiles
    stores = web.page.evaluate("""async () => ({
        workers: navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0,
        caches: window.caches ? (await caches.keys()).length : 0 })""")
    assert stores == {"workers": 0, "caches": 0}
