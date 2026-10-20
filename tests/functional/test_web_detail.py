"""Escenarios funcionales de la ficha completa (add-station-detail, spec
`station-detail`): carga del detalle, horario, precios, captura, peticiones,
errores y textos. Respuestas fijas de `tests/fixtures/web/`; por defecto en el
iPhone (WebKit) y lo común también en el Pixel 7 (design.md D11).
"""

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.fixtures.web.make_web_fixtures import (
    CAPTURE, NEWER_CAPTURE, detail, nearby, price, station)
from tests.functional.test_web_search import GRANT, KEY, expand, row, rows, tap_marker
from tests.web_helpers import click_map, wait_until

pytestmark = pytest.mark.browser

LOADING = "Cargando horario…"
LOADED = "Ficha cargada"
UNEXPECTED = "El servidor ha dado una respuesta inesperada"
UNREACHABLE = ("No se puede conectar con el servidor. Comprueba que está en marcha y que el "
               "túnel está abierto.")
SERVER_ERROR = "El servidor ha dado un error. Inténtalo más tarde."
BUSY = "El servidor está ocupado; inténtalo en unos segundos"
HEAD = ["REPSOL", "CALLE MAYOR, 1", "Madrid", "1,459 €/l", "0,0 km"]


def fuel_pref(slug):
    return f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(json.dumps({'fuel': slug}))})"


@pytest.fixture
def opened(open_page):
    """Abre la web con combustibles, salud y cercanas fijos y, para cada
    gasolinera de `details`, las respuestas de su `/api/stations/{id}` en orden.
    Devuelve la página con `web.details[id]` (el `ApiMock` de cada una)."""
    def open_(nearby_spec="nearby_detail", details=None, device="iphone", fuel=None,
              hold=(), geo=GRANT, clock=False, **kwargs):
        mocks_by_id = {}

        def mocks(web):
            web.mock("/api/fuels", "fuels_ok")
            web.mock("/api/health", "health_ok")
            if isinstance(nearby_spec, (list, tuple)):
                web.mock("/api/stations/nearby", *nearby_spec)
            else:
                web.mock("/api/stations/nearby", nearby_spec)
            for sid, specs in (details or {}).items():
                specs = specs if isinstance(specs, (list, tuple)) else [specs]
                mocks_by_id[sid] = web.mock(f"/api/stations/{sid}", *specs, hold=sid in hold)
        scripts = [fuel_pref(fuel)] if fuel else []
        web = open_page(device=device, geo=geo, clock=clock, before_goto=mocks,
                        init_scripts=scripts, **kwargs)
        web.details = mocks_by_id
        if geo is GRANT:
            web.page.wait_for_selector("#count:not([hidden])")
        return web
    return open_


def open_station(web, sid):
    tap_marker(web, sid)
    web.page.wait_for_selector("#detail:not([hidden])")


def status(web):
    return web.page.locator("#detail-status").text_content()


def wait_status(web, text):
    web.page.wait_for_function(
        "(t) => document.getElementById('detail-status').textContent === t", arg=text)


def head(web):
    return [line for line in web.page.locator("#detail-head").inner_text().split("\n") if line]


def schedule(web):
    return web.page.locator("#detail-schedule li").all_text_contents()


def prices(web):
    return web.page.locator("#detail-prices li").all_text_contents()


def detail_calls(web):
    return [urlsplit(r["url"]).path for r in web.guard.requests
            if urlsplit(r["url"]).path.startswith("/api/stations/")
            and urlsplit(r["url"]).path != "/api/stations/nearby"]


def info_visible(web):
    return web.page.locator("#detail-info").is_visible()


def retry_visible(web):
    return web.page.locator("#detail-retry").is_visible()


def schedule_of(text):
    return detail("4375", text, [price("gasoleo-a", 1.459)])


# --- Carga del detalle al abrir la ficha -----------------------------------------

@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_open_detail(opened, device):
    """Escenario: Abrir la ficha (datos de la búsqueda y «Cargando horario…»)."""
    web = opened(details={"4375": "station_4375"}, hold={"4375"}, device=device)
    open_station(web, "4375")
    wait_status(web, LOADING)
    assert head(web) == HEAD
    assert web.details["4375"].calls == [web.base + "/api/stations/4375"]
    assert not info_visible(web)


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_detail_arrives(opened, device):
    """Escenario: Llega el detalle."""
    web = opened(details={"4375": "station_4375"}, hold={"4375"}, device=device)
    open_station(web, "4375")
    wait_status(web, LOADING)
    web.details["4375"].release()
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]
    assert prices(web) == ["Gasoleo A · 1,459 €/l Buscado", "Gasolina 95 E5 · 1,529 €/l"]
    assert head(web) == HEAD
    assert LOADING not in web.page.locator("#detail").inner_text()


def test_detail_with_different_fixed_data(opened):
    """Escenario: Detalle con datos fijos distintos."""
    other = detail("4375", "L-D: 24H", [price("gasoleo-a", 1.459)], brand="REPSOL BUTANO")
    web = opened(details={"4375": other})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert head(web)[0] == "REPSOL"
    assert "REPSOL BUTANO" not in web.page.locator("#detail").inner_text()


def test_identifier_with_special_characters(opened):
    """Escenario: Identificador con caracteres especiales (API simulada)."""
    odd = nearby([station("12/3?x", 1.459, 0.04, lat=40.416775, lon=-3.70379)])
    web = opened(odd, details={"12%2F3%3Fx": detail("12/3?x", "L-D: 24H",
                                                     [price("gasoleo-a", 1.459)])})
    open_station(web, "12/3?x")
    wait_status(web, LOADED)
    assert web.details["12%2F3%3Fx"].calls == [web.base + "/api/stations/12%2F3%3Fx"]


@pytest.mark.parametrize("sid", ["", 4375], ids=["vacio", "numero"])
def test_station_without_valid_identifier(opened, sid):
    """Escenario: Gasolinera de la búsqueda sin identificador válido."""
    odd = nearby([station(sid, 1.459, 0.04, lat=40.416775, lon=-3.70379)])
    web = opened(odd)
    tap_marker(web, str(sid))
    web.page.wait_for_selector("#detail:not([hidden])")
    wait_status(web, UNEXPECTED)
    web.page.wait_for_timeout(200)
    assert detail_calls(web) == []
    assert not retry_visible(web)
    assert head(web) == HEAD
    link = web.page.locator("#detail-directions")
    assert link.is_visible() and link.get_attribute("href") == (
        "https://maps.apple.com/?daddr=40.416775,-3.70379")


# --- Horario tal como lo publica el Ministerio -----------------------------------

@pytest.mark.parametrize(("text", "lines"), [
    ("L-J: 06:00-22:30; V: 06:00-23:00; S: 06:45-23:00; D: 07:45-22:30",
     ["L-J: 06:00-22:30", "V: 06:00-23:00", "S: 06:45-23:00", "D: 07:45-22:30"]),
    ("L-D: 24H", ["L-D: 24H"]),
    ("L-V: 09:00-13:30 y 16:00-18:30; S: 09:00-13:30",
     ["L-V: 09:00-13:30 y 16:00-18:30", "S: 09:00-13:30"]),
    ("L: 24H", ["L: 24H"]),
    ("L-V: 07:00-22:00;;  S: 08:00-14:00 ; ", ["L-V: 07:00-22:00", "S: 08:00-14:00"]),
], ids=["varios", "uno", "dos-franjas", "L-24H", "vacios"])
def test_schedule(opened, text, lines):
    """Escenarios: Varios tramos, Un solo tramo, Dos franjas, Abreviatura ambigua y
    Tramos vacíos y espacios."""
    web = opened(details={"4375": schedule_of(text)})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert schedule(web) == lines
    assert not web.page.locator("#detail-no-schedule").is_visible()


def test_odd_schedule_not_interpreted(opened):
    """Escenario: Formato raro sin interpretar."""
    web = opened(details={"4375": schedule_of(
        "L: 06:30-22:30; M-D: 06:30-14:29 y 14:30-22:30 (festivos cerrado)")})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert schedule(web) == ["L: 06:30-22:30", "M-D: 06:30-14:29 y 14:30-22:30 (festivos cerrado)"]
    text = web.page.locator("#detail").inner_text()
    assert "Abierta" not in text and "Cerrada" not in text


@pytest.mark.parametrize("value", [None, ";", 24], ids=["null", "punto-coma", "numero"])
def test_no_schedule(opened, value):
    """Escenario: Sin horario."""
    web = opened(details={"4375": schedule_of(value)})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert schedule(web) == []
    assert web.page.locator("#detail-no-schedule").inner_text() == "Horario no disponible"
    assert prices(web) == ["Gasoleo A · 1,459 €/l Buscado"]


# --- Precios de todos los combustibles -------------------------------------------

def test_searched_fuel_first(opened):
    """Escenario: Buscado el primero (se busca Gasolina 95 E5)."""
    full = detail("4375", "L-D: 24H", [price("adblue", 0.899), price("gasoleo-a", 1.459),
                                       price("gasolina-95-e5", 1.529)])
    web = opened(details={"4375": full}, fuel="gasolina-95-e5")
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert prices(web) == ["Gasolina 95 E5 · 1,529 €/l Buscado", "Adblue · 0,899 €/l",
                           "Gasoleo A · 1,459 €/l"]
    assert web.page.locator("#detail-prices .searched").count() == 1


def test_other_unit(opened):
    """Escenario: Otra unidad."""
    hydrogen = detail("4375", "L-D: 24H", [price("hidrogeno", 12.95), price("gasoleo-a", 1.459)])
    web = opened(details={"4375": hydrogen})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert prices(web) == ["Gasoleo A · 1,459 €/l Buscado", "Hidrogeno · 12,950 €/kg"]


def test_no_prices(opened):
    """Escenario: Sin precios."""
    web = opened(details={"4375": detail("4375", "L-D: 24H", [])})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert prices(web) == []
    assert web.page.locator("#detail-no-prices").inner_text() == (
        "No hay precios de esta gasolinera en la última captura")
    assert schedule(web) == ["L-D: 24H"]


def test_searched_fuel_missing(opened):
    """Escenario: El buscado ya no aparece."""
    web = opened(details={"4375": detail("4375", "L-D: 24H", [price("gasolina-95-e5", 1.529)])})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert prices(web) == ["Gasolina 95 E5 · 1,529 €/l"]
    assert "1,459 €/l" in head(web)


def test_invalid_price_items(opened):
    """Escenario: Elementos no válidos."""
    e5 = price("gasolina-95-e5", 1.529)
    items = [price("gasoleo-a", 1.459), {**e5, "name": None}, {**e5, "price": None},
             {**e5, "price": "1,5"}, {**e5, "price": 0}]
    web = opened(details={"4375": detail("4375", "L-D: 24H", items)})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert prices(web) == ["Gasoleo A · 1,459 €/l Buscado"]
    assert "descart" not in web.page.locator("#detail").inner_text()


def test_no_valid_price(opened):
    """Escenario: Ningún precio válido (respuesta inesperada con «Reintentar»)."""
    e5 = price("gasolina-95-e5", 1.529)
    items = [{**price("gasoleo-a", 1.459), "name": None}, {**e5, "price": None}]
    web = opened(details={"4375": detail("4375", "L-D: 24H", items)})
    open_station(web, "4375")
    wait_status(web, UNEXPECTED)
    assert retry_visible(web)
    assert not info_visible(web)
    assert "No hay precios" not in web.page.locator("#detail").inner_text()


def test_searched_price_from_newer_capture(opened):
    """Escenario: Precio del buscado distinto en una captura más nueva."""
    web = opened(details={"4375": "station_4375_newer"}, timezone_id="UTC")
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert "1,459 €/l" in head(web)
    assert prices(web)[0] == "Gasoleo A · 1,479 €/l Buscado"
    assert web.page.locator("#detail-newer").inner_text() == (
        "Horario y precios de una captura más reciente: del 16/10/2026 a las 10:26 "
        "(hora de Madrid)")


@pytest.mark.parametrize("variant", ["null", "objeto", "sin-prices"])
def test_prices_not_a_list(opened, variant):
    """Escenario: Precios no es una lista."""
    spec = detail("4375", "L-D: 24H", [])
    data = spec["body"]["data"]
    if variant == "sin-prices":
        del data["prices"]
    else:
        data["prices"] = None if variant == "null" else {"gasoleo-a": 1.459}
    web = opened(details={"4375": spec})
    open_station(web, "4375")
    wait_status(web, UNEXPECTED)
    assert retry_visible(web) and not info_visible(web)


# --- Captura del detalle más nueva que la de la búsqueda --------------------------

def test_newer_capture_notice(opened):
    """Escenario: Captura nueva entre la búsqueda y la ficha (navegador en UTC)."""
    web = opened(details={"4375": "station_4375_newer"}, timezone_id="UTC")
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert web.page.locator("#detail-newer").inner_text() == (
        "Horario y precios de una captura más reciente: del 16/10/2026 a las 10:26 "
        "(hora de Madrid)")


@pytest.mark.parametrize(("nearby_capture", "detail_capture"), [
    (CAPTURE, CAPTURE),
    (CAPTURE, None),
    (CAPTURE, {"downloaded_at": "ayer", "source_date": None}),
    (NEWER_CAPTURE, CAPTURE),
    (None, NEWER_CAPTURE),
], ids=["misma", "sin-captura", "ayer", "anterior", "busqueda-sin-fecha"])
def test_no_newer_capture_notice(opened, nearby_capture, detail_capture):
    """Escenarios: Misma captura, Captura del detalle desconocida, Captura del detalle
    anterior y Búsqueda sin fecha de captura."""
    near = nearby([station("4375", 1.459, 0.04, lat=40.416775, lon=-3.70379)],
                  capture=nearby_capture)
    spec = detail("4375", "L-D: 24H", [price("gasoleo-a", 1.459)], capture=detail_capture)
    web = opened(near, details={"4375": spec}, timezone_id="UTC")
    if nearby_capture is None:
        assert web.page.locator("#capture").text_content() == "Fecha de la captura desconocida"
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert not web.page.locator("#detail-newer").is_visible()
    assert schedule(web) == ["L-D: 24H"]
    assert prices(web) == ["Gasoleo A · 1,459 €/l Buscado"]


# --- Una petición por gasolinera y búsqueda y sin respuestas de otra ficha --------

def close(web):
    web.press("#detail-close")
    web.page.wait_for_selector("#detail", state="hidden")


def release_each(mock, order=None):
    """Contesta las peticiones retenidas en el orden pedido; las que el navegador
    ya abortó (búsqueda nueva) fallan al contestar y se ignoran."""
    held, mock.held = mock.held, []
    for index in (order or range(len(held))):
        route, spec = held[index]
        try:
            mock._answer(route, spec)
        except Exception:
            pass


def record_schedules(web):
    """Anota cada texto que llega a tener la lista del horario."""
    web.page.evaluate("""() => { window.__seen = [];
        new MutationObserver(() => window.__seen.push(
            document.getElementById('detail-schedule').textContent))
        .observe(document.getElementById('detail-schedule'), {childList: true, subtree: true,
                                                               characterData: true}); }""")


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_reopen_same_detail(opened, device):
    """Escenario: Reabrir la misma ficha (desde la lista)."""
    web = opened(details={"4375": "station_4375"}, device=device)
    open_station(web, "4375")
    wait_status(web, LOADED)
    close(web)
    expand(web)
    web.press('.station-row[data-id="4375"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    assert info_visible(web)  # horario y precios ya están, sin «Cargando horario…»
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]
    assert len(web.details["4375"].calls) == 1


def test_reopen_while_loading(opened):
    """Escenario: Reabrir mientras llega."""
    web = opened(details={"4375": "station_4375"}, hold={"4375"})
    open_station(web, "4375")
    wait_status(web, LOADING)
    close(web)
    open_station(web, "4375")
    wait_status(web, LOADING)
    web.details["4375"].release()
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]
    assert len(web.details["4375"].calls) == 1


def test_three_details(opened):
    """Escenario: Tres fichas."""
    web = opened("nearby_madrid", details={"1001": "station_1001", "1002": "station_1002",
                                           "1003": "station_1003"})
    for sid in ("1001", "1002", "1003", "1001"):
        open_station(web, sid)
        wait_status(web, LOADED)
        close(web)
    assert sorted(detail_calls(web)) == ["/api/stations/1001", "/api/stations/1002",
                                         "/api/stations/1003"]


def test_new_search_forgets_details(opened):
    """Escenario: Nueva búsqueda (cambiar el radio a 25 km)."""
    web = opened(details={"4375": "station_4375"})
    open_station(web, "4375")
    wait_status(web, LOADED)
    close(web)
    web.page.select_option("#radius", "25")
    web.page.wait_for_function("() => window.__mapView.state.radius === 25")
    web.page.wait_for_selector("#count:not([hidden])")
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert detail_calls(web) == ["/api/stations/4375", "/api/stations/4375"]


def test_location_search_forgets_details(opened):
    """Escenario: Nueva búsqueda, también la de la ubicación del navegador
    (probada con «Volver a mi ubicación»)."""
    web = opened(details={"4375": "station_4375"})
    open_station(web, "4375")
    wait_status(web, LOADED)
    close(web)
    nearby_before = len(web.guard.api_calls("/api/stations/nearby"))
    web.press("#back-to-location")
    web.page.wait_for_function(
        f"() => performance.getEntriesByType('resource').filter("
        f"e => e.name.includes('/api/stations/nearby')).length > {nearby_before}")
    web.page.wait_for_selector("#count:not([hidden])")
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert detail_calls(web) == ["/api/stations/4375", "/api/stations/4375"]


def test_response_from_previous_search(opened):
    """Escenario: Respuesta de una búsqueda anterior (la vieja llega después)."""
    web = opened(details={"4375": ["station_4375", schedule_of("L-S: 07:00-21:00")]},
                 hold={"4375"})
    open_station(web, "4375")
    wait_status(web, LOADING)
    click_map(web, 40.4168, -3.7038)  # otro punto: búsqueda nueva con la ficha abierta
    web.page.wait_for_selector("#detail", state="hidden")
    web.page.wait_for_selector("#count:not([hidden])")
    open_station(web, "4375")
    wait_status(web, LOADING)
    mock = web.details["4375"]
    wait_until(web, lambda: len(mock.calls) == 2)
    record_schedules(web)
    release_each(mock, order=[1, 0])  # primero la nueva; la vieja, abortada, después
    wait_status(web, LOADED)
    web.page.wait_for_timeout(300)
    assert schedule(web) == ["L-S: 07:00-21:00"]
    assert not any("L-D: 24H" in text for text in web.page.evaluate("() => window.__seen"))


def test_quiet_page_with_detail_open(opened):
    """Escenario: Página quieta con la ficha abierta (5 minutos)."""
    web = opened(details={"4375": "station_4375"}, clock=True)
    open_station(web, "4375")
    wait_status(web, LOADED)
    before = len([r for r in web.guard.requests if "/api/" in r["url"]])
    web.page.clock.run_for(5 * 60 * 1000)
    web.page.wait_for_timeout(300)
    assert len([r for r in web.guard.requests if "/api/" in r["url"]]) == before


@pytest.mark.parametrize("device", ["iphone", "pixel"])
def test_switch_detail_before_response(opened, device):
    """Escenario: Cambiar de ficha antes de la respuesta."""
    web = opened("nearby_madrid", details={"1001": "station_1001", "1002": "station_1002"},
                 hold={"1001"}, device=device)
    open_station(web, "1001")
    wait_status(web, LOADING)
    open_station(web, "1002")
    record_schedules(web)
    wait_status(web, LOADED)
    assert schedule(web) == ["L-S: 07:00-21:00"]
    web.details["1001"].release()
    web.page.wait_for_timeout(300)
    assert schedule(web) == ["L-S: 07:00-21:00"]
    assert not any("L-D: 24H" in text for text in web.page.evaluate("() => window.__seen"))
    close(web)
    open_station(web, "1001")
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]
    assert len(web.details["1001"].calls) == 1


@pytest.mark.parametrize("variant", ["otro", "numero", "sin-id"])
def test_response_with_other_identifier(opened, variant):
    """Escenario: Respuesta con otro identificador."""
    spec = detail("1001", "L-D: 24H", [price("gasoleo-a", 1.459)])
    data = spec["body"]["data"]
    if variant == "otro":
        data["id"] = "1002"
    elif variant == "numero":
        data["id"] = 1001
    else:
        del data["id"]
    web = opened("nearby_madrid", details={"1001": spec})
    open_station(web, "1001")
    wait_status(web, UNEXPECTED)
    assert not info_visible(web) and schedule(web) == [] and prices(web) == []


def test_close_before_response(opened):
    """Escenario: Cerrar antes de la respuesta."""
    web = opened("nearby_madrid", details={"1001": "station_1001"}, hold={"1001"})
    expand(web)
    web.press('.station-row[data-id="1001"]')
    web.page.wait_for_selector("#detail:not([hidden])")
    close(web)
    listed = rows(web)
    web.details["1001"].release()
    web.page.wait_for_timeout(300)
    assert web.page.locator("#detail").is_hidden()
    assert rows(web) == listed
    assert row(web, "1001").is_visible()


# --- Límite de tiempo y errores del detalle ------------------------------------------

def retry_disabled(web):
    return web.page.locator("#detail-retry").is_disabled()


def run(web, ms):
    web.page.clock.run_for(ms)
    web.page.wait_for_timeout(50)


def test_detail_timeout(opened):
    """Escenario: Detalle que no contesta (15 s, con un margen de 1 s)."""
    web = opened(details={"4375": None}, clock=True)
    open_station(web, "4375")
    run(web, 100)
    assert status(web) == LOADING
    run(web, 13_900)  # 14 s
    assert status(web) == LOADING
    run(web, 2_000)  # 16 s
    wait_status(web, UNREACHABLE)
    assert retry_visible(web)
    assert head(web) == HEAD


@pytest.mark.parametrize(("spec", "seconds"), [
    ("busy_base_retry_5", 5), ("busy_api_retry_12", 12), ("busy_base_retry_abc", 5),
    ("long_query", 5),
], ids=["base-5", "api-12", "abc", "consulta-larga"])
def test_busy_with_retry_after(opened, spec, seconds):
    """Escenarios: Ocupado con Retry-After, Consulta demasiado larga y Ocupado con
    otro Retry-After o uno raro (margen de 0,5 s)."""
    web = opened(details={"4375": spec}, clock=True)
    open_station(web, "4375")
    run(web, 100)
    wait_status(web, BUSY)
    assert retry_visible(web) and retry_disabled(web)
    run(web, seconds * 1000 - 600)
    assert retry_disabled(web)
    run(web, 1_000)
    assert not retry_disabled(web)
    assert len(web.details["4375"].calls) == 1  # no se repite sola


def test_retry_succeeds_with_double_tap(opened):
    """Escenario: Reintentar con éxito (dos toques seguidos, respuesta que tarda)."""
    web = opened(details={"4375": ["busy_base_retry_5", "station_4375"]}, hold={"4375"},
                 clock=True)
    mock = web.details["4375"]
    open_station(web, "4375")
    wait_until(web, lambda: len(mock.held) == 1)
    mock.release()
    run(web, 100)
    wait_status(web, BUSY)
    run(web, 5_500)
    assert not retry_disabled(web)
    before = [r["url"] for r in web.guard.requests]
    web.page.evaluate("""() => { const b = document.getElementById('detail-retry');
        b.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        b.dispatchEvent(new MouseEvent('click', {bubbles: true})); }""")
    run(web, 100)
    wait_status(web, LOADING)
    assert not retry_visible(web)
    wait_until(web, lambda: len(mock.held) == 1)
    run(web, 1_000)
    mock.release()
    run(web, 100)
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]
    assert len(mock.calls) == 2
    new = [urlsplit(u).path for u in [r["url"] for r in web.guard.requests][len(before):]]
    assert "/api/stations/nearby" not in new and "/api/fuels" not in new


@pytest.mark.parametrize("variant", ["ningun-precio", "otro-id", "prices-no-lista"])
def test_retry_after_rejected_response(opened, variant):
    """«Reintentar» funciona tras un 200 rechazado (D6)."""
    bad = detail("4375", "L-D: 24H", [price("gasoleo-a", 1.459)])
    if variant == "ningun-precio":
        bad["body"]["data"]["prices"] = [{"slug": "gasoleo-a", "price": None}]
    elif variant == "otro-id":
        bad["body"]["data"]["id"] = "5120"
    else:
        bad["body"]["data"]["prices"] = None
    web = opened(details={"4375": [bad, "station_4375"]})
    open_station(web, "4375")
    wait_status(web, UNEXPECTED)
    web.press("#detail-retry")
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]


@pytest.mark.parametrize(("spec", "text"), [
    ("no_captures", "No hay datos disponibles. Detalle: todavía no hay capturas guardadas"),
    ("network_error", UNREACHABLE),
    ("bad_gateway_html", UNEXPECTED),
    ("proxy_503_html", UNEXPECTED),
    ("station_not_found", SERVER_ERROR),
    ("internal_error", SERVER_ERROR),
], ids=["sin-datos", "red", "html-502", "html-503", "404", "500"])
def test_detail_errors(opened, spec, text):
    """Escenarios: Sin datos, Red caída, Respuesta que no es JSON, 503 que no es JSON,
    Gasolinera no encontrada y Error interno."""
    web = opened(details={"4375": spec})
    open_station(web, "4375")
    wait_status(web, text)
    assert retry_visible(web) and not retry_disabled(web)
    shown = web.page.locator("#detail").inner_text()
    assert "Bad Gateway" not in shown and "nginx" not in shown
    assert "estacion_no_encontrada" not in shown and "no existe la estación" not in shown
    assert head(web) == HEAD
    assert web.page.locator("#detail-directions").is_visible()


def test_data_not_an_object(opened):
    """Escenario: Respuesta que no es JSON (200 con `data` que no es un objeto)."""
    spec = detail("4375", "L-D: 24H", [])
    spec["body"]["data"] = "no es un objeto"
    web = opened(details={"4375": spec})
    open_station(web, "4375")
    wait_status(web, UNEXPECTED)
    assert retry_visible(web)


def test_rest_of_page_unchanged(opened):
    """Escenario: El resto de la página sigue igual."""
    web = opened("nearby_madrid", details={"1001": "network_error"})
    count = web.page.locator("#count").inner_text()
    listed = rows(web)
    markers = web.page.eval_on_selector_all(".price-marker", "e => e.map(x => x.dataset.id)")
    open_station(web, "1001")
    wait_status(web, UNREACHABLE)
    close(web)
    assert web.page.locator("#count").inner_text() == count
    assert rows(web) == listed
    assert web.page.eval_on_selector_all(".price-marker",
                                         "e => e.map(x => x.dataset.id)") == markers
    assert web.page.locator("#message").is_hidden()
    assert web.page.locator("#retry").is_hidden()


def test_reopen_detail_with_error(opened):
    """Escenario: Reabrir una ficha con error."""
    web = opened(details={"4375": "network_error"})
    open_station(web, "4375")
    wait_status(web, UNREACHABLE)
    close(web)
    open_station(web, "4375")
    wait_status(web, UNREACHABLE)
    assert retry_visible(web)
    assert len(web.details["4375"].calls) == 1


def test_reopen_while_retry_waits(opened):
    """Escenario: Reabrir mientras «Reintentar» espera (cuenta desde el error)."""
    web = opened(details={"4375": "busy_base_retry_5"}, clock=True)
    open_station(web, "4375")
    run(web, 100)
    wait_status(web, BUSY)
    run(web, 2_000)
    close(web)
    open_station(web, "4375")
    run(web, 100)
    wait_status(web, BUSY)
    assert retry_disabled(web)
    run(web, 2_300)  # ~4,4 s desde el error
    assert retry_disabled(web)
    run(web, 1_000)  # ~5,4 s desde el error; serían ~3,4 s desde la reapertura
    assert not retry_disabled(web)
    assert len(web.details["4375"].calls) == 1


# --- Textos del detalle como texto -----------------------------------------------

def test_schedule_with_markup(opened):
    """Escenario: Horario con etiquetas."""
    dialogs = []
    web = opened(details={"4375": schedule_of("<img src=x onerror=alert(1)>; L-D: 24H")})
    web.page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert schedule(web) == ["<img src=x onerror=alert(1)>", "L-D: 24H"]
    assert web.page.locator("#detail img").count() == 0
    web.page.wait_for_timeout(200)
    assert dialogs == []


def test_fuel_name_with_markup(opened):
    """Escenario: Nombre de combustible con etiquetas."""
    item = {**price("gasoleo-a", 1.459), "name": "<b>Gasoleo A</b>"}
    web = opened(details={"4375": detail("4375", "L-D: 24H", [item])})
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert prices(web) == ["<b>Gasoleo A</b> · 1,459 €/l Buscado"]
    assert web.page.locator("#detail-prices b").count() == 0


# --- Encaje con la API real -----------------------------------------------------------

def test_detail_against_real_api(open_page, web_db, web_server):
    """Escenario: Encaje del detalle con la API real ("4375" de «Estación con
    precios» de prices-api, en una base de prueba temporal)."""
    from tests.api_helpers import basic_db
    from tests.helpers import check_not_real_data

    check_not_real_data(web_db)
    basic_db(web_db)
    web = open_page(geo=GRANT, clock=False)
    web.page.wait_for_selector("#count:not([hidden])")
    open_station(web, "4375")
    wait_status(web, LOADED)
    assert schedule(web) == ["L-D: 24H"]
    assert prices(web) == ["Gasoleo A · 1,459 €/l Buscado", "Gasolina 95 E5 · 1,529 €/l"]
    assert detail_calls(web) == ["/api/stations/4375"]
    real_data = Path(__file__).resolve().parents[2] / "data"
    assert real_data not in web_db.resolve().parents  # base temporal, nunca ./data
